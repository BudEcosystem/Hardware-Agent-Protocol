"""Fixtures that are not links: the tool rack (automatic tool change), a
snap-in cable clip for the link grooves, and a printer tolerance coupon.

Tool rack frame: z = 0 is the table; the fork plate is horizontal at
``RACK_Z``.  Tools hang plug-up (tool frame rotated 180 deg about y), the
collar groove riding on the fork plate and the key tab in the collar notch.
To dock, the arm brings a tool in along +y; to pick, it descends onto the
plug, rolls +30 deg (lock), then withdraws along -y.
"""

from __future__ import annotations

from build123d import Part

from common import CLEARANCE_D, box, cyl_z, prism_xy, union
from params import BEARING_608, BEARING_624, Params
from parts.tool_interface import rack_slot_profile

RACK_PITCH = 100.0
RACK_SLOTS = 4
RACK_Z = 175.0  # fork plate mid-plane above the table (longest tool hangs ~150 mm)
RACK_DEPTH = 70.0
LIP_W = 6.0
PLATE_T = 8.0


def rack_slot_centres() -> list[tuple[float, float]]:
    """(x, y) of each fork's tool axis in the rack frame."""
    x0 = -RACK_PITCH * (RACK_SLOTS - 1) / 2
    return [(x0 + i * RACK_PITCH, 0.0) for i in range(RACK_SLOTS)]


def tool_rack(p: Params) -> Part:
    slot_w, lip_t = rack_slot_profile(p)
    f = p.flange
    half_len = RACK_PITCH * RACK_SLOTS / 2
    z_mid = RACK_Z
    # Thin lip (rides in the collar groove) around every slot, thick plate
    # beyond the collar radius.
    lip = box(-half_len, half_len, -RACK_DEPTH / 2, RACK_DEPTH / 2, z_mid - lip_t / 2, z_mid + lip_t / 2)
    thick = box(-half_len, half_len, -RACK_DEPTH / 2, RACK_DEPTH / 2, z_mid - lip_t / 2 - PLATE_T, z_mid - lip_t / 2)
    plate = lip + thick
    for x, y in rack_slot_centres():
        r = slot_w / 2
        slot = cyl_z(r, z_mid - 20, z_mid + 20, x, y) + box(x - r, x + r, -RACK_DEPTH, y, z_mid - 20, z_mid + 20)
        plate -= slot
        # Collar clearance in the thick part (collar radius + 1 mm).
        rc = f.collar_r + 1.0
        plate -= cyl_z(rc, z_mid - lip_t / 2 - PLATE_T - 1, z_mid - lip_t / 2 + 0.01, x, y) + box(
            x - rc, x + rc, -RACK_DEPTH, y, z_mid - lip_t / 2 - PLATE_T - 1, z_mid - lip_t / 2 + 0.01)
        # Anti-rotation key at the closed end (+y), fits the collar notch.
        g0, g1, gr = f.collar_groove
        plate += box(x - f.rack_key_w / 2, x + f.rack_key_w / 2, y + gr - 2.5, y + r + 0.01, z_mid - lip_t / 2, z_mid + lip_t / 2)
        # Lead-in chamfer on the slot mouth.
        mouth = prism_xy([(x - r - 6, -RACK_DEPTH / 2 - 0.01), (x + r + 6, -RACK_DEPTH / 2 - 0.01), (x + r, -RACK_DEPTH / 2 + 6),
                          (x - r, -RACK_DEPTH / 2 + 6)], z_mid - 20, z_mid + 20)
        plate -= mouth
    # Two legs with feet (screw to the bench or clamp).
    legs = []
    for sx in (-1, 1):
        x0 = sx * half_len
        xl0, xl1 = sorted((x0, x0 - sx * 10.0))
        legs.append(box(xl0, xl1, -RACK_DEPTH / 2, RACK_DEPTH / 2, 0.0, z_mid + lip_t / 2))
        foot = box(xl0 - (25.0 if sx < 0 else 0.0), xl1 + (25.0 if sx > 0 else 0.0), -RACK_DEPTH / 2, RACK_DEPTH / 2, 0.0, 6.0)
        for yy in (-RACK_DEPTH / 2 + 10, RACK_DEPTH / 2 - 10):
            foot -= cyl_z(CLEARANCE_D[5.0] / 2, -1, 7, x0 + sx * 15.0, yy)
        legs.append(foot)
    # Back rail ties the legs together (stiffness against the roll twist).
    rail = box(-half_len, half_len, RACK_DEPTH / 2 - 8.0, RACK_DEPTH / 2, 0.0, 12.0)
    return union([plate, rail] + legs)


def cable_clip(p: Params) -> Part:
    """Snap clip that closes the rear cable groove of a link (print 8)."""
    a = p.arm
    cw, cd = a.cable_channel
    w = a.link_width
    clip = box(-1.6, 0.0, -w / 2 - 2.0, w / 2 + 2.0, 0.0, 4.6)
    for s in (-1, 1):
        clip += box(-1.6, 3.0, s * (w / 2 + 2.0) - (2.0 if s > 0 else 0.0), s * (w / 2 + 2.0) + (0.0 if s > 0 else 2.0), 0.0, 4.6)
        # Barb that hooks behind the link side face.
        y_in = s * (w / 2 + 0.05)
        y0, y1 = sorted((y_in, y_in - s * 0.6))
        clip += box(2.2, 3.0, y0, y1, 0.0, 4.6)
    return clip


def tolerance_coupon(p: Params) -> Part:
    """Bearing seats and insert holes at the configured fits, to tune
    ``Printer.press_fit`` / ``fit_clearance`` before printing the arm."""
    pf = p.printer.press_fit
    plate = box(0.0, 120.0, 0.0, 40.0, 0.0, 8.0)
    x = 14.0
    for b in (BEARING_608, BEARING_624):
        for delta in (-0.1, 0.0, 0.1):
            r = b.od / 2 + pf + delta
            plate -= cyl_z(r, 1.0, 8.01, x, 20.0)
            plate -= cyl_z(max(b.od / 2 - 2.0, 2.0), -0.01, 1.01, x, 20.0)
            x += b.od / 2 + 9.0 if b is BEARING_608 else b.od / 2 + 6.0
    return plate
