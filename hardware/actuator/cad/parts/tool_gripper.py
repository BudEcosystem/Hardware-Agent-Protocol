"""Parallel gripper: one STS3215 (bus ID 6) drives a 24T module-1 pinion
between two racks that slide in a closed guide; each rack carries one
finger, so the fingers move symmetrically (0..60 mm opening).

Tool frame (see tool_interface).  Rack/finger B is rack/finger A turned
180 deg about z, so one rack and one finger design are printed twice.
"""

from __future__ import annotations

from build123d import Location, Part, Pos, Rot

from common import (
    CLEARANCE_D,
    bolt_circle,
    HEAD_D,
    INSERT_HOLE_D,
    box,
    cyl_z,
    horn_bolt_holes,
    horn_face_z,
    prism_xy,
    rack_profile,
    servo_cradle,
    spur_gear_profile,
)
from params import Params
from parts.tool_interface import collar_top, tool_plug, wire_channel

PINION_W = 8.0
RACK_LEN = 48.0
RACK_BACK = 21.0  # rack outer face x
GUIDE_CLR = 0.3
COVER_T = 3.4
SIDE_T = 3.7


def servo_location(p: Params) -> Location:
    """Servo frame -> tool frame: output +z on the tool axis, body toward -x."""
    return Pos(0, 0, collar_top(p) + p.servo.height + p.printer.fit_clearance + 2.6)


def _z(p: Params) -> dict[str, float]:
    zs = collar_top(p) + p.servo.height + p.printer.fit_clearance + 2.6
    zh = zs + horn_face_z(p)
    return {
        "servo": zs,
        "horn": zh,
        "pinion0": zh,
        "pinion1": zh + PINION_W,
        "cover0": zh + PINION_W + GUIDE_CLR,
        "cover1": zh + PINION_W + GUIDE_CLR + COVER_T,
    }


def pitch_r(p: Params) -> float:
    return p.tools.gripper_pinion_module * p.tools.gripper_pinion_teeth / 2


def finger_tip_z(p: Params) -> float:
    return _z(p)["cover1"] + 0.3 + p.tools.gripper_finger_len


def tcp_z(p: Params) -> float:
    """Tool centre point: between the pads, 10 mm below the fingertips."""
    return finger_tip_z(p) - 10.0


def rack_travel_y(p: Params) -> tuple[float, float]:
    """Finger A inner-face y at closed and open."""
    return 1.0, 1.0 + p.tools.gripper_stroke


def gripper_body(p: Params) -> Part:
    z = _z(p)
    ct = collar_top(p)
    plug = tool_plug(p)
    solid, cut = servo_cradle(p)
    loc = servo_location(p)
    cradle = loc * solid
    hy = RACK_LEN / 2 + p.tools.gripper_stroke / 2 + 6.0
    xw = RACK_BACK + GUIDE_CLR + SIDE_T
    floor = box(-xw, xw, -hy, hy, z["servo"] + 2.0 - 0.01, z["pinion0"] - GUIDE_CLR)
    sides = box(-xw, -xw + SIDE_T, -hy, hy, z["servo"] + 2.0, z["cover1"]) + box(xw - SIDE_T, xw, -hy, hy, z["servo"] + 2.0,
                                                                                    z["cover1"])
    cover = box(-xw, xw, -hy, hy, z["cover0"], z["cover1"])
    # Pedestal between collar and cradle floor is the cradle itself; add a
    # web under the guide where it overhangs the cradle.
    web = box(-xw, xw, -6.0, 6.0, ct - 0.01, z["servo"] + 2.0)
    body = plug + cradle + floor + sides + cover + web
    body -= loc * cut
    # Horn / pinion running clearance and screw access through the cover.
    body -= cyl_z(pitch_r(p) + p.tools.gripper_pinion_module + 1.0, z["servo"] + 2.0, z["cover0"] + 0.01)
    body -= cyl_z(4.0, z["cover0"] - 0.01, z["cover1"] + 0.01)
    # Rack channels (racks slide on the floor, under the cover).
    body -= box(-RACK_BACK - GUIDE_CLR, RACK_BACK + GUIDE_CLR, -hy - 1, hy + 1, z["pinion0"] - GUIDE_CLR, z["cover0"] + 0.01)
    # Finger slots in the cover (A at +x, B at -x).
    y_closed, y_open = rack_travel_y(p)
    for sx in (+1, -1):
        x0, x1 = sorted((sx * 13.5, sx * (RACK_BACK - 0.5)))
        ys = sorted((sx * (y_closed + 4.0 - 4.5), sx * (y_open + 4.0 + 4.5)))
        body -= box(x0, x1, ys[0], ys[1], z["cover0"] - 0.01, z["cover1"] + 0.01)
    body -= wire_channel(p, -40.0)
    # Web must not block the rack channels; the channel cut above does that.
    return body


def gripper_pinion(p: Params) -> Part:
    """Pinion part frame = tool frame (bolted to the horn)."""
    z = _z(p)
    t = p.tools
    part = Pos(0, 0, z["pinion0"]) * prism_xy(spur_gear_profile(t.gripper_pinion_module, t.gripper_pinion_teeth, 20.0, 0.1),
                                               0.0, PINION_W)
    part -= Pos(0, 0, z["pinion0"]) * horn_bolt_holes(p, -0.01, PINION_W + 0.01)
    for x, y in bolt_circle(4, p.servo.horn_bolt_circle_d, 45.0):
        part -= cyl_z(HEAD_D[2.0] / 2 + 0.3, z["pinion0"] + 3.0, z["pinion1"] + 0.01, x, y)
    return part


def gripper_rack(p: Params) -> Part:
    """Rack A at the closed position (tool frame)."""
    z = _z(p)
    m = p.tools.gripper_pinion_module
    r = pitch_r(p)
    y_closed, _ = rack_travel_y(p)
    yc = y_closed - 16.0  # rack spans [yA - 40, yA + 8]: meshes over the full stroke
    depth = RACK_BACK - r  # pitch line to back face
    prof = rack_profile(m, RACK_LEN, depth, 20.0, 0.1)
    # Map rack (u along rack, v toward the pinion = -x): x = r + (-v)?  Teeth
    # point +v in the profile; at x = r the pitch line, teeth toward -x.
    pts = [(r - v, yc + u) for u, v in prof]
    rack = prism_xy(pts, z["pinion0"], z["pinion1"])
    rack = rack & box(r - m - 0.01, RACK_BACK, yc - RACK_LEN / 2, yc + RACK_LEN / 2, z["pinion0"] - 1, z["pinion1"] + 1)
    # Finger seat: tenon pocket + M3 insert on the top face at y = yA + 4.
    ys = y_closed + 4.0
    xm = (13.5 + RACK_BACK) / 2 + 0.5
    rack -= box(xm - 2.5, xm + 2.5, ys - 3.0, ys + 3.0, z["pinion1"] - 1.5, z["pinion1"] + 0.01)
    rack -= cyl_z(INSERT_HOLE_D[3.0] / 2, z["pinion1"] - 5.0, z["pinion1"] + 0.01, xm, ys)
    return rack


def gripper_finger(p: Params) -> Part:
    """Finger A at the closed position (tool frame)."""
    z = _z(p)
    y_closed, _ = rack_travel_y(p)
    ys = y_closed + 4.0
    xm = (13.5 + RACK_BACK) / 2 + 0.5
    base = box(14.0, RACK_BACK - 1.0, ys - 4.0, ys + 4.0, z["pinion1"] + 0.01, z["cover1"] + 0.3)
    tenon = box(xm - 2.3, xm + 2.3, ys - 2.8, ys + 2.8, z["pinion1"] - 1.4, z["pinion1"] + 0.02)
    z_arm = z["cover1"] + 0.3
    arm = box(-6.0, RACK_BACK - 1.0, y_closed, y_closed + 8.0, z_arm, z_arm + 6.0)
    blade = box(-6.0, 6.0, y_closed, y_closed + 5.0, z_arm, finger_tip_z(p))
    finger = base + tenon + arm + blade
    finger -= cyl_z(CLEARANCE_D[3.0] / 2, z["pinion1"] - 1.5, z_arm + 6.01, xm, ys)
    finger -= cyl_z(HEAD_D[3.0] / 2 + 0.3, z_arm + 2.5, z_arm + 6.01, xm, ys)
    # Grip ribs on the inner face (0.6 mm deep, 2 mm pitch) over the pad area.
    zr = finger_tip_z(p) - 24.0
    while zr < finger_tip_z(p) - 2.0:
        finger -= box(-6.1, 6.1, y_closed - 0.01, y_closed + 0.6, zr, zr + 1.0)
        zr += 2.0
    return finger


def mirrored(part: Part) -> Part:
    """Rack/finger B: the A part turned 180 deg about the tool axis."""
    return Rot(Z=180) * part
