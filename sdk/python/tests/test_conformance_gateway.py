"""Defects the conformance runner found in the gateway, and BHMS-SEC-022 against a malicious upstream."""

from __future__ import annotations

import asyncio

import pytest

from bhms.client.client import Client
from bhms.protocol.errors import BhmsError
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


async def test_a_retained_transaction_observation_needs_only_read_authority(tmp_path):  # BHMS-OBS-011
    """Found by observations.retained-after-effect: the gateway demanded invoke scope and a lease for every read."""
    from bhms.runtime.authority import token_digest
    from helpers.gateway_rig import principals

    doc = {**principals(), "reader": {"tokens": [token_digest("tok-reader")], "scopes": ["read"]}}
    async with rig(tmp_path, ("a",), conformance=True, principals_doc=doc) as r:
        admin = await r.client(token="tok-admin")
        reader = await r.client(token="tok-reader")  # read scope only: no invoke, no lease
        with pytest.raises(BhmsError) as nothing_retained:
            await reader.properties_read("a/axis-1", "fifo")
        assert nothing_retained.value.code == "UNAUTHORIZED"  # nothing is retained yet: a new transaction would be needed
        lease = (await admin.leases_acquire(["a/axis-1/motion"], 30_000)).lease
        popped = (await admin.properties_read("a/axis-1", "fifo", fresh=True)).observation
        await admin.leases_release(lease.lease_id)
        again = (await reader.properties_read("a/axis-1", "fifo")).observation
        assert again.value == popped.value and again.sequence == popped.sequence and again.age_ms >= popped.age_ms
        within = (await reader.properties_read("a/axis-1", "fifo", max_age_ms=60_000)).observation
        assert within.sequence == popped.sequence
        with pytest.raises(BhmsError) as fresh:
            await reader.properties_read("a/axis-1", "fifo", fresh=True)  # a new acquisition needs invoke authority (BHMS-AUTH-012)
        assert fresh.value.code == "UNAUTHORIZED"
        with pytest.raises(BhmsError) as too_old:
            await reader.properties_read("a/axis-1", "fifo", max_age_ms=0)
        assert too_old.value.code == "UNAUTHORIZED"


async def test_an_operation_that_misses_its_deadline_in_the_upstream_queue_is_rejected_through_the_gateway(tmp_path):  # OPS-070
    """Found while reviewing the conformance run: the gateway showed upstream ``accepted`` as ``dispatching`` and mapped an
    upstream ``rejected`` to ``failed``; a refusal before dispatch must stay ``rejected`` with effect none."""
    async with rig(tmp_path, ("a",), conformance=True) as r:
        client = await r.client(token="tok-admin")
        busy = (await client.actions_invoke("a/axis-1", "slow_move", {"duration_ms": 900})).operation
        queued = (await client.actions_invoke("a/axis-1", "pulse", {"count": 1}, deadline_ms=150)).operation
        assert queued.state == "accepted"
        settled = (await client.operations_wait(queued.operation_id, 5000)).operation
        assert settled.state == "rejected" and settled.effect == "none"
        assert settled.error.bhms_code == "DEADLINE_EXCEEDED" and settled.error.may_have_acted is False
        await client.operations_wait(busy.operation_id, 5000)


async def test_an_operation_queued_upstream_survives_a_gateway_restart_indexed_and_unknown(tmp_path):
    """The gateway now records upstream-queued operations as ``accepted``; after a restart they are found, moved to ``unknown``
    (BHMS-OPS-080) and indexed by their upstream operation id so that the upstream's notifications reconcile them."""
    async with rig(tmp_path, ("a",), conformance=True) as r:
        client = await r.client(token="tok-admin")
        busy = (await client.actions_invoke("a/axis-1", "slow_move", {"duration_ms": 1500})).operation
        queued = (await client.actions_invoke("a/axis-1", "pulse", {"count": 1})).operation
        assert queued.state == "accepted"
        config = r.gateway.config
        await client.close()
        await r.gateway.close()
        second = Gateway(config)
        await second.start()
        try:
            record = second.journal.get(queued.operation_id)
            assert record is not None and record.state == "unknown"
            upstream_id = record.private["upstreamOperationId"]
            assert second.router.by_upstream[("a", upstream_id)] == queued.operation_id
            for _ in range(150):  # the upstream finishes both operations; its notifications reconcile the gateway's record
                if second.journal.get(queued.operation_id).state != "unknown":
                    break
                await asyncio.sleep(0.1)
            assert second.journal.get(queued.operation_id).state in ("completed", "running")
            assert second.journal.get(busy.operation_id).state != "accepted"
        finally:
            await second.close()
