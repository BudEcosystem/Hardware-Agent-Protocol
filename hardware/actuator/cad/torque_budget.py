#!/usr/bin/env python3
"""Static worst-case torque budget per joint, from the CAD mass model.

Worst case for every pitch joint: the arm fully outstretched horizontally
(shoulder 90 deg, elbow 0, wrist 0) carrying the rated object of 250 g
(Controller ruling R13: the object EXCLUDES the tool) with its centre of
mass ``payload_offset`` beyond the flange face, plus the mass of the
heaviest object-carrying tool (the gripper, fingers included) at its CAD
centre of mass.  Link masses and centres of mass come from
cad/out/assembly.json (CAD solids + purchased hardware).  The other tools
are checked with their own mass and no carried object.

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
    TOOL_PARTS = {"gripper": ["gripper", "gripper_finger_a", "gripper_finger_b"], "knob_turner": ["knob_turner", "knob_output"],
                  "button_presser": ["button_presser", "presser_plunger"], "slider_pusher": ["slider_pusher"]}
    tool_name = asm["payload"]["tool"]
    results = {}
    for case, (tool_n, obj_g) in {"gripper + 250 g object (rated, R13)": (tool_name, asm["payload"]["mass_g"]),
                                  "knob_turner, no object": ("knob_turner", 0.0),
                                  "button_presser, no object": ("button_presser", 0.0),
                                  "slider_pusher, no object": ("slider_pusher", 0.0)}.items():
        results[case] = _case(asm, links, tree, arm, servo, eff_gear, tool_n, TOOL_PARTS[tool_n], obj_g,
                              asm["payload"]["offset_mm"] / 1000.0)
    rated = results["gripper + 250 g object (rated, R13)"]
    (HERE / "out" / "torque_budget.json").write_text(json.dumps({"cases": results, "pass": all(r["pass"] for r in results.values())}, indent=1))
    for case, r in results.items():
        print(f"\n### {case}: tool {r['tool_mass_g']:.0f} g (CoM {r['tool_com_mm']:.0f} mm beyond flange), object {r['object_g']:.0f} g")
        print("| Joint | Static joint torque (N·m) | Ratio × η | Servo torque (N·m) | Required with 2× (N·m) | "
              "STS3215 stall (N·m) | Margin vs stall | Est. holding current (A) |")
        print("|---|---|---|---|---|---|---|---|")
        for jn in ("shoulder_pitch", "elbow_pitch", "wrist_pitch"):
            j = r["joints"][jn]
            print(f"| {jn} | {j['joint_torque_nm']:.2f} | {j['ratio']:.0f} × {j['efficiency']:.2f} | {j['servo_torque_nm']:.2f} | "
                  f"{j['required_with_2x_nm']:.2f} | {j['stall_nm']:.2f} | {j['margin_vs_stall']:.2f}× | {j['holding_current_a_est']:.2f} |")
        print(f"Worst-case holding current, all joints: {r['worst_case_holding_current_a_est']:.2f} A (estimate)")
        print("PASS" if r["pass"] else "FAIL")
    print("\nArithmetic, shoulder_pitch (rated case): T = sum m*g*lever;  servo torque = T / (ratio * eta);  margin = stall / servo torque")
    for c in rated["joints"]["shoulder_pitch"]["contributions"]:
        print(f"  {c['link']:28s} {c['mass_kg']*1000:7.1f} g x 9.81 x {c['lever_m']*1000:6.1f} mm = {c['torque_nm']:.3f} N·m")
    j = rated["joints"]["shoulder_pitch"]
    print(f"  total {j['joint_torque_nm']:.3f} N·m / ({j['ratio']:.0f} x {j['efficiency']:.2f}) = {j['servo_torque_nm']:.3f} N·m;"
          f" margin {servo['stall_torque_nm']:.2f} / {j['servo_torque_nm']:.3f} = {j['margin_vs_stall']:.2f}x")
    print("\nPASS" if all(r["pass"] for r in results.values()) else "\nFAIL")
    return 0 if all(r["pass"] for r in results.values()) else 1


def _case(asm, links, tree, arm, servo, eff_gear, tool_n, parts, obj_g, payload_off) -> dict:
    payload_kg = obj_g / 1000.0
    tool_kg = sum(links[x]["mass_kg"] for x in parts)
    tool_com = sum(links[x]["mass_kg"] * links[x]["com_m"][2] for x in parts) / tool_kg
    # The gripper fingers' CoM z is in the finger frame, which is the gripper frame.
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
        t_tool = tool_kg * G * (origin_from[jn]["flange"] + tool_com)
        t_pay = payload_kg * G * payload_from[jn]
        torque += t_tool + t_pay
        contrib.append({"link": f"tool ({tool_n})", "mass_kg": tool_kg, "lever_m": origin_from[jn]["flange"] + tool_com,
                        "torque_nm": t_tool})
        if payload_kg:
            contrib.append({"link": "carried object", "mass_kg": payload_kg, "lever_m": payload_from[jn], "torque_nm": t_pay})
        link_name = {"shoulder_pitch": "upper_arm", "elbow_pitch": "forearm", "wrist_pitch": "wrist"}[jn]
        ratio = tree[link_name]["ratio"]
        eff = eff_gear if ratio > 1.0 else 1.0  # same 0.92 printed-spur-pair estimate for both gear pairs
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
    return {"tool": tool_n, "tool_mass_g": tool_kg * 1000.0, "tool_com_mm": tool_com * 1000.0, "object_g": obj_g,
            "reach_to_flange_m": L1 + L2 + LW, "joints": rows, "worst_case_holding_current_a_est": total_hold_current,
            "pass": all(r["pass"] for r in rows.values())}


if __name__ == "__main__":
    sys.exit(main())
