"""A compact bridge in front of a native C endpoint, over a fault-injecting wire (real sockets, real SQLite)."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bhms.client.client import Client
from bhms.gateway.compact_bridge import CompactBridge, Timing
from bhms.protocol.types import to_wire
from bhms.testing.compact_endpoint import NativeEndpoint, Wire
from bhms.transport import compact as cp

ROOT = Path(__file__).resolve().parents[4]
BENCH = json.loads((ROOT / "sdk/c/tests/host/bench.sidecar.json").read_text())
LED = json.loads((ROOT / "sdk/c/arduino/BHMS/examples/LedAnalog/led_analog.sidecar.json").read_text())

FAST = Timing(reply=0.25, retries=3, poll=0.3, probe=0.4, probe_misses=2, hello=0.3, stop_confirm=2.0)


@dataclass
class CompactRig:
    bridge: CompactBridge
    wire: Wire
    endpoint: NativeEndpoint
    client: Client
    tmp: Path
    device: str
    sidecar: dict[str, Any] | None = None
    timing: Timing = FAST

    async def invoke(self, action: str, arguments: dict[str, Any], *, key: str | None = None, wait_ms: int = 3000,
                     lease: dict[str, Any] | None = None) -> dict[str, Any]:
        kw: dict[str, Any] = {}
        if lease is not None:
            kw["lease_id"] = lease["leaseId"]
        result = await self.client.actions_invoke(self.device, action, arguments, wait_ms=wait_ms,
                                                  operation_key=key, **kw)
        return to_wire(result)["operation"]

    async def lease(self, resource: str, ttl_ms: int = 30_000) -> dict[str, Any]:
        reply = await self.client.leases_acquire([resource], ttl_ms)
        return to_wire(reply)["lease"]

    async def operation(self, op_id: str) -> dict[str, Any]:
        got = await self.client.operations_get(op_id)
        return to_wire(got)["operation"]

    async def restart_bridge(self, *, wait: bool = True) -> None:
        """Stop the gateway side (its journal and the endpoint stay) and start it again on the same state directory,
        which is what a gateway restart does to its bridge (BHMS-CMP-034)."""
        await self.client.close()
        await self.bridge.close()
        self.bridge = CompactBridge("rig", self.wire.url, self.sidecar, state_dir=self.tmp / "bridge", timing=self.timing)
        await self.bridge.start()
        self.client = await Client.from_transport(await self.bridge.connector(),
                                                  client_info={"name": "bhms-gateway", "version": "t"})
        if wait:
            await wait_served(self.bridge)

    async def wait_for(self, predicate: Callable[[], Any], timeout: float = 5.0, what: str = "condition") -> Any:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = predicate()
            if asyncio.iscoroutine(found):
                found = await found
            if found:
                return found
            await asyncio.sleep(0.02)
        raise AssertionError(f"timed out waiting for {what}")


async def wait_served(bridge: CompactBridge, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if bridge.ready and bridge.device is not None:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("the bridge never served the device (no matching HELLO)")


@asynccontextmanager
async def compact_rig(tmp: Path, binaries: dict[str, Path], *, binary: str = "sim_bench", sidecar: dict[str, Any] | None = None,
                      epoch: bool = True, timing: Timing = FAST, args: tuple[str, ...] = (), served: bool = True,
                      bridge_kw: dict[str, Any] | None = None) -> AsyncIterator[CompactRig]:
    tmp.mkdir(parents=True, exist_ok=True)
    sidecar = sidecar if sidecar is not None else (BENCH if binary == "sim_bench" else LED)
    endpoint = NativeEndpoint(binaries[binary], tmp, *args, epoch=epoch)
    wire = Wire(endpoint, str(tmp / "wire.sock"))
    await wire.start()
    bridge = CompactBridge("rig", wire.url, sidecar, state_dir=tmp / "bridge", timing=timing, **(bridge_kw or {}))
    await bridge.start()
    client = await Client.from_transport(await bridge.connector(), client_info={"name": "bhms-gateway", "version": "t"})
    rig = CompactRig(bridge, wire, endpoint, client, tmp, sidecar["deviceId"], sidecar, timing)
    try:
        if served:
            await wait_served(bridge)
        yield rig
    finally:
        await rig.client.close()
        await rig.bridge.close()
        await wire.close()


@dataclass
class GatewayRig:
    gateway: Any
    client: Client
    wire: Wire
    endpoint: NativeEndpoint
    tmp: Path
    config_path: Path

    @property
    def bridge(self) -> CompactBridge:
        return self.gateway.upstreams["rig"].cfg.connector.bridge

    async def invoke(self, device: str, action: str, arguments: dict[str, Any], **kw: Any) -> dict[str, Any]:
        kw.setdefault("wait_ms", 3000)
        return to_wire(await self.client.actions_invoke(device, action, arguments, **kw))["operation"]

    async def operation(self, op_id: str) -> dict[str, Any]:
        return to_wire(await self.client.operations_get(op_id))["operation"]

    async def wait_listed(self, timeout: float = 8.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if [d async for d in self.client.iter_devices()]:
                return
            await asyncio.sleep(0.05)
        raise AssertionError("the gateway never listed the compact device")


@asynccontextmanager
async def compact_gateway(tmp: Path, binaries: dict[str, Path], *, binary: str = "sim_bench", sidecar: dict[str, Any] | None = None,
                          epoch: bool = True, args: tuple[str, ...] = (), extra: str = "", served: bool = True
                          ) -> AsyncIterator[GatewayRig]:
    """A real gateway configured from TOML with one ``type = "compact"`` upstream ("rig") on a Wire to a native endpoint."""
    from bhms.gateway import Gateway, load_config

    tmp.mkdir(parents=True, exist_ok=True)
    sidecar = sidecar if sidecar is not None else (BENCH if binary == "sim_bench" else LED)
    sidecar_path = tmp / "device.sidecar.json"
    sidecar_path.write_text(json.dumps(sidecar))
    endpoint = NativeEndpoint(binaries[binary], tmp, *args, epoch=epoch)
    wire = Wire(endpoint, str(tmp / "wire.sock"))
    await wire.start()
    config_path = tmp / "gateway.toml"
    config_path.write_text(f"""[gateway]
id = "compact-test"
state_dir = "state"
connect_wait_ms = 8000

[[upstream]]
name = "rig"
type = "compact"
port = "{wire.url}"
sidecar = "device.sidecar.json"
reply_timeout_ms = 250
retries = 3
poll_interval_ms = 300
probe_interval_ms = 400
probe_misses = 2
hello_timeout_ms = 300
health_interval_ms = 500
health_timeout_ms = 1000
{extra}
""")
    gateway = Gateway(load_config(config_path))
    await gateway.start()
    await gateway.listen(f"unix:{tmp}/gw.sock")
    client = await Client.connect(f"unix:{tmp}/gw.sock")
    rig = GatewayRig(gateway, client, wire, endpoint, tmp, config_path)
    try:
        if served:  # the board says HELLO after the gateway started: the device appears through devicesListChanged
            await rig.wait_listed()
        yield rig
    finally:
        await client.close()
        await gateway.close()
        await wire.close()


def effects(rig: CompactRig, prefix: str) -> list[str]:
    return [line for line in rig.endpoint.effects() if line.startswith(prefix)]


__all__ = ["BENCH", "FAST", "LED", "CompactRig", "GatewayRig", "compact_gateway", "compact_rig", "effects", "wait_served", "cp"]
