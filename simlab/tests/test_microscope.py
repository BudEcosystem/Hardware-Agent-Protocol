"""Microscope twin (validation plan §11 Task 5)."""

import pytest

from lab_helpers import scope_lab, turn
from simlab.imaging import sharpness


def snap_at(scope, z):
    scope.set_z(z)
    return scope.snap()


def test_focus_curve_peaks_at_specimen_plane():
    w, scope = scope_lab(with_slide_on_stage=True, specimen_z_um=40.0)
    zs = [20.0 + 2.0 * i for i in range(21)]
    scores = [sharpness(snap_at(scope, z)) for z in zs]
    assert abs(zs[scores.index(max(scores))] - 40.0) <= 2.0
    assert max(scores) / min(scores) > 2.0  # the trial measured 2.3


def test_empty_stage_gives_no_focus_peak():
    w, scope = scope_lab(with_slide_on_stage=False)
    scores = [sharpness(snap_at(scope, z)) for z in (20.0, 40.0, 60.0)]
    assert max(scores) / (min(scores) + 1e-9) < 1.2


def test_knob_backlash_is_visible_at_the_stage():
    w, scope = scope_lab(backlash_rad=0.05, focus_um_per_rev=100.0)
    z0 = scope.true_z_um()
    turn(w, "focus_fine", +1.0)
    turn(w, "focus_fine", -1.0)
    assert abs((scope.true_z_um() - z0) - 100.0 * 0.05 / 6.283185) < 0.05


def test_manual_focus_turn_moves_the_true_z_by_the_calibrated_travel():
    w, scope = scope_lab(backlash_rad=0.0, focus_um_per_rev=100.0)
    z0 = scope.true_z_um()
    turn(w, "focus_fine", 6.283185307)  # one revolution
    assert abs(scope.true_z_um() - z0 - 100.0) < 1e-3
    assert abs(scope.motor_z_um() - 20.0) < 1e-9  # the motor encoder is blind to the knob


def test_motorized_z_takes_world_time_at_finite_speed():
    w, scope = scope_lab()
    t0 = w.time_s
    scope.set_z(120.0)
    assert 0.4 < w.time_s - t0 < 0.6  # 100 um at 200 um/s
    with pytest.raises(ValueError):
        scope.set_z(500.0)


def test_objective_changes_the_field_of_view_and_the_blur_scale():
    w, scope = scope_lab()
    scope.set_z(40.0)
    ten = scope.snap()
    scope.set_objective(3)
    forty = scope.snap()
    assert ten.shape == forty.shape == (256, 256) and (ten != forty).any()
    assert w.effect_log()[-1].detail["objective"] == 40


def test_every_capture_is_an_effect_with_true_axis_positions():
    w, scope = scope_lab()
    scope.set_z(33.0, cause="op-1")
    frame = scope.capture(cause="op-2")
    effect = w.effect_log()[-1]
    assert effect.kind == "image_captured" and effect.cause == "op-2"
    assert effect.detail["z_um"] == pytest.approx(33.0) and effect.detail["specimen_present"] is True
    assert scope.frames.get(frame.frame_id) is frame


def test_exposure_scales_the_signal():
    w, scope = scope_lab()
    scope.set_z(40.0)
    dim, bright = scope.snap(exposure_ms=10.0), scope.snap(exposure_ms=40.0)
    assert bright.mean() > 2.5 * dim.mean()
