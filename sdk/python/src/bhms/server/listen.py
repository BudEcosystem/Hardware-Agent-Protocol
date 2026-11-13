"""``subscriptions/listen`` for :class:`~bhms.server.server.DeviceServer` (spec/bhms/03-lifecycle.md §3.7).

:meth:`Subscriptions.listen` returns an async generator that the session pumps (the session owns the bounded
per-subscription queue and the LIF-043 overflow policy). It yields, in order:

1. ``notifications/subscriptions/acknowledged`` with the honoured filter, a ``refused`` entry per part it will not honour
   (unknown device → ``UNKNOWN_DEVICE``, unknown property → ``INVALID_ARGUMENT``, non-observable property →
   ``UNSUPPORTED`` (BHMS-OBS-020), over the per-subscription limits → ``OUT_OF_RANGE``) and ``eventsGap`` (BHMS-LIF-040);
2. retained events after ``events.after``, then live events with no duplicate and no omission at the seam
   (BHMS-EVT-020) — the live listener is registered before the retained read, both on one loop iteration;
3. live ``notifications/operation`` (every state/cancel/effect change of visible operations, in change order,
   BHMS-OPS-090), ``notifications/observation`` (rate-limited, BHMS-LIF-043/OBS-021), ``notifications/event`` and
   ``notifications/devices/listChanged``;
4. a final ``{"endReason": "shutdown"}`` when the server closes, or ``"unauthorized"`` when a policy change removes the
   principal's ``read`` scope (BHMS-LIF-042/044).

Only the notification types the client asked for are produced (BHMS-LIF-041); the session tags each with
``_meta["bhms/subscriptionId"]``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any

from bhms.jsonrpc.session import Complete, Notification, RequestContext
from bhms.protocol.types import to_wire

if TYPE_CHECKING:
    from bhms.runtime.authority import Principal
    from bhms.runtime.operations import OperationRecord
    from bhms.server.server import DeviceServer

MAX_OBSERVATIONS = 256
MAX_OPERATION_IDS = 256


class _Feed:
    """One subscription's local buffer between runtime callbacks and its generator."""

    def __init__(self) -> None:
        self.items: deque[tuple[str, dict[str, Any]]] = deque()
        self.wake = asyncio.Event()

    def push(self, method: str, params: dict[str, Any]) -> None:
        self.items.append((method, params))
        self.wake.set()


class Subscriptions:
    """All live ``subscriptions/listen`` streams of one server."""

    def __init__(self, server: DeviceServer) -> None:
        self.server = server
        self._feeds: set[_Feed] = set()
        self._list_changed: set[_Feed] = set()
        self._policy_version = 0
        self._active = 0
        self._idle = asyncio.Event()
        self._idle.set()

    # ------------------------------------------------------------------ server-side triggers

    def devices_changed(self) -> None:
        for feed in list(self._list_changed):
            feed.push("notifications/devices/listChanged", {})

    def policy_changed(self) -> None:
        self._policy_version += 1
        for feed in list(self._feeds):
            feed.wake.set()

    async def drain(self, timeout: float) -> None:
        """Wake every stream so it ends with ``endReason: shutdown``; wait up to ``timeout`` for them to finish."""
        for feed in list(self._feeds):
            feed.wake.set()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._idle.wait(), timeout)

    # ------------------------------------------------------------------ listen

    def listen(self, principal: Principal, params: Any, ctx: RequestContext) -> AsyncIterator[Any]:
        """Prepare the subscription (validating cursors before anything is sent) and return its stream."""
        srv = self.server
        flt = params.notifications
        feed = _Feed()
        cleanups: list[Callable[[], None]] = []
        honoured: dict[str, Any] = {}
        refused: list[dict[str, Any]] = []
        replay: list[tuple[int, dict[str, Any]]] = []
        events_gap = False
        try:
            if flt.devices_list_changed:
                honoured["devicesListChanged"] = True
                self._list_changed.add(feed)
                cleanups.append(lambda: self._list_changed.discard(feed))
            if flt.operations is not None:
                ops = flt.operations
                wire = to_wire(ops)
                if ops.operation_ids is not None and len(ops.operation_ids) > MAX_OPERATION_IDS:
                    refused.append({"path": "notifications.operations.operationIds", "bhmsCode": "OUT_OF_RANGE",
                                    "hint": f"subscribe to at most {MAX_OPERATION_IDS} operation ids"})
                else:
                    honoured["operations"] = wire
                    cleanups.append(self._watch_operations(principal, ops, feed))
            if flt.observations:
                accepted = []
                for index, item in enumerate(flt.observations):
                    path = f"notifications.observations[{index}]"
                    problem = self._observation_problem(principal, item, index)
                    if problem is not None:
                        refused.append({"path": path, **problem})
                        continue
                    dev = srv.devices[item.device_id]
                    cleanups.append(srv.observations.subscribe(
                        dev, item.property, item.min_interval_ms,
                        lambda p: feed.push("notifications/observation", p)))
                    accepted.append(to_wire(item))
                if accepted:
                    honoured["observations"] = accepted
            if flt.events is not None:
                ev = flt.events
                if not principal.can_read:
                    refused.append({"path": "notifications.events", "bhmsCode": "UNAUTHORIZED",
                                    "hint": "events need the read scope"})
                else:
                    start, events_gap = srv.events.start_position(ev.after, "notifications.events.after")
                    device_ids = set(ev.device_ids) if ev.device_ids is not None else None
                    types = set(ev.types) if ev.types is not None else None

                    def on_event(event: dict[str, Any], seq: int) -> None:
                        if (device_ids is None or event.get("deviceId") in device_ids) and \
                                (types is None or event["type"] in types):
                            feed.push("notifications/event", {"event": event})

                    cleanups.append(srv.events.listen(on_event))  # registered before the retained read: no seam
                    if ev.after is not None:
                        replay = srv.events.retained_after(start, upto=srv.events.head(),
                                                           device_ids=list(device_ids) if device_ids else None,
                                                           types=list(types) if types else None)
                    honoured["events"] = to_wire(ev)
        except BaseException:
            for cleanup in cleanups:
                cleanup()
            raise
        ack: dict[str, Any] = {"notifications": honoured}
        if refused:
            ack["refused"] = refused
        if flt.events is not None and principal.can_read:
            ack["eventsGap"] = events_gap
        return self._stream(principal, ctx, feed, ack, replay, cleanups)

    def _observation_problem(self, principal: Principal, item: Any, index: int) -> dict[str, Any] | None:
        srv = self.server
        if index >= MAX_OBSERVATIONS:
            return {"bhmsCode": "OUT_OF_RANGE", "hint": f"subscribe to at most {MAX_OBSERVATIONS} properties per "
                                                        "subscription"}
        dev = srv.devices.get(item.device_id)
        if dev is None or not principal.can_read:
            return {"bhmsCode": "UNKNOWN_DEVICE", "hint": "devices/list shows the devices you can use"}
        spec = dev.properties.get(item.property)
        if spec is None:
            return {"bhmsCode": "INVALID_ARGUMENT",
                    "hint": f"properties of {dev.device_id}: {', '.join(sorted(dev.properties)) or 'none'}"}
        if not spec.observable:
            return {"bhmsCode": "UNSUPPORTED", "hint": f"{dev.device_id}.{item.property} is not observable; poll it "
                                                       "with properties/read (BHMS-OBS-020)"}
        return None

    def _watch_operations(self, principal: Principal, ops: Any, feed: _Feed) -> Callable[[], None]:
        ids = set(ops.operation_ids or ())
        devices = set(ops.device_ids or ())
        everything = bool(ops.all)

        def on_change(rec: OperationRecord, wire: dict[str, Any]) -> None:
            if rec.principal != principal.id and not principal.operations_all:
                return
            if everything or rec.id in ids or wire.get("deviceId") in devices or \
                    (rec.op.get("parentOperationId") in ids):
                feed.push("notifications/operation", {"operation": wire})

        listeners = self.server.journal.listeners
        listeners.append(on_change)
        return lambda: listeners.remove(on_change) if on_change in listeners else None

    async def _stream(self, principal: Principal, ctx: RequestContext, feed: _Feed, ack: dict[str, Any],
                      replay: list[tuple[int, dict[str, Any]]], cleanups: list[Callable[[], None]]
                      ) -> AsyncIterator[Notification | Complete]:
        srv = self.server
        self._feeds.add(feed)
        self._active += 1
        self._idle.clear()
        policy_seen = self._policy_version
        try:
            yield Notification("notifications/subscriptions/acknowledged", ack)
            for _, event in replay:
                yield Notification("notifications/event", {"event": event})
            while True:
                while feed.items:
                    method, params = feed.items.popleft()
                    yield Notification(method, params)
                closing = srv._closing
                if closing is not None and closing.is_set():
                    yield Complete({"endReason": "shutdown"})
                    return
                if self._policy_version != policy_seen:
                    policy_seen = self._policy_version
                    current = srv.principal_of(ctx)
                    if current is None or not current.can_read:
                        yield Complete({"endReason": "unauthorized"})
                        return
                feed.wake.clear()
                await feed.wake.wait()
        finally:
            for cleanup in cleanups:
                cleanup()
            self._feeds.discard(feed)
            self._active -= 1
            if self._active == 0:
                self._idle.set()


__all__ = ["Subscriptions"]
