"""``Gateway``: a BHMS server that is also a client of many device servers (spec/bhms/01-overview.md, 13-security.md).

A gateway aggregates its upstreams under namespaced device ids, enforces its own authority and policy, grants leases that
span upstreams, isolates failures, journals the operations it forwards so idempotency survives restarts, fans ``stop``
out to every upstream, fans their events in, and serves clients over a Unix socket, WebSocket, Streamable HTTP and stdio.

Run one from a configuration file (see ``examples/bhms/gateway.toml`` and :mod:`bhms.gateway.config`)::

    python -m bhms.gateway examples/bhms/gateway.toml

or embed it::

    from bhms.gateway import Gateway, GatewayConfig, UpstreamConfig

    config = GatewayConfig(id="lab", state_dir=Path("state"), listen=("unix:/run/lab.sock",),
                           upstreams=(UpstreamConfig(name="bench", stdio="python bench_stage.py"),))
    async with Gateway(config) as gateway:
        await gateway.listen("unix:/run/lab.sock")
        ...

Clients cannot tell a gateway from a device server except through ``capabilities.gateway``; every protocol method of the
:class:`~bhms.client.client.Client` works unchanged against it (``programs/*`` is not offered: programs run inside a
device server).

Parts (one module each): :mod:`~bhms.gateway.config`, :mod:`~bhms.gateway.upstreams` (connections, isolation),
:mod:`~bhms.gateway.catalog` (namespacing, descriptions), :mod:`~bhms.gateway.policy` (narrowing, named refusals),
:mod:`~bhms.gateway.journal` (forwarding journal), :mod:`~bhms.gateway.router` (the handlers),
:mod:`~bhms.gateway.leases` (cross-device leases), :mod:`~bhms.gateway.listen` (subscriptions, fan-in).

Lifecycle: :meth:`Gateway.start` opens the store, settles what a crash left in flight (every operation found
``dispatching``/``running`` is ``unknown`` until its upstream answers, BHMS-OPS-080), starts the upstream tasks and waits up
to ``connect_wait_ms`` for their first connection (an upstream that is not there yet does not prevent start-up: its devices
read ``offline`` until it connects). ``SIGHUP`` re-reads ``[principals]`` from the file and applies it to new admissions at
once (BHMS-SEC-012).

Thread-safety: one asyncio event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import ssl as ssl_module
from collections import deque
from typing import Any

from bhms.gateway.catalog import Catalog, gateway_id
from bhms.gateway.config import GatewayConfig, load_config
from bhms.gateway.journal import ForwardJournal
from bhms.gateway.leases import GatewayLeases
from bhms.gateway.listen import GatewayObservations, GatewaySubscriptions
from bhms.gateway.policy import GatewayPolicy
from bhms.gateway.router import Router
from bhms.gateway.upstreams import Upstream, UpstreamHooks
from bhms.jsonrpc.dispatcher import Server as RpcServer
from bhms.jsonrpc.session import RequestContext
from bhms.protocol import schema
from bhms.protocol.errors import BhmsError
from bhms.runtime.authority import Authenticator, Policy, Principal
from bhms.runtime.events import EventLog
from bhms.runtime.heap import freeze_startup_heap
from bhms.runtime.leases import Lease
from bhms.runtime.store import Store, StoreError

log = logging.getLogger("bhms.gateway")


class _Hooks(UpstreamHooks):
    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway

    def status_changed(self, upstream: Upstream, old: str, new: str, cause: str) -> None:
        self.gateway.upstream_status(upstream, old, new, cause)

    def catalog_changed(self, upstream: Upstream) -> None:
        self.gateway.upstream_catalog(upstream)

    def notification(self, upstream: Upstream, method: str, params: dict[str, Any]) -> None:
        self.gateway.upstream_notification(upstream, method, params)

    def events_gap(self, upstream: Upstream) -> None:
        self.gateway.record("device.degraded", severity="warning",
                            message=f"events of upstream {upstream.name} may be missing (its retention no longer "
                                    "covers the gap since the gateway last read them)")


class Gateway:
    """A BHMS gateway; see the module docstring.

    Args:
        config: a :class:`~bhms.gateway.config.GatewayConfig` (``load_config(path)`` reads one from TOML).
        memory: keep the journal in memory (no durability, a new epoch every start): tests and throw-away gateways.
    """

    def __init__(self, config: GatewayConfig, *, memory: bool = False) -> None:
        self.config = config
        self.memory = memory
        self.policy = GatewayPolicy(Policy(config.principals, trust_same_uid=config.trust_same_uid))
        self.auth = Authenticator(lambda: self.policy.policy)
        self.catalog = Catalog()
        self.upstreams: dict[str, Upstream] = {}
        self.rpc: RpcServer | None = None
        self.listeners: list[Any] = []
        self._started = False
        self._closing: asyncio.Event | None = None
        self._journal_ok = True
        self._validator: asyncio.Task[None] | None = None
        self._unvalidated: deque[tuple[str, str]] = deque()  # (device id, upstream digest) awaiting schema validation
        self._wake_validator = asyncio.Event()
        self._validating = False
        self.observations: GatewayObservations
        self.subscriptions: GatewaySubscriptions
        self.leases: GatewayLeases
        self.router: Router
        self.journal: ForwardJournal
        self.events: EventLog
        self.store: Store

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Open the journal, settle what a crash left, connect the upstreams and register every method (idempotent)."""
        if self._started:
            return
        cfg = self.config
        self.store = Store(None if self.memory else cfg.state_dir / f"{cfg.id}.sqlite3", durability=cfg.durability)
        try:
            self._closing = asyncio.Event()
            self.journal = ForwardJournal(self.store)
            self.events = EventLog(self.store, retention_s=cfg.event_retention_s)
            self.observations = GatewayObservations(self)
            self.leases = GatewayLeases(self)
            self.router = Router(self)
            self.subscriptions = GatewaySubscriptions(self)  # type: ignore[arg-type]
            self.journal.recover_forwarded()  # BHMS-OPS-080: before any request is answered
            self.journal.convert_all_pending()  # forwards whose answer was never recorded are unknown operations
            self.store.prune_operations(["completed", "failed", "canceled", "rejected"],
                                        _ns_ago(cfg.key_retention_s))
            self.events.prune()
            self.router.start()
            hooks = _Hooks(self)
            for entry in cfg.upstreams:
                up = Upstream(entry, hooks, event_cursor=self.store.meta_get(f"cursor:{entry.name}"))
                self.upstreams[entry.name] = up
                up.start()
            await asyncio.gather(*(up.wait_ready(cfg.connect_wait_ms / 1000) for up in self.upstreams.values()))
            self.policy.check_loadable(self.catalog)  # BHMS-SEC-011
            self.rpc = self._make_rpc()
            self._started = True
            self._validator = asyncio.get_running_loop().create_task(self._validate_loop(), name="bhms-gateway-validate")
        except BaseException:
            await self._teardown()
            raise

    def _make_rpc(self) -> RpcServer:
        cfg = self.config
        caps: dict[str, Any] = {
            "devices": {"listChanged": True},
            "observations": {"subscribe": True, "minIntervalMs": cfg.observation_min_interval_ms},
            "operations": {"durable": self.store.durable, "cancel": True, "resolve": True,
                           "keyRetentionS": cfg.key_retention_s if self.store.durable else 0},
            "stop": {}, "subscriptions": {"maxObservations": 256, "maxOperationIds": 256},
            "leases": self.leases.capability,
            "events": {"retentionS": cfg.event_retention_s, "maxPageSize": cfg.max_page_size},
            "gateway": {"crossDeviceLeases": True, "upstreams": len(cfg.upstreams)}}
        authority = self.policy.policy.authority_capability()
        if authority is not None:
            caps["authority"] = authority

        def principal(peer: Any) -> dict[str, Any] | None:
            found = self.policy.policy.resolve(peer)
            return found.wire() if found is not None else None

        rpc = RpcServer(server_info={"name": cfg.id, "version": "0.1.0", "title": "BHMS gateway"}, capabilities=caps,
                        epoch=self.store.epoch, instructions=cfg.instructions, principal=principal,
                        max_page_size=cfg.max_page_size, max_wait_ms=cfg.max_wait_ms)
        self.router.register(rpc)
        return rpc

    async def _teardown(self) -> None:
        for task in (self._validator,):
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self._validator = None
        for attr in ("router", "observations"):
            part = getattr(self, attr, None)
            if part is not None:
                await part.close()
        if getattr(self, "leases", None) is not None:
            self.leases.close()
        await asyncio.gather(*(up.close() for up in self.upstreams.values()), return_exceptions=True)
        if getattr(self, "store", None) is not None:
            self.store.close()

    async def close(self) -> None:
        """End subscriptions (``endReason: shutdown``), close connections and upstreams, close the journal."""
        if not self._started:
            return
        self._started = False
        assert self._closing is not None
        self._closing.set()
        await self.subscriptions.drain(1.0)
        if self.rpc is not None:
            await self.rpc.close()  # connections first: a listener waits for its live connections to end
        for listener in self.listeners:
            await listener.close()
        self.listeners.clear()
        await self._teardown()

    async def __aenter__(self) -> Gateway:
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------ serving

    async def listen(self, url: str, *, ssl: ssl_module.SSLContext | None = None) -> Any:
        """Accept clients on ``unix:<path>``, ``ws[s]://host:port`` or ``http[s]://host:port[/path]`` (Streamable HTTP).

        WebSocket and HTTP need a bearer token that maps to a principal of the policy (BHMS-SEC-001); a non-loopback
        address needs TLS (BHMS-SEC-004). Returns the listener (``await listener.close()``).
        """
        from bhms.transport import serve_unix, serve_websocket
        from bhms.transport.stream import is_loopback

        await self.start()
        assert self.rpc is not None
        if url.startswith("unix:"):
            path = url[len("unix:"):]
            listener = await serve_unix(path[2:] if path.startswith("//") else path, self.rpc.handle_connection)
        elif url.startswith(("ws://", "wss://", "http://", "https://")):
            scheme, host, port, path = _parse(url, default_path=self.config.http_path)
            if not is_loopback(host) and ssl is None:
                raise ValueError(f"refusing to serve {url} without TLS: a non-loopback listener must use TLS "
                                 "(BHMS-SEC-004); pass ssl=<SSLContext> or bind 127.0.0.1")
            authenticate = lambda token: self.policy.policy.by_token(token) is not None  # noqa: E731
            if scheme.startswith("ws"):
                listener = await serve_websocket(host, port, self.rpc.handle_connection, authenticate=authenticate,
                                                 ssl=ssl)
            else:
                from bhms.transport.http import serve_http

                listener = await serve_http(host, port, self.rpc, authenticate=authenticate, path=path, ssl=ssl)
        else:
            raise ValueError(f"unsupported listen url {url!r}; use unix:<path>, ws://host:port, http://host:port/bhms "
                             "or stdio")
        self.listeners.append(listener)
        return listener

    async def serve(self) -> None:
        """Serve ``config.listen`` until SIGINT/SIGTERM (or until the parent closes stdio when ``stdio`` is listed)."""
        await self.start()
        assert self.rpc is not None
        loop = asyncio.get_running_loop()
        stopped = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, stopped.set)
        with contextlib.suppress(NotImplementedError, RuntimeError, AttributeError):
            loop.add_signal_handler(signal.SIGHUP, self._sighup)
        try:
            # A gateway serving ten thousand devices holds hundreds of thousands of long-lived objects; a generation-2
            # collection over them pauses the loop for ~200 ms. They never die, so move them out of the collector's way.
            freeze_startup_heap()
            stdio = False
            for url in self.config.listen:
                if url == "stdio":
                    stdio = True
                else:
                    await self.listen(url)
                    log.info("gateway %s listening on %s", self.config.id, url)
            if stdio:
                await self.rpc.serve_stdio()
            else:
                await stopped.wait()
        finally:
            await self.close()

    def run(self) -> None:
        """Blocking entry point."""
        asyncio.run(self.serve())

    def _sighup(self) -> None:
        try:
            self.reload_policy()
            log.info("policy reloaded from %s", self.config.source)
        except Exception:  # noqa: BLE001 - a bad file must not take the gateway down; the old policy stays
            log.exception("policy reload failed; keeping the current policy")

    @property
    def devices(self) -> Catalog:
        """The catalog (the device view :class:`~bhms.server.listen.Subscriptions` expects of a server)."""
        return self.catalog

    # ------------------------------------------------------------------ authority

    def principal_of(self, ctx: RequestContext) -> Principal | None:
        return self.auth.principal_of(ctx)

    def set_policy(self, policy: Policy) -> None:
        """Replace the policy; new admissions follow it at once and ``policy.changed`` is recorded (BHMS-SEC-012).

        Raises ``ValueError`` (nothing changes) when a bound would widen a device's own (BHMS-SEC-011).
        """
        candidate = GatewayPolicy(policy)
        candidate.check_loadable(self.catalog)
        before = {p.id: p for p in self.policy.policy.principals}
        self.policy = candidate
        self.auth.reset()
        for principal_id, old in before.items():
            now = next((p for p in policy.principals if p.id == principal_id), None)
            if old.has("lease") and (now is None or not now.has("lease")):
                self.leases.manager.revoke_principal(principal_id)  # BHMS-AUTH-013
        self.record("policy.changed", message="the authorization policy changed")
        self.subscriptions.policy_changed()

    def reload_policy(self) -> None:
        """Re-read ``[principals]`` (and ``trust_same_uid``) from the configuration file and apply them."""
        if self.config.source is None:
            raise RuntimeError("this gateway was not loaded from a file; call set_policy() instead")
        fresh = load_config(self.config.source)
        self.set_policy(Policy(fresh.principals, trust_same_uid=fresh.trust_same_uid))

    # ------------------------------------------------------------------ journal health (BHMS-AUTH-025)

    @property
    def journal_ok(self) -> bool:
        return self._journal_ok

    def journal_failed(self, exc: Exception) -> None:
        if self._journal_ok:
            log.error("the journal cannot be written (%s); ordinary operations are refused until it can", exc)
        self._journal_ok = False

    def require_journal(self) -> None:
        if self._journal_ok or self.store.probe_writable():
            self._journal_ok = True
            return
        raise BhmsError("BUSY", "the gateway's journal cannot be written; new operations are refused until it can",
                        retry="same-key", hint="retry later with the same operationKey; stop remains available "
                                               "(gateway rule: isolation:journal)")

    # ------------------------------------------------------------------ events and upstream callbacks

    def record(self, type: str, **kw: Any) -> dict[str, Any] | None:
        """Append an event to the gateway's log; a journal failure is noted, never raised."""
        try:
            return self.events.append(type, **kw)
        except StoreError as exc:
            self.journal_failed(exc)
            return None

    def lease_ended(self, lease: Lease, reason: str) -> None:
        self.record(f"lease.{reason}", severity="warning" if reason == "revoked" else "info",
                    data={"leaseId": lease.lease_id})

    def upstream_status(self, up: Upstream, old: str, new: str, cause: str) -> None:
        if self._closing is not None and self._closing.is_set():
            return
        if new in ("down", "stalled"):
            self.router.upstream_lost(up, cause)
            if old in ("up", "stalled"):
                for entry in self.catalog.entries_of(up.name):
                    self.record("device.offline", severity="warning", device_id=entry.device_id,
                                message=f"{entry.device_id} is offline: upstream {up.name} is {new} ({cause})"[:1000])
        elif new == "up":
            if up.connections > 1 or old == "stalled":
                for entry in self.catalog.entries_of(up.name):
                    self.record("device.online", device_id=entry.device_id,
                                message=f"{entry.device_id} is online again (upstream {up.name})")
            self.router.upstream_back(up)
            self.router.spawn(self.leases.release_orphans(up.name))

    def upstream_catalog(self, up: Upstream) -> None:
        known = {e.device_id: e.upstream_description["digest"] for e in self.catalog.entries_of(up.name)}
        if self.catalog.replace_upstream(up.name, up.descriptions, up.summaries):
            for uid, description in up.descriptions.items():
                device_id = gateway_id(up.name, uid)
                if known.get(device_id) != description["digest"] and device_id in self.catalog:
                    self._unvalidated.append((device_id, description["digest"]))
            self._wake_validator.set()
            if self._started:
                self.subscriptions.devices_changed()

    async def wait_validated(self, timeout: float = 300.0) -> bool:
        """Wait until every served description has been schema-validated; False on timeout."""
        deadline = asyncio.get_running_loop().time() + timeout
        while self._unvalidated or self._validating:
            if asyncio.get_running_loop().time() > deadline:
                return False
            await asyncio.sleep(0.05)
        return True

    async def _validate_loop(self) -> None:
        """Validate every newly served description against the schema (BHMS-SEC-021), one at a time, yielding to the
        event loop between descriptions; a device whose description is invalid stops being served."""
        while True:
            while not self._unvalidated:
                self._wake_validator.clear()
                await self._wake_validator.wait()
            device_id, upstream_digest = self._unvalidated.popleft()
            self._validating = True
            entry = self.catalog.get(device_id)
            if entry is None or entry.upstream_description["digest"] != upstream_digest:
                self._validating = False
                continue
            try:
                schema.validate("DeviceDescription", entry.upstream_description)
            except BhmsError as exc:
                log.error("not serving %s: its description is not a valid DeviceDescription at %s: %s",
                          device_id, exc.field or "/", exc.message)
                self.catalog.drop(device_id)
                self.record("device.degraded", severity="error", device_id=device_id,
                            message="the upstream's description is invalid and the device is no longer served")
                self.subscriptions.devices_changed()
            self._validating = False
            await asyncio.sleep(0)

    def upstream_notification(self, up: Upstream, method: str, params: dict[str, Any]) -> None:
        if method == "notifications/operation":
            self.router.on_operation_notification(up, params["operation"])
        elif method == "notifications/event":
            event = params["event"]
            try:
                with self.store.transaction():  # the event and the cursor it came from commit together: no duplicate
                    self._ingest(up, event)     # after a restart, no gap
                    self.store.meta_set(f"cursor:{up.name}", event["cursor"])
            except StoreError as exc:
                self.journal_failed(exc)

    def _ingest(self, up: Upstream, event: dict[str, Any]) -> None:
        """Re-record an upstream event in the gateway's log with the gateway's ids and cursor (see
        :mod:`bhms.gateway.listen`)."""
        kind = event["type"]
        if kind == "policy.changed":
            return  # the upstream's policy is not the gateway's
        op_id = event.get("operationId")
        gateway_op = self.router.gateway_operation_id(up.name, op_id) if op_id else None
        if kind == "operation.state" and gateway_op is None:
            return  # an operation the gateway did not forward is not this gateway's to report
        data = event.get("data")
        if kind.startswith("lease.") and isinstance(data, dict):
            mapped = self.leases.gateway_lease_of(data.get("leaseId", ""))
            data = {**data, "leaseId": mapped} if mapped else {k: v for k, v in data.items() if k != "leaseId"}
        device = event.get("deviceId")
        purged_ids: list[str] = []
        if kind == "device.epoch" and isinstance(data, dict) and data.get("purged") is True:
            ids = data.get("operationIds")
            purged_ids = [i for i in ids if isinstance(i, str)] if isinstance(ids, list) else []
            if data.get("truncated") is True:
                log.warning("upstream %s: the purge proof for %s named only part of the operations dispatched before it; the "
                            "others stay inhibited until a confirmed stop or an operator resolves them", up.name, device)
            mapped_ids = [g for g in (self.router.gateway_operation_id(up.name, i) for i in purged_ids) if g]
            data = {**{k: v for k, v in data.items() if k != "operationIds"}, "operationIds": mapped_ids}  # this gateway's ids
        self.events.append(kind, severity=event.get("severity", "info"),
                           device_id=gateway_id(up.name, device) if device else None, operation_id=gateway_op,
                           message=event.get("message"), data=data or None)
        if purged_ids:
            self.router.endpoint_purged(up.name, purged_ids)



def _parse(url: str, *, default_path: str) -> tuple[str, str, int, str]:
    scheme, rest = url.split("://", 1)
    authority, _, path = rest.partition("/")
    host, sep, port = authority.rpartition(":")
    if not sep or not port.isdigit():
        raise ValueError(f"bad url {url!r}; expected {scheme}://host:port[/path]")
    return scheme, host.strip("[]"), int(port), "/" + path if path else default_path


def _ns_ago(seconds: int) -> int:
    from bhms.runtime.operations import now_ns

    return now_ns() - seconds * 1_000_000_000

