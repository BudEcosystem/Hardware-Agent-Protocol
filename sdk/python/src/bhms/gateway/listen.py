"""``subscriptions/listen`` at the gateway: fan-in from the upstreams (spec/bhms/03-lifecycle.md §3.7, 09-events-and-streams.md).

The gateway serves every subscription from state it owns, so a client sees one coherent stream however many upstreams
stand behind it (and :class:`~bhms.server.listen.Subscriptions` — the one implementation of acknowledgement, retained
replay, overflow and ``endReason`` handling — is reused):

* ``devicesListChanged`` — the catalog changed (an upstream appeared, vanished or re-described a device);
* ``operations`` — every state/cancel/effect change of the gateway's own operation records, in change order, mirrored
  from the upstream's notifications (BHMS-OPS-090); visibility is the principal's own operations, or all with
  ``operations:read``/``admin``;
* ``events`` — the gateway's *own* durable event log. Each upstream's ``events`` stream (opened once per upstream, with
  the last cursor the gateway saw, so a gateway restart loses nothing the upstream still retains) is re-recorded here with
  the gateway's cursor, ids rewritten to the gateway's (``deviceId``, ``operationId``, ``leaseId``); a client therefore
  resumes with one cursor and gaps are the gateway's to report (BHMS-EVT-011);
* ``observations`` — relayed: the first subscriber of a ``(device, property)`` opens a ``subscriptions/listen`` on the
  owning upstream, later ones share it, the last one closes it. Each subscriber's ``minIntervalMs`` is applied by the
  gateway (the upstream applies its own floor, BHMS-LIF-043). At most :data:`MAX_UPSTREAM_STREAMS` relays per upstream.

Cost at scale (measured in the Task 5 report): one stream per upstream carries events and operations, so 1,000 upstreams are
1,000 streams, not 1,000 per subscriber; a client subscription adds no upstream traffic except observation relays.

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from bhms.gateway.catalog import CatalogEntry
from bhms.protocol.errors import BhmsError
from bhms.server.listen import Subscriptions
from bhms.transport.base import TransportClosed

if TYPE_CHECKING:
    from bhms.gateway.gateway import Gateway
    from bhms.runtime.authority import Principal

log = logging.getLogger("bhms.gateway.listen")

MAX_UPSTREAM_STREAMS = 256


class _Subscriber:
    __slots__ = ("deliver", "floor_s", "last", "pending", "latest")

    def __init__(self, deliver: Callable[[dict[str, Any]], None], floor_s: float) -> None:
        self.deliver = deliver
        self.floor_s = floor_s
        self.last = 0.0
        self.pending: asyncio.TimerHandle | None = None
        self.latest: dict[str, Any] | None = None

    def offer(self, params: dict[str, Any]) -> None:
        """Deliver now, or keep only the newest value and deliver it when the subscriber's floor has passed."""
        now = time.monotonic()
        if now - self.last >= self.floor_s:
            self._send(params)
        else:
            self.latest = params
            if self.pending is None:
                loop = asyncio.get_running_loop()
                self.pending = loop.call_at(loop.time() + (self.last + self.floor_s - now), self._flush)

    def _flush(self) -> None:
        self.pending = None
        if self.latest is not None:
            latest, self.latest = self.latest, None
            self._send(latest)

    def _send(self, params: dict[str, Any]) -> None:
        self.last = time.monotonic()
        self.deliver(params)

    def stop(self) -> None:
        if self.pending is not None:
            self.pending.cancel()
            self.pending = None


class _Relay:
    """One upstream observation stream shared by every subscriber of a ``(device, property)``."""

    def __init__(self, gateway: Gateway, entry: CatalogEntry, prop: str) -> None:
        self.gateway = gateway
        self.entry = entry
        self.prop = prop
        self.subscribers: list[_Subscriber] = []
        self.task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self.task = asyncio.get_running_loop().create_task(self._run(), name=f"bhms-relay-{self.entry.device_id}.{self.prop}")

    async def _run(self) -> None:
        up = self.gateway.upstreams[self.entry.namespace]
        while self.subscribers:
            try:
                if not up.available:
                    await asyncio.sleep(0.25)
                    continue
                floor = min((s.floor_s for s in self.subscribers), default=0.0)
                stream = await up.open_stream({"observations": [{
                    "deviceId": self.entry.upstream_id, "property": self.prop, "minIntervalMs": int(floor * 1000)}]})
                try:
                    async for message in stream:
                        if message["method"] != "notifications/observation":
                            continue
                        params = {**message["params"], "deviceId": self.entry.device_id}
                        params.pop("_meta", None)
                        for sub in list(self.subscribers):
                            sub.offer(params)
                finally:
                    await stream.cancel()
                await asyncio.sleep(0.25)  # the upstream ended the stream: do not spin
            except asyncio.CancelledError:
                raise
            except (BhmsError, TransportClosed, asyncio.TimeoutError) as exc:
                log.debug("observation relay %s.%s: %s", self.entry.device_id, self.prop, exc)
                await asyncio.sleep(0.5)


class GatewayObservations:
    """Observation relays of a gateway (the ``observations`` of the object :class:`Subscriptions` drives)."""

    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway
        self._relays: dict[tuple[str, str], _Relay] = {}
        self._per_upstream: dict[str, int] = {}

    def streams_of(self, namespace: str) -> int:
        return self._per_upstream.get(namespace, 0)

    def subscribe(self, entry: CatalogEntry, prop: str, min_interval_ms: int | None,
                  deliver: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        """Relay ``entry.prop`` observations to ``deliver``; returns the unsubscribe function."""
        key = (entry.device_id, prop)
        floor_ms = max(min_interval_ms or 0, self.gateway.config.observation_min_interval_ms)
        sub = _Subscriber(deliver, floor_ms / 1000)
        relay = self._relays.get(key)
        if relay is None:
            relay = self._relays[key] = _Relay(self.gateway, entry, prop)
            self._per_upstream[entry.namespace] = self._per_upstream.get(entry.namespace, 0) + 1
            relay.subscribers.append(sub)
            relay.start()
        else:
            relay.subscribers.append(sub)

        def unsubscribe() -> None:
            sub.stop()
            if sub in relay.subscribers:
                relay.subscribers.remove(sub)
            if not relay.subscribers and self._relays.get(key) is relay:
                del self._relays[key]
                self._per_upstream[entry.namespace] -= 1
                if relay.task is not None:
                    relay.task.cancel()

        return unsubscribe

    async def close(self) -> None:
        tasks = [r.task for r in self._relays.values() if r.task is not None]
        for task in tasks:
            task.cancel()
        with contextlib.suppress(Exception):
            await asyncio.gather(*tasks, return_exceptions=True)
        self._relays.clear()


class GatewaySubscriptions(Subscriptions):
    """:class:`~bhms.server.listen.Subscriptions` over a gateway: the same streams, plus the relay cap."""

    def _observation_problem(self, principal: Principal, item: Any, index: int) -> dict[str, Any] | None:
        problem = super()._observation_problem(principal, item, index)
        if problem is not None:
            return problem
        gateway: Gateway = self.server  # type: ignore[assignment]
        entry = gateway.catalog.get(item.device_id)
        key = (entry.device_id, item.property)
        if key not in gateway.observations._relays and \
                gateway.observations.streams_of(entry.namespace) >= MAX_UPSTREAM_STREAMS:
            return {"bhmsCode": "OUT_OF_RANGE", "hint": f"the gateway relays at most {MAX_UPSTREAM_STREAMS} observation "
                    f"streams per upstream; {entry.namespace}/ is at the limit (gateway rule: isolation:relay-cap)"}
        return None


__all__ = ["MAX_UPSTREAM_STREAMS", "GatewayObservations", "GatewaySubscriptions"]
