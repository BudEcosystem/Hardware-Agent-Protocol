"""Load symbols and footprints from the stock KiCad libraries.

Library locations come from the environment (as set by KiCad itself):
``KICAD_SYMBOL_DIR`` / ``KICAD_FOOTPRINT_DIR``, falling back to the
``KICAD10_*``/``KICAD9_*``/``KICAD8_*`` variants and /usr/share/kicad.
Generated boards and schematics embed what they use, so the outputs do
not depend on these paths.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sexpr import Q, find, find_all, loads


def _dir(kind: str) -> Path:
    for var in (f"KICAD_{kind}_DIR", f"KICAD10_{kind}_DIR", f"KICAD9_{kind}_DIR", f"KICAD8_{kind}_DIR"):
        if os.environ.get(var):
            return Path(os.environ[var])
    return Path("/usr/share/kicad") / ("symbols" if kind == "SYMBOL" else "footprints")


@lru_cache(maxsize=None)
def _symbol_lib(lib: str) -> dict[str, list]:
    path = _dir("SYMBOL") / f"{lib}.kicad_sym"
    tree = loads(path.read_text())
    return {str(s[1]): s for s in find_all(tree, "symbol")}


def _prop(sym: list, name: str) -> list | None:
    for p in find_all(sym, "property"):
        if str(p[1]) == name:
            return p
    return None


def load_symbol(lib_id: str) -> list:
    """Return a flattened copy of ``Lib:Name`` ready for ``lib_symbols``."""
    lib, name = lib_id.split(":", 1)
    syms = _symbol_lib(lib)
    sym = copy.deepcopy(syms[name])
    ext = find(sym, "extends")
    if ext is not None:
        parent = load_symbol(f"{lib}:{ext[1]}")
        pname = str(parent[1]).split(":", 1)[1]
        child_props = {str(p[1]): p for p in find_all(sym, "property")}
        out = [x for x in parent if not (isinstance(x, list) and x and x[0] in ("property", "symbol"))]
        for p in find_all(parent, "property"):
            out.append(child_props.pop(str(p[1]), p))
        out += list(child_props.values())
        for unit in find_all(parent, "symbol"):
            u = copy.deepcopy(unit)
            u[1] = Q(str(u[1]).replace(pname, name, 1))
            out.append(u)
        sym = out
    sym[1] = Q(lib_id)
    return sym


@dataclass(frozen=True)
class Pin:
    number: str
    name: str
    etype: str
    x: float
    y: float
    angle: float
    length: float
    unit: int
    hidden: bool


def symbol_pins(sym: list) -> list[Pin]:
    pins: list[Pin] = []
    for unit in find_all(sym, "symbol"):
        uname = str(unit[1])
        try:
            unit_no = int(uname.rsplit("_", 2)[-2])
        except ValueError:
            unit_no = 0
        for p in find_all(unit, "pin"):
            at = find(p, "at")
            num = find(p, "number")
            nm = find(p, "name")
            ln = find(p, "length")
            hidden = any(x == "hide" for x in p) or (find(p, "hide") is not None and find(p, "hide")[1] == "yes")
            pins.append(Pin(str(num[1]), str(nm[1]), str(p[1]), float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0,
                            float(ln[1]), unit_no, hidden))
    return pins


def symbol_default_footprint(sym: list) -> str:
    p = _prop(sym, "Footprint")
    return str(p[2]) if p is not None else ""


def load_footprint(lib_id: str) -> list:
    lib, name = lib_id.split(":", 1)
    path = _dir("FOOTPRINT") / f"{lib}.pretty" / f"{name}.kicad_mod"
    return loads(path.read_text())


@dataclass(frozen=True)
class Pad:
    number: str
    kind: str  # smd / thru_hole / np_thru_hole / connect
    shape: str
    x: float
    y: float
    rot: float
    w: float
    h: float
    layers: tuple[str, ...]
    drill: float


def footprint_pads(fp: list) -> list[Pad]:
    pads = []
    for p in find_all(fp, "pad"):
        at = find(p, "at")
        size = find(p, "size")
        layers = find(p, "layers")
        drill = find(p, "drill")
        d = 0.0
        if drill is not None:
            nums = [x for x in drill[1:] if not isinstance(x, list) and x != "oval"]
            d = float(nums[0]) if nums else 0.0
        pads.append(Pad(str(p[1]), str(p[2]), str(p[3]), float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0,
                        float(size[1]), float(size[2]), tuple(str(x) for x in layers[1:]), d))
    return pads


def courtyard_bbox(fp: list, layer: str = "F.CrtYd") -> tuple[float, float, float, float] | None:
    """Axis-aligned bounding box (footprint-local) of the courtyard layer."""
    xs: list[float] = []
    ys: list[float] = []
    for item in fp:
        if not isinstance(item, list) or not item or item[0] not in ("fp_line", "fp_rect", "fp_circle", "fp_poly", "fp_arc"):
            continue
        ly = find(item, "layer")
        if ly is None or str(ly[1]) != layer:
            continue
        if item[0] == "fp_circle":
            c, e = find(item, "center"), find(item, "end")
            r = ((float(e[1]) - float(c[1])) ** 2 + (float(e[2]) - float(c[2])) ** 2) ** 0.5
            xs += [float(c[1]) - r, float(c[1]) + r]
            ys += [float(c[2]) - r, float(c[2]) + r]
        elif item[0] == "fp_poly":
            for xy in find_all(find(item, "pts"), "xy"):
                xs.append(float(xy[1]))
                ys.append(float(xy[2]))
        else:
            for key in ("start", "end", "mid"):
                pt = find(item, key)
                if pt is not None:
                    xs.append(float(pt[1]))
                    ys.append(float(pt[2]))
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)
