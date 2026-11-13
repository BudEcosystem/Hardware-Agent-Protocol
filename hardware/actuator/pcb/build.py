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
    write_pcb(b, res, pcb, tracks, vias)
    fills = fill_zones(pcb)
    write_pcb(b, res, pcb, tracks, vias, fills)
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


def kicad_checks(name: str) -> dict:
    cli = kicad_cli()
    d = out_dir(name)
    b = BOARDS[name]()
    out = {"kicad_cli": None}
    if cli is None:
        return out
    ver = subprocess.run([cli, "version"], capture_output=True, text=True).stdout.strip().splitlines()[-1]
    out["kicad_cli"] = ver
    sch = d / f"{b.name}.kicad_sch"
    pcb = d / f"{b.name}.kicad_pcb"
    erc_json = d / "erc.json"
    drc_json = d / "drc.json"
    subprocess.run([cli, "sch", "erc", "--format", "json", "--severity-all", "-o", str(erc_json), str(sch)],
                   capture_output=True, text=True)
    subprocess.run([cli, "pcb", "drc", "--format", "json", "--severity-all", "--schematic-parity", "-o", str(drc_json),
                    str(pcb)], capture_output=True, text=True)
    for key, path in (("erc", erc_json), ("drc", drc_json)):
        if path.exists():
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
                        "by_type": _count(items)}
    return out


def _count(items) -> dict:
    c: dict[str, int] = {}
    for sec, sev, typ, _ in items:
        k = f"{sec}:{sev}:{typ}"
        c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items()))


def fab(name: str) -> None:
    cli = kicad_cli()
    if cli is None:
        print("kicad-cli not available: no Gerbers produced")
        return
    d = out_dir(name)
    b = BOARDS[name]()
    pcb = d / f"{b.name}.kicad_pcb"
    sch = d / f"{b.name}.kicad_sch"
    fabd = d / "fab"
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
    for cmd in cmds:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print("FAILED:", " ".join(cmd), r.stdout[-2000:], r.stderr[-2000:])
    print(f"[{name}] fab outputs: {sorted(p.name for p in fabd.iterdir())}")


def _known_open(name: str) -> list[str]:
    """Prefixes of scripted-DRC messages that are acknowledged as unfinished
    routing (the autorouter could not complete them); anything else fails."""
    p = HERE / name / "known_open.json"
    return json.loads(p.read_text())["prefixes"] if p.exists() else []


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
            report["kicad"] = kicad_checks(name)
            (out_dir(name) / "check_report.json").write_text(json.dumps(report, indent=1))
            k = report["kicad"]
            print(f"[{name}] scripted DRC violations: {len(report['drc_violations'])}, ERC problems: {len(report['erc_problems'])}; "
                  f"kicad-cli: ERC {k.get('erc', {}).get('errors')} err / DRC {k.get('drc', {}).get('errors')} err")
            known = _known_open(name)
            fresh = [v for v in report["drc_violations"] if not any(v.startswith(k) for k in known)]
            report["accepted_known_open"] = [v for v in report["drc_violations"] if v not in fresh]
            (out_dir(name) / "check_report.json").write_text(json.dumps(report, indent=1))
            if report["accepted_known_open"]:
                print(f"[{name}] WARNING: {len(report['accepted_known_open'])} KNOWN OPEN items (pcb/{name}/known_open.json): "
                      "board is NOT fabrication-ready until they are routed by hand")
            if fresh or report["erc_problems"]:
                rc = 1
        if step in ("fab", "all"):
            fab(name)
    return rc


if __name__ == "__main__":
    sys.exit(main())
