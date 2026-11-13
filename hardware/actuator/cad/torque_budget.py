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
Margin                 = ENFORCED servo torque limit (Joint.torque_limit x stall) /
                         (joint torque / (ratio * eff))

Gear stress (printed/machined teeth) is checked at the enforced torque limit:
Lewis bending stress x AGMA thin-rim factor K_B must stay <= 0.5 x material yield.

Also reports the holding current estimate per servo (linear in torque
between idle and stall current) for supply sizing.

    python cad/torque_budget.py      # -> cad/out/torque_budget.json + markdown on stdout
"""

from __future__ import annotations

import json
import math
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
    gear_stress = gear_stress_table(asm, servo, tree)
    (HERE / "out" / "torque_budget.json").write_text(json.dumps(
        {"cases": results, "gear_stress": gear_stress, "pass": all(r["pass"] for r in results.values()) and
         all(g["pass"] for g in gear_stress)}, indent=1))
    for case, r in results.items():
        print(f"\n### {case}: tool {r['tool_mass_g']:.0f} g (CoM {r['tool_com_mm']:.0f} mm beyond flange), object {r['object_g']:.0f} g")
        print("| Joint | Static joint torque (N·m) | Ratio × η | Servo torque (N·m) | Required with 2× (N·m) | "
              "Enforced servo limit (N·m) | Margin vs enforced limit | Est. holding current (A) |")
        print("|---|---|---|---|---|---|---|---|")
        for jn in ("shoulder_pitch", "elbow_pitch", "wrist_pitch"):
            j = r["joints"][jn]
            print(f"| {jn} | {j['joint_torque_nm']:.2f} | {j['ratio']:.0f} × {j['efficiency']:.2f} | {j['servo_torque_nm']:.2f} | "
                  f"{j['required_with_2x_nm']:.2f} | {j['enforced_limit_nm']:.2f} | {j['margin_vs_stall']:.2f}× | {j['holding_current_a_est']:.2f} |")
        print(f"Worst-case holding current, all joints: {r['worst_case_holding_current_a_est']:.2f} A (estimate)")
        print("PASS" if r["pass"] else "FAIL")
    print("\nArithmetic, shoulder_pitch (rated case): T = sum m*g*lever;  servo torque = T / (ratio * eta);  margin = stall / servo torque")
    for c in rated["joints"]["shoulder_pitch"]["contributions"]:
        print(f"  {c['link']:28s} {c['mass_kg']*1000:7.1f} g x 9.81 x {c['lever_m']*1000:6.1f} mm = {c['torque_nm']:.3f} N·m")
    j = rated["joints"]["shoulder_pitch"]
    print(f"  total {j['joint_torque_nm']:.3f} N·m / ({j['ratio']:.0f} x {j['efficiency']:.2f}) = {j['servo_torque_nm']:.3f} N·m;"
          f" margin {j['enforced_limit_nm']:.3f} / {j['servo_torque_nm']:.3f} = {j['margin_vs_stall']:.2f}x (enforced limit)")
    stress_ok = print_gear_stress(gear_stress)
    ok = all(r["pass"] for r in results.values()) and stress_ok
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


# Shigley Table 14-2: Lewis form factor Y for 20 deg full-depth teeth.
LEWIS_Y = [(12, 0.245), (13, 0.261), (14, 0.277), (15, 0.290), (16, 0.296), (17, 0.303), (18, 0.309), (19, 0.314),
           (20, 0.322), (21, 0.328), (22, 0.331), (24, 0.337), (26, 0.346), (28, 0.353), (30, 0.359), (34, 0.371),
           (38, 0.384), (43, 0.397), (50, 0.409), (60, 0.422), (75, 0.435), (100, 0.447)]
# Yield strengths (MPa): PETG printed in-plane, low end of the 45-50 MPa range; machined C45 steel, normalised (handbook, estimate).
YIELD_MPA = {"PETG": 45.0, "steel": 300.0}
STRESS_FRACTION = 0.5  # allowed fraction of yield at the enforced torque limit


def lewis_y(teeth: int) -> float:
    for (n0, y0), (n1, y1) in zip(LEWIS_Y, LEWIS_Y[1:]):
        if n0 <= teeth <= n1:
            return y0 + (y1 - y0) * (teeth - n0) / (n1 - n0)
    raise ValueError(teeth)


def rim_factor(m_b: float) -> float:
    """AGMA 2001 thin-rim factor K_B (1 for backup ratio m_B >= 1.2)."""
    return 1.0 if m_b >= 1.2 else 1.6 * math.log(2.242 / m_b)


def gear_stress_table(asm, servo, tree) -> list[dict]:
    rims = asm["gear_rims"]
    rows = []
    for stage, link, pin_mat in (("shoulder", "upper_arm", "steel"), ("elbow", "forearm", "PETG")):
        r = rims[stage]
        limit_nm = servo["stall_torque_nm"] * tree[link].get("torque_limit", 1.0)
        m, b = r["module"], r["face_mm"]
        force = limit_nm / (m * r["pinion_teeth"] / 2 / 1000.0)  # N, tangential force at the pitch circle
        for part, teeth, m_b, mat in (("pinion", r["pinion_teeth"], r["pinion_m_B"], pin_mat),
                                      ("gear", r["gear_teeth"], r["gear_m_B"], "PETG")):
            sigma = force / (b * m * lewis_y(teeth))
            kb = rim_factor(m_b)
            eff = sigma * kb
            allowed = STRESS_FRACTION * YIELD_MPA[mat]
            rows.append({"stage": stage, "part": part, "material": mat, "teeth": teeth, "limit_nm": limit_nm, "force_n": force,
                         "lewis_y": lewis_y(teeth), "m_B": m_b, "K_B": kb, "sigma_lewis_mpa": sigma, "sigma_eff_mpa": eff,
                         "yield_mpa": YIELD_MPA[mat], "allowed_mpa": allowed, "fraction_of_yield": eff / YIELD_MPA[mat],
                         "pass": eff <= allowed})
    return rows


def print_gear_stress(rows) -> bool:
    print("\n### Gear stress at the enforced torque limit (Lewis x thin-rim factor <= 0.5 x yield)")
    print("| Stage | Part | Material | Teeth | Limit (N·m) | F (N) | Y | m_B | K_B | σ Lewis (MPa) | σ × K_B (MPa) | Yield (MPa) | σ/yield |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for g in rows:
        print(f"| {g['stage']} | {g['part']} | {g['material']} | {g['teeth']} | {g['limit_nm']:.3f} | {g['force_n']:.1f} | {g['lewis_y']:.3f} | "
              f"{g['m_B']:.2f} | {g['K_B']:.2f} | {g['sigma_lewis_mpa']:.1f} | {g['sigma_eff_mpa']:.1f} | {g['yield_mpa']:.0f} | "
              f"{g['fraction_of_yield']:.2f} {'ok' if g['pass'] else 'FAIL'} |")
    return all(g["pass"] for g in rows)


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
        limit_nm = servo["stall_torque_nm"] * tree[link_name].get("torque_limit", 1.0)
        margin = limit_nm / servo_t
        current = servo["idle_current_a"] + servo["stall_current_a"] * servo_t / servo["stall_torque_nm"]
        rows[jn] = {"joint_torque_nm": torque, "ratio": ratio, "efficiency": eff, "servo_torque_nm": servo_t,
                    "required_with_2x_nm": MARGIN_REQUIRED * servo_t, "stall_nm": servo["stall_torque_nm"], "enforced_limit_nm": limit_nm,
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
