"""Microscope twin: a motorized face and a manual-knob face over one optical model.

Motorized face (what a Micro-Manager style controller drives): ``set_z`` / ``set_xy`` / ``set_objective`` move at finite
speed on world time, ``snap`` renders a frame. Manual face: the four knob joints in the scene (``focus_coarse``,
``focus_fine``, ``stage_x_knob``, ``stage_y_knob``) drive the same axes through the backlash and slip mechanism of
``World`` (``focus_um_per_rev`` and friends): a human or a retrofit actuator turning a knob changes ``true_z_um`` exactly
as a motor would, plus the lost motion of the gear train.

The image is computed from the world: the slide currently on ``microscope_stage`` in the ledger supplies the specimen
(its focal plane is the slide's ``specimen_z_um``); with nothing on the stage the frame is an empty field. Frames are
saved to a frame store and every capture is an effect (``image_captured``) with the true axis positions, which is how
the oracle can tell a frame taken in focus from one that was not.

Thread-safety: belongs to its world's thread.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from bhms.server.context import DeviceFault
from bhms.server.decorators import Range
from bhms.server.server import DeviceServer
from simlab import imaging
from simlab.simdevice import PowerLost, TwinHost, make_server
from simlab.world import World

STAGE_SITE = "microscope_stage"
Z_RANGE_UM = (0.0, 200.0)
XY_RANGE_UM = (0.0, float(imaging.SPECIMEN_PX - 1))
Z_SPEED_UM_S = 200.0
XY_SPEED_UM_S = 2000.0
OBJECTIVE_SWAP_S = 1.0
DEFAULT_EXPOSURE_MS = 20.0
CAMERA = "scope"


class CameraUnavailable(RuntimeError):
    """The camera is disconnected (fault ``sensor_disconnect``): no frame can be produced."""


@dataclass(frozen=True)
class Ramp:
    """A linear move of one axis from ``start`` to ``end`` between two world times."""

    t0: float
    t1: float
    start: float
    end: float

    def at(self, now_s: float) -> float:
        if now_s >= self.t1 or self.t1 <= self.t0:
            return self.end
        return self.start + (self.end - self.start) * max(0.0, now_s - self.t0) / (self.t1 - self.t0)


@dataclass(frozen=True)
class Frame:
    """A captured frame: ``pixels`` plus what was true when it was captured."""

    frame_id: str
    pixels: np.ndarray
    z_um: float
    x_um: float
    y_um: float
    objective: int
    exposure_ms: float
    specimen_present: bool
    stale: bool
    sharpness: float
    captured_s: float


class FrameStore:
    """Frames kept in memory and, when a directory is given, saved as ``<frame_id>.npy`` (the images 'recorded')."""

    def __init__(self, directory: Path | None = None, keep: int = 64) -> None:
        self.directory, self.keep = directory, keep
        self._frames: dict[str, Frame] = {}
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)

    def save(self, frame: Frame) -> None:
        self._frames[frame.frame_id] = frame
        while len(self._frames) > self.keep:
            self._frames.pop(next(iter(self._frames)))
        if self.directory is not None:
            np.save(self.directory / f"{frame.frame_id}.npy", frame.pixels)

    def get(self, frame_id: str) -> Frame:
        return self._frames[frame_id]

    def ids(self) -> list[str]:
        return list(self._frames)


class MicroscopeTwin:
    """The microscope in a world; see the module docstring."""

    def __init__(self, world: World, *, device: str = "microscope", frames: FrameStore | None = None) -> None:
        self.world, self.device = world, device
        self.frames = frames or FrameStore()
        self._z = Ramp(0.0, 0.0, 20.0, 20.0)
        self._x = Ramp(0.0, 0.0, 1024.0, 1024.0)
        self._y = Ramp(0.0, 0.0, 1024.0, 1024.0)
        self._objective = 1  # index into imaging.OBJECTIVES (10x)
        self._objective_ready_s = 0.0
        self._specimens: dict[int, np.ndarray] = {}
        self._last_frame: Frame | None = None
        self._count = 0

    # ------------------------------------------------------------------ the manual face

    def _knob_axis(self, name: str) -> float:
        """A knob's output angle relative to its engaged-flank start (so a fresh scope reads zero knob offset)."""
        return self.world.knob_output(name) + self.world.params.backlash_rad / 2

    def _knob_z_um(self) -> float:
        p = self.world.params
        return (self._knob_axis("focus_coarse") * p.focus_coarse_um_per_rev
                + self._knob_axis("focus_fine") * p.focus_um_per_rev) / math.tau

    def _knob_xy_um(self) -> tuple[float, float]:
        per_rev = self.world.params.stage_um_per_rev
        return (self._knob_axis("stage_x_knob") * per_rev / math.tau, self._knob_axis("stage_y_knob") * per_rev / math.tau)

    # ------------------------------------------------------------------ truth

    def true_z_um(self) -> float:
        """Where the focus axis really is: motor position plus whatever the knobs have contributed."""
        return self._z.at(self.world.time_s) + self._knob_z_um()

    def true_xy_um(self) -> tuple[float, float]:
        kx, ky = self._knob_xy_um()
        return self._x.at(self.world.time_s) + kx, self._y.at(self.world.time_s) + ky

    def motor_z_um(self) -> float:
        """The motor's own z (what a motor encoder reports; blind to knob turns)."""
        return self._z.at(self.world.time_s)

    @property
    def objective_index(self) -> int:
        return self._objective

    @property
    def magnification(self) -> int:
        return imaging.OBJECTIVES[self._objective]

    def slide_on_stage(self) -> str | None:
        ledger = self.world.ledger
        slides = [c for c in ledger.containers_at(STAGE_SITE) if ledger.kind(c) == "slide"]
        return slides[0] if slides else None

    def specimen_z_um(self) -> float | None:
        slide = self.slide_on_stage()
        return None if slide is None else float(self.world.ledger.meta(slide).get("specimen_z_um", 40.0))

    # ------------------------------------------------------------------ the motorized face

    def begin_z(self, um: float, cause: str | None = None) -> float:
        """Start a z move; returns its duration in world seconds. ``set_z`` is the synchronous form."""
        lo, hi = Z_RANGE_UM
        if not lo <= um <= hi:
            raise ValueError(f"z {um} um is outside {lo}..{hi} um")
        now = self.world.time_s
        start = self._z.at(now)
        end = um - self._knob_z_um()  # the drive servos the focus axis (encoder after the knobs) to ``um``
        duration = abs(end - start) / Z_SPEED_UM_S
        self._z = Ramp(now, now + duration, start, end)
        self.world.record(self.device, "z_move", {"from_um": round(start, 6), "to_um": um}, cause)
        return duration

    def begin_xy(self, x_um: float, y_um: float, cause: str | None = None) -> float:
        lo, hi = XY_RANGE_UM
        if not (lo <= x_um <= hi and lo <= y_um <= hi):
            raise ValueError(f"stage position ({x_um}, {y_um}) um is outside {lo}..{hi} um")
        now = self.world.time_s
        sx, sy = self._x.at(now), self._y.at(now)
        duration = max(abs(x_um - sx), abs(y_um - sy)) / XY_SPEED_UM_S
        self._x, self._y = Ramp(now, now + duration, sx, x_um), Ramp(now, now + duration, sy, y_um)
        self.world.record(self.device, "xy_move", {"to_um": [x_um, y_um]}, cause)
        return duration

    def begin_objective(self, index: int, cause: str | None = None) -> float:
        if not 0 <= index < len(imaging.OBJECTIVES):
            raise ValueError(f"objective index {index} outside 0..{len(imaging.OBJECTIVES) - 1}")
        duration = 0.0 if index == self._objective else OBJECTIVE_SWAP_S
        self._objective = index
        self._objective_ready_s = self.world.time_s + duration
        self.world.record(self.device, "objective_changed", {"index": index,
                                                             "magnification": imaging.OBJECTIVES[index]}, cause)
        return duration

    def freeze(self) -> None:
        """Stop every axis where it is now (the stop procedure)."""
        now = self.world.time_s
        z, x, y = self._z.at(now), self._x.at(now), self._y.at(now)
        self._z, self._x, self._y = Ramp(now, now, z, z), Ramp(now, now, x, x), Ramp(now, now, y, y)

    def set_z(self, um: float, cause: str | None = None) -> None:
        self.world.step(self.begin_z(um, cause))

    def set_xy(self, x_um: float, y_um: float, cause: str | None = None) -> None:
        self.world.step(self.begin_xy(x_um, y_um, cause))

    def set_objective(self, index: int, cause: str | None = None) -> None:
        self.world.step(self.begin_objective(index, cause))

    def _specimen(self, slide: str) -> np.ndarray:
        seed = int(self.world.ledger.meta(slide).get("specimen_seed", self.world.seed))
        if seed not in self._specimens:
            self._specimens[seed] = imaging.make_specimen(np.random.default_rng([seed, 0x5ec]))
        return self._specimens[seed]

    def capture(self, exposure_ms: float = DEFAULT_EXPOSURE_MS, cause: str | None = None) -> Frame:
        """Take a frame now. A ``stale_camera`` fault returns the previous frame again (recorded as stale); a
        ``sensor_disconnect`` fault raises ``CameraUnavailable``."""
        faults = self.world.faults
        if faults.active(CAMERA, "sensor_disconnect"):
            raise CameraUnavailable("the camera is disconnected")
        if self.world.time_s < self._objective_ready_s:
            raise CameraUnavailable("the objective turret is still moving")
        self._count += 1
        frame_id = f"{self.device}-{self._count:05d}"
        z, (x, y), slide = self.true_z_um(), self.true_xy_um(), self.slide_on_stage()
        if faults.active(CAMERA, "stale_camera") and self._last_frame is not None:
            last = self._last_frame
            frame = Frame(frame_id, last.pixels, last.z_um, last.x_um, last.y_um, last.objective, last.exposure_ms,
                          last.specimen_present, True, last.sharpness, last.captured_s)
        else:
            specimen = self._specimen(slide) if slide else None
            plane = self.specimen_z_um()
            pixels = imaging.render_frame(specimen, x_um=x, y_um=y, dz_um=0.0 if plane is None else z - plane,
                                          magnification=self.magnification, exposure_ms=exposure_ms,
                                          rng=self.world.rng_for(CAMERA))
            frame = Frame(frame_id, pixels, z, x, y, self.magnification, exposure_ms, slide is not None, False,
                          imaging.sharpness(pixels), self.world.time_s)
            self._last_frame = frame
        self.frames.save(frame)
        self.world.record(self.device, "image_captured", {
            "frame_id": frame_id, "z_um": round(frame.z_um, 6), "xy_um": [round(frame.x_um, 3), round(frame.y_um, 3)],
            "objective": frame.objective, "exposure_ms": exposure_ms, "specimen_present": frame.specimen_present,
            "stale": frame.stale, "captured_s": round(frame.captured_s, 6), "sha256": hashlib.sha256(frame.pixels.tobytes()).hexdigest()}, cause)
        return frame

    def snap(self, exposure_ms: float = DEFAULT_EXPOSURE_MS, cause: str | None = None) -> np.ndarray:
        """The pixels of a new frame (see ``capture``)."""
        return self.capture(exposure_ms, cause).pixels


# ---------------------------------------------------------------------------------------------------- BHMS server

Z_ENCODER_SIGMA_UM = 0.02
XY_ENCODER_SIGMA_UM = 0.1
Z_TOLERANCE_UM = 0.25
XY_TOLERANCE_UM = 1.0


def build_server(world: World, scope: MicroscopeTwin | None = None, *, state_dir: str | Path | None,
                 durability: str = "process", name: str = "simlab-microscope", device_id: str = "microscope-1",
                 **kw: Any) -> tuple[DeviceServer, MicroscopeTwin]:
    """The motorized microscope as a BHMS device server.

    Evidence: ``z_position`` and ``xy_position`` are ``measured`` by encoders on the focus axis and the stage *after*
    the knobs, so a human turning a knob is visible as a changed reading with no operation behind it (F9); the turret
    ``objective`` is ``reported``. ``snap`` returns a frame id, intensity statistics, the focus score and the camera's
    own capture time next to its current time: a frozen camera (F6) keeps returning an old frame, and its capture time
    betrays it. Frames are saved by the scope's frame store.
    """
    scope = scope or MicroscopeTwin(world, device=device_id)
    srv = make_server(world, name, state_dir=state_dir, durability=durability, title="SimLab microscope", **kw)
    dev = srv.device(device_id, name="Motorized microscope",
                     capabilities=["bhms.microscope", "bhms.axis.linear", "bhms.camera"],
                     resources=[f"{device_id}/focus", f"{device_id}/stage", f"{device_id}/turret"],
                     tags=["simlab", "microscope"],
                     description="Upright microscope with motorized focus, XY stage, objective turret and a camera; "
                                 "images the slide on its stage.",
                     identity={"manufacturer": "SimLab", "model": "microscope twin", "firmwareVersion": "1"})
    host = TwinHost(world, dev)

    @dev.property(unit="um", evidence="measured", max_rate_hz=20)
    def z_position() -> float:
        """Focus axis position (um) from its encoder, including any manual knob turns."""
        return host.measure("z", scope.true_z_um(), Z_ENCODER_SIGMA_UM)

    @dev.property(evidence="measured", max_rate_hz=20)
    def xy_position() -> {"x": "um", "y": "um"}:  # noqa: F821
        """Stage position (um) from the stage encoders, including any manual knob turns."""
        x, y = scope.true_xy_um()
        return {"x": host.measure("x", x, XY_ENCODER_SIGMA_UM), "y": host.measure("y", y, XY_ENCODER_SIGMA_UM)}

    @dev.property(unit="1", evidence="reported")
    def objective_magnification() -> float:
        """Magnification of the objective in the optical path."""
        return float(scope.magnification)

    async def move(ctx, seconds: float, what: str) -> None:
        """Let a motion run; a cancel or a power cut stops the axes where they are."""
        try:
            cancelled = await host.elapse(ctx, seconds)
        except PowerLost:
            scope.freeze()
            raise
        if cancelled:
            scope.freeze()
            raise host.canceled(ctx, f"stopped while moving {what}")

    @dev.action(effect="reversible", idempotency="absolute", completion_evidence="measured",
                verified_by=["z_position"], cancel="supported", max_duration_ms=10_000, typical_duration_ms=500,
                resources=[f"{device_id}/focus"])
    async def set_z(ctx, z: Range(0, 200, unit="um")) -> {"z_um": "um"}:  # noqa: F821
        """Move the focus axis to an absolute position (um)."""
        host.begin(ctx)
        await move(ctx, scope.begin_z(z, cause=ctx.operation_id), "focus")
        reading = await ctx.verify("z_position", lambda v: abs(v - z) <= Z_TOLERANCE_UM)
        return host.log.end(ctx.operation_id, {"z_um": round(reading if reading is not None else -1.0, 4)})

    @dev.action(effect="reversible", idempotency="absolute", completion_evidence="measured",
                verified_by=["xy_position"], cancel="supported", max_duration_ms=10_000, typical_duration_ms=500,
                resources=[f"{device_id}/stage"])
    async def move_stage(ctx, x: Range(0, 2047, unit="um"), y: Range(0, 2047, unit="um")) -> {"x_um": "um", "y_um": "um"}:  # noqa: F821
        """Move the stage to an absolute XY position (um)."""
        host.begin(ctx)
        await move(ctx, scope.begin_xy(x, y, cause=ctx.operation_id), "the stage")
        reading = await ctx.verify("xy_position", lambda v: abs(v["x"] - x) <= XY_TOLERANCE_UM
                                   and abs(v["y"] - y) <= XY_TOLERANCE_UM)
        got = reading or {"x": -1.0, "y": -1.0}
        return host.log.end(ctx.operation_id, {"x_um": round(got["x"], 3), "y_um": round(got["y"], 3)})

    @dev.action(effect="reversible", idempotency="absolute", completion_evidence="reported", cancel="unsupported",
                max_duration_ms=5000, typical_duration_ms=1000, resources=[f"{device_id}/turret"])
    async def set_objective(ctx, index: Range(0, 3, unit="1", integer=True)) -> {"magnification": "1"}:  # noqa: F821
        """Rotate the turret to objective ``index`` (0..3 = 4x, 10x, 20x, 40x)."""
        host.begin(ctx)
        await move(ctx, scope.begin_objective(index, cause=ctx.operation_id), "the turret")
        return host.log.end(ctx.operation_id, {"magnification": float(scope.magnification)})

    @dev.action(effect="none", idempotency="relative", completion_evidence="reported", cancel="unsupported",
                max_duration_ms=5000, typical_duration_ms=100)
    async def snap(ctx, exposure_ms: Range(1, 500, unit="ms") = 20) -> {  # noqa: F821
            "frame_id": str, "mean_counts": "1", "focus_score": "1", "captured_at_s": "s", "device_time_s": "s"}:  # noqa: F821
        """Capture a frame and store it. ``captured_at_s`` is the camera's capture time; compare it with
        ``device_time_s``: a frozen camera returns an old frame."""
        host.begin(ctx)
        await move(ctx, exposure_ms / 1000.0, "exposing")
        try:
            frame = scope.capture(float(exposure_ms), cause=ctx.operation_id)
        except CameraUnavailable as exc:
            raise DeviceFault(str(exc), proof="the camera produced no frame", effect="none") from exc
        return host.log.end(ctx.operation_id, {
            "frame_id": frame.frame_id, "mean_counts": round(float(frame.pixels.mean()), 3),
            "focus_score": round(frame.sharpness, 3), "captured_at_s": round(frame.captured_s, 6),
            "device_time_s": round(world.time_s, 6)})

    @dev.on_stop(evidence="reported", max_duration_ms=100)
    async def halt(ctx: Any) -> None:
        scope.freeze()

    return srv, scope
