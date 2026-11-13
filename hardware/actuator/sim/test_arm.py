#!/usr/bin/env python3
"""Acceptance test for the generated BHMS Arm MJCF (MuJoCo >= 3.2).

1. Load every generated model.
2. Gravity hold: with the rated load (Controller ruling R13: a 250 g carried
   OBJECT, excluding the 159 g gripper, 70 mm beyond the flange) the
   position servos hold 5 poses; the joint error stays below HOLD_TOL_DEG
   and no actuator saturates.  MuJoCo's gravity torques are cross-checked
   against the static torque budget (cad/out/torque_budget.json).
2b. Speed limit: a full-range step command never drives a joint faster than
   the STS3215 no-load speed / ratio (<custom> max_speed_<joint>); gravity is
   switched off for this test (the limit is the servo's own drive speed).
2c. Keep-out: random poses inside the joint limits AND the coupled
   pitch limits (forearm: shoulder+elbow, tool: shoulder+elbow+wrist) produce no contact between the forearm/wrist/flange/tool
   and the static base/turret; a pose outside the coupled limits
   (wrist_curl) does, proving the collision pairs are live.
3. Pick and place a 50 g cube with the parallel gripper by contact
   (friction) grasp - no weld - from (0.24, 0) to (0.18, 0.16) m.

    python sim/test_arm.py          # writes sim/results/sim_results.json, exit 1 on failure
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
HOLD_TOL_DEG = 2.0
ASM = HERE.parent / "cad" / "out" / "assembly.json"
_PAY = json.loads(ASM.read_text())["payload"]
PAYLOAD_OBJECT_KG = _PAY["mass_g"] / 1000.0  # carried object, tool excluded (R13)
PAYLOAD_OFFSET_M = _PAY["offset_mm"] / 1000.0
SPEED_TOL = 1.03  # measured peak speed / datasheet limit
ARM_JOINTS = ["base_yaw", "shoulder_pitch", "elbow_pitch", "wrist_pitch", "wrist_roll"]
HOLD_POSES = {
    "horizontal_reach": {"shoulder_pitch": 90.0, "elbow_pitch": 0.0, "wrist_pitch": 0.0},
    "home": {"shoulder_pitch": 0.0, "elbow_pitch": 90.0, "wrist_pitch": 90.0},
    "forward_45": {"base_yaw": 60.0, "shoulder_pitch": 45.0, "elbow_pitch": 45.0, "wrist_pitch": 0.0},
    "folded_back": {"base_yaw": -90.0, "shoulder_pitch": -15.0, "elbow_pitch": 120.0, "wrist_pitch": -45.0},
    "rear_limit": {"base_yaw": 0.0, "shoulder_pitch": -20.0, "elbow_pitch": 60.0, "wrist_pitch": 0.0},
}


def tool_mass(model: mujoco.MjModel) -> float:
    names = ["gripper", "gripper_finger_a", "gripper_finger_b"]
    return float(sum(model.body_mass[model.body(n).id] for n in names))


def model_with_payload(path: Path) -> tuple[mujoco.MjModel, float]:
    """Add the 250 g carried object as a point mass PAYLOAD_OFFSET_M beyond
    the flange (centre of the finger pads); the tool mass is already in the model."""
    extra = PAYLOAD_OBJECT_KG
    spec = mujoco.MjSpec.from_file(str(path))
    flange = spec.body("flange")
    b = flange.add_body(name="payload", pos=[0.0, 0.0, PAYLOAD_OFFSET_M])
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
    out = {"object_kg": extra, "tool_mass_kg": tool_mass(model), "object_offset_m": PAYLOAD_OFFSET_M, "poses": {}}
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


def speed_limit(path: Path) -> dict:
    """Step every arm joint from one limit to the other; the peak joint speed
    must stay within the datasheet no-load speed / ratio."""
    model = mujoco.MjModel.from_xml_path(str(path))
    model.opt.gravity[:] = 0.0  # the limit is the servo's own drive speed; gravity assist is not part of the datasheet figure
    out = {"gravity": "off", "joints": {}}
    ok = True
    for jn in ARM_JOINTS:
        w_max = float(model.numeric(f"max_speed_{jn}").data[0])
        lo, hi = (float(x) for x in model.jnt_range[model.joint(jn).id])
        data = mujoco.MjData(model)
        data.qpos[model.joint(jn).qposadr[0]] = lo
        data.ctrl[model.actuator(jn).id] = lo
        mujoco.mj_forward(model, data)
        data.ctrl[model.actuator(jn).id] = hi
        peak = 0.0
        for _ in range(int(1.5 / model.opt.timestep)):
            mujoco.mj_step(model, data)
            peak = max(peak, abs(float(data.qvel[model.joint(jn).dofadr[0]])))
        good = peak <= SPEED_TOL * w_max
        ok &= good
        out["joints"][jn] = {"limit_rad_s": w_max, "peak_rad_s": peak, "pass": good}
    out["pass"] = ok
    return out


def keepout(path: Path, require_curl: bool = True, n: int = 400, seed: int = 7) -> dict:
    """Contact between keepout geoms (forearm..tool) and static geoms
    (base, turret) at random in-limit poses, inside and outside the coupled limit."""
    model = mujoco.MjModel.from_xml_path(str(path))
    limits = []
    for i in range(model.ntext):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_TEXT, i)
        if name.startswith("coupled_") and name.endswith("_joints"):
            adr, size = int(model.text_adr[i]), int(model.text_size[i])
            joints = bytes(model.text_data[adr:adr + size]).split(b"\0")[0].decode().split("+")
            lo, hi = (float(x) for x in model.numeric(name[: -len("_joints")] + "_deg").data)
            limits.append((name[: -len("_joints")], joints, lo, hi))
    assert limits, "no coupled limits in the model"
    cls_static = {g for g in range(model.ngeom) if (model.geom_contype[g] & 4) and model.geom_conaffinity[g] & 8}
    cls_keep = {g for g in range(model.ngeom) if model.geom_contype[g] & 8}
    rng = random.Random(seed)
    data = mujoco.MjData(model)
    inside_hits = outside_hits = inside_n = outside_n = 0
    for _ in range(n):
        q = {}
        for jn in ARM_JOINTS:
            lo, hi = (float(x) for x in model.jnt_range[model.joint(jn).id])
            q[jn] = rng.uniform(lo, hi)
        within = all(lo <= math.degrees(sum(q[j] for j in joints)) <= hi for _, joints, lo, hi in limits)
        for jn in ARM_JOINTS:
            data.qpos[model.joint(jn).qposadr[0]] = q[jn]
        mujoco.mj_forward(model, data)
        hit = any((c.geom1 in cls_static and c.geom2 in cls_keep) or (c.geom2 in cls_static and c.geom1 in cls_keep)
                  for c in data.contact[: data.ncon])
        if within:
            inside_n += 1
            inside_hits += hit
        else:
            outside_n += 1
            outside_hits += hit
    # Named forbidden pose from the CAD check (shoulder 30, elbow 100, wrist +100).
    data = mujoco.MjData(model)
    for jn, deg in (("shoulder_pitch", 30.0), ("elbow_pitch", 100.0), ("wrist_pitch", 100.0)):
        data.qpos[model.joint(jn).qposadr[0]] = math.radians(deg)
    mujoco.mj_forward(model, data)
    curl = any((c.geom1 in cls_static and c.geom2 in cls_keep) or (c.geom2 in cls_static and c.geom1 in cls_keep)
               for c in data.contact[: data.ncon])
    ok = inside_hits == 0 and (curl or not require_curl)
    return {"samples_inside_limit": inside_n, "contacts_inside_limit": inside_hits, "samples_outside_limit": outside_n,
            "contacts_outside_limit": outside_hits, "wrist_curl_30_100_100_contacts": bool(curl),
            "coupled_limits": {b: [lo, hi] for b, _, lo, hi in limits}, "pass": bool(ok)}


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
            jn: {"mujoco_nm": abs(hz[jn]),
                 "budget_nm": budget["cases"]["gripper + 250 g object (rated, R13)"]["joints"][jn]["joint_torque_nm"]}
            for jn in ("shoulder_pitch", "elbow_pitch", "wrist_pitch")}
    report["speed_limit"] = speed_limit(HERE / "bhms_arm.xml")
    report["keepout"] = keepout(HERE / "bhms_arm.xml")
    report["keepout_other_tools"] = {t: keepout(HERE / f"bhms_arm_{t}.xml", require_curl=False) for t in ("knob_turner", "button_presser", "slider_pusher")}
    report["pick_and_place"] = pick_and_place(HERE / "scene_pick.xml")
    report["pass"] = bool(report["gravity_hold"]["pass"] and report["pick_and_place"]["pass"] and report["speed_limit"]["pass"]
                          and report["keepout"]["pass"] and all(v["pass"] for v in report["keepout_other_tools"].values()))
    (RESULTS / "sim_results.json").write_text(json.dumps(report, indent=1))
    for name, r in report["gravity_hold"]["poses"].items():
        print(f"hold {name:17s} max err {r['max_abs_error_deg']:.3f} deg  max util "
              f"{max(r['utilization'].values()):.2f}  {'PASS' if r['pass'] else 'FAIL'}")
    for jn, r in report["speed_limit"]["joints"].items():
        print(f"speed {jn:15s} peak {r['peak_rad_s']:.2f} rad/s vs limit {r['limit_rad_s']:.2f}  {'PASS' if r['pass'] else 'FAIL'}")
    ko = report["keepout"]
    print(f"keepout gripper: {ko['contacts_inside_limit']}/{ko['samples_inside_limit']} contacts inside the coupled limit, "
          f"{ko['contacts_outside_limit']}/{ko['samples_outside_limit']} outside, wrist_curl contact {ko['wrist_curl_30_100_100_contacts']}  "
          f"{'PASS' if ko['pass'] else 'FAIL'}")
    for t, r in report["keepout_other_tools"].items():
        print(f"keepout {t}: {r['contacts_inside_limit']}/{r['samples_inside_limit']} inside, wrist_curl contact "
              f"{r['wrist_curl_30_100_100_contacts']}  {'PASS' if r['pass'] else 'FAIL'}")
    pp = report["pick_and_place"]
    print(f"pick&place xy err {pp['xy_error_m'] * 1000:.1f} mm, lift {pp['lift_z_m']:.3f} m, slip {pp['carry_slip_m'] * 1000:.1f} mm "
          f"{'PASS' if pp['pass'] else 'FAIL'}")
    print("PASS" if report["pass"] else "FAIL")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
