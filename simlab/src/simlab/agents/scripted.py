"""Deterministic scripted agents: the workflows that prove the lab (validation plan §11 Task 8, UC1 and UC4).

One algorithm, two ways to reach the devices. The workflow (``autofocus``, ``load_and_image``) is written once against two
small ports, an arm port and a scope port; ``Direct*`` ports call the twins' own interfaces (no BHMS involved, as the plan's
V1 tests want) and ``Bhms*`` ports invoke real BHMS actions through the SDK client, recording every operation so the oracle
can judge each claim the runtime made. Agents see only what a device or the runtime tells them; they never touch the world.

The agents are honest scripts: they check the evidence the devices give (jaw width after a carry, the camera's capture time
against its clock, the focus axis reading against the commanded one) and stop with a precise status instead of continuing on
a guess. Statuses: ``ok``, ``no_focus``, ``stale_frame``, ``interference``, ``grasp_failed``, ``object_lost``, ``step_failed``.

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from bhms.client.client import Client
from simlab.twins.arm import ArmTwin
from simlab.twins.microscope import MicroscopeTwin

MIN_CONTRAST = 1.5  # peak / floor of the coarse sweep below which the stage shows no focusable specimen
MAX_FRAME_AGE_S = 0.25
Z_TOLERANCE_UM = 0.6


@dataclass(frozen=True)
class Snap:
    """What a camera tells the agent about a frame."""

    frame_id: str
    score: float
    age_s: float  # the camera's clock minus the frame's capture time


@dataclass(frozen=True)
class FocusResult:
    status: str
    z_um: float | None
    contrast: float
    sweep: tuple[tuple[float, float], ...] = ()


class StepFailed(Exception):
    """A device refused or failed a step; ``operation`` is the BHMS record when there is one."""

    def __init__(self, step: str, detail: str, operation: Any = None) -> None:
        super().__init__(f"{step}: {detail}")
        self.step, self.detail, self.operation = step, detail, operation


class ScopePort(Protocol):
    async def set_z(self, z_um: float) -> None: ...
    async def z_reading(self) -> float | None: ...
    async def snap(self, exposure_ms: float = 20.0) -> Snap: ...
    async def move_stage(self, x_um: float, y_um: float) -> None: ...


class ArmPort(Protocol):
    async def move(self, site: str) -> None: ...
    async def close_gripper(self) -> bool: ...
    async def open_gripper(self) -> None: ...
    async def width_mm(self) -> float | None: ...


# ------------------------------------------------------------------------------------------------ the algorithm


async def autofocus(scope: ScopePort, *, lo: float = 20.0, hi: float = 80.0, coarse: float = 10.0,
                    fine: float = 1.0) -> FocusResult:
    """Coarse-to-fine focus search by gradient sharpness.

    A coarse sweep over ``lo..hi`` finds the best region; ``no_focus`` when the best frame is not clearly sharper than the
    worst (an empty stage has no peak); a fine sweep around it finds the plane. A frame older than the camera's clock, or a
    focus axis that is not where it was sent (someone turned a knob), ends the search with a status that says so.
    """
    sweep: list[tuple[float, float]] = []

    async def measure(z: float) -> tuple[float, float] | FocusResult:
        await scope.set_z(z)
        reading = await scope.z_reading()
        if reading is not None and abs(reading - z) > Z_TOLERANCE_UM:
            return FocusResult("interference", None, 0.0, tuple(sweep))
        snap = await scope.snap()
        if snap.age_s > MAX_FRAME_AGE_S:
            return FocusResult("stale_frame", None, 0.0, tuple(sweep))
        sweep.append((z, snap.score))
        return z, snap.score

    zs = [lo + i * coarse for i in range(int(round((hi - lo) / coarse)) + 1)]
    for z in zs:
        outcome = await measure(z)
        if isinstance(outcome, FocusResult):
            return outcome
    best_z, best = max(sweep, key=lambda item: item[1])
    floor = min(score for _, score in sweep)
    contrast = best / max(floor, 1e-9)
    if contrast < MIN_CONTRAST:
        return FocusResult("no_focus", None, contrast, tuple(sweep))
    z = max(lo, best_z - coarse)
    while z <= min(hi, best_z + coarse) + 1e-9:
        if all(abs(z - done) > 1e-6 for done, _ in sweep):
            outcome = await measure(z)
            if isinstance(outcome, FocusResult):
                return outcome
        z += fine
    plane, _ = max(sweep, key=lambda item: item[1])
    return FocusResult("ok", plane, contrast, tuple(sweep))


@dataclass
class RunReport:
    status: str
    detail: str = ""
    focus: FocusResult | None = None
    frames: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)


async def load_and_image(arm: ArmPort, scope: ScopePort, *, frames: int = 2,
                         log: Callable[[str], None] = lambda _msg: None) -> RunReport:
    """UC4: the arm loads the slide onto the stage, the microscope autofocuses, images are recorded, the slide goes back.

    Checks after every carry that the jaw still holds the slide (a plate that fell shows as a closed jaw), and stops with
    ``object_lost`` rather than imaging an empty stage.
    """
    report = RunReport("ok")

    def step(text: str) -> None:
        report.steps.append(text)
        log(text)

    async def carry(source: str, target: str) -> RunReport | None:
        await arm.move(source)
        if not await arm.close_gripper():
            step(f"grasp at {source} held nothing")
            return RunReport("grasp_failed", f"nothing in the jaw at {source}", steps=report.steps)
        await arm.move(target)
        width = await arm.width_mm()
        if width is not None and width < 2.0:
            step(f"jaw closed on nothing on the way to {target}")
            return RunReport("object_lost", f"the jaw is empty after the carry to {target} (width {width:.1f} mm)",
                             steps=report.steps)
        await arm.open_gripper()
        return None

    try:
        failed = await carry("slide_rack", "microscope_stage")
        if failed:
            return failed
        step("slide on the stage")
        await arm.move("hotel")  # clear the optical path
        focus = await autofocus(scope)
        report.focus = focus
        step(f"autofocus: {focus.status}")
        if focus.status != "ok":
            return RunReport(focus.status, "the microscope could not find a focus plane", focus, steps=report.steps)
        assert focus.z_um is not None
        await scope.set_z(focus.z_um)
        for index in range(frames):
            await scope.move_stage(900.0 + 120.0 * index, 1000.0)
            snap = await scope.snap()
            if snap.age_s > MAX_FRAME_AGE_S:
                return RunReport("stale_frame", "the camera returned an old frame", focus, report.frames, report.steps)
            report.frames.append(snap.frame_id)
            step(f"image {snap.frame_id}")
        failed = await carry("microscope_stage", "slide_rack")
        if failed:
            failed.focus, failed.frames = focus, report.frames
            return failed
        step("slide returned")
    except StepFailed as exc:
        return RunReport("step_failed", str(exc), report.focus, report.frames, report.steps)
    return report


# ------------------------------------------------------------------------------------------------ direct ports


class DirectScope:
    """The scope port over the twin's own interface (synchronous calls, no BHMS)."""

    def __init__(self, scope: MicroscopeTwin) -> None:
        self.scope, self._n = scope, 0

    def _cause(self) -> str:
        self._n += 1
        return f"direct-scope-{self._n}"

    async def set_z(self, z_um: float) -> None:
        self.scope.set_z(z_um, self._cause())

    async def z_reading(self) -> float | None:
        return self.scope.true_z_um()

    async def snap(self, exposure_ms: float = 20.0) -> Snap:
        frame = self.scope.capture(exposure_ms, self._cause())
        return Snap(frame.frame_id, frame.sharpness, self.scope.world.time_s - frame.captured_s)

    async def move_stage(self, x_um: float, y_um: float) -> None:
        self.scope.set_xy(x_um, y_um, self._cause())


class DirectArm:
    def __init__(self, arm: ArmTwin) -> None:
        self.arm, self._n = arm, 0

    def _cause(self) -> str:
        self._n += 1
        return f"direct-arm-{self._n}"

    async def move(self, site: str) -> None:
        result = self.arm.move_to_site(site, self._cause())
        if not result.reached:
            raise StepFailed(f"move to {site}", f"{result.error_mm:.1f} mm short")

    async def close_gripper(self) -> bool:
        return self.arm.grip(True, self._cause()) is not None

    async def open_gripper(self) -> None:
        self.arm.grip(False, self._cause())

    async def width_mm(self) -> float | None:
        return self.arm.gripper_width_mm()


# ------------------------------------------------------------------------------------------------ BHMS ports


class Recorder:
    """Invokes BHMS actions and keeps every operation record (the runtime's claims) for the oracle."""

    def __init__(self, client: Client, device_id: str, wait_ms: int = 60_000) -> None:
        self.client, self.device_id, self.wait_ms = client, device_id, wait_ms
        self.operations: list[Any] = []

    async def invoke(self, action: str, arguments: dict[str, Any] | None = None, *, step: str | None = None) -> Any:
        result = await self.client.actions_invoke(self.device_id, action, arguments or {}, wait_ms=self.wait_ms)
        operation = result.operation
        self.operations.append(operation)
        if operation.state != "completed":
            detail = operation.error.message if operation.error else operation.state
            raise StepFailed(step or action, f"{operation.state}: {detail}", operation)
        return operation

    async def read(self, prop: str) -> Any:
        return (await self.client.properties_read(self.device_id, prop, fresh=True)).observation


class BhmsScope(Recorder):
    async def set_z(self, z_um: float) -> None:
        await self.invoke("set_z", {"z": z_um})

    async def z_reading(self) -> float | None:
        observation = await self.read("z_position")
        return None if observation.value is None else float(observation.value)

    async def snap(self, exposure_ms: float = 20.0) -> Snap:
        result = (await self.invoke("snap", {"exposure_ms": exposure_ms})).result
        return Snap(result["frame_id"], result["focus_score"], result["device_time_s"] - result["captured_at_s"])

    async def move_stage(self, x_um: float, y_um: float) -> None:
        await self.invoke("move_stage", {"x": x_um, "y": y_um})


class BhmsArm(Recorder):
    async def move(self, site: str) -> None:
        await self.invoke("move_to_site", {"site": site}, step=f"move to {site}")

    async def close_gripper(self) -> bool:
        return bool((await self.invoke("close_gripper")).result["holding"])

    async def open_gripper(self) -> None:
        await self.invoke("open_gripper")

    async def width_mm(self) -> float | None:
        observation = await self.read("gripper_width")
        return None if observation.value is None else float(observation.value)


# ------------------------------------------------------------------------------------------------ plan-named agents


def _drive(coroutine: Awaitable[Any]) -> Any:
    return asyncio.run(coroutine)  # type: ignore[arg-type]


class ScriptedAutofocus:
    """``ScriptedAutofocus(scope).run()``: the focus search over the twin's direct interface."""

    def __init__(self, scope: MicroscopeTwin) -> None:
        self.scope = scope

    def run(self) -> FocusResult:
        return _drive(autofocus(DirectScope(self.scope)))


class ScriptedLoadAndImage:
    """``ScriptedLoadAndImage(arm, scope).run()``: UC4 over the twins' direct interfaces."""

    def __init__(self, arm: ArmTwin, scope: MicroscopeTwin, frames: int = 2) -> None:
        self.arm, self.scope, self.frames = arm, scope, frames

    def run(self) -> RunReport:
        return _drive(load_and_image(DirectArm(self.arm), DirectScope(self.scope), frames=self.frames))


__all__ = ["ArmPort", "BhmsArm", "BhmsScope", "DirectArm", "DirectScope", "FocusResult", "Recorder", "RunReport",
           "ScopePort", "ScriptedAutofocus", "ScriptedLoadAndImage", "Snap", "StepFailed", "autofocus",
           "load_and_image"]
