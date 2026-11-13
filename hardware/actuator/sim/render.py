#!/usr/bin/env python3
"""Render the generated MJCF models to PNG (offscreen, EGL) for the docs.

    MUJOCO_GL=egl python sim/render.py      # -> docs/img/*.png
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco  # noqa: E402
from PIL import Image  # noqa: E402

HERE = Path(__file__).resolve().parent
IMG = HERE.parent / "docs" / "img"

VIEWS = [
    ("scene_pick.xml", "arm_home", "home", None, (0.10, 0.0, 0.20), 0.85, 135.0, -22.0),
    ("scene_pick.xml", "arm_grasp", None, {"shoulder_pitch": 41.02, "elbow_pitch": 78.48, "wrist_pitch": 60.51,
                                           "gripper_a": 0.0115, "gripper_b": 0.0115}, (0.18, 0.0, 0.10), 0.7, 120.0, -18.0),
    ("scene_pick.xml", "arm_reach", None, {"shoulder_pitch": 90.0, "elbow_pitch": 0.0, "wrist_pitch": 0.0, "gripper_a": 0.03,
                                            "gripper_b": 0.03}, (0.25, 0.0, 0.15), 0.9, 100.0, -12.0),
    ("bhms_arm.xml", "gripper_detail", "home", None, (0.17, 0.0, 0.12), 0.32, 50.0, -5.0),
    ("bhms_arm_knob_turner.xml", "knob_turner", "home", None, (0.17, 0.0, 0.12), 0.32, 50.0, -5.0),
    ("bhms_arm_button_presser.xml", "button_presser", "home", None, (0.17, 0.0, 0.12), 0.32, 50.0, -5.0),
    ("bhms_arm_slider_pusher.xml", "slider_pusher", "home", None, (0.17, 0.0, 0.12), 0.32, 50.0, -5.0),
]


def main() -> int:
    IMG.mkdir(parents=True, exist_ok=True)
    for xml, name, key, q, lookat, dist, az, el in VIEWS:
        model = mujoco.MjModel.from_xml_path(str(HERE / xml))
        model.vis.global_.offwidth = 960
        model.vis.global_.offheight = 720
        data = mujoco.MjData(model)
        if key is not None:
            mujoco.mj_resetDataKeyframe(model, data, model.key(key).id)
        if q:
            for jn, val in q.items():
                j = model.joint(jn)
                data.qpos[j.qposadr[0]] = math.radians(val) if model.jnt_type[j.id] == mujoco.mjtJoint.mjJNT_HINGE else val
        mujoco.mj_forward(model, data)
        cam = mujoco.MjvCamera()
        cam.lookat[:] = lookat
        cam.distance = dist
        cam.azimuth = az
        cam.elevation = el
        opt = mujoco.MjvOption()
        with mujoco.Renderer(model, 720, 960) as r:
            r.update_scene(data, cam, opt)
            Image.fromarray(r.render()).save(IMG / f"{name}.png")
        print(f"wrote docs/img/{name}.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
