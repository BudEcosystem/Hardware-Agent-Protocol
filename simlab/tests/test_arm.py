"""Arm twin (validation plan §11 Task 4)."""

import numpy as np
import pytest

from lab_helpers import lab
from simlab.twins.arm import SITES


def test_pick_and_place_updates_truth():
    w, arm = lab()
    assert arm.move_to_site("hotel", cause="op-4").reached
    arm.grip(True, cause="op-4")
    assert w.ledger.location("plate") == "in_gripper"
    assert arm.move_to_site("microscope_stage", cause="op-5").error_mm < 1.0
    arm.grip(False, cause="op-5")
    assert w.ledger.location("plate") == "microscope_stage"
    assert np.linalg.norm(w.data.mocap_pos[w.body_index("plate")] - w.site_pos("microscope_stage")) < 1e-9


def test_grip_away_from_plate_holds_nothing():
    w, arm = lab()
    arm.move_to_site("reader", cause="op-6")
    assert arm.grip(True, cause="op-6") is None
    assert w.ledger.location("plate") == "hotel"
    assert arm.gripper_width_mm() == 0.0  # closed on nothing: the jaw encoder says so


def test_held_object_travels_with_the_gripper_and_sets_the_jaw_width():
    w, arm = lab()
    arm.move_to_site("hotel", cause="a")
    arm.grip(True, cause="a")
    assert arm.gripper_width_mm() == 85.0
    arm.move_to_site("reader", cause="b")
    held = w.data.mocap_pos[w.body_index("plate")]
    assert np.linalg.norm(held - arm.tcp_position()) < 1e-6


@pytest.mark.parametrize("site", SITES)
def test_every_site_is_reached_within_a_millimetre(site):
    w, arm = lab()
    result = arm.move_to_site(site, cause="reach")
    assert result.reached and result.error_mm < 1.0
    assert 0.5 < result.duration_s < 10


def test_opening_the_jaw_away_from_every_site_drops_the_plate():
    w, arm = lab()
    arm.move_to_site("hotel", cause="a")
    arm.grip(True, cause="a")
    motion = arm.begin_move("reader", cause="b")
    w.step(motion.duration_s * 0.5)  # half way: over no site
    arm.begin_grip(False, cause="b")  # the jaw opens now, where the arm happens to be
    arm.finish_grip(False, cause="b")
    assert w.ledger.location("plate") == "lost"


def test_joint_state_reports_every_joint():
    w, arm = lab()
    state = arm.joint_state()
    assert set(state) == {"Rotation", "Pitch", "Elbow", "Wrist_Pitch", "Wrist_Roll", "Jaw"}


def test_a_second_move_while_moving_is_refused():
    w, arm = lab()
    arm.begin_move("hotel", cause="a")
    with pytest.raises(RuntimeError):
        arm.begin_move("reader", cause="b")


def test_stalled_joint_is_visible_as_a_missed_site():
    from simlab.faults import At, Fault
    w, arm = lab()
    w.faults.inject(Fault("Pitch", "joint_stall", At(0.0)))
    result = arm.move_to_site("reader", cause="stalled")
    assert not result.reached and result.error_mm > 20.0
