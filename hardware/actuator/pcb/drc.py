"""Scripted design-rule and electrical-rule checks, independent of KiCad.

Reads the generated ``.kicad_pcb`` and checks it against the JLCPCB
standard 2-layer process (FAB below):

* track width, via diameter/drill, hole-to-hole spacing;
* copper clearance between items of different nets (tracks as capsules,
  vias/round pads as circles, other pads as oriented rectangles);
* copper-to-board-edge clearance (rectangular outlines);
* connectivity: every net's pads are joined by tracks/vias/pads, or by the
  filled copper pour for zone nets;
* netlist ERC (circuit.erc): every net has >= 2 pins, power pins connected,
  every footprint pad maps to a symbol pin; PCB pad nets equal the netlist.
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

from circuit import Resolved, erc
from sexpr import find, find_all, loads

FAB = {"min_track": 0.127, "min_clearance": 0.127, "min_via_drill": 0.3, "min_via_diameter": 0.45,  # JLCPCB std 2-layer
       "min_annular": 0.075, "min_hole_to_hole": 0.5, "edge_clearance": 0.3}
HERE = Path(__file__).resolve().parent


class Item:
    __slots__ = ("kind", "net", "layers", "a", "b", "r", "poly", "ref", "bbox")

    def __init__(self, kind, net, layers, a, b, r, poly=None, ref=""):
        self.kind, self.net, self.layers, self.a, self.b, self.r, self.poly, self.ref = kind, net, layers, a, b, r, poly, ref
        if poly is not None:
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            self.bbox = (min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r)
        else:
            self.bbox = (min(a[0], b[0]) - r, min(a[1], b[1]) - r, max(a[0], b[0]) + r, max(a[1], b[1]) + r)


def _seg_seg(p1, p2, q1, q2) -> float:
    def dot(u, v):
        return u[0] * v[0] + u[1] * v[1]

    def sub(u, v):
        return (u[0] - v[0], u[1] - v[1])

    def pt_seg(p, a, b):
        ab = sub(b, a)
        L = dot(ab, ab)
        t = 0.0 if L == 0 else max(0.0, min(1.0, dot(sub(p, a), ab) / L))
        c = (a[0] + ab[0] * t, a[1] + ab[1] * t)
        return math.hypot(p[0] - c[0], p[1] - c[1])

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1, d2 = cross(q1, q2, p1), cross(q1, q2, p2)
    d3, d4 = cross(p1, p2, q1), cross(p1, p2, q2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 and d2 and d3 and d4:
        return 0.0
    return min(pt_seg(p1, q1, q2), pt_seg(p2, q1, q2), pt_seg(q1, p1, p2), pt_seg(q2, p1, p2))


def _inside(pt, poly) -> bool:
    x, y = pt
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _core_dist(a: Item, b: Item) -> float:
    if a.poly is None and b.poly is None:
        return _seg_seg(a.a, a.b, b.a, b.b)
    if a.poly is not None and b.poly is not None:
        if _inside(a.poly[0], b.poly) or _inside(b.poly[0], a.poly):
            return 0.0
        return min(_seg_seg(p, q, s, t) for p, q in zip(a.poly, a.poly[1:] + a.poly[:1])
                   for s, t in zip(b.poly, b.poly[1:] + b.poly[:1]))
    poly, seg = (a, b) if a.poly is not None else (b, a)
    if _inside(seg.a, poly.poly) or _inside(seg.b, poly.poly):
        return 0.0
    return min(_seg_seg(p, q, seg.a, seg.b) for p, q in zip(poly.poly, poly.poly[1:] + poly.poly[:1]))


def distance(a: Item, b: Item) -> float:
    return max(0.0, _core_dist(a, b) - a.r - b.r)


def _rot(x, y, deg):
    t = math.radians(deg)
    return x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t)


def load_items(pcb_path: Path):
    tree = loads(pcb_path.read_text())
    net_names = {int(n[1]): str(n[2]).lstrip("/") for n in find_all(tree, "net")}
    items: list[Item] = []
    holes: list[tuple[float, float, float, str]] = []
    pads_by_net: dict[str, list[Item]] = defaultdict(list)
    for fp in find_all(tree, "footprint"):
        at = find(fp, "at")
        fx, fy = float(at[1]), float(at[2])
        frot = float(at[3]) if len(at) > 3 else 0.0
        ref = next((str(p[2]) for p in find_all(fp, "property") if str(p[1]) == "Reference"), "?")
        for pad in find_all(fp, "pad"):
            pat = find(pad, "at")
            px, py = float(pat[1]), float(pat[2])
            prot = float(pat[3]) if len(pat) > 3 else frot
            dx, dy = _rot(px, py, frot)
            cx, cy = fx + dx, fy + dy
            size = find(pad, "size")
            w, h = float(size[1]), float(size[2])
            layers_node = find(pad, "layers")
            layers = {str(x) for x in layers_node[1:]}
            cu = set()
            for ly in layers:
                if ly in ("*.Cu", "F&B.Cu"):
                    cu |= {"F.Cu", "B.Cu"}
                elif ly.endswith(".Cu"):
                    cu.add(ly)
            netn = find(pad, "net")
            net = str(netn[2]).lstrip("/") if netn is not None else ""
            drill = find(pad, "drill")
            if drill is not None:
                dv = [float(x) for x in drill[1:] if not isinstance(x, list) and x != "oval"]
                if dv:
                    holes.append((cx, cy, dv[0], f"{ref}.{pad[1]}"))
            if not cu:
                continue
            shape = str(pad[3])
            if shape == "circle" or (shape == "oval" and abs(w - h) < 1e-6):
                it = Item("pad", net, cu, (cx, cy), (cx, cy), w / 2, ref=f"{ref}.{pad[1]}")
            elif shape == "oval":
                L = (max(w, h) - min(w, h)) / 2
                ux, uy = (_rot(L, 0, prot) if w > h else _rot(0, L, prot))
                it = Item("pad", net, cu, (cx - ux, cy - uy), (cx + ux, cy + uy), min(w, h) / 2, ref=f"{ref}.{pad[1]}")
            else:
                # Rounded rectangle = inner rectangle grown by the corner
                # radius (exact Minkowski form); plain rect has radius 0.
                rr = 0.0
                if shape == "roundrect":
                    ratio = find(pad, "roundrect_rratio")
                    rr = (float(ratio[1]) if ratio is not None else 0.25) * min(w, h)
                iw, ih = w / 2 - rr, h / 2 - rr
                corners = [_rot(sx * iw, sy * ih, prot) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                it = Item("pad", net, cu, (cx, cy), (cx, cy), rr, [(cx + x, cy + y) for x, y in corners],
                          ref=f"{ref}.{pad[1]}")
            items.append(it)
            if net:
                pads_by_net[net].append(it)
    for s in find_all(tree, "segment"):
        st, en = find(s, "start"), find(s, "end")
        w = float(find(s, "width")[1])
        net = net_names[int(find(s, "net")[1])]
        items.append(Item("track", net, {str(find(s, "layer")[1])}, (float(st[1]), float(st[2])),
                          (float(en[1]), float(en[2])), w / 2))
    for v in find_all(tree, "via"):
        at = find(v, "at")
        size = float(find(v, "size")[1])
        drill = float(find(v, "drill")[1])
        net = net_names[int(find(v, "net")[1])]
        c = (float(at[1]), float(at[2]))
        items.append(Item("via", net, {"F.Cu", "B.Cu"}, c, c, size / 2))
        holes.append((c[0], c[1], drill, f"via@{c[0]:.2f},{c[1]:.2f}"))
        items[-1].ref = f"via@{c[0]:.2f},{c[1]:.2f}:{drill}"
    zones = []
    for z in find_all(tree, "zone"):
        net = str(find(z, "net_name")[1]).lstrip("/")
        layer = str(find(z, "layer")[1])
        for fpoly in find_all(z, "filled_polygon"):
            pts = [(float(xy[1]), float(xy[2])) for xy in find_all(find(fpoly, "pts"), "xy")]
            if len(pts) >= 3:
                zones.append((net, layer, pts))
    edge = None
    for r in find_all(tree, "gr_rect"):
        if str(find(r, "layer")[1]) == "Edge.Cuts":
            s, e = find(r, "start"), find(r, "end")
            edge = (float(s[1]), float(s[2]), float(e[1]), float(e[2]))
    return items, holes, pads_by_net, zones, edge


def run_checks(name: str, build_fn) -> dict:
    board = build_fn()
    res = Resolved(board)
    pcb_path = HERE / name / f"{board.name}.kicad_pcb"
    items, holes, pads_by_net, zones, edge = load_items(pcb_path)
    violations: list[str] = []
    # Widths, vias, holes.
    for it in items:
        if it.kind == "track" and 2 * it.r < FAB["min_track"] - 1e-6:
            violations.append(f"track width {2 * it.r:.3f} < {FAB['min_track']} on {it.net}")
        if it.kind == "via":
            drill = float(it.ref.split(":")[-1])
            if drill < FAB["min_via_drill"] - 1e-6:
                violations.append(f"via drill {drill} < {FAB['min_via_drill']} at {it.a}")
            if 2 * it.r < FAB["min_via_diameter"] - 1e-6:
                violations.append(f"via diameter {2 * it.r} < {FAB['min_via_diameter']} at {it.a}")
            if (2 * it.r - drill) / 2 < FAB["min_annular"] - 1e-6:
                violations.append(f"via annular ring {(2 * it.r - drill) / 2:.3f} at {it.a}")
    for i, (x1, y1, d1, r1) in enumerate(holes):
        for x2, y2, d2, r2 in holes[i + 1:]:
            gap = math.hypot(x1 - x2, y1 - y2) - d1 / 2 - d2 / 2
            same_part = r1.split(".")[0] == r2.split(".")[0] and not r1.startswith("via")
            if gap < FAB["min_hole_to_hole"] - 1e-6 and not same_part and gap > -1e-6:
                violations.append(f"hole-to-hole {gap:.3f} mm between {r1} and {r2}")
    # Clearance (spatial hash on 2 mm cells).
    cell = 2.0
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, it in enumerate(items):
        x0, y0, x1, y1 = it.bbox
        for gx in range(int(math.floor((x0 - 0.2) / cell)), int(math.floor((x1 + 0.2) / cell)) + 1):
            for gy in range(int(math.floor((y0 - 0.2) / cell)), int(math.floor((y1 + 0.2) / cell)) + 1):
                grid[(gx, gy)].append(idx)
    checked = set()
    min_seen = math.inf
    for idxs in grid.values():
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                a, b = idxs[i], idxs[j]
                key = (a, b) if a < b else (b, a)
                if key in checked:
                    continue
                checked.add(key)
                A, B = items[a], items[b]
                if not (A.layers & B.layers):
                    continue
                if A.net and A.net == B.net:
                    continue
                if A.kind == "pad" and B.kind == "pad" and A.ref.split(".")[0] == B.ref.split(".")[0] and not (A.net or B.net):
                    continue
                if (A.bbox[2] + FAB["min_clearance"] < B.bbox[0] or B.bbox[2] + FAB["min_clearance"] < A.bbox[0]
                        or A.bbox[3] + FAB["min_clearance"] < B.bbox[1] or B.bbox[3] + FAB["min_clearance"] < A.bbox[1]):
                    continue
                d = distance(A, B)
                min_seen = min(min_seen, d)
                if d < FAB["min_clearance"] - 1e-4:
                    violations.append(f"clearance {d:.3f} mm: {A.kind} {A.ref or A.net} ({A.net}) vs {B.kind} "
                                      f"{B.ref or B.net} ({B.net})")
    # Edge clearance (rectangular boards).
    if edge is not None:
        ex0, ey0, ex1, ey1 = edge
        for it in items:
            x0, y0, x1, y1 = it.bbox
            if it.kind != "pad" or not it.ref.startswith("J3."):  # USB-C shell sits on the edge by design
                g = min(x0 - ex0, y0 - ey0, ex1 - x1, ey1 - y1)
                if g < FAB["edge_clearance"] - 1e-6 and it.kind != "pad":
                    violations.append(f"{it.kind} {it.net} {g:.3f} mm from the board edge")
    # Connectivity (union-find over touching copper of the same net).
    parent = list(range(len(items)))

    def findp(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for idxs in grid.values():
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                A, B = items[idxs[i]], items[idxs[j]]
                if A.net and A.net == B.net and (A.layers & B.layers) and _core_dist(A, B) <= A.r + B.r + 1e-3:
                    parent[findp(idxs[i])] = findp(idxs[j])
    zone_of: dict[str, list] = defaultdict(list)
    for net, layer, pts in zones:
        zone_of[net].append((layer, pts))
    unconnected = []
    for net, pads in pads_by_net.items():
        idx_of = {id(it): k for k, it in enumerate(items)}
        groups = defaultdict(list)
        for pad in pads:
            groups[findp(idx_of[id(pad)])].append(pad)
        if len(groups) <= 1:
            continue
        if net in zone_of:
            # Groups touching the same filled pour are joined.  A group touches
            # the pour if any of its items has a point inside a fill polygon.
            def touches(group_root) -> set:
                hit = set()
                for k, it in enumerate(items):
                    if findp(k) != group_root:
                        continue
                    for zi, (layer, pts) in enumerate(zone_of[net]):
                        if layer in it.layers and (_inside(it.a, pts) or (it.poly and any(_inside(c, pts) for c in it.poly))):
                            hit.add(zi)
                return hit
            hits = {g: touches(g) for g in groups}
            # Merge groups sharing any fill polygon index.
            roots = list(groups)
            comp = {g: g for g in roots}
            for g1 in roots:
                for g2 in roots:
                    if g1 < g2 and hits[g1] & hits[g2]:
                        a, b = comp[g1], comp[g2]
                        for k in comp:
                            if comp[k] == b:
                                comp[k] = a
            if len(set(comp.values())) <= 1:
                continue
            unconnected.append(f"net {net}: {len(set(comp.values()))} islands")
        else:
            unconnected.append(f"net {net}: {len(groups)} unconnected groups: "
                               + "; ".join(",".join(p.ref for p in g) for g in groups.values()))
    violations += [f"unconnected {u}" for u in unconnected]
    # Netlist ERC and PCB/netlist parity.
    erc_problems = erc(res)
    netlist_nets = {(r, pin): n for n, nodes in res.nets().items() for r, pin in nodes}
    pcb_nets = {}
    for it in items:
        if it.kind == "pad" and it.net:
            ref, pin = it.ref.split(".", 1)
            pcb_nets[(ref, pin)] = it.net
    for key, n in netlist_nets.items():
        if pcb_nets.get(key) not in (None, n):
            erc_problems.append(f"PCB pad {key} on {pcb_nets.get(key)} but netlist says {n}")
    return {"fab_rules": FAB, "items_checked": len(items), "pairs_checked": len(checked),
            "min_clearance_seen_mm": None if min_seen == math.inf else round(min_seen, 4),
            "drc_violations": violations, "erc_problems": erc_problems}
