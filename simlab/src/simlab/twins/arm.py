"""Arm twin: pick and place to named sites on the shared bench, with real joint dynamics.

The arm is the SO-ARM100 (Menagerie) attached to the bench by ``World``; any MJCF with the same joint and jaw names can
replace it (the scene takes the model as a parameter). The twin is a PI joint controller on the MuJoCo position
actuators: gravity is compensated in the model (``gravcomp``), the integral term removes the static error that joint
friction would otherwise leave, and joint-space paths follow a minimum-jerk profile through a hover waypoint above each
site (inverse kinematics solved once per site at construction by damped least squares on a private ``MjData``).

Objects are kinematic: a plate or slide is a mocap body that the ledger places. Closing the jaw within
``GRASP_RADIUS_M`` (3 mm) of a container attaches it to the gripper (``Ledger.location == "in_gripper"``); opening the
jaw over a site puts it there, opening it anywhere else drops it (``"lost"``). Contact grasping is not simulated: the
joint dynamics are real, the grasp is a rule, and the jaw's reported opening is derived from what is in it, so a dropped
plate is visible in the gripper-width reading.

Thread-safety: the twin belongs to its world's thread.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from bhms.server.context import DeviceFault
from bhms.server.decorators import OneOf, Range
from bhms.server.server import DeviceServer
from simlab.ledger import IN_GRIPPER, LOST
from simlab.simdevice import PowerLost, TwinHost, make_server, simulated_device
from simlab.world import ARM_PREFIX, GRIPPER_SITE, World

ARM_JOINTS = ("Rotation", "Pitch", "Elbow", "Wrist_Pitch", "Wrist_Roll")
JAW = "Jaw"
HOME = np.array([0.0, -1.57, 1.57, 1.57, -1.57])
SITES = ("hotel", "slide_rack", "lh_deck", "microscope_stage", "reader", "balance")
GRASP_RADIUS_M = 0.003
HOVER_M = 0.05
REACHED_MM = 3.0
MAX_JOINT_SPEED = 1.5  # rad/s
SETTLE_S = 1.2
GRIP_S = 0.4
JAW_OPEN_RAD = 1.7
JAW_CLOSED_RAD = -0.17
JAW_RAD_PER_MM = 1.0 / 60.0  # jaw angle ~ opening width of the object it holds
_WIDTH_MM = {"microplate_96": 85.0, "slide": 25.0}
_KI = 8.0  # integral gain (1/s) of the joint controller
_TRIM_LIMIT = 0.05  # rad


@dataclass(frozen=True)
class MoveResult:
    """``reached``: the tool tip ended within ``REACHED_MM`` of the site; ``error_mm`` measured from the world."""

    reached: bool
    error_mm: float
    duration_s: float


@dataclass
class Motion:
    """A move in progress. ``duration_s`` is the world time it needs; call ``finish`` after that time has elapsed."""

    arm: ArmTwin
    site: str
    cause: str | None
    waypoints: list[np.ndarray]
    segment_s: list[float]
    started_s: float
    start_q: np.ndarray
    aborted: bool = False
    result: MoveResult | None = field(default=None, repr=False)

    @property
    def duration_s(self) -> float:
        return sum(self.segment_s) + SETTLE_S

    def finish(self) -> MoveResult:
        """Record and return the outcome, measured from the world (never from the plan)."""
        if self.result is None:
            self.result = self.arm._finish(self)
        return self.result


class ArmTwin:
    """The arm and its gripper in a world; see the module docstring."""

    def __init__(self, world: World, *, device: str = "arm") -> None:
        if not world.has_arm:
            raise ValueError("this world has no arm attached")
        self.world, self.device = world, device
        m = world.model
        self._q_idx = [int(m.jnt_qposadr[m.joint(ARM_PREFIX + j).id]) for j in ARM_JOINTS]
        self._act = [m.actuator(ARM_PREFIX + j).id for j in ARM_JOINTS]
        self._jaw_act = m.actuator(ARM_PREFIX + JAW).id
        self._jaw_q = int(m.jnt_qposadr[m.joint(ARM_PREFIX + JAW).id])
        self._tcp = m.site(GRIPPER_SITE).id
        self._trim = np.zeros(len(ARM_JOINTS))
        self._motion: Motion | None = None
        self._hold = HOME.copy()
        self._jaw_target = JAW_OPEN_RAD
        self._jaw_open = True
        self.last_site: str | None = None
        self._candidate: str | None = None
        world.data.qpos[self._q_idx] = HOME
        world.data.qpos[self._jaw_q] = JAW_OPEN_RAD
        world.data.ctrl[self._act] = HOME
        world.data.ctrl[self._jaw_act] = JAW_OPEN_RAD
        mujoco.mj_forward(m, world.data)
        self._poses = {site: self._solve_site(site) for site in SITES}
        world.add_controller(self._control)

    # ------------------------------------------------------------------ inverse kinematics (once per site)

    def _solve_site(self, site: str) -> tuple[np.ndarray, np.ndarray]:
        target = self.world.site_pos(site)
        hover = target + np.array([0.0, 0.0, HOVER_M])
        q_hover = self._ik(hover, HOME)
        return q_hover, self._ik(target, q_hover)

    def _ik(self, target: np.ndarray, seed: np.ndarray) -> np.ndarray:
        """Damped least squares for the tool-tip position with a soft preference for pointing down; the joint limits
        clip every iterate. Raises when the site is out of reach of this arm model (never returns a wrong pose)."""
        m, scratch = self.world.model, mujoco.MjData(self.world.model)
        lo, hi = m.jnt_range[[m.joint(ARM_PREFIX + j).id for j in ARM_JOINTS], :].T
        best: tuple[float, np.ndarray] | None = None
        for attempt, weight in enumerate((0.4, 0.15, 0.0)):
            q = np.clip(seed + np.random.default_rng(attempt).normal(0.0, 0.05 * attempt, len(seed)), lo, hi)
            jacp, jacr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
            for _ in range(400):
                scratch.qpos[self._q_idx] = q
                mujoco.mj_kinematics(m, scratch)
                mujoco.mj_comPos(m, scratch)
                err = target - scratch.site_xpos[self._tcp]
                if np.linalg.norm(err) < 2e-5:
                    break
                mujoco.mj_jacSite(m, scratch, jacp, jacr, self._tcp)
                rows, residual = [jacp[:, self._q_idx]], [err]
                if weight:
                    tool = -scratch.site_xmat[self._tcp].reshape(3, 3)[:, 1]
                    skew = np.array([[0, -tool[2], tool[1]], [tool[2], 0, -tool[0]], [-tool[1], tool[0], 0]])
                    rows.append(weight * skew @ jacr[:, self._q_idx])
                    residual.append(weight * (np.array([0.0, 0.0, -1.0]) - tool))
                jac, res = np.vstack(rows), np.concatenate(residual)
                step = jac.T @ np.linalg.solve(jac @ jac.T + 1e-5 * np.eye(len(res)), res)
                q = np.clip(q + 0.8 * step, lo, hi)
            scratch.qpos[self._q_idx] = q
            mujoco.mj_kinematics(m, scratch)
            miss = float(np.linalg.norm(target - scratch.site_xpos[self._tcp]))
            if best is None or miss < best[0]:
                best = (miss, q.copy())
            if miss < 1e-4:
                break
        assert best is not None
        if best[0] > 2e-4:
            raise ValueError(f"site at {np.round(target, 3).tolist()} m is out of reach of this arm model "
                             f"(closest approach {best[0] * 1000:.1f} mm)")
        return best[1]

    # ------------------------------------------------------------------ state

    @property
    def busy(self) -> bool:
        return self._motion is not None and not self._motion.aborted and self._motion.result is None

    def joint_state(self) -> dict[str, float]:
        """True joint angles in rad (the world's, not a sensor's)."""
        data = self.world.data
        return {**{j: float(data.qpos[i]) for j, i in zip(ARM_JOINTS, self._q_idx, strict=True)},
                JAW: float(data.qpos[self._jaw_q])}

    def tcp_position(self) -> np.ndarray:
        return self.world.site_pos(GRIPPER_SITE)

    def holding(self) -> str | None:
        held = self.world.ledger.held()
        return held[0] if held else None

    def gripper_width_mm(self) -> float:
        """The jaw opening as the jaw's own encoder would see it: the held object's width, 0 closed on nothing,
        ~100 mm when open."""
        held = self.holding()
        if self._jaw_open:
            return 100.0
        return _WIDTH_MM.get(self.world.ledger.kind(held), 40.0) if held else 0.0

    # ------------------------------------------------------------------ control

    def _control(self, world: World) -> None:
        data = world.data
        q = data.qpos[self._q_idx]
        motion = self._motion
        settled = True
        if motion is not None and not motion.aborted and motion.result is None:
            target = self._reference(motion, world.time_s)
            settled = world.time_s - motion.started_s >= sum(motion.segment_s)
        else:
            target = self._hold
        stalled = world.faults.stalled_joints()
        for k, joint in enumerate(ARM_JOINTS):
            if ARM_PREFIX + joint in stalled or joint in stalled:
                data.ctrl[self._act[k]] = q[k]  # a stalled joint holds wherever it is
                continue
            if settled:  # integrate only while the reference is stationary (anti-windup)
                self._trim[k] = float(np.clip(self._trim[k] + _KI * (target[k] - q[k]) * world.dt,
                                              -_TRIM_LIMIT, _TRIM_LIMIT))
            data.ctrl[self._act[k]] = target[k] + self._trim[k]
        data.ctrl[self._jaw_act] = self._jaw_target

    @staticmethod
    def _reference(motion: Motion, now_s: float) -> np.ndarray:
        """Minimum-jerk interpolation through the waypoints; holds the last waypoint afterwards."""
        elapsed = now_s - motion.started_s
        previous = motion.start_q
        for waypoint, seconds in zip(motion.waypoints, motion.segment_s, strict=True):
            if elapsed < seconds:
                s = elapsed / seconds
                return previous + (waypoint - previous) * (10 * s**3 - 15 * s**4 + 6 * s**5)
            elapsed -= seconds
            previous = waypoint
        return motion.waypoints[-1]

    # ------------------------------------------------------------------ commands

    def begin_move(self, site: str, cause: str | None) -> Motion:
        """Start a move to ``site`` (through its hover waypoint). The caller lets ``motion.duration_s`` of world time
        pass (``world.step`` or ``await world.advance``) and then calls ``motion.finish()``."""
        if site not in self._poses:
            raise KeyError(f"unknown site {site!r}; sites are {', '.join(SITES)}")
        if self.busy:
            raise RuntimeError("the arm is already moving")
        hover, place = self._poses[site]
        start = np.array(self.world.data.qpos[self._q_idx])
        waypoints, segments, previous = [], [], start
        for waypoint in (hover, place):
            waypoints.append(waypoint)
            segments.append(max(0.3, float(np.abs(waypoint - previous).max()) / MAX_JOINT_SPEED))
            previous = waypoint
        self._trim[:] = 0.0
        self.last_site = site
        self._motion = Motion(self, site, cause, waypoints, segments, self.world.time_s, start)
        self.world.record(self.device, "move_started", {"site": site, "holding": self.holding()}, cause)
        return self._motion

    def abort(self, cause: str | None = None) -> None:
        """Stop where the arm is: hold the present joint angles (the stop path of the twin)."""
        if self._motion is not None and self._motion.result is None and not self._motion.aborted:
            self._motion.aborted = True
            self._hold = np.array(self.world.data.qpos[self._q_idx])
            self.world.record(self.device, "move_aborted", {"site": self._motion.site}, cause)

    def _finish(self, motion: Motion) -> MoveResult:
        error_mm = float(np.linalg.norm(self.tcp_position() - self.world.site_pos(motion.site)) * 1000.0)
        reached = error_mm <= REACHED_MM
        if not motion.aborted:
            self._hold = motion.waypoints[-1].copy()
        result = MoveResult(reached, round(error_mm, 3), round(self.world.time_s - motion.started_s, 3))
        self.world.record(self.device, "move_finished", {"site": motion.site, "reached": reached,
                                                         "error_mm": result.error_mm}, motion.cause)
        return result

    def move_to_site(self, site: str, cause: str | None) -> MoveResult:
        """Synchronous move for tests and scripted agents: start, let the world run, finish."""
        motion = self.begin_move(site, cause)
        self.world.step(motion.duration_s)
        return motion.finish()

    def begin_grip(self, close: bool, cause: str | None) -> float:
        """Start the jaw; returns the world seconds it takes. A closing jaw targets the container within 3 mm of the
        tool tip (it stops at that object's width), or closes fully on nothing."""
        ledger, tip = self.world.ledger, self.tcp_position()
        self._candidate = None
        self._jaw_open = not close
        if not close:
            self._jaw_target = JAW_OPEN_RAD
        elif self.holding() is not None:
            self._jaw_target = _WIDTH_MM.get(ledger.kind(self.holding()), 40.0) * JAW_RAD_PER_MM
        else:
            near = sorted((float(np.linalg.norm(self.world.data.mocap_pos[self.world.body_index(c)] - tip)), c)
                          for c in ledger.container_ids()
                          if self.world.body_index(c) is not None and ledger.location(c) not in (IN_GRIPPER, LOST))
            near = [item for item in near if item[0] <= GRASP_RADIUS_M]
            self._candidate = near[0][1] if near else None
            self._jaw_target = (_WIDTH_MM.get(ledger.kind(self._candidate), 40.0) * JAW_RAD_PER_MM
                                if self._candidate else JAW_CLOSED_RAD)
        return GRIP_S

    def finish_grip(self, close: bool, cause: str | None) -> str | None:
        """Close: attach the targeted container if it is still where it was. Open: put the held container on the site
        it is over, or lose it. Returns the container now held (or ``None``)."""
        ledger = self.world.ledger
        if close:
            candidate, self._candidate = self._candidate, None
            if candidate is not None and ledger.location(candidate) not in (IN_GRIPPER, LOST):
                ledger.move(candidate, IN_GRIPPER, cause)
            self.world.record(self.device, "grip", {"close": True, "holding": self.holding()}, cause)
        else:
            held = self.holding()
            if held is not None:
                tip = self.tcp_position()
                over = [s for s in SITES if float(np.linalg.norm(self.world.site_pos(s) - tip)) <= 2 * GRASP_RADIUS_M]
                ledger.move(held, over[0] if over else LOST, cause)
            self.world.record(self.device, "grip", {"close": False, "holding": None}, cause)
        return self.holding()

    def grip(self, close: bool, cause: str | None) -> str | None:
        """Synchronous grip for tests and scripted agents."""
        self.world.step(self.begin_grip(close, cause))
        return self.finish_grip(close, cause)


# ---------------------------------------------------------------------------------------------------- BHMS server

ENCODER_SIGMA_M = 5e-5  # the arm's FK position estimate from joint encoders: 0.05 mm per axis
JAW_SIGMA_MM = 0.1


def build_server(world: World, arm: ArmTwin | None = None, *, state_dir: str | Path | None, durability: str = "process",
                 name: str = "simlab-arm", device_id: str = "arm-1", **kw: Any) -> tuple[DeviceServer, ArmTwin]:
    """The arm twin as a BHMS device server.

    Evidence: ``tcp_position`` and ``gripper_width`` are ``measured`` (joint and jaw encoders with Gaussian noise, read
    through ``TwinHost.measure``); nothing else is read from the world. ``move_to_site`` completes ``verified`` only when
    the measured tool position is within 3 mm of the taught site; a missed site is a ``DEVICE_FAULT`` (the arm knows).
    ``close_gripper`` is verified by the jaw width, so a grasp that held nothing, or a plate dropped later, is visible.
    """
    arm = arm or ArmTwin(world, device=device_id)
    srv = make_server(world, name, state_dir=state_dir, durability=durability, title="SimLab arm (SO-ARM100)", **kw)
    dev = simulated_device(srv, device_id, name="Bench arm", capabilities=["bhms.arm.manipulator", "bhms.gripper"],
                     resources=[f"{device_id}/motion", f"{device_id}/gripper"], tags=["simlab", "arm"],
                     description="5-axis desktop arm with a jaw gripper; moves to taught bench sites and grips labware.",
                     identity={"manufacturer": "SimLab", "model": "SO-ARM100 twin", "firmwareVersion": "1"},
                     safety_summary="Moves in the shared bench workspace; the stop procedure holds the present pose.")
    host = TwinHost(world, dev)

    @dev.property(evidence="measured", max_rate_hz=20)
    def tcp_position() -> {"x": "m", "y": "m", "z": "m"}:  # noqa: F821
        """Tool tip position in the bench frame (m), from joint encoders and forward kinematics."""
        x, y, z = (host.measure(f"tcp_{axis}", float(v), ENCODER_SIGMA_M)
                   for axis, v in zip("xyz", arm.tcp_position(), strict=True))
        return {"x": x, "y": y, "z": z}

    @dev.property(unit="mm", evidence="measured", max_rate_hz=20)
    def gripper_width() -> float:
        """Jaw opening (mm) from the jaw encoder: about 100 open, the held object's width when holding, 0 closed on
        nothing."""
        return host.measure("jaw", arm.gripper_width_mm(), JAW_SIGMA_MM)

    def site_error_mm(measured: dict[str, float], site: str) -> float:
        tip = np.array([measured["x"], measured["y"], measured["z"]])
        return float(np.linalg.norm(tip - world.site_pos(site)) * 1000.0)

    @dev.action(effect="reversible", idempotency="absolute", completion_evidence="measured",
                verified_by=["tcp_position"], cancel="supported", max_duration_ms=30_000, typical_duration_ms=4000,
                resources=[f"{device_id}/motion"])
    async def move_to_site(ctx, site: OneOf(*SITES)) -> {"error_mm": Range(0, 1e6, unit="mm", nullable=True), "duration_s": "s"}:  # noqa: F821
        """Move the tool tip to a named bench site (via a hover point above it). Fails if the site is not reached."""
        host.begin(ctx)
        motion = arm.begin_move(site, cause=ctx.operation_id)
        try:
            cancelled = await host.elapse(ctx, motion.duration_s)
        except PowerLost:
            arm.abort(ctx.operation_id)
            raise
        if cancelled:
            arm.abort(ctx.operation_id)
            motion.finish()
            raise host.canceled(ctx, f"stopped on the way to {site}")
        result = motion.finish()
        measured = await ctx.verify("tcp_position", lambda v: site_error_mm(v, site) <= REACHED_MM)
        error = site_error_mm(measured, site) if measured is not None else None
        if error is not None and error > REACHED_MM:
            raise DeviceFault(f"the tool tip is {error:.1f} mm from {site}", partial="moved but did not arrive",
                              hint="check for a stalled joint; read tcp_position before retrying")
        return host.log.end(ctx.operation_id, {"error_mm": None if error is None else round(error, 3),
                                               "duration_s": result.duration_s})

    @dev.action(effect="reversible", idempotency="absolute", completion_evidence="measured",
                verified_by=["gripper_width"], cancel="unsupported", max_duration_ms=5000, typical_duration_ms=400,
                resources=[f"{device_id}/gripper"])
    async def close_gripper(ctx) -> {"width_mm": Range(0, 200, unit="mm", nullable=True), "holding": bool | None}:  # noqa: F821
        """Close the jaw on whatever is at the tool tip. ``holding`` is true when the jaw stopped on an object."""
        host.begin(ctx)
        seconds = arm.begin_grip(True, cause=ctx.operation_id)
        await host.elapse(ctx, seconds)
        arm.finish_grip(True, cause=ctx.operation_id)
        width = await ctx.verify("gripper_width", lambda v: v > 1.0)
        return host.log.end(ctx.operation_id, {"width_mm": None if width is None else round(width, 3),
                                               "holding": None if width is None else width > 1.0})

    @dev.action(effect="irreversible", idempotency="absolute", completion_evidence="measured",
                verified_by=["gripper_width"], cancel="unsupported", max_duration_ms=5000, typical_duration_ms=400,
                resources=[f"{device_id}/gripper"])
    async def open_gripper(ctx) -> {"width_mm": Range(0, 200, unit="mm", nullable=True)}:  # noqa: F821
        """Open the jaw: a held object is released onto the site below the tool tip, or dropped if there is none."""
        host.begin(ctx)
        seconds = arm.begin_grip(False, cause=ctx.operation_id)
        await host.elapse(ctx, seconds)
        arm.finish_grip(False, cause=ctx.operation_id)
        width = await ctx.verify("gripper_width", lambda v: v > 90.0)
        return host.log.end(ctx.operation_id, {"width_mm": None if width is None else round(width, 3)})

    @dev.on_stop(evidence="reported", max_duration_ms=200)
    async def halt(ctx: Any) -> None:
        arm.abort(None)

    return srv, arm
