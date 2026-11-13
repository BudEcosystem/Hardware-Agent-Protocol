"""Fault-injection runs: each scenario injects one fault class into a scripted run and classifies what came back.

The question every scenario asks (validation plan §3.3): did the runtime and the devices give an *honest* outcome? The
acceptable outcomes are an exact result, an honest ``unknown`` (later reconciled, never a second effect), a refusal that
proves nothing happened, or a stop by the agent on evidence the devices gave it. The unacceptable outcomes are the oracle's
``FALSE_CERTAINTY``, ``FALSE_NO_EFFECT`` and ``DUPLICATE_EFFECT``, an effect on a world that says it did not happen, or an
agent that images an empty stage.

Scenarios implemented here are the ones that act on the world or on a twin or adapter: F2, F3, F5, F6, F7, F8, F9, F10, F13,
F14 (see ``SCENARIOS``). Message-level faults (F1, F4, F11, F12, F15, F16) belong to the SDK's transport and runtime tests and
are not repeated here.

``python -m simlab.runs.fault_runs --out DIR`` runs them all and writes ``DIR/faults.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from bhms.client.client import Client
from bhms.protocol.errors import BhmsError
from simlab.agents.scripted import BhmsArm, BhmsScope, Recorder, load_and_image
from simlab.faults import At, Fault, OnEvent
from simlab.lab import Lab
from simlab.oracle import Oracle, Verdict
from simlab.runs.judge import judge_operations

ACCEPTABLE = {Verdict.CONSISTENT.value, Verdict.HONEST_UNKNOWN.value}


@dataclass
class Outcome:
    scenario: str
    fault_class: str
    expectation: str
    observed: dict[str, Any]
    verdicts: dict[str, int]
    passed: bool
    wall_s: float = 0.0
    notes: list[str] = field(default_factory=list)


def _verdicts(lab: Lab, recorders: list[Recorder]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in judge_operations(lab.oracle, [op for r in recorders for op in r.operations]):
        counts[item.verdict.value] = counts.get(item.verdict.value, 0) + 1
    return counts


def _outcome(name: str, fault_class: str, expectation: str, observed: dict[str, Any], verdicts: dict[str, int],
             condition: bool, started: float, *notes: str) -> Outcome:
    honest = set(verdicts) <= ACCEPTABLE
    return Outcome(name, fault_class, expectation, observed, verdicts, bool(condition and honest),
                   round(time.perf_counter() - started, 3), list(notes))


async def _uc4_lab(run_dir: Path, seed: int, **kw: Any) -> tuple[Lab, BhmsArm, BhmsScope]:
    lab = await Lab.start(run_dir, seed=seed, devices=("arm", "microscope"), **kw)
    lab.world.ledger.add_container("slide", "slide", {}, "slide_rack", meta={"specimen_z_um": 48.0})
    return lab, BhmsArm(lab.client("arm"), "arm-1"), BhmsScope(lab.client("microscope"), "microscope-1")


# ------------------------------------------------------------------------------------------------ scenarios


async def f14_drop_during_carry(run_dir: Path) -> Outcome:
    started = time.perf_counter()
    lab, arm, scope = await _uc4_lab(run_dir, 21)
    async with lab:
        lab.world.faults.inject(Fault("slide", "drop_object", OnEvent("move_started"),
                                      {"require_location": "in_gripper", "delay_s": 0.5}))
        report = await load_and_image(arm, scope)
        images = [e for e in lab.world.effect_log() if e.kind == "image_captured"]
        verdicts = _verdicts(lab, [arm, scope])
        return _outcome("f14_drop_during_carry", "F14", "agent stops on the empty jaw; nothing is imaged",
                        {"status": report.status, "slide": lab.world.ledger.location("slide"), "images": len(images)},
                        verdicts, report.status == "object_lost" and not images
                        and lab.world.ledger.location("slide") == "lost", started)


async def f6_stale_camera(run_dir: Path) -> Outcome:
    started = time.perf_counter()
    lab, arm, scope = await _uc4_lab(run_dir, 22)
    async with lab:
        lab.world.faults.inject(Fault("scope", "stale_camera", OnEvent("z_move")))
        report = await load_and_image(arm, scope)
        stale = [e for e in lab.world.effect_log() if e.kind == "image_captured" and e.detail["stale"]]
        verdicts = _verdicts(lab, [arm, scope])
        return _outcome("f6_stale_camera", "F6", "agent refuses a frame older than the camera's clock; no plane reported",
                        {"status": report.status, "stale_frames_served": len(stale)}, verdicts,
                        report.status == "stale_frame" and len(stale) >= 1 and report.focus is not None
                        and report.focus.z_um is None, started)


async def f7_camera_disconnected(run_dir: Path) -> Outcome:
    started = time.perf_counter()
    lab, arm, scope = await _uc4_lab(run_dir, 23)
    async with lab:
        lab.world.faults.inject(Fault("scope", "sensor_disconnect", At(0.0)))
        report = await load_and_image(arm, scope)
        failed = [op for op in scope.operations if op.state == "failed"]
        verdicts = _verdicts(lab, [arm, scope])
        return _outcome("f7_camera_disconnected", "F7", "the snap fails with proof of no effect; the run stops",
                        {"status": report.status, "failed_ops": [(o.action, o.effect, o.error.may_have_acted)
                                                                 for o in failed]}, verdicts,
                        report.status == "step_failed" and len(failed) == 1 and failed[0].effect == "none"
                        and failed[0].error.may_have_acted is False, started)


async def f8_joint_stall(run_dir: Path) -> Outcome:
    started = time.perf_counter()
    lab, arm, scope = await _uc4_lab(run_dir, 24)
    async with lab:
        lab.world.faults.inject(Fault("Pitch", "joint_stall", At(0.0)))
        report = await load_and_image(arm, scope)
        failed = [op for op in arm.operations if op.state == "failed"]
        verdicts = _verdicts(lab, [arm, scope])
        return _outcome("f8_joint_stall", "F8", "the arm's own encoders see the miss: DEVICE_FAULT, effect not verified",
                        {"status": report.status, "failed": [(o.action, o.effect, o.error.bhms_code) for o in failed]},
                        verdicts, report.status == "step_failed" and bool(failed) and failed[0].effect != "verified"
                        and failed[0].error.bhms_code == "DEVICE_FAULT", started)


async def f9_manual_knob_turn(run_dir: Path) -> Outcome:
    started = time.perf_counter()
    lab, arm, scope = await _uc4_lab(run_dir, 25)
    async with lab:
        lab.world.faults.inject(Fault("focus_fine", "manual_move", OnEvent("image_captured"),
                                      {"delay_s": 0.01, "delta_rad": 2.0}))
        report = await load_and_image(arm, scope)
        turns = [e for e in lab.world.effect_log() if e.kind == "joint_turned"]
        verdicts = _verdicts(lab, [arm, scope])
        return _outcome("f9_manual_knob_turn", "F9", "a turn nobody commanded is seen as a moved focus axis; no plane "
                        "is claimed", {"status": report.status, "turns_with_no_cause": len([t for t in turns
                                                                                            if t.cause is None])},
                        verdicts, report.status == "interference" and len(turns) == 1 and turns[0].cause is None
                        and report.focus is not None and report.focus.z_um is None, started)


async def f3_power_loss_mid_move(run_dir: Path) -> Outcome:
    started = time.perf_counter()
    lab, arm, scope = await _uc4_lab(run_dir, 26)
    async with lab:
        lab.world.faults.inject(Fault("arm-1", "power_loss", OnEvent("move_started"), {"delay_s": 0.8}))
        report = await load_and_image(arm, scope)
        unknown = [op for op in arm.operations if op.state == "unknown"]
        before = len([e for e in lab.world.effect_log() if e.kind == "move_started"])
        lab.world.faults.clear("fault-1")
        await lab.servers["arm"].reconcile("arm-1")
        settled = [(await lab.client("arm").operations_get(op.operation_id)).operation for op in unknown]
        after = len([e for e in lab.world.effect_log() if e.kind == "move_started"])
        verdicts = _verdicts(lab, [arm, scope])
        return _outcome("f3_power_loss_mid_move", "F3", "unknown while powered off, reconciled from the device log to "
                        "failed (may have acted); no second effect",
                        {"status": report.status, "states": [(s.state, s.error.may_have_acted) for s in settled],
                         "moves_before_reconcile": before, "moves_after": after}, verdicts,
                        report.status == "step_failed" and len(unknown) == 1 and settled[0].state == "failed"
                        and settled[0].error.may_have_acted is True and before == after, started)


async def f2_reply_lost_after_effect(run_dir: Path) -> Outcome:
    started = time.perf_counter()
    lab = await Lab.start(run_dir, seed=27, devices=("arm",))
    async with lab:
        arm = Recorder(lab.client("arm"), "arm-1")
        client: Client = lab.client("arm")
        # the request reaches the device and the physical move happens; the client gives up before it sees the reply
        try:
            await asyncio.wait_for(client.actions_invoke("arm-1", "move_to_site", {"site": "reader"},
                                                         operation_key="lost-reply", wait_ms=30_000), timeout=0.02)
            lost = False
        except (asyncio.TimeoutError, TimeoutError):
            lost = True
        # the safe recovery: ask again with the same key (operations/get would do too)
        result = await client.actions_invoke("arm-1", "move_to_site", {"site": "reader"}, operation_key="lost-reply",
                                             wait_ms=30_000)
        arm.operations.append(result.operation)
        starts = [e for e in lab.world.effect_log() if e.kind == "move_started"]
        verdicts = _verdicts(lab, [arm])
        return _outcome("f2_reply_lost_after_effect", "F2", "same key returns the same operation; exactly one effect",
                        {"reply_lost": lost, "state": result.operation.state, "effects": len(starts),
                         "duplicates": len(Oracle(lab.world).duplicates(result.operation.operation_id))}, verdicts,
                        lost and result.operation.state == "completed" and len(starts) == 1, started)


async def f5_adapter_stall_other_devices_continue(run_dir: Path) -> Outcome:
    started = time.perf_counter()
    lab = await Lab.start(run_dir, seed=28, devices=("arm", "microscope", "thermal"), bridged=("thermal",))
    async with lab:
        lab.world.ledger.add_container("slide", "slide", {}, "slide_rack", meta={"specimen_z_um": 48.0})
        arm, scope = BhmsArm(lab.client("arm"), "arm-1"), BhmsScope(lab.client("microscope"), "microscope-1")
        thermal = Recorder(lab.client("thermal"), "thermal-m1", wait_ms=20_000)
        lab.world.faults.inject(Fault("thermal-m1", "power_loss", At(0.0)))  # the Modbus instrument stops answering
        lab.world.step(0.01)

        async def heater() -> str:
            try:
                await thermal.invoke("set_setpoint", {"value": 40.0})
                return "completed"
            except Exception as exc:  # noqa: BLE001 - the operation record carries the outcome
                return getattr(getattr(exc, "operation", None), "state", type(exc).__name__)

        heater_state, report = await asyncio.gather(heater(), load_and_image(arm, scope))
        verdicts = _verdicts(lab, [arm, scope, thermal])
        return _outcome("f5_adapter_stall", "F5", "the stalled adapter's work is unknown; the other devices complete",
                        {"thermal": heater_state, "uc4": report.status}, verdicts,
                        heater_state == "unknown" and report.status == "ok", started)


async def f10_two_agents_one_arm(run_dir: Path) -> Outcome:
    started = time.perf_counter()
    lab = await Lab.start(run_dir, seed=29, devices=("arm",))
    async with lab:
        url = f"unix:{lab.socket_dir}/arm.sock"
        second = await Client.connect(url)
        try:
            first = Recorder(lab.client("arm"), "arm-1")
            other = Recorder(second, "arm-1")
            await asyncio.gather(first.invoke("move_to_site", {"site": "reader"}),
                                 other.invoke("move_to_site", {"site": "balance"}))
            kinds = [e.kind for e in lab.world.effect_log() if e.kind in ("move_started", "move_finished")]
            serialised = kinds == ["move_started", "move_finished", "move_started", "move_finished"]
            verdicts = _verdicts(lab, [first, other])
            return _outcome("f10_two_agents_one_arm", "F10", "the two moves run one after the other, never overlapping",
                            {"effects": kinds, "states": [o.state for o in first.operations + other.operations]},
                            verdicts, serialised, started)
        finally:
            await second.close()


async def f13_journal_unwritable_stop_still_works(run_dir: Path) -> Outcome:
    started = time.perf_counter()
    lab = await Lab.start(run_dir, seed=30, devices=("arm",))
    async with lab:
        server, client = lab.servers["arm"], lab.client("arm")
        server.store.set_writable(False)
        try:
            await client.actions_invoke("arm-1", "move_to_site", {"site": "reader"}, wait_ms=5000)
            refused = None
        except BhmsError as exc:
            refused = exc.code
        moves = len([e for e in lab.world.effect_log() if e.kind == "move_started"])
        stopped = await client.stop("journal is unwritable", device_ids=["arm-1"], wait_ms=2000)
        server.store.set_writable(True)
        arm = Recorder(client, "arm-1")
        await arm.invoke("move_to_site", {"site": "hotel"})
        return _outcome("f13_journal_unwritable", "F13", "new mutations are denied, the stop path still works, and work "
                        "resumes when the journal is writable again",
                        {"invoke_refused": refused, "moves_while_unwritable": moves,
                         "stop_outcome": getattr(getattr(stopped, "stop", stopped), "outcome", "returned")},
                        _verdicts(lab, [arm]), refused is not None and moves == 0, started)


SCENARIOS: dict[str, Callable[[Path], Awaitable[Outcome]]] = {
    f.__name__: f for f in (f14_drop_during_carry, f6_stale_camera, f7_camera_disconnected, f8_joint_stall,
                            f9_manual_knob_turn, f3_power_loss_mid_move, f2_reply_lost_after_effect,
                            f5_adapter_stall_other_devices_continue, f10_two_agents_one_arm,
                            f13_journal_unwritable_stop_still_works)}


async def run_all(out: Path) -> list[Outcome]:
    outcomes = []
    for name, scenario in SCENARIOS.items():
        outcomes.append(await scenario(out / name))
    return outcomes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simlab.runs.fault_runs", description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    outcomes = asyncio.run(run_all(args.out))
    (args.out / "faults.json").write_text(json.dumps([asdict(o) for o in outcomes], indent=2, default=str))
    for o in outcomes:
        print(f"{'PASS' if o.passed else 'FAIL'} {o.fault_class:4} {o.scenario}: {o.expectation} -> {o.observed}; "
              f"verdicts {o.verdicts}")
    return 0 if all(o.passed for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
