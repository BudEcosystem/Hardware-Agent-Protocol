"""Throughput and latency with 1, 10 and 100 concurrent clients (one connection each), ``waitMs=1000`` invokes over a unix socket.

Two shapes, because one device executes one operation at a time: ``same-device`` (all clients on ``dev-1``; the executor
serialises them) and ``spread`` (client j uses ``dev-(j mod 100)+1``; devices execute in parallel but every intent still
shares the one journal and its fsync). Durability ``dispatch`` and ``process``. The difference between ``dispatch`` and
``process`` at 100 clients is the cost of one fsync barrier per intent without group commit.
"""

from __future__ import annotations

import asyncio
import secrets
import time

from common import Context, device_server, stats_ms, timed
from bhms.client.client import Client

NAME = "concurrency"


async def cell(ctx: Context, durability: str, clients: int, spread: bool, total: int) -> dict:
    tag = secrets.token_hex(3)
    async with device_server(ctx, durability, "unix", devices=100 if spread else 1, queue_limit=1024) as (target, _):
        conns = [await Client.connect(target, timeout=120) for _ in range(clients)]
        try:
            async def one(j: int, i: int) -> None:
                device = f"dev-{j % 100 + 1}" if spread else "dev-1"
                res = await conns[j].actions_invoke(device, "set_point", {"value": abs(i)}, operation_key=f"{tag}-{j}-{i}", wait_ms=2000)
                if res.operation.state != "completed":
                    raise RuntimeError(res.operation.state)

            per = max(1, total // clients)
            await asyncio.gather(*(one(j, -i - 1) for j in range(clients) for i in range(min(5, per))))  # warm-up
            samples: list[float] = []
            failures = 0
            row: dict = {}

            async def worker(j: int) -> None:
                nonlocal failures
                for i in range(per):
                    started = time.perf_counter()
                    try:
                        await one(j, i)
                    except Exception:  # noqa: BLE001 - counted, never hidden
                        failures += 1
                        continue
                    samples.append((time.perf_counter() - started) * 1000)

            with timed(row):
                begin = time.perf_counter()
                await asyncio.gather(*(worker(j) for j in range(clients)))
                elapsed = time.perf_counter() - begin
            row.update(stats_ms(samples, elapsed, failures))
            row["clients"] = clients
            return row
        finally:
            for c in conns:
                await c.close()


async def run(ctx: Context) -> dict:
    out: dict = {}
    clients_list = (1, 10, 100)
    for durability in ("dispatch", "process"):
        for spread in (False, True):
            for clients in clients_list:
                if clients == 1 and spread:
                    continue
                total = ctx.n(200, 2000) if durability == "dispatch" else ctx.n(500, 5000)
                key = f"{durability}/{'spread' if spread else 'same-device'}/{clients}"
                out[key] = await cell(ctx, durability, clients, spread, max(total, clients * 2))
    return out
