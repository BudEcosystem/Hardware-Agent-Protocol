#!/usr/bin/env python3
"""Regenerate every BHMS Arm part and the derived data.

    python cad/build.py            # all parts -> cad/out/
    python cad/build.py --only turret --no-step

Outputs (cad/out/):
  <part>.stl, <part>.step   one file per printed part, in its own frame
  parts.json                volume, surface area, material, modelled mass
  assembly.json             link mass properties (SI) + mesh placements +
                            kinematic tree + tool TCPs  -> sim/gen_mjcf.py
  manifest.json             sha256 / size of every generated file

Mass model for printed parts (stated in docs/design.md): perimeters/top/
bottom are solid to a depth of ``Printer.shell``; the remaining volume is
filled at ``Printer.infill``:
    m = rho * (min(V, A*t) + infill * max(0, V - A*t))
The inertia of a part is its uniform-density inertia scaled to that mass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
from build123d import Location, Part, export_step, export_stl  # noqa: E402
from OCP.BRepGProp import BRepGProp  # noqa: E402
from OCP.GProp import GProp_GProps  # noqa: E402

from assembly import DENSITY, build_assembly, kinematic_tree, tool_info  # noqa: E402
from params import DEFAULT, Params  # noqa: E402

OUT = HERE / "out"
STL_TOL = 0.02  # mm chordal deviation
STL_ANG = 0.2  # rad


def volume_props(shape: Part) -> tuple[float, np.ndarray, np.ndarray]:
    """(volume mm^3, centroid mm, inertia about centroid for unit density mm^5)."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props)
    c = props.CentreOfMass()
    m = props.MatrixOfInertia()
    inertia = np.array([[m.Value(i, j) for j in range(1, 4)] for i in range(1, 4)])
    return props.Mass(), np.array([c.X(), c.Y(), c.Z()]), inertia


def surface_area(shape: Part) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape.wrapped, props)
    return props.Mass()


def printed_mass_g(volume: float, area: float, material: str, p: Params) -> float:
    shell = min(volume, area * p.printer.shell)
    core = max(0.0, volume - area * p.printer.shell)
    return DENSITY[material] * (shell + p.printer.infill * core) / 1000.0


def print_time_h(mass_g: float, material: str, height_mm: float, p: Params) -> float:
    extruded = mass_g / DENSITY[material] * 1000.0
    layers = height_mm / p.printer.layer
    return (extruded / p.printer.flow_mm3_s + layers * p.printer.layer_overhead_s) / 3600.0


def combine(pieces: list[tuple[float, np.ndarray, np.ndarray]]) -> tuple[float, np.ndarray, np.ndarray]:
    """Combine (mass, com, inertia-about-own-com) pieces (any consistent units)."""
    total = sum(m for m, _, _ in pieces)
    com = sum(m * c for m, c, _ in pieces) / total
    inertia = np.zeros((3, 3))
    for m, c, i in pieces:
        d = c - com
        inertia += i + m * (np.dot(d, d) * np.eye(3) - np.outer(d, d))
    return total, com, inertia


def loc_pose(loc: Location) -> tuple[list[float], list[float]]:
    trsf = loc.wrapped.Transformation()
    t = trsf.TranslationPart()
    q = trsf.GetRotation()
    return [t.X() / 1000.0, t.Y() / 1000.0, t.Z() / 1000.0], [q.W(), q.X(), q.Y(), q.Z()]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="build only these parts (no assembly.json)")
    ap.add_argument("--no-step", action="store_true", help="skip STEP export")
    args = ap.parse_args()

    p = DEFAULT
    OUT.mkdir(exist_ok=True)
    asm = build_assembly(p)
    selected = [d for d in asm.parts if not args.only or d.name in args.only]
    parts_info: dict[str, dict] = {}
    solids: dict[str, Part] = {}
    t_all = time.time()
    for d in selected:
        t0 = time.time()
        solid = d.build(p)
        if not solid.is_valid:
            raise SystemExit(f"{d.name}: invalid solid")
        n_solids = len(solid.solids())
        solids[d.name] = solid
        vol, com, _ = volume_props(solid)
        area = surface_area(solid)
        mass = printed_mass_g(vol, area, d.material, p) if d.printed else 0.0
        bb = solid.bounding_box()
        # Print height along the recommended orientation is not modelled;
        # use the smallest bounding-box extent as an optimistic layer count.
        height = min(bb.size.X, bb.size.Y, bb.size.Z)
        export_stl(solid, str(OUT / f"{d.name}.stl"), tolerance=STL_TOL, angular_tolerance=STL_ANG)
        if not args.no_step:
            export_step(solid, str(OUT / f"{d.name}.step"))
        parts_info[d.name] = {
            "material": d.material,
            "qty": d.qty,
            "solids": n_solids,
            "volume_cm3": vol / 1000.0,
            "area_cm2": area / 100.0,
            "mass_model_g": mass,
            "printed": d.printed,
            "solid_equivalent_g": DENSITY[d.material] * vol / 1000.0 if d.printed else 0.0,
            "bbox_mm": [bb.size.X, bb.size.Y, bb.size.Z],
            "print_time_h_est": print_time_h(mass, d.material, height, p) if d.printed else 0.0,
            "orientation": d.orientation,
            "centroid_mm": com.tolist(),
        }
        print(f"{d.name:22s} {vol / 1000:8.2f} cm3 {mass:7.1f} g  solids={n_solids}  {time.time() - t0:5.1f} s", flush=True)

    if not args.only:
        links: dict[str, dict] = {}
        pieces: dict[str, list] = {}
        for d in asm.parts:
            info = parts_info[d.name]
            vol, _, _ = volume_props(solids[d.name])
            scale = info["mass_model_g"] / vol  # g per mm^3 (effective)
            for link, loc in d.instances:
                if link == "none" or not d.in_sim:
                    continue
                if d.printed:  # purchased envelopes carry their mass as hardware
                    v, c, i = volume_props(loc * solids[d.name])
                    pieces.setdefault(link, []).append((scale * v, c, scale * i))
                pos, quat = loc_pose(loc)
                links.setdefault(link, {"meshes": [], "hardware": []})["meshes"].append(
                    {"mesh": d.name, "pos": pos, "quat": quat, "material": d.material})
        for hw in asm.hardware:
            v, c, i = volume_props(hw.solid)
            pieces.setdefault(hw.link, []).append((hw.mass_g, c, hw.mass_g / v * i))
            links.setdefault(hw.link, {"meshes": [], "hardware": []})["hardware"].append(
                {"name": hw.name, "mass_g": hw.mass_g, "note": hw.note})
        for link, pcs in pieces.items():
            m_g, com_mm, i_gmm2 = combine(pcs)
            links[link]["mass_kg"] = m_g / 1000.0
            links[link]["com_m"] = (com_mm / 1000.0).tolist()
            inertia = i_gmm2 * 1e-9  # g mm^2 -> kg m^2
            links[link]["inertia_kgm2"] = inertia.tolist()
            links[link]["fullinertia"] = [inertia[0, 0], inertia[1, 1], inertia[2, 2], inertia[0, 1], inertia[0, 2],
                                          inertia[1, 2]]
        assembly = {
            "units": "SI (m, kg, kg m^2); meshes are mm STL in their part frame",
            "links": links,
            "tree": kinematic_tree(p),
            "tools": tool_info(p),
            "servo": asdict(p.servo),
            "gear": {**asdict(p.gear), "ratio": p.gear.ratio, "center_distance": p.gear.center_distance},
            "arm": {k: v for k, v in asdict(p.arm).items() if k != "joints"},
            "payload": {"mass_g": p.arm.payload_g, "offset_mm": p.arm.payload_offset},
        }
        (OUT / "assembly.json").write_text(json.dumps(assembly, indent=1))
        (OUT / "parts.json").write_text(json.dumps(parts_info, indent=1))
        manifest = {}
        for f in sorted(OUT.iterdir()):
            if f.suffix in {".stl", ".step", ".json"} and f.name != "manifest.json":
                manifest[f.name] = {"sha256": sha256(f), "bytes": f.stat().st_size}
        (OUT / "manifest.json").write_text(json.dumps(
            {"regenerate": "python hardware/actuator/cad/build.py (build123d 0.13, OCP 8.0.1)",
             "note": "STEP files embed a timestamp, so their hashes change on every run",
             "files": manifest}, indent=1))
    print(f"total {time.time() - t_all:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
