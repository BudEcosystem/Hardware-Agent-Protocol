"""Shared build123d geometry helpers for the BHMS Arm parts.

Conventions: millimetres; every helper returns a ``Part`` positioned in the
caller's frame.  Holes and pockets add ``Printer.fit_clearance`` (radially)
so that a part designed at nominal size prints to a working fit.
"""

from __future__ import annotations

import math
from functools import reduce

from build123d import (
    Align,
    Box,
    Cylinder,
    Part,
    Polygon,
    Pos,
    Rot,
    extrude,
)

from params import Params

MIN = (Align.MIN, Align.MIN, Align.MIN)

# ISO metric clearance (normal fit) and heat-set insert hole diameters.
CLEARANCE_D = {2.0: 2.4, 2.5: 2.9, 3.0: 3.4, 4.0: 4.5, 5.0: 5.5, 8.0: 8.4}
INSERT_HOLE_D = {2.0: 3.2, 3.0: 4.0, 4.0: 5.6, 5.0: 6.4}  # brass heat-set inserts
NUT_AF = {3.0: 5.5, 4.0: 7.0, 5.0: 8.0, 8.0: 13.0}  # hex nut across flats
NUT_T = {3.0: 2.4, 4.0: 3.2, 5.0: 4.0, 8.0: 6.5}
HEAD_D = {2.0: 4.0, 3.0: 6.0, 4.0: 7.5, 5.0: 9.0, 8.0: 13.5}  # socket head cap
HEAD_H = {2.0: 2.0, 3.0: 3.0, 4.0: 4.0, 5.0: 5.0, 8.0: 8.0}


def union(parts: list[Part]) -> Part:
    return reduce(lambda a, b: a + b, parts)


def box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> Part:
    """Axis-aligned box from min/max corners."""
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        raise ValueError(f"degenerate box {(x0, x1, y0, y1, z0, z1)}")
    return Pos(x0, y0, z0) * Box(x1 - x0, y1 - y0, z1 - z0, align=MIN)


def cyl_z(r: float, z0: float, z1: float, x: float = 0.0, y: float = 0.0) -> Part:
    return Pos(x, y, z0) * Cylinder(r, z1 - z0, align=(Align.CENTER, Align.CENTER, Align.MIN))


def cyl_y(r: float, y0: float, y1: float, x: float = 0.0, z: float = 0.0) -> Part:
    # Rot(X=-90) maps +z to +y, so a z-cylinder starting at 0 spans [0, h] in y.
    return Pos(x, y0, z) * Rot(X=-90) * Cylinder(r, y1 - y0, align=(Align.CENTER, Align.CENTER, Align.MIN))


def cyl_x(r: float, x0: float, x1: float, y: float = 0.0, z: float = 0.0) -> Part:
    # Rot(Y=90) maps +z to +x.
    return Pos(x0, y, z) * Rot(Y=90) * Cylinder(r, x1 - x0, align=(Align.CENTER, Align.CENTER, Align.MIN))


def ccw(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Return the polygon wound counter-clockwise.  build123d extrudes along
    the face normal, so a clockwise outline would extrude backwards."""
    area2 = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))
    return list(points) if area2 > 0 else list(reversed(points))


def prism_xz(points: list[tuple[float, float]], y0: float, y1: float) -> Part:
    """Extrude a polygon given in (x, z) across y in [y0, y1]."""
    face = Polygon(*ccw(points), align=None)
    solid = extrude(face, amount=y1 - y0)  # occupies z in [0, h], profile in xy
    # Rot(X=90): (x, y, z) -> (x, -z, y); profile y becomes z, extrusion -> -y.
    return Pos(0, y1, 0) * Rot(X=90) * solid


def prism_yz(points: list[tuple[float, float]], x0: float, x1: float) -> Part:
    """Extrude a polygon given in (y, z) across x in [x0, x1]."""
    face = Polygon(*ccw(points), align=None)
    solid = extrude(face, amount=x1 - x0)  # (u, v, w), w in [0, h]
    # Rot(X=90) maps (u, v, w) -> (u, -w, v); Rot(Z=90) then maps that to
    # (w, u, v), i.e. extrusion along +x and the profile in the yz plane.
    return Pos(x0, 0, 0) * Rot(Z=90) * Rot(X=90) * solid


def prism_xy(points: list[tuple[float, float]], z0: float, z1: float) -> Part:
    face = Polygon(*ccw(points), align=None)
    return Pos(0, 0, z0) * extrude(face, amount=z1 - z0)


def rounded_slot_xy(length: float, width: float, z0: float, z1: float) -> Part:
    """Stadium-shaped slot along x centred on the origin."""
    r = width / 2.0
    core = box(-length / 2 + r, length / 2 - r, -r, r, z0, z1) if length > width else None
    ends = [cyl_z(r, z0, z1, x=-length / 2 + r), cyl_z(r, z0, z1, x=length / 2 - r)]
    return union(([core] if core is not None else []) + ends)


def bolt_circle(n: int, d: float, phase_deg: float = 0.0) -> list[tuple[float, float]]:
    return [
        (d / 2 * math.cos(math.radians(phase_deg + 360.0 * i / n)), d / 2 * math.sin(math.radians(phase_deg + 360.0 * i / n)))
        for i in range(n)
    ]


def hex_prism_z(af: float, z0: float, z1: float, x: float = 0.0, y: float = 0.0) -> Part:
    r = af / math.sqrt(3.0)
    pts = [(x + r * math.cos(math.radians(60 * i)), y + r * math.sin(math.radians(60 * i))) for i in range(6)]
    return prism_xy(pts, z0, z1)


# ---------------------------------------------------------------------------
# Involute spur gears
# ---------------------------------------------------------------------------


def _involute(rb: float, t: float) -> tuple[float, float]:
    return rb * (math.cos(t) + t * math.sin(t)), rb * (math.sin(t) - t * math.cos(t))


def spur_gear_profile(module: float, teeth: int, pressure_angle_deg: float = 20.0, backlash: float = 0.1,
                      flank_points: int = 6) -> list[tuple[float, float]]:
    """Closed outline of a standard involute spur gear (addendum m, dedendum 1.25 m).

    ``backlash`` is the circular tooth-thickness reduction (per tooth) at
    the pitch circle, giving running clearance for printed teeth.
    """
    if teeth < 8:
        raise ValueError("teeth < 8 undercuts badly without profile shift")
    alpha = math.radians(pressure_angle_deg)
    rp = module * teeth / 2.0
    rb = rp * math.cos(alpha)
    ra = rp + module
    rf = max(rp - 1.25 * module, 0.5 * rb)
    # Half tooth angle at the pitch circle, minus backlash.
    half_pitch_thick = (math.pi * module / 2.0 - backlash) / (2.0 * rp)
    inv_alpha = math.tan(alpha) - alpha
    t_max = math.sqrt(max((ra / rb) ** 2 - 1.0, 0.0))
    pts: list[tuple[float, float]] = []
    step = 2.0 * math.pi / teeth
    for k in range(teeth):
        centre = k * step
        # Right flank (rotating clockwise from tooth centre) then left flank.
        flank = []
        for i in range(flank_points + 1):
            t = t_max * i / flank_points
            x, y = _involute(rb, t)
            r = math.hypot(x, y)
            ang = math.atan2(y, x)
            # Involute starts at base circle at angle 0; place relative to tooth centre.
            theta = half_pitch_thick + inv_alpha - ang
            flank.append((r, theta))
        # Flank from the root (radial line below the base circle) to the tip;
        # psi(r) is the half tooth angle at radius r.
        flank_up = [(rf, flank[0][1])] + flank
        lower = [(r, centre - th) for r, th in flank_up]  # root -> tip
        upper = [(r, centre + th) for r, th in reversed(flank_up)]  # tip -> root
        for r, th in lower + upper:
            pts.append((r * math.cos(th), r * math.sin(th)))
    return pts


def spur_gear(module: float, teeth: int, width: float, bore: float = 0.0, pressure_angle_deg: float = 20.0,
              backlash: float = 0.1) -> Part:
    """Spur gear centred on the z axis, occupying z in [0, width]."""
    gear = prism_xy(spur_gear_profile(module, teeth, pressure_angle_deg, backlash), 0.0, width)
    if bore > 0:
        gear = gear - cyl_z(bore / 2, -1.0, width + 1.0)
    return gear


def rack_profile(module: float, length: float, height: float, pressure_angle_deg: float = 20.0,
                 backlash: float = 0.1) -> list[tuple[float, float]]:
    """Rack outline in (x, y): teeth point toward +y, pitch line at y=0,
    tooth tips at +m, roots at -1.25 m, body down to -height."""
    alpha = math.radians(pressure_angle_deg)
    pitch = math.pi * module
    half_top = pitch / 4.0 - backlash / 2.0 - module * math.tan(alpha)
    half_root = pitch / 4.0 - backlash / 2.0 + 1.25 * module * math.tan(alpha)
    n = int(length // pitch)
    x_start = -n * pitch / 2.0
    pts: list[tuple[float, float]] = [(x_start - pitch / 2, -height)]
    pts.append((x_start - pitch / 2, -1.25 * module))
    for i in range(n + 1):
        c = x_start + i * pitch
        pts += [(c - half_root, -1.25 * module), (c - half_top, module), (c + half_top, module), (c + half_root, -1.25 * module)]
    pts.append((x_start + n * pitch + pitch / 2, -1.25 * module))
    pts.append((x_start + n * pitch + pitch / 2, -height))
    return pts


# ---------------------------------------------------------------------------
# STS3215 servo envelope (servo frame)
# ---------------------------------------------------------------------------
# Servo frame: output axis = +z through the origin; body top face at z=0,
# body in z in [-H, 0]; front short face at x = +spline_from_front; back
# short face (cable exit) at x = spline_from_front - L; y symmetric.


def servo_extent(p: Params) -> tuple[float, float, float, float, float, float]:
    s = p.servo
    return (s.spline_from_front - s.length, s.spline_from_front, -s.width / 2, s.width / 2, -s.height, 0.0)


def servo_body(p: Params) -> Part:
    """Envelope solid of the servo incl. output boss and horn (reference only)."""
    s = p.servo
    x0, x1, y0, y1, z0, z1 = servo_extent(p)
    body = box(x0, x1, y0, y1, z0, z1)
    boss = cyl_z(s.boss_d / 2, 0.0, s.boss_height)
    horn = cyl_z(s.horn_d / 2, s.boss_height, s.boss_height + s.horn_thickness)
    return body + boss + horn


def horn_face_z(p: Params) -> float:
    return p.servo.boss_height + p.servo.horn_thickness


def servo_pocket(p: Params, open_dir: str = "+y", extra: float = 0.0) -> Part:
    """Cut body for a servo cradle: envelope + clearance, boss/horn relief
    and a cable channel, extended along ``open_dir`` so the servo can be
    dropped in.  ``open_dir`` is '+y' or '-z' (servo frame)."""
    s = p.servo
    c = p.printer.fit_clearance
    x0, x1, y0, y1, z0, z1 = servo_extent(p)
    pocket = box(x0 - c, x1 + c, y0 - c, y1 + c, z0 - c, z1 + 0.01)
    relief_r = s.horn_d / 2 + 1.0
    boss = cyl_z(s.boss_d / 2 + 0.6, -0.5, s.boss_height + 0.5) + cyl_z(relief_r, s.boss_height - 0.5, s.boss_height + s.horn_thickness + 2.0)
    cable = box(x0 - 12.0, x0 + 0.5, -s.cable_exit_w / 2, s.cable_exit_w / 2, z0 + 4.0, z1 - 4.0)
    cut = pocket + boss + cable
    if open_dir == "+y":
        cut = cut + box(x0 - c, x1 + c, 0.0, 60.0 + extra, z0 - c, z1 + 0.01)
        cut = cut + box(-s.boss_d / 2 - 0.6, s.boss_d / 2 + 0.6, 0.0, 60.0 + extra, -0.5, s.boss_height + 0.5)
    elif open_dir == "-z":
        cut = cut + box(x0 - c, x1 + c, y0 - c, y1 + c, z0 - 60.0 - extra, z0)
    else:
        raise ValueError(open_dir)
    return cut


CRADLE_WALL = 2.6
LID_T = 3.0
_BOSS = 8.0


def _cradle_boss_centres(p: Params) -> list[tuple[float, float]]:
    """(x, z) centres of the four lid-screw bosses, servo frame."""
    x0, x1, _, _, z0, _ = servo_extent(p)
    c = p.printer.fit_clearance
    off = c + _BOSS / 2 - 0.4
    # Bosses stay inside the cradle's z extent (floor at z0 - 2.8, top at
    # z = 2) so the lid never protrudes below the floor or past the horn face.
    return [(x0 - off, z0 + 1.2), (x1 + off, z0 + 1.2), (x0 - off, -2.4), (x1 + off, -2.4)]


def servo_cradle(p: Params) -> tuple[Part, Part]:
    """(solid, cut) of a servo cradle in the servo frame.

    The servo slides in along +y and is retained by ``servo_lid`` screwed
    into four M3 heat-set inserts.  A 2 mm top wall under the horn takes
    axial load; the opposite (-y) wall and the floor locate the body.
    """
    x0, x1, y0, y1, z0, z1 = servo_extent(p)
    c = p.printer.fit_clearance
    w = CRADLE_WALL
    y_lid = y1 + c
    block = box(x0 - c - w, x1 + c + w, y0 - c - w, y_lid, z0 - c - w, 2.0)
    bosses = [box(x - _BOSS / 2, x + _BOSS / 2, y_lid - 10.0, y_lid, z - _BOSS / 2, z + _BOSS / 2)
              for x, z in _cradle_boss_centres(p)]
    solid = union([block] + bosses)
    inserts = [cyl_y(INSERT_HOLE_D[3.0] / 2, y_lid - 6.0, y_lid + 0.01, x=x, z=z) for x, z in _cradle_boss_centres(p)]
    cut = union([servo_pocket(p, "+y")] + inserts)
    return solid, cut


def servo_lid(p: Params) -> Part:
    """Retaining lid for every servo cradle (servo frame, sits on y = W/2 + c)."""
    _, _, _, y1, _, _ = servo_extent(p)
    c = p.printer.fit_clearance
    y_lid = y1 + c
    cs = _cradle_boss_centres(p)
    xs = [x for x, _ in cs]
    zs = [z for _, z in cs]
    lid = box(min(xs) - _BOSS / 2, max(xs) + _BOSS / 2, y_lid, y_lid + LID_T, min(zs) - _BOSS / 2, max(zs) + _BOSS / 2)
    holes = [cyl_y(CLEARANCE_D[3.0] / 2, y_lid - 1, y_lid + LID_T + 1, x=x, z=z) for x, z in cs]
    # Window over the servo label/vent area keeps the lid light and lets the
    # cable be checked without removing it.
    x0, x1, _, _, z0, _ = servo_extent(p)
    window = box(x0 + 6.0, x1 - 6.0, y_lid - 1, y_lid + LID_T + 1, z0 + 7.0, -7.0)
    return lid - union(holes) - window


def horn_bolt_holes(p: Params, z0: float, z1: float) -> Part:
    """M2 clearance holes on the horn bolt circle plus a centre relief."""
    s = p.servo
    holes = [cyl_z(CLEARANCE_D[2.0] / 2, z0, z1, x, y) for x, y in bolt_circle(4, s.horn_bolt_circle_d, 45.0)]
    centre = cyl_z(3.2, z0, z1)
    return union(holes + [centre])


def horn_recess(p: Params, z0: float) -> Part:
    """Pocket that centres a part on the disc horn (horn face at z0, part above)."""
    s = p.servo
    return cyl_z(s.horn_d / 2 + p.printer.fit_clearance, z0 - s.horn_thickness - 0.01, z0)


def bearing_seat_y(b, p: Params, y_face: float, inward: int, x: float, z: float, through_d: float,
                   through_len: float = 40.0) -> Part:
    """Cut for a press-fit bearing whose outer face is flush at ``y_face`` and
    which extends ``inward`` (+1 or -1) along y, plus a coaxial through hole
    of ``through_d`` running ``through_len`` further inward (shoulder for
    the outer race is left by choosing through_d < b.od)."""
    od = b.od + 2 * p.printer.press_fit
    if inward > 0:
        seat = cyl_y(od / 2, y_face - 0.01, y_face + b.width, x=x, z=z)
        hole = cyl_y(through_d / 2, y_face, y_face + b.width + through_len, x=x, z=z)
    else:
        seat = cyl_y(od / 2, y_face - b.width, y_face + 0.01, x=x, z=z)
        hole = cyl_y(through_d / 2, y_face - b.width - through_len, y_face, x=x, z=z)
    return seat + hole
