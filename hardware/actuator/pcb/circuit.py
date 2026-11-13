"""Board description: components with library symbol/footprint, purchase
data, pin-to-net map and placement.  One instance describes a board
completely; the KiCad writers and the checks consume it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from kicadlib import Pad, Pin, footprint_pads, load_footprint, load_symbol, symbol_pins


@dataclass
class Part:
    ref: str
    symbol: str  # "Lib:Name"
    footprint: str  # "Lib:Name" (or "bhms:..." for generated footprints)
    value: str
    mpn: str
    manufacturer: str
    nets: dict[str, str]  # pin number or pin name -> net
    pos: tuple[float, float] = (0.0, 0.0)  # board mm (x right, y down)
    rot: float = 0.0
    dnp: bool = False
    note: str = ""
    unit_price_usd: float = 0.0
    price_source: str = "estimate"
    group: str = ""  # schematic block
    custom_footprint: list | None = None  # s-expression for generated footprints
    custom_symbol: list | None = None


@dataclass
class Board:
    name: str
    title: str
    size: tuple[float, float]  # width x height (mm) for rectangular boards
    parts: list[Part] = field(default_factory=list)
    outline: list | None = None  # optional list of (x, y) polygon / arcs for non-rect boards
    holes: list[tuple[float, float]] = field(default_factory=list)
    power_nets: dict[str, float] = field(default_factory=dict)  # net -> track width (mm)
    pwr_flag_nets: list[str] = field(default_factory=list)
    zone_nets: list[str] = field(default_factory=lambda: ["GND"])
    keepouts: list[tuple[float, float, float, float]] = field(default_factory=list)
    origin: tuple[float, float] = (100.0, 100.0)
    rev: str = "A"

    def part(self, ref: str) -> Part:
        for p in self.parts:
            if p.ref == ref:
                return p
        raise KeyError(ref)


class Resolved:
    """Pins of every part resolved to numbers, with the library data."""

    def __init__(self, board: Board):
        self.board = board
        self.sym: dict[str, list] = {}
        self.pins: dict[str, list[Pin]] = {}
        self.fp: dict[str, list] = {}
        self.pads: dict[str, list[Pad]] = {}
        self.pin_net: dict[str, dict[str, str]] = {}
        for p in board.parts:
            sym = p.custom_symbol if p.custom_symbol is not None else load_symbol(p.symbol)
            fp = p.custom_footprint if p.custom_footprint is not None else load_footprint(p.footprint)
            self.sym[p.ref] = sym
            self.fp[p.ref] = fp
            pins = symbol_pins(sym)
            self.pins[p.ref] = pins
            self.pads[p.ref] = footprint_pads(fp)
            by_num = {pin.number for pin in pins}
            mapping: dict[str, str] = {}
            for key, net in p.nets.items():
                if key in by_num:
                    mapping[key] = net
                    continue
                matched = [pin.number for pin in pins if pin.name == key]
                if not matched:
                    raise KeyError(f"{p.ref}: no pin {key!r} in {p.symbol}")
                for num in matched:
                    mapping[num] = net
            self.pin_net[p.ref] = mapping

    def nets(self) -> dict[str, list[tuple[str, str]]]:
        out: dict[str, list[tuple[str, str]]] = {}
        for ref, m in self.pin_net.items():
            for num, net in m.items():
                if net:
                    out.setdefault(net, []).append((ref, num))
        return dict(sorted(out.items()))

    def pad_world(self, ref: str, pad: Pad) -> tuple[float, float]:
        part = self.board.part(ref)
        x, y = rotate(pad.x, pad.y, part.rot)
        return part.pos[0] + x, part.pos[1] + y


def rotate(x: float, y: float, deg: float) -> tuple[float, float]:
    """KiCad footprint rotation (counter-clockwise on screen, y down)."""
    a = math.radians(deg)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


def erc(res: Resolved) -> list[str]:
    """Electrical rule checks on the netlist itself (independent of KiCad):
    every net has >= 2 pins, every power-input pin is connected, no
    symbol pin is left unassigned unless it is a no-connect pin, and
    every footprint pad with a number maps to a symbol pin."""
    problems = []
    for net, nodes in res.nets().items():
        if len(nodes) < 2:
            problems.append(f"net {net} has a single pin {nodes}")
    for p in res.board.parts:
        assigned = res.pin_net[p.ref]
        for pin in res.pins[p.ref]:
            if pin.etype == "no_connect":
                continue
            if pin.number not in assigned:
                problems.append(f"{p.ref} pin {pin.number} ({pin.name}, {pin.etype}) unconnected")
            elif pin.etype.startswith("power_in") and not assigned[pin.number]:
                problems.append(f"{p.ref} power pin {pin.number} not connected")
        pin_nums = {pin.number for pin in res.pins[p.ref]}
        for pad in res.pads[p.ref]:
            if pad.number and pad.number not in pin_nums:
                problems.append(f"{p.ref} footprint pad {pad.number} has no symbol pin")
    return problems
