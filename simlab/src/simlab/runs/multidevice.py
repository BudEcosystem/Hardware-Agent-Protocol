"""Scripted multi-device runs through BHMS, judged operation by operation by the oracle.

Two scenarios, both driven only through BHMS clients (``actions/invoke``, ``properties/read``) against real device servers
sharing one world:

* ``uc4`` (the brief's acceptance run): the arm loads a slide onto the microscope stage, the microscope autofocuses, images
  are recorded, the arm returns the slide. Cross-device consequence: the microscope images whatever the arm actually put on
  the stage.
* ``assay``: the arm carries a microplate to the liquid handler, the handler dispenses a dye into wells, the arm carries the
  plate to the reader, the reader measures absorbance, the arm carries the plate to the balance and the balance weighs it.
  Cross-device consequences: under-dispensing lowers the absorbance and the mass; a dropped plate is simply not there.

``python -m simlab.runs.multidevice --scenario uc4 --seed 1 --out DIR`` runs one and writes ``DIR/<scenario>.json`` with
every operation, its claim and the oracle's verdict, the agent's own result, wall and simulated times and the world digest.
Exit status 0 only when every verdict is CONSISTENT and the agent's result is ``ok``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from simlab.agents.scripted import BhmsArm, BhmsScope, Recorder, StepFailed, load_and_image
from simlab.lab import Lab
from simlab.oracle import Verdict
from simlab.runs.judge import Judged, judge_operations
from simlab.twins.plate_reader import BLANK_A, WELL_AREA_CM2, extinction

DYE_MM = 2.0  # the reservoir's dye concentration (see LiquidHandlerTwin)


@dataclass
class RunResult:
    scenario: str
    seed: int
    mode: str
    status: str
    detail: str
    wall_s: float
    sim_s: float
    operations: list[dict[str, Any]] = field(default_factory=list)
    verdict_counts: dict[str, int] = field(default_factory=dict)
    digest: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def realtime_factor(self) -> float:
        return self.sim_s / self.wall_s if self.wall_s > 0 else float("inf")

    @property
    def all_consistent(self) -> bool:
        return self.status == "ok" and set(self.verdict_counts) <= {Verdict.CONSISTENT.value}


def summarize(lab: Lab, scenario: str, seed: int, mode: str, status: str, detail: str, wall_s: float,
              recorders: list[Recorder], extra: dict[str, Any] | None = None) -> RunResult:
    """Judge every operation the recorders saw and build the run record."""
    lab.attribute_bridged()
    operations = sorted((op for r in recorders for op in r.operations), key=lambda op: op.created_at)
    judged: list[Judged] = judge_operations(lab.oracle, operations)
    counts: dict[str, int] = {}
    for item in judged:
        counts[item.verdict.value] = counts.get(item.verdict.value, 0) + 1
    return RunResult(scenario, seed, mode, status, detail, round(wall_s, 3), round(lab.world.time_s, 3),
                     [{**asdict(item), "verdict": item.verdict.value} for item in judged], counts,
                     lab.world.digest(anonymize_causes=True),
                     extra or {})


async def run_uc4(run_dir: Path, seed: int = 1, *, mode: str = "stepped", durability: str = "process",
                  specimen_z_um: float = 48.0) -> RunResult:
    """The arm loads a slide, the microscope autofocuses, images are recorded, the slide goes back."""
    started = time.perf_counter()
    async with await Lab.start(run_dir, seed=seed, mode=mode, devices=("arm", "microscope"), durability=durability) as lab:
        lab.world.ledger.add_container("slide", "slide", {}, "slide_rack", meta={"specimen_z_um": specimen_z_um})
        arm, scope = BhmsArm(lab.client("arm"), "arm-1"), BhmsScope(lab.client("microscope"), "microscope-1")
        report = await load_and_image(arm, scope)
        frames = [lab.twins["microscope"].frames.get(f) for f in report.frames]
        extra = {"frames": report.frames, "focus_um": report.focus.z_um if report.focus else None,
                 "specimen_plane_um": specimen_z_um, "steps": report.steps,
                 "frame_z_um": [f.z_um for f in frames], "slide_location": lab.world.ledger.location("slide"),
                 "frame_files": sorted(p.name for p in (run_dir / "frames").glob("*.npy"))}
        status = report.status
        if status == "ok" and not (lab.world.ledger.location("slide") == "slide_rack" and frames
                                   and all(f.specimen_present and abs(f.z_um - specimen_z_um) <= 2.0 for f in frames)):
            status = "world_disagrees"  # the agent says ok, the world says otherwise: the oracle's run-level check
        return summarize(lab, "uc4", seed, mode, status, report.detail, time.perf_counter() - started, [arm, scope], extra)


async def run_assay(run_dir: Path, seed: int = 1, *, mode: str = "stepped", durability: str = "process",
                    wells: tuple[tuple[str, float], ...] = (("A1", 100.0), ("A2", 50.0)),
                    prepare: Callable[[Lab], None] | None = None) -> RunResult:
    """Plate to the handler, dispense a dye, plate to the reader, read absorbance, plate to the balance, weigh.

    ``prepare(lab)`` may change the world before the agent starts (a test arranges a nearly dry reservoir with it)."""
    started = time.perf_counter()
    devices = ("arm", "liquid_handler", "plate_reader", "balance")
    async with await Lab.start(run_dir, seed=seed, mode=mode, devices=devices, durability=durability) as lab:
        if prepare is not None:
            prepare(lab)
        arm = BhmsArm(lab.client("arm"), "arm-1")
        lh = Recorder(lab.client("liquid_handler"), "lh-1")
        reader = Recorder(lab.client("plate_reader"), "reader-1")
        balance = Recorder(lab.client("balance"), "balance-1")
        status, detail, extra = "ok", "", {}

        async def carry(source: str, target: str) -> None:
            await arm.move(source)
            if not await arm.close_gripper():
                raise StepFailed("grasp", f"nothing in the jaw at {source}")
            await arm.move(target)
            width = await arm.width_mm()
            if width is not None and width < 2.0:
                raise StepFailed("carry", f"the plate was lost on the way to {target}")
            await arm.open_gripper()

        try:
            await carry("hotel", "lh_deck")
            await lh.invoke("pick_up_tip")
            for well, volume in wells:
                await lh.invoke("aspirate", {"position": "reservoir", "well": "A1", "volume": volume})
                await lh.invoke("dispense", {"position": "deck", "well": well, "volume": volume})
            await lh.invoke("eject_tip")
            await carry("lh_deck", "reader")
            names = [w for w, _ in wells] + ["A3"]
            read = (await reader.invoke("read_absorbance", {"wavelength": 560, "wells": names})).result
            await carry("reader", "balance")
            mass = (await balance.invoke("weigh", {"samples": 10})).result["mass_g"]
            # the agent's own analysis: concentration from absorbance and the volumes it dispensed
            eps = extinction("dye", 560.0)
            estimated = {}
            for (well, volume), absorbance in zip(wells, read["absorbance"], strict=False):
                path = volume * 1e-3 / WELL_AREA_CM2
                estimated[well] = round((absorbance - BLANK_A) / (eps * path), 3)
            expected_mass = 40.0 + sum(v for _, v in wells) * 1e-3
            extra = {"absorbance": dict(zip(names, read["absorbance"], strict=True)), "estimated_dye_mM": estimated,
                     "mass_g": mass, "expected_mass_g": expected_mass}
            if any(abs(c - DYE_MM) > 0.1 * DYE_MM for c in estimated.values()) or abs(mass - expected_mass) > 0.02:
                status, detail = "assay_out_of_range", "absorbance or mass disagrees with what was dispensed"
        except StepFailed as exc:
            status, detail = "step_failed", str(exc)
        return summarize(lab, "assay", seed, mode, status, detail, time.perf_counter() - started,
                         [arm, lh, reader, balance], extra)


SCENARIOS = {"uc4": run_uc4, "assay": run_assay}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simlab.runs.multidevice", description=__doc__.split("\n\n")[0])
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="uc4")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--mode", choices=("stepped", "realtime"), default="stepped")
    parser.add_argument("--durability", choices=("process", "dispatch", "full"), default="process")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(SCENARIOS[args.scenario](args.out / "run", args.seed, mode=args.mode,
                                                  durability=args.durability))
    record = {**asdict(result), "realtime_factor": round(result.realtime_factor, 2),
              "all_consistent": result.all_consistent}
    (args.out / f"{args.scenario}.json").write_text(json.dumps(record, indent=2, default=str))
    print(f"{args.scenario} seed={args.seed} mode={args.mode}: {result.status}; {len(result.operations)} operations, "
          f"verdicts {result.verdict_counts}; sim {result.sim_s} s in {result.wall_s} s wall "
          f"(x{result.realtime_factor:.1f}); digest {result.digest}")
    return 0 if result.all_consistent else 1


if __name__ == "__main__":
    sys.exit(main())
