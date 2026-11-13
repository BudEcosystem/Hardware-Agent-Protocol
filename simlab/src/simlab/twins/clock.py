"""Bench clock twin: the one way an agent can let time pass (incubate, wait between images, hold).

Agents need a timer; a stepped SimLab world advances only while a device works, so the clock is a device with a ``wait``
action that elapses world time (paced or instant per the world's mode) and a ``now`` reading of the world clock. Waiting has no
physical effect on anything; the other devices simply keep running through it (a heater keeps holding its band), which is what
UC6 incubation and UC7 scheduled imaging need.

Thread-safety: one event loop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bhms.server.decorators import Range
from bhms.server.server import DeviceServer
from simlab.simdevice import TwinHost, make_server, simulated_device
from simlab.world import World


def build_server(world: World, *, state_dir: str | Path | None, durability: str = "process", name: str = "simlab-clock",
                 device_id: str = "clock-1", **kw: Any) -> tuple[DeviceServer, None]:
    """The clock as a BHMS device server."""
    srv = make_server(world, name, state_dir=state_dir, durability=durability, title="SimLab bench clock", **kw)
    dev = simulated_device(srv, device_id, name="Bench clock", capabilities=["bhms.timer"],
                           resources=[f"{device_id}/timer"], tags=["simlab", "timer"],
                           description="Bench timer: wait for a number of seconds; now is the bench clock in seconds.",
                           identity={"manufacturer": "SimLab", "model": "clock twin", "firmwareVersion": "1"})
    host = TwinHost(world, dev)

    @dev.property(unit="s", evidence="reported")
    def now() -> float:
        """The bench clock (seconds since the experiment started)."""
        return round(world.time_s, 3)

    @dev.action(effect="none", idempotency="relative", completion_evidence="reported", cancel="supported",
                max_duration_ms=3_600_000, typical_duration_ms=60_000)
    async def wait(ctx, seconds: Range(1, 3600, unit="s")) -> {"waited_s": "s", "now_s": "s"}:  # noqa: F821
        """Wait ``seconds`` of bench time; the other devices keep running meanwhile."""
        host.begin(ctx)
        start = world.time_s
        cancelled = await host.elapse(ctx, float(seconds), chunk_s=1.0)
        if cancelled:
            raise host.canceled(ctx, "waiting stopped")
        return host.log.end(ctx.operation_id, {"waited_s": round(world.time_s - start, 3), "now_s": round(world.time_s, 3)})

    @dev.on_stop(evidence="reported", max_duration_ms=100)
    async def halt(ctx: Any) -> None:
        return None

    return srv, None
