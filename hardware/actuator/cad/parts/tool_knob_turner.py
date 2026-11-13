"""Knob turner: a compliant TPU collet on an 8 mm steel shaft, driven by an
STS3215 (bus ID 7) through a 20:40 module-1.5 spur pair whose driven gear
couples to the shaft through a printed spiral flexure (series-elastic
element).  A diametric magnet on the shaft end faces an AS5600 on the tool
contact PCB, so the output angle is measured directly:

    flexure deflection = servo_angle / ratio - AS5600 angle
    output torque     ~= k_flexure * deflection

Tool frame (see tool_interface).  The shaft runs on two 608-2RS bearings.
"""

from __future__ import annotations

import math

from build123d import Location, Part, Pos, Rot

from common import (
    CLEARANCE_D,
    HEAD_D,
    INSERT_HOLE_D,
    bolt_circle,
    box,
    cyl_x,
    cyl_z,
    horn_bolt_holes,
    horn_face_z,
    prism_xy,
    servo_cradle,
    spur_gear_profile,
    union,
)
from params import BEARING_608, Params
from parts.tool_interface import collar_top, tool_plug, wire_channel

MODULE = 1.5
SERVO_TEETH = 20
OUTPUT_TEETH = 40
GEAR_W = 6.0
BASE_T = 3.5
TOP_T = 8.0
SHAFT_D = 8.0
PILLARS = [(27.0, 27.0), (27.0, -27.0), (-12.0, 35.0), (-12.0, -35.0)]
PILLAR_R = 3.5


def centre_distance() -> float:
    return MODULE * (SERVO_TEETH + OUTPUT_TEETH) / 2


def ratio() -> float:
    return OUTPUT_TEETH / SERVO_TEETH


def _z(p: Params) -> dict[str, float]:
    ct = collar_top(p)
    zs = ct + BASE_T + p.servo.height + p.printer.fit_clearance + 2.6
    zh = zs + horn_face_z(p)
    top0 = zh + GEAR_W + 0.7
    return {
        "base0": ct,
        "base1": ct + BASE_T,
        "servo": zs,
        "gear0": zh,
        "gear1": zh + GEAR_W,
        "top0": top0,
        "top1": top0 + TOP_T,
        "hub0": top0 + TOP_T + 0.5,
        "hub1": top0 + TOP_T + 6.5,
        "collet0": top0 + TOP_T + 6.5,
        "collet1": top0 + TOP_T + 6.5 + 24.0,
        "magnet0": p.flange.contact_pcb_t + 1.5 + p.tools.magnet_to_sensor_gap,  # SOIC-8 body 1.5 mm
    }


def servo_location(p: Params) -> Location:
    """Servo frame -> tool: output +z at x = -centre_distance, body along -y,
    cradle lid toward -x."""
    return Pos(-centre_distance(), 0, _z(p)["servo"]) * Rot(Z=90)


def shaft_span(p: Params) -> tuple[float, float]:
    z = _z(p)
    return z["magnet0"] + p.tools.magnet_h + 2.0, z["hub1"]


def tcp_z(p: Params) -> float:
    """TCP at the collet mouth (knob face contact)."""
    return _z(p)["collet1"]


def knob_body(p: Params) -> Part:
    z = _z(p)
    plug = tool_plug(p)
    solid, cut = servo_cradle(p)
    loc = servo_location(p)
    cradle = loc * solid
    cb = cradle.bounding_box()
    base = box(min(cb.min.X, -30.0), 31.0, -38.5, 38.5, z["base0"] - 0.01, z["base1"])
    boss = cyl_z(BEARING_608.od / 2 + 3.0, z["base1"] - 0.01, z["base0"] + BEARING_608.width + 1.0)
    pillars = union([cyl_z(PILLAR_R, z["base1"] - 0.01, z["top0"] + 0.01, x, y) for x, y in PILLARS])
    top = box(-16.0, 31.0, -38.5, 38.5, z["top0"], z["top1"])
    body = plug + base + boss + cradle + pillars + top
    body -= loc * cut
    # Lower 608 (seated from above, lip below), upper 608 (seated from below).
    b = BEARING_608
    body -= cyl_z(b.od / 2 + p.printer.press_fit, z["base0"] + 1.0, z["base0"] + 1.0 + b.width + 0.01)
    body -= cyl_z(6.0, z["base0"] - 3.0, z["base0"] + 1.01)
    body -= cyl_z(b.od / 2 + p.printer.press_fit, z["top0"] - 0.01, z["top0"] + b.width)
    body -= cyl_z(6.0, z["top0"] + b.width - 0.01, z["top1"] + 0.01)
    # Gear running clearance (servo gear + output gear) below the top plate.
    body -= cyl_z(MODULE * (OUTPUT_TEETH / 2 + 1) + 1.0, z["gear0"] - 0.5, z["top0"] + 0.01)
    body -= cyl_z(MODULE * (SERVO_TEETH / 2 + 1) + 1.0, z["servo"] + 2.0, z["top0"] + 0.01, x=-centre_distance())
    body -= wire_channel(p, -30.0)
    return body


def servo_gear(p: Params) -> Part:
    z = _z(p)
    g = Pos(-centre_distance(), 0, z["gear0"]) * prism_xy(spur_gear_profile(MODULE, SERVO_TEETH, 20.0, 0.12), 0.0, GEAR_W)
    g -= Pos(-centre_distance(), 0, z["gear0"]) * horn_bolt_holes(p, -0.01, GEAR_W + 0.01)
    return g


def _spiral_arm(r0: float, r1: float, a0_deg: float, sweep_deg: float, width: float, n: int = 40) -> list[tuple[float, float]]:
    """Outline of an Archimedean spiral arm of constant width."""
    left, right = [], []
    for i in range(n + 1):
        t = i / n
        r = r0 + (r1 - r0) * t
        a = math.radians(a0_deg + sweep_deg * t)
        # Tangent of the centreline, then the in-plane normal.
        dr = (r1 - r0)
        da = math.radians(sweep_deg)
        tx = dr * math.cos(a) - r * da * math.sin(a)
        ty = dr * math.sin(a) + r * da * math.cos(a)
        L = math.hypot(tx, ty)
        nx, ny = -ty / L, tx / L
        cx, cy = r * math.cos(a), r * math.sin(a)
        left.append((cx + nx * width / 2, cy + ny * width / 2))
        right.append((cx - nx * width / 2, cy - ny * width / 2))
    return left + list(reversed(right))


FLEX_HUB_R = 7.0
FLEX_RING_R = 24.0
FLEX_ARM_W = 1.6
FLEX_ARMS = 3
FLEX_SWEEP = 120.0


def flexure_stiffness_nm_per_rad(e_mpa: float = 2000.0) -> float:
    """Torsional stiffness estimate of the spiral flexure (PETG, E~2 GPa):
    k = n E I / l, I = t w^3 / 12, l = arc length of one arm."""
    r0, r1 = FLEX_HUB_R + 1.0, FLEX_RING_R - 0.5
    n = 200
    length = 0.0
    prev = None
    for i in range(n + 1):
        t = i / n
        r = r0 + (r1 - r0) * t
        a = math.radians(FLEX_SWEEP * t)
        pt = (r * math.cos(a), r * math.sin(a))
        if prev is not None:
            length += math.hypot(pt[0] - prev[0], pt[1] - prev[1])
        prev = pt
    inertia = GEAR_W * FLEX_ARM_W ** 3 / 12.0
    return FLEX_ARMS * e_mpa * inertia / length / 1000.0  # N mm/rad -> N m/rad


def output_gear(p: Params) -> Part:
    """40T ring gear + 3 spiral arms + shaft hub (one PETG print).  The
    set-screw hub extends below the gear so the upper 608 stays clear."""
    z = _z(p)
    ring = prism_xy(spur_gear_profile(MODULE, OUTPUT_TEETH, 20.0, 0.12), 0.0, GEAR_W) - cyl_z(FLEX_RING_R, -1, GEAR_W + 1)
    hub = cyl_z(FLEX_HUB_R + 1.5, -6.0, GEAR_W)
    arms = union([prism_xy(_spiral_arm(FLEX_HUB_R + 1.0, FLEX_RING_R + 0.5, 120.0 * i, FLEX_SWEEP, FLEX_ARM_W), 0.0, GEAR_W)
                  for i in range(FLEX_ARMS)])
    part = ring + hub + arms
    part -= cyl_z(SHAFT_D / 2 + 0.1, -7.0, GEAR_W + 1.0)
    # M3 set screw (radial) onto a flat on the shaft, nut trap in the hub.
    part -= cyl_x(CLEARANCE_D[3.0] / 2 - 0.3, 0.0, FLEX_HUB_R + 2.0, 0.0, -3.0)
    part -= box(SHAFT_D / 2 + 0.8, SHAFT_D / 2 + 3.4, -2.9, 2.9, -6.01, -0.5)
    return Pos(0, 0, z["gear0"]) * part


def collet_hub(p: Params) -> Part:
    z = _z(p)
    hub = cyl_z(15.0, z["hub0"], z["hub1"])
    hub -= cyl_z(SHAFT_D / 2 + 0.1, z["hub0"] - 1, z["hub1"] + 1)
    for x, y in bolt_circle(3, 22.0, 90.0):
        hub -= cyl_z(INSERT_HOLE_D[3.0] / 2, z["hub1"] - 5.0, z["hub1"] + 0.01, x, y)
    hub -= cyl_x(CLEARANCE_D[3.0] / 2 - 0.3, 0.0, 16.0, 0.0, (z["hub0"] + z["hub1"]) / 2)
    hub -= box(SHAFT_D / 2 + 1.2, SHAFT_D / 2 + 3.8, -2.9, 2.9, z["hub0"] - 0.01, z["hub1"] - 1.5)
    return hub


def collet(p: Params) -> Part:
    """TPU 95A collet: cone bore Ø28 -> Ø8, six fingers."""
    z = _z(p)
    t = p.tools
    z0, z1 = z["collet0"], z["collet1"]
    body = cyl_z(18.0, z0, z1)
    # Cone bore as a stack of short cylinders (printable 45 deg-ish steps).
    steps = 16
    depth = z1 - z0 - 4.0
    for i in range(steps):
        frac = (i + 1) / steps
        r = t.collet_bore_min / 2 + (t.collet_bore_max - t.collet_bore_min) / 2 * frac
        zz = z1 - depth * (1 - (i / steps))
        body -= cyl_z(r, zz, z1 + 0.01)
    for i in range(t.collet_fingers):
        body -= Rot(Z=360.0 * i / t.collet_fingers) * box(0.0, 19.0, -0.75, 0.75, z1 - 16.0, z1 + 0.01)
    for x, y in bolt_circle(3, 22.0, 90.0):
        body -= cyl_z(CLEARANCE_D[3.0] / 2, z0 - 0.01, z0 + 4.0, x, y)
        body -= cyl_z(HEAD_D[3.0] / 2 + 0.3, z0 + 2.0, z1 + 0.01, x, y)
    return body


def magnet_cap(p: Params) -> Part:
    """Holds the 6 x 2.5 mm diametric magnet 2 mm clear of the steel shaft."""
    z = _z(p)
    t = p.tools
    z0 = z["magnet0"]
    s0, _ = shaft_span(p)
    cap = cyl_z(6.0, z0, s0 + 6.0)
    cap -= cyl_z(t.magnet_d / 2 + 0.1, z0 - 0.01, z0 + t.magnet_h)
    cap -= cyl_z(SHAFT_D / 2 + 0.05, s0, s0 + 6.01)
    return cap
