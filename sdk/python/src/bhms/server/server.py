"""``DeviceServer``: a complete, honest BHMS server for devices declared with decorators.

A working server in a few lines::

    from bhms import DeviceServer, Range

    srv = DeviceServer("bench-stage")
    stage = srv.device("stage-z", capabilities=["bhms.axis.linear"], resources=["stage-z"])

    @stage.property(unit="um", evidence="measured")
    def position() -> float: ...

    @stage.action(effect="reversible", idempotency="absolute", requires_lease=False,
                  completion_evidence="measured", max_duration_ms=5000)
    async def move_to(ctx, target: Range(0, 200, unit="um")) -> {"position": "um"}:
        ...
        await ctx.progress(0.5)
        return {"position": ...}

    if __name__ == "__main__":
        srv.run()        # stdio by default; srv.run("unix:/run/stage.sock"), srv.run("ws://127.0.0.1:8765")

``DeviceServer`` builds on :class:`bhms.jsonrpc.Server` and implements every method of the schema's ``x-bhms-methods``
(``server/discover``, ``devices/*``, ``properties/read``, ``actions/invoke``, ``operations/*``, ``stop``,
``subscriptions/listen``, ``leases/*``, ``events/read`` and ``programs/*``) over the durable runtime in
:mod:`bhms.runtime`: a SQLite journal (operations, events, programs, fences) under ``state_dir``
(``$BHMS_STATE_DIR``, else ``$XDG_STATE_HOME/bhms``, else ``~/.local/state/bhms``), recovered before the first request is
answered (BHMS-OPS-080).

Authentication comes from the transport (BHMS-SEC-001, :class:`~bhms.runtime.authority.Policy`): the stdio parent and
same-uid Unix peers are ``admin``; WebSocket clients present a bearer token (``token=``, ``$BHMS_TOKEN``, or a generated
one written to ``<state_dir>/<name>.token`` with mode 0600 — tokens are never logged, BHMS-SEC-002). A non-loopback
WebSocket listener needs ``ssl=`` (BHMS-SEC-004). TCP has no credential in this SDK and is refused.

Thread-safety: one asyncio event loop; declare devices before :meth:`start`.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import inspect
import logging
import os
import re
import secrets
import signal
import ssl as ssl_module
from pathlib import Path
from typing import Any

from bhms.jsonrpc.dispatcher import Server as RpcServer
from bhms.jsonrpc.session import RequestContext
from bhms.protocol.errors import BhmsError
from bhms.runtime.authority import Authenticator, Policy, Principal, token_digest
from bhms.runtime.events import EventLog
from bhms.runtime.heap import freeze_startup_heap
from bhms.runtime.leases import Lease, LeaseManager
from bhms.runtime.observations import ObservationHub
from bhms.runtime.operations import Journal, OperationRecord, intent_digest, key_conflict_error, server_key
from bhms.runtime.store import Store, StoreError
from bhms.server.device import Device
from bhms.server.executor import Executor
from bhms.server.listen import Subscriptions

log = logging.getLogger("bhms.server")

_DEFAULT = object()
DEFAULT_PROGRAM_LIMITS = {"maxSteps": 256, "maxRepeat": 1000, "maxDepth": 4, "maxExecutedSteps": 4096,
                          "maxVariables": 64, "maxProgramBytes": 65536, "maxDurationMs": 3_600_000}


def default_state_dir() -> Path:
    if os.environ.get("BHMS_STATE_DIR"):
        return Path(os.environ["BHMS_STATE_DIR"])
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return Path(base) / "bhms"


class DeviceServer:
    """A BHMS device server; see the module docstring.

    Args:
        name: server name (``serverInfo.name``) and the default store file name.
        version / title / instructions: ``serverInfo`` and model guidance (untrusted text).
        state_dir: directory of the store (and generated token file).
        store: explicit store path, or ``None`` for a non-durable in-memory store (new epoch every start).
        durability: ``"dispatch"`` (default; fsync before every dispatch), ``"full"`` or ``"process"``
            (see :mod:`bhms.runtime.store`).
        policy: :class:`~bhms.runtime.authority.Policy` (default: stdio/same-uid admin, plus ``token``).
        token: bearer token granting ``admin`` over WebSocket.
        key_retention_s: how long keys and settled operations are kept (≥ 86 400, BHMS-OPS-034).
        event_retention_s: event retention (BHMS-EVT-012).
        max_wait_ms / max_page_size: ``limits`` (BHMS-SEC-060).
        lease_min_ttl_ms / lease_max_ttl_ms / lease_max_wait_ms: ``capabilities.leases``.
        queue_limit: queued operations per device before ``BUSY``.
        observation_min_interval_ms: subscription rate floor.
        cancel_grace_ms: how long a cancelled handler may take to terminate after a duration bound.
        stop_shutdown_ceiling_s: the longest :meth:`close` waits for a running stop procedure, whatever its declared
            bound (BHMS-AUTH-024); set it below your supervisor's kill timeout so a stop ended at shutdown is recorded.
        programs: enable ``programs/*`` (with a durable registry).
        strict: full JSON Schema validation of every request and result (conformance mode).
    """

    def __init__(self, name: str, *, version: str = "0.1.0", title: str | None = None,
                 instructions: str | None = None, state_dir: str | os.PathLike[str] | None = None,
                 store: Any = _DEFAULT, durability: str = "dispatch", policy: Policy | None = None,
                 token: str | None = None, key_retention_s: int = 7 * 86400, event_retention_s: int = 7 * 86400,
                 max_wait_ms: int = 60_000, max_page_size: int = 500, lease_min_ttl_ms: int = 1000,
                 lease_max_ttl_ms: int = 600_000, lease_max_wait_ms: int = 30_000, queue_limit: int = 64,
                 observation_min_interval_ms: int = 50, cancel_grace_ms: int = 1000, programs: bool = True,
                 program_limits: dict[str, int] | None = None, strict: bool = False,
                 liveness_interval_s: float | None = None, reconcile_timeout_s: float = 10.0,
                 stop_shutdown_ceiling_s: float = 60.0) -> None:
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", name):
            raise ValueError(f"server name {name!r} must be 1-128 characters of [A-Za-z0-9._-]")
        if liveness_interval_s is not None and liveness_interval_s <= 0:
            raise ValueError("liveness_interval_s must be positive (None leaves periodic liveness probes off)")
        if reconcile_timeout_s <= 0:
            raise ValueError("reconcile_timeout_s must be positive")
        if stop_shutdown_ceiling_s <= 0:
            raise ValueError("stop_shutdown_ceiling_s must be positive")
        self.stop_shutdown_ceiling_s = stop_shutdown_ceiling_s
        self.liveness_interval_s, self.reconcile_timeout_s = liveness_interval_s, reconcile_timeout_s
        if key_retention_s < 86_400:
            raise ValueError("key_retention_s must be at least 86400 (BHMS-OPS-034)")
        self.name, self.version, self.title, self.instructions = name, version, title, instructions
        self.state_dir = Path(state_dir) if state_dir is not None else default_state_dir()
        self._store_arg = store
        self.durability = durability
        self.token = token or os.environ.get("BHMS_TOKEN")
        self.policy = policy or Policy()
        if self.token:
            self.policy = _with_admin_token(self.policy, self.token)
        self.key_retention_s, self.event_retention_s = key_retention_s, event_retention_s
        self.max_wait_ms, self.max_page_size = max_wait_ms, max_page_size
        self._lease_cfg = (lease_min_ttl_ms, lease_max_ttl_ms, lease_max_wait_ms)
        self.queue_limit, self.cancel_grace_ms = queue_limit, cancel_grace_ms
        self.observation_min_interval_ms = observation_min_interval_ms
        self.programs_enabled = programs
        self.program_limits = {**DEFAULT_PROGRAM_LIMITS, **(program_limits or {})}
        self.strict = strict
        self.devices: dict[str, Device] = {}
        self._started = False
        self._closing: asyncio.Event | None = None  # set by close(); ends subscriptions with endReason shutdown
        self.auth = Authenticator(lambda: self.policy)
        self._journal_ok = True
        self._listeners: list[Any] = []
        self._extensions: dict[str, dict[str, Any]] = {}
        self._extension_methods: dict[str, Any] = {}
        self.rpc: RpcServer | None = None
        self._ready = False  # start() finished: a device that returns from now on triggers its reconcile hook
        self._liveness_tasks: dict[str, asyncio.Task[None]] = {}
        self._returning: dict[str, asyncio.Task[None]] = {}
        self._return_again: set[str] = set()

    # ------------------------------------------------------------------ declaration

    def device(self, device_id: str, **kw: Any) -> Device:
        """Declare a device; see :class:`~bhms.server.device.Device` for options and decorators."""
        if device_id in self.devices:
            raise ValueError(f"device {device_id!r} is already declared (BHMS-DEV-001)")
        dev = Device(self, device_id, **kw)
        self.devices[device_id] = dev
        if self._started:
            dev.description()
            self._device_changed(dev)
        return dev

    def device_from_description(self, description: dict[str, Any], **kw: Any) -> Device:
        """Declare a device from a given description; see :meth:`Device.from_description` for ``kw``. Works before and
        after :meth:`start` (a bridge declares its device once the endpoint has proven it is the described one)."""
        device_id = description.get("deviceId")
        if device_id in self.devices:
            raise ValueError(f"device {device_id!r} is already declared (BHMS-DEV-001)")
        dev = Device.from_description(self, description, **kw)
        self.devices[dev.device_id] = dev
        if self._started:
            self._device_changed(dev)
        return dev

    def extension(self, key: str, info: dict[str, Any], methods: dict[str, Any]) -> None:
        """Advertise extension ``key`` (``"<prefix>/<name>"``, BHMS-LIF-070) under ``capabilities.extensions`` and
        register its methods (``x-<name>/<method>`` or ``<prefix>/<name>/<method>``; ``handler(params, ctx)`` gets
        raw params). Declare before :meth:`start`. Extensions cannot weaken core guarantees (BHMS-LIF-071)."""
        if self._started:
            raise RuntimeError("declare extensions before start()")
        self._extensions[key] = info
        self._extension_methods.update(methods)

    def resources(self) -> set[str]:
        return {r for dev in self.devices.values() for r in dev.resources}

    # ------------------------------------------------------------------ lifecycle

    def _store_path(self) -> Any:
        if self._store_arg is _DEFAULT:
            return self.state_dir / f"{self.name}.sqlite3"
        return self._store_arg

    async def start(self) -> None:
        """Open the store, recover, validate descriptions and register every method (idempotent)."""
        if self._started:
            return
        for dev in self.devices.values():
            dev.description()  # fail fast on invalid declarations
        self.store = Store(self._store_path(), durability=self.durability)
        try:
            self._closing = asyncio.Event()
            self.journal = Journal(self.store)
            self.events = EventLog(self.store, retention_s=self.event_retention_s)
            self.observations = ObservationHub(self, min_interval_ms=self.observation_min_interval_ms)
            lo, hi, wait = self._lease_cfg
            self.leases = LeaseManager(self.store, resources=self.resources, min_ttl_ms=lo, max_ttl_ms=hi,
                                       max_wait_ms=wait, on_end=self._lease_ended)
            self.executor = Executor(self, queue_limit=self.queue_limit, cancel_grace_ms=self.cancel_grace_ms)
            from bhms.runtime.programs import ProgramRunner
            from bhms.runtime.stop import StopController

            self.programs = ProgramRunner(self)
            self.stopper = StopController(self, close_ceiling=self.stop_shutdown_ceiling_s)
            self.subscriptions = Subscriptions(self)
            self.journal.on_unknown.append(self._record_unknown)
            self.journal.recover()  # BHMS-OPS-080: before any request is answered
            self.executor.load_inhibitions()
            self.store.prune_operations(["completed", "failed", "canceled", "rejected"],
                                        _ns_ago(self.key_retention_s))
            self.events.prune()
            self.policy.check_bounds(lambda d: self.devices[d].description() if d in self.devices else None)
            self.rpc = self._make_rpc()
            self._started = True
            for dev in self.devices.values():
                with contextlib.suppress(StoreError):
                    self.events.append("device.epoch", device_id=dev.device_id, data={"epoch": self.observations.epoch},
                                       message="observation sequences restarted with the server")
            for dev in self.devices.values():
                await self._check_liveness(dev)
                await self.executor.reconcile(dev)
            self._ready = True
            for dev in self.devices.values():
                self.start_liveness(dev)
        except BaseException:
            self.store.close()
            raise

    def _make_rpc(self) -> RpcServer:
        caps: dict[str, Any] = {
            "devices": {"listChanged": True},
            "observations": {"subscribe": True, "minIntervalMs": self.observation_min_interval_ms},
            "operations": {"durable": self.store.durable, "cancel": True, "resolve": True,
                           "keyRetentionS": self.key_retention_s if self.store.durable else 0},
            "stop": {}, "subscriptions": {"maxObservations": 256, "maxOperationIds": 256},
            "leases": self.leases.capability,
            "events": {"retentionS": self.event_retention_s, "maxPageSize": self.max_page_size}}
        if self.programs_enabled:
            caps["programs"] = {"registry": True, "limits": self.program_limits}
        authority = self.policy.authority_capability()
        if authority is not None:
            caps["authority"] = authority
        if self._extensions:
            caps["extensions"] = dict(self._extensions)
        info = {"name": self.name, "version": self.version}
        if self.title:
            info["title"] = self.title

        def principal(peer: Any) -> dict[str, Any] | None:
            found = self.policy.resolve(peer)
            return found.wire() if found is not None else None

        rpc = RpcServer(server_info=info, capabilities=caps, epoch=self.store.epoch, instructions=self.instructions,
                        principal=principal, max_page_size=self.max_page_size, max_wait_ms=self.max_wait_ms,
                        strict=self.strict)
        from bhms.server import handlers

        handlers.register(self, rpc)
        for method, handler in self._extension_methods.items():
            rpc.register(method, handler)
        return rpc

    async def _check_liveness(self, dev: Device) -> None:
        """Run the device's liveness probe once (bounded by its ``timeout_s``) and record the evidence either way."""
        if dev.liveness_handler is None:
            return
        try:
            outcome = dev.liveness_handler()
            if inspect.isawaitable(outcome):
                outcome = await asyncio.wait_for(outcome, dev.liveness_timeout_s)
        except Exception as exc:  # noqa: BLE001 - the probe did not answer: evidence that the device is unreachable
            if dev.status != "offline":
                log.warning("liveness probe of %s failed: %s: %s", dev.device_id, type(exc).__name__, exc)
            outcome = False
        if outcome:
            dev.report_alive()
        else:
            dev.report_unreachable()

    def start_liveness(self, dev: Device) -> None:
        """Begin the periodic liveness probe of ``dev`` when it declares one with an interval (its own ``interval_s`` or
        the server's ``liveness_interval_s``; off when neither is set). Called for every device by :meth:`start`; call it
        for a device, or a probe, declared after the server started. Idempotent."""
        interval = dev.liveness_interval_s if dev.liveness_interval_s is not None else self.liveness_interval_s
        if not self._ready or dev.liveness_handler is None or interval is None or dev.device_id in self._liveness_tasks:
            return
        self._liveness_tasks[dev.device_id] = asyncio.get_running_loop().create_task(
            self._liveness_loop(dev, interval), name=f"bhms-liveness-{dev.device_id}")

    async def _liveness_loop(self, dev: Device, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            await self._check_liveness(dev)

    def _device_returned(self, dev: Device) -> None:
        """The device's status became ``online`` again: ask its reconcile hook about its ``unknown`` operations, once per
        return (a return during a running pass queues exactly one more pass)."""
        if not self._ready or not self._started or dev.reconcile_handler is None:
            return
        if dev.device_id in self._returning:
            self._return_again.add(dev.device_id)
            return
        self._returning[dev.device_id] = asyncio.get_running_loop().create_task(
            self._reconcile_returned(dev), name=f"bhms-reconcile-{dev.device_id}")

    async def _reconcile_returned(self, dev: Device) -> None:
        try:
            while True:
                self._return_again.discard(dev.device_id)
                try:
                    changed = await self.executor.reconcile(dev)
                except StoreError as exc:
                    self.journal_failed(exc)
                    return
                if changed:
                    log.info("%s returned: %d unknown operation(s) reconciled from device evidence", dev.device_id,
                             len(changed))
                    self.executor.pump()
                if dev.device_id not in self._return_again:
                    return
        finally:
            self._returning.pop(dev.device_id, None)

    async def listen(self, url: str, *, ssl: ssl_module.SSLContext | None = None) -> Any:
        """Start (if needed) and accept connections on ``unix:<path>`` or ``ws[s]://host:port``; returns the
        listener (``await listener.close()`` stops accepting)."""
        from bhms.transport import serve_unix, serve_websocket
        from bhms.transport.stream import is_loopback

        await self.start()
        assert self.rpc is not None
        if url.startswith("unix:"):
            path = url[len("unix:"):]
            listener = await serve_unix(path[2:] if path.startswith("//") else path, self.rpc.handle_connection)
        elif url.startswith(("ws://", "wss://")):
            host, port = _host_port(url)
            if url.startswith("wss://") and ssl is None:
                raise ValueError(f"refusing to serve {url} without a TLS context: wss:// promises encryption; pass "
                                 "ssl=<SSLContext>, or use ws:// on a loopback address")
            if not is_loopback(host) and ssl is None:
                raise ValueError(f"refusing to serve {url} without TLS: a non-loopback listener must use TLS "
                                 "(BHMS-SEC-004); pass ssl=<SSLContext> or bind 127.0.0.1")
            self._ensure_token()
            listener = await serve_websocket(host, port, self.rpc.handle_connection,
                                             authenticate=lambda token: self.policy.by_token(token) is not None,
                                             ssl=ssl)
        elif url.startswith("tcp://"):
            raise ValueError("TCP carries no credential in this SDK, so every request would be refused "
                             "(BHMS-SEC-001); serve unix:<path> or ws://host:port instead")
        else:
            raise ValueError(f"unsupported url {url!r}; use stdio (default), unix:<path> or ws://host:port")
        self._listeners.append(listener)
        return listener

    def _ensure_token(self) -> None:
        if any(p.id == "token" for p in self.policy.principals) or self.token:
            return
        self.token = secrets.token_urlsafe(24)
        self.policy = _with_admin_token(self.policy, self.token)
        self.auth.reset()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_dir / f"{self.name}.token"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(self.token + "\n")
        log.warning("bearer token for %s written to %s (mode 0600); clients pass it as Authorization: Bearer",
                    self.name, path)

    async def serve(self, url: str | None = None, *, ssl: ssl_module.SSLContext | None = None) -> None:
        """Serve until the parent closes stdio (default) or until SIGINT/SIGTERM, then close cleanly."""
        await self.start()
        assert self.rpc is not None
        freeze_startup_heap()  # no generation-2 pause over the start-up heap while serving (Task 12a: 42-81 ms)
        try:
            if url is None or url == "stdio":
                await self.rpc.serve_stdio()
                return
            await self.listen(url, ssl=ssl)
            stopped = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                with contextlib.suppress(NotImplementedError, RuntimeError):
                    loop.add_signal_handler(sig, stopped.set)
            await stopped.wait()
        finally:
            await self.close()

    def run(self, url: str | None = None, *, ssl: ssl_module.SSLContext | None = None) -> None:
        """Blocking entry point: ``srv.run()`` serves stdio; ``srv.run("unix:/path")``, ``srv.run("ws://h:p")``."""
        asyncio.run(self.serve(url, ssl=ssl))

    async def close(self) -> None:
        """End subscriptions (``endReason: shutdown``), close connections, wait for running handlers (their outcomes
        are recorded), close the store."""
        if not self._started:
            return
        self._started = False
        assert self._closing is not None
        self._closing.set()
        await self.subscriptions.drain(1.0)
        for listener in self._listeners:
            await listener.close()
        self._listeners.clear()
        if self.rpc is not None:
            await self.rpc.close()
        self._ready = False
        background = [*self._liveness_tasks.values(), *self._returning.values()]
        for task in background:
            task.cancel()
        await asyncio.gather(*background, return_exceptions=True)
        self._liveness_tasks.clear()
        await self.programs.close()
        await self.stopper.close()
        pending = [t for t in self.executor.tasks if not t.done()]
        if pending:
            await asyncio.wait(pending, timeout=self.rpc.drain_timeout if self.rpc else 10.0)
        for task in [t for t in self.executor.tasks if not t.done()]:
            task.cancel()
        with contextlib.suppress(Exception):
            await asyncio.gather(*self.executor.tasks, return_exceptions=True)
        self.observations.close()
        self.leases.close()
        self.store.close()

    async def __aenter__(self) -> DeviceServer:
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------ authority

    def principal_of(self, ctx: RequestContext) -> Principal | None:
        return self.auth.principal_of(ctx)

    def authenticate(self, ctx: RequestContext) -> Principal:
        """The request's principal, or ``UNAUTHORIZED`` when the transport carries no valid credential."""
        return self.auth.authenticate(ctx)

    def set_policy(self, policy: Policy) -> None:
        """Replace the policy; takes effect for new admissions at once and is recorded (BHMS-SEC-012)."""
        policy.check_bounds(lambda d: self.devices[d].description() if d in self.devices else None)
        if self.token:
            policy = _with_admin_token(policy, self.token)
        before = {p.id: p for p in self.policy.principals}
        self.policy = policy
        self.auth.reset()
        for principal_id, old in before.items():
            now = next((p for p in policy.principals if p.id == principal_id), None)
            if old.has("lease") and (now is None or not now.has("lease")):
                self.leases.revoke_principal(principal_id)  # BHMS-AUTH-013
        with contextlib.suppress(StoreError):
            self.events.append("policy.changed", message="the authorization policy changed")
        self.subscriptions.policy_changed()

    def visible_device(self, principal: Principal, device_id: str, *, field: str = "deviceId") -> Device:
        """The device if the principal may read it; otherwise ``UNKNOWN_DEVICE`` (BHMS-DEV-010, BHMS-AUTH-002)."""
        dev = self.devices.get(device_id)
        if dev is None or not principal.can_read:
            from bhms.server.handlers import unknown_device

            raise unknown_device(device_id, self.devices if principal.can_read else (), field=field)
        return dev

    # ------------------------------------------------------------------ journal health (BHMS-AUTH-025)

    def journal_failed(self, exc: Exception) -> None:
        if self._journal_ok:
            log.error("the journal cannot be written (%s); ordinary operations are refused until it can", exc)
        self._journal_ok = False

    def require_journal(self) -> None:
        if self._journal_ok:
            return
        if self.store.probe_writable():
            self._journal_ok = True
            return
        raise BhmsError("BUSY", "the operation journal cannot be written; new operations are refused until it can",
                        retry="same-key", hint="retry later with the same operationKey; stop remains available")

    @property
    def journal_ok(self) -> bool:
        return self._journal_ok

    # ------------------------------------------------------------------ operations API used by handlers

    async def invoke(self, principal: Principal, params: Any, raw: dict[str, Any]) -> tuple[OperationRecord, bool]:
        """``actions/invoke`` from key lookup to admission (§6.5); returns (operation, replayed)."""
        key = params.operation_key
        if key is not None and key.startswith("g-") and not principal.gateway:
            raise BhmsError("INVALID_ARGUMENT", "operationKey prefix g- is reserved for gateways", field="operationKey",
                            hint="use a key that does not start with d- or g- (BHMS-OPS-037)")
        if params.wait_ms is not None and params.wait_ms > self.max_wait_ms:
            raise _wait_error("waitMs", params.wait_ms, self.max_wait_ms)
        digest = intent_digest("actions/invoke", raw)
        if key is None:
            return await self.executor.admit(principal, params, server_key(), "server", digest), False
        async with self.journal.admission(principal.id, key):
            existing = self.journal.lookup_key(principal.id, key)  # BHMS-OPS-033: before anything else
            if existing is not None:
                if existing.op["requestDigest"] != digest:
                    raise key_conflict_error(existing, key)
                return existing, True
            return await self.executor.admit(principal, params, key, "client", digest), False

    def operation_for(self, principal: Principal, op_id: str) -> OperationRecord:
        """An operation the principal may see, else ``INVALID_ARGUMENT`` (BHMS-OPS-062)."""
        rec = self.journal.get(op_id)
        if rec is None or not self.journal.observable(rec) or (rec.principal != principal.id
                                                                and not principal.operations_all):
            raise BhmsError("INVALID_ARGUMENT", f"no operation {op_id!r} is visible to you", field="operationId",
                            hint="use an operationId returned to you (operations/list shows yours)")
        return rec

    async def resolve(self, principal: Principal, operation_id: str, resolution: Any = None) -> OperationRecord:
        """``operations/resolve`` (§6.10): ask the device again about an ``unknown`` operation and, when it still cannot
        say and ``resolution`` (an ``OperatorResolution``) is given, record the operator's resolution.

        Needs ``admin`` or ``operations:resolve``, on an operation the principal can see. Device evidence wins: the
        reconcile hook is asked first and its answer, if any, is what is recorded. An operation that is not ``unknown``
        is returned unchanged. Nothing is ever removed from history.
        """
        if not principal.has("operations:resolve"):
            raise BhmsError("UNAUTHORIZED", "operations/resolve needs the operations:resolve scope (or admin)",
                            hint="missing scope operations:resolve; an operator resolves unknown operations, not the "
                                 "client that started them")
        rec = self.operation_for(principal, operation_id)
        if rec.op.get("kind") != "action":
            raise BhmsError("INVALID_ARGUMENT", f"{operation_id} is a program operation; it settles when its unknown "
                            "step operations are resolved", field="operationId",
                            hint="list its steps with operations/list parentOperationId and resolve the unknown ones "
                                 "(BHMS-PRG-017)")
        if rec.state != "unknown":
            return rec
        self.require_journal()
        device = self.devices.get(rec.op.get("deviceId", ""))
        try:
            if device is not None:
                await self.executor.reconcile_one(device, rec)
            if rec.state == "unknown" and resolution is not None:
                self.executor.resolve_by_operator(rec, principal.id, resolution)
        except StoreError as exc:
            self.journal_failed(exc)
            raise BhmsError("BUSY", "the journal cannot be written; the operation is still unknown", retry="backoff",
                            hint="retry when the server's journal is writable again") from None
        if rec.state != "unknown":
            self.executor.pump()
        return rec

    async def reconcile(self, device_id: str | None = None) -> list[OperationRecord]:
        """Run the ``reconcile`` hooks for ``unknown`` operations (one device or all); returns changed records."""
        changed: list[OperationRecord] = []
        for dev in self.devices.values():
            if device_id is None or dev.device_id == device_id:
                changed += await self.executor.reconcile(dev)
        self.executor.pump()
        return changed

    # ------------------------------------------------------------------ runtime callbacks

    def _record_unknown(self, rec: OperationRecord) -> None:
        with contextlib.suppress(StoreError):
            self.events.append("operation.state", severity="warning", device_id=rec.op.get("deviceId"),
                               operation_id=rec.id, message=rec.op.get("error", {}).get("message"),
                               data={"state": "unknown", "previousState": _previous_state(rec)})

    def _lease_ended(self, lease: Lease, reason: str) -> None:
        with contextlib.suppress(StoreError):
            self.events.append(f"lease.{reason}", severity="warning" if reason == "revoked" else "info",
                               data={"leaseId": lease.lease_id})
        self.executor.on_lease_end(lease, reason)
        self.programs.on_lease_end(lease, reason)

    def _device_changed(self, dev: Device) -> None:
        if self._started:
            self.subscriptions.devices_changed()

    def _status_changed(self, dev: Device, previous: str) -> None:
        if not self._started:
            return
        status = dev.status
        if status in ("online", "offline", "degraded"):
            with contextlib.suppress(StoreError):
                self.events.append(f"device.{status}", severity="warning" if status != "online" else "info",
                                   device_id=dev.device_id, message=f"{dev.device_id} is {status} (was {previous})")
        if status == "online":
            self._device_returned(dev)


def _with_admin_token(policy: Policy, token: str) -> Policy:
    entries: dict[str, dict[str, Any]] = {}
    for principal in policy.principals:
        entry = next(e for e in policy._entries if e.principal is principal)
        spec: dict[str, Any] = {"scopes": list(principal.scopes)}
        if entry.token_digests:
            spec["tokens"] = list(entry.token_digests)
        if entry.uids:
            spec["uids"] = list(entry.uids)
        if principal.bounds:
            spec["bounds"] = principal.bounds
        if principal.gateway:
            spec["gateway"] = True
        entries[principal.id] = spec
    if "token" not in entries:
        entries["token"] = {"tokens": [token_digest(token)], "scopes": ["admin"]}
    return Policy(entries, trust_same_uid=policy.trust_same_uid, stdio_scopes=policy.stdio.scopes)


def _host_port(url: str) -> tuple[str, int]:
    rest = url.split("://", 1)[1].split("/", 1)[0]
    host, sep, port = rest.rpartition(":")
    if not sep or not port.isdigit():
        raise ValueError(f"bad url {url!r}; expected ws://host:port")
    return host.strip("[]"), int(port)


def _ns_ago(seconds: int) -> int:
    from bhms.runtime.operations import now_ns

    return now_ns() - seconds * 1_000_000_000


def _previous_state(rec: OperationRecord) -> str:
    history = rec._history or []
    states = [h["state"] for h in history if h.get("state")]
    return states[-2] if len(states) >= 2 else "dispatching"


def _wait_error(field: str, value: int, limit: int) -> BhmsError:
    return BhmsError("OUT_OF_RANGE", f"{field} {value} is above limits.maxWaitMs {limit}", field=field,
                     bound={"maximum": limit}, hint=f"send {field} of at most {limit} and call operations/wait again "
                                                    "if needed")


def encode_cursor(prefix: str, value: str) -> str:
    return f"{prefix}.{base64.urlsafe_b64encode(value.encode()).decode().rstrip('=')}"


def decode_cursor(prefix: str, cursor: str) -> str:
    try:
        head, body = cursor.split(".", 1)
        if head != prefix:
            raise ValueError
        return base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        raise BhmsError("INVALID_ARGUMENT", "cursor was not issued by this server for this list", field="cursor",
                        hint="pass nextCursor exactly as returned, or omit it (BHMS-LIF-060)") from None


__all__ = ["DeviceServer", "decode_cursor", "default_state_dir", "encode_cursor"]
