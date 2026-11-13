#!/usr/bin/env python3
"""Static worst-case torque budget per joint, from the CAD mass model.

Worst case for every pitch joint: the arm fully outstretched horizontally
(shoulder 90 deg, elbow 0, wrist 0), rated end-effector load of 250 g
(tool included, ISO 9283 convention) with its centre of mass 50 mm beyond
the flange face.  Link masses and centres of mass come from
cad/out/assembly.json (CAD solids + purchased hardware).

Required servo torque  = joint torque / (ratio * efficiency) * 2  (2x margin)
Margin                 = servo stall torque / (joint torque / (ratio * eff))

Also reports the holding current estimate per servo (linear in torque
between idle and stall current) for supply sizing.

    python cad/torque_budget.py      # -> cad/out/torque_budget.json + markdown on stdout
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
G = 9.81
MARGIN_REQUIRED = 2.0


def main() -> int:
    asm = json.loads((HERE / "out" / "assembly.json").read_text())
    links = asm["links"]
    tree = {n["link"]: n for n in asm["tree"]}
    arm = asm["arm"]
    servo = asm["servo"]
    eff_gear = asm["gear"]["efficiency"]
    payload_kg = asm["payload"]["mass_g"] / 1000.0
    payload_off = asm["payload"]["offset_mm"] / 1000.0
    L1, L2, LW = arm["l_upper"] / 1000.0, arm["l_fore"] / 1000.0, arm["l_wrist"] / 1000.0

    # Distance of each link origin along the outstretched arm from each joint.
    origin_from = {
        "shoulder_pitch": {"upper_arm": 0.0, "forearm": L1, "wrist": L1 + L2, "flange": L1 + L2 + LW},
        "elbow_pitch": {"forearm": 0.0, "wrist": L2, "flange": L2 + LW},
        "wrist_pitch": {"wrist": 0.0, "flange": LW},
    }
    payload_from = {"shoulder_pitch": L1 + L2 + LW + payload_off, "elbow_pitch": L2 + LW + payload_off,
                    "wrist_pitch": LW + payload_off}
    rows = {}
    for jn, offsets in origin_from.items():
        contrib = []
        torque = 0.0
        for lk, off in offsets.items():
            m = links[lk]["mass_kg"]
            # With the arm horizontal the link z axis is horizontal; the link
            # centre-of-mass z coordinate is the lever arm along the arm.
            lever = off + links[lk]["com_m"][2]
            t = m * G * lever
            torque += t
            contrib.append({"link": lk, "mass_kg": m, "lever_m": lever, "torque_nm": t})
        t_pay = payload_kg * G * payload_from[jn]
        torque += t_pay
        contrib.append({"link": "payload (incl. tool)", "mass_kg": payload_kg, "lever_m": payload_from[jn], "torque_nm": t_pay})
        link_name = {"shoulder_pitch": "upper_arm", "elbow_pitch": "forearm", "wrist_pitch": "wrist"}[jn]
        ratio = tree[link_name]["ratio"]
        eff = eff_gear if ratio > 1.0 else 1.0
        servo_t = torque / (ratio * eff)
        margin = servo["stall_torque_nm"] / servo_t
        current = servo["idle_current_a"] + servo["stall_current_a"] * servo_t / servo["stall_torque_nm"]
        rows[jn] = {"joint_torque_nm": torque, "ratio": ratio, "efficiency": eff, "servo_torque_nm": servo_t,
                    "required_with_2x_nm": MARGIN_REQUIRED * servo_t, "stall_nm": servo["stall_torque_nm"],
                    "margin_vs_stall": margin, "rated_continuous_nm": servo["rated_torque_nm"],
                    "within_rated_continuous": servo_t <= servo["rated_torque_nm"],
                    "holding_current_a_est": current, "pass": margin >= MARGIN_REQUIRED, "contributions": contrib}
    # Yaw and roll carry no static gravity torque in any pose with the
    # payload on the roll axis; their budget is dynamic (stated in docs).
    for jn, link_name in (("base_yaw", "turret"), ("wrist_roll", "flange")):
        rows[jn] = {"joint_torque_nm": 0.0, "ratio": tree[link_name]["ratio"], "servo_torque_nm": 0.0,
                    "margin_vs_stall": None, "pass": True, "note": "no static gravity load; dynamic only"}
    total_hold_current = sum(r.get("holding_current_a_est", servo["idle_current_a"]) for r in rows.values())
    out = {"case": "outstretched horizontal, 250 g rated load (tool included) at 50 mm beyond flange",
           "reach_to_flange_m": L1 + L2 + LW, "joints": rows, "worst_case_holding_current_a_est": total_hold_current,
           "pass": all(r["pass"] for r in rows.values())}
    (HERE / "out" / "torque_budget.json").write_text(json.dumps(out, indent=1))
    print("| Joint | Static joint torque (N·m) | Ratio × η | Servo torque (N·m) | Required with 2× (N·m) | "
          "STS3215 stall (N·m) | Margin vs stall | Est. holding current (A) |")
    print("|---|---|---|---|---|---|---|---|")
    for jn in ("shoulder_pitch", "elbow_pitch", "wrist_pitch"):
        r = rows[jn]
        print(f"| {jn} | {r['joint_torque_nm']:.2f} | {r['ratio']:.0f} × {r['efficiency']:.2f} | {r['servo_torque_nm']:.2f} | "
              f"{r['required_with_2x_nm']:.2f} | {r['stall_nm']:.2f} | {r['margin_vs_stall']:.2f}× | "
              f"{r['holding_current_a_est']:.2f} |")
    print(f"\nWorst-case holding current, all joints: {total_hold_current:.2f} A (estimate)")
    print("PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
