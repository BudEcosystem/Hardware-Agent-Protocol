#!/usr/bin/env python3
"""BHMS benchmark harness: one command, ``--quick`` or ``--full``, JSON results, budget verdicts.

    python bench/run.py --quick                       # smoke sizes (about 2 minutes)
    python bench/run.py --full --label amd            # the committed measurement run
    python bench/run.py --full --only invoke,fsync    # a subset

Results go to ``bench/results/<date>-<host>[-label]/``: ``environment.json``, one ``<scenario>.json`` per scenario (the
scenario's result plus its wall time and the load average around it), ``budgets.json`` and ``summary.json``. A scenario that
raises is recorded with its traceback and the run continues; its budgets then show "not measured", which counts as a failure.

Run it pinned and niced on a shared machine: ``nice -n 10 taskset -c 0-7 python bench/run.py --full`` (``--cpus 0-7`` pins this
process and so every child it spawns). Needs ``bhms`` installed with the ``http`` and ``mcp`` extras; ``--node`` (or ``node`` on
PATH) enables the TypeScript comparison.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import shutil
import socket
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "python" / "src"))  # always the checked-out SDK

import budgets  # noqa: E402
from common import Context, dump, environment  # noqa: E402

ORDER = ["fsync", "transports", "invoke", "concurrency", "gateway", "gateway_http", "subscription", "recovery", "compact",
         "mcp_compare", "ts_vs_py"]


def parse_cpus(spec: str) -> set[int]:
    cpus: set[int] = set()
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        cpus.update(range(int(lo), int(hi or lo) + 1))
    return cpus


def verdict_table(records: list[dict]) -> str:
    return "\n".join(f"{'PASS' if r['pass'] else 'FAIL'}  {r['budget']}: {r['measured']} (limit {r['limit']})"
                     + (f"  [{r['detail']}]" if r['detail'] else "") for r in records)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true", help="small sample sizes (default)")
    mode.add_argument("--full", action="store_true", help="the committed sizes")
    parser.add_argument("--only", help="comma-separated scenario names")
    parser.add_argument("--skip", default="", help="comma-separated scenario names")
    parser.add_argument("--label", default="", help="suffix of the results directory")
    parser.add_argument("--out", type=Path, help="results directory (default bench/results/<date>-<host>[-label])")
    parser.add_argument("--state-root", type=Path, default=None,
                        help="where durable state is written; this decides the fsync cost (default: $BENCH_DIR or ~/.cache/bhms-bench)")
    parser.add_argument("--cpus", help="pin this process (and its children) to these CPUs, e.g. 0-7")
    parser.add_argument("--node", default=shutil.which("node"), help="node binary for the TypeScript comparison")
    parser.add_argument("--simavr-json", help="compact.py JSON produced in the AVR container, folded into the compact scenario")
    args = parser.parse_args()
    if args.cpus:
        os.sched_setaffinity(0, parse_cpus(args.cpus))
    quick = not args.full
    state_root = args.state_root or Path(os.environ.get("BENCH_DIR") or Path.home() / ".cache" / "bhms-bench")
    state_root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d")
    out_dir = args.out or Path(__file__).resolve().parent / "results" / (f"{stamp}-{socket.gethostname()}" + (f"-{args.label}" if args.label else ""))
    out_dir.mkdir(parents=True, exist_ok=True)
    only = [s for s in (args.only.split(",") if args.only else ORDER) if s not in args.skip.split(",")]
    env = environment(state_root)
    env["mode"] = "quick" if quick else "full"
    env["node_binary"] = args.node
    dump(out_dir / "environment.json", env)
    print(f"environment: {env['cpu']}, {env['cpus_online']} CPUs, affinity {len(env['affinity'])}, python {env['python']}, "
          f"node {env['node']}, fs {env['state_dir_fs']}, load {env['load']['load1']:.2f}", flush=True)
    results: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(dir=state_root) as scratch:
        ctx = Context(quick=quick, state_root=Path(scratch), out_dir=out_dir, node=args.node, simavr_cmd=args.simavr_json)
        for name in only:
            module = importlib.import_module(f"scenarios.{name}")
            started = time.perf_counter()
            load_before = os.getloadavg()
            print(f"== {name} ...", flush=True)
            try:
                result = await module.run(ctx)
                entry: dict = {"result": result}
            except Exception:  # noqa: BLE001 - recorded, the run continues
                entry = {"error": traceback.format_exc()}
                print(entry["error"], file=sys.stderr, flush=True)
            entry["seconds"] = round(time.perf_counter() - started, 1)
            entry["load_around"] = {"before": load_before, "after": os.getloadavg()}
            results[name] = entry
            dump(out_dir / f"{name}.json", entry)
            print(f"   {name}: {'ERROR' if 'error' in entry else 'ok'} in {entry['seconds']} s, load {load_before[0]:.1f} -> {os.getloadavg()[0]:.1f}",
                  flush=True)
    records = budgets.evaluate(results, ctx.extra.get("fsync_p50_ms"), ctx.extra.get("fsync_p99_ms"))
    dump(out_dir / "budgets.json", records)
    dump(out_dir / "summary.json", {"environment": env, "scenarios": {k: {"seconds": v["seconds"], "error": v.get("error")} for k, v in results.items()},
                                    "budgets_passed": sum(r["pass"] for r in records), "budgets_total": len(records)})
    print("\n" + verdict_table(records))
    print(f"\nresults: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
