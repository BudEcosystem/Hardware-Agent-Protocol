"""The gateway over Streamable HTTP versus its unix socket: ``devices/list`` paging over 10,000 devices and an ``actions/invoke``.

Light fleet of 100 upstreams x 100 devices behind one gateway with two listeners (unix and ``http://127.0.0.1:P/bhms``); the same
Python client pages the catalog over each and invokes a real device (in-process upstream, ``waitMs=0`` and ``1000``). Needs the
optional ``http`` extra (aiohttp). Client, gateway and upstreams share one event loop, as in Task 5's benchmark.
"""

from __future__ import annotations

import gc
import tempfile
import time
from pathlib import Path

from common import TOKEN, Context, free_port, stats_ms, timed
from bhms import DeviceServer, Range
from bhms.client.client import Client
from bhms.runtime.authority import token_digest
from bhms.gateway import Gateway, GatewayConfig, UpstreamConfig
from bhms.testing.gateway_fleet import build_light_fleet, gateway_uid_policy

NAME = "gateway_http"


async def page(client: Client, limit: int, rounds: int, seen: list[str] | None = None) -> list[float]:
    samples: list[float] = []
    for _ in range(rounds):
        cursor = None
        while True:
            started = time.perf_counter()
            result = await client.devices_list(limit=limit, cursor=cursor)
            samples.append((time.perf_counter() - started) * 1000)
            if seen is not None:
                seen.extend(d.device_id for d in result.devices)
            cursor = result.next_cursor
            if cursor is None:
                break
    return samples


async def run(ctx: Context) -> dict:
    out: dict = {}
    with tempfile.TemporaryDirectory(dir=ctx.state_root) as tmp:
        fleet = await build_light_fleet(100, devices_per=100)
        upstream = DeviceServer("bench-up", store=None, programs=False, policy=gateway_uid_policy())
        dev = upstream.device("dev-1", resources=["dev-1"])
        dev.report_alive()

        @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
        async def set_point(ctx, value: Range(0, 1e9, unit="1")) -> None:  # noqa: F821
            return None

        await upstream.listen(f"unix:{tmp}/up.sock")
        configs = (*fleet.upstream_configs(), UpstreamConfig(name="real", url=f"unix:{tmp}/up.sock"))
        gateway = Gateway(GatewayConfig(id="bench", state_dir=Path(tmp) / "gw", upstreams=configs,
                                        principals={"admin": {"tokens": [token_digest(TOKEN)], "scopes": ["admin"]}},
                                        connect_wait_ms=600_000), memory=True)
        await gateway.start()
        await gateway.wait_validated(600)
        port = free_port()
        await gateway.listen(f"unix:{tmp}/gw.sock")
        await gateway.listen(f"http://127.0.0.1:{port}/bhms")
        gc.collect()
        gc.freeze()
        out["devices"] = len(gateway.catalog)
        clients = {"unix": await Client.connect(f"unix:{tmp}/gw.sock", timeout=60),
                   "http": await Client.connect(f"http://127.0.0.1:{port}/bhms", token=TOKEN, timeout=60)}
        try:
            for name, client in clients.items():
                row: dict = {}
                with timed(row):
                    for limit in (100, 500):
                        seen: list[str] = []
                        await page(client, limit, 1, seen)  # warm-up and the correctness pass: every device once, in order
                        row[f"listed_correctly_limit_{limit}"] = (len(seen) == out["devices"] and seen == sorted(seen)
                                                                  and len(set(seen)) == len(seen))
                        samples = await page(client, limit, 3)
                        row[f"devices_list_limit_{limit}"] = stats_ms(samples, sum(samples) / 1000, label=f"gateway_http__{name}_list{limit}")
                    for wait_ms in (0, 1000):
                        lat: list[float] = []
                        for i in range(ctx.n(100, 500) + 50):
                            started = time.perf_counter()
                            await client.actions_invoke("real/dev-1", "set_point", {"value": i}, operation_key=f"{name}-{wait_ms}-{i}",
                                                        wait_ms=wait_ms or None)
                            if i >= 50:
                                lat.append((time.perf_counter() - started) * 1000)
                        row[f"invoke_waitMs_{wait_ms}"] = stats_ms(lat, sum(lat) / 1000, label=f"gateway_http__{name}_invoke{wait_ms}")
                out[name] = row
        finally:
            for client in clients.values():
                await client.close()
            await gateway.close()
            await upstream.close()
            await fleet.close()
    return out
