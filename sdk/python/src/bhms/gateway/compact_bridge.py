"""The gateway's BHMS-Compact bridge: serves a microcontroller endpoint as an ordinary BHMS device server.

A gateway upstream of ``type = "compact"`` (``examples/bhms/compact-gateway.toml``) is a :class:`CompactBridge`: a
:class:`~bhms.server.server.DeviceServer` in the gateway's process whose one device is an endpoint speaking the compact
binary binding (spec/bhms/11-compact-binding.md) over a serial port, pty, Unix or TCP stream. The gateway talks JSON-RPC to
it over an in-memory transport exactly as it does to any other upstream, so everything durable stays where it already is:
the gateway's pending-forward rows and ``unknown`` records, and this server's journal, in which every operation lives from
``dispatching`` on (BHMS-OPS-003). Nothing here re-implements the journal; the bridge only translates.

**Description by sidecar.** The endpoint cannot describe itself in JSON; the full ``DeviceDescription`` (with the ``compact``
layouts of §4.8) lives in a sidecar file. The bridge computes its digest and serves the device only when HELLO reports the
first 8 bytes of that digest (BHMS-DEV-021); a mismatch is logged and the device is never served (and is taken offline if
it was). Layouts are used by index and field order, never by name order (BHMS-CMP-011).

**Invoke.** Arguments are encoded with the one codec of :mod:`bhms.transport.compact`, which refuses what the wire cannot
carry exactly (BHMS-CMP-010) before anything is sent. The operation's u16 handle (strictly increasing per epoch, BHMS-CMP-030)
and dispatch epoch are written to the store with a barrier *before* the INVOKE is sent. Then:

* RESULT -> ``completed`` / ``failed`` (device fault number) / ``canceled`` / not started; STATUS -> running, progress, cancel
  acknowledgement; ERROR -> the mapped BHMS code. Every ERROR except HANDLE_UNKNOWN, SESSION_MISMATCH and HANDLE_CONFLICT
  proves the endpoint did not start the operation and is recorded as such; those three leave it ``unknown`` (a
  SESSION_MISMATCH answering the very first transmission is also a proof: the endpoint refuses a frame of another session
  without effect, BHMS-CMP-021).
* No reply: to an endpoint with ``PERSISTENT_EPOCH`` the same INVOKE (same handle, identical payload) is retransmitted a few
  times while no HELLO has reported another epoch; to any other endpoint an INVOKE is **never** retransmitted, the bridge
  QUERYs instead (BHMS-CMP-033). A running operation is polled with QUERY (the RESULT is sent once, so a lost one is found
  that way). Still silent: the operation becomes ``unknown`` (BHMS-OPS-004).

**Epochs.** A HELLO with a new epoch (or, for an endpoint without ``PERSISTENT_EPOCH``, any HELLO) makes every operation
dispatched earlier and not yet terminal ``unknown``, emits ``device.epoch`` and re-sends nothing (BHMS-CMP-022). Only a
``PERSISTENT_EPOCH`` endpoint whose epoch advanced, or an accepted NEW_SESSION, proves the old work was purged: then, and
only then, the resource inhibition of BHMS-OPS-042 is lifted (the operations stay ``unknown``; their outcome is not known).
A confirmed stop lifts it through the ordinary stop path.

**Reconciliation** (BHMS-CMP-034, BHMS-OPS-005) is by evidence only: an ``unknown`` operation dispatched in the *current*
epoch is QUERYed; the endpoint's RESULT settles it, HANDLE_UNKNOWN or silence leaves it ``unknown``. An operation dispatched
in an earlier epoch is never QUERYed. An operation whose handle was never journaled provably never reached the wire.

**Stop** sends STOP (any session) the moment the stop procedure runs, waits for STOP_ACK and, for ``initiated``, for the
second ack that confirms it with the evidence the description declares (BHMS-CMP-050). **Reads** are READ/VALUE; invalid
and unknown values stay invalid and unknown, with the endpoint's boot epoch and VALUE sequence in the observation
(BHMS-CMP-060); unsolicited VALUEs are published.

Thread-safety: one event loop (the gateway's).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bhms.protocol.errors import BhmsError
from bhms.runtime.authority import Policy
from bhms.runtime.operations import OperationRecord
from bhms.runtime.store import StoreError
from bhms.server.context import ActionContext, Canceled, DeviceFault, Reading, Reconciled
from bhms.server.device import Device
from bhms.server.server import DeviceServer
from bhms.testing.memory import connect_in_process
from bhms.transport import compact as cp
from bhms.transport.base import Transport

log = logging.getLogger("bhms.gateway.compact")

HANDLE_ROTATE_AT = 65_000  # start a new session well before handle 65535 (BHMS-CMP-030)
STOP_REASON_GATEWAY = 3
PROBE_HANDLE = 0xFFFF  # QUERY of a handle no INVOKE has used: answered HANDLE_UNKNOWN, proves liveness and the epoch

# What each ERROR code that proves "not started" is reported as (spec 11.2).
_ERROR_CODE = {cp.E_MALFORMED: "INVALID_ARGUMENT", cp.E_UNKNOWN_ACTION: "UNKNOWN_ACTION",
               cp.E_UNKNOWN_PROPERTY: "INVALID_ARGUMENT", cp.E_OUT_OF_RANGE: "OUT_OF_RANGE", cp.E_FENCED: "FENCED",
               cp.E_LEASE_REQUIRED: "LEASE_REQUIRED", cp.E_BUSY: "BUSY", cp.E_EXPIRED: "DEADLINE_EXCEEDED",
               cp.E_UNSUPPORTED: "UNSUPPORTED", cp.E_PRECONDITION: "STALE", cp.E_INHIBITED: "DEVICE_UNAVAILABLE",
               cp.E_INTERNAL: "INTERNAL"}


@dataclass(frozen=True)
class Timing:
    """Time bounds of the link, in seconds. The defaults suit a 115200 baud serial line to a small board."""

    reply: float = 1.0  # wait for the reply to one request before retransmitting or QUERYing
    retries: int = 3  # further tries after the first before an operation becomes unknown
    poll: float = 2.0  # QUERY period of a running operation (the RESULT is sent once, so a lost one must be asked for)
    probe: float = 2.0  # liveness probe period of an idle link
    probe_misses: int = 3  # unanswered probes before the link is declared down and HELLO is repeated
    hello: float = 1.0  # wait for one HELLO (a board that just reset needs a moment; HELLO_REQ repeats)
    stop_confirm: float = 5.0  # wait for the second STOP_ACK when the stop description declares no bound


class OutcomeUnknown(Exception):  # noqa: N818 - a state of knowledge, not an error condition
    """The endpoint may or may not have acted; the executor records the operation ``unknown`` (BHMS-OPS-004).
    ``lift``: an epoch advance proved the old work purged, so the resource inhibition is lifted (BHMS-OPS-042)."""

    def __init__(self, message: str, *, lift: bool = False) -> None:
        super().__init__(message)
        self.lift = lift


@dataclass(frozen=True)
class LinkEvent:
    """Told to every waiting operation when HELLO changes what is known about the endpoint."""

    kind: str  # "epoch" (a new epoch), "reset" (same epoch value, no persistent counter), "up" (link restored)
    proven: bool = False  # the old work is proven purged (persistent epoch advanced or accepted NEW_SESSION)


@dataclass
class Info:
    """What the bridge durably records about one operation before sending its INVOKE."""

    handle: int
    epoch: int
    persistent: bool
    action: int

    def dump(self) -> str:
        return json.dumps({"handle": self.handle, "epoch": self.epoch, "persistent": self.persistent,
                           "action": self.action}, separators=(",", ":"))

    @staticmethod
    def load(text: str) -> Info:
        raw = json.loads(text)
        return Info(raw["handle"], raw["epoch"], raw["persistent"], raw["action"])


def gateway_policy() -> Policy:
    """The bridge's policy: the gateway (this process's uid) is the only caller and may use ``g-`` keys (BHMS-OPS-037)."""
    return Policy({"gateway": {"uids": [os.getuid()], "scopes": ["admin"], "gateway": True}})


def advanced(old: int, new: int) -> bool:
    """Whether ``new`` is a later boot epoch than ``old`` (u32 counter that skips 0 when it wraps, BHMS-CMP-020)."""
    return 0 < (new - old) % 2**32 < 2**31


@dataclass
class _Link:
    link: cp.CompactLink
    pump: asyncio.Task[None] | None = None


class CompactBridge:
    """One compact endpoint served as a device server; see the module docstring.

    Args:
        name: the upstream's name (the gateway prefixes the device id with it).
        port: ``/dev/ttyACM0``, ``pty:/dev/pts/3``, ``unix:/path`` or ``tcp://host:port`` (:func:`bhms.transport.compact.open_stream`).
        sidecar: the full ``DeviceDescription`` (without ``digest``) with ``compact`` layouts, as a dict or a JSON file path.
        baud: serial speed.
        state_dir: directory of the bridge's journal (``None``: in memory, a new epoch and no durability; tests only).
        timing: :class:`Timing`.
        opener: ``await opener(port, baud)`` returns the byte stream (replaceable in tests).
    """

    def __init__(self, name: str, port: str, sidecar: dict[str, Any] | str | os.PathLike[str], *, baud: int = 115200,
                 state_dir: str | os.PathLike[str] | None = None, timing: Timing | None = None,
                 opener: Callable[[str, int], Awaitable[cp.ByteStream]] = cp.open_stream) -> None:
        self.name, self.port, self.baud, self.timing = name, port, baud, timing or Timing()
        self.opener = opener
        raw = json.loads(Path(sidecar).read_text()) if isinstance(sidecar, str | os.PathLike) else dict(sidecar)
        problems = cp.layout_problems(raw)
        if problems:
            raise ValueError("the sidecar violates the compact layout rules: " + "; ".join(f"{r}: {m}" for r, m in problems[:5]))
        self.layouts = cp.layouts_from_description(raw)
        self.sidecar = {k: v for k, v in raw.items() if k != "digest"}
        self.digest8 = cp.digest8_of(self.sidecar)
        self.device_id: str = self.sidecar["deviceId"]
        self.prefix = f"compact/{self.device_id}/"
        options: dict[str, Any] = {"state_dir": state_dir} if state_dir is not None else {"store": None}
        self.server = DeviceServer(f"compact-{name}", policy=gateway_policy(), programs=False, **options)
        self.device: Device | None = None
        self.hello: cp.Hello | None = None
        self.epoch: int | None = None
        self.persistent = False
        self.next_handle = 1
        self.up = False
        self.mismatch = False
        self._link: cp.CompactLink | None = None
        self._waiters: dict[tuple[str, int], asyncio.Queue[Any]] = {}
        self._hello_waiter: tuple[int, asyncio.Future[cp.Incoming]] | None = None
        self._stop_waiters: list[asyncio.Queue[cp.Incoming]] = []
        self._by_handle: dict[tuple[int, int], str] = {}
        self._action_names = {a.index: n for n, a in self.layouts.actions.items()}
        self._property_names = {p.index: n for n, p in self.layouts.properties.items()}
        self._request = 0
        self._needs_hello = asyncio.Event()
        self._frame_seen = asyncio.Event()
        self._runner: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._reconcile_pending = False
        self._closing = False
        self._started = False

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Open the journal and start supervising the link (idempotent). The device appears once HELLO matches."""
        if self._started:
            return
        self._started = True
        await self.server.start()
        self.server.journal.on_settled.append(self._settled)
        self._runner = asyncio.get_running_loop().create_task(self._run(), name=f"bhms-compact-{self.name}")

    async def close(self) -> None:
        self._closing = True
        tasks = [t for t in (self._runner, *self._tasks) if t is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self._link is not None:
            await self._link.close()
            self._link = None
        if self._started:
            await self.server.close()
            self._started = False

    async def connector(self) -> Transport:
        """What a gateway's ``UpstreamConfig(connector=...)`` calls: an in-memory connection to this server."""
        await self.start()
        assert self.server.rpc is not None
        return await connect_in_process(self.server.rpc)

    aclose = close

    def _spawn(self, coro: Any) -> asyncio.Task[Any]:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    @property
    def ready(self) -> bool:
        return self.up and self._link is not None and not self._link.closed and self.hello is not None

    # ------------------------------------------------------------------ link supervision

    async def _run(self) -> None:
        attempt = 0
        while not self._closing:
            try:
                stream = await self.opener(self.port, self.baud)
            except (OSError, ConnectionError) as exc:
                log.warning("compact %s: cannot open %s: %s", self.name, self.port, exc)
                await asyncio.sleep(min(0.2 * 2 ** attempt, 5.0))
                attempt += 1
                continue
            attempt = 0
            link = cp.CompactLink(stream)
            link.start()
            self._link = link
            pump = asyncio.get_running_loop().create_task(self._pump(link))
            try:
                await self._session(link, pump)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a failing session ends this connection; the loop reopens it
                log.exception("compact %s: session failed", self.name)
            finally:
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
                self._go_down("the link to the endpoint ended")
                await link.close()
                self._link = None
            if not self._closing:
                await asyncio.sleep(0.2)

    async def _session(self, link: cp.CompactLink, pump: asyncio.Task[None]) -> None:
        """HELLO, then watch the link until it is lost or an epoch change asks for a new HELLO."""
        while not pump.done():
            hello = await self._race(self._handshake(link), pump)
            if hello is None:
                return
            if not self._adopt(hello, link):
                await self._race(asyncio.sleep(max(self.timing.probe, 1.0)), pump)
                continue
            await self._race(self._monitor(link), pump)

    @staticmethod
    async def _race(coro: Awaitable[Any], pump: asyncio.Task[None]) -> Any:
        """Run ``coro`` unless the link's pump ends first (then None)."""
        work = asyncio.ensure_future(coro)
        try:
            await asyncio.wait({work, pump}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            if not work.done():
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
        return work.result() if work.done() and not work.cancelled() else None

    async def _handshake(self, link: cp.CompactLink, *, new_session: bool = False) -> cp.Hello:
        """HELLO_REQ until the endpoint answers (a board that just reset may take a while)."""
        flags = cp.HELLO_NEW_SESSION if new_session else 0
        while True:
            nonce = random.getrandbits(32)
            future: asyncio.Future[cp.Incoming] = asyncio.get_running_loop().create_future()
            self._hello_waiter = (nonce, future)
            link.send(cp.HelloReq(nonce, flags), session=self.epoch or 0)
            try:
                reply = await asyncio.wait_for(asyncio.shield(future), self.timing.hello)
            except asyncio.TimeoutError:
                continue
            finally:
                self._hello_waiter = None
            assert isinstance(reply.message, cp.Hello)
            return reply.message

    async def _monitor(self, link: cp.CompactLink) -> None:
        """Probe an idle link, ask for a new HELLO on evidence of a restart, reconcile unknown operations."""
        misses = 0
        last_reconcile = 0.0
        while True:
            self._frame_seen.clear()
            try:
                await asyncio.wait_for(self._needs_hello.wait(), self.timing.probe)
            except asyncio.TimeoutError:
                pass
            if self._needs_hello.is_set():
                self._needs_hello.clear()
                log.info("compact %s: the endpoint's epoch changed; asking for a new HELLO", self.name)
                return
            if self._frame_seen.is_set():
                misses = 0
            else:
                link.send(cp.Query(PROBE_HANDLE), session=self.epoch or 0)
                try:
                    await asyncio.wait_for(self._frame_seen.wait(), self.timing.reply)
                    misses = 0
                except asyncio.TimeoutError:
                    misses += 1
                    if misses >= self.timing.probe_misses:
                        self._go_down(f"no answer to {misses} probes")
                        return
            if time.monotonic() - last_reconcile >= max(5.0, self.timing.probe) and self._unknown_operations():
                last_reconcile = time.monotonic()
                self._kick_reconcile()

    def _go_down(self, why: str) -> None:
        was_up = self.up
        self.up = False
        self.hello = None
        if was_up:
            log.warning("compact %s: %s", self.name, why)
        if self.device is not None:
            self.device.set_status("offline")

    # ------------------------------------------------------------------ incoming frames

    async def _pump(self, link: cp.CompactLink) -> None:
        try:
            while True:
                incoming = await link.receive()
                assert incoming is not None
                try:
                    self._on_incoming(incoming)
                except Exception:  # noqa: BLE001 - one bad frame must not end the link
                    log.exception("compact %s: handling %r failed", self.name, incoming.message)
        except cp.LinkClosed:
            return

    def _on_incoming(self, incoming: cp.Incoming) -> None:
        message = incoming.message
        self._frame_seen.set()
        if self.device is not None and self.up:
            self.device.report_alive()
        if isinstance(message, cp.Hello):
            waiter = self._hello_waiter
            if waiter is not None and waiter[0] == message.nonce and not waiter[1].done():
                waiter[1].set_result(incoming)
            return
        stale = self.epoch is not None and incoming.session != self.epoch
        if stale:
            self._needs_hello.set()  # a frame of another epoch: the endpoint restarted since we last said HELLO
            if not isinstance(message, cp.Error | cp.StopAck):
                return
        if isinstance(message, cp.StopAck):
            for queue in list(self._stop_waiters):
                queue.put_nowait(incoming)
            return
        if isinstance(message, cp.Error):
            key = ("r", message.ident) if message.request_type == cp.READ else ("h", message.ident)
        elif isinstance(message, cp.Value):
            if message.request == 0:
                self._spawn(self._publish(message))
                return
            key = ("r", message.request)
        elif isinstance(message, cp.Status | cp.Result):
            key = ("h", message.handle)
        else:
            return
        queue = self._waiters.get(key)
        if queue is not None:
            queue.put_nowait(incoming)
        elif isinstance(message, cp.Result):
            self._kick_reconcile()  # a RESULT nobody waits for: an operation that was unknown may be settled by it

    def _register(self, key: tuple[str, int]) -> asyncio.Queue[Any]:
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._waiters[key] = queue
        return queue

    def _unregister(self, key: tuple[str, int]) -> None:
        self._waiters.pop(key, None)

    def _broadcast(self, event: LinkEvent) -> None:
        for key, queue in list(self._waiters.items()):
            if key[0] == "h":
                queue.put_nowait(event)

    # ------------------------------------------------------------------ HELLO and epochs (BHMS-CMP-020..023)

    def _adopt(self, hello: cp.Hello, link: cp.CompactLink) -> bool:
        """Apply a HELLO: check the digest, handle the epoch, serve the device. Returns whether the endpoint is served."""
        if hello.version != cp.COMPACT_VERSION:
            log.error("compact %s: the endpoint speaks compact version %d; this bridge speaks %d", self.name, hello.version,
                      cp.COMPACT_VERSION)
            return False
        if hello.digest8 != self.digest8:
            self.mismatch = True
            self._go_down("digest mismatch")
            log.error("compact %s: the endpoint reports description digest %s but the sidecar %s has %s; the device is "
                      "not served (BHMS-DEV-021)", self.name, hello.digest8.hex(), self.device_id, self.digest8.hex())
            return False
        self.mismatch = False
        state = self._link_state()
        known = self.epoch if self.epoch is not None else state.get("epoch")
        changed = known is not None and known != hello.epoch
        possible_reset = known is not None and known == hello.epoch and not hello.persistent
        proven = changed and (self._new_session_pending or (hello.persistent and advanced(known, hello.epoch)))
        self._new_session_pending = False
        self.hello, self.epoch, self.persistent = hello, hello.epoch, hello.persistent
        link.session = hello.epoch
        if changed or known is None:
            link.reset_sequence()
        base = 1 if changed or known is None else state.get("next_handle", 1)
        self.next_handle = max(base, hello.last_handle + 1)
        self._save_link_state()
        self._load_handles()
        if changed or possible_reset:
            if known is not None:
                self._emit_epoch(hello, changed, proven)
            self._broadcast(LinkEvent("epoch" if changed else "reset", proven))
        else:
            self._broadcast(LinkEvent("up"))
        if proven:
            self._lift_inhibitions(f"the endpoint reported boot epoch {hello.epoch} after {known} "
                                   f"({'persistent counter advanced' if hello.persistent else 'accepted NEW_SESSION'}), so it "
                                   "has purged the old work (BHMS-CMP-022, BHMS-OPS-042)")
        self._needs_hello.clear()
        self.up = True
        self._serve()
        self._kick_reconcile()
        return True

    _new_session_pending = False

    def _emit_epoch(self, hello: cp.Hello, changed: bool, proven: bool) -> None:
        reason = ("the endpoint reports a new boot epoch" if changed else
                  "the endpoint has no persistent epoch, so every HELLO may follow a reset (BHMS-CMP-020)")
        with contextlib.suppress(StoreError):
            self.server.events.append("device.epoch", severity="warning", device_id=self.device_id,
                                      message=f"{reason}; operations dispatched before are unknown",
                                      data={"epoch": hello.epoch, "persistent": hello.persistent, "purged": proven})

    def _serve(self) -> None:
        if self.device is None:
            self.device = self.server.device_from_description(
                self.sidecar, run=self._action_handler, read=self._property_getter, hold=self._hold,
                stop=self._stop if self.sidecar["safety"].get("stop") == "supported" else None,
                read_timeout_ms=int(self.timing.reply * 1000 * 2))
            self.device.liveness_s = max(10.0, self.timing.probe * 5)
            self.device.reconcile(self._reconcile)
            log.info("compact %s: serving %s (epoch %d, persistent %s, ring %d, fencing %s, stop %s)", self.name,
                     self.device_id, self.epoch, self.persistent, self.hello.ring if self.hello else 0,
                     self.hello.fencing if self.hello else False, self.hello.stop_supported if self.hello else False)
        self.device.set_status(None)
        self.device.report_alive()

    # ------------------------------------------------------------------ durable records

    def _link_state(self) -> dict[str, Any]:
        raw = self.server.store.meta_get(self.prefix + "link")
        return json.loads(raw) if raw else {}

    def _link_json(self) -> str:
        return json.dumps({"epoch": self.epoch, "persistent": self.persistent, "next_handle": self.next_handle})

    def _save_link_state(self) -> None:
        try:
            self.server.store.meta_set(self.prefix + "link", self._link_json(), barrier=True)
        except StoreError as exc:
            self.server.journal_failed(exc)

    def _info(self, op_id: str) -> Info | None:
        raw = self.server.store.meta_get(f"{self.prefix}ops/{op_id}")
        return Info.load(raw) if raw else None

    def _load_handles(self) -> None:
        self._by_handle.clear()
        for key, raw in self.server.store.meta_prefix(self.prefix + "ops/").items():
            info = Info.load(raw)
            self._by_handle[(info.epoch, info.handle)] = key.rsplit("/", 1)[1]

    def _settled(self, rec: OperationRecord) -> None:
        if rec.op.get("deviceId") != self.device_id or not rec.terminal:
            return
        info = self._info(rec.id)
        if info is not None:
            self._by_handle.pop((info.epoch, info.handle), None)
            with contextlib.suppress(StoreError):
                self.server.store.meta_delete(f"{self.prefix}ops/{rec.id}")

    def _unknown_operations(self) -> list[OperationRecord]:
        found = []
        for row in self.server.store.operations_in_states(["unknown"]):
            if row.record.get("kind") == "action" and row.record.get("deviceId") == self.device_id:
                rec = self.server.journal.get(row.id)
                if rec is not None:
                    found.append(rec)
        return found

    def _lift_inhibitions(self, why: str) -> None:
        """Operations dispatched before the proven purge stay unknown but no longer block their resources (BHMS-OPS-042)."""
        for rec in self._unknown_operations():
            info = self._info(rec.id)
            if info is not None and info.epoch == self.epoch:
                continue
            self.server.executor.lift_inhibition(rec)
            with contextlib.suppress(StoreError):
                self.server.journal.mark_private(rec, inhibitionLifted=True)
                self.server.journal.annotate(rec, "evidence", why)
        self.server.executor.pump()

    # ------------------------------------------------------------------ actions

    def _action_handler(self, name: str) -> Callable[..., Awaitable[Any]]:
        layout = self.layouts.actions[name]
        cancellable = self.sidecar["actions"][name]["cancel"] == "supported"

        async def run(ctx: ActionContext, **arguments: Any) -> Any:
            return await self._invoke(ctx, name, layout, cancellable, arguments)

        run.__name__ = name
        return run

    async def _hold(self, ctx: ActionContext) -> None:
        """``onLeaseLoss: hold``: the compact binding has no hold command; a cancellable running handler sends CANCEL when
        the executor signals it (it observes ``ctx.cancelled``), which is the endpoint's way to stop moving."""

    @staticmethod
    def _refusal(message: str, code: str, proof: str) -> DeviceFault:
        return DeviceFault(message, proof=proof, effect="none", code=code)

    async def _invoke(self, ctx: ActionContext, name: str, layout: cp.ActionLayout, cancellable: bool,
                      arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            args = cp.encode_fields(layout.args, arguments)
        except cp.CompactValueError as exc:
            raise self._refusal(str(exc), exc.code, "refused by the bridge before sending (BHMS-CMP-010); "
                                                    "nothing reached the endpoint") from None
        hello = self.hello
        if not self.ready or hello is None:
            raise self._refusal(f"{self.device_id} is not reachable", "DEVICE_UNAVAILABLE",
                                "the link was down when the operation was dispatched; nothing was sent")
        if len(args) > hello.max_args:
            raise self._refusal(f"{name}: {len(args)} argument bytes exceed the endpoint's limit of {hello.max_args}",
                                "OUT_OF_RANGE", "refused by the bridge before sending; nothing reached the endpoint")
        fence = ctx.fence or 0
        if fence > 0xFFFFFFFF:
            raise self._refusal("the lease fence does not fit the 32-bit fence field; start a new session",
                                "FENCED", "refused by the bridge before sending; nothing reached the endpoint")
        if self.next_handle >= HANDLE_ROTATE_AT:
            await self._rotate()
        if self.next_handle > 0xFFFF:
            raise self._refusal("the endpoint's operation handles are exhausted and a new session could not be started "
                                "(an operation is active)", "BUSY", "nothing was sent; retry when the endpoint is idle")
        handle = self._assign(ctx.operation_id, layout.index)
        message = cp.Invoke(handle, layout.index, args, fence, 0)
        try:
            return await self._drive(ctx, handle, message, layout, cancellable)
        except OutcomeUnknown as unknown:
            if unknown.lift:  # the epoch advance proved the old work purged: the resources are free (BHMS-OPS-042)
                rec = self.server.journal.get(ctx.operation_id)
                if rec is not None:
                    with contextlib.suppress(StoreError):
                        self.server.journal.mark_private(rec, inhibitionLifted=True)
                        self.server.journal.annotate(rec, "evidence", "the endpoint's boot epoch advanced: it purged this "
                                                     "operation's work; the outcome stays unknown (BHMS-CMP-022)")
            raise


    def _assign(self, op_id: str, action: int) -> int:
        """Take the next handle and record it with its epoch durably, before anything is sent (BHMS-CMP-030)."""
        assert self.epoch is not None
        handle = self.next_handle
        self.next_handle += 1
        info = Info(handle, self.epoch, self.persistent, action)
        try:
            self.server.store.meta_set_many({f"{self.prefix}ops/{op_id}": info.dump(), self.prefix + "link": self._link_json()},
                                            barrier=True)
        except StoreError as exc:
            self.server.journal_failed(exc)
            raise self._refusal("the bridge journal cannot be written", "BUSY",
                                "nothing was sent: the handle could not be recorded first") from None
        self._by_handle[(self.epoch, handle)] = op_id
        return handle

    async def _rotate(self) -> None:
        """Begin a new session before the handle space runs out; the endpoint honours it only while idle (BHMS-CMP-023)."""
        link = self._link
        if link is None or not self.ready or any(key[0] == "h" for key in self._waiters):
            return
        self._new_session_pending = True
        try:
            hello = await asyncio.wait_for(self._handshake(link, new_session=True), self.timing.hello * 4)
        except asyncio.TimeoutError:
            self._new_session_pending = False
            return
        self._adopt(hello, link)

    async def _drive(self, ctx: ActionContext, handle: int, invoke: cp.Invoke, layout: cp.ActionLayout,
                     cancellable: bool) -> dict[str, Any]:
        """Send the INVOKE and follow it to a terminal outcome; see the module docstring for the policy."""
        key = ("h", handle)
        queue = self._register(key)
        loop = asyncio.get_running_loop()
        link = self._link
        assert link is not None
        timing = self.timing
        sent_epoch = self.epoch
        invokes, queries, silent = 1, 0, 0
        heard, cancel_wanted, cancel_sent = False, False, False
        link.send(invoke, session=sent_epoch)
        next_try = loop.time() + timing.reply
        try:
            while True:
                kind, item = await self._next(queue, ctx, next_try - loop.time(),
                                              watch_cancel=cancellable and not cancel_wanted)
                if kind == "cancel":
                    cancel_wanted = True  # CANCEL goes out once the endpoint has answered: until then it may not know the handle
                elif kind == "timeout":
                    silent += 1
                    if silent > timing.retries:
                        raise OutcomeUnknown(f"the endpoint did not answer {invokes} INVOKE and {queries} QUERY "
                                             f"transmissions for handle {handle}")
                    if not heard and self.persistent and self.epoch == sent_epoch:
                        link.send(invoke, session=sent_epoch)  # BHMS-CMP-033: only to a persistent-epoch endpoint
                        invokes += 1
                    else:
                        link.send(cp.Query(handle), session=self.epoch or 0)
                        queries += 1
                    next_try = loop.time() + (timing.poll if heard else timing.reply)
                elif kind == "event":
                    if item.kind in ("epoch", "reset"):
                        raise OutcomeUnknown(
                            "the endpoint restarted (it reports a new boot epoch)" if item.kind == "epoch" else
                            "the endpoint answered HELLO without a persistent epoch, so it may have restarted",
                            lift=item.proven)
                    next_try = loop.time()  # the link is back with the same epoch: ask at once
                else:
                    message = item.message
                    silent = 0
                    if isinstance(message, cp.Error):
                        self._on_error(ctx, message, invokes, queries)
                    else:
                        heard = True
                        next_try = loop.time() + timing.poll
                        if isinstance(message, cp.Result):
                            return self._finish(message, layout)
                        await self._on_status(ctx, message)
                        if message.state == cp.ST_REJECTED:
                            raise DeviceFault("the endpoint rejected the operation", effect="none",
                                              proof="the endpoint reported the operation rejected: it did not start")
                if heard and cancel_wanted and not cancel_sent:
                    link.send(cp.Cancel(handle), session=self.epoch or 0)
                    cancel_sent = True
        finally:
            self._unregister(key)

    async def _next(self, queue: asyncio.Queue[Any], ctx: ActionContext, timeout: float, *, watch_cancel: bool
                    ) -> tuple[str, Any]:
        """The next thing to react to: a message, a link event, the cancel request or a timeout."""
        getter = asyncio.ensure_future(queue.get())
        watchers: set[asyncio.Future[Any]] = {getter}
        cancel = asyncio.ensure_future(ctx.cancelled.wait()) if watch_cancel else None
        if cancel is not None:
            watchers.add(cancel)
        try:
            done, _ = await asyncio.wait(watchers, timeout=max(0.0, timeout), return_when=asyncio.FIRST_COMPLETED)
        finally:
            for future in watchers:
                if not future.done():
                    future.cancel()
            await asyncio.gather(*watchers, return_exceptions=True)
        if getter in done and not getter.cancelled():
            item = getter.result()
            return ("event", item) if isinstance(item, LinkEvent) else ("message", item)
        if cancel is not None and cancel in done:
            return "cancel", None
        return "timeout", None

    def _on_error(self, ctx: ActionContext, message: cp.Error, invokes: int, queries: int) -> None:
        """React to an ERROR for this handle: raise the operation's outcome, or return when it only concerns a CANCEL."""
        code = message.code
        detail = f" (detail {message.detail})" if message.detail else ""
        if message.request_type == cp.CANCEL:
            if code == cp.E_HANDLE_UNKNOWN:
                raise OutcomeUnknown("the endpoint no longer knows the handle (HANDLE_UNKNOWN answering CANCEL)")
            self._spawn(ctx.refuse_cancel(f"the endpoint refused the cancellation: {message.name}{detail}"))
            return
        if code == cp.E_SESSION_MISMATCH:
            self._needs_hello.set()
            if message.request_type == cp.INVOKE and invokes == 1 and queries == 0:
                raise self._refusal(f"the endpoint restarted before it saw the command (SESSION_MISMATCH{detail})", "STALE",
                                    "the endpoint refused a frame of another session without effect (BHMS-CMP-021)")
            raise OutcomeUnknown("the endpoint restarted (SESSION_MISMATCH) after the command may have reached it")
        if code in (cp.E_HANDLE_UNKNOWN, cp.E_HANDLE_CONFLICT):
            raise OutcomeUnknown(f"the endpoint answered {message.name} for the handle: it may have executed the command "
                                 "and no longer holds the outcome" if code == cp.E_HANDLE_UNKNOWN else
                                 "the endpoint holds another command under this handle (HANDLE_CONFLICT, a bridge bug)")
        mapped = _ERROR_CODE.get(code, "INTERNAL")
        raise self._refusal(f"the endpoint refused the command: {message.name}{detail}", mapped,
                            f"the endpoint answered {message.name}, which guarantees it did not start the operation")

    async def _on_status(self, ctx: ActionContext, status: cp.Status) -> None:
        if status.state == cp.ST_RUNNING:
            await ctx.running()
        if status.progress != cp.PROGRESS_UNKNOWN and status.progress <= 100:
            await ctx.progress(status.progress / 100)
        if status.cancel == cp.CANCEL_ACK:
            await ctx.acknowledge_cancel()
        elif status.cancel == cp.CANCEL_REFUSED:
            await ctx.refuse_cancel("the endpoint refused the cancellation")

    def _finish(self, message: cp.Result, layout: cp.ActionLayout) -> dict[str, Any]:
        if message.state == cp.ST_COMPLETED:
            try:
                return cp.decode_fields(layout.result, message.fields)
            except cp.CompactError as exc:
                raise OutcomeUnknown(f"the endpoint's RESULT cannot be read ({exc})") from None
        if message.state == cp.ST_FAILED:
            raise DeviceFault(f"the endpoint reported device fault {message.fault}",
                              partial=f"evidence {message.evidence}" if message.evidence else None)
        if message.state == cp.ST_CANCELED:
            raise Canceled(detail="the endpoint reported the operation canceled")
        raise DeviceFault("the endpoint rejected the operation", proof="the endpoint's RESULT says rejected: it did not start",
                          effect="none")

    # ------------------------------------------------------------------ reconciliation (BHMS-CMP-034)

    def _kick_reconcile(self) -> None:
        if self._reconcile_pending or self._closing or not self._started:
            return
        self._reconcile_pending = True

        async def run() -> None:
            await asyncio.sleep(0.05)
            self._reconcile_pending = False
            if self.ready and self.device is not None:
                with contextlib.suppress(Exception):
                    await self.server.reconcile(self.device_id)

        self._spawn(run())

    async def _reconcile(self, op: dict[str, Any]) -> Reconciled | None:
        info = self._info(op["operationId"])
        if info is None:
            return Reconciled("failed", evidence="the bridge journaled no handle for this operation, so no INVOKE was ever "
                              "sent to the endpoint", may_have_acted=False, effect="none", code="INTERNAL",
                              message="the operation was dispatched but its command never reached the wire")
        if not self.ready or info.epoch != self.epoch:
            return None  # earlier epoch: unknown stays (BHMS-CMP-022); link down: ask again when it is up
        reply = await self._ask(info.handle)
        if reply is None:
            return None
        message = reply.message
        layout = self.layouts.actions[self._action_names[info.action]]
        if isinstance(message, cp.Result):
            where = "the endpoint answered QUERY with its RESULT"
            if message.state == cp.ST_COMPLETED:
                try:
                    return Reconciled("completed", evidence=where, result=cp.decode_fields(layout.result, message.fields))
                except cp.CompactError:
                    return None
            if message.state == cp.ST_FAILED:
                return Reconciled("failed", evidence=f"{where}: device fault {message.fault}",
                                  message=f"the endpoint reported device fault {message.fault}")
            if message.state == cp.ST_CANCELED:
                return Reconciled("canceled", evidence=f"{where}: canceled")
            return Reconciled("failed", evidence=f"{where}: rejected, it did not start", may_have_acted=False, effect="none")
        return None  # still running (its RESULT will arrive unprompted), HANDLE_UNKNOWN or a mismatch: evidence is missing

    async def _ask(self, handle: int) -> cp.Incoming | None:
        """QUERY ``handle`` and return the endpoint's STATUS or RESULT, or None (silence, an ERROR)."""
        link = self._link
        key = ("h", handle)
        if link is None or key in self._waiters:
            return None
        queue = self._register(key)
        loop = asyncio.get_running_loop()
        try:
            for _ in range(2):
                link.send(cp.Query(handle), session=self.epoch or 0)
                deadline = loop.time() + self.timing.reply
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), max(0.0, deadline - loop.time()))
                    except asyncio.TimeoutError:
                        break
                    if isinstance(item, cp.Incoming):  # (link events are not for a bare QUERY)
                        return item if isinstance(item.message, cp.Result | cp.Status) else None
            return None
        finally:
            self._unregister(key)

    # ------------------------------------------------------------------ stop (BHMS-CMP-050)

    async def _stop(self, ctx: Any) -> None:
        link = self._link
        if link is None or link.closed:
            raise ConnectionError("no link to the endpoint: STOP could not be sent")
        spec = self.server.devices[self.device_id].stop_spec
        assert spec is not None
        bound = (spec.max_duration_ms or self.timing.stop_confirm * 1000) / 1000
        queue: asyncio.Queue[cp.Incoming] = asyncio.Queue()
        self._stop_waiters.append(queue)
        try:
            ack: cp.StopAck | None = None
            for _ in range(self.timing.retries + 1):
                link.send(cp.Stop(STOP_REASON_GATEWAY), session=self.epoch or 0)
                try:
                    first = await asyncio.wait_for(queue.get(), self.timing.reply)
                except asyncio.TimeoutError:
                    continue
                ack = first.message  # type: ignore[assignment]
                break
            if ack is None:
                raise TimeoutError("the endpoint did not acknowledge STOP")
            if ack.outcome == cp.STOPACK_UNSUPPORTED:
                raise RuntimeError("the endpoint has no stop procedure although its description declares one")
            if ack.outcome == cp.STOPACK_INITIATED:
                ack = None
                deadline = asyncio.get_running_loop().time() + bound
                while ack is None:
                    left = deadline - asyncio.get_running_loop().time()
                    second = await asyncio.wait_for(queue.get(), max(0.0, left))
                    if isinstance(second.message, cp.StopAck) and second.message.outcome == cp.STOPACK_CONFIRMED:
                        ack = second.message
            if ack.evidence < (cp.EVIDENCE_MEASURED if spec.evidence == "measured" else cp.EVIDENCE_REPORTED):
                raise RuntimeError(f"the endpoint confirmed STOP with evidence {ack.evidence}, weaker than the declared "
                                   f"{spec.evidence}: a stop without the declared evidence is never confirmed (BHMS-AUTH-022)")
        finally:
            self._stop_waiters.remove(queue)

    # ------------------------------------------------------------------ properties (BHMS-CMP-060)

    def _property_getter(self, name: str) -> Callable[..., Awaitable[Reading]]:
        layout = self.layouts.properties[name]
        retry = self.sidecar["properties"][name].get("readEffect", "none") == "none"

        async def read() -> Reading:
            link = self._link
            if not self.ready or link is None:
                raise ConnectionError(f"{self.device_id} is not reachable")
            self._request = self._request % 0xFFFF + 1
            while ("r", self._request) in self._waiters:
                self._request = self._request % 0xFFFF + 1
            request = self._request
            key = ("r", request)
            queue = self._register(key)
            try:
                for _ in range(2 if retry else 1):
                    link.send(cp.Read(request, layout.index, cp.READ_FRESH), session=self.epoch or 0)
                    try:
                        item = await asyncio.wait_for(queue.get(), self.timing.reply)
                    except asyncio.TimeoutError:
                        continue
                    if isinstance(item.message, cp.Error):
                        raise BhmsError("INVALID_ARGUMENT", f"the endpoint refused READ: {item.message.name}")
                    return self._reading(item.message, layout)
                raise asyncio.TimeoutError(f"no VALUE for {name}")
            finally:
                self._unregister(key)

        return read

    def _reading(self, message: cp.Value, layout: cp.PropertyLayout) -> Reading:
        quality = cp.QUALITY_NAMES.get(message.quality, "unknown")
        evidence = cp.VALUE_EVIDENCE_NAMES.get(message.evidence)
        value = None
        if message.quality in (cp.Q_VALID, cp.Q_STALE):
            value = cp.decode_value(layout.type, layout.scale, message.raw)
        elif message.raw:
            raise cp.CompactError("VALUE with quality invalid/unknown must carry no value bytes (BHMS-CMP-060)")
        # An invalid or unknown reading has no value to age; its acquisition attempt is as old as this reply.
        age = 0.0 if value is None else (None if message.age_ms == cp.AGE_UNKNOWN else float(message.age_ms))
        return Reading(value, quality, evidence, latency_ms=age, sequence=message.sequence, epoch=f"compact:{self.epoch}")

    async def _publish(self, message: cp.Value) -> None:
        name = self._property_names.get(message.prop)
        if name is None or self.device is None:
            return
        layout = self.layouts.properties[name]
        try:
            reading = self._reading(message, layout)
            await self.server.observations.publish(
                self.device, name, reading.value, quality=reading.quality, evidence=reading.evidence,
                latency_ms=reading.latency_ms, sequence=reading.sequence, epoch=reading.epoch)
        except Exception:  # noqa: BLE001 - an unreadable unsolicited VALUE is dropped
            log.warning("compact %s: dropped an unsolicited VALUE for property %d", self.name, message.prop, exc_info=True)


@dataclass
class CompactUpstream:
    """The ``connector`` of a gateway upstream with ``type = "compact"``: starts the bridge on first use and connects the
    gateway to it in memory, again after every gateway reconnect (the bridge and its link outlive a connection).
    ``aclose`` is called by the gateway when the upstream closes."""

    bridge: CompactBridge
    name: str = field(init=False)

    def __post_init__(self) -> None:
        self.name = self.bridge.name

    async def __call__(self) -> Transport:
        return await self.bridge.connector()

    async def aclose(self) -> None:
        await self.bridge.close()


__all__ = ["CompactBridge", "CompactUpstream", "Info", "LinkEvent", "OutcomeUnknown", "Timing", "advanced", "gateway_policy"]
