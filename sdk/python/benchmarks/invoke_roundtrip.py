"""``actions/invoke`` round trip through a real DeviceServer process over a Unix socket with a durable SQLite journal.

Run: ``python3 sdk/python/benchmarks/invoke_roundtrip.py [--n 2000] [--clients 16] [--modes dispatch,full,process]
[--json out.json] [--profile]``. For each durability mode (see ``bhms.runtime.store``) the server runs in its own process (so client and
server do not share an event loop) and the client sends sequential keyed invokes of an action whose handler returns at
once:

* ``waitMs=0``  — the response returns after admission and the dispatch record (the intent) is durable;
* ``waitMs=1000`` — the response returns after the completion is recorded (full operation round trip).

Each case runs sequentially (one client, ``--n`` invokes after a warm-up) and concurrently (``--clients`` connections,
each issuing ``--n`` / clients invokes at once; only for ``waitMs=1000``, since unawaited invokes from many
clients would fill the device's bounded operation queue by design). ``dispatch`` is WAL ``synchronous=NORMAL`` with an fsync barrier on the
intent; ``full`` is ``synchronous=FULL`` everywhere.

It prints p50/p99 latency per case, plus the store's raw commit latency so the fsync cost is visible.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from bhms.client.client import Client

SERVER = """
import asyncio, sys
from bhms import DeviceServer, Range
srv = DeviceServer("bench", state_dir=sys.argv[1], durability=sys.argv[3])
dev = srv.device("dev-1", resources=["dev-1"])
dev.report_alive()

@dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
async def set_point(ctx, value: Range(0, 1e9, unit="1")) -> None:
    return None

async def main():
    await srv.listen("unix:" + sys.argv[2])
    print("ready", flush=True)
    await asyncio.Event().wait()

if "--profile" in sys.argv:
    import cProfile, pstats, signal
    profiler = cProfile.Profile()
    def dump(*_):
        profiler.disable()
        pstats.Stats(profiler).sort_stats("cumulative").print_stats(25)
        sys.exit(0)
    signal.signal(signal.SIGTERM, dump)
    profiler.enable()
asyncio.run(main())
"""


def percentile(samples: list[float], q: float) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


async def invoke_loop(client: Client, wait: int, tag: str, n: int) -> list[float]:
    samples = []
    for i in range(n):
        start = time.perf_counter()
        res = await client.actions_invoke("dev-1", "set_point", {"value": i}, operation_key=f"k{wait}-{tag}-{i}",
                                          wait_ms=wait)
        samples.append((time.perf_counter() - start) * 1000)
        if wait and res.operation.state != "completed":
            raise RuntimeError(f"operation ended {res.operation.state}")
    return samples


def summary(samples: list[float]) -> dict[str, float]:
    return {"n": len(samples), "p50_ms": statistics.median(samples), "p99_ms": percentile(samples, 0.99),
            "max_ms": max(samples)}


async def run_mode(mode: str, n: int, clients: int, profile: bool) -> dict[str, dict[str, float]]:
    with tempfile.TemporaryDirectory(dir=os.environ.get("BENCH_DIR")) as tmp:
        sock = f"{tmp}/bench.sock"
        args = [sys.executable, "-c", SERVER, tmp, sock, mode] + (["--profile"] if profile else [])
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, text=True)
        assert proc.stdout is not None and proc.stdout.readline().strip() == "ready"
        out: dict[str, dict[str, float]] = {}
        try:
            async with await Client.connect(f"unix:{sock}") as client:
                for wait in (0, 1000):
                    for i in range(200):  # warm-up
                        await client.actions_invoke("dev-1", "set_point", {"value": i}, operation_key=f"w{wait}-{i}",
                                                    wait_ms=wait)
                    out[f"waitMs={wait} sequential"] = summary(await invoke_loop(client, wait, "s", n))
                    if not wait:  # fire-and-forget from 16 clients would just fill the device's bounded queue
                        continue
                    conns = [await Client.connect(f"unix:{sock}") for _ in range(clients)]
                    try:
                        per_client = max(1, n // clients)
                        started = time.perf_counter()
                        runs = await asyncio.gather(*(invoke_loop(c, wait, f"c{j}", per_client)
                                                      for j, c in enumerate(conns)))
                        elapsed = time.perf_counter() - started
                    finally:
                        for c in conns:
                            await c.close()
                    result = summary([x for run in runs for x in run])
                    result["throughput_per_s"] = per_client * clients / elapsed
                    out[f"waitMs={wait} {clients} clients"] = result
        finally:
            proc.terminate()
            stats, _ = proc.communicate(timeout=30)
            if profile:
                print(stats)
        return out


def commit_latency(path: Path, sync: str, n: int = 300) -> tuple[float, float]:
    db = sqlite3.connect(path, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(f"PRAGMA synchronous={sync}")
    db.execute("CREATE TABLE IF NOT EXISTS t(v BLOB)")
    samples = []
    for _ in range(n):
        start = time.perf_counter()
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO t VALUES(?)", (b"x" * 600,))
        db.execute("COMMIT")
        samples.append((time.perf_counter() - start) * 1000)
    db.close()
    return statistics.median(samples), percentile(samples, 0.99)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--clients", type=int, default=16)
    parser.add_argument("--modes", default="dispatch,full,process")
    parser.add_argument("--json", metavar="PATH", help="write the results as JSON")
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    report: dict[str, dict] = {"raw_commit": {}, "invoke": {}}
    with tempfile.TemporaryDirectory(dir=os.environ.get("BENCH_DIR")) as tmp:
        for sync in ("NORMAL", "FULL"):
            p50, p99 = commit_latency(Path(tmp) / f"{sync}.db", sync)
            report["raw_commit"][sync] = {"p50_ms": p50, "p99_ms": p99}
            print(f"raw SQLite WAL commit, synchronous={sync:6s}: p50 {p50:6.3f} ms  p99 {p99:6.3f} ms")
    for mode in args.modes.split(","):
        results = await run_mode(mode, args.n, args.clients, args.profile)
        report["invoke"][mode] = results
        for case, r in results.items():
            print(f"invoke durability={mode:8s} {case:22s}: p50 {r['p50_ms']:6.3f} ms  p99 {r['p99_ms']:6.3f} ms  "
                  f"(n={int(r['n'])})")
    if args.json:
        Path(args.json).write_text(json.dumps({"n": args.n, "clients": args.clients, **report}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
