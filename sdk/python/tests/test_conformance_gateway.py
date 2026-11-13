"""Defects the conformance runner found in the gateway, and BHMS-SEC-022 against a malicious upstream."""

from __future__ import annotations

import asyncio

from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig, UpstreamConfig
from bhms.testing.broken_devices import DEFECTS, Mutator
from bhms.testing.conformance_device import build
from bhms.testing.gateway_fleet import gateway_uid_policy
from bhms.testing.memory import connect_in_process, memory_pair
from helpers.gateway_rig import rig


async def test_cancel_without_a_reason_is_forwarded_without_a_null_reason(tmp_path):
    """Found by conformance.operations.cancel-states through a gateway: ``reason: null`` was forwarded and refused upstream."""
    async with rig(tmp_path, ("a",), conformance=True) as r:
        client = await r.client(token="tok-admin")
        op = (await client.actions_invoke("a/axis-1", "slow_move", {"duration_ms": 2000})).operation
        cancelled = (await client.operations_cancel(op.operation_id)).operation
        assert cancelled.cancel.state in ("requested", "acknowledged", "confirmed")
        settled = await client.operations_wait(op.operation_id, 5000)
        assert settled.operation.state == "canceled"


async def test_a_wrong_description_digest_from_an_upstream_is_not_served(tmp_path):  # BHMS-SEC-022
    healthy, _ = build(memory=True, policy=gateway_uid_policy())
    broken, _ = build(memory=True, policy=gateway_uid_policy())
    await healthy.start()
    await broken.start()

    async def good():
        return await connect_in_process(healthy.rpc)

    async def bad():
        client, server_end = memory_pair()
        task = asyncio.get_running_loop().create_task(broken.rpc.handle_connection(Mutator(server_end, DEFECTS["wrong-description-digest"])))
        task.add_done_callback(lambda t: t.cancelled() or t.exception())
        return client

    config = GatewayConfig(id="sec-022", state_dir=tmp_path / "gw", connect_wait_ms=3000,
                           upstreams=(UpstreamConfig(name="good", connector=good), UpstreamConfig(name="bad", connector=bad)))
    gateway = Gateway(config, memory=True)
    try:
        await gateway.start()
        async with await Client.from_transport(await connect_in_process(gateway.rpc)) as client:
            ids = [d.device_id async for d in client.iter_devices()]
    finally:
        await gateway.close()
        await healthy.close()
        await broken.close()
    assert "good/axis-1" in ids
    assert not [i for i in ids if i.startswith("bad/")], f"a description with a wrong digest was served: {ids}"
