"""Host durability floor: ``fdatasync``/``fsync`` latency on the state directory's filesystem, plus the raw SQLite WAL commit.

The durable-invoke budget is defined relative to this number (p50 <= fsync + 1 ms, p99 <= 5x), so it is measured first and
every later scenario reads it from ``ctx.extra["fsync_p50_ms"]``. The SQLite commit baseline is Task 4's
``commit_latency`` (``sdk/python/benchmarks/invoke_roundtrip.py``).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from common import Context, fsync_samples, load_sdk_benchmark, stats_ms, timed

NAME = "fsync"


async def run(ctx: Context) -> dict:
    n = ctx.n(300, 3000)
    out: dict = {"state_root": str(ctx.state_root)}
    with timed(out):
        for sync in ("fdatasync", "fsync"):
            for size in (600, 4096):
                samples = fsync_samples(ctx.state_root, n, size=size, sync=sync)
                out[f"{sync}_{size}B"] = stats_ms(samples, sum(samples) / 1000, label=f"fsync__{sync}_{size}B")
        invoke_roundtrip = load_sdk_benchmark("invoke_roundtrip")
        out["sqlite_wal_commit"] = {}
        with tempfile.TemporaryDirectory(dir=ctx.state_root) as tmp:
            for sync in ("NORMAL", "FULL"):
                p50, p99 = invoke_roundtrip.commit_latency(Path(tmp) / f"{sync}.db", sync, n=ctx.n(300, 1000))
                out["sqlite_wal_commit"][sync] = {"p50_ms": round(p50, 4), "p99_ms": round(p99, 4)}
    ctx.extra["fsync_p50_ms"] = out["fdatasync_600B"]["p50_ms"]
    ctx.extra["fsync_p99_ms"] = out["fdatasync_600B"]["p99_ms"]
    out["reference"] = {"fsync_p50_ms": ctx.extra["fsync_p50_ms"], "fsync_p99_ms": ctx.extra["fsync_p99_ms"]}
    return out
