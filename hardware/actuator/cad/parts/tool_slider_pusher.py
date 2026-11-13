"""Slider / rocker pusher: a passive tool (only the tool-ID resistor on its
contact PCB).  A stiff stem ends in a fork whose slot captures slider knobs
(<= 11 mm wide) and whose flat TPU-padded face pushes rockers and paddles.
"""

from __future__ import annotations

from build123d import Part

from common import box, prism_yz
from params import Params
from parts.tool_interface import collar_top, tool_plug

STEM = 18.0
STEM_LEN = 50.0
FORK_T = 6.0
TINE_LEN = 18.0
SLOT_W = 12.0


def _z(p: Params) -> dict[str, float]:
    ct = collar_top(p)
    return {"stem0": ct, "stem1": ct + STEM_LEN, "fork1": ct + STEM_LEN + FORK_T,
            "tine1": ct + STEM_LEN + FORK_T + TINE_LEN}


def tcp_z(p: Params) -> float:
    """TCP at the bottom of the fork slot (contact point with a slider knob)."""
    return _z(p)["fork1"]


def pusher_body(p: Params) -> Part:
    z = _z(p)
    plug = tool_plug(p)
    pw, ph = p.tools.pusher_pad
    stem = box(-STEM / 2, STEM / 2, -STEM / 2, STEM / 2, z["stem0"] - 0.01, z["stem1"])
    fork = box(-STEM / 2, STEM / 2, -pw / 2, pw / 2, z["stem1"], z["fork1"])
    # 45 deg gussets between stem and fork plate (printable without support).
    gus = prism_yz([(STEM / 2 - 0.01, z["stem1"] + 0.01), (pw / 2, z["stem1"] + 0.01), (STEM / 2 - 0.01, z["stem1"] - (pw - STEM) / 2)],
                   -STEM / 2, STEM / 2)
    gus += prism_yz([(-STEM / 2 + 0.01, z["stem1"] + 0.01), (-STEM / 2 + 0.01, z["stem1"] - (pw - STEM) / 2), (-pw / 2, z["stem1"] + 0.01)],
                    -STEM / 2, STEM / 2)
    tines = box(-STEM / 2, STEM / 2, SLOT_W / 2, pw / 2, z["fork1"] - 0.01, z["tine1"]) + box(
        -STEM / 2, STEM / 2, -pw / 2, -SLOT_W / 2, z["fork1"] - 0.01, z["tine1"])
    body = plug + stem + fork + gus + tines
    # Pad pocket on the +x face of the fork plate (TPU pad pushed in).
    body -= box(STEM / 2 - 2.0, STEM / 2 + 0.01, -pw / 2 + 1.0, pw / 2 - 1.0, z["stem1"] + 0.5, z["tine1"] - 0.5) - box(
        -STEM, STEM, -SLOT_W / 2, SLOT_W / 2, z["fork1"], z["tine1"] + 1)
    # Weight relief through the stem (x direction), keeps 3 mm walls.
    body -= box(-STEM / 2 - 1, STEM / 2 + 1, -STEM / 2 + 3.0, STEM / 2 - 3.0, z["stem0"] + 8.0, z["stem1"] - 10.0)
    return body


def pusher_pad(p: Params) -> Part:
    """TPU 95A face pad (two halves joined below the slot)."""
    z = _z(p)
    pw, _ = p.tools.pusher_pad
    pad = box(STEM / 2 - 2.0 + 0.15, STEM / 2 + 1.0, -pw / 2 + 1.15, pw / 2 - 1.15, z["stem1"] + 0.65, z["tine1"] - 0.65)
    pad -= box(STEM / 2 - 3, STEM / 2 + 2, -SLOT_W / 2 - 0.15, SLOT_W / 2 + 0.15, z["fork1"] - 0.15, z["tine1"])
    return pad
