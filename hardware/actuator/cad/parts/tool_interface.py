"""Tool side of the quick-change flange, shared by every end effector.

Tool frame: origin on the flange face (socket floor) when locked, +z away
from the arm.  The plug carries:

* a lip (z 0..lip_height) with three entry notches; the arm-side lugs pass
  the notches, then a +30 deg roll locks the lip under the lugs;
* the tool contact PCB (6 ENIG pads facing -z, tool-ID resistor, optional
  3.3 V LDO / AS5600 / sensor divider) bonded in a keyed recess;
* an arc slot for the stop pin (sets the locked angle) and a detent dimple;
* a collar with a groove and key notch so the tool rack can hold the tool
  against rotation while the arm twists the bayonet.
"""

from __future__ import annotations

import math

from build123d import Part, Pos, Rot

from common import box, cyl_z, prism_xy
from params import Params


def _arc_pts(r: float, a0: float, a1: float, n: int = 12) -> list[tuple[float, float]]:
    return [(r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def _annular_sector(r0: float, r1: float, a0: float, a1: float, z0: float, z1: float) -> Part:
    pts = _arc_pts(r1, a0, a1) + list(reversed(_arc_pts(r0, a0, a1)))
    return prism_xy(pts, z0, z1)


def collar_top(p: Params) -> float:
    return p.flange.collar_z0 + p.flange.collar_height


def contact_pcb_flat(p: Params) -> tuple[float, float]:
    """(distance, angle deg) of the keying flat on the contact PCB / recess."""
    return p.flange.contact_pcb_flat_dist, p.flange.contact_pcb_flat_angle_deg


def tool_plug(p: Params, bore: float = 22.0) -> Part:
    """``bore`` leaves room for the components on the contact PCB's inner
    face (they must stay inside r = bore/2 - 0.5)."""
    f = p.flange
    lock = f.lock_angle_deg
    r_lip = f.plug_od / 2
    r_neck = f.socket_id / 2 - f.lug_radial - f.neck_clearance
    lip = cyl_z(r_lip, 0.0, f.lip_height)
    # 0.8 mm lead-in chamfer on the lip bottom edge (ball plunger ride-up).
    lip -= cyl_z(r_lip + 1, -0.01, 0.8) - cyl_z(r_lip - 0.8, -0.02, 0.81)
    neck = cyl_z(r_neck, f.lip_height, f.collar_z0 + 0.01)
    zc0, zc1 = f.collar_z0, collar_top(p)
    g0, g1, gr = f.collar_groove
    collar = cyl_z(f.collar_r, zc0, zc1) - (cyl_z(f.collar_r + 1, g0, g1) - cyl_z(gr, g0 - 0.01, g1 + 0.01))
    # Key notch in the groove floor at tool angle +90 deg.
    collar -= box(-f.rack_key_w / 2 - 0.2, f.rack_key_w / 2 + 0.2, gr - 3.0, f.collar_r + 1, g0, g1)
    plug = lip + neck + collar
    # Lip entry notches: lugs (flange angle L) pass at insertion, when the
    # tool is rotated +lock relative to the flange, so notches sit at L - lock.
    for lug in f.lug_angles_deg:
        a = lug - lock
        half = f.lug_width_deg / 2 + 2.0
        plug -= _annular_sector(r_neck - 0.5, r_lip + 1.0, a - half, a + half, -0.01, f.lip_height)
    # Stop-pin arc slot: pin (flange angle 0) is at tool angle -lock during
    # insertion and 0 when locked; the slot end at 0 is the rotation stop.
    pin_half = math.degrees((f.stop_pin_d / 2 + 0.25) / f.stop_pin_r)
    plug -= _annular_sector(f.stop_pin_r - f.stop_pin_d / 2 - 0.25, f.stop_pin_r + f.stop_pin_d / 2 + 0.25,
                            -lock - pin_half - 2.0, pin_half, -0.01, 3.4)
    # Detent dimple for the ball plunger at the locked angle.
    plug -= Pos(0, 0, f.detent_z) * Rot(Z=f.detent_angle_deg) * Pos(r_lip, 0, 0) * Rot(Y=90) * cyl_z(1.3, -0.8, 1.0)
    # Contact PCB recess (keyed with a flat) and the wiring bore.
    pcb_r = f.contact_pcb_d / 2 + 0.2
    dist, ang = contact_pcb_flat(p)
    recess = cyl_z(pcb_r, -0.01, f.contact_pcb_t) - Rot(Z=ang) * box(dist + 0.2, pcb_r + 1, -pcb_r - 1, pcb_r + 1, -1, 3)
    plug -= recess
    plug -= cyl_z(bore / 2, f.contact_pcb_t - 0.01, zc1 + 0.01)
    return plug


def rack_slot_profile(p: Params) -> tuple[float, float]:
    """(slot width, groove height) the tool rack fork must match."""
    g0, g1, gr = p.flange.collar_groove
    return 2 * gr + 0.6, g1 - g0 - 0.4


def wire_channel(p: Params, x_end: float, y: float = 0.0) -> Part:
    """Cut: radial wiring channel from the plug bore out along -x in the
    top 3 mm of the collar (above the rack groove), for tools whose
    harness leaves the plug sideways under the body."""
    ct = collar_top(p)
    return box(x_end, 0.0, y - 4.0, y + 4.0, ct - 3.0, ct + 0.01)
