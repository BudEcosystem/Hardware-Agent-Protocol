"""Oracle (validation plan §11 Task 7)."""

from lab_helpers import carry_plate, inject_drop_during_next_carry, lab
from simlab.oracle import Claim, Oracle, Verdict


def dropped_world():
    w, arm = lab()
    inject_drop_during_next_carry(w)
    carry_plate(arm, to="microscope_stage", cause="op-9")
    return w


def test_oracle_flags_false_certainty():
    w = dropped_world()
    assert w.ledger.location("plate") == "lost"
    claim = Claim("op-9", "completed", "verified", lambda s: s["ledger"]["plate"] == "microscope_stage")
    assert Oracle(w).judge(claim) is Verdict.FALSE_CERTAINTY


def test_unknown_is_honest_when_truth_is_ambiguous_to_the_caller():
    claim = Claim("op-9", "outcome_unknown", "unverified", lambda s: True)
    assert Oracle(dropped_world()).judge(claim) is Verdict.HONEST_UNKNOWN


def test_rejected_claim_with_an_effect_is_flagged():
    w, arm = lab()
    arm.grip(True, cause="op-10")
    claim = Claim("op-10", "rejected_before_dispatch", "unverified", lambda s: True)
    assert Oracle(w).judge(claim) is Verdict.FALSE_NO_EFFECT


def test_two_effects_for_one_cause_is_a_duplicate():
    w, arm = lab()
    arm.grip(True, cause="op-11")
    arm.grip(True, cause="op-11")
    assert Oracle(w).judge(Claim("op-11", "completed", "verified", lambda s: True)) is Verdict.DUPLICATE_EFFECT


def test_a_true_verified_completion_is_consistent():
    w, arm = lab()
    carry_plate(arm, to="reader", cause="op-12")
    claim = Claim("op-12", "completed", "verified", lambda s: s["ledger"]["plate"] == "reader")
    assert Oracle(w).judge(claim) is Verdict.CONSISTENT


def test_a_failed_claim_that_says_no_effect_is_checked_against_the_log():
    w, arm = lab()
    assert Oracle(w).judge(Claim("op-13", "failed", "failed", lambda s: False)) is Verdict.CONSISTENT
    arm.move_to_site("hotel", cause="op-13")
    assert Oracle(w).judge(Claim("op-13", "failed", "failed", lambda s: False)) is Verdict.FALSE_NO_EFFECT


def test_effects_for_returns_the_operations_effects_in_order():
    w, arm = lab()
    arm.move_to_site("hotel", cause="op-14")
    kinds = [e.kind for e in Oracle(w).effects_for("op-14")]
    assert kinds == ["move_started", "move_finished"]


def test_unverified_completion_that_the_world_contradicts_is_an_honest_hedge():
    w = dropped_world()
    claim = Claim("op-9", "completed", "unverified", lambda s: s["ledger"]["plate"] == "microscope_stage")
    assert Oracle(w).judge(claim) is Verdict.HONEST_UNKNOWN
