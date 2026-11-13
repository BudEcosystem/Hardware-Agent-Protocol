"""Actuator Node twin: a motor that turns one of the manual microscope's knobs (validation plan UC3 and UC10).

The node drives the knob joint through a coupler. The node knows what it commanded, not what the axis did: backlash takes up
the first part of a reversal and a slipping coupler loses rotation, and neither is visible to the node, so ``turn`` completes
with ``reported`` evidence (effect unverified) and its result is the commanded rotation only. The agent has to read the
microscope's focus or stage encoder (a modelled, measured sensor on the axis) to learn what the turn did; that is the
honest-evidence loop UC3 exercises.

Effects: ``actuator_turn`` (an execution start with the joint and the commanded angle) and, through ``World.turn_joint``, the
``joint_turned`` observation that carries the same cause.

Thread-safety: one event loop (the world's).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from bhms.server.decorators import OneOf, Range
from bhms.server.server import DeviceServer
from simlab.simdevice import TwinHost, make_server, simulated_device
from simlab.world import World

KNOBS = ("focus_coarse", "focus_fine", "stage_x_knob", "stage_y_knob")
MAX_REV = 20.0
TURN_S_PER_REV = 0.5


def build_server(world: World, *, state_dir: str | Path | None, durability: str = "process", name: str = "simlab-knob-actuator",
                 device_id: str = "knob-1", **kw: Any) -> tuple[DeviceServer, None]:
    """The Actuator Node as a BHMS device server (one resource per knob)."""
    srv = make_server(world, name, state_dir=state_dir, durability=durability, title="SimLab Actuator Node (knob turner)",
                      **kw)
    dev = simulated_device(srv, device_id, name="Knob actuator", capabilities=["bhms.actuator.rotary"],
                           resources=[f"{device_id}/{knob}" for knob in KNOBS], tags=["simlab", "actuator"],
                           description="Turns one manual microscope knob by a commanded number of revolutions. It cannot "
                                       "sense the axis: read the microscope's encoder to see what the turn did.",
                           identity={"manufacturer": "SimLab", "model": "actuator node twin", "firmwareVersion": "1"})
    host = TwinHost(world, dev)
    done: dict[str, float] = {k: 0.0 for k in KNOBS}

    @dev.property(unit="1", evidence="reported")
    def commanded_revolutions_focus_fine() -> float:
        """Net revolutions commanded on the fine focus knob since start (the node's own count, not the axis)."""
        return done["focus_fine"]

    @dev.action(effect="reversible", idempotency="relative", completion_evidence="reported", cancel="unsupported",
                max_duration_ms=60_000, typical_duration_ms=2000, resources=[f"{device_id}/{k}" for k in KNOBS])
    async def turn(ctx, knob: OneOf(*KNOBS), revolutions: Range(-MAX_REV, MAX_REV, unit="1")) -> {"commanded": "1"}:  # noqa: F821
        """Turn ``knob`` by ``revolutions`` (positive is clockwise). The result is what was commanded; it is not evidence of
        how far the axis moved."""
        host.begin(ctx)
        angle = float(revolutions) * math.tau
        world.record(device_id, "actuator_turn", {"joint": knob, "revolutions": float(revolutions), "angle_rad": angle},
                     ctx.operation_id)
        if await host.elapse(ctx, abs(float(revolutions)) * TURN_S_PER_REV, chunk_s=0.5):
            return host.log.end(ctx.operation_id, {"commanded": 0.0})
        world.turn_joint(knob, angle, ctx.operation_id)
        done[knob] += float(revolutions)
        return host.log.end(ctx.operation_id, {"commanded": float(revolutions)})

    @dev.on_stop(evidence="reported", max_duration_ms=100)
    async def halt(ctx: Any) -> None:
        return None

    return srv, None
