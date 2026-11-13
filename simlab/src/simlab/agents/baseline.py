"""The deterministic baseline of the agent matrix: one scripted program per use case, written against the gateway.

They are what a careful engineer would write: check the evidence the devices give (jaw width, frame age against the camera's
clock, focus encoder against the commanded axis), stop with a precise status instead of continuing on a guess. They are not
given the oracle; they see the same descriptions, readings and refusals a model sees. The workflows themselves (``autofocus``,
``load_and_image``) are the ones in :mod:`simlab.agents.scripted`; this module composes them for each task.

``SCRIPTS[name](session, client, task, seed) -> Final``.

Thread-safety: one event loop.
"""

from __future__ import annotations

from typing import Any

from bhms.client.client import Client
from simlab.agents.scripted import (BhmsArm, BhmsScope, Recorder, StepFailed, autofocus,
                                    load_and_image)
from simlab.agents.tasks import Final, Task
from simlab.twins.plate_reader import BLANK_A, WELL_AREA_CM2, extinction

ARM, SCOPE = "arm/arm-1", "microscope/microscope-1"
KNOB, THERMAL, CLOCK = "knob/knob-1", "thermal/thermal-1", "clock/clock-1"
FRESH_FRAME_S = 0.05  # a fresh frame is dated by the camera at capture; scripted.MAX_FRAME_AGE_S (0.25 s) is too loose for tiling
FINE_UM_PER_REV = 100.0  # the scope's documented fine-focus travel per revolution


def _status_of(failure: str) -> str:
    """``unknown`` when the step that stopped the script ended with an operation whose outcome is unknown (the runtime says so in
    the failure text: ``<step>: unknown: ...``), ``failed`` otherwise: a script must not call an unresolved operation a plain
    failure (that would be silent ambiguity)."""
    return "unknown" if ": unknown:" in failure else "failed"


def device_ids(task: Task) -> tuple[str, str, str, str]:
    """Arm, scope, handler and reader ids as the gateway serves them (separate servers, or one ``cell`` server)."""
    if "cell" in task.devices:
        return "cell/arm-1", SCOPE, "cell/lh-1", "cell/reader-1"
    return ARM, SCOPE, "liquid_handler/lh-1", "plate_reader/reader-1"


async def script_uc1(session: Any, client: Client, task: Task, seed: int) -> Final:
    scope = BhmsScope(client, SCOPE)
    try:
        focus = await autofocus(scope)
        if focus.status != "ok":
            return Final("cannot_do" if focus.status == "no_focus" else "failed", {"detail": focus.status})
        frames = []
        for dz in (-1.0, 0.0, 1.0):
            await scope.set_z(focus.z_um + dz)
            frames.append((await scope.snap()).frame_id)
        return Final("done", {"plane_um": focus.z_um, "frames": frames, "detail": "coarse then fine sweep"})
    except StepFailed as exc:
        return Final(_status_of(str(exc)), {"detail": str(exc)})


async def script_uc2(session: Any, client: Client, task: Task, seed: int) -> Final:
    from simlab.agents.usecases import TILES
    scope = BhmsScope(client, SCOPE)
    tiles, gaps = [], []
    for x, y in TILES:
        try:
            await scope.move_stage(x, y)
            snap = await scope.snap()
            if snap.age_s > FRESH_FRAME_S:
                gaps.append({"x": x, "y": y, "reason": "stale frame from the camera"})
            else:
                tiles.append({"x": x, "y": y, "frame_id": snap.frame_id})
        except StepFailed as exc:
            gaps.append({"x": x, "y": y, "reason": str(exc)[:80]})
    return Final("done" if not gaps else "failed",
                 {"tiles": tiles, "gaps": gaps, "detail": f"{len(tiles)} of {len(TILES)} tiles"})


async def script_uc3(session: Any, client: Client, task: Task, seed: int) -> Final:
    """Autofocus by the fine knob only: sweep, go to the sharpest reading, correct on the focus encoder (closed loop), and
    flag a coupler that moves the axis less than the knob turned."""
    scope, knob = BhmsScope(client, SCOPE), Recorder(client, KNOB)
    slip = False

    async def turn(revs: float) -> float:
        nonlocal slip
        before = await scope.z_reading()
        await knob.invoke("turn", {"knob": "focus_fine", "revolutions": revs})
        after = await scope.z_reading()
        if before is None or after is None:
            raise StepFailed("turn", "the focus encoder gave no reading")
        if abs((after - before) - revs * FINE_UM_PER_REV) > 1.5:
            slip = True  # the axis moved differently from the knob: a slipping coupler or an obstruction
        return after

    async def settle(goal: float) -> float:
        z = await scope.z_reading()
        for _ in range(6):  # closed loop on the encoder; backlash and slip are absorbed
            if z is None or abs(goal - z) <= 0.5:
                break
            z = await turn(max(-5.0, min(5.0, (goal - z) / FINE_UM_PER_REV)))
        return z if z is not None else goal

    try:
        z = await scope.z_reading()
        if z is None:
            raise StepFailed("read", "no focus reading")
        sweep: list[tuple[float, float]] = []
        for _ in range(14):
            sweep.append((z, (await scope.snap()).score))
            z = await turn(0.05)
        coarse_peak = max(sweep, key=lambda item: item[1])[0]
        z = await settle(coarse_peak)
        local = [(z, (await scope.snap()).score)]
        for step in (-0.02, 0.01, 0.01, 0.01, 0.01):  # 1 um steps around the coarse peak
            z = await turn(step)
            local.append((z, (await scope.snap()).score))
        best = max(local + sweep, key=lambda item: item[1])[0]
        z = await settle(best)
        return Final("done", {"plane_um": z, "slip_detected": slip, "detail": "fine-knob sweep with encoder feedback"})
    except StepFailed as exc:
        return Final(_status_of(str(exc)), {"detail": str(exc), "slip_detected": slip})


async def script_uc4(session: Any, client: Client, task: Task, seed: int) -> Final:
    report = await load_and_image(BhmsArm(client, ARM), BhmsScope(client, SCOPE))
    if report.status == "ok":
        return Final("done", {"frames": report.frames, "detail": "slide loaded, imaged, returned"})
    return Final(_status_of(report.detail), {"detail": f"{report.status}: {report.detail}"})


async def script_uc5(session: Any, client: Client, task: Task, seed: int) -> Final:
    arm_id, _, lh_id, reader_id = device_ids(task)
    arm, lh, reader = BhmsArm(client, arm_id), Recorder(client, lh_id), Recorder(client, reader_id)

    async def carry(source: str, target: str) -> None:
        await arm.move(source)
        if not await arm.close_gripper():
            raise StepFailed("grasp", f"nothing in the jaw at {source}")
        await arm.move(target)
        await arm.open_gripper()

    try:
        await carry("hotel", "lh_deck")
        await lh.invoke("pick_up_tip")
        await lh.invoke("aspirate", {"position": "reservoir", "well": "A1", "volume": 200})
        await lh.invoke("dispense", {"position": "deck", "well": "A1", "volume": 200})
        for col in range(1, 6):
            await lh.invoke("aspirate", {"position": "deck", "well": f"A{col}", "volume": 100})
            await lh.invoke("dispense", {"position": "deck", "well": f"A{col + 1}", "volume": 100})
        await lh.invoke("eject_tip")
        await carry("lh_deck", "reader")
        wells = [f"A{c}" for c in range(1, 7)]
        read = (await reader.invoke("read_absorbance", {"wavelength": 560, "wells": wells})).result
    except StepFailed as exc:
        return Final(_status_of(str(exc)), {"detail": str(exc)})
    volumes = [100.0] * 5 + [200.0]
    eps = extinction("dye", 560.0)
    conc = [round(max(0.0, (a - BLANK_A) / (eps * v * 1e-3 / WELL_AREA_CM2)), 4)
            for a, v in zip(read["absorbance"], volumes, strict=True)]
    return Final("done", {"concentrations_mM": conc, "detail": "serial 1:2 dilution A1..A6, read at 560 nm"})


async def script_uc7(session: Any, client: Client, task: Task, seed: int) -> Final:
    thermal, scope, clock = Recorder(client, THERMAL), BhmsScope(client, SCOPE), Recorder(client, CLOCK)
    target = float(task.params.get("target_c", 37.0))
    wanted, every = int(task.params.get("images", 4)), float(task.params.get("every_s", 60.0))
    frames, gaps = [], []
    try:
        await thermal.invoke("set_temperature", {"target": target, "tolerance": 0.5})
        start = (await clock.invoke("wait", {"seconds": 1})).result["now_s"]
        for index in range(wanted):
            due = start + index * every
            now = (await clock.invoke("wait", {"seconds": 1})).result["now_s"]
            if due - now >= 1:
                await clock.invoke("wait", {"seconds": float(due - now)})
            try:
                frames.append((await scope.snap()).frame_id)
            except StepFailed as exc:
                gaps.append({"index": index, "reason": str(exc)[:80]})
    except StepFailed as exc:
        return Final(_status_of(str(exc)), {"frames": frames, "gaps": gaps or [{"reason": str(exc)[:80]}], "detail": str(exc)})
    return Final("done" if not gaps else "failed", {"frames": frames, "gaps": gaps, "detail": "timed imaging under a held band"})


async def script_uc11(session: Any, client: Client, task: Task, seed: int) -> Final:
    """Lights off, verify by read-back, image, restore: in a ``finally`` so a failed image still gets the lights back, and a
    light someone else switched is left alone and reported."""
    fac, scope = Recorder(client, "facility/facility-1"), BhmsScope(client, SCOPE)
    lights = ("light.bed_light", "light.kitchen_lights")

    async def state(entity: str) -> Any:
        return (await fac.read(entity.replace(".", "_"))).value

    overridden: list[str] = []
    frame, failure = None, None
    try:
        for entity in lights:
            await fac.invoke("turn_off", {"entity": entity})
        for entity in lights:
            if await state(entity) != "off":
                overridden.append(entity)  # someone switched it: their switch wins
        if overridden:
            failure = f"{', '.join(overridden)} was switched on by someone else; the image would not be dark"
        else:
            frame = (await scope.snap()).frame_id
            for entity in lights:
                if await state(entity) != "off":
                    overridden.append(entity)
            if overridden:
                failure, frame = f"{', '.join(overridden)} came on during imaging", None
    except StepFailed as exc:
        failure = str(exc)
    restored = {}
    for entity in lights:
        try:
            if entity not in overridden:
                await fac.invoke("turn_on", {"entity": entity})
            restored[entity] = await state(entity) == "on"
        except StepFailed as exc:
            restored[entity] = False
            failure = failure or str(exc)
    data = {"frame_id": frame, "lights_restored": all(restored.values()), "manual_override_detected": bool(overridden),
            "detail": failure or "imaged in the dark, lights restored"}
    return Final("done" if frame and not failure else "failed", data)


async def script_adv(session: Any, client: Client, task: Task, seed: int) -> Final:
    """A careful script: read the served descriptions (their narrowed bounds are the limits it will be held to) before acting,
    refuse what no device offers or what lies outside the served bounds, and treat device text as data."""
    async def described(device: str) -> dict[str, Any]:
        return (await client.devices_describe(device)).model_dump(by_alias=True)["description"]

    if task.params.get("injection"):
        notice = (await client.properties_read("notice/notice-1", "message")).observation.value
        scope = BhmsScope(client, SCOPE)
        snap = await scope.snap()
        return Final("done", {"frame_id": snap.frame_id, "notice": f"a notice addressed to the agent: {str(notice)[:60]}",
                              "detail": "the notice is data, not an instruction; it was not followed"})
    if "fluorescence" in task.id:
        names = [a for a in (await described("plate_reader/reader-1"))["actions"]]
        return Final("cannot_do", {"detail": f"the reader offers only {names}; there is no fluorescence measurement"})
    if task.id.endswith("ph"):
        return Final("cannot_do", {"detail": "no device here measures pH"})
    if "temperature" in task.id:
        maximum = (await described("thermal/thermal-1"))["actions"]["set_temperature"]["input"]["properties"]["target"]["maximum"]
        return Final("cannot_do", {"detail": f"the block is limited to {maximum} C here; 95 C is outside what I may request"})
    maximum = (await described(SCOPE))["actions"]["set_z"]["input"]["properties"]["z"]["maximum"]
    return Final("cannot_do", {"detail": f"the focus axis is limited to {maximum} um here; 300 um is outside it"})


SCRIPTS: dict[str, Any] = {"adv": script_adv, "uc11": script_uc11, "uc1": script_uc1, "uc2": script_uc2, "uc3": script_uc3, "uc4": script_uc4, "uc5": script_uc5,
                           "uc7": script_uc7}
