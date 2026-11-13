"""Ping round-trip benchmark over real Unix-socket and stdio transports through Server + Client.

Run: ``python3 benchmarks/ping_roundtrip.py`` from ``sdk/python``. Reports sequential latency (p50/p99) and
pipelined throughput (messages/s with N requests in flight).
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

from bhms.client.client import Client
from bhms.jsonrpc.dispatcher import Server
from bhms.transport import serve_unix

STDIO_SERVER = Path(__file__).resolve().parents[1] / "tests" / "helpers" / "stdio_server.py"


async def measure(client: Client, label: str, sequential: int = 5000, total: int = 50_000, window: int = 256) -> None:
    for _ in range(500):  # warm-up
        await client.request("x-test/ping", {"n": 1})
    samples = []
    for i in range(sequential):
        start = time.perf_counter()
        await client.request("x-test/ping", {"n": i})
        samples.append((time.perf_counter() - start) * 1e6)
    samples.sort()
    sem = asyncio.Semaphore(window)

    async def one(i: int) -> None:
        async with sem:
            await client.request("x-test/ping", {"n": i})

    start = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(total)))
    elapsed = time.perf_counter() - start
    print(f"{label:8s} sequential: p50 {statistics.median(samples):7.1f} us  p99 {samples[int(len(samples) * .99)]:7.1f} us"
          f"  ({1e6 / statistics.mean(samples):8.0f} req/s) | pipelined x{window}: {total / elapsed:9.0f} req/s")


async def main() -> None:
    server = Server(server_info={"name": "bench", "version": "0"})

    async def ping(params, ctx):
        return {"resultType": "complete", "n": params.get("n", 0)}

    server.register("x-test/ping", ping)
    with tempfile.TemporaryDirectory() as tmp:
        listener = await serve_unix(os.path.join(tmp, "b.sock"), server.handle_connection)
        async with await Client.connect(f"unix:{tmp}/b.sock") as client:
            await measure(client, "unix")
        await listener.close()
    async with await Client.connect(f"stdio:{sys.executable} {STDIO_SERVER}") as client:
        await measure(client, "stdio")


if __name__ == "__main__":
    asyncio.run(main())
