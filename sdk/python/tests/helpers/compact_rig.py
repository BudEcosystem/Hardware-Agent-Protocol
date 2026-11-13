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
    rig = CompactRig(bridge, wire, endpoint, client, tmp, sidecar["deviceId"])
    try:
        if served:
            await wait_served(bridge)
        yield rig
    finally:
        await client.close()
        await bridge.close()
        await wire.close()


def effects(rig: CompactRig, prefix: str) -> list[str]:
    return [line for line in rig.endpoint.effects() if line.startswith(prefix)]


__all__ = ["BENCH", "FAST", "LED", "CompactRig", "compact_rig", "effects", "wait_served", "cp"]
