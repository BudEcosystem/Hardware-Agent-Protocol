"""Gateway scale, event fan-in and per-invoke overhead: Task 5's ``gateway_scale.py`` run as-is (imported, not copied).

* ``scale``: 1,000 light upstreams x 10 devices = 10,000 devices; start-up time, RSS, ``devices/list`` paging at limit 100 and
  500 over every page (the 50 ms budget is the per-page latency of a full page).
* ``fanin``: ``subscriptions/listen`` for events with no device filter while every upstream emits at once (events per second
  through the gateway, per-event latency).
* ``overhead``: ``actions/invoke`` straight to a device server versus through the gateway (journal modes process and dispatch).

All of it runs on one event loop with in-process upstreams (a measurement of the gateway's own CPU cost, not of 1,000 real
network peers); the report says so. ``--quick`` uses 100 upstreams.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from common import Context, load_sdk_benchmark, timed

NAME = "gateway"


async def run(ctx: Context) -> dict:
    mod = load_sdk_benchmark("gateway_scale")
    args = argparse.Namespace(upstreams=ctx.n(100, 1000), devices_per=10, events=5, n=ctx.n(200, 1000))
    out: dict = {"upstreams": args.upstreams}
    with tempfile.TemporaryDirectory(dir=ctx.state_root) as tmp:
        for name in ("scale", "fanin", "overhead"):
            row: dict = {}
            with timed(row):
                result = await getattr(mod, name)(args, Path(tmp))
            out[name] = {**result, "load": row["load"]}
    return out
