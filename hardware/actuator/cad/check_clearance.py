#!/usr/bin/env python3
"""Exact B-rep interference check of the assembled arm.

Every printed part and every servo envelope is placed by forward
kinematics; each pair of solids on *different* links is intersected with
OpenCASCADE and any overlap above ``TOL_MM3`` is reported.  Pairs that
mesh by design (pinion against the driven gear) are excluded and listed.

Two pose sets are checked, for each of the four tools (tool actuator at a
random position in its stroke):

* named poses and single-joint sweeps (every joint over its full range in
  5 deg steps, all others at zero) - these cover the adjacent-link pairs,
  whose relative pose depends on one joint only;
* ``N_RANDOM`` seeded random poses over the whole joint box - these cover
  every pair of links two or more joints apart (tool vs turret/base/
  forearm, wrist vs base, ...).

A cheap oriented-bounding-box separating-axis test removes almost all
pairs; the survivors go to the exact OpenCASCADE boolean (cached by the
relative pose of the two links).

At allowed poses the check also requires a minimum clearance of ``CLEARANCE_MM`` (3 mm,
exact distance) between links that can approach each other (not both in the wrist sub-tree),
on the random allowed poses and on seeded poses lying ON each coupled-limit surface (the
worst case of that limit).  A closer approach fails the check like a collision.

Poses inside every single-joint limit but outside the coupled limits
``Arm.coupled_limits`` (sums of joint angles, see firmware/INTERFACE.md §3.2)
are *forbidden*: collisions there are expected and are reported as the
justification for the limits.  ANY collision
at an allowed pose, adjacent or not, fails the check (exit 1).

    python cad/check_clearance.py          # writes cad/out/clearance.json
    python cad/check_clearance.py --derive # also prints the extreme angle sums at which collisions occur
"""

from __future__ import annotations

import concurrent.futures
import itertools
import json
import multiprocessing
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
from build123d import Location, Part, Pos, Rot  # noqa: E402
from OCP.BRepExtrema import BRepExtrema_DistShapeShape  # noqa: E402
from OCP.BRepGProp import BRepGProp  # noqa: E402
from OCP.GProp import GProp_GProps  # noqa: E402

from assembly import build_assembly  # noqa: E402
from parts import tool_button_presser as presser  # noqa: E402
from params import DEFAULT  # noqa: E402

TOL_MM3 = 1.0
CLEARANCE_MM = 3.0  # minimum distance required at allowed poses between links that can approach each other
WRIST_SUBTREE = {"wrist", "flange", "gripper", "gripper_finger_a", "gripper_finger_b", "knob_turner", "knob_output",
                 "button_presser", "presser_plunger", "slider_pusher"}
ARM_LINKS = ["base", "turret", "upper_arm", "forearm", "wrist", "flange"]
TOOL_LINKS = {"gripper": ["gripper", "gripper_finger_a", "gripper_finger_b"],
              "knob_turner": ["knob_turner", "knob_output"],
              "button_presser": ["button_presser", "presser_plunger"],
              "slider_pusher": ["slider_pusher"]}
# Gear meshes are line contacts at the pitch point; their phase is not
# modelled, so these pairs are checked by the gear geometry instead.
EXCLUDE = {("turret:pinion_shoulder", "upper_arm:upper_arm"), ("upper_arm:pinion_elbow", "forearm:forearm"),
           ("knob_turner:knob_servo_gear", "knob_output:knob_output_gear"),
           ("gripper:gripper_pinion", "gripper_finger_a:gripper_rack"),
           ("gripper:gripper_pinion", "gripper_finger_b:gripper_rack")}
PARENT = {"turret": "base", "upper_arm": "turret", "forearm": "upper_arm", "wrist": "forearm", "flange": "wrist",
          "gripper": "flange", "knob_turner": "flange", "button_presser": "flange", "slider_pusher": "flange",
          "gripper_finger_a": "gripper", "gripper_finger_b": "gripper", "knob_output": "knob_turner",
          "presser_plunger": "button_presser"}


def hops(a: str, b: str) -> int:
    """Tree distance between two links."""
    def chain(x: str) -> list[str]:
        out = [x]
        while out[-1] in PARENT:
            out.append(PARENT[out[-1]])
        return out
    ca, cb = chain(a), chain(b)
    common = next(x for x in ca if x in cb)
    return ca.index(common) + cb.index(common)
# Faces in contact by design (horn faces against pinions/brackets) are
# coplanar and give zero overlap volume, so they need no exclusion.


def distance_mm(a, b) -> float:
    """Exact minimum distance between two solids (mm)."""
    d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    d.Perform()
    return float(d.Value())


def volume(shape: Part | None) -> float:
    if shape is None or getattr(shape, "_wrapped", None) is None:
        return 0.0  # empty boolean result
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props)
    return props.Mass()


def link_solids(p) -> dict[str, list[tuple[str, Part]]]:
    asm = build_assembly(p)
    out: dict[str, list[tuple[str, Part]]] = {}
    built: dict[str, Part] = {}
    for d in asm.parts:
        if not d.in_sim:
            continue
        for link, loc in d.instances:
            if link in ("none", "tool_rack"):
                continue
            if d.name not in built:
                built[d.name] = d.build(p)
            out.setdefault(link, []).append((f"{link}:{d.name}", loc * built[d.name]))
    return out


def fk(p, q: dict[str, float], tool_q: dict[str, float]) -> dict[str, Location]:
    a = p.arm
    loc = {"base": Location()}
    loc["turret"] = Pos(0, 0, a.base_height) * Rot(Z=q.get("base_yaw", 0.0))
    loc["upper_arm"] = loc["turret"] * Pos(0, 0, a.shoulder_height) * Rot(Y=q.get("shoulder_pitch", 0.0))
    loc["forearm"] = loc["upper_arm"] * Pos(0, 0, a.l_upper) * Rot(Y=q.get("elbow_pitch", 0.0))
    loc["wrist"] = loc["forearm"] * Pos(0, 0, a.l_fore) * Rot(Y=q.get("wrist_pitch", 0.0))
    loc["flange"] = loc["wrist"] * Pos(0, 0, a.l_wrist) * Rot(Z=q.get("wrist_roll", 0.0))
    for tool in TOOL_LINKS:
        loc[tool] = loc["flange"]
    loc["gripper_finger_a"] = loc["gripper"] * Pos(0, tool_q.get("gripper", 0.0), 0)
    loc["gripper_finger_b"] = loc["gripper"] * Pos(0, -tool_q.get("gripper", 0.0), 0)
    loc["knob_output"] = loc["knob_turner"] * Rot(Z=tool_q.get("knob", 0.0))
    loc["presser_plunger"] = loc["button_presser"] * Pos(0, 0, tool_q.get("presser", 0.0))
    # The cam turns with the plunger: full lift at 0, half a turn at -stroke.
    zc = presser._z(p)["cam"]
    turn = 180.0 * -tool_q.get("presser", 0.0) / p.tools.presser_stroke
    loc["presser_cam"] = loc["button_presser"] * Pos(0, 0, zc) * Rot(X=turn) * Pos(0, 0, -zc)
    return loc


N_ALLOWED = 2000  # random poses inside the coupled limits (must be collision free)
N_FORBIDDEN = 500  # random poses outside them (collisions expected)
N_RANDOM = N_ALLOWED + N_FORBIDDEN
N_BOUNDARY = 150  # poses per coupled-limit surface (all four tools each)
SEED = 20261113
SWEEP_STEP_DEG = 5.0

def pitch_sum_ok(p, q: dict[str, float]) -> bool:
    """Inside every coupled limit of ``Arm.coupled_limits``."""
    return p.arm.coupled_ok(q)


def poses(p) -> list[tuple[str, dict[str, float]]]:
    out = [("zero", {})]
    for j in p.arm.joints:
        out.append((f"{j.name}=lower", {j.name: j.lower_deg}))
        out.append((f"{j.name}=upper", {j.name: j.upper_deg}))
    out += [
        ("home_rest", {"shoulder_pitch": 30.0, "elbow_pitch": 90.0, "wrist_pitch": 45.0}),
        ("reach_forward", {"shoulder_pitch": 90.0, "elbow_pitch": 0.0, "wrist_pitch": 0.0}),
        ("table_pick_near", {"shoulder_pitch": 15.0, "elbow_pitch": 122.0, "wrist_pitch": 40.0}),
        ("table_pick_far", {"shoulder_pitch": 55.0, "elbow_pitch": 95.0, "wrist_pitch": 30.0}),
        ("folded_back", {"shoulder_pitch": -20.0, "elbow_pitch": 125.0, "wrist_pitch": -100.0}),
        ("wrist_curl", {"shoulder_pitch": 30.0, "elbow_pitch": 100.0, "wrist_pitch": 100.0}),
        ("wrist_curl_neg", {"shoulder_pitch": 30.0, "elbow_pitch": 100.0, "wrist_pitch": -100.0}),
    ]
    for j in p.arm.joints:  # single-joint sweeps (adjacent-link pairs)
        a = j.lower_deg
        while a <= j.upper_deg + 1e-9:
            out.append((f"sweep {j.name}={a:.1f}", {j.name: a}))
            a += SWEEP_STEP_DEG
    return out


def random_poses(p, n_allowed: int = N_ALLOWED, n_forbidden: int = N_FORBIDDEN,
                 seed: int = SEED) -> list[tuple[str, dict[str, float]]]:
    """Seeded uniform samples of the joint box: ``n_allowed`` inside the coupled
    pitch limits (these must be collision free) and ``n_forbidden`` outside them
    (collisions expected: they justify the limits)."""
    rng = random.Random(seed)
    inside, outside = [], []
    while len(inside) < n_allowed or len(outside) < n_forbidden:
        q = {j.name: rng.uniform(j.lower_deg, j.upper_deg) for j in p.arm.joints}
        bucket = inside if pitch_sum_ok(p, q) else outside
        cap = n_allowed if bucket is inside else n_forbidden
        if len(bucket) < cap:
            bucket.append(q)
    return [(f"random{i}", q) for i, q in enumerate(inside + outside)]


def boundary_poses(p, n_per_limit: int = N_BOUNDARY, seed: int = SEED + 2) -> list[tuple[str, dict[str, float]]]:
    """Seeded poses ON each coupled-limit surface (sum of the limit's joints = its upper bound),
    all other joints random inside every limit: the worst case for that limit."""
    rng = random.Random(seed)
    J = {j.name: j for j in p.arm.joints}
    out = []
    for c in p.arm.coupled_limits:
        made = 0
        while made < n_per_limit:
            q = {j.name: rng.uniform(j.lower_deg, j.upper_deg) for j in p.arm.joints}
            solve = rng.choice(c.joints)
            q[solve] = c.hi - sum(q[j] for j in c.joints if j != solve)
            if not (J[solve].lower_deg <= q[solve] <= J[solve].upper_deg) or not p.arm.coupled_ok(q):
                continue
            out.append((f"boundary_{c.name}_{made}", q))
            made += 1
    return out


def tool_states(p, tool: str, rng: random.Random) -> dict[str, float]:
    t = p.tools
    if tool == "gripper":
        return {"gripper": rng.uniform(0.0, t.gripper_stroke)}
    if tool == "knob_turner":
        return {"knob": rng.uniform(-180.0, 180.0)}
    if tool == "button_presser":
        return {"presser": -rng.uniform(0.0, t.presser_stroke)}
    return {}


def matrix(loc: Location) -> np.ndarray:
    t = loc.wrapped.Transformation()
    m = np.eye(4)
    for i in range(3):
        for j in range(4):
            m[i, j] = t.Value(i + 1, j + 1)
    return m


def obb_overlap(ca, ra, ha, cb, rb, hb) -> bool:
    """Separating-axis test of two oriented boxes (centre, rotation, half extents)."""
    r = ra.T @ rb
    ar = np.abs(r) + 1e-9
    t = ra.T @ (cb - ca)
    for i in range(3):
        if abs(t[i]) > ha[i] + hb @ ar[i]:
            return False
    for j in range(3):
        if abs(t[:] @ r[:, j]) > ha @ ar[:, j] + hb[j]:
            return False
    for i in range(3):
        for j in range(3):
            i1, i2, j1, j2 = (i + 1) % 3, (i + 2) % 3, (j + 1) % 3, (j + 2) % 3
            if abs(t[i2] * r[i1, j] - t[i1] * r[i2, j]) > ha[i1] * ar[i2, j] + ha[i2] * ar[i1, j] + hb[j1] * ar[i, j2] + hb[j2] * ar[i, j1]:
                return False
    return True


class Checker:
    def __init__(self, p, solids) -> None:
        self.p = p
        self.solids = solids
        self.cache: dict[tuple, float] = {}
        # (link, name, solid, centre, half extents, frame key)
        self.items: dict[str, list] = {}
        for lk, lst in solids.items():
            rows = []
            for n, s in lst:
                bb = s.bounding_box()
                c = np.array([(bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2])
                h = np.array([(bb.max.X - bb.min.X) / 2, (bb.max.Y - bb.min.Y) / 2, (bb.max.Z - bb.min.Z) / 2])
                rows.append((n, s, c, h, "presser_cam" if n.endswith(":presser_cam") else lk))
            self.items[lk] = rows

    def pose_hits(self, tool: str, q: dict[str, float], tool_q: dict[str, float], pose_name: str,
                  pairs_filter, clear_mm: float = 0.0) -> list[dict]:
        """Collisions (overlap volume > TOL_MM3) and, when ``clear_mm`` > 0, near misses
        (closest distance < ``clear_mm``) between solids on different links.  The clearance
        requirement applies to pairs that can approach each other (not both inside the wrist
        sub-tree, whose relative pose only depends on the fully swept roll/tool actuators)."""
        p = self.p
        links = ARM_LINKS + TOOL_LINKS[tool]
        loc = fk(p, q, tool_q)
        mats = {k: matrix(v) for k, v in loc.items()}
        hits = []
        for la, lb in itertools.combinations(links, 2):
            if not pairs_filter(la, lb):
                continue
            need = clear_mm if (clear_mm > 0 and not (la in WRIST_SUBTREE and lb in WRIST_SUBTREE) and hops(la, lb) >= 2) else 0.0
            for na, sa, ca, ha, fa in self.items.get(la, []):
                Ta = mats[fa]
                wa = Ta[:3, :3] @ ca + Ta[:3, 3]
                for nb, sb, cb, hb, fb in self.items.get(lb, []):
                    if (na, nb) in EXCLUDE or (nb, na) in EXCLUDE:
                        continue
                    Tb = mats[fb]
                    wb = Tb[:3, :3] @ cb + Tb[:3, 3]
                    touching = obb_overlap(wa, Ta[:3, :3], ha, wb, Tb[:3, :3], hb)
                    if not touching and not (need and obb_overlap(wa, Ta[:3, :3], ha + need, wb, Tb[:3, :3], hb + need)):
                        continue
                    rel = np.linalg.inv(Ta) @ Tb
                    key = (na, nb, tuple(np.round(rel, 3).ravel()))
                    v = self.cache.get(key) if touching else 0.0
                    if touching and v is None:
                        v = volume((loc[fa] * sa) & (loc[fb] * sb))
                        self.cache[key] = v
                    base = {"tool": tool, "pose": pose_name, "a": na, "b": nb, "hops": hops(la, lb),
                            "q": {k: round(x, 2) for k, x in q.items()}, "tool_q": tool_q}
                    if v > TOL_MM3:
                        hits.append({**base, "overlap_mm3": round(v, 2), "kind": "collision", "distance_mm": 0.0})
                    elif need:
                        dkey = ("d",) + key
                        d = self.cache.get(dkey)
                        if d is None:
                            d = distance_mm(loc[fa] * sa, loc[fb] * sb)
                            self.cache[dkey] = d
                        if d < need:
                            hits.append({**base, "overlap_mm3": 0.0, "kind": "clearance", "distance_mm": round(d, 2)})
        return hits


TOOL_CONFIGS = {"gripper": [{"gripper": 0.0}, {"gripper": 30.0}], "knob_turner": [{"knob": 0.0}],
                "button_presser": [{"presser": 0.0}, {"presser": -8.0}], "slider_pusher": [{}]}


_WORKER: dict = {}


def _init_worker() -> None:
    """Per-process state: the solids are built once in every worker."""
    p = DEFAULT
    _WORKER["chk"] = Checker(p, link_solids(p))


def _run_task(task) -> list[dict]:
    tool, name, q, tq, mode = task
    pairs = (lambda a, b: True) if mode == "all" else (lambda a, b: hops(a, b) >= 2)
    return _WORKER["chk"].pose_hits(tool, q, tq, name, pairs, clear_mm=CLEARANCE_MM if mode == "clear" else 0.0)


def main() -> int:
    derive = "--derive" in sys.argv
    p = DEFAULT
    jobs = int(os.environ.get("CLEARANCE_JOBS", "6"))  # worker processes (keep <= 8 on the shared machine)
    rng = random.Random(SEED + 1)
    tasks = []
    n_checks = {"named_and_sweeps": 0, "random": 0}
    for tool, cfgs in TOOL_CONFIGS.items():
        for pose_name, q in poses(p):
            for tq in cfgs:
                n_checks["named_and_sweeps"] += 1
                tasks.append((tool, pose_name, q, tq, "all"))
    for pose_name, q in random_poses(p):
        for tool in TOOL_CONFIGS:
            n_checks["random"] += 1
            tasks.append((tool, pose_name, q, tool_states(p, tool, rng), "clear" if pitch_sum_ok(p, q) else "far"))
    n_checks["boundary"] = 0
    for pose_name, q in boundary_poses(p):
        for tool in TOOL_CONFIGS:
            n_checks["boundary"] += 1
            tasks.append((tool, pose_name, q, tool_states(p, tool, rng), "clear"))
    hits_allowed, hits_forbidden = [], []
    ctx = multiprocessing.get_context("spawn")
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs, mp_context=ctx, initializer=_init_worker) as pool:
        for task, hits in zip(tasks, pool.map(_run_task, tasks, chunksize=25)):
            for h in hits:
                (hits_allowed if pitch_sum_ok(p, task[2]) else hits_forbidden).append(h)
    for h in hits_allowed:
        print(f"{h['kind'].upper():9s} {h['distance_mm']:.2f} mm {h['tool']:15s} {h['pose']:26s} {h['a']} <-> {h['b']}: {h['overlap_mm3']} mm3  q={h['q']}")
    forbidden_poses = sorted({h["pose"] for h in hits_forbidden})
    sums = lambda hs: sorted({round(h["q"].get("shoulder_pitch", 0) + h["q"].get("elbow_pitch", 0) + h["q"].get("wrist_pitch", 0), 1)
                              for h in hs})  # noqa: E731
    report = {"tolerance_mm3": TOL_MM3, "n_random_poses": N_RANDOM, "seed": SEED, "sweep_step_deg": SWEEP_STEP_DEG,
              "checks": n_checks, "worker_processes": jobs, "required_clearance_mm": CLEARANCE_MM,
              "coupled_limits": [{"name": c.name, "joints": list(c.joints), "lo_deg": c.lo, "hi_deg": c.hi} for c in p.arm.coupled_limits],
              "excluded_pairs": sorted(list(map(list, EXCLUDE))),
              "collisions_at_allowed_poses": hits_allowed,
              "forbidden_pose_collisions": {"poses_with_hits": len(forbidden_poses),
                                            "pitch_sum_range_deg": [sums(hits_forbidden)[0], sums(hits_forbidden)[-1]] if hits_forbidden else None,
                                            "pairs": sorted({f"{h['tool']}: {h['a']} <-> {h['b']}" for h in hits_forbidden})},
              "joint_limits_deg": {j.name: [j.lower_deg, j.upper_deg] for j in p.arm.joints}}
    if derive:
        every = hits_allowed + hits_forbidden
        report["derive"] = {}
        for c in p.arm.coupled_limits:
            sums_c = sorted(round(sum(h["q"].get(j, 0.0) for j in c.joints), 1) for h in every)
            report["derive"][c.name] = {"min_sum_at_hit": sums_c[0] if sums_c else None, "max_sum_at_hit": sums_c[-1] if sums_c else None}
        print("derive (extreme joint sums over all colliding poses):", report["derive"])
    (HERE / "out" / "clearance.json").write_text(json.dumps(report, indent=1))
    print(f"{n_checks['named_and_sweeps']} named/sweep + {n_checks['random']} random pose/tool combinations; "
          f"{sum(h['kind'] == 'collision' for h in hits_allowed)} collisions and "
          f"{sum(h['kind'] == 'clearance' for h in hits_allowed)} clearance < {CLEARANCE_MM} mm at allowed poses "
          f"({n_checks['boundary']} of them on the limit surfaces); {len(hits_forbidden)} (in {len(forbidden_poses)} poses) at "
          f"poses forbidden by the coupled limits {[(c.name, c.lo, c.hi) for c in p.arm.coupled_limits]}")
    return 1 if hits_allowed else 0


if __name__ == "__main__":
    sys.exit(main())
