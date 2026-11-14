"""A device that appears between an upstream's first sync and its subscription is served (a board that says HELLO late)."""

from __future__ import annotations

import asyncio

from helpers.compact_rig import LED

from bhms import DeviceServer
from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig, UpstreamConfig
from bhms.gateway.upstreams import Upstream
from bhms.runtime.authority import Policy
from bhms.testing.memory import connect_in_process


async def test_a_device_added_between_the_initial_sync_and_the_subscription_is_still_served(tmp_path, monkeypatch):
    import os

    upstream_server = DeviceServer("late", policy=Policy({"gateway": {"uids": [os.getuid()], "scopes": ["admin"], "gateway": True}}),
                                   programs=False, store=None)
    await upstream_server.start()

    async def run(ctx, **arguments):
        return {"writes": 1}

    async def read():
        raise NotImplementedError

    original = Upstream._sync
    calls = {"n": 0}

    async def sync_then_a_device_appears(self, client):
        await original(self, client)
        calls["n"] += 1
        if calls["n"] == 1:  # after the list was loaded, before subscriptions/listen is open: no listChanged can reach us
            upstream_server.device_from_description(LED, run=lambda name: run, read=lambda name: read)

    monkeypatch.setattr(Upstream, "_sync", sync_then_a_device_appears)

    async def connect():
        return await connect_in_process(upstream_server.rpc)

    config = GatewayConfig(id="late", state_dir=tmp_path / "gw", connect_wait_ms=3000,
                           upstreams=(UpstreamConfig(name="u", connector=connect),))
    gateway = Gateway(config, memory=True)
    try:
        await gateway.start()
        async with await Client.from_transport(await connect_in_process(gateway.rpc)) as client:
            ids: list[str] = []
            for _ in range(100):
                ids = [d.device_id async for d in client.iter_devices()]
                if ids:
                    break
                await asyncio.sleep(0.05)
    finally:
        await gateway.close()
        await upstream_server.close()
    assert ids == ["u/bench-led"]
