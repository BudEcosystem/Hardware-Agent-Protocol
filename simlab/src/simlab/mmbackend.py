"""The microscope twin behind the Micro-Manager core API (pymmcore-plus ``UniMMCore`` Python devices).

The plan's spike question (``simlab-microscope-face``): *can a pymmcore-plus Python camera and stage be backed by the
world?* Yes: ``UniMMCore.loadPyDevice`` takes Python device objects, and these three are thin shells over
``MicroscopeTwin``: a focus stage, an XY stage and a camera. The core calls are synchronous, so each call steps the world
synchronously for the time the motion takes (world time is still honest: the world clock advances by the travel time).
Everything an application does through the standard Micro-Manager API (``setPosition``, ``setXYPosition``, ``snapImage``,
``getImage``) lands on the shared world, and the BHMS Micro-Manager adapter (``simlab.adapters.micromanager``) bridges the
same core API into BHMS: twin, Micro-Manager, adapter, BHMS.

Thread-safety: call from the world's thread (the core's synchronous calls step the world directly).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
from pymmcore_plus.experimental.unicore import SimpleCameraDevice, StageDevice, XYStageDevice, UniMMCore

from simlab import imaging
from simlab.twins.microscope import MicroscopeTwin

FOCUS_LABEL, XY_LABEL, CAMERA_LABEL = "Z", "XY", "Camera"


class WorldFocusStage(StageDevice):
    """The focus axis as a Micro-Manager stage."""

    def __init__(self, scope: MicroscopeTwin) -> None:
        super().__init__()
        self.scope = scope

    def set_position_um(self, val: float) -> None:
        self.scope.set_z(val, cause="micro-manager")

    def get_position_um(self) -> float:
        return self.scope.true_z_um()

    def home(self) -> None:
        self.scope.set_z(0.0, cause="micro-manager")  # the park position

    def stop(self) -> None:
        self.scope.freeze()

    def set_origin(self) -> None:
        raise NotImplementedError("the focus axis has an absolute encoder; there is no origin to reset")


class WorldXYStage(XYStageDevice):
    """The stage as a Micro-Manager XY stage."""

    def __init__(self, scope: MicroscopeTwin) -> None:
        super().__init__()
        self.scope = scope

    def set_position_um(self, x: float, y: float) -> None:
        self.scope.set_xy(x, y, cause="micro-manager")

    def get_position_um(self) -> tuple[float, float]:
        return self.scope.true_xy_um()

    def home(self) -> None:
        self.scope.set_xy(1024.0, 1024.0, cause="micro-manager")  # the centre of the specimen field

    def stop(self) -> None:
        self.scope.freeze()

    def set_origin_x(self) -> None:
        raise NotImplementedError("the stage has absolute encoders; there is no origin to reset")

    def set_origin_y(self) -> None:
        raise NotImplementedError("the stage has absolute encoders; there is no origin to reset")


class WorldCamera(SimpleCameraDevice):
    """The camera: a frame of whatever is on the stage, rendered by the imaging model."""

    def __init__(self, scope: MicroscopeTwin) -> None:
        super().__init__()
        self.scope, self._exposure = scope, 20.0

    def get_exposure(self) -> float:
        return self._exposure

    def set_exposure(self, exposure: float) -> None:
        self._exposure = float(exposure)

    def dtype(self) -> Any:
        return np.uint16

    def sensor_shape(self) -> tuple[int, int]:
        return (imaging.FRAME_PX, imaging.FRAME_PX)

    def snap(self, buffer: np.ndarray) -> Mapping:
        frame = self.scope.capture(self._exposure, cause="micro-manager")
        buffer[:] = frame.pixels
        return {"frame_id": frame.frame_id, "z_um": frame.z_um}


def load_core(scope: MicroscopeTwin) -> UniMMCore:
    """A ``UniMMCore`` with the twin's focus stage, XY stage and camera loaded and selected."""
    core = UniMMCore()
    for label, device in ((FOCUS_LABEL, WorldFocusStage(scope)), (XY_LABEL, WorldXYStage(scope)),
                          (CAMERA_LABEL, WorldCamera(scope))):
        core.loadPyDevice(label, device)
        core.initializeDevice(label)
    core.setFocusDevice(FOCUS_LABEL)
    core.setXYStageDevice(XY_LABEL)
    core.setCameraDevice(CAMERA_LABEL)
    return core


__all__ = ["CAMERA_LABEL", "FOCUS_LABEL", "XY_LABEL", "WorldCamera", "WorldFocusStage", "WorldXYStage",
           "load_core"]
