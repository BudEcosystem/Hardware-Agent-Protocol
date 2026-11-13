"""Completion pass after the autorouter.

Freerouting leaves a few connections open on dense boards.  This module
finishes them with explicit tracks and vias, found by an A* maze router on
a 0.05 mm grid over a window around the connection, using the same copper
model (``drc.Item``) as the scripted DRC:

* ``complete_signals``  joins the unconnected pad groups of every net that
  is not a copper-pour net (VIN_RAW, +1V1, USB_DP, ...);
* ``stitch_pours``      joins ground-pour islands to the main pour with vias
  (and short tracks for pads/tracks that the pour does not reach).

Everything is deterministic (no randomness, ordered iteration).  KiCad's own
DRC is the judge afterwards (``build.py check``).

Coordinates here are KiCad file coordinates (board origin included);
``to_board`` subtracts the origin when the result goes back to the writer.
"""

from __future__ import annotations

import heapq
import math
from collections import defaultdict

import numpy as np

from drc import FAB, Item, _inside, distance, pour_components as _pour_components, spatial_grid, union_find

RES = 0.05  # grid pitch (mm)
CLR = FAB["min_clearance"] + 0.02  # router clearance: DRC minimum plus margin
VIA_D, VIA_DRILL = 0.5, 0.3
VIA_PENALTY = 40.0  # in grid steps
LAYERS = ("F.Cu", "B.Cu")


# ---------------------------------------------------------------------------
# Geometry helpers (vectorised over grid points)
# ---------------------------------------------------------------------------


def _dist_segment(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    if L == 0.0:
        return np.hypot(px - ax, py - ay)
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / L, 0.0, 1.0)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _dist_core(px, py, it: Item):
    """Distance from points to the item's core shape (segment or polygon); 0 inside a polygon."""
    if it.poly is None:
        return _dist_segment(px, py, it.a, it.b)
    d = np.full(px.shape, np.inf)
    for p, q in zip(it.poly, it.poly[1:] + it.poly[:1]):
        d = np.minimum(d, _dist_segment(px, py, p, q))
    inside = np.zeros(px.shape, dtype=bool)
    for (x1, y1), (x2, y2) in zip(it.poly, it.poly[1:] + it.poly[:1]):
        if y1 == y2:
            continue
        cond = (y1 > py) != (y2 > py)
        xi = (x2 - x1) * (py - y1) / (y2 - y1) + x1
        inside ^= cond & (px < xi)
    d[inside] = 0.0
    return d


class Window:
    """Rectangular routing window with per-layer clearance fields."""

    def __init__(self, x0: float, y0: float, x1: float, y1: float, anchor: tuple[float, float]):
        # Align the grid so that ``anchor`` is exactly on a grid point.
        self.x0 = anchor[0] - math.ceil((anchor[0] - x0) / RES) * RES
        self.y0 = anchor[1] - math.ceil((anchor[1] - y0) / RES) * RES
        self.nx = int((x1 - self.x0) / RES) + 1
        self.ny = int((y1 - self.y0) / RES) + 1
        xs = self.x0 + np.arange(self.nx) * RES
        ys = self.y0 + np.arange(self.ny) * RES
        self.px, self.py = np.meshgrid(xs, ys)

    def cell(self, x: float, y: float) -> tuple[int, int]:
        return int(round((x - self.x0) / RES)), int(round((y - self.y0) / RES))

    def xy(self, ix: int, iy: int) -> tuple[float, float]:
        return self.x0 + ix * RES, self.y0 + iy * RES


def clearance_fields(win: Window, items: list[Item], holes: list, net: str, limit: float, clr_of=None, route_clr: float = CLR):
    """Per layer: distance from each cell to the nearest copper of a different
    net (surface distance, capped at ``limit``); plus the distance to the
    nearest foreign drilled hole edge."""
    fields = {ly: np.full((win.ny, win.nx), limit) for ly in LAYERS}
    hole_d = np.full((win.ny, win.nx), limit)
    hole_same = np.full((win.ny, win.nx), limit)
    wx0, wy0 = win.x0 - limit, win.y0 - limit
    wx1, wy1 = win.x0 + win.nx * RES + limit, win.y0 + win.ny * RES + limit
    for it in items:
        if it.net == net and net:
            continue
        x0, y0, x1, y1 = it.bbox
        if x1 < wx0 or x0 > wx1 or y1 < wy0 or y0 > wy1:
            continue
        ix0 = max(0, int((x0 - limit - win.x0) / RES))
        ix1 = min(win.nx, int((x1 + limit - win.x0) / RES) + 2)
        iy0 = max(0, int((y0 - limit - win.y0) / RES))
        iy1 = min(win.ny, int((y1 + limit - win.y0) / RES) + 2)
        if ix0 >= ix1 or iy0 >= iy1:
            continue
        sx, sy = win.px[iy0:iy1, ix0:ix1], win.py[iy0:iy1, ix0:ix1]
        # KiCad applies the larger of the two net-class clearances (power classes need more).
        extra = max(0.0, clr_of(it.net) - route_clr) if clr_of else 0.0
        d = _dist_core(sx, sy, it) - it.r - extra
        for ly in it.layers & set(LAYERS):
            f = fields[ly][iy0:iy1, ix0:ix1]
            np.minimum(f, d, out=f)
    for hx, hy, hd, ref, hnet in holes:
        same = bool(hnet == net and net)
        if hx < wx0 or hx > wx1 or hy < wy0 or hy > wy1:
            continue
        ix0 = max(0, int((hx - limit - win.x0) / RES))
        ix1 = min(win.nx, int((hx + limit - win.x0) / RES) + 2)
        iy0 = max(0, int((hy - limit - win.y0) / RES))
        iy1 = min(win.ny, int((hy + limit - win.y0) / RES) + 2)
        if ix0 >= ix1 or iy0 >= iy1:
            continue
        d = np.hypot(win.px[iy0:iy1, ix0:ix1] - hx, win.py[iy0:iy1, ix0:ix1] - hy) - hd / 2
        f = (hole_same if same else hole_d)[iy0:iy1, ix0:ix1]
        np.minimum(f, d, out=f)
    return fields, hole_d, hole_same


# ---------------------------------------------------------------------------
# A* maze router
# ---------------------------------------------------------------------------


def maze(win: Window, fields, hole_d, hole_same, clr: float, width: float, start: tuple[float, float], start_layers, goal: tuple[float, float],
         goal_layers, edge: tuple[float, float, float, float] | None):
    """Shortest legal path between two points; returns [(layer, x, y), ...] or None."""
    nx, ny = win.nx, win.ny
    half = width / 2
    blk = {}
    for ly in LAYERS:
        b = fields[ly] < clr + half
        if edge is not None:  # keep copper 0.3 mm + half width off the board edge
            m = FAB["edge_clearance"] + half
            b |= (win.px < edge[0] + m) | (win.px > edge[2] - m) | (win.py < edge[1] + m) | (win.py > edge[3] - m)
        blk[ly] = b
    via_blk = np.zeros((ny, nx), dtype=bool)
    for ly in LAYERS:
        via_blk |= fields[ly] < clr + VIA_D / 2
    via_blk |= hole_d < FAB["min_hole_to_hole"] + VIA_DRILL / 2  # different-net holes: 0.5 mm
    via_blk |= hole_same < FAB["min_hole_to_hole_same_net"] + VIA_DRILL / 2 + 0.01  # same net: 0.254 mm
    if edge is not None:
        m = FAB["edge_clearance"] + VIA_D / 2
        via_blk |= (win.px < edge[0] + m) | (win.px > edge[2] - m) | (win.py < edge[1] + m) | (win.py > edge[3] - m)
    flat_blk = [blk[ly].ravel().tolist() for ly in LAYERS]
    flat_via = via_blk.ravel().tolist()
    N = nx * ny
    sx, sy = win.cell(*start)
    gx, gy = win.cell(*goal)
    starts = [(LAYERS.index(ly), sy * nx + sx) for ly in start_layers]
    goals = {(LAYERS.index(ly), gy * nx + gx) for ly in goal_layers}
    if not (0 <= sx < nx and 0 <= sy < ny and 0 <= gx < nx and 0 <= gy < ny):
        return None
    moves = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    gscore: dict[tuple[int, int], float] = {}
    prev: dict[tuple[int, int], tuple[int, int] | None] = {}
    heap: list = []

    def h(idx: int) -> float:
        x, y = idx % nx, idx // nx
        dx, dy = abs(x - gx), abs(y - gy)
        return (dx + dy) + (1.414 - 2) * min(dx, dy)

    for st in starts:
        gscore[st] = 0.0
        prev[st] = None
        heapq.heappush(heap, (h(st[1]), 0.0, st[0], st[1]))
    found = None
    while heap:
        f, g, ly, idx = heapq.heappop(heap)
        if g > gscore.get((ly, idx), 1e18) + 1e-9:
            continue
        if (ly, idx) in goals:
            found = (ly, idx)
            break
        x, y = idx % nx, idx // nx
        for dx, dy, c in moves:
            x2, y2 = x + dx, y + dy
            if not (0 <= x2 < nx and 0 <= y2 < ny):
                continue
            i2 = y2 * nx + x2
            if flat_blk[ly][i2] and (ly, i2) not in goals:
                continue
            if dx and dy and (flat_blk[ly][y * nx + x2] or flat_blk[ly][y2 * nx + x]):
                continue  # no corner cutting
            g2 = g + c
            if g2 < gscore.get((ly, i2), 1e18) - 1e-9:
                gscore[(ly, i2)] = g2
                prev[(ly, i2)] = (ly, idx)
                heapq.heappush(heap, (g2 + h(i2), g2, ly, i2))
        ly2 = 1 - ly
        if not flat_via[idx] and not flat_blk[ly2][idx]:
            g2 = g + VIA_PENALTY
            if g2 < gscore.get((ly2, idx), 1e18) - 1e-9:
                gscore[(ly2, idx)] = g2
                prev[(ly2, idx)] = (ly, idx)
                heapq.heappush(heap, (g2 + h(idx), g2, ly2, idx))
    if found is None:
        return None
    path = []
    cur = found
    while cur is not None:
        ly, idx = cur
        path.append((LAYERS[ly],) + win.xy(idx % nx, idx // nx))
        cur = prev[cur]
    path.reverse()
    return path


def path_to_copper(path, net: str, width: float, start: tuple[float, float], goal: tuple[float, float]):
    """Compress a cell path into track segments and vias (file coordinates)."""
    tracks, vias = [], []
    pts = [(ly, x, y) for ly, x, y in path]
    # exact endpoints
    pts[0] = (pts[0][0], start[0], start[1])
    pts[-1] = (pts[-1][0], goal[0], goal[1])
    run = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        if a[0] != b[0]:  # layer change: via at this point
            vias.append({"x": a[1], "y": a[2], "size": VIA_D, "drill": VIA_DRILL, "net": net})
            _flush(run, tracks, net, width)
            run = [b]
        else:
            run.append(b)
    _flush(run, tracks, net, width)
    return tracks, vias


def _flush(run, tracks, net, width):
    if len(run) < 2:
        return
    layer = run[0][0]
    out = [run[0]]
    for i in range(1, len(run) - 1):
        p0, p1, p2 = out[-1], run[i], run[i + 1]
        cross = (p1[1] - p0[1]) * (p2[2] - p1[2]) - (p1[2] - p0[2]) * (p2[1] - p1[1])
        if abs(cross) > 1e-9:
            out.append(p1)
    out.append(run[-1])
    for a, b in zip(out, out[1:]):
        if (a[1], a[2]) != (b[1], b[2]):
            tracks.append({"x1": a[1], "y1": a[2], "x2": b[1], "y2": b[2], "w": round(width, 4), "layer": layer, "net": net})


def route_points(items, holes, edge, net: str, p0, layers0, p1, layers1, widths, margin: float = 6.0, clr_of=None):
    """Try each width in turn; widen the window if no path is found."""
    for width in widths:
        for m in (margin, margin * 2.5):
            x0, x1 = min(p0[0], p1[0]) - m, max(p0[0], p1[0]) + m
            y0, y1 = min(p0[1], p1[1]) - m, max(p0[1], p1[1]) + m
            win = Window(x0, y0, x1, y1, p0)
            clr = max(CLR, clr_of(net)) if clr_of else CLR
            fields, hole_d, hole_same = clearance_fields(win, items, holes, net, clr + max(width, VIA_D) / 2 + 0.6, clr_of, clr)
            path = maze(win, fields, hole_d, hole_same, clr, width, p0, layers0, p1, layers1, edge)
            if path:
                return path_to_copper(path, net, width, p0, p1) + (width,)
    return None


def add_items(items: list[Item], holes: list, tracks, vias) -> None:
    for t in tracks:
        items.append(Item("track", t["net"], {t["layer"]}, (t["x1"], t["y1"]), (t["x2"], t["y2"]), t["w"] / 2))
    for v in vias:
        c = (v["x"], v["y"])
        items.append(Item("via", v["net"], set(LAYERS), c, c, v["size"] / 2))
        items[-1].ref = f"via@{c[0]:.2f},{c[1]:.2f}:{v['drill']}"
        holes.append((c[0], c[1], v["drill"], items[-1].ref, v["net"]))



def _groups(items, pads_by_net, net):
    grid = spatial_grid(items)
    findp = union_find(items, grid)
    idx_of = {id(it): k for k, it in enumerate(items)}
    groups: dict[int, list[Item]] = defaultdict(list)
    for pad in pads_by_net[net]:
        groups[findp(idx_of[id(pad)])].append(pad)
    return [g for _, g in sorted(groups.items(), key=lambda kv: min(p.ref for p in kv[1]))]


def pour_components(items, pads_by_net, polys, net):
    """Components of the net's copper and pour polygons (see drc.pour_components)."""
    return _pour_components(items, polys, net, union_find(items, spatial_grid(items)))


def _via_ok(items, grid, holes, net, c, edge, clr_of=None) -> bool:
    cand = Item("via", net, set(LAYERS), c, c, VIA_D / 2)
    for gx in range(int(math.floor((c[0] - 1.2) / 2.0)), int(math.floor((c[0] + 1.2) / 2.0)) + 1):
        for gy in range(int(math.floor((c[1] - 1.2) / 2.0)), int(math.floor((c[1] + 1.2) / 2.0)) + 1):
            for idx in grid.get((gx, gy), []):
                it = items[idx]
                if it.net == net and net:
                    continue
                if distance(cand, it) < (max(CLR, clr_of(it.net), clr_of(net)) if clr_of else CLR):
                    return False
    for hx, hy, hd, ref, hnet in holes:
        need = FAB["min_hole_to_hole_same_net"] if hnet == net else FAB["min_hole_to_hole"]
        if math.hypot(hx - c[0], hy - c[1]) - hd / 2 - VIA_DRILL / 2 < need + 0.01:
            return False
    if edge is not None:
        m = FAB["edge_clearance"] + VIA_D / 2
        if not (edge[0] + m < c[0] < edge[2] - m and edge[1] + m < c[1] < edge[3] - m):
            return False
    return True


# ---------------------------------------------------------------------------
# Board state with rip-up and re-route
# ---------------------------------------------------------------------------


class State:
    """Copper added on top of the fixed pads (tracks/vias in file coordinates), with
    rip-up of a blocking net when a connection cannot be routed."""

    def __init__(self, pad_items, pad_holes, pads_by_net, edge, zone_nets, power_nets, log: list[str]):
        self.pad_items, self.pad_holes, self.pads_by_net = pad_items, pad_holes, pads_by_net
        self.edge, self.zone_nets, self.power_nets, self.log = edge, set(zone_nets), power_nets, log
        self.tracks: list[dict] = []
        self.vias: list[dict] = []

    def build(self):
        items = list(self.pad_items)
        holes = list(self.pad_holes)
        add_items(items, holes, self.tracks, self.vias)
        return items, holes

    def clr_of(self, net: str) -> float:
        """Router clearance for a net: its net-class clearance plus a margin (power classes 0.2 mm)."""
        return 0.22 if net in self.power_nets else CLR

    def widths_for(self, net: str) -> list[float]:
        w = self.power_nets.get(net)
        return [x for x in (1.5, 1.0, 0.6, 0.4, 0.25) if x <= w] if w else [0.2, 0.15]

    def snapshot(self):
        return list(self.tracks), list(self.vias)

    def restore(self, snap) -> None:
        self.tracks, self.vias = list(snap[0]), list(snap[1])

    def rip(self, net: str) -> int:
        n = sum(1 for t in self.tracks if t["net"] == net) + sum(1 for v in self.vias if v["net"] == net)
        self.tracks = [t for t in self.tracks if t["net"] != net]
        self.vias = [v for v in self.vias if v["net"] != net]
        return n

    def add(self, tracks, vias) -> None:
        self.tracks += tracks
        self.vias += vias

    # -- routing ---------------------------------------------------------
    def blockers(self, net: str, points) -> list[str]:
        """Signal nets with copper (tracks/vias) within 0.8 mm of ``points``, fewest segments first."""
        items, _ = self.build()
        count: dict[str, int] = defaultdict(int)
        for t in self.tracks:
            count[t["net"]] += 1
        for v in self.vias:
            count[v["net"]] += 1
        found = set()
        for p in points:
            probe = Item("via", net, set(LAYERS), p, p, 0.0)
            for it in items:
                if it.kind != "pad" and it.net and it.net != net and it.net not in self.zone_nets and distance(probe, it) < 0.8:
                    found.add(it.net)
        return sorted(found, key=lambda n: (count[n], n))

    def route(self, net: str, p0, layers0, p1, layers1, extra_via=None, ripup: bool = True) -> bool:
        """Route p0 -> p1; on failure rip up each blocking net in turn, route this connection first
        and re-join the ripped net.  Mutates the state; returns success."""
        def attempt() -> bool:
            items, holes = self.build()
            if extra_via is not None:
                add_items(items, holes, [], [extra_via])
            res = route_points(items, holes, self.edge, net, p0, layers0, p1, layers1, self.widths_for(net), clr_of=self.clr_of)
            if res is None:
                return False
            tracks, vias, width = res
            self.add(tracks, vias + ([extra_via] if extra_via is not None else []))
            self.log.append(f"{net}: routed {len(tracks)} segments, {len(vias)} vias, width {width} mm")
            return True

        if attempt():
            return True
        if not ripup:
            return False
        for blk in self.blockers(net, [p0, p1])[:4]:
            snap = self.snapshot()
            removed = self.rip(blk)
            if attempt() and self.complete_net(blk, ripup=False):
                self.log.append(f"{net}: ripped up and re-routed {blk} ({removed} items)")
                return True
            self.restore(snap)
        return False

    def complete_net(self, net: str, ripup: bool = True) -> bool:
        for _ in range(12):
            items, _holes = self.build()
            groups = _groups(items, self.pads_by_net, net)
            if len(groups) <= 1:
                return True
            best = None
            for pa in groups[0]:
                for g in groups[1:]:
                    for pb in g:
                        d = math.dist(pa.a, pb.a)
                        if best is None or d < best[0]:
                            best = (d, pa, pb)
            _, pa, pb = best
            if not self.route(net, pa.a, sorted(pa.layers & set(LAYERS)), pb.a, sorted(pb.layers & set(LAYERS)), ripup=ripup):
                self.log.append(f"{net}: NO PATH between {pa.ref} and {pb.ref}")
                return False
        return False

    def complete_signals(self) -> None:
        for net in sorted(self.pads_by_net):
            if net not in self.zone_nets:
                self.complete_net(net)

    # -- hole spacing ------------------------------------------------------
    def repair_holes(self) -> bool:
        """Remove one via of every different-net via pair closer than the fab hole-to-hole minimum
        (Freerouting has no such rule) with the tracks attached to it, then prune signal copper left
        without a pad.  complete_signals/stitch re-route with the rule enforced."""
        need = FAB["min_hole_to_hole"]
        drop_v: set[int] = set()

        def touches(t, v) -> bool:
            return t["net"] == v["net"] and ((abs(t["x1"] - v["x"]) < 1e-3 and abs(t["y1"] - v["y"]) < 1e-3)
                                             or (abs(t["x2"] - v["x"]) < 1e-3 and abs(t["y2"] - v["y"]) < 1e-3))

        for i in range(len(self.vias)):
            for j in range(i + 1, len(self.vias)):
                a, b = self.vias[i], self.vias[j]
                if i in drop_v or j in drop_v:
                    continue
                lim = FAB["min_hole_to_hole_same_net"] if a["net"] == b["net"] else need
                if math.hypot(a["x"] - b["x"], a["y"] - b["y"]) - a["drill"] / 2 - b["drill"] / 2 < lim - 1e-6:
                    deg = lambda v: sum(1 for t in self.tracks if touches(t, v))  # noqa: E731
                    drop_v.add(i if deg(a) <= deg(b) else j)
        if not drop_v:
            return False
        drop_t = set()
        for i in drop_v:
            v = self.vias[i]
            drop_t |= {k for k, t in enumerate(self.tracks) if touches(t, v)}
            self.log.append(f"hole spacing: removed via at ({v['x']:.2f}, {v['y']:.2f}) on {v['net']}")
        self.tracks = [t for k, t in enumerate(self.tracks) if k not in drop_t]
        self.vias = [v for k, v in enumerate(self.vias) if k not in drop_v]
        self.prune_dangling()
        self.prune_spurs()
        return True

    def prune_spurs(self) -> int:
        """Remove signal tracks with a free end (an end touching no pad, via or other track of the
        net): leftovers of rip-up.  Repeats until none is left; returns the number removed."""
        removed = 0
        while True:
            items, _ = self.build()
            npad = len(self.pad_items)
            grid = spatial_grid(items)
            drop = set()
            for k, t in enumerate(self.tracks):
                if t["net"] in self.zone_nets:
                    continue
                me = npad + k
                for end in ((t["x1"], t["y1"]), (t["x2"], t["y2"])):
                    probe = Item("via", t["net"], {t["layer"]}, end, end, 0.0)
                    gx, gy = int(math.floor(end[0] / 2.0)), int(math.floor(end[1] / 2.0))
                    touched = False
                    for idx in grid.get((gx, gy), []):
                        o = items[idx]
                        if idx == me or o.net != t["net"] or t["layer"] not in o.layers:
                            continue
                        if distance(probe, o) <= 1e-3:
                            touched = True
                            break
                    if not touched:
                        drop.add(k)
                        break
            if not drop:
                return removed
            self.tracks = [t for k, t in enumerate(self.tracks) if k not in drop]
            removed += len(drop)

    def prune_dangling(self) -> None:
        items, _ = self.build()
        npad = len(self.pad_items)
        findp = union_find(items, spatial_grid(items))
        has_pad: dict[int, bool] = defaultdict(bool)
        for k in range(npad):
            has_pad[findp(k)] = True
        nt = len(self.tracks)
        self.tracks = [t for k, t in enumerate(self.tracks) if t["net"] in self.zone_nets or has_pad[findp(npad + k)]]
        self.vias = [v for k, v in enumerate(self.vias) if v["net"] in self.zone_nets or has_pad[findp(npad + nt + k)]]


# ---------------------------------------------------------------------------
# Ground-pour stitching
# ---------------------------------------------------------------------------


def stitch_pours(state: State, polys_by_net, max_new: int = 400) -> int:
    """Join every component of a pour net that holds copper to the main component with
    vias inside the pours and, where the pour does not reach, a short track + via.  Returns
    the number of connections made."""
    made = 0
    for net, polys in sorted(polys_by_net.items()):
        skipped: set[int] = set()
        for _ in range(max_new):
            items, holes = state.build()
            comps = [c for c in pour_components(items, state.pads_by_net, polys, net) if any(kind == "i" for kind, _ in c)]

            def weight(c):
                return sum(1 for kind, k in c if kind == "i" and items[k].kind == "pad")

            comps.sort(key=lambda c: (-weight(c), min(c)))
            todo = [c for c in comps[1:] if min(k for kind, k in c if kind == "i") not in skipped]
            if not todo:
                break
            main, orphan = comps[0], todo[0]
            main_polys = {k for kind, k in main if kind == "z"}
            if _connect_orphan(state, items, holes, polys, net, main_polys, orphan):
                made += 1
            else:
                skipped.add(min(k for kind, k in orphan if kind == "i"))
                names = [items[k].ref or items[k].kind for kind, k in orphan if kind == "i"][:3]
                state.log.append(f"{net}: could not join the component holding {names}")
        else:
            state.log.append(f"{net}: stitching stopped at the safety limit")
    return made


def _connect_orphan(state: State, items, holes, polys, net, main_polys, orphan) -> bool:
    grid = spatial_grid(items)
    edge = state.edge
    orphan_polys = [k for kind, k in orphan if kind == "z"]
    orphan_items = [k for kind, k in orphan if kind == "i"]
    via = lambda c: {"x": round(c[0], 4), "y": round(c[1], 4), "size": VIA_D, "drill": VIA_DRILL, "net": net}  # noqa: E731
    # 1. A stitching via inside an orphan polygon that also lies in a main polygon of the other layer.
    for zi in sorted(orphan_polys):
        layer, pts = polys[zi]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x = min(xs)
        while x <= max(xs):
            y = min(ys)
            while y <= max(ys):
                c = (x, y)
                if _inside(c, pts) and any(polys[mz][0] != layer and _inside(c, polys[mz][1]) for mz in sorted(main_polys)) \
                        and _via_ok(items, grid, holes, net, c, edge, state.clr_of):
                    state.add([], [via(c)])
                    return True
                y += 0.4
            x += 0.4
    # 2. Reach the main pour with a short track + via from an item of the orphan.
    src_items = [items[k] for k in orphan_items]
    src_items.sort(key=lambda it: (it.kind != "pad", it.ref))
    anchors = []
    for it in src_items:
        for pt in {it.a, it.b}:
            anchors.append((pt, it))
    for ripup in (False, True):
        for a, src in anchors:
            layers = sorted(src.layers & set(LAYERS)) or ["F.Cu"]
            for r in (0.8, 1.2, 1.6, 2.0, 2.6, 3.2, 4.0):
                for i in range(24):
                    ang = 2 * math.pi * i / 24
                    c = (round(a[0] + r * math.cos(ang), 3), round(a[1] + r * math.sin(ang), 3))
                    if not _via_ok(items, grid, holes, net, c, edge, state.clr_of):
                        continue
                    if not any(_inside(c, polys[mz][1]) for mz in main_polys):
                        continue
                    if state.route(net, a, layers, c, list(LAYERS), extra_via=via(c), ripup=ripup):
                        return True
                if ripup and r > 1.6:
                    break
    return False
