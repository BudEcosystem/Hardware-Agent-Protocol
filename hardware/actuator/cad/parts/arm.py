"""Moving links of the BHMS Arm: turret, geared shoulder/elbow, forearm,
wrist bracket and the arm side of the tool flange.

Each part is modelled in its own link frame, which is also the MJCF body
frame, so mass properties computed from these solids drop straight into
the simulation model:

* turret     - origin on the yaw axis at the turret interface plane
               (world z = base_height); joint axis +z.
* upper_arm  - origin on the shoulder axis; joint axis +y; link along +z.
* forearm    - origin on the elbow axis; joint axis +y; link along +z.
* wrist      - origin on the wrist-pitch axis; joint axis +y; link along +z.
* flange     - origin on the flange face (socket floor) on the roll axis;
               joint axis +z.  Tool frames coincide with this frame.

Positive pitch tilts the link toward +x (right-hand rule about +y).
"""

from __future__ import annotations

import math

from build123d import Location, Part, Pos, Rot

from common import (
    CLEARANCE_D,
    HEAD_D,
    INSERT_HOLE_D,
    bearing_seat_y,
    bolt_circle,
    box,
    cyl_y,
    cyl_z,
    horn_bolt_holes,
    horn_face_z,
    prism_xy,
    prism_xz,
    servo_cradle,
    spur_gear_profile,
    union,
)
from params import BEARING_608, BEARING_624, BEARING_6806, Gear, Params
from parts.base import SPIGOT_LEN

HUB_HALF = 17.0  # half width of a hub between cheeks (= link width / 2)
CHEEK_GAP = 1.0
CHEEK_T = 10.0
HUB_R = 22.0
GEAR_Y = (-HUB_HALF, -3.0)  # gear/pinion plane (y range) in shoulder & elbow
PINION_SERVO_Y = 4.0  # servo-frame origin y so the horn face sits at GEAR_Y[1]
TURRET_DISC_T = 8.0


def cheek_y(side: int) -> tuple[float, float]:
    """(inner, outer) y of the cheek on ``side`` (+1 or -1)."""
    inner = side * (HUB_HALF + CHEEK_GAP)
    outer = side * (HUB_HALF + CHEEK_GAP + CHEEK_T)
    return inner, outer


def _arc(cx: float, cz: float, r: float, a0: float, a1: float, n: int = 24) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cz + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def _cheek_profile(z_bottom: float, half_w: float, z_axis: float, r_top: float) -> list[tuple[float, float]]:
    """Plate outline in (x, z): straight sides from z_bottom, round top."""
    return [(-half_w, z_bottom), (half_w, z_bottom), (half_w, z_axis)] + _arc(0.0, z_axis, r_top, 0.0, 180.0)[1:-1] + [
        (-half_w, z_axis)]


def geared_servo_location(p: Params, axis_z: float) -> Location:
    """Servo frame -> link frame for a pinion drive whose output joint axis
    is at (0, 0, axis_z).  Servo output points to -y, body along -x, servo
    +y (cradle opening/lid) points to +z."""
    zs = axis_z - p.gear.center_distance
    return Pos(0.0, PINION_SERVO_Y, zs) * Rot(X=90)


def pinion_location(p: Params, axis_z: float) -> Location:
    """Pinion part frame (gear on z in [0, w], horn side at z=0) -> link."""
    zs = axis_z - p.gear.center_distance
    return Pos(0.0, GEAR_Y[1], zs) * Rot(X=90)


def _geared_clevis(p: Params, axis_z: float, z_bottom: float, g: Gear) -> tuple[Part, Part]:
    """(solid, cut) for a two-cheek clevis that carries a geared joint at
    (0, 0, axis_z) and its pinion servo, in the proximal link frame."""
    sides = []
    cuts = []
    for side in (+1, -1):
        inner, outer = cheek_y(side)
        y0, y1 = sorted((inner, outer))
        sides.append(prism_xz(_cheek_profile(z_bottom, 24.0, axis_z, 18.0), y0, y1))
        # 608 at the joint axis, outer face flush with the cheek outer face.
        cuts.append(bearing_seat_y(BEARING_608, p, outer, -side, 0.0, axis_z, 12.0, CHEEK_T))
    # 624 outboard support for the pinion stub, in the -y cheek.
    zs = axis_z - p.gear.center_distance
    _, outer_m = cheek_y(-1)
    cuts.append(bearing_seat_y(BEARING_624, p, outer_m, +1, 0.0, zs, 11.5, CHEEK_T - BEARING_624.width))
    solid, cut = servo_cradle(p)
    loc = geared_servo_location(p, axis_z)
    sides.append(loc * solid)
    cuts.append(loc * cut)
    # Pinion running clearance through anything between the cheeks.
    cuts.append(cyl_y(g.module * (g.pinion_teeth / 2 + 1) + 1.5, GEAR_Y[0] - 0.5, GEAR_Y[1] + 0.5, 0.0, zs))
    # Driven-gear running clearance (the distal hub's gear sweeps here).
    cuts.append(cyl_y(g.module * (g.gear_teeth / 2 + 1) + 1.0, -HUB_HALF - 0.5, HUB_HALF + 0.5, 0.0, axis_z))
    return union(sides), union(cuts)


def geared_hub(p: Params, g: Gear) -> Part:
    """Hub of a geared distal link at its own origin (joint axis = y):
    hub boss, integral driven gear in GEAR_Y, inner-race spacer bosses
    and the M8 shaft bore."""
    hub = cyl_y(HUB_R, -HUB_HALF, HUB_HALF)
    gear = Pos(0, GEAR_Y[1], 0) * Rot(X=90) * prism_xy(
        spur_gear_profile(g.module, g.gear_teeth, g.pressure_angle_deg, g.backlash), 0.0, GEAR_Y[1] - GEAR_Y[0])
    # Inner-race spacers: reach through the cheek lip (bore 12) to the 608
    # inner race; 11.6 mm keeps them off the outer race (ID ~17.7).
    reach = CHEEK_GAP + CHEEK_T - BEARING_608.width
    spacers = cyl_y(5.8, -HUB_HALF - reach, -HUB_HALF + 0.01) + cyl_y(5.8, HUB_HALF - 0.01, HUB_HALF + reach)
    part = hub + gear + spacers
    part -= cyl_y(CLEARANCE_D[8.0] / 2, -40, 40)
    # Lightening holes in the gear web (between hub and tooth ring).
    r_mid = (HUB_R + g.module * (g.gear_teeth / 2 - 1.25)) / 2 + 1.0
    for x, z in bolt_circle(6, 2 * r_mid, 30.0):
        part -= cyl_y(2.5, GEAR_Y[0] - 1, GEAR_Y[1] + 0.01, x, z)
    return part


def _beam(z0: float, z1: float, p: Params) -> Part:
    """Solid link beam (printed with sparse infill) with a rear cable groove
    and cable-clip notches."""
    a = p.arm
    hx, hy = a.link_depth / 2, a.link_width / 2
    beam = box(-hx, hx, -hy, hy, z0, z1)
    cw, cd = a.cable_channel
    beam -= box(-hx - 1, -hx + cd, -cw / 2, cw / 2, z0 - 1, z1 + 1)
    # Clip notches every 40 mm: 2 mm deep slots across the groove lips.
    z = z0 + 20.0
    while z < z1 - 10.0:
        beam -= box(-hx - 1, -hx + 2.0, -hy - 1, hy + 1, z - 2.5, z + 2.5)
        z += 40.0
    return beam


# ---------------------------------------------------------------------------
# Turret
# ---------------------------------------------------------------------------


def turret(p: Params) -> Part:
    a = p.arm
    disc = cyl_z(a.turret_d / 2, 0.0, TURRET_DISC_T)
    land = cyl_z(16.8, -0.5, 0.01)  # sits on the 6806 inner race
    spigot = cyl_z(BEARING_6806.bore / 2 - p.printer.press_fit, -SPIGOT_LEN, -0.49)
    solid, cut = _geared_clevis(p, a.shoulder_height, 0.0, p.shoulder_gear)
    part = disc + land + spigot + solid
    part -= cut
    # Yaw horn: bolts from the top through counterbores (M2 x 12).
    part -= horn_bolt_holes(p, -SPIGOT_LEN - 0.01, TURRET_DISC_T + 0.01)
    for x, y in bolt_circle(4, p.servo.horn_bolt_circle_d, 45.0):
        part -= cyl_z(HEAD_D[2.0] / 2 + 0.3, -SPIGOT_LEN + 3.0, TURRET_DISC_T + 0.01, x, y)
    # Rear cable post (service-loop anchor) with a tie slot.
    post = box(-a.turret_d / 2 + 2, -a.turret_d / 2 + 14, -8, 8, TURRET_DISC_T - 0.01, 40.0)
    post -= box(-a.turret_d / 2 + 5.5, -a.turret_d / 2 + 10.5, -9, 9, 20.0, 26.0)  # cable-tie slot
    part += post
    return part


def pinion(p: Params, g: Gear) -> Part:
    """Driving pinion, bolted to the servo horn (z=0 face).  An outboard
    stub carries an M4 heat-set insert; an M4 x 12 screw through a 624-2RS
    in the opposite cheek (and an M4 washer that bears on the inner race
    only) supports the pinion against the mesh separating force.
    Part frame: axis z, horn face z = 0, gear z in [0, face]."""
    w = GEAR_Y[1] - GEAR_Y[0]
    part = prism_xy(spur_gear_profile(g.module, g.pinion_teeth, g.pressure_angle_deg, g.backlash), 0.0, w)
    # Stub reaches to 0.8 mm (washer) short of the 624 inner face.
    stub_len = CHEEK_GAP + (CHEEK_T - BEARING_624.width) - 0.8
    part += cyl_z(5.0, w - 0.01, w + stub_len)
    part -= horn_bolt_holes(p, -0.01, 4.5)
    for x, y in bolt_circle(4, p.servo.horn_bolt_circle_d, 45.0):
        part -= cyl_z(HEAD_D[2.0] / 2 + 0.3, 4.5, w + 0.01, x, y)  # screw access from the outboard face
    part -= cyl_z(INSERT_HOLE_D[4.0] / 2, w + stub_len - 8.0, w + stub_len + 0.01)
    return part


# ---------------------------------------------------------------------------
# Upper arm and forearm
# ---------------------------------------------------------------------------


def upper_arm(p: Params) -> Part:
    a = p.arm
    L = a.l_upper
    zs = L - p.gear.center_distance
    clevis, cut = _geared_clevis(p, L, zs - 26.0, p.gear)
    beam_top = zs - 14.0
    part = geared_hub(p, p.shoulder_gear) + _beam(HUB_R - 2.0, beam_top, p) + clevis
    # Web joining the beam to the clevis cheeks below the servo.
    part += box(-24.0, 24.0, -HUB_HALF - CHEEK_GAP - CHEEK_T, HUB_HALF + CHEEK_GAP + CHEEK_T, zs - 26.0, zs - 16.0)
    part -= cut
    part -= cyl_y(CLEARANCE_D[8.0] / 2, -40, 40)  # shoulder shaft bore stays clear
    return part


WRIST_SERVO_Y0 = -17.5  # servo-frame origin y (body centred on the link)


def wrist_servo_location(p: Params) -> Location:
    """Servo frame -> forearm frame for the direct-drive wrist pitch:
    output to -y, body down the forearm (-z), lid toward -x."""
    return Pos(0.0, WRIST_SERVO_Y0, p.arm.l_fore) * Rot(Y=-90) * Rot(X=90)


def wrist_horn_y(p: Params) -> float:
    return WRIST_SERVO_Y0 - horn_face_z(p)


IDLER_BOSS_Y = (20.3, 31.3)  # boss carrying the 624 idler, outer face flush
BRACKET_RIGHT_Y = (31.8, 37.8)  # 0.5 mm M4 washer gap to the idler boss


def forearm(p: Params) -> Part:
    a = p.arm
    L = a.l_fore
    solid, cut = servo_cradle(p)
    loc = wrist_servo_location(p)
    cradle = loc * solid
    cb = cradle.bounding_box()
    part = geared_hub(p, p.gear) + _beam(HUB_R - 2.0, cb.min.Z, p) + cradle
    # Idler boss on +y, coaxial with the wrist pitch axis.  The 624 sits in
    # the boss; the bracket's M4 x 16 screw passes its inner race and is
    # locked by a nyloc nut that turns in the 9 mm cavity behind it.
    part += cyl_y(9.0, IDLER_BOSS_Y[0] - 3.0, IDLER_BOSS_Y[1], 0.0, L)
    part -= loc * cut
    part -= bearing_seat_y(BEARING_624, p, IDLER_BOSS_Y[1], -1, 0.0, L, 9.0, 5.6)
    return part


# ---------------------------------------------------------------------------
# Wrist bracket and arm-side flange
# ---------------------------------------------------------------------------


def roll_servo_location(p: Params) -> Location:
    """Servo frame -> wrist frame: output +z, horn face at l_wrist - floor,
    body along -y, cradle lid toward -x (clear of the bridge)."""
    a = p.arm
    return Pos(0.0, 0.0, a.l_wrist - a.flange_floor - horn_face_z(p)) * Rot(Z=90)



def wrist_bracket(p: Params) -> Part:
    a = p.arm
    b0, b1 = a.wrist_bridge
    yl = wrist_horn_y(p)  # horn face (bracket left arm inner face)
    left = (yl - 5.0, yl)
    right = BRACKET_RIGHT_Y
    # The roll-servo lid lies on the plane x = lid_x (servo +y -> wrist -x)
    # and reaches down to the cradle floor; arms and bridge stay behind it.
    lid_x = -(p.servo.width / 2 + p.printer.fit_clearance)
    z_floor = a.l_wrist - a.flange_floor - horn_face_z(p) - p.servo.height - p.printer.fit_clearance - 2.6
    arm_profile = [(-15.0, 0.0)] + _arc(0.0, 0.0, 15.0, 180.0, 360.0)[1:-1] + [
        (15.0, 0.0), (15.0, b1), (lid_x + 0.3, b1), (lid_x + 0.3, z_floor - 0.3), (-15.0, z_floor - 3.0)]
    arms = prism_xz(arm_profile, *left) + prism_xz(arm_profile, *right)
    solid, cut = servo_cradle(p)
    loc = roll_servo_location(p)
    cradle = loc * solid
    cbb = cradle.bounding_box()
    bridge = box(lid_x + 0.3, max(cbb.max.X, 15.0), left[0], right[1], b0, b1)
    part = arms + bridge + cradle
    part -= loc * cut
    # Left arm: horn bolts (M2) with heads on the outside.
    horn = Pos(0, yl, 0) * Rot(X=90) * horn_bolt_holes(p, -0.01, 5.01)
    part -= horn
    # Right arm: M4 clearance and head counterbore (idler screw).
    part -= cyl_y(CLEARANCE_D[4.0] / 2, right[0] - 0.01, right[1] + 0.01)
    part -= cyl_y(HEAD_D[4.0] / 2 + 0.3, right[1] - 3.0, right[1] + 0.01)
    # Cable anchor slot on the bridge for the tool cable service loop.
    part -= box(-4.0, 4.0, right[1] - 4.0, right[1] + 1, b0 - 1, b0 + 3.0)
    return part


def _lug_ring(p: Params) -> Part:
    f = p.flange
    r_in = f.socket_id / 2
    lugs = []
    for ang in f.lug_angles_deg:
        a0, a1 = ang - f.lug_width_deg / 2, ang + f.lug_width_deg / 2
        outer = _arc(0.0, 0.0, r_in + 0.5, a0, a1, 8)
        inner = list(reversed(_arc(0.0, 0.0, r_in - f.lug_radial, a0, a1, 8)))
        lugs.append(prism_xy(outer + inner, f.socket_depth - f.lug_thickness, f.socket_depth))
    return union(lugs)


def pogo_positions(p: Params) -> list[tuple[float, float]]:
    """(x, y) of pogo pin i at flange angle 60*i deg (CCW about +z)."""
    f = p.flange
    return [(f.pogo_circle_r * math.cos(math.radians(360.0 * i / f.pogo_count)),
             f.pogo_circle_r * math.sin(math.radians(360.0 * i / f.pogo_count))) for i in range(f.pogo_count)]


def flange_arm(p: Params) -> Part:
    f = p.flange
    a = p.arm
    zf = -a.flange_floor
    body = cyl_z(f.socket_od / 2, zf, f.socket_depth) - cyl_z(f.socket_id / 2, 0.0, f.socket_depth + 0.01)
    body += _lug_ring(p)
    # Horn bolts from inside the socket, heads counterbored below the floor top.
    body -= horn_bolt_holes(p, zf - 0.01, 0.01)
    for x, y in bolt_circle(4, p.servo.horn_bolt_circle_d, 45.0):
        body -= cyl_z(HEAD_D[2.0] / 2 + 0.3, -2.2, 0.01, x, y)
    # Pogo pin bores (drilled to the barrel size after printing).
    for x, y in pogo_positions(p):
        body -= cyl_z(f.pogo_barrel_d / 2 - 0.05, zf - 0.01, 0.01, x, y)
    # Stop pin (3 mm dowel, 6 mm long, 3 mm proud) at flange angle 0.
    body -= cyl_z(f.stop_pin_d / 2 - 0.05, -3.0, 0.01, f.stop_pin_r, 0.0)
    # Detent ball plunger (M5) radial, in an M5 heat-set insert.
    loc = Pos(0, 0, f.detent_z) * Rot(Z=f.detent_angle_deg) * Rot(Y=90)
    body -= loc * cyl_z(INSERT_HOLE_D[5.0] / 2, f.socket_id / 2 - 0.5, f.socket_od / 2 + 0.01)
    # Wire exit notches under the floor for the pogo tails.
    for i in range(3):
        ang = 60.0 + 120.0 * i
        body -= Rot(Z=ang) * box(f.pogo_circle_r + 3.0, f.socket_od / 2 + 1, -2.5, 2.5, zf - 0.01, zf + 2.0)
    return body


def pinion_shoulder(p: Params) -> Part:
    return pinion(p, p.shoulder_gear)


def pinion_elbow(p: Params) -> Part:
    return pinion(p, p.gear)
