"""Bench scene (validation plan §11 Task 3)."""

import numpy as np
import pytest

from simlab.scene import BENCH
from simlab.world import SceneParams, World

SITES = ("hotel", "microscope_stage", "reader", "balance", "lh_deck", "slide_rack", "arm_mount")
JOINTS = ("focus_coarse", "focus_fine", "stage_x_knob", "stage_y_knob")


def test_scene_has_every_named_object():
    w = World(BENCH, seed=1)
    for name in SITES:
        assert w.model.site(name).id >= 0
    for name in ("plate", "slide"):
        assert w.model.body(name).id >= 0
    for name in JOINTS:
        assert w.model.joint(name).id >= 0
    for name in ("overhead", "scope"):
        assert w.model.camera(name).id >= 0
    assert w.has_arm and w.model.joint("arm_Rotation").id >= 0  # the SO-ARM100, attached by reference


def test_plate_stays_at_hotel_with_no_command():
    w = World(BENCH, seed=1)
    w.step(2.0)
    plate = w.data.mocap_pos[w.body_index("plate")]
    assert np.linalg.norm(plate - w.site_pos("hotel")) < 1e-4  # 0.1 mm


def test_overhead_camera_renders_a_frame():
    w = World(BENCH, seed=1)
    frame = w.render("overhead", 480, 640)
    assert frame.shape == (480, 640, 3) and frame.mean() > 5


def test_scene_parameters_are_per_world_instance():
    a = World(BENCH, seed=1, params=SceneParams(backlash_rad=0.2, knob_friction_nm=0.5), attach_arm=False)
    b = World(BENCH, seed=1, attach_arm=False)
    assert a.knobs["focus_fine"].backlash_rad == 0.2 and b.knobs["focus_fine"].backlash_rad != 0.2
    assert a.model.dof_frictionloss[a.model.joint("focus_fine").dofadr[0]] == 0.5


def test_the_arm_model_is_a_parameter(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        World(BENCH, seed=1, arm_model=tmp_path / "no_arm.xml")
