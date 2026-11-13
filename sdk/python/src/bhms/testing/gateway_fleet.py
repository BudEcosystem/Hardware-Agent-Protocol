"""A fleet of in-process upstream device servers for gateway scale tests and benchmarks.

Two kinds of fleet, both served over in-memory transports (:mod:`bhms.testing.memory`):

* ``await build_light_fleet(1000, devices_per=10)`` — 1,000 *light* upstreams: protocol-correct but minimal servers
  (``server/discover``, ``devices/list``, ``devices/describe``, ``subscriptions/listen`` with events pushed on demand by
  :meth:`LightUpstream.emit`). A thousand of them with ten thousand devices start in seconds, which is what a scale
  measurement of the *gateway* needs.
* ``await build_fleet(10, devices_per=2)`` — real device servers, for measuring the gateway's overhead per invoke.

``build_fleet`` starts :class:`~bhms.server.server.DeviceServer` objects (in-memory
journals, so no files) and returns :class:`Fleet`, whose ``upstream_configs()`` are :class:`~bhms.gateway.config.UpstreamConfig`
objects whose ``connector`` serves each device server over an in-memory transport
(:mod:`bhms.testing.memory`). Server ``i`` has devices ``d0``..; each has an observable ``value`` property and a ``bump``
action. The namespace of server ``i`` is ``u<i>``, so the gateway serves device ``d<j>`` as ``u<i>/d<j>``.

Used by ``tests/test_gateway_scale.py`` and ``benchmarks/gateway_scale.py``; Task 10 (many simulated twins behind one
gateway) and Task 12 (fan-out benchmarks) build on it.

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

from bhms import DeviceServer, Range
from bhms.gateway.config import UpstreamConfig
from bhms.jsonrpc.dispatcher import Server as RpcServer
from bhms.jsonrpc.session import Notification
from bhms.protocol.canonical import digest
from bhms.runtime.authority import Policy
from bhms.testing.memory import connect_in_process


@dataclass
class Fleet:
    """The started upstream servers of a fleet (real :class:`DeviceServer` or :class:`LightUpstream` objects)."""

    servers: list[Any] = field(default_factory=list)
    devices_per: int = 0

    @property
    def device_count(self) -> int:
        return len(self.servers) * self.devices_per

    def upstream_configs(self, **kw: int) -> tuple[UpstreamConfig, ...]:
        """One :class:`UpstreamConfig` per server (namespace ``u<i>``) connecting in memory; ``kw`` overrides its
        numeric settings (``timeout_ms``, ``health_interval_ms``, ...)."""
        kw.setdefault("health_interval_ms", 60_000)  # a thousand probes every two seconds would measure the probes
        kw.setdefault("health_timeout_ms", 5_000)
        return tuple(UpstreamConfig(name=f"u{i}", connector=_connector(server), **kw)
                     for i, server in enumerate(self.servers))

    async def close(self) -> None:
        await asyncio.gather(*(s.close() for s in self.servers), return_exceptions=True)

    def __iter__(self):
        return iter(self.servers)


def _connector(server: Any):
    async def connect():
        assert server.rpc is not None
        return await connect_in_process(server.rpc)

    return connect


def gateway_uid_policy() -> Policy:
    """Upstream policy for a gateway in this process: this uid is the gateway (may use ``g-`` keys) and admin."""
    return Policy({"gateway": {"uids": [os.getuid()], "scopes": ["admin"], "gateway": True}})


def _declare(device) -> None:
    state = {"n": 0.0}

    @device.property(unit="1", evidence="simulated", max_rate_hz=100)
    def value() -> float:
        return state["n"]

    @device.action(effect="reversible", idempotency="relative", max_duration_ms=1000)
    async def bump(ctx, by: Range(0, 10, unit="1") = 1.0) -> {"n": "1"}:  # noqa: F821
        state["n"] += by
        return {"n": state["n"]}


async def build_fleet(upstreams: int, *, devices_per: int = 10) -> Fleet:
    """Start ``upstreams`` device servers with ``devices_per`` devices each."""
    fleet = Fleet(devices_per=devices_per)
    for i in range(upstreams):
        srv = DeviceServer(f"fleet-{i}", store=None, programs=False, policy=gateway_uid_policy())
        for j in range(devices_per):
            device = srv.device(f"d{j}", name=f"Device {j} of {i}", description="A simulated fleet device.",
                                capabilities=["bhms.fleet.sim"], tags=["fleet"], resources=[f"d{j}"])
            device.report_alive()
            _declare(device)
        await srv.start()
        fleet.servers.append(srv)
    return fleet


class LightUpstream:
    """A minimal protocol-correct upstream: ``devices/list`` and ``devices/describe`` over ``devices_per`` devices
    ``d0``.., and ``subscriptions/listen`` delivering whatever :meth:`emit` pushes as ``notifications/event``."""

    def __init__(self, index: int, devices_per: int, template: dict[str, Any]) -> None:
        self.index = index
        self.descriptions: dict[str, dict[str, Any]] = {}
        for j in range(devices_per):
            body = {k: v for k, v in template.items() if k != "digest"}
            body.update(deviceId=f"d{j}", name=f"Device {j} of {index}", resources=[f"d{j}"])
            body["digest"] = digest(body)
            self.descriptions[f"d{j}"] = body
        self.subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self.sequence = 0
        self.rpc = RpcServer(server_info={"name": f"light-{index}", "version": "0.1.0"}, epoch=f"light-{index}",
                             capabilities={"devices": {"listChanged": True},
                                           "events": {"retentionS": 86_400, "maxPageSize": 500}},
                             max_page_size=500)
        self.rpc.register("devices/list", self._list)
        self.rpc.register("devices/describe", self._describe)
        self.rpc.register("subscriptions/listen", self._listen)

    async def _list(self, params: Any, ctx: Any) -> dict[str, Any]:
        ids = sorted(self.descriptions)
        start = int(params.cursor) if params.cursor else 0
        limit = params.limit or 100
        page = ids[start:start + limit]
        out: dict[str, Any] = {"devices": [_summary(self.descriptions[i]) for i in page]}
        if start + limit < len(ids):
            out["nextCursor"] = str(start + limit)
        return out

    async def _describe(self, params: Any, ctx: Any) -> dict[str, Any]:
        return {"description": self.descriptions[params.device_id]}

    async def _listen(self, params: Any, ctx: Any) -> Any:
        return self._stream()

    async def _stream(self):
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.subscribers.append(queue)
        try:
            yield Notification("notifications/subscriptions/acknowledged", {"notifications": {}})
            while True:
                yield Notification("notifications/event", {"event": await queue.get()})
        finally:
            self.subscribers.remove(queue)

    def emit(self, type: str = "device.fault", device: str = "d0", message: str = "fault") -> None:
        """Push one event to every subscriber (the gateway has exactly one stream per upstream)."""
        self.sequence += 1
        event = {"cursor": f"light-{self.index}-{self.sequence}", "time": "2026-11-13T00:00:00.000000Z", "type": type,
                 "severity": "info", "deviceId": device, "message": message}
        for queue in self.subscribers:
            queue.put_nowait(event)

    async def close(self) -> None:
        await self.rpc.close()


def _summary(description: dict[str, Any]) -> dict[str, Any]:
    return {"deviceId": description["deviceId"], "name": description["name"], "summary": description["description"][:280],
            "capabilities": list(description["capabilities"]), "tags": list(description["tags"]), "status": "online",
            "digest": description["digest"], "actions": sorted(description["actions"]),
            "properties": sorted(description["properties"])}


async def build_light_fleet(upstreams: int, *, devices_per: int = 10) -> Fleet:
    """``upstreams`` :class:`LightUpstream` objects with ``devices_per`` devices each."""
    reference = DeviceServer("light-template", store=None, programs=False)
    device = reference.device("d0", name="Device", description="A simulated fleet device.",
                              capabilities=["bhms.fleet.sim"], tags=["fleet"], resources=["d0"])
    device.report_alive()
    _declare(device)
    template = device.description()
    fleet = Fleet(devices_per=devices_per)
    fleet.servers = [LightUpstream(i, devices_per, template) for i in range(upstreams)]
    return fleet


__all__ = ["Fleet", "LightUpstream", "build_fleet", "build_light_fleet"]
