"""Gateway step 4: cross-device leases.

Spec: BHMS-LSE-001/002/003/005/011/013, AUTH-013.
"""

from __future__ import annotations

import asyncio

import pytest

from bhms.client.client import Client
from bhms.gateway import Gateway
from bhms.protocol.errors import BhmsError
from bhms.runtime.authority import Policy
from helpers.gateway_rig import TOKENS, principals, rig

CLAMP, PLUNGER = "a/axis-1/clamp", "b/pump-1/plunger"


def upstream_leases(r, name):
    return [lease for lease in r.servers[name].leases.active()]


async def test_a_cross_upstream_lease_is_held_on_both(tmp_path):  # BHMS-LSE-013
    async with rig(tmp_path, conformance=True) as r:
        client = await r.client()
        lease = (await client.leases_acquire([PLUNGER, CLAMP], 5000)).lease
        assert lease.resources == [PLUNGER, CLAMP] and lease.state == "active"
        a, b = upstream_leases(r, "a"), upstream_leases(r, "b")
        assert [x.resources for x in a] == [("axis-1/clamp",)] and [x.resources for x in b] == [("pump-1/plunger",)]
        assert a[0].lease_id != lease.lease_id  # the upstream holds its own lease, for the gateway
        renewed = (await client.leases_renew(lease.lease_id, 8000)).lease
        assert renewed.fence == lease.fence and renewed.ttl_ms == 8000
        assert a[0].ttl_ms == 8000 and b[0].ttl_ms == 8000  # renewed together
        released = (await client.leases_release(lease.lease_id)).lease
        assert released.state == "released"
        assert upstream_leases(r, "a") == [] and upstream_leases(r, "b") == []  # released together
        assert (await client.leases_release(lease.lease_id)).lease.state == "released"  # unchanged (BHMS-LSE-006)


async def test_upstream_leases_are_acquired_in_ascending_resource_order(tmp_path, monkeypatch):  # BHMS-LSE-013
    from bhms.gateway.upstreams import Upstream

    order = []
    original = Upstream.call

    async def spy(self, method, params, **kw):
        if method == "leases/acquire":
            order.append((self.name, params["resources"]))
        return await original(self, method, params, **kw)

    monkeypatch.setattr(Upstream, "call", spy)
    async with rig(tmp_path, names=("a", "b", "c"), conformance=True) as r:
        client = await r.client()
        await client.leases_acquire(["c/pump-1/plunger", "b/axis-1/motion", "a/axis-1/motion", "b/axis-1/clamp"], 5000)
        assert order == [("a", ["axis-1/motion"]), ("b", ["axis-1/clamp", "axis-1/motion"]), ("c", ["pump-1/plunger"])]


async def test_nothing_is_held_when_one_upstream_cannot_grant(tmp_path):  # BHMS-LSE-001, LSE-013, LSE-002
    async with rig(tmp_path, conformance=True) as r:
        client = await r.client()
        rival = await Client.connect(f"unix:{tmp_path}/b.sock")  # another path to the same upstream
        held = (await rival.leases_acquire(["pump-1/plunger"], 5000)).lease
        with pytest.raises(BhmsError) as exc:
            await client.leases_acquire([CLAMP, PLUNGER], 5000)
        assert exc.value.code == "LEASE_CONFLICT" and exc.value.bound == [PLUNGER]
        assert held.lease_id not in str(exc.value) and "pump-1/plunger" not in exc.value.message.replace(PLUNGER, "")
        assert upstream_leases(r, "a") == [] and r.gateway.leases.manager.active() == []
        await rival.close()
        await asyncio.sleep(0.05)
        assert (await client.leases_acquire([CLAMP], 5000)).lease.state == "active"  # nothing was left behind


async def test_gateway_arbitrates_contenders_and_never_names_the_holder(tmp_path):  # BHMS-LSE-002, LSE-005
    async with rig(tmp_path, conformance=True) as r:
        one = await r.client()
        two = await r.client(token=TOKENS["agent-b"])
        lease = (await one.leases_acquire([CLAMP], 5000)).lease
        with pytest.raises(BhmsError) as exc:
            await two.leases_acquire([CLAMP], 5000)
        assert exc.value.code == "LEASE_CONFLICT" and exc.value.bound == [CLAMP] and "agent" not in exc.value.message
        with pytest.raises(BhmsError) as exc:
            await two.leases_renew(lease.lease_id, 5000)  # another principal's lease
        assert exc.value.code == "LEASE_CONFLICT"
        waiter = asyncio.create_task(two.leases_acquire([CLAMP], 5000, wait_ms=3000))
        await asyncio.sleep(0.2)
        assert not waiter.done()
        await one.leases_release(lease.lease_id)
        assert (await asyncio.wait_for(waiter, 3)).lease.fence > lease.fence


async def test_leased_actions_use_the_gateway_lease_and_forward_the_upstream_one(tmp_path):  # BHMS-LSE-010/011
    async with rig(tmp_path, conformance=True) as r:
        client = await r.client()
        other = await r.client(token=TOKENS["agent-b"])
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/axis-1", "clamp", {"force": 10}, operation_key="c0")
        assert exc.value.code == "LEASE_REQUIRED"
        lease = (await client.leases_acquire([CLAMP], 5000)).lease
        with pytest.raises(BhmsError) as exc:
            await other.actions_invoke("a/axis-1", "clamp", {"force": 10}, operation_key="c1", lease_id=lease.lease_id)
        assert exc.value.code == "LEASE_CONFLICT"
        op = (await client.actions_invoke("a/axis-1", "clamp", {"force": 10}, operation_key="c2",
                                          lease_id=lease.lease_id, wait_ms=2000)).operation
        assert op.state == "completed" and op.lease_id == lease.lease_id and op.fence == lease.fence
        upstream_op = next(row.record for row in r.servers["a"].store.list_operations(principal=None, limit=10))
        assert upstream_op["leaseId"] == upstream_leases(r, "a")[0].lease_id != lease.lease_id
        await client.leases_release(lease.lease_id)
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/axis-1", "clamp", {"force": 10}, operation_key="c3", lease_id=lease.lease_id)
        assert exc.value.code == "LEASE_EXPIRED"


async def test_a_superseded_holder_is_rejected_by_the_upstream(tmp_path):  # BHMS-LSE-011, 14-conformance fault row
    async with rig(tmp_path, conformance=True) as r:
        client = await r.client()
        lease = (await client.leases_acquire([CLAMP], 60000)).lease
        sim = r.axes["a"]
        before = sim.counter
        # "partition": the upstream's lease for this gateway lease is taken away and a newer one is granted
        # through another path; the gateway still believes its lease is active
        r.servers["a"].leases.revoke_covering(["axis-1/clamp"])
        rival = await Client.connect(f"unix:{tmp_path}/a.sock")
        newer = (await rival.leases_acquire(["axis-1/clamp"], 5000)).lease
        assert newer.fence > lease.fence or newer.fence > 0
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/axis-1", "clamp", {"force": 10}, operation_key="old", lease_id=lease.lease_id)
        assert exc.value.code in ("FENCED", "LEASE_EXPIRED", "LEASE_CONFLICT") and exc.value.may_have_acted is False
        assert sim.counter == before  # the endpoint rejected the old holder; nothing executed
        await rival.close()


async def test_a_lost_upstream_lease_revokes_the_gateway_lease_on_renew(tmp_path):
    async with rig(tmp_path, conformance=True) as r:
        client = await r.client()
        lease = (await client.leases_acquire([CLAMP, PLUNGER], 60000)).lease
        r.servers["b"].leases.revoke_covering(["pump-1/plunger"])
        with pytest.raises(BhmsError) as exc:
            await client.leases_renew(lease.lease_id, 60000)
        assert exc.value.code in ("FENCED", "LEASE_EXPIRED")
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/axis-1", "clamp", {"force": 1}, operation_key="x", lease_id=lease.lease_id)
        assert exc.value.code == "FENCED"
        await asyncio.sleep(0.1)
        assert upstream_leases(r, "a") == []  # the part still held was released


async def test_expiry_releases_the_upstream_parts(tmp_path):  # BHMS-LSE-006
    async with rig(tmp_path, conformance=True, gateway_kw={"lease_min_ttl_ms": 50}) as r:
        client = await r.client()
        lease = (await client.leases_acquire([CLAMP, PLUNGER], 100)).lease
        assert len(upstream_leases(r, "a")) == 1
        await asyncio.sleep(0.4)
        assert r.gateway.leases.manager.get(lease.lease_id).state == "expired"
        assert upstream_leases(r, "a") == [] and upstream_leases(r, "b") == []
        with pytest.raises(BhmsError) as exc:
            await client.leases_renew(lease.lease_id, 1000)
        assert exc.value.code == "LEASE_EXPIRED"


async def test_fences_increase_across_a_gateway_restart(tmp_path):  # BHMS-LSE-003
    async with rig(tmp_path, conformance=True) as r:
        client = await r.client()
        first = (await client.leases_acquire([CLAMP], 5000)).lease
        await client.close()
        await r.gateway.close()
        again = Gateway(r.gateway.config)
        await again.start()
        try:
            listener = await again.listen(r.socket)
            async with await Client.connect(r.socket) as fresh:
                with pytest.raises(BhmsError) as exc:  # leases are not persisted: the old id is unknown
                    await fresh.leases_renew(first.lease_id, 5000)
                assert exc.value.code == "LEASE_EXPIRED"
                await asyncio.sleep(0.1)
                second = (await fresh.leases_acquire([CLAMP], 5000)).lease
            await listener.close()
        finally:
            await again.close()
        assert second.fence > first.fence


async def test_revoking_the_lease_scope_revokes_the_leases(tmp_path):  # BHMS-AUTH-013
    async with rig(tmp_path, conformance=True) as r:
        client = await r.client()
        lease = (await client.leases_acquire([CLAMP], 60000)).lease
        r.gateway.set_policy(Policy(principals(agent_scopes=["read", "invoke:*/*"])))
        assert r.gateway.leases.manager.get(lease.lease_id).state == "revoked"
        await asyncio.sleep(0.1)
        assert upstream_leases(r, "a") == []
