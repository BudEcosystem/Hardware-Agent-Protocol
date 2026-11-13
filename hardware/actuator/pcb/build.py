#!/usr/bin/env python3
"""Generate, route and check the BHMS Arm PCBs.

    python pcb/build.py generate      # .kicad_sch/.kicad_pcb (unrouted)/.kicad_pro + netlist.json
    python pcb/build.py route         # needs pcbnew + Freerouting (FREEROUTING env: command line)
    python pcb/build.py dsn / import  # the same, split: export DSN, route elsewhere, import the SES
    python pcb/build.py check         # scripted ERC/DRC (+ kicad-cli ERC/DRC if available)
    python pcb/build.py fab           # kicad-cli Gerber/drill/position/netlist/PDF exports
    python pcb/build.py all

Boards: controller (pcb/controller.py) and tool_contact (pcb/tool_contact.py).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import controller  # noqa: E402
import tool_contact  # noqa: E402
from circuit import Resolved, erc, rotate  # noqa: E402
from kicad_writer import write_pcb, write_project, write_schematic  # noqa: E402
from kicadlib import courtyard_bbox  # noqa: E402
from sexpr import find, find_all, loads  # noqa: E402

FAB_HOLE_TO_HOLE = 0.5  # mm, JLCPCB different-net hole spacing (drc.FAB)
BOARDS = {"controller": controller.build, "tool_contact": tool_contact.build}


def out_dir(name: str) -> Path:
    d = HERE / name
    d.mkdir(exist_ok=True)
    return d


def placement_check(res: Resolved) -> list[str]:
    """Courtyards inside the outline and not overlapping (per side)."""
    b = res.board
    boxes = []
    problems = []
    for p in b.parts:
        fp = res.fp[p.ref]
        for side in ("F", "B"):
            bb = courtyard_bbox(fp, f"{side}.CrtYd")
            if bb is None:
                continue
            corners = [rotate(x, y, p.rot) for x in (bb[0], bb[2]) for y in (bb[1], bb[3])]
            xs = [p.pos[0] + c[0] for c in corners]
            ys = [p.pos[1] + c[1] for c in corners]
            boxes.append((p.ref, side, min(xs), min(ys), max(xs), max(ys)))
    for i, a in enumerate(boxes):
        for bx in boxes[i + 1:]:
            if a[1] != bx[1]:
                continue
            ox = min(a[4], bx[4]) - max(a[2], bx[2])
            oy = min(a[5], bx[5]) - max(a[3], bx[3])
            if ox > 0.01 and oy > 0.01:
                problems.append(f"courtyard overlap {a[0]} / {bx[0]} ({ox:.2f} x {oy:.2f} mm)")
    if b.outline is None:
        w, h = b.size
        for ref, side, x0, y0, x1, y1 in boxes:
            # USB-C / edge connectors may overhang the rear edge by design.
            if ref.startswith("J") and y0 < 0:
                continue
            if x0 < -0.01 or y0 < -0.01 or x1 > w + 0.01 or y1 > h + 0.01:
                problems.append(f"{ref} courtyard outside the board ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f})")
    return problems


def netlist_json(res: Resolved) -> dict:
    parts = []
    for p in res.board.parts:
        parts.append({"ref": p.ref, "value": p.value, "footprint": p.footprint, "symbol": p.symbol, "mpn": p.mpn,
                      "manufacturer": p.manufacturer, "dnp": p.dnp, "unit_price_usd": p.unit_price_usd,
                      "price_source": p.price_source, "note": p.note, "pos_mm": list(p.pos), "rot": p.rot,
                      "pins": res.pin_net[p.ref]})
    return {"board": res.board.name, "nets": {n: [f"{r}.{pin}" for r, pin in nodes] for n, nodes in res.nets().items()},
            "parts": parts}


def generate(name: str) -> Resolved:
    b = BOARDS[name]()
    res = Resolved(b)
    d = out_dir(name)
    problems = erc(res) + placement_check(res)
    write_schematic(b, res, d / f"{b.name}.kicad_sch", b.name)
    write_pcb(b, res, d / f"{b.name}.kicad_pcb")
    write_project(b, d / f"{b.name}.kicad_pro")
    (d / "netlist.json").write_text(json.dumps(netlist_json(res), indent=1))
    (d / "generate_report.json").write_text(json.dumps({"problems": problems, "parts": len(b.parts),
                                                         "nets": len(res.nets())}, indent=1))
    print(f"[{name}] {len(b.parts)} parts, {len(res.nets())} nets, {len(problems)} netlist/placement problems")
    for pr in problems:
        print("   ", pr)
    return res


# ---------------------------------------------------------------------------
# Routing: pcbnew Specctra export -> freerouting -> SES import (own parser)
# ---------------------------------------------------------------------------


def _pcbnew():
    import pcbnew  # KiCad's Python module (system python of the KiCad install)

    return pcbnew


def export_dsn(pcb: Path, dsn: Path) -> None:
    pcbnew = _pcbnew()
    board = pcbnew.LoadBoard(str(pcb))
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise RuntimeError("Specctra export failed")


def parse_ses(ses: Path, origin: tuple[float, float]) -> tuple[list[dict], list[dict]]:
    tree = loads(ses.read_text())
    routes = find(tree, "routes")
    res = find(routes, "resolution")
    unit, per = str(res[1]), float(res[2])
    scale = {"um": 0.001, "mil": 0.0254, "mm": 1.0, "inch": 25.4}[unit] / per
    padstacks = {}
    lib = find(routes, "library_out")
    if lib is not None:
        for ps in find_all(lib, "padstack"):
            shape = find(ps, "shape")
            circ = find(shape, "circle") if shape is not None else None
            if circ is not None:
                padstacks[str(ps[1])] = float(circ[2]) * scale
    tracks, vias = [], []
    ox, oy = origin
    for net in find_all(find(routes, "network_out"), "net"):
        name = str(net[1]).lstrip("/")
        for w in find_all(net, "wire"):
            path = find(w, "path")
            layer, width = str(path[1]), float(path[2]) * scale
            pts = [float(v) for v in path[3:] if not isinstance(v, list)]
            xy = [(pts[i] * scale - ox, -pts[i + 1] * scale - oy) for i in range(0, len(pts), 2)]
            for (x1, y1), (x2, y2) in zip(xy, xy[1:]):
                tracks.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "w": round(width, 4), "layer": layer, "net": name})
        for v in find_all(net, "via"):
            ps = str(v[1])
            m = re.search(r"(\d+):(\d+)_um", ps)
            size, drill = (int(m.group(1)) / 1000.0, int(m.group(2)) / 1000.0) if m else (padstacks.get(ps, 0.6), 0.3)
            vias.append({"x": float(v[2]) * scale - ox, "y": -float(v[3]) * scale - oy, "size": size, "drill": drill,
                         "net": name})
    return tracks, vias


def _polys_by_net(fills: dict) -> dict[str, list]:
    out: dict[str, list] = {}
    for (net, layer), polys in fills.items():
        for fp in polys:
            pts = [(float(xy[1]), float(xy[2])) for xy in find_all(find(fp, "pts"), "xy")]
            if len(pts) >= 3:
                out.setdefault(net, []).append((layer, pts))
    return out


def finish_board(b, res: Resolved, pcb: Path, tracks: list, vias: list, rounds: int = 8):
    """Completion pass (pcb/finish.py): fix via pairs that violate the fab hole-to-hole rule, join the
    nets the router left open (with rip-up of blocking nets), then stitch the ground pours with vias,
    re-filling the pours after each round.  Returns the new track/via lists (board coordinates) and a log."""
    import finish
    from drc import load_items

    ox, oy = b.origin
    log: list[str] = []

    def to_board(ts, vs):
        return ([{**t, "x1": t["x1"] - ox, "y1": t["y1"] - oy, "x2": t["x2"] - ox, "y2": t["y2"] - oy} for t in ts],
                [{**v, "x": v["x"] - ox, "y": v["y"] - oy} for v in vs])

    write_pcb(b, res, pcb, [], [], zone_layers=())
    items, holes, pads_by_net, _zones, edge = load_items(pcb)
    state = finish.State(items, holes, pads_by_net, edge, b.zone_nets, b.power_nets, log)
    state.tracks = [{**t, "x1": t["x1"] + ox, "y1": t["y1"] + oy, "x2": t["x2"] + ox, "y2": t["y2"] + oy} for t in tracks]
    state.vias = [{**v, "x": v["x"] + ox, "y": v["y"] + oy} for v in vias]
    for _ in range(6):  # via pairs closer than the hole-to-hole rule: rip up one via, re-route below
        if not state.repair_holes():
            break
    state.complete_signals()
    n_spur = state.prune_spurs()
    log.append(f"pruned {n_spur} dangling track segments")
    for rnd in range(rounds):
        tb, vb = to_board(state.tracks, state.vias)
        write_pcb(b, res, pcb, tb, vb)
        fills = fill_zones(pcb)
        polys = {n: p for n, p in _polys_by_net(fills).items() if n in b.zone_nets}
        made = finish.stitch_pours(state, polys)
        log.append(f"stitching round {rnd + 1}: {made} connections")
        if not made:
            break
    n_spur = state.prune_spurs()
    log.append(f"final prune: {n_spur} dangling track segments")
    tb, vb = to_board(state.tracks, state.vias)
    return tb, vb, log


def fill_zones(pcb: Path) -> dict:
    """Fill copper zones with pcbnew and return the filled polygons per
    (net, layer) as s-expressions to embed into the KiCad 8 file."""
    pcbnew = _pcbnew()
    board = pcbnew.LoadBoard(str(pcb))
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    tmp = pcb.with_suffix(".filled.kicad_pcb")
    pcbnew.SaveBoard(str(tmp), board)
    tree = loads(tmp.read_text())
    tmp.unlink()
    fills = {}
    for z in find_all(tree, "zone"):
        nn = find(z, "net_name")
        net = str(nn[1]) if nn is not None else str(find(z, "net")[1])  # KiCad 10: (net "NAME")
        net = net.lstrip("/")
        layer_node = find(z, "layer")
        layer = str(layer_node[1]) if layer_node is not None else str(find(z, "layers")[1])
        polys = find_all(z, "filled_polygon")
        fills[(net, layer)] = polys
    return fills


def make_dsn(name: str) -> Path:
    """Write the unrouted board and export it to Specctra DSN (pcbnew)."""
    b = BOARDS[name]()
    res = Resolved(b)
    d = out_dir(name)
    pcb = d / f"{b.name}.kicad_pcb"
    # Only the bottom GND pour is exported (as a Specctra plane): the router
    # then fans every top-side GND pad out to it with a via.  With planes on
    # both layers it would consider top pads connected and leave islands.
    # The top pour is added back after routing.
    write_pcb(b, res, pcb, zone_layers=("B.Cu",))
    dsn = d / f"{b.name}.dsn"
    export_dsn(pcb, dsn)
    # Specctra has no hole-to-hole rule: JLCPCB wants 0.5 mm between the holes of
    # different nets, i.e. (0.5 - (via - drill)) = 0.3 mm of copper gap between
    # 0.5/0.3 mm vias.  The default class gets that as a via_via clearance.
    text = dsn.read_text()
    gap_um = round(1000 * (FAB_HOLE_TO_HOLE - (0.5 - 0.3)))
    patched = text.replace("(clearance 32.5 (type smd_smd))", f"(clearance 32.5 (type smd_smd))\n      (clearance {gap_um} (type via_via))", 1)
    if patched == text:
        raise RuntimeError("could not add the via_via clearance to the DSN (exporter format changed?)")
    dsn.write_text(patched)
    return dsn


def run_router(name: str) -> Path:
    """Run Freerouting on the DSN.  FREEROUTING is a command line, e.g.
    ``xvfb-run -a java -jar freerouting-1.9.0.jar`` (1.9.0 needs a display;
    the 2.5.0 native CLI crashed with a GraalVM serialization error)."""
    b = BOARDS[name]()
    d = out_dir(name)
    dsn = d / f"{b.name}.dsn"
    ses = d / f"{b.name}.ses"
    cmd = shlex.split(os.environ.get("FREEROUTING", "freerouting")) + [
        "-de", str(dsn), "-do", str(ses), "-mp", os.environ.get("FREEROUTING_PASSES", "100"),
        "-mt", os.environ.get("FREEROUTING_THREADS", "1")]  # multi-threaded optimisation can break clearances
    print("running", " ".join(cmd), flush=True)
    log = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, stdin=subprocess.DEVNULL)
    (d / "freerouting.log").write_text(log.stdout[-20000:] + "\n" + log.stderr[-20000:])
    if not ses.exists():
        raise RuntimeError(f"freerouting produced no session file (exit {log.returncode})")
    return ses


def route(name: str, run: bool = True) -> None:
    """dsn -> (router) -> import the SES, fill zones, write the routed board."""
    b = BOARDS[name]()
    res = Resolved(b)
    d = out_dir(name)
    pcb = d / f"{b.name}.kicad_pcb"
    dsn = d / f"{b.name}.dsn"
    ses = d / f"{b.name}.ses"
    if run:
        make_dsn(name)
        run_router(name)
    # pcbnew's Specctra export writes coordinates in um with y inverted and
    # an offset to the board origin; recover it from a component placement.
    tracks, vias = parse_ses(ses, _dsn_origin(dsn, res))
    n_router = (len(tracks), len(vias))
    tracks, vias, finish_log = finish_board(b, res, pcb, tracks, vias)
    write_pcb(b, res, pcb, tracks, vias)
    fills = fill_zones(pcb)
    write_pcb(b, res, pcb, tracks, vias, fills)
    (d / "finish.log").write_text("\n".join(finish_log) + "\n")
    print(f"[{name}] router: {n_router[0]} segments, {n_router[1]} vias; completion pass added "
          f"{len(tracks) - n_router[0]} segments, {len(vias) - n_router[1]} vias ({len(finish_log)} log lines, pcb/{name}/finish.log)")
    (d / "routing.json").write_text(json.dumps({"tracks": len(tracks), "vias": len(vias),
                                                 "track_length_mm": sum(((t["x2"] - t["x1"]) ** 2 + (t["y2"] - t["y1"]) ** 2) ** 0.5
                                                                        for t in tracks)}, indent=1))
    print(f"[{name}] routed: {len(tracks)} segments, {len(vias)} vias")


def _dsn_origin(dsn: Path, res: Resolved) -> tuple[float, float]:
    """Offset between DSN coordinates (mm after scaling) and board
    coordinates, from a component placement.  The DSN declares a
    ``string_quote`` of a bare double quote, so it is scanned with regular
    expressions rather than the s-expression reader."""
    text = dsn.read_text()
    unit = re.search(r"\(unit (\w+)\)", text)
    scale = {"um": 0.001, "mil": 0.0254, "mm": 1.0, "inch": 25.4}[unit.group(1) if unit else "um"]
    for m in re.finditer(r"\(place (\S+) (-?[\d.]+) (-?[\d.]+)", text):
        try:
            part = res.board.part(m.group(1))
        except KeyError:
            continue
        x, y = float(m.group(2)) * scale, float(m.group(3)) * scale
        # board x = x_dsn - ox ; board y = -y_dsn - oy
        return x - part.pos[0], -y - part.pos[1]
    raise RuntimeError("no placement in DSN")


# ---------------------------------------------------------------------------
# KiCad CLI checks and fabrication outputs
# ---------------------------------------------------------------------------


def kicad_cli() -> str | None:
    return shutil.which("kicad-cli")


class ToolMissing(RuntimeError):
    pass


def allow_no_kicad() -> bool:
    return os.environ.get("ALLOW_NO_KICAD") == "1"


def kicad_checks(name: str) -> dict:
    """Run kicad-cli ERC and DRC.  A missing kicad-cli is a failure unless
    ALLOW_NO_KICAD=1, in which case the result says ``skipped``."""
    cli = kicad_cli()
    d = out_dir(name)
    b = BOARDS[name]()
    if cli is None:
        if not allow_no_kicad():
            raise ToolMissing("kicad-cli not found: install KiCad 10 (or set ALLOW_NO_KICAD=1 to skip the KiCad checks, "
                              "which is reported as SKIPPED)")
        return {"kicad_cli": None, "skipped": True}
    out: dict = {"kicad_cli": None, "skipped": False}
    ver = subprocess.run([cli, "version"], capture_output=True, text=True).stdout.strip().splitlines()[-1]
    out["kicad_cli"] = ver
    sch = d / f"{b.name}.kicad_sch"
    pcb = d / f"{b.name}.kicad_pcb"
    erc_json = d / "erc.json"
    drc_json = d / "drc.json"
    for path in (erc_json, drc_json):
        path.unlink(missing_ok=True)
    r1 = subprocess.run([cli, "sch", "erc", "--format", "json", "--severity-all", "-o", str(erc_json), str(sch)],
                        capture_output=True, text=True)
    r2 = subprocess.run([cli, "pcb", "drc", "--format", "json", "--severity-all", "--schematic-parity", "-o", str(drc_json),
                         str(pcb)], capture_output=True, text=True)
    for key, path, r in (("erc", erc_json, r1), ("drc", drc_json, r2)):
        if not path.exists():
            raise RuntimeError(f"kicad-cli {key} produced no report (exit {r.returncode}): {r.stderr[-500:]}")
        data = json.loads(path.read_text())
        items = []
        for sec in ("violations", "unconnected_items", "schematic_parity"):
            for v in data.get(sec, []):
                items.append((sec, v.get("severity"), v.get("type"), v.get("description")))
        for sheet in data.get("sheets", []):
            for v in sheet.get("violations", []):
                items.append(("violations", v.get("severity"), v.get("type"), v.get("description")))
        out[key] = {"errors": sum(1 for i in items if i[1] == "error"),
                    "warnings": sum(1 for i in items if i[1] == "warning"),
                    "unconnected": sum(1 for i in items if i[0] == "unconnected_items"),
                    "by_type": _count(items)}
    return out


def _count(items) -> dict:
    c: dict[str, int] = {}
    for sec, sev, typ, _ in items:
        k = f"{sec}:{sev}:{typ}"
        c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items()))


def known_open_items(name: str) -> dict:
    """Acknowledged unfinished routing: exact scripted-DRC messages and the
    exact KiCad unconnected-item count.  Empty for a finished board."""
    p = HERE / name / "known_open.json"
    if not p.exists():
        return {"messages": [], "kicad_unconnected": 0}
    data = json.loads(p.read_text())
    return {"messages": data.get("messages", []), "kicad_unconnected": int(data.get("kicad_unconnected", 0))}


def fab(name: str) -> bool:
    """Gerber/drill/position/netlist/PDF export with kicad-cli.  Returns
    True on success.  Refuses to emit fabrication files while the board has
    known open items: removes any stale fab/ and writes DO_NOT_FABRICATE.md."""
    d = out_dir(name)
    b = BOARDS[name]()
    fabd = d / "fab"
    guard = d / "DO_NOT_FABRICATE.md"
    ko = known_open_items(name)
    if ko["messages"] or ko["kicad_unconnected"]:
        if fabd.exists():
            shutil.rmtree(fabd)
        guard.write_text(
            f"# DO NOT FABRICATE: {b.name}\n\n"
            "This board is not completely routed, so no Gerber/drill files are generated.\n"
            f"Open items (pcb/{name}/known_open.json):\n\n"
            + "".join(f"* {m}\n" for m in ko["messages"])
            + f"\nKiCad DRC reports {ko['kicad_unconnected']} unconnected items.\n\n"
            "Finish the routing, empty known_open.json and re-run `pcb/build.py fab`.\n")
        print(f"[{name}] DO NOT FABRICATE: known open items, fab outputs not generated ({guard.name} written)")
        return True
    guard.unlink(missing_ok=True)
    cli = kicad_cli()
    if cli is None:
        if allow_no_kicad():
            print(f"[{name}] SKIPPED: kicad-cli not available, no Gerbers produced (ALLOW_NO_KICAD=1)")
            return True
        print(f"[{name}] FAILED: kicad-cli not found, no Gerbers produced")
        return False
    pcb = d / f"{b.name}.kicad_pcb"
    sch = d / f"{b.name}.kicad_sch"
    if fabd.exists():
        shutil.rmtree(fabd)
    fabd.mkdir()
    layers = "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
    cmds = [
        [cli, "pcb", "export", "gerbers", "--layers", layers, "--subtract-soldermask", "-o", str(fabd) + "/", str(pcb)],
        [cli, "pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th", "--generate-map",
         "--map-format", "gerberx2", "-o", str(fabd) + "/", str(pcb)],
        [cli, "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both", "-o",
         str(fabd / f"{b.name}-pos.csv"), str(pcb)],
        [cli, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(d / f"{b.name}.net"), str(sch)],
        [cli, "sch", "export", "pdf", "-o", str(d / f"{b.name}-schematic.pdf"), str(sch)],
        [cli, "pcb", "export", "pdf", "--layers", "F.Cu,B.Cu,Edge.Cuts,F.SilkS", "--mode-single", "-o",
         str(d / f"{b.name}-layout.pdf"), str(pcb)],
    ]
    ok = True
    for cmd in cmds:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            ok = False
            print("FAILED:", " ".join(cmd), r.stdout[-2000:], r.stderr[-2000:])
    needed = [f"{b.name}-F_Cu.gtl", f"{b.name}-B_Cu.gbl", f"{b.name}-Edge_Cuts.gm1", f"{b.name}-PTH.drl"]
    missing = [n for n in needed if not (fabd / n).exists()]
    if missing:
        ok = False
        print(f"FAILED: missing fabrication outputs {missing}")
    print(f"[{name}] fab outputs: {sorted(p.name for p in fabd.iterdir())}")
    return ok


def main() -> int:
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    names = sys.argv[2:] or list(BOARDS)
    rc = 0
    for name in names:
        if step in ("generate", "all"):
            generate(name)
        if step == "dsn":
            make_dsn(name)
        if step == "import":  # SES produced elsewhere (e.g. router on another host)
            route(name, run=False)
        if step in ("route", "all"):
            route(name)
        if step in ("check", "all"):
            from drc import run_checks

            report = run_checks(name, BOARDS[name])
            try:
                report["kicad"] = kicad_checks(name)
            except ToolMissing as e:
                print(f"[{name}] FAILED: {e}")
                report["kicad"] = {"kicad_cli": None, "skipped": False, "error": str(e)}
                rc = 1
            ko = known_open_items(name)
            fresh = [v for v in report["drc_violations"] if v not in ko["messages"]]
            vanished = [m for m in ko["messages"] if m not in report["drc_violations"]]  # known_open.json must stay exact
            report["accepted_known_open"] = [v for v in report["drc_violations"] if v in ko["messages"]]
            problems = [f"scripted DRC: {v}" for v in fresh] + [f"known_open.json is stale (no longer reported): {m}" for m in vanished]
            problems += [f"netlist ERC: {e}" for e in report["erc_problems"]]
            k = report["kicad"]
            if k.get("skipped"):
                print(f"[{name}] SKIPPED: KiCad ERC/DRC (kicad-cli missing, ALLOW_NO_KICAD=1)")
            elif "erc" in k:
                if k["erc"]["errors"] or k["erc"]["warnings"]:
                    problems.append(f"KiCad ERC: {k['erc']['errors']} errors, {k['erc']['warnings']} warnings: {k['erc']['by_type']}")
                other = k["drc"]["errors"] - k["drc"]["unconnected"]
                if other:
                    problems.append(f"KiCad DRC: {other} non-connectivity errors: {k['drc']['by_type']}")
                if k["drc"]["unconnected"] != ko["kicad_unconnected"]:
                    problems.append(f"KiCad DRC: {k['drc']['unconnected']} unconnected items (known_open.json allows {ko['kicad_unconnected']})")
            report["problems"] = problems
            (out_dir(name) / "check_report.json").write_text(json.dumps(report, indent=1))
            ke = k.get("erc", {})
            kd = k.get("drc", {})
            print(f"[{name}] scripted DRC findings: {len(report['drc_violations'])}, ERC problems: {len(report['erc_problems'])}; "
                  f"kicad-cli: ERC {ke.get('errors')} err {ke.get('warnings')} warn / DRC {kd.get('errors')} err "
                  f"({kd.get('unconnected')} unconnected) {kd.get('warnings')} warn")
            if report["accepted_known_open"] or ko["kicad_unconnected"]:
                print(f"[{name}] WARNING: board is NOT fully routed ({len(ko['messages'])} known open items, "
                      f"{ko['kicad_unconnected']} KiCad unconnected); do not fabricate")
            for pr in problems:
                print(f"[{name}] FAILED: {pr}")
            if problems:
                rc = 1
        if step in ("fab", "all"):
            if not fab(name):
                rc = 1
        if step == "summary":
            rep = json.loads((out_dir(name) / "check_report.json").read_text())
            k = rep.get("kicad", {})
            if k.get("skipped"):
                print(f"[{name}] SKIPPED KiCad ERC/DRC (ALLOW_NO_KICAD=1); scripted DRC findings {len(rep['drc_violations'])}")
            else:
                e, d = k["erc"], k["drc"]
                ko = known_open_items(name)
                print(f"[{name}] KiCad {k['kicad_cli']}: ERC {e['errors']} err/{e['warnings']} warn; DRC {d['errors']} err "
                      f"({d['unconnected']} unconnected)/{d['warnings']} warn; scripted DRC findings {len(rep['drc_violations'])}; "
                      f"known open items {len(ko['messages'])}; fab outputs "
                      f"{'NOT generated (DO_NOT_FABRICATE.md)' if (out_dir(name) / 'DO_NOT_FABRICATE.md').exists() else 'present'}")
            if rep.get("problems"):
                rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
