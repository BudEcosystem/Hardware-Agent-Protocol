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
from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig
from bhms.testing.gateway_fleet import build_light_fleet

NAME = "gateway"


async def listing(upstreams: int, devices_per: int, tmp: Path) -> dict:
    """B3 evidence: page the whole catalog and compare it with the expected ids, in code-point order (BHMS-LIF-062)."""
    fleet = await build_light_fleet(upstreams, devices_per=devices_per)
    expected = sorted(f"u{i}/d{j}" for i in range(upstreams) for j in range(devices_per))
    gateway = Gateway(GatewayConfig(id="bench-list", state_dir=tmp / "gw-list", upstreams=fleet.upstream_configs(), principals={},
                                    connect_wait_ms=600_000), memory=True)
    await gateway.start()
    await gateway.wait_validated(600)
    await gateway.listen(f"unix:{tmp}/gw-list.sock")
    client = await Client.connect(f"unix:{tmp}/gw-list.sock", timeout=60)
    seen: list[str] = []
    cursor = None
    try:
        while True:
            page = await client.devices_list(limit=500, cursor=cursor)
            seen.extend(d.device_id for d in page.devices)
            cursor = page.next_cursor
            if cursor is None:
                break
    finally:
        await client.close()
        await gateway.close()
        await fleet.close()
    return {"expected": len(expected), "listed": len(seen), "unique": len(set(seen)) == len(seen), "ordered": seen == sorted(seen),
            "equals_expected_in_order": seen == expected}


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
        out["listing"] = await listing(args.upstreams, args.devices_per, Path(tmp))
    return out
