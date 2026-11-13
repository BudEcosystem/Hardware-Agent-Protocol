#!/usr/bin/env python3
"""Check every exported STL with trimesh: watertight, consistent winding,
a single body (unless the part is meant to be several), positive volume
that matches the B-rep volume, and file size under the commit limit.

    python cad/check_meshes.py        # writes cad/out/mesh_check.json, exit 1 on failure
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
MAX_STL_BYTES = 2 * 1024 * 1024
VOLUME_RTOL = 0.01  # tessellated vs exact B-rep volume


def main() -> int:
    parts = json.loads((OUT / "parts.json").read_text())
    results = {}
    failures = []
    totals = {"mass_model_g": 0.0, "print_time_h_est": 0.0}
    for name, info in sorted(parts.items()):
        path = OUT / f"{name}.stl"
        mesh = trimesh.load_mesh(path, process=True)
        bodies = trimesh.graph.connected_components(mesh.face_adjacency, min_len=1, nodes=np.arange(len(mesh.faces)))
        vol_brep = info["volume_cm3"] * 1000.0
        rel = abs(mesh.volume - vol_brep) / vol_brep
        size = path.stat().st_size
        r = {
            "watertight": bool(mesh.is_watertight),
            "winding_consistent": bool(mesh.is_winding_consistent),
            "is_volume": bool(mesh.is_volume),
            "bodies": len(bodies),
            "triangles": int(len(mesh.faces)),
            "volume_cm3_mesh": mesh.volume / 1000.0,
            "volume_rel_err": rel,
            "euler_number": int(mesh.euler_number),
            "stl_bytes": size,
            "mass_model_g": info["mass_model_g"],
            "qty": info["qty"],
            "material": info["material"],
            "print_time_h_est": info["print_time_h_est"],
        }
        problems = []
        if not r["watertight"]:
            problems.append("not watertight")
        if not r["winding_consistent"]:
            problems.append("inconsistent winding")
        if not r["is_volume"]:
            problems.append("not a volume")
        if r["bodies"] != info["solids"]:
            problems.append(f"{r['bodies']} mesh bodies vs {info['solids']} B-rep solids")
        if info["solids"] != 1:
            problems.append(f"{info['solids']} solids (expected 1)")
        if rel > VOLUME_RTOL:
            problems.append(f"volume differs from B-rep by {rel:.2%}")
        if size > MAX_STL_BYTES:
            problems.append(f"STL {size} bytes > 2 MiB")
        r["problems"] = problems
        if problems:
            failures.append((name, problems))
        results[name] = r
        if info["qty"] and info.get("printed", True):
            totals["mass_model_g"] += info["mass_model_g"] * info["qty"]
            totals["print_time_h_est"] += info["print_time_h_est"] * info["qty"]
        flag = "OK " if not problems else "FAIL"
        print(f"{flag} {name:22s} tri={r['triangles']:6d} V={r['volume_cm3_mesh']:8.2f} cm3 err={rel:.4%} "
              f"bytes={size:8d} {'; '.join(problems)}")
    summary = {"parts": len(results), "failures": len(failures), "totals": totals, "results": results,
               "tool": f"trimesh {trimesh.__version__}"}
    (OUT / "mesh_check.json").write_text(json.dumps(summary, indent=1))
    print(f"{len(results)} parts, {len(failures)} failures; all copies: {totals['mass_model_g']:.0f} g, "
          f"~{totals['print_time_h_est']:.1f} h printing (estimate)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
