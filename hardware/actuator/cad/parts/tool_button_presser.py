"""Button presser: an STS3215 (bus ID 8) with its axis across the tool turns
an eccentric cam (4 mm throw -> 8 mm stroke) under a square plunger.  A
compression spring keeps the plunger follower on the cam in any arm pose.
The plunger tip carries an Interlink FSR 400 under a TPU cap; the FSR and
a divider resistor on the tool contact PCB give the press force on AUX1.

Pressing force is bounded twice: by the servo torque limit (EEPROM) and by
the firmware closing the loop on the FSR reading.
"""

from __future__ import annotations

from build123d import Location, Part, Pos, Rot

from common import (
    CLEARANCE_D,
    HEAD_D,
    bolt_circle,
    box,
    cyl_x,
    cyl_z,
    horn_face_z,
    servo_cradle,
)
from params import Params
from parts.tool_interface import collar_top, tool_plug, wire_channel

BASE_T = 3.0
CAM_R = 16.0  # > horn radius + 4 mm throw, so the follower never meets the horn
CAM_W = 6.0
PLUNGER = 8.0  # square section
FOLLOWER_R = 7.0
BRIDGE_T = 4.0
TOWER_H = 22.0
WALL_Y = (21.5, 24.5)
SPRING_SPACE = 8.0  # compressed length of the return spring at full lift


def _z(p: Params) -> dict[str, float]:
    ct = collar_top(p)
    s = p.servo
    c = ct + BASE_T + (s.length - s.spline_from_front) + p.printer.fit_clearance + 2.6
    e = p.tools.presser_stroke / 2
    return {
        "base0": ct,
        "base1": ct + BASE_T,
        "cam": c,
        "follower_min": c - e + CAM_R,
        "follower_max": c + e + CAM_R,
        "bridge0": c + e + CAM_R + 2.0 + SPRING_SPACE,
        "bridge1": c + e + CAM_R + 2.0 + SPRING_SPACE + BRIDGE_T,
    }


def servo_location(p: Params) -> Location:
    """Servo frame -> tool: output +x, body toward -z (servo x -> tool z)."""
    z = _z(p)
    xs = -(horn_face_z(p) + CAM_W / 2)
    return Pos(xs, 0, z["cam"]) * Rot(X=180) * Rot(Y=90)


def plunger_len(p: Params) -> float:
    return 52.0


def tcp_z(p: Params, extended: bool = True) -> float:
    z = _z(p)
    base = z["follower_max"] if extended else z["follower_min"]
    return base + plunger_len(p) + 2.0  # + TPU cap


def presser_body(p: Params) -> Part:
    z = _z(p)
    plug = tool_plug(p)
    solid, cut = servo_cradle(p)
    loc = servo_location(p)
    cradle = loc * solid
    cb = cradle.bounding_box()
    base = box(min(cb.min.X, -24.0), 22.0, -WALL_Y[1] - 1.5, WALL_Y[1] + 1.5, z["base0"] - 0.01, z["base1"])
    walls = box(-9.0, 9.0, WALL_Y[0], WALL_Y[1], z["base1"] - 0.01, z["bridge1"]) + box(
        -9.0, 9.0, -WALL_Y[1], -WALL_Y[0], z["base1"] - 0.01, z["bridge1"])
    bridge = box(-9.0, 9.0, -WALL_Y[1], WALL_Y[1], z["bridge0"], z["bridge1"])
    tower = box(-7.0, 7.0, -7.0, 7.0, z["bridge1"] - 0.01, z["bridge1"] + TOWER_H)
    body = plug + base + cradle + walls + bridge + tower
    body -= loc * cut
    sq = PLUNGER / 2 + p.printer.slide_clearance
    body -= box(-sq, sq, -sq, sq, z["bridge0"] - 0.01, z["bridge1"] + TOWER_H + 0.01)
    # Slot for the FSR tail and wires along the plunger (+x face).
    body -= box(sq - 0.01, sq + 1.5, -3.0, 3.0, z["bridge0"] - 0.01, z["bridge1"] + TOWER_H + 0.01)
    body -= wire_channel(p, -26.0)
    return body


def cam(p: Params) -> Part:
    """Eccentric cam, bolted to the horn; tool frame at angle 0 (max lift)."""
    z = _z(p)
    e = p.tools.presser_stroke / 2
    x0 = -CAM_W / 2
    disc = cyl_x(CAM_R, x0, x0 + CAM_W, 0.0, z["cam"] + e)
    # Horn bolts on the servo axis (cam frame: horn face at x0).
    for y, zz in bolt_circle(4, p.servo.horn_bolt_circle_d, 45.0):
        disc -= cyl_x(CLEARANCE_D[2.0] / 2, x0 - 0.01, x0 + CAM_W + 0.01, y, z["cam"] + zz)
        disc -= cyl_x(HEAD_D[2.0] / 2 + 0.3, x0 + 3.0, x0 + CAM_W + 0.01, y, z["cam"] + zz)
    disc -= cyl_x(3.2, x0 - 0.01, x0 + CAM_W + 0.01, 0.0, z["cam"])
    return disc


def plunger(p: Params) -> Part:
    """Plunger at full extension (cam at max lift)."""
    z = _z(p)
    f = z["follower_max"]
    L = plunger_len(p)
    rod = box(-PLUNGER / 2, PLUNGER / 2, -PLUNGER / 2, PLUNGER / 2, f, f + L)
    follower = cyl_z(FOLLOWER_R, f, f + 2.0)
    part = rod + follower
    # FSR 400 pocket on the tip and a groove for its tail along +x.
    part -= cyl_z(p.tools.fsr_d / 2, f + L - 0.6, f + L + 0.01)
    part -= box(PLUNGER / 2 - 0.8, PLUNGER / 2 + 0.01, -2.2, 2.2, f + 2.0, f + L + 0.01)
    return part


def tip_cap(p: Params) -> Part:
    """TPU 95A cap that snaps over the plunger tip and loads the FSR."""
    z = _z(p)
    f = z["follower_max"] + plunger_len(p)
    cap = cyl_z(p.tools.presser_tip_d / 2 + 1.0, f - 6.0, f + 2.0)
    cap -= box(-PLUNGER / 2 - 0.1, PLUNGER / 2 + 0.1, -PLUNGER / 2 - 0.1, PLUNGER / 2 + 0.1, f - 6.01, f)
    # Load puck: a 5 mm boss that presses the FSR active area only.
    cap += cyl_z(2.5, f - 0.6, f + 0.01)
    return cap
