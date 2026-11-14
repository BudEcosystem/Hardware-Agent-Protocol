#!/usr/bin/env python3
"""Where do the 100+ ms outliers of durable invokes come from? Sequential ``waitMs=1000`` invokes against the server as shipped (which
freezes its start-up heap since Task 12b), with the background WAL checkpointer effectively off (``--no-checkpoint``) and without the
start-up ``gc.freeze()`` (``--no-gc-freeze``, the SDK before Task 12b), same machine, same state directory
filesystem, several rounds each. Prints per round: samples, p50, p99, p99.9, max, how many invokes took more than 10 ms and the
sample indices of the first five, and what overlapped each slow invoke (bench/stalls.py): an fdatasync over 5 ms in the server,
a server event-loop stall, a client event-loop stall, or nothing seen.

``python bench/scripts/tail_experiment.py [--n 8000] [--rounds 3] [--state-root DIR]``
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import secrets
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "python" / "src"))

import stalls  # noqa: E402
from common import DEVICE_SERVER, spawn_server  # noqa: E402
from bhms.client.client import Client  # noqa: E402


async def one(root: Path | None, n: int, variant: str, samples_to: Path | None = None) -> str:
    tag = secrets.token_hex(3)
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        url = f"unix:{tmp}/t.sock"
        gc_log, stall_log = Path(tmp) / "gc.log", Path(tmp) / "stalls.jsonl"
        extra = {"as shipped": [], "checkpointer off": ["--no-checkpoint"], "no gc.freeze": ["--no-gc-freeze"]}[variant]
        extra += ["--gc-log", str(gc_log), "--stall-log", str(stall_log)]
        server = spawn_server(DEVICE_SERVER, ["--listen", url, "--durability", "dispatch", "--state-dir", tmp, *extra], url=url)
        watcher = asyncio.get_running_loop().create_task(stalls.watch_loop(stall_log, who="client"))
        slow_windows: list[tuple[float, float]] = []
        try:
            async with await Client.connect(url, timeout=60) as client:
                samples = []
                for i in range(n + 200):
                    wall, started = time.time(), time.perf_counter()
                    await client.actions_invoke("dev-1", "set_point", {"value": i}, operation_key=f"{tag}-{i}", wait_ms=1000)
                    took = (time.perf_counter() - started) * 1000
                    if i >= 200:
                        samples.append(took)
                        if took > 10:
                            slow_windows.append((wall, wall + took / 1000))
        finally:
            watcher.cancel()
            server.stop()
        gc_lines = gc_log.read_text().splitlines() if gc_log.exists() else []
        events = stalls.load(stall_log)
    causes = stalls.attribute(slow_windows, events)
    if samples_to is not None:
        with gzip.open(samples_to, "wt") as handle:
            json.dump({"unit": "ms", "order": "arrival", "variant": variant, "gc_pauses": gc_lines, "stalls": events,
                       "slow_windows": slow_windows, "attribution": causes, "samples": [round(x, 4) for x in samples]}, handle)
    ordered = sorted(samples)
    slow = [i for i, v in enumerate(samples) if v > 10]
    pick = lambda q: ordered[min(len(ordered) - 1, int(len(ordered) * q))]  # noqa: E731
    worst_fsync = max((e["ms"] for e in events if e["kind"] == "fsync"), default=0.0)
    worst_loop = {who: max((e["ms"] for e in events if e["kind"] == "loop" and e["who"] == who), default=0.0)
                  for who in ("server", "client")}
    return (f"{variant:16s} n={n} p50={pick(.5):.2f} p99={pick(.99):.2f} p99.9={pick(.999):.2f} "
            f"max={ordered[-1]:.1f} ms; >10 ms: {len(slow)} first at {slow[:5]}; overlapping: {causes}; "
            f"worst fdatasync {worst_fsync} ms, worst loop stall server {worst_loop['server']} / client {worst_loop['client']} ms; "
            f"GC pauses >5 ms: {len(gc_lines)} {gc_lines[:4]}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n", type=int, default=8000)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--samples-dir", type=Path, help="write the raw per-invoke latencies (gzip JSON) of every round and variant here")
    args = parser.parse_args()
    if args.samples_dir:
        args.samples_dir.mkdir(parents=True, exist_ok=True)
    for round_no in range(1, args.rounds + 1):
        for variant in ("as shipped", "checkpointer off", "no gc.freeze"):
            target = args.samples_dir / f"round{round_no}_{variant.replace(' ', '_')}.json.gz" if args.samples_dir else None
            print(await one(args.state_root, args.n, variant, target), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
