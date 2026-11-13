"""Write KiCad 8 format schematic (.kicad_sch, version 20231120), board
(.kicad_pcb, version 20240108) and project (.kicad_pro) files.

Library content is copied from the installed KiCad libraries; tokens
introduced after KiCad 8 are stripped so the files stay KiCad-8 readable.
UUIDs are derived deterministically from names (uuid5), so regeneration
gives identical files.
"""

from __future__ import annotations

import copy
import json
import math
import uuid
from pathlib import Path

from circuit import Board, Resolved
from kicadlib import load_symbol
from sexpr import Q, dumps, find, find_all

NS = uuid.UUID("6f1c9c2e-6b38-4c1b-9d55-0f3f2a7e5b10")
POST_V8_TOKENS = {"embedded_fonts", "embedded_files", "duplicate_pad_numbers_are_jumpers",
                  "duplicate_pin_numbers_are_jumpers", "jumper_pad_groups", "jumper_pin_groups", "in_pos_files",
                  "show_name", "do_not_autoplace", "tenting", "covering", "plugging", "filling", "capping",
                  "component_classes", "unit_name", "body_style"}
GRID = 2.54


def uid(*parts: str) -> Q:
    return Q(str(uuid.uuid5(NS, "/".join(parts))))


def sanitize(node):
    if not isinstance(node, list):
        return node
    out = []
    for x in node:
        if isinstance(x, list) and x and x[0] in POST_V8_TOKENS:
            continue
        out.append(sanitize(x))
    return out


def snap(v: float) -> float:
    return round(v / GRID) * GRID


# ---------------------------------------------------------------------------
# Schematic
# ---------------------------------------------------------------------------


def _effects(size: float = 1.27, hide: bool = False, justify: str | None = None) -> list:
    e = ["effects", ["font", ["size", size, size]]]
    if justify:
        e.append(["justify"] + justify.split())
    if hide:
        e.append(["hide", "yes"])
    return e


def _sym_bbox(pins) -> tuple[float, float, float, float]:
    if not pins:
        return (-2.54, -2.54, 2.54, 2.54)
    xs = [p.x for p in pins]
    ys = [p.y for p in pins]
    return min(xs), min(ys), max(xs), max(ys)


def _unhide_power_pins(sym: list) -> list:
    """Hidden power-input pins would join an implicit global net named after
    the pin; every net here is explicit, so make them ordinary pins."""
    sym = copy.deepcopy(sym)
    for unit in find_all(sym, "symbol"):
        for pin in find_all(unit, "pin"):
            if "hide" in pin:
                pin.remove("hide")
            h = find(pin, "hide")
            if h is not None:
                pin.remove(h)
    return sym


def write_schematic(board: Board, res: Resolved, path: Path, project: str) -> None:
    root_uuid = uid(board.name, "schematic")
    lib_symbols = ["lib_symbols"]
    seen = set()
    for p in board.parts:
        if p.symbol not in seen:
            seen.add(p.symbol)
            lib_symbols.append(sanitize(_unhide_power_pins(res.sym[p.ref])))
    flag = None
    if board.pwr_flag_nets:
        flag = load_symbol("power:PWR_FLAG")
        lib_symbols.append(sanitize(flag))

    items: list = []
    groups: dict[str, list] = {}
    for p in board.parts:
        groups.setdefault(p.group or "misc", []).append(p)

    # Lay groups out in columns; each part gets a cell sized by its pins.
    x0, y0 = 30.48, 30.48
    col_x = x0
    max_y = 0.0
    col_w = 0.0
    y = y0
    page_h = 400.0
    for gname, parts in groups.items():
        items.append(["text", Q(f"{gname}"), ["exclude_from_sim", "no"], ["at", snap(col_x), snap(y - 7.62), 0],
                      _effects(2.54, justify="left bottom"), ["uuid", uid(board.name, "grp", gname)]])
        for p in parts:
            pins = res.pins[p.ref]
            bx0, by0, bx1, by1 = _sym_bbox(pins)
            w = (bx1 - bx0) + 30.0
            h = (by1 - by0) + 12.7
            if y + h > page_h:
                col_x += col_w + 10.16
                col_w = 0.0
                y = y0
            sx = snap(col_x - bx0 + 15.24)
            sy = snap(y + by1 + 5.08)
            items += _place_symbol(board, res, p, sx, sy, root_uuid, project)
            y += h
            col_w = max(col_w, w)
            max_y = max(max_y, y)
        y += 12.7
    if flag is not None:
        for i, net in enumerate(board.pwr_flag_nets):
            fx = snap(col_x + col_w + 20.32)
            fy = snap(y0 + i * 12.7)
            ref = f"#FLG{i + 1:02d}"
            u = uid(board.name, "flag", net)
            items.append(["symbol", ["lib_id", Q("power:PWR_FLAG")], ["at", fx, fy, 0], ["unit", 1],
                          ["exclude_from_sim", "no"], ["in_bom", "no"], ["on_board", "no"], ["dnp", "no"], ["uuid", u],
                          ["property", Q("Reference"), Q(ref), ["at", fx, fy - 3.81, 0], _effects(hide=True)],
                          ["property", Q("Value"), Q("PWR_FLAG"), ["at", fx, fy - 5.08, 0], _effects()],
                          ["property", Q("Footprint"), Q(""), ["at", fx, fy, 0], _effects(hide=True)],
                          ["property", Q("Datasheet"), Q(""), ["at", fx, fy, 0], _effects(hide=True)],
                          ["pin", Q("1"), ["uuid", uid(board.name, "flag", net, "pin")]],
                          ["instances", ["project", Q(project), ["path", Q(f"/{root_uuid}"), ["reference", Q(ref)], ["unit", 1]]]]])
            # PWR_FLAG pin 1 is at the symbol origin; a stub down to a label.
            items.append(_wire(board.name, f"flag{net}", fx, fy, fx, fy + GRID))
            items.append(_label(board.name, f"flag{net}", net, fx, fy + GRID, 270))
    width = max(594.0, col_x + col_w + 60.0)
    paper = "A1" if width > 594.0 else "A2"
    sch = ["kicad_sch", ["version", 20231120], ["generator", Q("bhms_pcb_gen")], ["generator_version", Q("1.0")],
           ["uuid", root_uuid], ["paper", Q(paper)],
           ["title_block", ["title", Q(board.title)], ["rev", Q(board.rev)], ["company", Q("BHMS project")],
            ["comment", 1, Q("Generated by hardware/actuator/pcb/build.py - do not edit by hand")]],
           lib_symbols] + items + [["sheet_instances", ["path", Q("/"), ["page", Q("1")]]]]
    path.write_text(dumps(sch) + "\n")


def _wire(bname: str, key: str, x1, y1, x2, y2) -> list:
    return ["wire", ["pts", ["xy", round(x1, 4), round(y1, 4)], ["xy", round(x2, 4), round(y2, 4)]],
            ["stroke", ["width", 0], ["type", "default"]], ["uuid", uid(bname, "wire", key)]]


def _label(bname: str, key: str, net: str, x, y, angle) -> list:
    just = {0: "left bottom", 90: "left bottom", 180: "right bottom", 270: "right bottom"}[angle]
    return ["label", Q(net), ["at", round(x, 4), round(y, 4), angle], ["fields_autoplaced", "yes"],
            _effects(justify=just), ["uuid", uid(bname, "label", key)]]


def _place_symbol(board: Board, res: Resolved, p, sx: float, sy: float, root_uuid, project: str) -> list:
    out = []
    u = uid(board.name, "sym", p.ref)
    props = [
        ("Reference", p.ref, False), ("Value", p.value, False), ("Footprint", p.footprint, True),
        ("Datasheet", "", True), ("Description", p.note, True), ("MPN", p.mpn, True), ("Manufacturer", p.manufacturer, True),
    ]
    sym = ["symbol", ["lib_id", Q(p.symbol)], ["at", sx, sy, 0], ["unit", 1], ["exclude_from_sim", "no"],
           ["in_bom", "yes" if p.mpn else "no"], ["on_board", "yes"], ["dnp", "yes" if p.dnp else "no"],
           ["fields_autoplaced", "yes"],
           ["uuid", u]]
    pins = res.pins[p.ref]
    bx0, by0, bx1, by1 = _sym_bbox(pins)
    for i, (name, val, hide) in enumerate(props):
        sym.append(["property", Q(name), Q(val), ["at", sx + bx1 + 3.0, sy - by1 - 2.54 + i * 2.54, 0],
                    _effects(hide=hide, justify="left")])
    for pin in pins:
        sym.append(["pin", Q(pin.number), ["uuid", uid(board.name, "pin", p.ref, pin.number)]])
    sym.append(["instances", ["project", Q(project), ["path", Q(f"/{root_uuid}"), ["reference", Q(p.ref)], ["unit", 1]]]])
    out.append(sym)
    nets = res.pin_net[p.ref]
    done = set()
    for pin in pins:
        if pin.etype == "no_connect":
            continue
        ex, ey = sx + pin.x, sy - pin.y
        key = (round(ex, 3), round(ey, 3))
        if key in done:  # stacked pins share one connection point
            continue
        done.add(key)
        net = nets.get(pin.number, "")
        if not net:
            out.append(["no_connect", ["at", round(ex, 4), round(ey, 4)], ["uuid", uid(board.name, "nc", p.ref, pin.number)]])
            continue
        a = math.radians(pin.angle)
        dx, dy = -math.cos(a), math.sin(a)  # outward, sheet coordinates (y down)
        tx, ty = ex + dx * GRID, ey + dy * GRID
        out.append(_wire(board.name, f"{p.ref}.{pin.number}", ex, ey, tx, ty))
        ang = 0 if dx > 0.5 else 180 if dx < -0.5 else 90 if dy < 0 else 270
        out.append(_label(board.name, f"{p.ref}.{pin.number}", net, tx, ty, ang))
    return out


# ---------------------------------------------------------------------------
# Board
# ---------------------------------------------------------------------------

LAYERS = ["layers", [0, Q("F.Cu"), "signal"], [31, Q("B.Cu"), "signal"], [32, Q("B.Adhes"), "user", Q("B.Adhesive")],
          [33, Q("F.Adhes"), "user", Q("F.Adhesive")], [34, Q("B.Paste"), "user"], [35, Q("F.Paste"), "user"],
          [36, Q("B.SilkS"), "user", Q("B.Silkscreen")], [37, Q("F.SilkS"), "user", Q("F.Silkscreen")],
          [38, Q("B.Mask"), "user"], [39, Q("F.Mask"), "user"], [40, Q("Dwgs.User"), "user", Q("User.Drawings")],
          [41, Q("Cmts.User"), "user", Q("User.Comments")], [42, Q("Eco1.User"), "user", Q("User.Eco1")],
          [43, Q("Eco2.User"), "user", Q("User.Eco2")], [44, Q("Edge.Cuts"), "user"], [45, Q("Margin"), "user"],
          [46, Q("B.CrtYd"), "user", Q("B.Courtyard")], [47, Q("F.CrtYd"), "user", Q("F.Courtyard")],
          [48, Q("B.Fab"), "user"], [49, Q("F.Fab"), "user"]]


def net_table(res: Resolved) -> dict[str, int]:
    names = sorted(res.nets().keys(), key=lambda n: (n != "GND", n)) + nc_nets(res)
    return {n: i + 1 for i, n in enumerate(names)}


def nc_name(ref: str, pin_name: str, pad: str) -> str:
    """KiCad's net name for an unconnected symbol pin."""
    return f"unconnected-({ref}-{pin_name}-Pad{pad})"


def nc_nets(res: Resolved) -> list[str]:
    out = []
    for p in res.board.parts:
        for pin in res.pins[p.ref]:
            if not res.pin_net[p.ref].get(pin.number):
                out.append(nc_name(p.ref, pin.name, pin.number))
    return sorted(set(out))


def kname(net: str) -> str:
    """Board net name: KiCad names root-sheet local-label nets "/NAME"."""
    return f"/{net}"


def _place_footprint(board: Board, res: Resolved, p, nets: dict[str, int]) -> list:
    fp = sanitize(copy.deepcopy(res.fp[p.ref]))
    ox, oy = board.origin
    x, y = ox + p.pos[0], oy + p.pos[1]
    out = ["footprint", Q(p.footprint)]
    rest = [n for n in fp[2:] if not (isinstance(n, list) and n and n[0] in ("version", "generator", "generator_version"))]
    pin_net = res.pin_net[p.ref]
    pin_names = {pin.number: pin.name for pin in res.pins[p.ref]}
    layer = find(fp, "layer")
    out.append(layer if layer is not None else ["layer", Q("F.Cu")])
    out.append(["uuid", uid(board.name, "fp", p.ref)])
    out.append(["at", round(x, 4), round(y, 4)] + ([p.rot] if p.rot else []))
    for n in rest:
        if not isinstance(n, list) or not n:
            continue
        if n[0] == "layer":
            continue
        if n[0] == "property":
            name = str(n[1])
            if name == "Reference":
                n[2] = Q(p.ref)
            elif name == "Value":
                n[2] = Q(p.value)
            elif name == "Footprint":
                n[2] = Q(p.footprint)
            elif name == "Datasheet":
                n[2] = Q("")
            elif name == "Description":
                n[2] = Q(p.note)
            _rot_at(n, p.rot)
            n.append(["uuid", uid(board.name, "fpprop", p.ref, name)])
        elif n[0] in ("fp_text",):
            _rot_at(n, p.rot)
        elif n[0] == "pad":
            _rot_at(n, p.rot, force=True)
            num = str(n[1])
            net = pin_net.get(num, "")
            if net:
                n.append(["net", nets[net], Q(kname(net))])
            elif num in pin_names:
                ncn = nc_name(p.ref, pin_names[num], num)
                n.append(["net", nets[ncn], Q(ncn)])
            n.append(["uuid", uid(board.name, "pad", p.ref, num, str(len(out)))])
        out.append(n)
    have = {str(x[1]) for x in out if isinstance(x, list) and x and x[0] == "property"}
    for fname, fval in (("Datasheet", ""), ("Description", p.note), ("MPN", p.mpn), ("Manufacturer", p.manufacturer)):
        if fname not in have:
            out.append(["property", Q(fname), Q(fval), ["at", 0, 0, 0], ["layer", Q("F.Fab")], ["hide", "yes"],
                        ["uuid", uid(board.name, "fpprop", p.ref, fname)], _effects(hide=True)])
    if not p.mpn:  # mechanical / pads: not purchased, matches symbol in_bom
        attr = find(out, "attr")
        if attr is None:
            out.append(["attr", "smd", "exclude_from_bom"])
        elif "exclude_from_bom" not in attr:
            attr.append("exclude_from_bom")
    if p.dnp:
        attr = find(out, "attr")
        if attr is None:
            out.append(["attr", "smd", "dnp"])
        elif "dnp" not in attr:
            attr.append("dnp")
    return out


def _rot_at(node: list, rot: float, force: bool = False) -> None:
    at = find(node, "at")
    if at is None:
        return
    base = float(at[3]) if len(at) > 3 and not isinstance(at[3], list) and at[3] != "unlocked" else 0.0
    new = (base + rot) % 360.0
    tail = [t for t in at[3:] if t == "unlocked"]
    del at[3:]
    if new or force:
        at.append(round(new, 4))
    at += tail


def write_pcb(board: Board, res: Resolved, path: Path, tracks: list | None = None, vias: list | None = None,
              zone_fills: dict | None = None, zone_layers: tuple[str, ...] = ("F.Cu", "B.Cu")) -> dict[str, int]:
    nets = net_table(res)
    pcb = ["kicad_pcb", ["version", 20240108], ["generator", Q("bhms_pcb_gen")], ["generator_version", Q("1.0")],
           ["general", ["thickness", 1.6], ["legacy_teardrops", "no"]], ["paper", Q("A4")],
           ["title_block", ["title", Q(board.title)], ["rev", Q(board.rev)], ["company", Q("BHMS project")]],
           copy.deepcopy(LAYERS),
           ["setup", ["pad_to_mask_clearance", 0], ["allow_soldermask_bridges_in_footprints", "no"],
            ["pcbplotparams", ["layerselection", "0x00010fc_ffffffff"], ["plot_on_all_layers_selection", "0x0000000_00000000"],
             ["disableapertmacros", "no"], ["usegerberextensions", "no"], ["usegerberattributes", "yes"],
             ["usegerberadvancedattributes", "yes"], ["creategerberjobfile", "yes"], ["svgprecision", 4],
             ["excludeedgelayer", "yes"], ["plotframeref", "no"], ["viasonmask", "no"], ["mode", 1],
             ["useauxorigin", "no"], ["hpglpennumber", 1], ["hpglpenspeed", 20], ["hpglpendiameter", 15.0],
             ["dxfpolygonmode", "yes"], ["dxfimperialunits", "yes"], ["dxfusepcbnewfont", "yes"],
             ["psnegative", "no"], ["psa4output", "no"], ["plotreference", "yes"], ["plotvalue", "yes"],
             ["plotfptext", "yes"], ["plotinvisibletext", "no"], ["sketchpadsonfab", "no"], ["subtractmaskfromsilk", "no"],
             ["outputformat", 1], ["mirror", "no"], ["drillshape", 0], ["scaleselection", 1],
             ["outputdirectory", Q("fab/")]]],
           ["net", 0, Q("")]]
    for n, i in nets.items():
        pcb.append(["net", i, Q(n if n.startswith("unconnected-(") else kname(n))])
    for p in board.parts:
        pcb.append(_place_footprint(board, res, p, nets))
    ox, oy = board.origin
    pcb += _outline(board)
    for k, t in enumerate(tracks or []):
        pcb.append(["segment", ["start", round(ox + t["x1"], 4), round(oy + t["y1"], 4)],
                    ["end", round(ox + t["x2"], 4), round(oy + t["y2"], 4)], ["width", t["w"]], ["layer", Q(t["layer"])],
                    ["net", nets[t["net"]]], ["uuid", uid(board.name, "seg", str(k))]])
    for k, v in enumerate(vias or []):
        pcb.append(["via", ["at", round(ox + v["x"], 4), round(oy + v["y"], 4)], ["size", v["size"]], ["drill", v["drill"]],
                    ["layers", Q("F.Cu"), Q("B.Cu")], ["net", nets[v["net"]]], ["uuid", uid(board.name, "via", str(k))]])
    for zn in board.zone_nets:
        for layer in zone_layers:
            pcb.append(_zone(board, zn, nets[zn], layer, (zone_fills or {}).get((zn, layer))))
    path.write_text(dumps(pcb) + "\n")
    return nets


def _outline(board: Board) -> list:
    ox, oy = board.origin
    out = []
    if board.outline is None:
        w, h = board.size
        out.append(["gr_rect", ["start", ox, oy], ["end", ox + w, oy + h], ["stroke", ["width", 0.1], ["type", "default"]],
                    ["fill", "none"], ["layer", Q("Edge.Cuts")], ["uuid", uid(board.name, "edge")]])
    else:
        for k, seg in enumerate(board.outline):
            if seg[0] == "line":
                _, (x1, y1), (x2, y2) = seg
                out.append(["gr_line", ["start", ox + x1, oy + y1], ["end", ox + x2, oy + y2],
                            ["stroke", ["width", 0.1], ["type", "default"]], ["layer", Q("Edge.Cuts")],
                            ["uuid", uid(board.name, "edge", str(k))]])
            elif seg[0] == "arc":
                _, (x1, y1), (xm, ym), (x2, y2) = seg
                out.append(["gr_arc", ["start", ox + x1, oy + y1], ["mid", ox + xm, oy + ym], ["end", ox + x2, oy + y2],
                            ["stroke", ["width", 0.1], ["type", "default"]], ["layer", Q("Edge.Cuts")],
                            ["uuid", uid(board.name, "edge", str(k))]])
    return out


def zone_outline(board: Board) -> list[tuple[float, float]]:
    """Zone polygon (board coordinates): the outline inset by 0.3 mm."""
    if board.outline is None:
        w, h = board.size
        return [(0.3, 0.3), (w - 0.3, 0.3), (w - 0.3, h - 0.3), (0.3, h - 0.3)]
    pts = []
    for seg in board.outline:
        if seg[0] == "line":
            pts.append(seg[1])
        else:
            (x1, y1), (xm, ym), (x2, y2) = seg[1], seg[2], seg[3]
            cx, cy, r = _circle(x1, y1, xm, ym, x2, y2)
            a1, am, a2 = (math.atan2(y - cy, x - cx) for x, y in ((x1, y1), (xm, ym), (x2, y2)))
            # Sweep from a1 to a2 through am.
            def norm(a):
                return (a - a1) % (2 * math.pi)
            sweep = norm(a2)
            if norm(am) > sweep:
                sweep -= 2 * math.pi
            for i in range(24):
                a = a1 + sweep * i / 24
                pts.append((cx + (r - 0.3) * math.cos(a), cy + (r - 0.3) * math.sin(a)))
    return pts


def _circle(x1, y1, x2, y2, x3, y3):
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    ux = ((x1 ** 2 + y1 ** 2) * (y2 - y3) + (x2 ** 2 + y2 ** 2) * (y3 - y1) + (x3 ** 2 + y3 ** 2) * (y1 - y2)) / d
    uy = ((x1 ** 2 + y1 ** 2) * (x3 - x2) + (x2 ** 2 + y2 ** 2) * (x1 - x3) + (x3 ** 2 + y3 ** 2) * (x2 - x1)) / d
    return ux, uy, math.hypot(x1 - ux, y1 - uy)


def _zone(board: Board, net: str, net_id: int, layer: str, fill: list | None) -> list:
    ox, oy = board.origin
    pts = ["pts"] + [["xy", round(ox + x, 4), round(oy + y, 4)] for x, y in zone_outline(board)]
    z = ["zone", ["net", net_id], ["net_name", Q(kname(net))], ["layer", Q(layer)], ["uuid", uid(board.name, "zone", net, layer)],
         ["hatch", "edge", 0.5], ["priority", 0], ["connect_pads", ["clearance", 0.3]], ["min_thickness", 0.25],
         ["filled_areas_thickness", "no"],
         ["fill", "yes", ["thermal_gap", 0.4], ["thermal_bridge_width", 0.4], ["island_removal_mode", 0],
          ["island_area_min", 2.0]],
         ["polygon", pts]]
    if fill:
        z += fill
    return z


# ---------------------------------------------------------------------------
# Project (net classes and fab rules)
# ---------------------------------------------------------------------------

FAB_RULES = {  # JLCPCB standard 2-layer, 1 oz (checked against their published capabilities)
    "min_track_width": 0.127, "min_clearance": 0.127, "min_via_diameter": 0.45, "min_through_hole_diameter": 0.3,
    "min_via_annular_width": 0.1, "min_hole_to_hole": 0.254, "min_copper_edge_clearance": 0.3, "min_hole_clearance": 0.15,
    "min_silk_clearance": 0.0, "min_text_height": 0.8, "min_text_thickness": 0.08, "min_microvia_diameter": 0.2,
    "min_microvia_drill": 0.1, "min_resolved_spokes": 1, "max_error": 0.005, "solder_mask_to_copper_clearance": 0.0,
    "allow_blind_buried_vias": False, "allow_microvias": False, "use_height_for_length_calcs": True,
}


def write_project(board: Board, path: Path) -> None:
    classes = [{
        "name": "Default", "clearance": 0.13, "track_width": 0.15, "via_diameter": 0.5, "via_drill": 0.3,
        "microvia_diameter": 0.3, "microvia_drill": 0.1, "diff_pair_width": 0.2, "diff_pair_gap": 0.25,
        "diff_pair_via_gap": 0.25, "wire_width": 6, "bus_width": 12, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
        "schematic_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647,
    }]
    patterns = []
    widths = sorted(set(board.power_nets.values()))
    for w in widths:
        name = f"Power_{w:g}mm"
        classes.append({**classes[0], "name": name, "clearance": 0.2, "track_width": w, "via_diameter": 0.8, "via_drill": 0.4,
                        "priority": 1})
        for net, wn in board.power_nets.items():
            if wn == w:
                patterns.append({"netclass": name, "pattern": kname(net)})
    pro = {
        "board": {
            "design_settings": {
                "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2, "copper_text_size_h": 1.5,
                             "copper_text_size_v": 1.5, "copper_text_thickness": 0.3, "silk_line_width": 0.12,
                             "silk_text_size_h": 1.0, "silk_text_size_v": 1.0, "silk_text_thickness": 0.15},
                "rules": FAB_RULES,
                "rule_severities": {"lib_footprint_issues": "ignore", "lib_footprint_mismatch": "ignore",
                                    "silk_overlap": "ignore", "silk_over_copper": "warning", "silk_edge_clearance": "ignore",
                                    "text_height": "ignore", "text_thickness": "ignore"},
                "track_widths": [0.0, 0.15, 0.2, 0.25, 0.4] + widths, "via_dimensions": [{"diameter": 0.0, "drill": 0.0},
                                                                                     {"diameter": 0.5, "drill": 0.3},
                                                                                     {"diameter": 0.8, "drill": 0.4}],
            },
        },
        "meta": {"filename": f"{board.name}.kicad_pro", "version": 1},
        "net_settings": {"classes": classes, "meta": {"version": 3}, "netclass_patterns": patterns},
        "erc": {"rule_severities": {"lib_symbol_issues": "ignore", "lib_symbol_mismatch": "ignore",
                                    "footprint_link_issues": "ignore", "simulation_model_issue": "ignore"}},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "pcbnew": {"last_paths": {}, "page_layout_descr_file": ""},
        "sheets": [[str(uid(board.name, "schematic")), "Root"]],
        "text_variables": {},
    }
    path.write_text(json.dumps(pro, indent=2) + "\n")
