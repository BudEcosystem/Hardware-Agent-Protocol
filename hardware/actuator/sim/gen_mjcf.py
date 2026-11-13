#!/usr/bin/env python3
"""Generate the BHMS Arm MJCF from the CAD build output.

Reads ``cad/out/assembly.json`` (written by ``cad/build.py``): link masses,
centres of mass and full inertia tensors computed from the CAD solids
(plus purchased hardware), mesh placements, joint axes/limits and tool
TCPs.  Writes:

  sim/bhms_arm.xml                 arm + parallel gripper (default tool)
  sim/bhms_arm_<tool>.xml          arm + knob turner / button presser / slider pusher
  sim/scene_pick.xml               arm + gripper + table + 50 g cube (pick test)

Only the standard library is needed, so this runs anywhere.

Actuator model (STS3215, 12 V; see docs/design.md):
  * position servo per joint, joint-side force limit = enforced Max_Torque_Limit
    (fraction of stall, Joint.torque_limit) x stall torque x gear ratio x gear efficiency;
  * joint-side stiffness kp = kp_servo * ratio^2 * efficiency, critically
    damped (dampratio = 1);
  * armature = rotor inertia reflected through the 1:345 servo gearbox and
    the printed reduction (estimate);
  * frictionloss = gearbox friction reflected to the joint (estimate);
  * velocity limit: viscous joint damping = joint force limit / joint no-load
    speed (the DC-motor torque-speed line), so the joint cannot exceed
    no_load_speed / ratio.  No-load speed 4.71 rad/s (45 rpm, 0.222 s/60 deg
    at 12 V) is the vendor figure recorded in cad/params.py, ESTIMATE until
    measured on the physical servo.  The limits are also exported as <custom>
    numerics (max_speed_<joint>, rad/s).

Collision: arm geoms keep contype 2 / conaffinity 0 (table and cube only).
Extra "keepout" geoms (convex hulls of the CAD meshes of the forearm, wrist,
flange and the tool) have contype 8 and collide with the static base and
turret hulls (contype 4 / conaffinity 8), so tool-vs-base/turret
intersections are real contacts in simulation.  The coupled joint-sum limits
(Arm.coupled_limits) are exported as the custom numerics coupled_<name>_deg
([lo, hi]) with the joints of the sum in the custom text coupled_<name>_joints.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
ASM = HERE.parent / "cad" / "out" / "assembly.json"

KP_SERVO = 30.0  # N m/rad at the servo output (ESTIMATE; STS3215 P=32 default)
ROTOR_INERTIA = 1.0e-7  # kg m^2 (ESTIMATE for the STS3215 core motor)
SERVO_GEARBOX = 345.0  # STS3215 C018 internal reduction
SERVO_FRICTION = 0.03  # N m at the servo output (ESTIMATE)
GRIP_FORCE_LIMIT = 20.0  # N per finger, firmware torque limit (see docs)
GRIP_KP = 2000.0  # N/m (sim stiffness; force limit dominates)
TOOL_LINKS = {
    "gripper": ["gripper", "gripper_finger_a", "gripper_finger_b"],
    "knob_turner": ["knob_turner", "knob_output"],
    "button_presser": ["button_presser", "presser_plunger"],
    "slider_pusher": ["slider_pusher"],
}
RGBA = {"steel": "0.62 0.64 0.67 1", "PLA": "0.85 0.85 0.82 1", "PETG": "0.22 0.47 0.78 1", "TPU": "0.12 0.12 0.12 1", "servo": "0.06 0.06 0.06 1"}


def fmt(v) -> str:
    if isinstance(v, (list, tuple)):
        return " ".join(fmt(x) for x in v)
    return f"{v:.6g}"


CUBE_HALF = 0.0125
CUBE_MASS = 0.050
CUBE_POS = (0.24, 0.0, CUBE_HALF)
PLACE_POS = (0.18, 0.16, CUBE_HALF)


def joint_limits(servo: dict, gear: dict, ratio: float, torque_limit: float = 1.0) -> tuple[float, float]:
    """(joint-side force limit N m, joint no-load speed rad/s) for a servo behind a
    reduction of ``ratio`` (same efficiency for every pair).  ``torque_limit`` is the
    enforced Max_Torque_Limit as a fraction of stall: the force limit follows it."""
    eff = gear["efficiency"] if ratio > 1.0 else 1.0
    return servo["stall_torque_nm"] * torque_limit * ratio * eff, servo["no_load_speed_rad_s"] / ratio


def build(asm: dict, tool: str, scene: bool = False) -> ET.ElementTree:
    servo = asm["servo"]
    gear = asm["gear"]
    links = asm["links"]
    tree = {n["link"]: n for n in asm["tree"]}

    root = ET.Element("mujoco", model=f"bhms_arm_{tool}" + ("_pick_scene" if scene else ""))
    ET.SubElement(root, "compiler", angle="radian", meshdir="../cad/out", autolimits="true")
    ET.SubElement(root, "option", timestep="0.002", integrator="implicitfast", cone="elliptic", impratio="10")
    ET.SubElement(root, "size", memory="20M")
    vis = ET.SubElement(root, "visual")
    ET.SubElement(vis, "headlight", ambient="0.35 0.35 0.35", diffuse="0.7 0.7 0.7", specular="0.1 0.1 0.1")
    ET.SubElement(vis, "global", offwidth="960", offheight="720")

    default = ET.SubElement(root, "default")
    d = ET.SubElement(default, "default", attrib={"class": "bhms"})
    ET.SubElement(d, "geom", contype="2", conaffinity="0", group="3", density="0")
    dk = ET.SubElement(d, "default", attrib={"class": "keepout"})
    ET.SubElement(dk, "geom", type="mesh", contype="8", conaffinity="0", group="4", density="0")
    ds = ET.SubElement(d, "default", attrib={"class": "static"})
    ET.SubElement(ds, "geom", type="mesh", contype="4", conaffinity="8", group="4", density="0")
    dv = ET.SubElement(d, "default", attrib={"class": "visual"})
    ET.SubElement(dv, "geom", type="mesh", contype="0", conaffinity="0", group="2", density="0")
    dp = ET.SubElement(d, "default", attrib={"class": "pad"})
    ET.SubElement(dp, "geom", type="box", contype="2", conaffinity="0", group="3", friction="1.5 0.01 0.001",
                  condim="4", solref="0.004 1", solimp="0.95 0.99 0.001", priority="1", density="0",
                  rgba="0.9 0.3 0.2 0.5")

    asset = ET.SubElement(root, "asset")
    used_meshes = set()
    wanted_links = ["base", "turret", "upper_arm", "forearm", "wrist", "flange"] + TOOL_LINKS[tool]
    for lk in wanted_links:
        for m in links[lk]["meshes"]:
            used_meshes.add(m["mesh"])
    for name in sorted(used_meshes):
        ET.SubElement(asset, "mesh", name=name, file=f"{name}.stl", scale="0.001 0.001 0.001")
    for mat, rgba in RGBA.items():
        ET.SubElement(asset, "material", name=mat, rgba=rgba)

    world = ET.SubElement(root, "worldbody")
    bodies: dict[str, ET.Element] = {}
    if scene:
        ET.SubElement(asset, "texture", name="grid", type="2d", builtin="checker", width="512", height="512",
                      rgb1="0.78 0.78 0.75", rgb2="0.68 0.68 0.65")
        ET.SubElement(asset, "material", name="grid", texture="grid", texrepeat="10 10")
        ET.SubElement(world, "light", pos="0.3 -0.4 1.4", dir="-0.2 0.3 -1", diffuse="0.6 0.6 0.6")
        # World objects collide with each other and with arm geoms.
        ET.SubElement(world, "geom", name="table", type="plane", size="0.8 0.8 0.01", material="grid", contype="1",
                      conaffinity="3", friction="0.8 0.005 0.0001")
        cube = ET.SubElement(world, "body", name="cube", pos=fmt(list(CUBE_POS)))
        ET.SubElement(cube, "freejoint", name="cube")
        ET.SubElement(cube, "geom", name="cube", type="box", size=fmt([CUBE_HALF] * 3), mass=fmt(CUBE_MASS),
                      rgba="0.95 0.6 0.1 1", contype="1", conaffinity="3", friction="1.0 0.005 0.0001", condim="4")
        ET.SubElement(world, "site", name="place_target", type="cylinder", pos=fmt([PLACE_POS[0], PLACE_POS[1], 0.0005]),
                      size="0.016 0.0005", rgba="0.1 0.8 0.1 0.5")

    def add_link(parent: ET.Element, name: str, pos_mm, quat=None) -> ET.Element:
        attrs = {"name": name, "pos": fmt([x / 1000.0 for x in pos_mm]), "childclass": "bhms"}
        if quat is not None:
            attrs["quat"] = fmt(quat)
        b = ET.SubElement(parent, "body", attrib=attrs)
        info = links[name]
        ET.SubElement(b, "inertial", pos=fmt(info["com_m"]), mass=fmt(info["mass_kg"]),
                      fullinertia=fmt(info["fullinertia"]))
        for i, m in enumerate(info["meshes"]):
            ET.SubElement(b, "geom", attrib={"class": "visual", "name": f"{name}_{m['mesh']}_{i}", "mesh": m["mesh"],
                                             "pos": fmt(m["pos"]), "quat": fmt(m["quat"]), "material": m["material"]})
        bodies[name] = b
        return b

    speed_limits: dict[str, float] = {}
    base = add_link(world, "base", [0, 0, 0])
    # Base is bolted/clamped to the table: no free joint.
    chain = ["turret", "upper_arm", "forearm", "wrist", "flange"]
    parent = base
    for lk in chain:
        n = tree[lk]
        b = add_link(parent, lk, n["pos"])
        lo, hi = (math.radians(x) for x in n["range_deg"])
        ratio = n["ratio"]
        _, wmax = joint_limits(servo, gear, ratio)
        fmax_full = servo["stall_torque_nm"] * ratio * (gear["efficiency"] if ratio > 1.0 else 1.0)
        ET.SubElement(b, "joint", name=n["joint"], type="hinge", axis=fmt(n["axis"]), range=fmt([lo, hi]),
                      armature=fmt(ROTOR_INERTIA * (SERVO_GEARBOX * ratio) ** 2),
                      frictionloss=fmt(SERVO_FRICTION * ratio), damping=fmt(max(0.05, fmax_full / wmax)))  # DC line: stall torque / no-load speed
        speed_limits[n["joint"]] = wmax
        parent = b
    flange = bodies["flange"]
    ET.SubElement(flange, "site", name="flange", pos="0 0 0", size="0.004", rgba="0 1 0 1", group="1")
    # Collision proxies for the arm (convex hulls of the CAD meshes). Arm
    # geoms do not collide with each other (contype 2 / conaffinity 0);
    # self-clearance is verified in CAD by cad/check_clearance.py.
    for lk in ["upper_arm", "forearm", "wrist", "flange"]:
        for i, m in enumerate(links[lk]["meshes"]):
            if m["mesh"] in ("servo_lid", "cable_clip") or m["mesh"].startswith("pinion"):
                continue
            ET.SubElement(bodies[lk], "geom", type="mesh", name=f"{lk}_col_{i}", mesh=m["mesh"], pos=fmt(m["pos"]),
                          quat=fmt(m["quat"]))

    # Static hulls (base, turret) and keepout hulls (forearm ... tool).
    skip = ("servo_lid", "cable_clip")
    for lk in ("base", "turret"):
        for i, m in enumerate(links[lk]["meshes"]):
            if m["mesh"] in skip or m["mesh"].startswith("ref_"):
                continue
            ET.SubElement(bodies[lk], "geom", attrib={"class": "static", "name": f"{lk}_static_{i}", "mesh": m["mesh"],
                                                      "pos": fmt(m["pos"]), "quat": fmt(m["quat"])})
    for lk in ("forearm", "wrist", "flange"):
        for i, m in enumerate(links[lk]["meshes"]):
            if m["mesh"] in skip:
                continue
            ET.SubElement(bodies[lk], "geom", attrib={"class": "keepout", "name": f"{lk}_keepout_{i}", "mesh": m["mesh"],
                                                      "pos": fmt(m["pos"]), "quat": fmt(m["quat"])})

    # Tool
    tinfo = asm["tools"][tool]
    tb = add_link(flange, tool, [0, 0, 0])
    ET.SubElement(tb, "site", name="tcp", pos=fmt([x / 1000.0 for x in tinfo["tcp_mm"]]), size="0.004", rgba="1 0 0 1",
                  group="1")
    for i, m in enumerate(links[tool]["meshes"]):
        ET.SubElement(tb, "geom", type="mesh", name=f"{tool}_col_{i}", mesh=m["mesh"], pos=fmt(m["pos"]),
                      quat=fmt(m["quat"]))

    actuator = ET.Element("actuator")
    sensor = ET.Element("sensor")
    equality = ET.Element("equality")
    for lk in chain:
        n = tree[lk]
        ratio = n["ratio"]
        eff = gear["efficiency"] if ratio > 1.0 else 1.0
        fmax, _ = joint_limits(servo, gear, ratio, n.get("torque_limit", 1.0))
        kp = KP_SERVO * ratio ** 2 * eff
        lo, hi = (math.radians(x) for x in n["range_deg"])
        ET.SubElement(actuator, "position", name=n["joint"], joint=n["joint"], kp=fmt(kp), dampratio="1",
                      forcerange=fmt([-fmax, fmax]), ctrlrange=fmt([lo, hi]))
        ET.SubElement(sensor, "jointpos", name=f"{n['joint']}_pos", joint=n["joint"])
        ET.SubElement(sensor, "actuatorfrc", name=f"{n['joint']}_torque", actuator=n["joint"])

    if tool == "gripper":
        y_closed = 0.001  # finger inner face at the closed position (m)
        for lk in ("gripper_finger_a", "gripper_finger_b"):
            n = tree[lk]
            side = n["axis"][1]  # +1 for finger A, -1 for finger B (opening direction)
            b = add_link(tb, lk, n["pos"])
            lo, hi = (x / 1000.0 for x in n["range_mm"])
            ET.SubElement(b, "joint", name=n["joint"], type="slide", axis=fmt(n["axis"]), range=fmt([lo, hi]),
                          armature="0.05", damping="2", frictionloss="0.5")
            # Grip pad on the finger's inner face, over the ribbed area.
            tip = tinfo["tcp_mm"][2] / 1000.0 + 0.010
            ET.SubElement(b, "geom", attrib={"class": "pad", "name": f"{lk}_pad", "size": "0.006 0.0025 0.011",
                                             "pos": fmt([0.0, side * (y_closed + 0.0025), tip - 0.012])})
        ET.SubElement(equality, "joint", joint1="gripper_b", joint2="gripper_a", polycoef="0 1 0 0 0",
                      solref="0.005 1")
        ET.SubElement(actuator, "position", name="gripper", joint="gripper_a", kp=fmt(GRIP_KP), dampratio="1",
                      forcerange=fmt([-GRIP_FORCE_LIMIT, GRIP_FORCE_LIMIT]),
                      ctrlrange=fmt([x / 1000.0 for x in tree["gripper_finger_a"]["range_mm"]]))
        ET.SubElement(sensor, "jointpos", name="gripper_pos", joint="gripper_a")
        ET.SubElement(sensor, "actuatorfrc", name="gripper_force", actuator="gripper")
    elif tool == "knob_turner":
        n = tree["knob_output"]
        b = add_link(tb, "knob_output", n["pos"])
        k = tinfo["flexure_k_nm_per_rad"]
        # The flexure is modelled as the actuator stiffness: a position
        # servo behind a torsion spring of stiffness k.
        ET.SubElement(b, "joint", name="knob_output", type="hinge", axis="0 0 1", armature="0.0005", damping="0.002")
        ET.SubElement(actuator, "position", name="knob", joint="knob_output", kp=fmt(k), dampratio="0.7",
                      forcerange=fmt([-servo["stall_torque_nm"] * tinfo["gear_ratio"], servo["stall_torque_nm"] * tinfo["gear_ratio"]]))
        ET.SubElement(sensor, "jointpos", name="knob_angle", joint="knob_output")
        ET.SubElement(sensor, "actuatorfrc", name="knob_torque", actuator="knob")
    elif tool == "button_presser":
        n = tree["presser_plunger"]
        b = add_link(tb, "presser_plunger", n["pos"])
        lo, hi = (x / 1000.0 for x in n["range_mm"])
        ET.SubElement(b, "joint", name="presser", type="slide", axis="0 0 1", range=fmt([lo, hi]), damping="5",
                      armature="0.01")
        tcp = tinfo["tcp_mm"][2] / 1000.0
        ET.SubElement(b, "geom", type="cylinder", name="presser_tip", size="0.006 0.003", pos=fmt([0, 0, tcp - 0.003]),
                      friction="1 0.01 0.001", rgba="0.9 0.3 0.2 0.5")
        ET.SubElement(b, "site", name="fsr", type="cylinder", size="0.0065 0.0045", pos=fmt([0, 0, tcp - 0.003]),
                      group="1")
        ET.SubElement(actuator, "position", name="presser", joint="presser", kp="3000", dampratio="1",
                      forcerange="-30 30", ctrlrange=fmt([lo, hi]))
        ET.SubElement(sensor, "actuatorfrc", name="press_force", actuator="presser")
        ET.SubElement(sensor, "touch", name="fsr", site="fsr")

    for lk in TOOL_LINKS[tool]:
        for i, m in enumerate(links[lk]["meshes"]):
            ET.SubElement(bodies[lk], "geom", attrib={"class": "keepout", "name": f"{lk}_keepout_{i}", "mesh": m["mesh"],
                                                      "pos": fmt(m["pos"]), "quat": fmt(m["quat"])})
    custom = ET.SubElement(root, "custom")
    for jn, w in speed_limits.items():
        ET.SubElement(custom, "numeric", name=f"max_speed_{jn}", data=fmt(w))
    for c in asm["coupled_limits"]:
        ET.SubElement(custom, "numeric", name=f"coupled_{c['name']}_deg", data=fmt([c["lo_deg"], c["hi_deg"]]))
        ET.SubElement(custom, "text", name=f"coupled_{c['name']}_joints", data="+".join(c["joints"]))
    root.append(actuator)
    if len(equality):
        root.append(equality)
    root.append(sensor)
    # The cube body precedes the arm in <worldbody>, so its free joint comes
    # first in qpos.
    qpos = (list(CUBE_POS) + [1.0, 0.0, 0.0, 0.0] if scene else []) + home_qpos(tool)
    ET.SubElement(ET.SubElement(root, "keyframe"), "key", name="home", qpos=fmt(qpos), ctrl=fmt(home_ctrl(tool)))
    ET.indent(root, space=" ")
    return ET.ElementTree(root)


# Home = rest pose (E-stop/shutdown park, docs/design.md section 9): shoulder 30, elbow 90, wrist 45 deg.
# Forearm pitch 120, hairpin 135, tool pitch 165: inside every joint and coupled limit.
HOME_ARM = [0.0, math.radians(30.0), math.radians(90.0), math.radians(45.0), 0.0]


def home_qpos(tool: str) -> list[float]:
    extra = {"gripper": [0.02, 0.02], "knob_turner": [0.0], "button_presser": [0.0], "slider_pusher": []}[tool]
    return HOME_ARM + extra


def home_ctrl(tool: str) -> list[float]:
    extra = {"gripper": [0.02], "knob_turner": [0.0], "button_presser": [0.0], "slider_pusher": []}[tool]
    return HOME_ARM + extra


def main() -> int:
    if not ASM.exists():
        print(f"missing {ASM}; run cad/build.py first", file=sys.stderr)
        return 1
    asm = json.loads(ASM.read_text())
    for tool in TOOL_LINKS:
        out = HERE / ("bhms_arm.xml" if tool == "gripper" else f"bhms_arm_{tool}.xml")
        tree = build(asm, tool)
        with out.open("wb") as fh:
            fh.write(b"<!-- Generated by sim/gen_mjcf.py from cad/out/assembly.json. Do not edit. -->\n")
            tree.write(fh, encoding="utf-8")
        print(f"wrote {out.relative_to(HERE.parent)}")
    out = HERE / "scene_pick.xml"
    with out.open("wb") as fh:
        fh.write(b"<!-- Generated by sim/gen_mjcf.py from cad/out/assembly.json. Do not edit. -->\n")
        build(asm, "gripper", scene=True).write(fh, encoding="utf-8")
    print(f"wrote {out.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
