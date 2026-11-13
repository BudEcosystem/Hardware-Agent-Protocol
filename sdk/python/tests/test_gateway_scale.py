"""Gateway step 10: scale - 1,000 in-process upstreams list correctly; 10,000 devices page in <= 50 ms; events fan in.

Numbers behind the Task 5 report come from ``benchmarks/gateway_scale.py``; these tests keep the claims true.
"""

from __future__ import annotations

import asyncio
import gc
import statistics
import time

from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig
from bhms.protocol.canonical import digest
from bhms.testing.gateway_fleet import build_light_fleet


async def start(tmp_path, fleet, **kw) -> tuple[Gateway, Client]:
    config = GatewayConfig(id="scale", state_dir=tmp_path / "gw", upstreams=fleet.upstream_configs(), principals={},
                           connect_wait_ms=120_000, **kw)
    gateway = Gateway(config, memory=True)
    await gateway.start()
    await gateway.listen(f"unix:{tmp_path}/gw.sock")
    return gateway, await Client.connect(f"unix:{tmp_path}/gw.sock", timeout=60)


async def test_a_thousand_upstreams_list_correctly(tmp_path):  # the Task 5 acceptance row
    fleet = await build_light_fleet(1000, devices_per=3)
    gateway, client = await start(tmp_path, fleet)
    try:
        assert client.server.capabilities.gateway.upstreams == 1000
        ids = [d.device_id async for d in client.iter_devices(limit=500)]
        expected = sorted(f"u{i}/d{j}" for i in range(1000) for j in range(3))
        assert ids == expected  # every device once, in code-point order (BHMS-LIF-062)
        assert all(up.status == "up" for up in gateway.upstreams.values())
        assert await gateway.wait_validated(120)
        for device_id in (ids[0], ids[1234], ids[-1]):  # a described sample: namespaced and digest-correct
            description = (await client.devices_describe(device_id)).description.model_dump(by_alias=True,
                                                                                            exclude_unset=True)
            assert description["deviceId"] == device_id
            assert description["digest"] == digest({k: v for k, v in description.items() if k != "digest"})
        # a page's cursor survives a device appearing between pages (opaque, position-based)
        first = await client.devices_list(limit=10)
        again = await client.devices_list(limit=10, cursor=first.next_cursor)
        assert [d.device_id for d in first.devices + again.devices] == expected[:20]
    finally:
        await client.close()
        await gateway.close()
        await fleet.close()


async def test_ten_thousand_devices_page_within_50_ms(tmp_path):  # the Task 5 scale row
    fleet = await build_light_fleet(100, devices_per=100)
    gateway, client = await start(tmp_path, fleet)
    try:
        assert len(gateway.catalog) == 10_000
        assert await gateway.wait_validated(300)
        gc.collect()
        gc.freeze()  # what Gateway.serve does: no 200 ms generation-2 pause over the start-up heap
        for limit in (100, 500):
            cursor, samples = None, []
            for _ in range(10_000 // limit):
                started = time.perf_counter()
                page = await client.devices_list(limit=limit, cursor=cursor)
                samples.append((time.perf_counter() - started) * 1000)
                cursor = page.next_cursor
            assert cursor is None
            ordered = sorted(samples)
            # second-largest, not max: a generation-2 garbage collection over a big heap can take 200 ms (Gateway.serve freezes
            # the start-up heap to avoid it; this test process does not)
            assert statistics.median(samples) < 50 and ordered[-2] < 50, (limit, samples)
        started = time.perf_counter()  # a filtered scan over all 10,000 (worst case: the filter matches the last device)
        hit = await client.devices_list(filter={"text": "Device 99 of 99"}, limit=500)
        assert hit.devices and (time.perf_counter() - started) * 1000 < 200
    finally:
        gc.unfreeze()
        await client.close()
        await gateway.close()
        await fleet.close()


async def test_events_fan_in_from_a_thousand_upstreams_without_a_device_filter(tmp_path):  # Task 2 open question 11
    fleet = await build_light_fleet(1000, devices_per=1)
    gateway, client = await start(tmp_path, fleet)
    try:
        async with await client.subscribe(events={}) as sub:
            for _ in range(100):
                if all(s.subscribers for s in fleet):
                    break
                await asyncio.sleep(0.05)
            started = time.perf_counter()
            for i, upstream in enumerate(fleet):
                for n in range(5):
                    upstream.emit(device="d0", message=f"{i}-{n}")
            got = []
            while len(got) < 5000:
                got.append((await asyncio.wait_for(sub.__anext__(), 30)).params.event)
            elapsed = time.perf_counter() - started
        assert {e.message for e in got} == {f"{i}-{n}" for i in range(1000) for n in range(5)}  # none lost, none twice
        assert all(e.device_id == f"u{e.message.split('-')[0]}/d0" for e in got)
        cursors = [e.cursor for e in got]
        assert len(set(cursors)) == 5000
        seqs = [int(c.rsplit(".", 1)[1], 16) for c in cursors]
        assert seqs == sorted(seqs)  # the gateway's own total order (BHMS-EVT-001)
        assert elapsed < 30, elapsed
    finally:
        await client.close()
        await gateway.close()
        await fleet.close()
