"""Measure SimLab's speed: physics throughput, scripted runs over many seeds, BHMS runs, realtime pacing.

``python -m simlab.runs.benchmark --out DIR [--seeds 100] [--skip-realtime]`` writes ``DIR/benchmark.json``. The numbers are
*realtime factors*: simulated seconds per wall second (above 1 is faster than real time). Nothing here asserts a value; the
V1 gate of the validation plan is "all V1 tests run in under five minutes", and this records how far inside that we are.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from simlab.agents.scripted import ScriptedLoadAndImage
from simlab.runs import multidevice
from simlab.scene import BENCH
from simlab.twins.arm import ArmTwin
from simlab.twins.microscope import MicroscopeTwin
from simlab.world import World


def physics(seconds: float = 120.0) -> dict[str, Any]:
    """The bench with the arm model, holding still: raw MuJoCo throughput through ``World.step``."""
    world = World(BENCH, seed=1)
    started = time.perf_counter()
    world.step(seconds)
    wall = time.perf_counter() - started
    return {"sim_s": seconds, "wall_s": round(wall, 3), "realtime_factor": round(seconds / wall, 1),
            "steps_per_s": round(seconds / world.dt / wall)}


def scripted_seeds(count: int) -> dict[str, Any]:
    """UC4 over ``count`` seeds through the twins' direct interfaces: success rate and time (plan Task 8 step 5)."""
    ok, sim, started = 0, 0.0, time.perf_counter()
    digests: dict[int, str] = {}
    for seed in range(count):
        world = World(BENCH, seed=seed)
        world.ledger.add_container("slide", "slide", {}, "slide_rack", meta={"specimen_z_um": 35.0 + seed % 30})
        report = ScriptedLoadAndImage(ArmTwin(world), MicroscopeTwin(world)).run()
        ok += report.status == "ok"
        sim += world.time_s
        digests[seed] = world.digest()
    wall = time.perf_counter() - started
    repeat = World(BENCH, seed=0)
    repeat.ledger.add_container("slide", "slide", {}, "slide_rack", meta={"specimen_z_um": 35.0})
    ScriptedLoadAndImage(ArmTwin(repeat), MicroscopeTwin(repeat)).run()
    return {"seeds": count, "success_rate": ok / count, "wall_s": round(wall, 2), "sim_s": round(sim, 1),
            "realtime_factor": round(sim / wall, 1), "wall_per_run_s": round(wall / count, 3),
            "same_seed_same_digest": repeat.digest() == digests[0], "distinct_digests": len(set(digests.values()))}


def bhms(out: Path, scenario: str, mode: str, durability: str) -> dict[str, Any]:
    result = asyncio.run(multidevice.SCENARIOS[scenario](out / f"{scenario}-{mode}-{durability}", 1, mode=mode,
                                                         durability=durability))
    return {"scenario": scenario, "mode": mode, "durability": durability, "status": result.status,
            "operations": len(result.operations), "verdicts": result.verdict_counts, "sim_s": result.sim_s,
            "wall_s": result.wall_s, "realtime_factor": round(result.realtime_factor, 2)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simlab.runs.benchmark", description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--skip-realtime", action="store_true")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"physics": physics(), "scripted_uc4_direct": scripted_seeds(args.seeds), "bhms": []}
    for scenario in ("uc4", "assay"):
        for durability in ("process", "dispatch"):
            report["bhms"].append(bhms(args.out, scenario, "stepped", durability))
    if not args.skip_realtime:
        report["bhms"].append(bhms(args.out, "uc4", "realtime", "process"))
    (args.out / "benchmark.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
