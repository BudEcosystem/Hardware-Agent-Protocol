"""Transport cost alone: ``x-test/ping`` round trip and pipelined throughput over stdio, unix, tcp and websocket.

A bare JSON-RPC ``Server`` (no device runtime, no journal; ``servers/ping_server.py``) in its own process, one client in this
process. TCP appears only here: ``DeviceServer`` refuses a TCP listener (no credential on TCP), so durable invokes cannot be
measured over it. Streamable HTTP is measured through the gateway (scenario ``gateway_http``).
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time

from common import PING_SERVER, Context, free_port, measure, spawn_server, stats_ms, timed
from bhms.client.client import Client

NAME = "transports"


async def run(ctx: Context) -> dict:
    n, window = ctx.n(500, 5000), 256
    out: dict = {}
    with tempfile.TemporaryDirectory(dir=ctx.state_root) as tmp:
        cases = {"unix": f"unix:{tmp}/p.sock", "tcp": f"tcp://127.0.0.1:{free_port()}", "websocket": f"ws://127.0.0.1:{free_port()}",
                 "stdio": None}
        for name, url in cases.items():
            server = spawn_server(PING_SERVER, [url] if url else [], url=url) if url else None
            target = url or f"stdio:{sys.executable} {PING_SERVER}"
            try:
                async with await Client.connect(target) as client:
                    async def ping(i: int, client: Client = client) -> None:
                        await client.request("x-test/ping", {"n": i})

                    await measure(ping, 300, 1)
                    row: dict = {}
                    with timed(row):
                        samples, elapsed, failures = await measure(ping, n, 1)
                        row["sequential"] = stats_ms(samples, elapsed, failures)
                        total = n * 10
                        started = time.perf_counter()
                        _, _, failures = await measure(ping, total, window)
                        row["pipelined"] = {"window": window, "requests": total, "per_s": round(total / (time.perf_counter() - started)),
                                            "failures": failures}
                    out[name] = row
            finally:
                if server:
                    server.stop()
            await asyncio.sleep(0)
    return out
