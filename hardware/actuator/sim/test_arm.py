#!/usr/bin/env python3
"""Acceptance test for the generated BHMS Arm MJCF (MuJoCo >= 3.2).

1. Load every generated model.
2. Gravity hold: with the rated end-effector load (250 g including the
   tool, at or beyond 50 mm from the flange) the position servos hold 4
   poses; the joint error stays below HOLD_TOL_DEG and no actuator
   saturates.  MuJoCo's gravity torques are cross-checked against the
   static torque budget (cad/out/torque_budget.json) where available.
3. Pick and place a 50 g cube with the parallel gripper by contact
   (friction) grasp - no weld - from (0.24, 0) to (0.18, 0.16) m.

    python sim/test_arm.py          # writes sim/results/sim_results.json, exit 1 on failure
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
HOLD_TOL_DEG = 2.0
PAYLOAD_TOTAL_KG = 0.250  # rated load at the flange, including the tool
PAYLOAD_OFFSET_M = 0.050
ARM_JOINTS = ["base_yaw", "shoulder_pitch", "elbow_pitch", "wrist_pitch", "wrist_roll"]
HOLD_POSES = {
    "horizontal_reach": {"shoulder_pitch": 90.0, "elbow_pitch": 0.0, "wrist_pitch": 0.0},
    "home": {"shoulder_pitch": 0.0, "elbow_pitch": 90.0, "wrist_pitch": 90.0},
    "forward_45": {"base_yaw": 60.0, "shoulder_pitch": 45.0, "elbow_pitch": 45.0, "wrist_pitch": 0.0},
    "folded_back": {"base_yaw": -90.0, "shoulder_pitch": -60.0, "elbow_pitch": 120.0, "wrist_pitch": -45.0},
}


def tool_mass(model: mujoco.MjModel) -> float:
    names = ["gripper", "gripper_finger_a", "gripper_finger_b"]
    return float(sum(model.body_mass[model.body(n).id] for n in names))


def model_with_payload(path: Path) -> tuple[mujoco.MjModel, float]:
    """Add a point load so the end-effector total is the rated payload,
    placed at max(TCP, 50 mm) along the tool axis (conservative)."""
    base = mujoco.MjModel.from_xml_path(str(path))
    extra = PAYLOAD_TOTAL_KG - tool_mass(base)
    tcp_z = float(base.site_pos[base.site("tcp").id][2])
    spec = mujoco.MjSpec.from_file(str(path))
    flange = spec.body("flange")
    b = flange.add_body(name="payload", pos=[0.0, 0.0, max(tcp_z, PAYLOAD_OFFSET_M)])
    b.add_geom(type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[0.015, 0, 0], mass=extra, contype=0, conaffinity=0,
               rgba=[0.9, 0.1, 0.1, 1])
    return spec.compile(), extra


def set_arm(model, data, q_deg: dict[str, float]) -> np.ndarray:
    q = np.zeros(len(ARM_JOINTS))
    for i, jn in enumerate(ARM_JOINTS):
        q[i] = math.radians(q_deg.get(jn, 0.0))
        data.qpos[model.joint(jn).qposadr[0]] = q[i]
        data.ctrl[model.actuator(jn).id] = q[i]
    return q


def gravity_hold(path: Path) -> dict:
    model, extra = model_with_payload(path)
    out = {"payload_added_kg": extra, "tool_mass_kg": PAYLOAD_TOTAL_KG - extra, "poses": {}}
    ok = True
    for name, pose in HOLD_POSES.items():
        data = mujoco.MjData(model)
        q = set_arm(model, data, pose)
        data.ctrl[model.actuator("gripper").id] = 0.0
        mujoco.mj_forward(model, data)
        gravity = {jn: float(data.qfrc_bias[model.joint(jn).dofadr[0]]) for jn in ARM_JOINTS}
        for _ in range(int(2.0 / model.opt.timestep)):
            mujoco.mj_step(model, data)
        err = {jn: math.degrees(float(data.qpos[model.joint(jn).qposadr[0]]) - q[i]) for i, jn in enumerate(ARM_JOINTS)}
        torque = {jn: float(data.actuator_force[model.actuator(jn).id]) for jn in ARM_JOINTS}
        limit = {jn: float(model.actuator_forcerange[model.actuator(jn).id][1]) for jn in ARM_JOINTS}
        util = {jn: abs(torque[jn]) / limit[jn] for jn in ARM_JOINTS}
        pose_ok = all(abs(e) < HOLD_TOL_DEG for e in err.values()) and all(u < 0.999 for u in util.values())
        ok &= pose_ok
        out["poses"][name] = {"target_deg": pose, "error_deg": err, "gravity_torque_nm": gravity, "actuator_torque_nm": torque,
                              "force_limit_nm": limit, "utilization": util, "max_abs_error_deg": max(abs(e) for e in err.values()),
                              "pass": pose_ok}
    out["pass"] = ok
    return out


# ---------------------------------------------------------------------------
# Pick and place
# ---------------------------------------------------------------------------


class Arm:
    def __init__(self, model: mujoco.MjModel, data: mujoco.MjData):
        self.m, self.d = model, data
        self.qadr = [model.joint(j).qposadr[0] for j in ARM_JOINTS]
        self.dadr = [model.joint(j).dofadr[0] for j in ARM_JOINTS]
        self.act = [model.actuator(j).id for j in ARM_JOINTS]
        self.lo = np.array([model.jnt_range[model.joint(j).id][0] for j in ARM_JOINTS])
        self.hi = np.array([model.jnt_range[model.joint(j).id][1] for j in ARM_JOINTS])
        self.tcp = model.site("tcp").id
        self.grip = model.actuator("gripper").id

    def fk(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        d = mujoco.MjData(self.m)
        d.qpos[:] = self.d.qpos
        d.qpos[self.qadr] = q
        mujoco.mj_kinematics(self.m, d)
        return d.site_xpos[self.tcp].copy(), d.site_xmat[self.tcp].reshape(3, 3).copy()

    def ik(self, target: np.ndarray, q0: np.ndarray, iters: int = 300) -> tuple[np.ndarray, float]:
        """Damped least squares on yaw/shoulder/elbow/wrist pitch for TCP
        position with the tool axis pointing straight down."""
        d = mujoco.MjData(self.m)
        d.qpos[:] = self.d.qpos
        q = q0.copy()
        jacp = np.zeros((3, self.m.nv))
        jacr = np.zeros((3, self.m.nv))
        idx = self.dadr[:4]
        err = np.inf
        for _ in range(iters):
            d.qpos[self.qadr] = q
            mujoco.mj_kinematics(self.m, d)
            mujoco.mj_comPos(self.m, d)
            pos = d.site_xpos[self.tcp]
            z = d.site_xmat[self.tcp].reshape(3, 3)[:, 2]
            e = np.concatenate([target - pos, 0.2 * np.cross(z, np.array([0.0, 0.0, -1.0]))])
            err = float(np.linalg.norm(e[:3]))
            if err < 1e-4 and np.linalg.norm(e[3:]) < 2e-3:
                break
            mujoco.mj_jacSite(self.m, d, jacp, jacr, self.tcp)
            J = np.vstack([jacp[:, idx], 0.2 * jacr[:, idx]])
            dq = J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), e)
            q[:4] = np.clip(q[:4] + np.clip(dq, -0.2, 0.2), self.lo[:4], self.hi[:4])
        return q, err

    def align_roll(self, q: np.ndarray) -> np.ndarray:
        """Choose the roll that puts the finger closing axis on a cube face normal."""
        best, best_cost = q.copy(), np.inf
        for r in np.radians(np.arange(-150.0, 150.1, 1.0)):
            qq = q.copy()
            qq[4] = r
            _, R = self.fk(qq)
            y = R[:, 1]
            ang = math.atan2(y[1], y[0])
            cost = abs(math.sin(2 * ang)) + 0.01 * abs(r)
            if cost < best_cost:
                best, best_cost = qq, cost
        return best


def run_segment(arm: Arm, q_from: np.ndarray, q_to: np.ndarray, grip_from: float, grip_to: float, seconds: float,
                log: list, cube_id: int, hold: float = 0.4) -> None:
    m, d = arm.m, arm.d
    n = int(seconds / m.opt.timestep)
    for k in range(n):
        s = (k + 1) / n
        s = 0.5 - 0.5 * math.cos(math.pi * s)  # smooth (cosine) blend
        d.ctrl[arm.act] = q_from + (q_to - q_from) * s
        d.ctrl[arm.grip] = grip_from + (grip_to - grip_from) * s
        mujoco.mj_step(m, d)
        if k % 25 == 0:
            log.append((d.time, d.xpos[cube_id].copy(), d.site_xpos[arm.tcp].copy()))
    for _ in range(int(hold / m.opt.timestep)):
        mujoco.mj_step(m, d)


def pick_and_place(path: Path) -> dict:
    model = mujoco.MjModel.from_xml_path(str(path))
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, model.key("home").id)
    mujoco.mj_forward(model, data)
    arm = Arm(model, data)
    cube = model.body("cube").id
    half = float(model.geom_size[model.geom("cube").id][0])
    place = model.site_pos[model.site("place_target").id].copy()
    start = data.xpos[cube].copy()
    q_home = data.qpos[arm.qadr].copy()
    open_w, closed = 0.022, -0.002  # finger opening (m); closed target squeezes the cube
    above = 0.07

    plan = {}
    q, e1 = arm.ik(start + [0, 0, above], q_home)
    plan["pre_grasp"] = arm.align_roll(q)
    q, e2 = arm.ik(start + [0, 0, 0.0], plan["pre_grasp"])
    q[4] = plan["pre_grasp"][4]
    plan["grasp"] = q
    q, e3 = arm.ik(place + [0, 0, above + half], plan["pre_grasp"])
    plan["pre_place"] = arm.align_roll(q)
    q, e4 = arm.ik(place + [0, 0, half + 0.001], plan["pre_place"])
    q[4] = plan["pre_place"][4]
    plan["place"] = q
    ik_err = max(e1, e2, e3, e4)

    log: list = []
    t0 = time.time()
    run_segment(arm, q_home, plan["pre_grasp"], 0.02, open_w, 1.5, log, cube)
    run_segment(arm, plan["pre_grasp"], plan["grasp"], open_w, open_w, 1.0, log, cube)
    run_segment(arm, plan["grasp"], plan["grasp"], open_w, closed, 0.6, log, cube, hold=0.5)
    grasp_width = float(data.qpos[model.joint("gripper_a").qposadr[0]] + data.qpos[model.joint("gripper_b").qposadr[0]])
    n_lift0 = len(log)
    run_segment(arm, plan["grasp"], plan["pre_grasp"], closed, closed, 1.0, log, cube)
    lift_z = float(data.xpos[cube][2])
    run_segment(arm, plan["pre_grasp"], plan["pre_place"], closed, closed, 2.0, log, cube)
    run_segment(arm, plan["pre_place"], plan["place"], closed, closed, 1.0, log, cube)
    n_carry1 = len(log)
    run_segment(arm, plan["place"], plan["place"], closed, open_w, 0.5, log, cube, hold=0.5)
    run_segment(arm, plan["place"], plan["pre_place"], open_w, open_w, 1.0, log, cube)
    wall = time.time() - t0

    final = data.xpos[cube].copy()
    carry = log[n_lift0:n_carry1]
    slip = max(float(np.linalg.norm(c - t)) for _, c, t in carry) - min(float(np.linalg.norm(c - t)) for _, c, t in carry)
    xy_err = float(np.linalg.norm(final[:2] - place[:2]))
    upright = float(abs(data.xquat[cube][0]))
    result = {
        "grasp": "contact (friction) grasp; no weld or attach constraint",
        "cube_mass_kg": float(model.body_mass[cube]),
        "start_m": start.tolist(),
        "place_target_m": place.tolist(),
        "final_m": final.tolist(),
        "xy_error_m": xy_err,
        "final_z_m": float(final[2]),
        "lift_z_m": lift_z,
        "grasp_width_m": grasp_width,
        "carry_slip_m": slip,
        "ik_max_pos_err_m": ik_err,
        "plan_deg": {k: np.degrees(v).round(2).tolist() for k, v in plan.items()},
        "sim_time_s": float(data.time),
        "wall_time_s": wall,
        "cube_quat_w": upright,
    }
    result["pass"] = bool(xy_err < 0.015 and abs(final[2] - half) < 0.004 and lift_z > start[2] + 0.04 and slip < 0.01
                          and ik_err < 1e-3)
    return result


def main() -> int:
    RESULTS.mkdir(exist_ok=True)
    report = {"mujoco": mujoco.__version__, "models": {}}
    for f in ["bhms_arm.xml", "bhms_arm_knob_turner.xml", "bhms_arm_button_presser.xml", "bhms_arm_slider_pusher.xml",
              "scene_pick.xml"]:
        m = mujoco.MjModel.from_xml_path(str(HERE / f))
        report["models"][f] = {"nbody": m.nbody, "njnt": m.njnt, "nu": m.nu, "total_mass_kg": float(sum(m.body_mass))}
    report["gravity_hold"] = gravity_hold(HERE / "bhms_arm.xml")
    budget_path = HERE.parent / "cad" / "out" / "torque_budget.json"
    if budget_path.exists():
        budget = json.loads(budget_path.read_text())
        hz = report["gravity_hold"]["poses"]["horizontal_reach"]["gravity_torque_nm"]
        report["torque_budget_crosscheck"] = {
            jn: {"mujoco_nm": abs(hz[jn]), "budget_nm": budget["joints"][jn]["joint_torque_nm"]}
            for jn in ("shoulder_pitch", "elbow_pitch", "wrist_pitch") if jn in budget.get("joints", {})}
    report["pick_and_place"] = pick_and_place(HERE / "scene_pick.xml")
    report["pass"] = bool(report["gravity_hold"]["pass"] and report["pick_and_place"]["pass"])
    (RESULTS / "sim_results.json").write_text(json.dumps(report, indent=1))
    for name, r in report["gravity_hold"]["poses"].items():
        print(f"hold {name:17s} max err {r['max_abs_error_deg']:.3f} deg  max util "
              f"{max(r['utilization'].values()):.2f}  {'PASS' if r['pass'] else 'FAIL'}")
    pp = report["pick_and_place"]
    print(f"pick&place xy err {pp['xy_error_m'] * 1000:.1f} mm, lift {pp['lift_z_m']:.3f} m, slip {pp['carry_slip_m'] * 1000:.1f} mm "
          f"{'PASS' if pp['pass'] else 'FAIL'}")
    print("PASS" if report["pass"] else "FAIL")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
