"""The spike: a Micro-Manager core (pymmcore-plus UniMMCore) backed by the world through Python devices."""

import numpy as np

from lab_helpers import scope_lab
from simlab import mmbackend
from simlab.imaging import sharpness


def test_standard_micromanager_calls_land_on_the_shared_world():
    w, scope = scope_lab(specimen_z_um=40.0)
    core = mmbackend.load_core(scope)
    assert core.getFocusDevice() == "Z" and core.getCameraDevice() == "Camera"
    core.setPosition(40.0)
    assert abs(scope.true_z_um() - 40.0) < 1e-6 and abs(core.getPosition() - 40.0) < 1e-6
    core.setXYPosition(900.0, 1100.0)
    assert np.allclose(core.getXYPosition(), (900.0, 1100.0))
    core.snapImage()
    sharp = core.getImage()
    assert sharp.shape == (256, 256) and sharp.dtype == np.uint16
    core.setPosition(75.0)
    core.snapImage()
    assert sharpness(sharp) > 2 * sharpness(core.getImage())  # defocus: the model is behind the API
    captured = [e for e in w.effect_log() if e.kind == "image_captured"]
    assert len(captured) == 2 and all(e.cause == "micro-manager" for e in captured)


def test_exposure_is_a_core_setting():
    w, scope = scope_lab()
    core = mmbackend.load_core(scope)
    core.setExposure(40.0)
    core.setPosition(40.0)
    core.snapImage()
    assert w.effect_log()[-1].detail["exposure_ms"] == 40.0
