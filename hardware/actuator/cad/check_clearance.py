#!/usr/bin/env python3
"""Exact B-rep interference check of the assembled arm at many poses.

Every printed part and every servo envelope is placed by forward
kinematics; each pair of solids on *different* links is intersected with
OpenCASCADE and any overlap above ``TOL_MM3`` is reported.  Pairs that
mesh by design (pinion against the driven gear) are excluded and listed.

    python cad/check_clearance.py     # writes cad/out/clearance.json, exit 1 on interference
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build123d import Location, Part, Pos, Rot  # noqa: E402
from OCP.BRepGProp import BRepGProp  # noqa: E402
from OCP.GProp import GProp_GProps  # noqa: E402

from assembly import build_assembly  # noqa: E402
from parts import tool_button_presser as presser  # noqa: E402
from params import DEFAULT  # noqa: E402

TOL_MM3 = 1.0
ARM_LINKS = ["base", "turret", "upper_arm", "forearm", "wrist", "flange"]
TOOL_LINKS = {"gripper": ["gripper", "gripper_finger_a", "gripper_finger_b"],
              "knob_turner": ["knob_turner", "knob_output"],
              "button_presser": ["button_presser", "presser_plunger"],
              "slider_pusher": ["slider_pusher"]}
# Gear meshes are line contacts at the pitch point; their phase is not
# modelled, so these pairs are checked by the gear geometry instead.
EXCLUDE = {("turret:pinion", "upper_arm:upper_arm"), ("upper_arm:pinion", "forearm:forearm"),
           ("knob_turner:knob_servo_gear", "knob_output:knob_output_gear"),
           ("gripper:gripper_pinion", "gripper_finger_a:gripper_rack"),
           ("gripper:gripper_pinion", "gripper_finger_b:gripper_rack")}
PARENT = {"turret": "base", "upper_arm": "turret", "forearm": "upper_arm", "wrist": "forearm", "flange": "wrist",
          "gripper": "flange", "knob_turner": "flange", "button_presser": "flange", "slider_pusher": "flange",
          "gripper_finger_a": "gripper", "gripper_finger_b": "gripper", "knob_output": "knob_turner",
          "presser_plunger": "button_presser"}


def hops(a: str, b: str) -> int:
    """Tree distance between two links."""
    def chain(x: str) -> list[str]:
        out = [x]
        while out[-1] in PARENT:
            out.append(PARENT[out[-1]])
        return out
    ca, cb = chain(a), chain(b)
    common = next(x for x in ca if x in cb)
    return ca.index(common) + cb.index(common)
# Faces in contact by design (horn faces against pinions/brackets) are
# coplanar and give zero overlap volume, so they need no exclusion.


def volume(shape: Part | None) -> float:
    if shape is None or getattr(shape, "_wrapped", None) is None:
        return 0.0  # empty boolean result
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props)
    return props.Mass()


def link_solids(p) -> dict[str, list[tuple[str, Part]]]:
    asm = build_assembly(p)
    out: dict[str, list[tuple[str, Part]]] = {}
    built: dict[str, Part] = {}
    for d in asm.parts:
        if not d.in_sim:
            continue
        for link, loc in d.instances:
            if link in ("none", "tool_rack"):
                continue
            if d.name not in built:
                built[d.name] = d.build(p)
            out.setdefault(link, []).append((f"{link}:{d.name}", loc * built[d.name]))
    return out


def fk(p, q: dict[str, float], tool_q: dict[str, float]) -> dict[str, Location]:
    a = p.arm
    loc = {"base": Location()}
    loc["turret"] = Pos(0, 0, a.base_height) * Rot(Z=q.get("base_yaw", 0.0))
    loc["upper_arm"] = loc["turret"] * Pos(0, 0, a.shoulder_height) * Rot(Y=q.get("shoulder_pitch", 0.0))
    loc["forearm"] = loc["upper_arm"] * Pos(0, 0, a.l_upper) * Rot(Y=q.get("elbow_pitch", 0.0))
    loc["wrist"] = loc["forearm"] * Pos(0, 0, a.l_fore) * Rot(Y=q.get("wrist_pitch", 0.0))
    loc["flange"] = loc["wrist"] * Pos(0, 0, a.l_wrist) * Rot(Z=q.get("wrist_roll", 0.0))
    for tool in TOOL_LINKS:
        loc[tool] = loc["flange"]
    loc["gripper_finger_a"] = loc["gripper"] * Pos(0, tool_q.get("gripper", 0.0), 0)
    loc["gripper_finger_b"] = loc["gripper"] * Pos(0, -tool_q.get("gripper", 0.0), 0)
    loc["knob_output"] = loc["knob_turner"] * Rot(Z=tool_q.get("knob", 0.0))
    loc["presser_plunger"] = loc["button_presser"] * Pos(0, 0, tool_q.get("presser", 0.0))
    # The cam turns with the plunger: full lift at 0, half a turn at -stroke.
    zc = presser._z(p)["cam"]
    turn = 180.0 * -tool_q.get("presser", 0.0) / p.tools.presser_stroke
    loc["presser_cam"] = loc["button_presser"] * Pos(0, 0, zc) * Rot(X=turn) * Pos(0, 0, -zc)
    return loc


def poses(p) -> list[tuple[str, dict[str, float]]]:
    out = [("zero", {})]
    for j in p.arm.joints:
        out.append((f"{j.name}=lower", {j.name: j.lower_deg}))
        out.append((f"{j.name}=upper", {j.name: j.upper_deg}))
    out += [
        ("reach_forward", {"shoulder_pitch": 90.0, "elbow_pitch": 0.0, "wrist_pitch": 0.0}),
        ("table_pick_near", {"shoulder_pitch": 15.0, "elbow_pitch": 122.0, "wrist_pitch": 40.0}),
        ("table_pick_far", {"shoulder_pitch": 55.0, "elbow_pitch": 95.0, "wrist_pitch": 30.0}),
        ("folded_back", {"shoulder_pitch": -75.0, "elbow_pitch": 125.0, "wrist_pitch": -100.0}),
        ("wrist_curl", {"shoulder_pitch": 30.0, "elbow_pitch": 100.0, "wrist_pitch": 100.0}),
        ("wrist_curl_neg", {"shoulder_pitch": 30.0, "elbow_pitch": 100.0, "wrist_pitch": -100.0}),
    ]
    return out


def check(p, tool: str, tool_q: dict[str, float], solids, pose_list) -> list[dict]:
    links = ARM_LINKS + TOOL_LINKS[tool]
    hits = []
    for pose_name, q in pose_list:
        loc = fk(p, q, tool_q)
        placed = {lk: [(n, (loc["presser_cam"] if n.endswith(":presser_cam") else loc[lk]) * s)
                       for n, s in solids.get(lk, [])] for lk in links}
        boxes = {lk: [(n, s, s.bounding_box()) for n, s in v] for lk, v in placed.items()}
        for la, lb in itertools.combinations(links, 2):
            for (na, sa, ba), (nb, sb, bb) in itertools.product(boxes[la], boxes[lb]):
                if (na, nb) in EXCLUDE or (nb, na) in EXCLUDE:
                    continue
                if (ba.max.X < bb.min.X or bb.max.X < ba.min.X or ba.max.Y < bb.min.Y or bb.max.Y < ba.min.Y
                        or ba.max.Z < bb.min.Z or bb.max.Z < ba.min.Z):
                    continue
                v = volume(sa & sb)
                if v > TOL_MM3:
                    # Within two joints of each other a collision is a design
                    # defect; farther apart it is a workspace self-collision
                    # that motion planning must avoid (MJCF has the geometry).
                    kind = "defect" if hops(la, lb) <= 2 else "self_collision"
                    hits.append({"tool": tool, "pose": pose_name, "a": na, "b": nb, "overlap_mm3": round(v, 2),
                                 "kind": kind})
    return hits


def main() -> int:
    p = DEFAULT
    solids = link_solids(p)
    all_hits = []
    pose_list = poses(p)
    n_checks = 0
    for tool, tq_list in (("gripper", [{"gripper": 0.0}, {"gripper": p.tools.gripper_stroke}]),
                          ("knob_turner", [{"knob": 0.0}]),
                          ("button_presser", [{"presser": 0.0}, {"presser": -p.tools.presser_stroke}]),
                          ("slider_pusher", [{}])):
        for tq in tq_list:
            hits = check(p, tool, tq, solids, pose_list)
            n_checks += len(pose_list)
            for h in hits:
                h["tool_q"] = tq
                print(f"{h['kind'].upper():14s} {h['tool']:15s} {h['pose']:22s} {h['a']} <-> {h['b']}: {h['overlap_mm3']} mm3")
            all_hits += hits
    defects = [h for h in all_hits if h["kind"] == "defect"]
    report = {"tolerance_mm3": TOL_MM3, "poses": [n for n, _ in pose_list], "pose_tool_combinations": n_checks,
              "excluded_pairs": sorted(list(map(list, EXCLUDE))), "defects": defects,
              "self_collisions": [h for h in all_hits if h["kind"] != "defect"],
              "joint_limits_deg": {j.name: [j.lower_deg, j.upper_deg] for j in p.arm.joints}}
    (HERE / "out" / "clearance.json").write_text(json.dumps(report, indent=1))
    print(f"{n_checks} pose/tool combinations, {len(defects)} design defects, "
          f"{len(all_hits) - len(defects)} workspace self-collisions")
    return 1 if defects else 0


if __name__ == "__main__":
    sys.exit(main())
