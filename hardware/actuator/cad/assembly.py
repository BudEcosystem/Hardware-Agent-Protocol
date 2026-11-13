"""Assembly registry: every printed part, where each instance sits in which
link frame, and the purchased hardware that contributes mass.

``build.py`` uses it to export parts and compute link mass properties;
``sim/gen_mjcf.py`` consumes the JSON that ``build.py`` writes, so the MJCF
never re-derives geometry on its own.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from build123d import Location, Part, Pos, Rot

from common import box, cyl_y, cyl_z, servo_body, servo_lid
from params import BEARING_608, BEARING_624, BEARING_6806, Bearing, Params
from parts import arm, base, clamp, fixtures
from parts import tool_button_presser as presser
from parts import tool_gripper as gripper
from parts import tool_knob_turner as knob
from parts import tool_slider_pusher as pusher

DENSITY = {"PLA": 1.24, "PETG": 1.27, "TPU": 1.21, "servo": 1.0}  # g/cm^3 (servo: unused)


@dataclass
class PartDef:
    name: str
    build: Callable[[Params], Part]
    material: str
    instances: list[tuple[str, Location]]
    orientation: str  # recommended print orientation
    in_sim: bool = True
    printed: bool = True  # False: purchased-part envelope, visual only (mass is in hardware)

    @property
    def qty(self) -> int:
        return len(self.instances)


@dataclass
class HardwareMass:
    name: str
    link: str
    mass_g: float
    solid: Part  # uniform-density stand-in for COM/inertia, link frame
    note: str = ""


@dataclass
class Assembly:
    parts: list[PartDef] = field(default_factory=list)
    hardware: list[HardwareMass] = field(default_factory=list)


IDENTITY = Location()


def _bearing_solid_y(b: Bearing, y0: float, x: float, z: float) -> Part:
    return cyl_y(b.od / 2, y0, y0 + b.width, x, z) - cyl_y(b.bore / 2, y0 - 1, y0 + b.width + 1, x, z)


def _bearing_solid_z(b: Bearing, z0: float, x: float = 0.0, y: float = 0.0) -> Part:
    return cyl_z(b.od / 2, z0, z0 + b.width, x, y) - cyl_z(b.bore / 2, z0 - 1, z0 + b.width + 1, x, y)


def build_assembly(p: Params) -> Assembly:
    a = p.arm
    asm = Assembly()
    sh = a.shoulder_height
    L1 = a.l_upper

    servo_locs = {
        "yaw": ("base", base.yaw_servo_location(p)),
        "shoulder": ("turret", arm.geared_servo_location(p, sh)),
        "elbow": ("upper_arm", arm.geared_servo_location(p, L1)),
        "wrist_pitch": ("forearm", arm.wrist_servo_location(p)),
        "wrist_roll": ("wrist", arm.roll_servo_location(p)),
        "gripper": ("gripper", gripper.servo_location(p)),
        "knob": ("knob_turner", knob.servo_location(p)),
        "presser": ("button_presser", presser.servo_location(p)),
    }
    # Flange frame relative to the wrist frame: the roll servo frame sits at
    # (0, 0, l_wrist - floor - horn_face); the flange frame at l_wrist.
    # The wrist-roll servo body belongs to the wrist link; lids too.
    hx = a.link_depth / 2

    def clips(link: str, z_list: list[float]) -> list[tuple[str, Location]]:
        return [(link, Pos(-hx + 2.0, 0, z - 2.3)) for z in z_list]

    # Clip notches are cut by arm._beam every 40 mm from 20 mm above the hub.
    upper_clip_z = [arm.HUB_R - 2.0 + 20.0, arm.HUB_R - 2.0 + 60.0]
    fore_clip_z = upper_clip_z

    clamp_sx = clamp.screw_axis_x(p)
    _, _, _, z_low = clamp._frame(p)
    asm.parts += [
        PartDef("base_plate", base.base_plate, "PETG", [("base", IDENTITY)], "flat, bottom face down"),
        PartDef("base_shell", base.base_shell, "PETG", [("base", IDENTITY)], "deck down (upside down), supports in pod cutouts"),
        PartDef("pod_lid", base.pod_lid, "PLA", [("base", IDENTITY)], "flat, label recess up"),
        PartDef("clamp_body", clamp.clamp_body, "PETG", [("base", IDENTITY)], "on its side (y face down), 6 walls"),
        PartDef("clamp_pad", clamp.clamp_pad, "PETG", [("base", Pos(clamp_sx, 0, -30.0 - 6.0))], "pad face down"),
        PartDef("clamp_knob", clamp.clamp_knob, "PLA", [("base", Pos(clamp_sx, 0, z_low - clamp.JAW_T - 22.0))], "flat"),
        PartDef("turret", arm.turret, "PETG", [("turret", IDENTITY)], "disc down"),
        PartDef("pinion", arm.pinion, "PETG",
                [("turret", arm.pinion_location(p, sh)), ("upper_arm", arm.pinion_location(p, L1))],
                "horn face down, 100% infill"),
        PartDef("upper_arm", arm.upper_arm, "PETG", [("upper_arm", IDENTITY)], "on its side (+y face down), supports under clevis"),
        PartDef("forearm", arm.forearm, "PETG", [("forearm", IDENTITY)], "on its side (-y face down)"),
        PartDef("wrist_bracket", arm.wrist_bracket, "PETG", [("wrist", IDENTITY)], "bridge down"),
        PartDef("flange_arm", arm.flange_arm, "PETG", [("flange", IDENTITY)], "socket mouth up"),
        PartDef("servo_lid", servo_lid, "PLA",
                [(link, loc) for link, loc in servo_locs.values() if link != "base"] + [servo_locs["yaw"]],
                "flat"),
        PartDef("cable_clip", fixtures.cable_clip, "PETG", clips("upper_arm", upper_clip_z) + clips("forearm", fore_clip_z)
                + [("none", IDENTITY)] * 4, "flat"),
        # Gripper
        PartDef("gripper_body", gripper.gripper_body, "PETG", [("gripper", IDENTITY)], "plug down, supports under cradle overhang"),
        PartDef("gripper_pinion", gripper.gripper_pinion, "PETG", [("gripper", IDENTITY)], "flat, 100% infill"),
        PartDef("gripper_rack", gripper.gripper_rack, "PETG",
                [("gripper_finger_a", IDENTITY), ("gripper_finger_b", Rot(Z=180))], "teeth vertical, flat side down"),
        PartDef("gripper_finger", gripper.gripper_finger, "PETG",
                [("gripper_finger_a", IDENTITY), ("gripper_finger_b", Rot(Z=180))], "on the outer face"),
        # Knob turner
        PartDef("knob_body", knob.knob_body, "PETG", [("knob_turner", IDENTITY)], "plug down, supports under top plate"),
        PartDef("knob_servo_gear", knob.servo_gear, "PETG", [("knob_turner", IDENTITY)], "flat, 100% infill"),
        PartDef("knob_output_gear", knob.output_gear, "PETG", [("knob_output", IDENTITY)], "flat (hub down), 100% infill"),
        PartDef("knob_collet_hub", knob.collet_hub, "PETG", [("knob_output", IDENTITY)], "flat"),
        PartDef("knob_collet", knob.collet, "TPU", [("knob_output", IDENTITY)], "base down, TPU 95A"),
        PartDef("knob_magnet_cap", knob.magnet_cap, "PETG", [("knob_output", IDENTITY)], "magnet pocket up"),
        # Button presser
        PartDef("presser_body", presser.presser_body, "PETG", [("button_presser", IDENTITY)], "plug down"),
        PartDef("presser_cam", presser.cam, "PETG", [("button_presser", IDENTITY)], "flat, 100% infill"),
        PartDef("presser_plunger", presser.plunger, "PETG", [("presser_plunger", IDENTITY)], "follower down"),
        PartDef("presser_tip_cap", presser.tip_cap, "TPU", [("presser_plunger", IDENTITY)], "open end down, TPU 95A"),
        # Slider pusher
        PartDef("pusher_body", pusher.pusher_body, "PETG", [("slider_pusher", IDENTITY)], "plug down"),
        PartDef("pusher_pad", pusher.pusher_pad, "TPU", [("slider_pusher", IDENTITY)], "flat, TPU 95A"),
        # Fixtures
        PartDef("tool_rack", fixtures.tool_rack, "PETG", [("tool_rack", IDENTITY)], "on its back rail, supports under plate",
                in_sim=True),
        PartDef("tolerance_coupon", fixtures.tolerance_coupon, "PLA", [("none", IDENTITY)], "flat", in_sim=False),
        # Purchased-part envelope (not printed): STS3215 body + horn, for
        # visuals, collision proxies and the interference check.
        PartDef("ref_sts3215", servo_body, "servo", list(servo_locs.values()), "not printed", printed=False),
    ]

    # ---- purchased hardware that moves with a link (mass model) ----------
    for name, (link, loc) in servo_locs.items():
        asm.hardware.append(HardwareMass(f"STS3215 ({name})", link, p.servo.mass_g, loc * servo_body(p), "datasheet mass"))
    zb = base.deck_top(p) - BEARING_6806.width
    asm.hardware.append(HardwareMass("6806-2RS yaw bearing", "base", BEARING_6806.mass_g, _bearing_solid_z(BEARING_6806, zb)))
    for link, axis_z in (("turret", sh), ("upper_arm", L1)):
        for side in (+1, -1):
            _, outer = arm.cheek_y(side)
            y0 = outer - BEARING_608.width if side > 0 else outer
            asm.hardware.append(HardwareMass(f"608-2RS ({link})", link, BEARING_608.mass_g,
                                             _bearing_solid_y(BEARING_608, y0, 0.0, axis_z)))
        _, outer_m = arm.cheek_y(-1)
        asm.hardware.append(HardwareMass(f"624-2RS pinion support ({link})", link, BEARING_624.mass_g,
                                         _bearing_solid_y(BEARING_624, outer_m, 0.0, axis_z - p.gear.center_distance)))
    # M8 x 70 shoulder/elbow shafts with nyloc nut and washers (~38 g) move
    # with the distal hub.
    for link in ("upper_arm", "forearm"):
        asm.hardware.append(HardwareMass(f"M8x70 shaft + nut ({link})", link, 38.0, cyl_y(4.0, -32.0, 38.0), "ISO 4014 + ISO 10511"))
    asm.hardware.append(HardwareMass("624-2RS wrist idler", "forearm", BEARING_624.mass_g,
                                     _bearing_solid_y(BEARING_624, arm.IDLER_BOSS_Y[1] - BEARING_624.width, 0.0, a.l_fore)))
    asm.hardware.append(HardwareMass("pogo pins + wires", "flange", 4.0, cyl_z(14.0, -10.0, -6.0), "estimate"))
    asm.hardware.append(HardwareMass("M5 ball plunger + insert", "flange", 3.0, cyl_z(2.5, 2.0, 7.0, 24.0, 0.0), "estimate"))
    # Harness: 6-core tool cable + servo bus cable along the links (~25 g/m).
    for link, length in (("upper_arm", L1), ("forearm", a.l_fore)):
        asm.hardware.append(HardwareMass(f"harness ({link})", link, 0.025 * length, box(-hx - 1, -hx + 6, -3, 3, 20.0, length - 20.0),
                                         "estimate 25 g/m"))
    # Tools: contact PCB and screws.
    for link in ("gripper", "knob_turner", "button_presser", "slider_pusher"):
        asm.hardware.append(HardwareMass(f"tool contact PCB ({link})", link, 2.5, cyl_z(15.0, 0.0, 1.6), "1.6 mm FR4"))
    shaft_z0, shaft_z1 = knob.shaft_span(p)
    shaft_mass = 7.85 * math.pi * 0.4 ** 2 * (shaft_z1 - shaft_z0) / 10.0
    asm.hardware.append(HardwareMass("8 mm steel shaft", "knob_output", shaft_mass, cyl_z(4.0, shaft_z0, shaft_z1)))
    kz = knob._z(p)
    for z0 in (kz["base0"] + 1.0, kz["top0"]):
        asm.hardware.append(HardwareMass("608-2RS (knob shaft)", "knob_turner", BEARING_608.mass_g, _bearing_solid_z(BEARING_608, z0)))
    return asm


# Kinematic tree (parent, joint) for the MJCF generator.  Positions are in
# millimetres in the parent frame.
def kinematic_tree(p: Params) -> list[dict]:
    a = p.arm
    j = {jt.name: jt for jt in a.joints}
    t = p.tools
    return [
        {"link": "turret", "parent": "base", "pos": [0, 0, a.base_height], "joint": "base_yaw", "axis": [0, 0, 1],
         "range_deg": [j["base_yaw"].lower_deg, j["base_yaw"].upper_deg], "ratio": j["base_yaw"].ratio, "servo_id": j["base_yaw"].servo_id},
        {"link": "upper_arm", "parent": "turret", "pos": [0, 0, a.shoulder_height], "joint": "shoulder_pitch", "axis": [0, 1, 0],
         "range_deg": [j["shoulder_pitch"].lower_deg, j["shoulder_pitch"].upper_deg], "ratio": j["shoulder_pitch"].ratio,
         "servo_id": j["shoulder_pitch"].servo_id},
        {"link": "forearm", "parent": "upper_arm", "pos": [0, 0, a.l_upper], "joint": "elbow_pitch", "axis": [0, 1, 0],
         "range_deg": [j["elbow_pitch"].lower_deg, j["elbow_pitch"].upper_deg], "ratio": j["elbow_pitch"].ratio,
         "servo_id": j["elbow_pitch"].servo_id},
        {"link": "wrist", "parent": "forearm", "pos": [0, 0, a.l_fore], "joint": "wrist_pitch", "axis": [0, 1, 0],
         "range_deg": [j["wrist_pitch"].lower_deg, j["wrist_pitch"].upper_deg], "ratio": j["wrist_pitch"].ratio,
         "servo_id": j["wrist_pitch"].servo_id},
        {"link": "flange", "parent": "wrist", "pos": [0, 0, a.l_wrist], "joint": "wrist_roll", "axis": [0, 0, 1],
         "range_deg": [j["wrist_roll"].lower_deg, j["wrist_roll"].upper_deg], "ratio": j["wrist_roll"].ratio,
         "servo_id": j["wrist_roll"].servo_id},
        # Tool sub-trees (attached to "flange" by the generator, one at a time).
        {"link": "gripper_finger_a", "parent": "gripper", "pos": [0, 0, 0], "joint": "gripper_a", "type": "slide",
         "axis": [0, 1, 0], "range_mm": [0.0, t.gripper_stroke], "servo_id": 6},
        # Finger B's meshes/inertia are already turned 180 deg in the tool
        # frame, so its body is not rotated; it opens along -y.
        {"link": "gripper_finger_b", "parent": "gripper", "pos": [0, 0, 0], "joint": "gripper_b",
         "type": "slide", "axis": [0, -1, 0], "range_mm": [0.0, t.gripper_stroke], "servo_id": 6, "coupled_to": "gripper_a"},
        {"link": "knob_output", "parent": "knob_turner", "pos": [0, 0, 0], "joint": "knob_output", "type": "hinge",
         "axis": [0, 0, 1], "range_deg": [-3600.0, 3600.0], "servo_id": 7},
        {"link": "presser_plunger", "parent": "button_presser", "pos": [0, 0, 0], "joint": "presser", "type": "slide",
         "axis": [0, 0, 1], "range_mm": [-t.presser_stroke, 0.0], "servo_id": 8},
    ]


def tool_info(p: Params) -> dict[str, dict]:
    return {
        "gripper": {"tcp_mm": [0, 0, gripper.tcp_z(p)], "servo_id": 6, "tool_id": "gripper"},
        "knob_turner": {"tcp_mm": [0, 0, knob.tcp_z(p)], "servo_id": 7, "tool_id": "knob_turner",
                        "flexure_k_nm_per_rad": knob.flexure_stiffness_nm_per_rad(), "gear_ratio": knob.ratio()},
        "button_presser": {"tcp_mm": [0, 0, presser.tcp_z(p)], "servo_id": 8, "tool_id": "button_presser",
                           "stroke_mm": p.tools.presser_stroke},
        "slider_pusher": {"tcp_mm": [0, 0, pusher.tcp_z(p)], "servo_id": None, "tool_id": "slider_pusher"},
    }
