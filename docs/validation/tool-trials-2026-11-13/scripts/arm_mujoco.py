"""Arm twin smoke test: load real robot models, hold a joint target, measure tracking, speed and rendering."""
import json, os, sys, time
os.environ.setdefault("MUJOCO_GL", "egl")
import numpy as np, mujoco
from robot_descriptions.loaders.mujoco import load_robot_description

out = {"mujoco": mujoco.__version__, "gl": os.environ["MUJOCO_GL"], "robots": {}}
for name in ["ur5e_mj_description", "panda_mj_description", "so_arm100_mj_description"]:
    r = {}
    try:
        m = load_robot_description(name); d = mujoco.MjData(m)
        r.update(nq=int(m.nq), nu=int(m.nu), timestep=float(m.opt.timestep))
        if m.nkey: mujoco.mj_resetDataKeyframe(m, d, 0)
        lo, hi = m.actuator_ctrlrange[:, 0], m.actuator_ctrlrange[:, 1]
        base = d.ctrl.copy() if m.nkey else (lo + hi) / 2
        target = np.clip(base + 0.15 * (hi - lo) * np.where(np.arange(m.nu) % 2 == 0, 1, -1), lo, hi)
        d.ctrl[:] = target
        steps = int(4.0 / m.opt.timestep); t0 = time.perf_counter()
        for _ in range(steps): mujoco.mj_step(m, d)
        wall = time.perf_counter() - t0
        r["realtime_factor"] = round(steps * m.opt.timestep / wall, 1)
        # joint-space tracking error for joint-attached actuators only
        errs = []
        for a in range(m.nu):
            if int(m.actuator_trntype[a]) == int(mujoco.mjtTrn.mjTRN_JOINT):
                j = int(m.actuator_trnid[a, 0])
                if int(m.jnt_type[j]) in (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)):
                    errs.append(abs(float(d.qpos[m.jnt_qposadr[j]]) - float(target[a])))
        r["max_tracking_error"] = round(float(max(errs)), 5) if errs else None
        r["contacts"] = int(d.ncon)
        try:
            with mujoco.Renderer(m, 240, 320) as ren:
                ren.update_scene(d); img = ren.render()
            r["render"] = {"shape": list(img.shape), "mean": round(float(img.mean()), 2)}
        except Exception as e:
            r["render_error"] = f"{type(e).__name__}: {e}"[:300]
        r["ok"] = True
    except Exception as e:
        r.update(ok=False, error=f"{type(e).__name__}: {e}"[:400])
    out["robots"][name] = r
print(json.dumps(out))
