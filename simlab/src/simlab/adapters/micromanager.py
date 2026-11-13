"""Micro-Manager adapter: any ``pymmcore-plus`` core (real hardware or Python devices) as a BHMS microscope.

The adapter speaks only the standard Micro-Manager core API (``setPosition``, ``getPosition``, ``setXYPosition``,
``getXYPosition``, ``setExposure``, ``snapImage``, ``getImage``), so the same code bridges any microscope Micro-Manager
supports. Honesty follows from that API: positions are what the device adapter *reports* (``reported``, not a measurement),
a move completes ``reported`` after a read-back (the effect stays unverified), and ``snap`` returns image statistics and a
stored frame, not a claim about focus.

The core API is synchronous. For real hardware set ``threaded=True`` so a blocking driver call does not stall the event loop;
for a core whose devices step the SimLab world (``simlab.mmbackend``) leave it ``False``: the world is not thread-safe.

Failure semantics: a core call that raises after being issued may have moved something, so the operation ends ``unknown``;
the reconcile hook resolves it by reading the position back (within tolerance of the target: completed, unverified).

Thread-safety: one event loop; the core is used from the loop thread unless ``threaded``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from bhms.server.context import DeviceFault, Reconciled
from bhms.server.decorators import Range
from bhms.server.server import DeviceServer
from simlab.adapters.common import declare_action, declare_property
from simlab.imaging import sharpness
from simlab.simdevice import CommandLog, make_server, simulated_device
from simlab.world import World

TOLERANCE_UM = 0.5
Z_LIMITS_UM = (0.0, 200.0)
XY_LIMITS_UM = (0.0, 2047.0)


def build_server(world: World, core: Any, *, device_id: str = "microscope-mm", state_dir: str | Path | None,
                 frames_dir: Path | None = None, durability: str = "process", name: str = "simlab-micromanager-adapter",
                 threaded: bool = False, **kw: Any) -> DeviceServer:
    """The BHMS server for a Micro-Manager core. ``world`` supplies the SimLab server plumbing only; the adapter never
    reads the world, it knows what the core API tells it."""
    srv = make_server(world, name, state_dir=state_dir, durability=durability, title="Micro-Manager adapter", **kw)
    dev = simulated_device(srv, device_id, name="Micro-Manager microscope", capabilities=["bhms.microscope", "bhms.camera"],
                     resources=[f"{device_id}/focus", f"{device_id}/stage", f"{device_id}/camera"],
                     tags=["simlab", "adapter", "micro-manager"],
                     description="A microscope reached through the Micro-Manager core API: focus, XY stage, camera.",
                     identity={"manufacturer": "Micro-Manager", "model": "core API", "firmwareVersion": "unknown"})
    log = CommandLog()
    counter = {"frames": 0}
    if frames_dir is not None:
        frames_dir.mkdir(parents=True, exist_ok=True)

    async def call(fn: Callable[[], Any]) -> Any:
        return await asyncio.to_thread(fn) if threaded else fn()

    async def z_position() -> float:
        return float(await call(core.getPosition))

    async def xy_position() -> dict[str, float]:
        x, y = await call(core.getXYPosition)
        return {"x": float(x), "y": float(y)}

    async def exposure() -> float:
        return float(await call(core.getExposure))

    declare_property(dev, "z_position", z_position, Range(*Z_LIMITS_UM, unit="um"), evidence="reported",
                     description="focus position as reported by the stage adapter (Micro-Manager getPosition)")
    declare_property(dev, "xy_position", xy_position, {"type": "object", "additionalProperties": False,
                                                       "required": ["x", "y"],
                                                       "properties": {"x": {"type": "number", "x-bhms-unit": "um"},
                                                                      "y": {"type": "number", "x-bhms-unit": "um"}}},
                     evidence="reported", description="XY stage position as reported (Micro-Manager getXYPosition)")
    declare_property(dev, "exposure", exposure, Range(0.0, 10_000.0, unit="ms"), evidence="reported",
                     description="camera exposure setting (Micro-Manager getExposure)")

    async def set_z(ctx: Any, z: float) -> Any:
        log.begin(ctx.operation_id)
        await call(lambda: core.setPosition(float(z)))
        back = await z_position()
        if abs(back - z) > TOLERANCE_UM:
            raise DeviceFault(f"the stage reports {back:.2f} um after a move to {z} um", partial="moved, short of target",
                              hint="read z_position before retrying")
        return log.end(ctx.operation_id, {"z_um": round(back, 4)})

    async def move_stage(ctx: Any, x: float, y: float) -> Any:
        log.begin(ctx.operation_id)
        await call(lambda: core.setXYPosition(float(x), float(y)))
        got = await xy_position()
        if abs(got["x"] - x) > TOLERANCE_UM or abs(got["y"] - y) > TOLERANCE_UM:
            raise DeviceFault(f"the stage reports ({got['x']:.2f}, {got['y']:.2f}) after a move to ({x}, {y})",
                              partial="moved, short of target", hint="read xy_position before retrying")
        return log.end(ctx.operation_id, {"x_um": round(got["x"], 4), "y_um": round(got["y"], 4)})

    async def set_exposure(ctx: Any, exposure_ms: float) -> Any:
        log.begin(ctx.operation_id)
        await call(lambda: core.setExposure(float(exposure_ms)))
        return log.end(ctx.operation_id, {"exposure_ms": await exposure()})

    async def snap(ctx: Any) -> Any:
        log.begin(ctx.operation_id)

        def grab() -> np.ndarray:
            core.snapImage()
            return np.asarray(core.getImage())

        image = await call(grab)
        counter["frames"] += 1
        frame_id = f"{device_id}-{counter['frames']:05d}"
        if frames_dir is not None:
            np.save(frames_dir / f"{frame_id}.npy", image)
        return log.end(ctx.operation_id, {"frame_id": frame_id, "mean_counts": round(float(image.mean()), 3),
                                          "focus_score": round(sharpness(image), 3)})

    declare_action(dev, "set_z", set_z, description="Move the focus stage to an absolute position (um).",
                   params={"z": Range(*Z_LIMITS_UM, unit="um")}, returns={"z_um": "um"}, effect="reversible",
                   idempotency="absolute", completion_evidence="reported", max_duration_ms=30_000,
                   resources=[f"{device_id}/focus"])
    declare_action(dev, "move_stage", move_stage, description="Move the XY stage to an absolute position (um).",
                   params={"x": Range(*XY_LIMITS_UM, unit="um"), "y": Range(*XY_LIMITS_UM, unit="um")},
                   returns={"x_um": "um", "y_um": "um"}, effect="reversible", idempotency="absolute",
                   completion_evidence="reported", max_duration_ms=30_000, resources=[f"{device_id}/stage"])
    declare_action(dev, "set_exposure", set_exposure, description="Set the camera exposure (ms).",
                   params={"exposure_ms": Range(0.1, 10_000.0, unit="ms")}, returns={"exposure_ms": "ms"},
                   effect="reversible", idempotency="absolute", completion_evidence="reported", max_duration_ms=5000,
                   resources=[f"{device_id}/camera"])
    declare_action(dev, "snap", snap, description="Snap one image and store it; returns statistics, not a focus claim.",
                   returns={"frame_id": str, "mean_counts": "1", "focus_score": "1"}, effect="none",
                   idempotency="relative", completion_evidence="reported", max_duration_ms=30_000)

    @dev.reconcile
    async def reconcile(op: dict[str, Any]) -> Reconciled | None:
        arguments = op.get("arguments", {})
        try:
            if op.get("action") == "set_z":
                back = await z_position()
                if abs(back - arguments["z"]) <= TOLERANCE_UM:
                    return Reconciled("completed", evidence=f"read back z_position = {back:.3f}",
                                      result={"z_um": round(back, 4)}, effect="unverified")
            elif op.get("action") == "move_stage":
                got = await xy_position()
                if abs(got["x"] - arguments["x"]) <= TOLERANCE_UM and abs(got["y"] - arguments["y"]) <= TOLERANCE_UM:
                    return Reconciled("completed", evidence=f"read back xy_position = {got}",
                                      result={"x_um": round(got["x"], 4), "y_um": round(got["y"], 4)},
                                      effect="unverified")
        except Exception:  # noqa: BLE001 - an unreadable core proves nothing
            return None
        return None

    return srv
