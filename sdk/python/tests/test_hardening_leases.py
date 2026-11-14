"""Task 7b group A, leases: a supplied lease is always validated (BHMS-LSE-005/007/010) and a held lease blocks every
request that does not present it (BHMS-LSE-014), at the device server and at the gateway.

Evidence: Task 11 report, hostile suite "lease theft" (T1a gateway defect, T1b spec gap): four attempts reached a device.
"""

from __future__ import annotations

import asyncio

import pytest

from bhms.client.client import Client
from bhms.protocol.errors import BhmsError
from bhms.testing.conformance_device import build as conformance_build
from helpers.gateway_rig import TOKENS, rig

MOTION, CLAMP = "a/axis-1/motion", "a/axis-1/clamp"


async def _refused(call, code: str) -> BhmsError:
    with pytest.raises(BhmsError) as exc:
        await call
    assert exc.value.bhms_code == code, exc.value
    assert exc.value.may_have_acted is False
    return exc.value


async def test_the_four_lease_thefts_of_task_11_are_refused_at_the_gateway(tmp_path):
    """``pulse`` acts on ``axis-1/motion`` and does not declare ``requiresLease`` (the twins "as declared")."""
    async with rig(tmp_path, conformance=True) as r:
        holder = await r.client()
        thief = await r.client(token=TOKENS["agent-b"])
        lease = (await holder.leases_acquire([MOTION], 30_000)).lease
        other = (await thief.leases_acquire([CLAMP], 30_000)).lease  # the thief's own lease, on another resource
        sim = r.axes["a"]
        before = sim.counter

        def pulse(key: str, **kw):
            return thief.actions_invoke("a/axis-1", "pulse", {"count": 1}, operation_key=key, **kw)

        # 1. no lease at all on a resource leased by another principal (T1b, BHMS-LSE-014)
        none = await _refused(pulse("theft-1"), "LEASE_CONFLICT")
        assert none.bound == [MOTION] and lease.lease_id not in str(none) and "agent" not in none.message
        # 2. the holder's lease id (T1a, BHMS-LSE-005)
        await _refused(pulse("theft-2", lease_id=lease.lease_id), "LEASE_CONFLICT")
        # 3. a made-up lease id (T1a, BHMS-LSE-007)
        await _refused(pulse("theft-3", lease_id="lease-made-up"), "LEASE_EXPIRED")
        # 4. the id of a lease on another resource (T1a, BHMS-LSE-010: not covering)
        wrong = await _refused(pulse("theft-4", lease_id=other.lease_id), "LEASE_CONFLICT")
        assert wrong.bound == [MOTION]
        assert sim.counter == before  # the device-side counter: nothing reached the device
        assert r.gateway.journal.list(principal=None, limit=10)[0] == []  # a refusal creates no operation (OPS-040)

        # the holder, presenting its lease, is served and the upstream lease is forwarded (BHMS-LSE-011)
        op = (await holder.actions_invoke("a/axis-1", "pulse", {"count": 1}, lease_id=lease.lease_id,
                                          wait_ms=2000)).operation
        assert op.state == "completed" and op.lease_id == lease.lease_id and op.fence == lease.fence
        upstream = next(row.record for row in r.servers["a"].store.list_operations(principal=None, limit=10))
        assert upstream["leaseId"] == r.gateway.leases.upstream_lease_id(lease.lease_id, "a")
        assert sim.counter == before + 1
        # even the holder must present the lease: the rule does not depend on who asks (BHMS-LSE-014)
        await _refused(holder.actions_invoke("a/axis-1", "pulse", {"count": 1}), "LEASE_CONFLICT")
        # once the lease ends, the resource is free again
        await holder.leases_release(lease.lease_id)
        assert (await thief.actions_invoke("a/axis-1", "pulse", {"count": 1}, wait_ms=2000)).operation.state == "completed"


async def test_a_supplied_lease_is_validated_for_an_action_without_resources_too(tmp_path):
    """BHMS-LSE-007 is unconditional: an unknown lease id is refused even when the action uses no resource."""
    async with rig(tmp_path) as r:  # helpers.devices: axis-1 with a resource-free ``ping``-like read action
        client = await r.client()
        description = (await client.devices_describe("a/axis-1")).description
        free = next((n for n, a in description.actions.items() if not a.resources), None)
        if free is None:
            pytest.skip("the helper device has no resource-free action")
        await _refused(client.actions_invoke("a/axis-1", free, {}, lease_id="lease-made-up"), "LEASE_EXPIRED")


async def test_a_held_lease_blocks_non_holders_at_the_device_server(tmp_path):
    srv, sim = conformance_build(state_dir=str(tmp_path))
    await srv.listen(f"unix:{tmp_path}/dev.sock")
    client = await Client.connect(f"unix:{tmp_path}/dev.sock")
    try:
        lease = (await client.leases_acquire(["axis-1/motion"], 30_000)).lease
        before = sim.counter
        refused = await _refused(client.actions_invoke("axis-1", "pulse", {"count": 1}), "LEASE_CONFLICT")
        assert refused.bound == ["axis-1/motion"] and refused.field == "leaseId"
        assert "leaseId" in refused.hint and lease.lease_id not in str(refused)
        assert sim.counter == before
        done = (await client.actions_invoke("axis-1", "pulse", {"count": 1}, lease_id=lease.lease_id,
                                            wait_ms=2000)).operation
        assert done.state == "completed" and done.lease_id == lease.lease_id
        # an action on another resource of the same device is not affected
        other = (await client.leases_acquire(["axis-1/clamp"], 30_000)).lease
        assert (await client.actions_invoke("axis-1", "clamp", {"force": 1}, lease_id=other.lease_id,
                                            wait_ms=2000)).operation.state == "completed"
        # a read-only action without resources is not affected, and stop stays lease-free (BHMS-AUTH-020)
        stops = (await client.stop("test", device_ids=["axis-1"])).stops
        assert stops[0].outcome in ("confirmed", "initiated")
    finally:
        await client.close()
        await srv.close()


async def test_a_queued_operation_is_rejected_when_a_lease_appears_before_dispatch(tmp_path):
    """BHMS-LSE-014 is checked again immediately before dispatch, like BHMS-LSE-010."""
    srv, sim = conformance_build(state_dir=str(tmp_path))
    await srv.listen(f"unix:{tmp_path}/dev.sock")
    client = await Client.connect(f"unix:{tmp_path}/dev.sock")
    try:
        running = (await client.actions_invoke("axis-1", "slow_move", {"duration_ms": 300})).operation
        queued = (await client.actions_invoke("axis-1", "pulse", {"count": 1})).operation
        assert queued.state == "accepted"
        before = sim.counter
        lease = (await client.leases_acquire(["axis-1/motion"], 30_000)).lease
        assert lease.state == "active"
        final = (await client.operations_wait(queued.operation_id, 5000)).operation
        assert final.state == "rejected" and final.error.bhms_code == "LEASE_CONFLICT" and final.effect == "none"
        assert (await client.operations_wait(running.operation_id, 5000)).operation.state == "completed"
        assert sim.counter == before  # slow_move had already counted; pulse never reached the device
    finally:
        await client.close()
        await srv.close()


async def test_a_program_step_runs_under_the_program_lease_and_is_blocked_by_a_foreign_one(tmp_path):
    """A step that does not require a lease still presents the program's lease when it covers the step's resources, and
    is refused (the program fails, nothing dispatched) when another holder leases them."""
    srv, sim = conformance_build(state_dir=str(tmp_path))
    await srv.listen(f"unix:{tmp_path}/dev.sock")
    client = await Client.connect(f"unix:{tmp_path}/dev.sock")
    try:
        def program(*steps):
            return {"bhmsProgram": "2026-11-13", "name": "p", "description": "p", "maxDurationMs": 70_000,
                    "input": {"type": "object", "additionalProperties": False, "properties": {}}, "steps": list(steps)}

        pulse = {"kind": "invoke", "deviceId": "axis-1", "action": "pulse", "arguments": {"count": 1}}
        guard = {"kind": "invoke", "deviceId": "axis-1", "action": "guard_finish", "arguments": {"duration_ms": 5}}
        lease = (await client.leases_acquire(["axis-1/motion"], 30_000)).lease
        ok = (await client.programs_run(arguments={}, program=program(guard, pulse), lease_id=lease.lease_id,
                                        wait_ms=10_000)).operation
        assert ok.state == "completed", ok
        before = sim.counter
        blocked = (await client.programs_run(arguments={}, program=program(pulse), wait_ms=10_000)).operation
        assert blocked.state == "failed" and blocked.error.bhms_code == "LEASE_CONFLICT"
        assert sim.counter == before
    finally:
        await client.close()
        await srv.close()


async def test_the_bridge_explains_a_conflict_with_its_own_lease(tmp_path):
    """An agent whose earlier lease-requiring operation still runs is told so (not "another principal")."""
    from bhms.bridges.core import AgentBridge

    srv, _sim = conformance_build(state_dir=str(tmp_path))
    await srv.listen(f"unix:{tmp_path}/dev.sock")
    client = await Client.connect(f"unix:{tmp_path}/dev.sock")
    bridge = AgentBridge(client)
    try:
        first = await bridge.call("bhms_invoke", {"device_id": "axis-1", "action": "guard_finish",
                                                  "arguments": {"duration_ms": 400}, "wait_ms": 0})
        assert not first.is_error
        second = await bridge.call("bhms_invoke", {"device_id": "axis-1", "action": "pulse", "arguments": {"count": 1}})
        assert second.error["bhmsCode"] == "LEASE_CONFLICT"
        assert "your own earlier operation" in second.error["hint"] and "another principal" not in second.error["hint"]
        await asyncio.sleep(0.6)
    finally:
        await bridge.aclose()
        await client.close()
        await srv.close()


async def test_a_program_whose_lease_covers_only_part_of_a_step_is_refused_before_it_starts(tmp_path):
    """Fix round 1: a non-lease step that touches a resource the program's own lease holds runs under that lease, so the
    lease must cover all of the step's resources; the refusal names the step instead of a conflict with nobody."""
    from bhms import DeviceServer

    srv = DeviceServer("cell", state_dir=str(tmp_path))
    dev = srv.device("cell-1", name="Cell", resources=["cell-1/arm", "cell-1/zone"])
    dev.report_alive()
    ran = []

    @dev.action(effect="reversible", idempotency="relative", max_duration_ms=1000, resources=["cell-1/arm", "cell-1/zone"])
    async def reach(ctx) -> None:
        ran.append("reach")

    @dev.action(effect="reversible", idempotency="relative", max_duration_ms=1000, resources=["cell-1/arm"])
    async def nudge(ctx) -> None:
        ran.append("nudge")

    await srv.listen(f"unix:{tmp_path}/c.sock")
    client = await Client.connect(f"unix:{tmp_path}/c.sock")
    try:
        def program(*actions):
            return {"bhmsProgram": "2026-11-13", "name": "p", "description": "p", "maxDurationMs": 10_000,
                    "input": {"type": "object", "additionalProperties": False, "properties": {}},
                    "steps": [{"kind": "invoke", "deviceId": "cell-1", "action": a, "arguments": {}} for a in actions]}

        arm = (await client.leases_acquire(["cell-1/arm"], 30_000)).lease
        refused = await _refused(client.programs_run(arguments={}, program=program("nudge", "reach"), lease_id=arm.lease_id),
                                 "LEASE_CONFLICT")
        assert refused.field == "leaseId" and refused.bound == ["cell-1/zone"]
        assert "program.steps[1]" in refused.message and "reach" in refused.message and "cell-1/zone" in refused.hint
        assert ran == []  # refused whole, before the first step (BHMS-PRG-001)
        ok = (await client.programs_run(arguments={}, program=program("nudge"), lease_id=arm.lease_id, wait_ms=5000)).operation
        assert ok.state == "completed" and ran == ["nudge"]
        await client.leases_release(arm.lease_id)
        both = (await client.leases_acquire(["cell-1/arm", "cell-1/zone"], 30_000)).lease
        ok = (await client.programs_run(arguments={}, program=program("nudge", "reach"), lease_id=both.lease_id,
                                        wait_ms=5000)).operation
        assert ok.state == "completed" and ran == ["nudge", "nudge", "reach"]
    finally:
        await client.close()
        await srv.close()
