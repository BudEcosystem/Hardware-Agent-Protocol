"""The shared physical world: a MuJoCo scene, one clock, the effect log, snapshots and a digest.

``World`` is the single source of truth every twin reads and writes (design: validation plan §3, §11). It owns

* the MuJoCo model and data (the bench scene with the arm model attached at ``arm_mount``; the arm model is a
  parameter of the scene, so the BHMS arm MJCF replaces the Menagerie SO-ARM100 without touching anything else),
* the clock (``stepped``: advanced as fast as the CPU allows; ``realtime``: paced against the wall clock),
* an append-only effect log (every physical effect, with the operation that caused it),
* the knob mechanisms (backlash and slip) between a knob's joint angle and the axis it drives,
* the material ``Ledger`` and the ``FaultPlane`` (created here so every twin shares them).

Determinism: all randomness comes from per-name generators derived from ``seed`` (``rng_for``); the clock advances in
whole physics steps (``dt`` = 2 ms, the clock resolution: ``step(0.0003)`` advances one step); ``digest()`` hashes the
canonical snapshot and effect log. Identical seeds and identical command sequences give identical digests.

Thread-safety: one event loop (or one thread) owns a world; twins call it from asyncio handlers.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import math
import time
import warnings
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import mujoco
import numpy as np

from bhms.protocol.canonical import digest as canonical_digest
from simlab.faults import FaultPlane
from simlab.ledger import IN_GRIPPER, LOST, Ledger
from simlab.scene import default_arm_model

ARM_PREFIX = "arm_"
GRIPPER_SITE = ARM_PREFIX + "tcp"
FLOOR_Z = -0.69
_SLICE_S = 0.02  # an asynchronous waiter yields to the event loop every 20 ms of simulated time


@dataclass(frozen=True)
class Effect:
    """One physical effect: what happened, to which device, when, and which operation caused it (``None`` = nobody)."""

    seq: int
    time_s: float
    device: str
    kind: str
    detail: dict[str, Any]
    cause: str | None


@dataclass(frozen=True)
class SceneParams:
    """Scene parameters set per world (validation plan §11 Task 3)."""

    backlash_rad: float = 0.02  # lost motion of every knob train (full dead-band width)
    knob_friction_nm: float = 0.005  # dry friction of a knob joint
    focus_um_per_rev: float = 100.0  # fine focus travel per revolution
    focus_coarse_um_per_rev: float = 1000.0  # coarse focus travel per revolution
    stage_um_per_rev: float = 500.0  # stage x/y knob travel per revolution


KNOB_JOINTS = ("focus_coarse", "focus_fine", "stage_x_knob", "stage_y_knob")


@dataclass
class KnobTrain:
    """A knob's mechanism: input joint angle -> output angle through a dead-band (backlash) plus slip losses.

    The gear train starts engaged on its forward flank (``output = input - backlash/2``), so a +x then -x turn nets one
    full ``backlash`` of lost motion at the axis (validation plan test ``test_knob_backlash_is_visible_at_the_stage``).
    """

    backlash_rad: float
    last_input: float = 0.0
    output: float = field(default=0.0)
    slip_offset: float = 0.0
    slipping: bool = False

    def __post_init__(self) -> None:
        self.output = -self.backlash_rad / 2

    def follow(self, angle: float) -> None:
        half = self.backlash_rad / 2
        if not self.slipping:
            if angle - half > self.output:
                self.output = angle - half
            elif angle + half < self.output:
                self.output = angle + half
        self.last_input = angle

    def angle(self) -> float:
        return self.output + self.slip_offset


class World:
    """One shared physical world; see the module docstring.

    Args:
        scene: bench MJCF (``simlab.scene.BENCH``).
        seed: seeds every generator; part of the snapshot.
        mode: ``"stepped"`` (default) or ``"realtime"`` (asynchronous waits sleep the wall clock).
        arm_model: MJCF of the arm attached at ``arm_mount`` with prefix ``arm_`` (default: Menagerie SO-ARM100);
            ``None`` with ``attach_arm=False`` builds a world without an arm.
        params: knob and focus parameters.
    """

    def __init__(self, scene: Path, seed: int, mode: Literal["stepped", "realtime"] = "stepped", *,
                 arm_model: Path | None = None, attach_arm: bool = True, params: SceneParams | None = None) -> None:
        if mode not in ("stepped", "realtime"):
            raise ValueError("mode must be 'stepped' or 'realtime'")
        self.scene, self.seed, self.mode = Path(scene), int(seed), mode
        self.params = params or SceneParams()
        self.model, self.has_arm = self._compile(arm_model, attach_arm)
        self.data = mujoco.MjData(self.model)
        mujoco.mj_forward(self.model, self.data)
        self.dt = float(self.model.opt.timestep)
        self._steps = 0
        self._effects: list[Effect] = []
        self._rngs: dict[str, np.random.Generator] = {}
        self._controllers: dict[int, Callable[[World], None]] = {}
        self._controller_ids = itertools.count()
        self.knobs = {name: KnobTrain(self.params.backlash_rad) for name in KNOB_JOINTS}
        self._loss_positions: dict[str, np.ndarray] = {}
        self._timers: list[tuple[float, int, asyncio.Future[None]]] = []
        self._tie = itertools.count()
        self._pump: asyncio.Task[None] | None = None
        self.ledger = Ledger(self)
        self.faults = FaultPlane(self)
        self.ledger.add_container("plate", "microplate_96", {}, "hotel")
        self.ledger.add_container("slide", "slide", {}, "slide_rack", meta={"specimen_z_um": 40.0})

    # ------------------------------------------------------------------ construction

    def _compile(self, arm_model: Path | None, attach_arm: bool) -> tuple[mujoco.MjModel, bool]:
        spec = mujoco.MjSpec.from_file(str(self.scene))
        for name in KNOB_JOINTS:
            spec.joint(name).frictionloss = self.params.knob_friction_nm
        if attach_arm:
            arm = mujoco.MjSpec.from_file(str(arm_model or default_arm_model()))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # option conflicts (cone, impratio): the bench's values win, by design
                spec.attach(arm, site=spec.site("arm_mount"), prefix=ARM_PREFIX)
            for body in spec.bodies:
                if body.name.startswith(ARM_PREFIX):
                    body.gravcomp = 1.0  # gravity-compensated joint controller (documented in twins/arm.py)
            jaw = spec.body(ARM_PREFIX + "Fixed_Jaw")
            jaw.add_site(name=GRIPPER_SITE, pos=[0.0, -0.10, 0.0], size=[0.004, 0, 0])
        return spec.compile(), attach_arm

    # ------------------------------------------------------------------ clock

    @property
    def time_s(self) -> float:
        return self._steps * self.dt

    def add_controller(self, fn: Callable[[World], None]) -> int:
        """Register ``fn(world)`` to run before every physics step (a joint controller); returns a handle."""
        handle = next(self._controller_ids)
        self._controllers[handle] = fn
        return handle

    def remove_controller(self, handle: int) -> None:
        self._controllers.pop(handle, None)

    def step(self, seconds: float) -> None:
        """Advance the world by ``seconds`` (rounded up to whole 2 ms physics steps), synchronously."""
        if seconds < 0 or not math.isfinite(seconds):
            raise ValueError(f"cannot step {seconds!r} seconds")
        for _ in range(math.ceil(seconds / self.dt - 1e-9)):
            self._physics_step()

    def _physics_step(self) -> None:
        for controller in list(self._controllers.values()):
            controller(self)
        mujoco.mj_step(self.model, self.data)
        self._steps += 1
        self._follow_knobs()
        self._sync_held()
        self.faults.on_time(self.time_s)

    async def advance(self, seconds: float) -> None:
        """Wait ``seconds`` of world time without blocking other waiters (stepped: instantly; realtime: paced)."""
        await self.until(self.time_s + seconds)

    async def until(self, target_s: float) -> None:
        """Wait until the world clock reaches ``target_s``. One pump task steps the world for every waiter, so
        concurrent devices share one timeline."""
        if self.time_s >= target_s - 1e-9:
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._timers, (target_s, next(self._tie), future))
        if self._pump is None or self._pump.done():
            self._pump = asyncio.get_running_loop().create_task(self._run_pump())
        await future

    async def _run_pump(self) -> None:
        while self._timers:
            while self._timers and self._timers[0][2].done():
                heapq.heappop(self._timers)
            if not self._timers:
                break
            chunk = min(self._timers[0][0] - self.time_s, _SLICE_S)
            if chunk > 1e-9:
                started = time.perf_counter()
                self.step(chunk)
                if self.mode == "realtime":
                    await asyncio.sleep(max(0.0, chunk - (time.perf_counter() - started)))
                else:
                    await asyncio.sleep(0)
            while self._timers and self._timers[0][0] <= self.time_s + 1e-9:
                _, _, future = heapq.heappop(self._timers)
                if not future.done():
                    future.set_result(None)

    # ------------------------------------------------------------------ randomness

    def rng_for(self, name: str) -> np.random.Generator:
        """The generator of one noise source (a sensor, a specimen): derived from the seed and the name only, so
        reading one sensor never shifts another's noise."""
        if name not in self._rngs:
            self._rngs[name] = np.random.default_rng([self.seed, zlib.crc32(name.encode())])
        return self._rngs[name]

    # ------------------------------------------------------------------ effects

    def record(self, device: str, kind: str, detail: dict[str, Any] | None = None, cause: str | None = None) -> Effect:
        """Append an effect (the only way anything is logged); faults may react to it (``OnEvent``)."""
        effect = Effect(len(self._effects), round(self.time_s, 9), device, kind, dict(detail or {}), cause)
        self._effects.append(effect)
        self.faults.on_effect(effect)
        return effect

    def effect_log(self) -> list[Effect]:
        return list(self._effects)

    # ------------------------------------------------------------------ geometry

    def site_pos(self, site: str) -> np.ndarray:
        """World position of a named site (the arm tcp included), current."""
        return np.array(self.data.site(site).xpos)

    def joint_angle(self, name: str) -> float:
        return float(self.data.joint(name).qpos[0])

    def turn_joint(self, name: str, delta_rad: float, cause: str | None) -> None:
        """Turn a free joint (a knob) by ``delta_rad`` and record it; ``cause=None`` is a human or a fault."""
        joint = self.data.joint(name)
        joint.qpos[0] += delta_rad
        mujoco.mj_forward(self.model, self.data)
        self._follow_knobs()
        self.record("bench", "joint_turned", {"joint": name, "delta_rad": delta_rad,
                                              "angle_rad": float(joint.qpos[0])}, cause)

    def _follow_knobs(self) -> None:
        for name, train in self.knobs.items():
            angle = self.joint_angle(name)
            if angle != train.last_input:
                train.follow(angle)

    def knob_output(self, name: str) -> float:
        """The angle the axis sees after backlash and slip losses."""
        return self.knobs[name].angle()

    # ------------------------------------------------------------------ bodies follow the ledger

    def place(self, container_id: str, location: str) -> None:
        """Put a container's mocap body where the ledger now says it is (called by the ledger on every move)."""
        body = self.body_index(container_id)
        if body is None:
            return
        if location == LOST:
            held = self._loss_positions.get(container_id)
            if held is None:
                held = np.array(self.data.mocap_pos[body])
            self._loss_positions[container_id] = np.array([held[0], held[1], FLOOR_Z])
            self.data.mocap_pos[body] = self._loss_positions[container_id]
        elif location == IN_GRIPPER:
            self._loss_positions.pop(container_id, None)
            self._sync_held()
        else:
            self._loss_positions.pop(container_id, None)
            self.data.mocap_pos[body] = self.model.site(location).pos
        mujoco.mj_forward(self.model, self.data)

    def _sync_held(self) -> None:
        if not self.has_arm:
            return
        for container_id in self.ledger.held():
            body = self.body_index(container_id)
            if body is not None:
                self.data.mocap_pos[body] = self.data.site(GRIPPER_SITE).xpos

    def body_index(self, container_id: str) -> int | None:
        """The mocap index of the body drawn for a container, or ``None`` when the container has no body."""
        try:
            mocap = int(self.model.body(container_id).mocapid[0])
        except KeyError:
            return None
        return mocap if mocap >= 0 else None

    # ------------------------------------------------------------------ truth

    def snapshot(self) -> dict[str, Any]:
        """The canonical state of the world: clock, seed, generators, joints, objects, ledger, knobs, faults."""
        joints = {self.model.joint(i).name: round(float(self.data.qpos[self.model.jnt_qposadr[i]]), 9)
                  for i in range(self.model.njnt)}
        objects = {c: [round(float(v), 9) for v in self.data.mocap_pos[self.body_index(c)]]
                   for c in self.ledger.container_ids() if self.body_index(c) is not None}
        return {"time_s": round(self.time_s, 9), "seed": self.seed,
                "rng": {n: _jsonable(g.bit_generator.state) for n, g in sorted(self._rngs.items())},
                "joints": joints, "objects": objects, "ledger": self.ledger.locations(),
                "materials": self.ledger.snapshot(),
                "knobs": {n: [round(t.output, 9), round(t.slip_offset, 9)] for n, t in sorted(self.knobs.items())},
                "faults": self.faults.snapshot()}

    def digest(self) -> str:
        """SHA-256 (``sha256:<hex>``) of the canonical snapshot and effect log (the shared canonicalizer)."""
        log = [[e.seq, e.time_s, e.device, e.kind, e.detail, e.cause] for e in self._effects]
        return canonical_digest({"snapshot": self.snapshot(), "effects": log})

    # ------------------------------------------------------------------ rendering

    def render(self, camera: str, height: int = 480, width: int = 640) -> np.ndarray:
        """Render a scene camera (EGL/OSMesa as configured by ``MUJOCO_GL``); a uint8 RGB frame."""
        with mujoco.Renderer(self.model, height, width) as renderer:
            renderer.update_scene(self.data, camera=camera)
            return renderer.render().copy()


def _jsonable(value: Any) -> Any:
    """Generator state holds 128-bit integers; canonical JSON is I-JSON (integers within 2**53), so use strings."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, int) and abs(value) > 2**53:
        return str(value)
    return value
