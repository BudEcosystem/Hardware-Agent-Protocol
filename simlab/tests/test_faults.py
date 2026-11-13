"""Fault plane (validation plan §11 Task 6)."""

import numpy as np
import pytest

from lab_helpers import carry_plate, inject_drop_during_next_carry, lab, scope_lab
from simlab.faults import At, Fault, OnEvent


def test_drop_object_during_a_carry_loses_the_slide_and_the_scope_sees_an_empty_field():
    from simlab.twins.microscope import MicroscopeTwin
    w, arm = lab()
    scope = MicroscopeTwin(w)
    carry_plate(arm, to="microscope_stage", cause="control", source="slide_rack")
    assert w.ledger.location("slide") == "microscope_stage" and scope.capture().specimen_present is True

    w, arm = lab()
    scope = MicroscopeTwin(w)
    w.faults.inject(Fault("slide", "drop_object", OnEvent("move_started", "arm"),
                          {"require_location": "in_gripper", "delay_s": 0.3}))
    carry_plate(arm, to="microscope_stage", cause="op-1", source="slide_rack")
    assert w.ledger.location("slide") == "lost"
    assert w.data.mocap_pos[w.body_index("slide")][2] < -0.5  # on the floor
    assert scope.capture().specimen_present is False  # the dropped slide never arrived


def test_a_dropped_plate_is_lost_and_reads_back_in_the_gripper_width():
    w, arm = lab()
    inject_drop_during_next_carry(w)
    carry_plate(arm, to="reader", cause="op-1")
    assert w.ledger.location("plate") == "lost" and arm.gripper_width_mm() == 100.0


def test_the_drop_only_fires_while_the_object_is_carried():
    w, arm = lab()
    fault = inject_drop_during_next_carry(w)
    arm.move_to_site("reader", cause="empty-handed")  # a move without the plate does not trigger it
    assert w.ledger.location("plate") == "hotel" and fault in w.faults.snapshot()["pending"]


def test_stale_camera_returns_identical_frames_while_z_differs():
    w, scope = scope_lab()
    scope.set_z(30.0)
    scope.snap()
    fault = w.faults.inject(Fault("scope", "stale_camera", At(0.0)))
    first = scope.snap()
    scope.set_z(60.0)
    second = scope.snap()
    assert np.array_equal(first, second) and scope.true_z_um() == pytest.approx(60.0)
    assert w.effect_log()[-1].detail["stale"] is True
    w.faults.clear(fault)
    scope.set_z(40.0)
    assert not np.array_equal(first, scope.snap())


def test_manual_move_changes_true_z_and_records_an_effect_with_no_cause():
    w, scope = scope_lab(backlash_rad=0.0)
    z0 = scope.true_z_um()
    w.faults.inject(Fault("focus_fine", "manual_move", At(0.5), {"delta_rad": 1.0}))
    w.step(1.0)
    assert scope.true_z_um() != z0
    turned = [e for e in w.effect_log() if e.kind == "joint_turned"]
    assert len(turned) == 1 and turned[0].cause is None and turned[0].detail["joint"] == "focus_fine"


def test_knob_slip_makes_the_axis_move_less_than_the_knob():
    w, scope = scope_lab(backlash_rad=0.0, focus_um_per_rev=100.0)
    w.faults.inject(Fault("focus_fine", "knob_slip", At(0.0), {"slip_rad": 0.5}))
    w.step(0.01)
    w.turn_joint("focus_fine", 1.0, cause=None)
    assert scope.true_z_um() - 20.0 == pytest.approx(100.0 * 0.5 / 6.283185307, abs=1e-3)


def test_sensor_disconnect_blocks_capture_until_cleared():
    from simlab.twins.microscope import CameraUnavailable
    w, scope = scope_lab()
    fault = w.faults.inject(Fault("scope", "sensor_disconnect", At(0.0)))
    w.step(0.01)
    with pytest.raises(CameraUnavailable):
        scope.snap()
    w.faults.clear(fault)
    assert scope.snap().shape == (256, 256)


def test_injection_and_firing_are_effects_and_unknown_kinds_are_refused():
    w, _ = lab()
    w.faults.inject(Fault("plate", "drop_object", At(0.1)))
    w.step(0.2)
    assert [e.kind for e in w.effect_log() if e.device == "fault"] == ["fault_injected", "fault_fired"]
    with pytest.raises(ValueError):
        w.faults.inject(Fault("plate", "gremlins", OnEvent("x")))
