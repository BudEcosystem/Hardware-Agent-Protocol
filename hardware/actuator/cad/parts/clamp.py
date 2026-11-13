"""Printed table-edge C-clamp for the base tongue.

Frame: world.  The top jaw presses the base-plate tongue onto the table
around the locating pin at ``CLAMP_PIN_X``; an M8 x 60 hex bolt (head in
the printed knob) runs up through a captive nut in the lower jaw and
pushes the swivel pad against the underside of the table.
"""

from __future__ import annotations

import math

from build123d import Part

from common import CLEARANCE_D, NUT_AF, NUT_T, box, cyl_z, hex_prism_z, prism_xy, prism_xz
from params import Params
from parts.base import CLAMP_PIN_X, PLATE_T

JAW_T = 14.0
SPINE_T = 14.0


def _frame(p: Params) -> tuple[float, float, float, float]:
    """(pin_x, z_top_of_tongue, x_spine_inner, z_lower_jaw_top)."""
    c = p.clamp
    x_inner = CLAMP_PIN_X - c.throat
    z_lower = -c.table_max - 6.0  # 6 mm of screw/pad travel below the thickest table
    return CLAMP_PIN_X, PLATE_T, x_inner, z_lower


def screw_axis_x(p: Params) -> float:
    pin_x, _, x_inner, _ = _frame(p)
    return x_inner + 22.0


def clamp_body(p: Params) -> Part:
    c = p.clamp
    pin_x, zt, x_in, z_low = _frame(p)
    w = c.width / 2
    x_out = x_in - SPINE_T
    top = box(x_out, pin_x + 12.0, -w, w, zt, zt + JAW_T)
    spine = box(x_out, x_in, -w, w, z_low - JAW_T, zt + JAW_T)
    lower = box(x_out, screw_axis_x(p) + 14.0, -w, w, z_low - JAW_T, z_low)
    # Gussets in the two inside corners (45 deg, 12 mm legs).
    g = 12.0
    gussets = prism_xz([(x_in, zt), (x_in + g, zt), (x_in, zt - g)], -w, w) + prism_xz(
        [(x_in, z_low), (x_in + g, z_low), (x_in, z_low + g)], -w, w)
    body = top + spine + lower + gussets
    # Locating pin into the tongue hole (8.8 mm in a 9.2 mm hole).
    body += cyl_z(4.4, zt - PLATE_T + 1.0, zt + 0.01, x=pin_x)
    # Captive M8 nut from above (inside the throat) and the bolt hole.
    sx = screw_axis_x(p)
    body -= cyl_z(CLEARANCE_D[8.0] / 2, z_low - JAW_T - 1, z_low + 1, x=sx)
    body -= hex_prism_z(NUT_AF[8.0] + 0.4, z_low - NUT_T[8.0] - 0.5, z_low + 0.01, x=sx)
    return body


def clamp_pad(p: Params) -> Part:
    """Swivel pad: sits on the bolt tip, TPU or PLA with a cork facing."""
    pad = cyl_z(14.0, 0.0, 6.0) + cyl_z(8.0, -8.0, 0.0)
    pad -= cyl_z(4.25, -8.01, -1.5)  # M8 tip pocket (bolt end sits here, greased)
    return pad


def clamp_knob(p: Params) -> Part:
    """Knob that captures the M8 hex bolt head (13 mm AF)."""
    r = 20.0
    lobes = 6
    pts = []
    for i in range(72):
        a = 2 * math.pi * i / 72
        rr = r - 2.5 * (0.5 + 0.5 * math.cos(lobes * a))
        pts.append((rr * math.cos(a), rr * math.sin(a)))
    knob = prism_xy(pts, 0.0, 16.0)
    # ISO 4017 M8 hex head: 13 mm AF, 5.3 mm tall; press in (or glue).
    knob -= hex_prism_z(NUT_AF[8.0] + 0.3, 16.0 - 5.5, 16.01)
    knob -= cyl_z(CLEARANCE_D[8.0] / 2, -0.01, 16.01)
    return knob
