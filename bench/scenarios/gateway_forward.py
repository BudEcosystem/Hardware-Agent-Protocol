"""Forwarding through the gateway with concurrent clients: what the pending-forward barrier costs (Task 12b, item 3).

Before the gateway sends an ``actions/invoke`` upstream it makes a pending-forward row durable (``ForwardJournal.pending_put``,
BHMS-OPS-003). This scenario sends ``waitMs=1000`` invokes through a gateway to an in-process upstream device server
(``store=None``, 100 devices, so the upstream adds no fsync of its own) with 1, 10 and 100 concurrent clients (client j uses
``up/dev-(j mod 100)+1``; the upstream link allows 128 calls in flight, so that 100 clients are not refused ``BUSY``), for the gateway journal modes ``dispatch`` (the barrier) and ``process`` (no barrier). The
difference between the two is the barrier's cost; with group commit concurrent forwards share their fsyncs.

Like the ``gateway`` scenario it runs the gateway, the upstream and the clients on one event loop (the gateway's CPU and
journal cost, not 100 real peers). The gateway's state directory is under ``ctx.state_root`` (the fsync being measured).
"""

from __future__ import annotations

import asyncio
import secrets
import tempfile
import time
from pathlib import Path

from common import Context, stats_ms, timed
from bhms import DeviceServer, Range
from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig
from bhms.gateway.config import UpstreamConfig
from bhms.testing.gateway_fleet import gateway_uid_policy

NAME = "gateway_forward"
DEVICES = 100


async def upstream(path: Path) -> DeviceServer:
    srv = DeviceServer("bench-forward-up", store=None, programs=False, policy=gateway_uid_policy(), queue_limit=1024)
    for i in range(1, DEVICES + 1):
        dev = srv.device(f"dev-{i}", resources=[f"dev-{i}"])
        dev.report_alive()

        @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
        async def set_point(ctx, value: Range(0, 1e9, unit="1")) -> None:  # noqa: F821 - unit marker
            return None

    await srv.listen(f"unix:{path}")
    return srv


async def cell(tmp: Path, mode: str, clients: int, total: int) -> dict:
    tag = secrets.token_hex(3)
    gateway = Gateway(GatewayConfig(id=f"bench-fwd-{mode}-{clients}", state_dir=tmp / f"gw-{mode}-{clients}", durability=mode,
                                    principals={}, upstreams=(UpstreamConfig(name="up", url=f"unix:{tmp}/up.sock", max_inflight=128,
                                                                              queue_size=256),),
                                    connect_wait_ms=10_000))
    await gateway.start()
    await gateway.listen(f"unix:{tmp}/gw-{mode}-{clients}.sock")
    conns = [await Client.connect(f"unix:{tmp}/gw-{mode}-{clients}.sock", timeout=120) for _ in range(clients)]
    try:
        async def one(j: int, i: int) -> None:
            res = await conns[j].actions_invoke(f"up/dev-{j % DEVICES + 1}", "set_point", {"value": abs(i)},
                                                operation_key=f"{tag}-{j}-{i}", wait_ms=1000)
            if res.operation.state != "completed":
                raise RuntimeError(res.operation.state)

        per = max(1, total // clients)
        for i in range(min(5, per)):  # warm-up: one invoke per client at a time, as in the measurement
            await asyncio.gather(*(one(j, -i - 1) for j in range(clients)))
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
        row.update(stats_ms(samples, elapsed, failures, f"gateway_forward__{mode}_{clients}"))
        row["clients"] = clients
        return row
    finally:
        for c in conns:
            await c.close()
        await gateway.close()


async def run(ctx: Context) -> dict:
    out: dict = {}
    with tempfile.TemporaryDirectory(dir=ctx.state_root) as directory:
        tmp = Path(directory)
        srv = await upstream(tmp / "up.sock")
        try:
            for mode in ("dispatch", "process"):
                for clients in (1, 10, 100):
                    out[f"{mode}/{clients}"] = await cell(tmp, mode, clients, max(ctx.n(200, 2000), clients * 2))
        finally:
            await srv.close()
    return out
