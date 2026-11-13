"""Gateway measurements: scale, event fan-in and the overhead the gateway adds to ``actions/invoke``.

Run: ``python3 sdk/python/benchmarks/gateway_scale.py [--upstreams 1000] [--devices-per 10] [--events 5] [--n 1000]
[--json out.json] [--skip scale,fanin,overhead]``.

* **scale** — start a gateway over ``--upstreams`` light in-process upstreams (``--devices-per`` devices each), report the
  start-up time (connect, list, describe, verify digests; schema validation continues in the background and is timed
  separately), the process memory, and ``devices/list`` paging latency at limit 100 and 500 over every page (Unix socket,
  Python client: includes JSON and pydantic parsing of the page on the client).
* **fanin** — ``subscriptions/listen`` with ``events`` and *no* deviceId filter while every upstream emits ``--events``
  events at once: total time, events per second, per-event latency from ``emit`` to the client (p50/p99/max), and the
  memory the run added.
* **overhead** — ``actions/invoke`` (waitMs=0 and waitMs=1000, sequential, ``--n`` after warm-up) straight to a device
  server over a Unix socket versus through a gateway whose upstream is the same server, for the gateway's journal modes
  ``process`` (no fsync) and ``dispatch`` (default: the gateway never needs a barrier, see ``bhms.gateway.journal``; the
  upstream's own durability is non-durable here so that only the gateway's cost is measured).
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import resource
import statistics
import sys
import tempfile
import time
from pathlib import Path

from bhms import DeviceServer, Range
from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig, UpstreamConfig
from bhms.testing.gateway_fleet import build_light_fleet, gateway_uid_policy


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def summarize(samples_ms: list[float]) -> dict[str, float]:
    ordered = sorted(samples_ms)
    pick = lambda q: ordered[min(len(ordered) - 1, int(len(ordered) * q))]  # noqa: E731
    return {"n": len(ordered), "p50": round(statistics.median(ordered), 3), "p95": round(pick(0.95), 3),
            "p99": round(pick(0.99), 3), "max": round(ordered[-1], 3)}


async def scale(args: argparse.Namespace, tmp: Path) -> dict:
    fleet = await build_light_fleet(args.upstreams, devices_per=args.devices_per)
    config = GatewayConfig(id="bench", state_dir=tmp / "gw", upstreams=fleet.upstream_configs(), principals={},
                           connect_wait_ms=600_000)
    gateway = Gateway(config, memory=True)
    before = rss_mb()
    started = time.perf_counter()
    await gateway.start()
    start_s = time.perf_counter() - started
    validated = time.perf_counter()
    await gateway.wait_validated(600)
    validate_s = time.perf_counter() - validated
    await gateway.listen(f"unix:{tmp}/gw.sock")
    client = await Client.connect(f"unix:{tmp}/gw.sock", timeout=60)
    gc.collect()
    gc.freeze()  # what Gateway.serve does
    out: dict = {"upstreams": args.upstreams, "devices": len(gateway.catalog), "start_s": round(start_s, 2),
                 "background_validation_s": round(validate_s, 2), "rss_mb_after_start": round(rss_mb(), 1),
                 "rss_mb_added": round(rss_mb() - before, 1), "paging": {}}
    for limit in (100, 500):
        for _ in range(3):  # warm the page cache of the client's parser
            cursor = None
            samples = []
            while True:
                t = time.perf_counter()
                page = await client.devices_list(limit=limit, cursor=cursor)
                samples.append((time.perf_counter() - t) * 1000)
                cursor = page.next_cursor
                if cursor is None:
                    break
        out["paging"][f"limit_{limit}_ms"] = summarize(samples)
    await client.close()
    await gateway.close()
    await fleet.close()
    return out


async def fanin(args: argparse.Namespace, tmp: Path) -> dict:
    fleet = await build_light_fleet(args.upstreams, devices_per=1)
    config = GatewayConfig(id="bench", state_dir=tmp / "gw2", upstreams=fleet.upstream_configs(), principals={},
                           connect_wait_ms=600_000)
    gateway = Gateway(config, memory=True)
    await gateway.start()
    await gateway.wait_validated(600)
    await gateway.listen(f"unix:{tmp}/gw2.sock")
    client = await Client.connect(f"unix:{tmp}/gw2.sock", timeout=60)
    total = args.upstreams * args.events
    before = rss_mb()
    async with await client.subscribe(events={}) as sub:
        while not all(s.subscribers for s in fleet):
            await asyncio.sleep(0.05)
        sent: dict[str, float] = {}
        started = time.perf_counter()
        for i, upstream in enumerate(fleet):
            for n in range(args.events):
                sent[f"{i}-{n}"] = time.perf_counter()
                upstream.emit(device="d0", message=f"{i}-{n}")
        latencies = []
        for _ in range(total):
            event = (await asyncio.wait_for(sub.__anext__(), 120)).params.event
            latencies.append((time.perf_counter() - sent[event.message]) * 1000)
        elapsed = time.perf_counter() - started
    out = {"upstreams": args.upstreams, "events": total, "total_s": round(elapsed, 3),
           "events_per_s": round(total / elapsed), "latency_ms": summarize(latencies),
           "rss_mb_added": round(rss_mb() - before, 1), "upstream_streams": args.upstreams}
    await client.close()
    await gateway.close()
    await fleet.close()
    return out


async def overhead(args: argparse.Namespace, tmp: Path) -> dict:
    srv = DeviceServer("bench-up", store=None, programs=False, policy=gateway_uid_policy())
    dev = srv.device("dev-1", resources=["dev-1"])
    dev.report_alive()

    @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
    async def set_point(ctx, value: Range(0, 1e9, unit="1")) -> None:  # noqa: F821
        return None

    await srv.listen(f"unix:{tmp}/up.sock")
    out: dict = {}

    async def run(client: Client, device: str, label: str, wait_ms: int) -> None:
        for i in range(args.n + 100):
            started = time.perf_counter()
            await client.actions_invoke(device, "set_point", {"value": i}, operation_key=f"{label}-{wait_ms}-{i}",
                                        wait_ms=wait_ms or None)
            if i >= 100:
                samples.append((time.perf_counter() - started) * 1000)

    direct = await Client.connect(f"unix:{tmp}/up.sock")
    for wait_ms in (0, 1000):
        samples: list[float] = []
        await run(direct, "dev-1", "direct", wait_ms)
        out[f"direct_wait{wait_ms}"] = summarize(samples)
    await direct.close()
    for mode in ("process", "dispatch"):
        config = GatewayConfig(id=f"bench-{mode}", state_dir=tmp / f"gw-{mode}", durability=mode, principals={},
                               upstreams=(UpstreamConfig(name="up", url=f"unix:{tmp}/up.sock"),), connect_wait_ms=10_000)
        gateway = Gateway(config)
        await gateway.start()
        await gateway.listen(f"unix:{tmp}/gw-{mode}.sock")
        client = await Client.connect(f"unix:{tmp}/gw-{mode}.sock")
        for wait_ms in (0, 1000):
            samples = []
            await run(client, "up/dev-1", mode, wait_ms)
            out[f"gateway_{mode}_wait{wait_ms}"] = summarize(samples)
        await client.close()
        await gateway.close()
    await srv.close()
    for wait_ms in (0, 1000):
        base = out[f"direct_wait{wait_ms}"]["p50"]
        for mode in ("process", "dispatch"):
            out[f"gateway_{mode}_wait{wait_ms}"]["overhead_p50_ms"] = round(
                out[f"gateway_{mode}_wait{wait_ms}"]["p50"] - base, 3)
    return out


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--upstreams", type=int, default=1000)
    parser.add_argument("--devices-per", type=int, default=10)
    parser.add_argument("--events", type=int, default=5, help="events emitted per upstream in the fan-in run")
    parser.add_argument("--n", type=int, default=1000, help="invokes per overhead case")
    parser.add_argument("--json", default=None)
    parser.add_argument("--skip", default="", help="comma-separated: scale, fanin, overhead")
    args = parser.parse_args()
    skip = set(args.skip.split(","))
    results: dict = {}
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        for name, runner in (("scale", scale), ("fanin", fanin), ("overhead", overhead)):
            if name not in skip:
                results[name] = await runner(args, tmp)
                print(json.dumps({name: results[name]}, indent=1), flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
