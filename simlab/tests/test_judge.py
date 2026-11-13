"""Negative tests for runs/judge.py: every rule gets a *lying* operation record against a world where something else happened,
and the judge must flag it. A judge that only ever says CONSISTENT is worthless, so these are the tests of the tests."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from lab_helpers import bench
from simlab import effects
from simlab.lab import Lab
from simlab.oracle import Oracle, Verdict
from simlab.runs.judge import MissingRule, judge_operations
from simlab.scene import BENCH
from simlab.twins import balance, centrifuge, liquid_handler, plate_reader, thermal
from simlab.twins.centrifuge import rotor_site
from simlab.twins.microscope import MicroscopeTwin
from simlab.world import World

_ids = iter(range(10_000))


def lie(device, action, arguments, result=None, *, state="completed", effect="verified", key=None, op_id=None):
    """A forged BHMS operation record."""
    n = next(_ids)
    return SimpleNamespace(operation_id=op_id or f"op-{n}", operation_key=key or f"key-{n}", device_id=device, action=action,
                           arguments=arguments, admitted_arguments=None, result=result, state=state, effect=effect,
                           created_at=n)


def verdict(world, record, rules=None):
    return judge_operations(Oracle(world), [record], rules)[0].verdict


def world(seed=1, **kw):
    return World(BENCH, seed=seed, attach_arm=False, **kw)


# ------------------------------------------------------------------------------------------------ rules, one lie each


def test_z_claim_is_checked_against_the_true_axis_not_the_commanded_target():
    w, arm, scope = bench(1)
    scope.begin_z(60.0, cause="op-z")  # the effect log says 60 was commanded ...
    w.step(0.05)  # ... but only 0.05 s of travel passed
    scope.finish_z("op-z")
    honest = lie("microscope-1", "set_z", {"z": 60.0}, {"z_um": 60.0}, op_id="op-z")
    assert verdict(w, honest) is Verdict.FALSE_CERTAINTY  # the axis is nowhere near 60
    w.step(1.0)
    scope.finish_z("op-z2")
    assert verdict(w, lie("microscope-1", "set_z", {"z": 60.0}, {"z_um": 60.0}, op_id="op-z2")) is Verdict.CONSISTENT
    assert verdict(w, lie("microscope-1", "set_z", {"z": 60.0}, {"z_um": 75.0}, op_id="op-z2")) is Verdict.FALSE_CERTAINTY


def test_a_knob_turn_after_a_move_makes_the_z_claim_false():
    w, arm, scope = bench(1, backlash_rad=0.0)
    scope.set_z(40.0, cause="op-k")
    w.turn_joint("focus_fine", 3.0, cause=None)  # a human moves the axis; the next finish records the truth
    scope.finish_z("op-k2")
    assert verdict(w, lie("microscope-1", "set_z", {"z": 40.0}, {"z_um": 40.0}, op_id="op-k2")) is Verdict.FALSE_CERTAINTY


def test_stage_and_objective_claims_are_checked_against_achieved_truth():
    w, arm, scope = bench(1)
    scope.set_xy(500.0, 600.0, cause="op-xy")
    assert verdict(w, lie("microscope-1", "move_stage", {"x": 500.0, "y": 600.0}, {"x_um": 500.0, "y_um": 600.0},
                          op_id="op-xy")) is Verdict.CONSISTENT
    assert verdict(w, lie("microscope-1", "move_stage", {"x": 900.0, "y": 600.0}, {"x_um": 900.0, "y_um": 600.0},
                          op_id="op-xy")) is Verdict.FALSE_CERTAINTY
    scope.set_objective(1, cause="op-ob")
    assert verdict(w, lie("microscope-1", "set_objective", {"index": 3}, {"magnification": 40.0},
                          op_id="op-ob")) is Verdict.FALSE_CERTAINTY


def test_arm_claims_follow_the_move_finish_and_grip_records():
    w, arm, scope = bench(1)
    arm.move_to_site("hotel", cause="op-m")
    assert verdict(w, lie("arm-1", "move_to_site", {"site": "reader"}, {"error_mm": 0.2, "duration_s": 3.0},
                          op_id="op-m")) is Verdict.FALSE_CERTAINTY
    arm.move_to_site("reader", cause="op-g")
    arm.grip(True, cause="op-g")  # nothing is at the reader: the jaw closes on air
    assert verdict(w, lie("arm-1", "close_gripper", {}, {"width_mm": 40.0, "holding": True},
                          op_id="op-g")) is Verdict.FALSE_CERTAINTY
    assert verdict(w, lie("arm-1", "open_gripper", {}, {"width_mm": 100.0}, op_id="op-g")) is Verdict.FALSE_CERTAINTY


def test_snap_claim_with_a_wrong_capture_time_is_flagged():
    w, arm, scope = bench(1, specimen_z_um=40.0, slide_site="microscope_stage")
    frame = scope.capture(cause="op-s")
    good = {"frame_id": frame.frame_id, "mean_counts": 1.0, "focus_score": 1.0, "captured_at_s": frame.captured_s,
            "device_time_s": w.time_s}
    assert verdict(w, lie("microscope-1", "snap", {}, good, effect="none", op_id="op-s")) is Verdict.CONSISTENT
    stale = {**good, "captured_at_s": frame.captured_s + 5.0}
    assert verdict(w, lie("microscope-1", "snap", {}, stale, effect="none", op_id="op-s")) is Verdict.FALSE_CERTAINTY


def test_thermal_claim_for_90_against_a_setpoint_of_37_is_flagged():
    w = world()
    block = thermal.ThermalModel(w)
    block.command(37.0, True, cause="op-t")
    w.step(300.0)
    block.finish("op-t")
    assert verdict(w, lie("thermal-1", "set_temperature", {"target": 37.0}, {"temperature": 37.0},
                          op_id="op-t")) is Verdict.CONSISTENT
    assert verdict(w, lie("thermal-1", "set_temperature", {"target": 90.0}, {"temperature": 90.0},
                          op_id="op-t")) is Verdict.FALSE_CERTAINTY
    assert verdict(w, lie("thermal-1", "set_temperature", {"target": 37.0}, {"temperature": 41.0},
                          op_id="op-t")) is Verdict.FALSE_CERTAINTY  # the returned reading is not the block's
    assert verdict(w, lie("thermal-1", "disable", {}, None, op_id="op-t")) is Verdict.FALSE_CERTAINTY  # it is still enabled


def test_a_block_that_has_not_arrived_is_not_verified():
    w = world()
    block = thermal.ThermalModel(w)
    block.command(80.0, True, cause="op-early")
    w.step(10.0)
    block.finish("op-early")
    assert verdict(w, lie("thermal-1", "set_temperature", {"target": 80.0}, {"temperature": 80.0},
                          op_id="op-early")) is Verdict.FALSE_CERTAINTY


def test_centrifuge_claims_are_checked_against_the_rotor():
    w = world()
    for n in (1, 5):
        w.ledger.add_container(f"tube{n}", "tube", {"a": (1000.0, {})}, rotor_site(n), max_volume_ul=2000.0)
    fuge = centrifuge.CentrifugeModel(w)
    fuge.start(60.0, 30.0, cause="op-c")
    w.step(3.0)  # still ramping up
    fuge.record_speed("op-c")
    assert verdict(w, lie("centrifuge-1", "spin", {"speed": 60.0, "duration": 30.0}, {"peak_speed": 60.0},
                          op_id="op-c")) is Verdict.FALSE_CERTAINTY
    assert verdict(w, lie("centrifuge-1", "open_lid", {}, None, op_id="op-c")) is Verdict.FALSE_CERTAINTY  # never opened


def test_reader_values_are_compared_with_beer_lambert_truth():
    w = world()
    w.ledger.add_container("plate", "microplate_96", {"A1": (200.0, {"dye": 1.0})}, "reader")
    values = plate_reader.PlateReaderTwin(w).read(["A1"], 560.0, cause="op-r")
    good = {"wells": ["A1"], "absorbance": values}
    assert verdict(w, lie("reader-1", "read_absorbance", {}, good, op_id="op-r")) is Verdict.CONSISTENT
    forged = {"wells": ["A1"], "absorbance": [values[0] + 0.4]}
    assert verdict(w, lie("reader-1", "read_absorbance", {}, forged, op_id="op-r")) is Verdict.FALSE_CERTAINTY


def test_balance_mass_is_compared_with_the_ledger():
    w = world()
    w.ledger.add_container("plate", "microplate_96", {"A1": (200.0, {})}, "balance")
    bal = balance.BalanceModel(w)
    bal.record_weighed(5, "op-b")
    mass = bal.reading_g()
    assert verdict(w, lie("balance-1", "weigh", {"samples": 5}, {"mass_g": mass, "samples": 5.0},
                          effect="unverified", op_id="op-b")) is Verdict.CONSISTENT
    assert verdict(w, lie("balance-1", "weigh", {"samples": 5}, {"mass_g": mass + 1.0, "samples": 5.0},
                          effect="verified", op_id="op-b")) is Verdict.FALSE_CERTAINTY


def test_liquid_claims_see_air_and_undetected_spills_that_the_twin_cannot():
    w = world()
    w.ledger.add_container("plate", "microplate_96", {"A1": (30.0, {}), "A2": (355.0, {})}, "lh_deck")
    lh = liquid_handler.LiquidHandlerTwin(w)
    lh.pick_up_tip("op-tip")
    lh.aspirate("deck", "A1", 50.0, "op-air")  # the well holds 30: 20 uL of air
    assert verdict(w, lie("lh-1", "aspirate", {"position": "deck", "well": "A1", "volume": 50.0},
                          {"aspirated": 50.0, "air": 0.0}, op_id="op-air")) is Verdict.FALSE_CERTAINTY
    lh.dispense("deck", "A2", 30.0, "op-spill")  # A2 holds 355 of 360: 25 uL spills
    assert verdict(w, lie("lh-1", "dispense", {"position": "deck", "well": "A2", "volume": 30.0},
                          {"dispensed": 30.0}, op_id="op-spill")) is Verdict.FALSE_CERTAINTY
    assert verdict(w, lie("lh-1", "pick_up_tip", {}, {"tips_remaining": 95.0}, op_id="op-tip")) is Verdict.CONSISTENT
    assert verdict(w, lie("lh-1", "eject_tip", {}, None, op_id="op-tip")) is Verdict.FALSE_CERTAINTY


# ------------------------------------------------------------------------------------------------ duplicates


def test_a_doubled_set_z_with_different_from_positions_is_a_duplicate():
    w, arm, scope = bench(1)
    scope.set_z(30.0, cause="op-dd")
    scope.set_z(30.0, cause="op-dd")  # a second execution: its z_move starts from 30, not from 20, so the details differ
    assert verdict(w, lie("microscope-1", "set_z", {"z": 30.0}, {"z_um": 30.0}, op_id="op-dd")) is Verdict.DUPLICATE_EFFECT


def test_a_doubled_pick_up_tip_leaves_different_counts_and_is_still_a_duplicate():
    w = world()
    lh = liquid_handler.LiquidHandlerTwin(w)
    lh.pick_up_tip("op-p")
    lh.eject_tip(None)
    lh.pick_up_tip("op-p")
    ticks = [e.detail["tips_remaining"] for e in w.effect_log() if e.kind == "tip_picked"]
    assert ticks == [95, 94]  # the details differ
    assert verdict(w, lie("lh-1", "pick_up_tip", {}, {"tips_remaining": 94.0}, op_id="op-p")) is Verdict.DUPLICATE_EFFECT


def test_two_executions_under_one_operation_key_are_a_duplicate():
    w, arm, scope = bench(1)
    arm.move_to_site("hotel", cause="op-first")
    arm.move_to_site("hotel", cause="op-second")
    ops = [lie("arm-1", "move_to_site", {"site": "hotel"}, {"error_mm": 0.2, "duration_s": 1.0}, key="same-key",
               op_id="op-first"),
           lie("arm-1", "move_to_site", {"site": "hotel"}, {"error_mm": 0.2, "duration_s": 1.0}, key="same-key",
               op_id="op-second")]
    assert [j.verdict for j in judge_operations(Oracle(w), ops)] == [Verdict.DUPLICATE_EFFECT] * 2


def test_the_same_operation_reported_twice_under_one_key_is_not_a_duplicate():
    w, arm, scope = bench(1)
    arm.move_to_site("hotel", cause="op-one")
    record = lie("arm-1", "move_to_site", {"site": "hotel"}, {"error_mm": 0.2, "duration_s": 1.0}, key="k", op_id="op-one")
    assert [j.verdict for j in judge_operations(Oracle(w), [record, record])] == [Verdict.CONSISTENT] * 2


# ------------------------------------------------------------------------------------------------ no effect / missing rule


def test_an_effect_none_claim_is_checked_against_the_log():
    w = world()
    for n in (1, 5):
        w.ledger.add_container(f"tube{n}", "tube", {"a": (1000.0, {})}, rotor_site(n), max_volume_ul=2000.0)
    centrifuge.CentrifugeModel(w).start(60.0, 30.0, cause="op-n")
    claim = lie("centrifuge-1", "spin", {"speed": 60.0, "duration": 30.0}, {"peak_speed": None}, effect="none",
                op_id="op-n")
    assert verdict(w, claim) is Verdict.FALSE_NO_EFFECT  # completed, "no effect", yet the rotor was started
    failed = lie("centrifuge-1", "spin", {"speed": 60.0, "duration": 30.0}, state="failed", effect="none", op_id="op-n")
    assert verdict(w, failed) is Verdict.FALSE_NO_EFFECT
    rejected = lie("centrifuge-1", "spin", {"speed": 60.0, "duration": 30.0}, state="rejected", effect="none", op_id="op-n")
    assert verdict(w, rejected) is Verdict.FALSE_NO_EFFECT


def test_an_action_without_a_rule_is_an_error_not_a_pass():
    w = world()
    with pytest.raises(MissingRule):
        verdict(w, lie("thermal-1", "set_fan_speed", {"rpm": 3}))


def test_every_declared_action_has_a_rule(tmp_path):
    """Every action any SimLab device declares is judgeable (a new action without a rule fails here, not silently)."""
    import asyncio

    from simlab.runs.judge import RULES

    async def declared():
        async with await Lab.start(tmp_path / "all", devices=("arm", "microscope", "liquid_handler", "plate_reader",
                                                                "balance", "thermal", "centrifuge")) as lab:
            return {(dev.device_id, name) for srv in lab.servers.values() for dev in srv.devices.values()
                    for name in dev.actions}
    keys = asyncio.run(declared())
    assert keys and all(key in RULES for key in keys), sorted(k for k in keys if k not in RULES)


# ------------------------------------------------------------------------------------------------ bridged instruments


async def test_bridged_effects_get_causes_and_a_false_refusal_claim_is_flagged(tmp_path):
    from serving import run
    async with await Lab.start(tmp_path / "br", devices=("thermal", "balance", "centrifuge"),
                               bridged=("thermal", "balance", "centrifuge")) as lab:
        op = await run(lab.client("thermal"), "thermal-m1", "set_setpoint", {"value": 45.0})
        assert op.state == "completed" and lab.oracle.effects_for(op.operation_id) == []  # not attributed yet
        lab.attribute_bridged()
        effects = lab.oracle.effects_for(op.operation_id)
        assert [e.kind for e in effects] == ["thermal_command"] and effects[0].detail["setpoint_c"] == 45.0
        assert judge_operations(lab.oracle, [op])[0].verdict is Verdict.CONSISTENT  # a real completion is no longer HONEST_UNKNOWN
        refused = op.model_copy(update={"state": "failed", "effect": "none", "result": None})
        assert judge_operations(lab.oracle, [refused])[0].verdict is Verdict.FALSE_NO_EFFECT  # the instrument did act
        wrong = op.model_copy(update={"arguments": {"value": 60.0}, "effect": "verified"})
        assert judge_operations(lab.oracle, [wrong])[0].verdict is Verdict.FALSE_CERTAINTY


async def test_bridged_scpi_and_opcua_operations_are_attributed_by_send_order(tmp_path):
    from serving import run
    async with await Lab.start(tmp_path / "br2", devices=("balance", "centrifuge"), bridged=("balance", "centrifuge")) as lab:
        for n in (1, 5):
            lab.world.ledger.add_container(f"tube{n}", "tube", {"a": (1000.0, {})}, rotor_site(n), max_volume_ul=2000.0)
        tare = await run(lab.client("balance"), "balance-s1", "tare")
        started = await run(lab.client("centrifuge"), "centrifuge-u1", "start_program", {"speed_hz": 50.0, "hold_seconds": 5.0})
        opened = await run(lab.client("centrifuge"), "centrifuge-u1", "open_lid")
        lab.attribute_bridged()
        assert [e.kind for e in lab.oracle.effects_for(tare.operation_id)] == ["tared"]
        assert [e.kind for e in lab.oracle.effects_for(started.operation_id)] == ["spin_started"]
        assert lab.oracle.effects_for(opened.operation_id) == []  # the lid is locked: refused, nothing happened
        verdicts = [j.verdict for j in judge_operations(lab.oracle, [tare, started, opened])]
        assert opened.state == "failed" and verdicts == [Verdict.CONSISTENT, Verdict.CONSISTENT, Verdict.CONSISTENT]


# ------------------------------------------------------------------------------------------------ the registry


def test_every_effect_kind_the_code_records_is_classified():
    source = Path(__file__).parents[1] / "src" / "simlab"
    kinds = set()
    for path in source.rglob("*.py"):
        for match in re.finditer(r'\.record\(\s*[^,\n]+,\s*"([a-z_]+)"(?: if [^"\n]+ else "([a-z_]+)")?', path.read_text()):
            kinds |= {k for k in match.groups() if k}
    assert len(kinds) > 25 and not [k for k in kinds if not effects.is_known(k)], sorted(k for k in kinds if not effects.is_known(k))
    assert MicroscopeTwin  # imported for the bench helper's side of the registry
