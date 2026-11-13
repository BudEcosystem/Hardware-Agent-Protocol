"""Upstream connection management: one :class:`Upstream` per configured device server (BHMS-SEC-061).

Each upstream owns

* a **connection task** that connects (spawning a ``stdio`` server, or dialling ``url``/``connector``), runs
  ``server/discover``, loads the device list and every description (verifying each digest, BHMS-SEC-022), opens one
  ``subscriptions/listen`` stream (``devicesListChanged``, all operations, events) and then supervises the link; when it
  breaks the task marks the upstream ``down`` and reconnects with exponential backoff (0.1 s to 5 s);
* a **health probe** (``server/discover`` every ``health_interval_ms``, also triggered at once by any call timeout): a probe
  that is not answered within ``health_timeout_ms`` marks the upstream ``stalled``; its devices read as unavailable and
  requests fail fast with ``DEVICE_UNAVAILABLE`` instead of queueing behind a dead peer. A later answer restores it;
* a **bounded call queue**: at most ``max_inflight`` calls run at once and at most ``queue_size`` wait (a worker task
  drains the queue); beyond that a call is refused with ``BUSY`` (retry with the same key) so one slow upstream cannot grow
  the gateway's memory or starve others. A call that exceeds ``timeout_ms`` fails with ``DEADLINE_EXCEEDED``,
  ``mayHaveActed: true`` (the caller records ``unknown`` for operations).

``stop`` and lease release use ``priority=True``: they bypass the queue and the concurrency limit and are attempted even
while the upstream is ``stalled`` (BHMS-AUTH-020) — a message written to a paused peer is still executed when it resumes.

States: ``connecting`` -> ``up`` <-> ``stalled``; any -> ``down`` -> ``connecting``; ``closed``. The owner is told about
every change through :class:`UpstreamHooks` (the gateway marks operations ``unknown``, emits events, reconciles).

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from bhms.client.client import Client, open_transport
from bhms.gateway.config import UpstreamConfig
from bhms.jsonrpc.session import ClientStream
from bhms.protocol.canonical import digest
from bhms.protocol.errors import BhmsError
from bhms.protocol.types import to_wire
from bhms.transport.base import Transport, TransportClosed

log = logging.getLogger("bhms.gateway.upstream")

DESCRIBE_CONCURRENCY = 16
_BACKOFF = (0.1, 0.2, 0.5, 1.0, 2.0, 5.0)


class UpstreamHooks:
    """What the gateway wants to hear from an upstream; the defaults do nothing."""

    def status_changed(self, upstream: Upstream, old: str, new: str, cause: str) -> None: ...

    def catalog_changed(self, upstream: Upstream) -> None: ...

    def notification(self, upstream: Upstream, method: str, params: dict[str, Any]) -> None: ...

    def events_gap(self, upstream: Upstream) -> None: ...


@dataclass(slots=True)
class _Queued:
    method: str
    params: dict[str, Any]
    timeout: float
    trace: dict[str, Any] | None
    future: asyncio.Future[dict[str, Any]]


class Upstream:
    """One upstream device server; see the module docstring.

    ``summaries`` and ``descriptions`` map the upstream's own device ids to its latest ``DeviceSummary`` and verified
    ``DeviceDescription``; ``epoch`` and ``capabilities`` come from its ``server/discover``.
    """

    def __init__(self, cfg: UpstreamConfig, hooks: UpstreamHooks, *, event_cursor: str | None = None) -> None:
        self.cfg = cfg
        self.name = cfg.name
        self.hooks = hooks
        self.status = "connecting"
        self.cause = "not connected yet"
        self.client: Client | None = None
        self.epoch: str | None = None
        self.capabilities: dict[str, Any] = {}
        self.summaries: dict[str, dict[str, Any]] = {}
        self.descriptions: dict[str, dict[str, Any]] = {}
        self.event_cursor = event_cursor
        self.event_cursor_dirty = False
        self.connections = 0
        self.timeouts = 0
        self._queue: asyncio.Queue[_Queued] = asyncio.Queue(cfg.queue_size)
        self._slots = asyncio.Semaphore(cfg.max_inflight)
        self._closing = False
        self._runner: asyncio.Task[None] | None = None
        self._worker: asyncio.Task[None] | None = None
        self._probe = asyncio.Event()
        self._resync = asyncio.Event()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._ready = asyncio.Event()
        self.latency_ms: deque[float] = deque(maxlen=256)

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        self._worker = asyncio.get_running_loop().create_task(self._drain(), name=f"bhms-up-queue-{self.name}")
        self._runner = asyncio.get_running_loop().create_task(self._run(), name=f"bhms-up-{self.name}")

    async def wait_ready(self, timeout: float) -> bool:
        """Wait until the first connection attempt has either succeeded (devices loaded) or failed."""
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._ready.wait(), timeout)
        return self.status == "up"

    async def close(self) -> None:
        self._closing = True
        self._set_status("closed", "the gateway is shutting down")
        for task in [self._runner, self._worker, *self._tasks]:
            if task is not None:
                task.cancel()
        await asyncio.gather(*[t for t in [self._runner, self._worker, *self._tasks] if t is not None],
                             return_exceptions=True)
        client, self.client = self.client, None
        if client is not None:
            await client.close()
        while not self._queue.empty():
            self._queue.get_nowait().future.cancel()

    @property
    def available(self) -> bool:
        return self.status == "up"

    def _set_status(self, new: str, cause: str) -> None:
        old, self.status, self.cause = self.status, new, cause
        if old != new:
            try:
                self.hooks.status_changed(self, old, new, cause)
            except Exception:  # noqa: BLE001 - a hook must not break connection supervision
                log.exception("status hook failed for upstream %s", self.name)

    def unavailable(self) -> BhmsError:
        """``DEVICE_UNAVAILABLE`` for a call that was refused before anything was sent (``mayHaveActed: false``)."""
        return BhmsError("DEVICE_UNAVAILABLE", f"upstream {self.name!r} is {self.status}: {self.cause}",
                         may_have_acted=False, retry="same-key",
                         hint=f"the devices of {self.name}/ are unavailable until the gateway reconnects; "
                              "nothing was sent (gateway rule: isolation:upstream-unavailable)")

    # ------------------------------------------------------------------ calls

    async def call(self, method: str, params: dict[str, Any], *, timeout: float | None = None, priority: bool = False,
                   trace: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send ``method`` upstream and return its result object.

        ``params`` excludes ``_meta`` (added here with the protocol version, the gateway's client info and ``trace`` —
        ``traceparent``/``tracestate``, BHMS-LIF-018). Raises the upstream's :class:`BhmsError` unchanged, ``BUSY`` when
        the bounded queue is full, ``DEVICE_UNAVAILABLE`` when the upstream is not up, and ``DEADLINE_EXCEEDED``
        (``mayHaveActed: true``) when ``timeout`` (default ``timeout_ms``) passes.
        """
        client = self.client
        usable = self.status == "up" or (priority and self.status in ("up", "stalled"))
        if client is None or not usable:
            raise self.unavailable()
        seconds = timeout if timeout is not None else self.cfg.timeout_ms / 1000
        if priority:
            return await self._send(client, method, params, seconds, trace)
        if not self._slots.locked() and self._queue.empty():
            async with self._slots:
                return await self._send(client, method, params, seconds, trace)
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        try:
            self._queue.put_nowait(_Queued(method, params, seconds, trace, future))
        except asyncio.QueueFull:
            raise BhmsError("BUSY", f"upstream {self.name!r} has {self.cfg.max_inflight} calls running and "
                            f"{self.cfg.queue_size} waiting", may_have_acted=False, retry="same-key",
                            hint="retry shortly with the same operationKey (gateway rule: isolation:queue-bounded)"
                            ) from None
        return await future

    async def _send(self, client: Client, method: str, params: dict[str, Any], seconds: float,
                    trace: dict[str, Any] | None) -> dict[str, Any]:
        meta = {"bhms/protocolVersion": client.version, "bhms/clientInfo": client.client_info}
        if trace:
            meta.update(trace)
        started = time.perf_counter()
        try:
            return await client.session.request(method, {"_meta": meta, **params}, timeout=seconds)
        except BhmsError as exc:
            if exc.code == "DEADLINE_EXCEEDED" and exc.may_have_acted and method != "server/discover":
                self.timeouts += 1
                self._probe.set()  # is the peer alive at all? decide in seconds, not after every caller's timeout
            raise
        finally:
            self.latency_ms.append((time.perf_counter() - started) * 1000)

    async def _drain(self) -> None:
        """Worker of the bounded queue: start a queued call as soon as a slot is free."""
        while True:
            item = await self._queue.get()
            if item.future.done():
                continue
            await self._slots.acquire()
            client = self.client
            if client is None or self.status != "up":
                self._slots.release()
                if not item.future.done():
                    item.future.set_exception(self.unavailable())
                continue
            self._spawn(self._run_queued(client, item))

    async def _run_queued(self, client: Client, item: _Queued) -> None:
        try:
            result = await self._send(client, item.method, item.params, item.timeout, item.trace)
            if not item.future.done():
                item.future.set_result(result)
        except BaseException as exc:  # noqa: BLE001 - delivered to the caller
            if not item.future.done():
                item.future.set_exception(exc)
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            self._slots.release()

    def _spawn(self, coro: Any) -> asyncio.Task[Any]:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def open_stream(self, notifications: dict[str, Any]) -> ClientStream:
        """Open a ``subscriptions/listen`` stream (the caller reads the acknowledgement and cancels it)."""
        client = self.client
        if client is None or self.status != "up":
            raise self.unavailable()
        meta = {"bhms/protocolVersion": client.version, "bhms/clientInfo": client.client_info}
        return await client.session.stream("subscriptions/listen", {"_meta": meta, "notifications": notifications})

    # ------------------------------------------------------------------ supervision

    async def _run(self) -> None:
        attempt = 0
        while not self._closing:
            client: Client | None = None
            try:
                client = await self._open()
                attempt = 0
                self.client = client
                self.epoch = client.server.epoch if client.server else None
                self.capabilities = to_wire(client.server.capabilities) if client.server else {}
                self.connections += 1
                await self._sync(client)
                self._set_status("up", "connected")
                self._ready.set()
                await self._supervise(client)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - any failure to connect or load is retried
                log.warning("upstream %s: %s", self.name, exc if isinstance(exc, BhmsError) else repr(exc))
                self._set_status("down", f"{type(exc).__name__}: {exc}"[:300])
                self._ready.set()
            finally:
                self.client = None
                if client is not None:
                    with contextlib.suppress(Exception):
                        await client.close()
            if self._closing:
                return
            if self.status != "down":
                self._set_status("down", "the connection ended")
            await asyncio.sleep(_BACKOFF[min(attempt, len(_BACKOFF) - 1)])
            attempt += 1
            self._set_status("connecting", "reconnecting")

    async def _open(self) -> Client:
        cfg = self.cfg
        if cfg.connector is not None:
            transport: Transport = await cfg.connector()
        elif cfg.stdio is not None:
            from bhms.transport.stdio import spawn_stdio

            transport = await spawn_stdio(cfg.stdio, cwd=cfg.cwd, env=_child_env(cfg))
        else:
            transport = await open_transport(cfg.target, token=cfg.token)
        return await Client.from_transport(transport, client_info={"name": "bhms-gateway", "version": "0.1.0"},
                                           timeout=cfg.timeout_ms / 1000)

    async def _supervise(self, client: Client) -> None:
        """Run the event stream, the health probe and the resync loop until the link breaks."""
        tasks = [asyncio.create_task(self._listen(client), name=f"bhms-up-listen-{self.name}"),
                 asyncio.create_task(self._health(client), name=f"bhms-up-health-{self.name}"),
                 asyncio.create_task(self._resyncer(client), name=f"bhms-up-resync-{self.name}"),
                 asyncio.create_task(client.session.wait_closed(), name=f"bhms-up-closed-{self.name}")]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.exception() is not None and not isinstance(task.exception(), asyncio.CancelledError):
                    log.warning("upstream %s: %r", self.name, task.exception())
            self._set_status("down", "the connection to the upstream ended")
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _health(self, client: Client) -> None:
        interval, limit = self.cfg.health_interval_ms / 1000, self.cfg.health_timeout_ms / 1000
        while True:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._probe.wait(), interval)
            self._probe.clear()
            try:
                await asyncio.wait_for(client.session.request(
                    "server/discover", {"_meta": {"bhms/protocolVersion": client.version}}, timeout=limit), limit + 0.5)
            except (BhmsError, asyncio.TimeoutError, TransportClosed) as exc:
                if client.session.closed:
                    return
                if self.status == "up":
                    self._set_status("stalled", f"no answer to a liveness probe within {limit:g} s ({type(exc).__name__})")
                continue
            if self.status == "stalled":
                with contextlib.suppress(Exception):
                    await self._sync(client)
                self._set_status("up", "the upstream answers again")

    async def _listen(self, client: Client) -> None:
        notifications: dict[str, Any] = {"devicesListChanged": True, "operations": {"all": True},
                                         "events": {"after": self.event_cursor} if self.event_cursor else {}}
        stream = await client.session.stream("subscriptions/listen", {"_meta": {
            "bhms/protocolVersion": client.version, "bhms/clientInfo": client.client_info},
            "notifications": notifications})
        try:
            async for message in stream:
                method, params = message["method"], message.get("params") or {}
                if method == "notifications/subscriptions/acknowledged":
                    if params.get("eventsGap"):
                        self.hooks.events_gap(self)
                    continue
                if method == "notifications/devices/listChanged":
                    self._resync.set()
                    continue
                if method == "notifications/event":
                    cursor = (params.get("event") or {}).get("cursor")
                    if cursor:
                        self.event_cursor, self.event_cursor_dirty = cursor, True
                self.hooks.notification(self, method, params)
        finally:
            await stream.cancel()
        # the server ended the subscription (overflow, shutdown): resubscribing is the supervisor's job
        raise TransportClosed("the upstream ended the subscription")

    async def _resyncer(self, client: Client) -> None:
        while True:
            await self._resync.wait()
            self._resync.clear()
            await asyncio.sleep(0.05)  # coalesce bursts of listChanged
            self._resync.clear()
            try:
                await self._sync(client)
            except (BhmsError, TransportClosed, asyncio.TimeoutError) as exc:
                log.warning("upstream %s: resync failed: %s", self.name, exc)

    # ------------------------------------------------------------------ device catalog of this upstream

    async def _sync(self, client: Client) -> None:
        """Load the device list and the descriptions that are new or changed; tell the hooks when it differs."""
        summaries: dict[str, dict[str, Any]] = {}
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 500}
            if cursor:
                params["cursor"] = cursor
            page = await self._send(client, "devices/list", params, self.cfg.timeout_ms / 1000, None)
            for summary in page["devices"]:
                summaries[summary["deviceId"]] = summary
            cursor = page.get("nextCursor")
            if not cursor:
                break
        by_digest = {d["digest"]: d for d in self.descriptions.values()}
        wanted = {uid: s for uid, s in summaries.items()
                  if uid not in self.descriptions or self.descriptions[uid]["digest"] != s["digest"]}
        fresh: dict[str, dict[str, Any]] = {}
        gate = asyncio.Semaphore(DESCRIBE_CONCURRENCY)

        async def describe(uid: str, summary: dict[str, Any]) -> None:
            cached = by_digest.get(summary["digest"])
            if cached is not None and cached["deviceId"] == uid:
                fresh[uid] = cached
                return
            async with gate:
                reply = await self._send(client, "devices/describe", {"deviceId": uid},
                                         self.cfg.timeout_ms / 1000, None)
            description = reply["description"]
            problem = _description_problem(description, uid)
            if problem is not None:
                log.error("upstream %s: not serving %s: %s (BHMS-SEC-022)", self.name, uid, problem)
                return
            fresh[uid] = description

        await asyncio.gather(*(describe(uid, s) for uid, s in wanted.items()))
        descriptions = {uid: fresh.get(uid) or self.descriptions[uid] for uid in summaries
                        if uid in fresh or uid in self.descriptions}
        summaries = {uid: s for uid, s in summaries.items() if uid in descriptions}
        changed = descriptions != self.descriptions or summaries != self.summaries
        self.summaries, self.descriptions = summaries, descriptions
        if changed:
            self.hooks.catalog_changed(self)


def _description_problem(description: dict[str, Any], expected_id: str) -> str | None:
    """Why a description must not be served, or None (BHMS-SEC-022, BHMS-DEV-021). Full schema validation (milliseconds
    per description) runs afterwards in the background (:meth:`bhms.gateway.gateway.Gateway._validate_loop`), so a start-up
    with ten thousand devices is not spent in a validator."""
    if description.get("deviceId") != expected_id:
        return f"it describes {description.get('deviceId')!r}, not {expected_id!r}"
    body = {k: v for k, v in description.items() if k != "digest"}
    if digest(body) != description.get("digest"):
        return "its digest does not match its content"
    return None


def _child_env(cfg: UpstreamConfig) -> dict[str, str] | None:
    if not cfg.env:
        return None
    import os

    return {**os.environ, **cfg.env}


__all__ = ["Upstream", "UpstreamHooks"]
