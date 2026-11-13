#!/usr/bin/env python3
"""Where do the 100+ ms outliers of durable invokes come from? Sequential ``waitMs=1000`` invokes against the server as shipped, with
the background WAL checkpointer effectively off (``--no-checkpoint``) and with ``gc.freeze()`` after start-up, same machine, same state directory
filesystem, several rounds each. Prints per round: samples, p50, p99, p99.9, max, how many invokes took more than 10 ms and the
sample indices of the first five.

``python bench/scripts/tail_experiment.py [--n 8000] [--rounds 3] [--state-root DIR]``
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "python" / "src"))

from common import DEVICE_SERVER, spawn_server  # noqa: E402
from bhms.client.client import Client  # noqa: E402


async def one(root: Path | None, n: int, variant: str) -> str:
    tag = secrets.token_hex(3)
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        url = f"unix:{tmp}/t.sock"
        gc_log = Path(tmp) / "gc.log"
        extra = {"as shipped": [], "checkpointer off": ["--no-checkpoint"], "gc.freeze": ["--gc-freeze"]}[variant] + ["--gc-log", str(gc_log)]
        server = spawn_server(DEVICE_SERVER, ["--listen", url, "--durability", "dispatch", "--state-dir", tmp, *extra], url=url)
        try:
            async with await Client.connect(url, timeout=60) as client:
                samples = []
                for i in range(n + 200):
                    started = time.perf_counter()
                    await client.actions_invoke("dev-1", "set_point", {"value": i}, operation_key=f"{tag}-{i}", wait_ms=1000)
                    if i >= 200:
                        samples.append((time.perf_counter() - started) * 1000)
        finally:
            server.stop()
        gc_lines = gc_log.read_text().splitlines() if gc_log.exists() else []
    ordered = sorted(samples)
    slow = [i for i, v in enumerate(samples) if v > 10]
    pick = lambda q: ordered[min(len(ordered) - 1, int(len(ordered) * q))]  # noqa: E731
    return (f"{variant:16s} n={n} p50={pick(.5):.2f} p99={pick(.99):.2f} p99.9={pick(.999):.2f} "
            f"max={ordered[-1]:.1f} ms; >10 ms: {len(slow)} first at {slow[:5]}; "
            f"GC pauses >5 ms: {len(gc_lines)} {gc_lines[:4]}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n", type=int, default=8000)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--state-root", type=Path)
    args = parser.parse_args()
    for _ in range(args.rounds):
        for variant in ("as shipped", "checkpointer off", "gc.freeze"):
            print(await one(args.state_root, args.n, variant), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
