"""Open-loop latency: invokes arrive at a fixed offered rate (Poisson), independent of how fast the server answers.

The ``concurrency`` scenario is closed-loop (each client waits for its answer before sending the next), so its latencies are
service time plus queueing behind the other clients and hide the tail an arrival process produces. Here capacity is first
measured (closed loop, 100 connections for a few seconds, devices spread over 100), then arrivals are generated at 50% and 90% of
it with exponential inter-arrival times; latency is measured **from the scheduled arrival instant**, not from when the client got
round to sending, so a stalled sender cannot hide queueing (no coordinated omission). The offered and achieved rates are
reported; if the achieved rate falls short (or arrivals fail or are unfinished after a 20 s drain) the client or server saturated and the cell is not a valid latency measurement. Arrivals use 20 connections
round-robin and ``waitMs=2000``. Durability ``dispatch`` (and ``process`` for the CPU-bound ceiling), unix socket.
"""

from __future__ import annotations

import asyncio
import random
import secrets
import time

from common import Context, device_server, stats_ms, timed
from bhms.client.client import Client

NAME = "openloop"


async def capacity(conns: list[Client], tag: str, seconds: float) -> float:
    done = 0
    stop = time.perf_counter() + seconds

    async def worker(j: int) -> None:
        nonlocal done
        i = 0
        while time.perf_counter() < stop:
            await conns[j].actions_invoke(f"dev-{j % 100 + 1}", "set_point", {"value": i}, operation_key=f"{tag}-cap-{j}-{i}", wait_ms=2000)
            done += 1
            i += 1

    begin = time.perf_counter()
    await asyncio.gather(*(worker(j) for j in range(len(conns))))
    return done / (time.perf_counter() - begin)


async def open_loop(conns: list[Client], tag: str, rate: float, seconds: float, label: str) -> dict:
    rng = random.Random(7)
    samples: list[float] = []
    failures = 0
    tasks: list[asyncio.Task] = []

    async def one(i: int, scheduled: float) -> None:
        nonlocal failures
        try:
            await conns[i % len(conns)].actions_invoke(f"dev-{i % 100 + 1}", "set_point", {"value": i % 1000},
                                                       operation_key=f"{tag}-{label}-{i}", wait_ms=2000)
        except Exception:  # noqa: BLE001 - counted, never hidden
            failures += 1
            return
        samples.append((time.perf_counter() - scheduled) * 1000)

    start = time.perf_counter()
    at, i = start, 0
    while at < start + seconds:
        at += rng.expovariate(rate)
        delay = at - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        tasks.append(asyncio.create_task(one(i, at)))
        i += 1
    _, pending = await asyncio.wait(tasks, timeout=20)  # a saturated server must not stall the run for minutes
    for task in pending:
        task.cancel()
    failures += len(pending)
    elapsed = time.perf_counter() - start
    row = stats_ms(samples, elapsed, failures, label)
    row.update(offered_per_s=round(rate), achieved_per_s=round(len(samples) / elapsed), arrivals=i)
    return row


async def cell(ctx: Context, durability: str) -> dict:
    tag = secrets.token_hex(3)
    async with device_server(ctx, durability, "unix", devices=100, queue_limit=4096) as (target, _):
        conns = [await Client.connect(target, timeout=120) for _ in range(20)]
        try:
            cap = await capacity(conns, tag, ctx.n(3, 6))
            out: dict = {"measured_capacity_per_s": round(cap)}
            # process mode saturates the single-process Python *client* long before the server (a first run offered 50% and 90%
            # of the closed-loop capacity and the client achieved only 1.7k/s, then overflowed the queue), so it is offered
            # 10% and 20% (well under what one Python client can generate) and shows the server tail at low load.
            for frac in (0.5, 0.9) if durability == "dispatch" else (0.1, 0.2):
                row: dict = {}
                with timed(row):
                    row.update(await open_loop(conns, tag, cap * frac, ctx.n(5, 15), f"openloop__{durability}_{int(frac * 100)}pct"))
                out[f"{int(frac * 100)}% of closed-loop capacity"] = row
            return out
        finally:
            for c in conns:
                await c.close()


async def run(ctx: Context) -> dict:
    return {durability: await cell(ctx, durability) for durability in ("dispatch", "process")}
