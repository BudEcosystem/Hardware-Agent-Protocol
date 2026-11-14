"""Leases, fencing and lease contention over WebSocket with two principals (BHMS-LSE-0xx, OPS-033, OPS-041)."""

from __future__ import annotations

import asyncio

import pytest

from bhms import Canceled, DeviceServer, Policy, Range, token_digest
from bhms.client.client import Client
from bhms.protocol.errors import BhmsError

TOKENS = {"alice": "alice-token", "bob": "bob-token"}
SCOPES = ["read", "lease", "invoke:arm-1/*", "invoke:arm-1/swing", "stop"]  # hazardous needs a literal


def build(state_dir, **kw):
    policy = Policy({name: {"tokens": [token_digest(t)], "scopes": SCOPES} for name, t in TOKENS.items()})
    srv = DeviceServer("lease-server", state_dir=state_dir, policy=policy, lease_min_ttl_ms=50,
                       lease_max_ttl_ms=60_000, lease_max_wait_ms=5_000, **kw)
    state = {"moves": 0, "holds": 0, "gate": asyncio.Event()}
    arm = srv.device("arm-1", resources=["arm-1/motion", "arm-1/gripper"])
    arm.report_alive()

    async def gated(ctx):
        state["moves"] += 1
        waiter = asyncio.ensure_future(state["gate"].wait())
        cancel = asyncio.ensure_future(ctx.cancelled.wait())
        await asyncio.wait({waiter, cancel}, return_when=asyncio.FIRST_COMPLETED)
        waiter.cancel()
        cancel.cancel()
        if ctx.cancelled.is_set() and not state["gate"].is_set():
            raise Canceled(effect="unverified", detail=ctx.cancel_reason)

    @arm.action(effect="reversible", idempotency="absolute", requires_lease=True, max_duration_ms=10_000,
                resources=["arm-1/motion"], on_lease_loss="finish", cancel="supported")
    async def move(ctx, x: Range(0, 100, unit="mm")) -> None:
        await gated(ctx)

    @arm.action(effect="reversible", idempotency="absolute", requires_lease=True, max_duration_ms=10_000,
                resources=["arm-1/motion"], on_lease_loss="cancel", cancel="supported")
    async def move_careful(ctx) -> None:
        await gated(ctx)

    @arm.on_hold
    async def hold(ctx):
        state["holds"] += 1

    @arm.action(effect="hazardous", idempotency="absolute", requires_lease=True, max_duration_ms=10_000,
                resources=["arm-1/motion"], on_lease_loss="hold", cancel="supported")
    async def swing(ctx) -> None:
        await gated(ctx)

    @arm.action(effect="reversible", idempotency="toggle", requires_lease=True, max_duration_ms=1000,
                resources=["arm-1/gripper"])
    async def grip(ctx) -> None:
        state["moves"] += 1

    return srv, state


@pytest.fixture
async def env(tmp_path):
    made = []

    async def make(state_dir=None, **kw):
        srv, state = build(state_dir or tmp_path / f"st{len(made)}", **kw)
        listener = await srv.listen("ws://127.0.0.1:0")
        url = f"ws://127.0.0.1:{listener.address[1]}"
        clients = {name: await Client.connect(url, token=t) for name, t in TOKENS.items()}
        made.append((srv, listener, clients))
        return srv, state, clients

    yield make
    for srv, listener, clients in made:
        for c in clients.values():
            await c.close()
        await listener.close()
        await srv.close()


async def refused(coro) -> BhmsError:
    with pytest.raises(BhmsError) as info:
        await coro
    return info.value


async def test_acquire_is_all_or_nothing_and_holds_nothing_while_waiting(env):  # BHMS-LSE-001
    srv, state, c = await env()
    grip = (await c["bob"].leases_acquire(["arm-1/gripper"], 2000)).lease
    waiting = asyncio.ensure_future(c["alice"].leases_acquire(["arm-1/motion", "arm-1/gripper"], 2000, wait_ms=3000))
    await asyncio.sleep(0.1)
    motion = (await c["bob"].leases_acquire(["arm-1/motion"], 2000)).lease  # motion is not held by the waiter
    await c["bob"].leases_release(motion.lease_id)
    await c["bob"].leases_release(grip.lease_id)
    got = (await waiting).lease
    assert got.state == "active" and sorted(got.resources) == ["arm-1/gripper", "arm-1/motion"]


async def test_contention_exactly_one_wins_and_the_loser_learns_what_and_when(env):  # BHMS-LSE-002 (Focus 5)
    srv, state, c = await env()
    results = await asyncio.gather(c["alice"].leases_acquire(["arm-1/motion"], 3000),
                                   c["bob"].leases_acquire(["arm-1/motion"], 3000), return_exceptions=True)
    winners = [r for r in results if not isinstance(r, Exception)]
    losers = [r for r in results if isinstance(r, BhmsError)]
    assert len(winners) == 1 and len(losers) == 1
    err = losers[0]
    assert err.bhms_code == "LEASE_CONFLICT" and err.bound == ["arm-1/motion"] and "expires in" in err.hint
    assert "alice" not in err.hint + err.message and "bob" not in err.hint + err.message


async def test_fences_increase_across_acquires_and_restarts_and_renew_keeps_it(env, tmp_path):  # BHMS-LSE-003
    state_dir = tmp_path / "fence"
    srv, state, c = await env(state_dir)
    a = (await c["alice"].leases_acquire(["arm-1/motion"], 1000)).lease
    renewed = (await c["alice"].leases_renew(a.lease_id, 2000)).lease
    assert renewed.fence == a.fence and renewed.ttl_ms == 2000
    await c["alice"].leases_release(a.lease_id)
    b = (await c["alice"].leases_acquire(["arm-1/motion"], 1000)).lease
    assert b.fence > a.fence
    for client in c.values():
        await client.close()
    await srv.close()
    srv2, _, c2 = await env(state_dir)
    after = (await c2["alice"].leases_acquire(["arm-1/motion"], 1000)).lease
    assert after.fence > b.fence
    err = await refused(c2["alice"].leases_renew(b.lease_id, 1000))  # forgotten across the restart
    assert err.bhms_code == "LEASE_EXPIRED"


async def test_lease_parameter_bounds(env):  # BHMS-LSE-004
    srv, state, c = await env()
    for ttl in (10, 120_000):
        err = await refused(c["alice"].leases_acquire(["arm-1/motion"], ttl))
        assert (err.bhms_code, err.field) == ("OUT_OF_RANGE", "ttlMs")
    err = await refused(c["alice"].leases_acquire(["arm-1/motion"], 1000, wait_ms=10_000))
    assert (err.bhms_code, err.field) == ("OUT_OF_RANGE", "waitMs")
    err = await refused(c["alice"].leases_acquire(["arm-1/motion", "arm-1/gripper", "arm-9"], 1000))
    assert (err.bhms_code, err.field) == ("INVALID_ARGUMENT", "resources[2]")


async def test_a_lease_belongs_to_its_principal(env):  # BHMS-LSE-005
    srv, state, c = await env()
    lease = (await c["alice"].leases_acquire(["arm-1/motion"], 3000)).lease
    for call in (c["bob"].leases_renew(lease.lease_id, 1000), c["bob"].leases_release(lease.lease_id),
                 c["bob"].actions_invoke("arm-1", "move", {"x": 1}, lease_id=lease.lease_id)):
        err = await refused(call)
        assert err.bhms_code == "LEASE_CONFLICT"
    assert state["moves"] == 0


async def test_expiry_renew_release_and_unknown_ids(env):  # BHMS-LSE-006, LSE-007
    srv, state, c = await env()
    lease = (await c["alice"].leases_acquire(["arm-1/motion"], 60)).lease
    await asyncio.sleep(0.15)
    assert (await refused(c["alice"].leases_renew(lease.lease_id, 1000))).bhms_code == "LEASE_EXPIRED"
    released = (await c["alice"].leases_release(lease.lease_id)).lease
    assert released.state == "expired"  # not active: returned unchanged
    assert (await refused(c["alice"].leases_renew("lease-fabricated", 1000))).bhms_code == "LEASE_EXPIRED"
    events = (await c["alice"].events_read(types=["lease.expired"])).events
    assert events and events[-1].data == {"leaseId": lease.lease_id}


async def test_invoke_lease_refusals_never_dispatch(env):  # BHMS-LSE-010
    srv, state, c = await env()
    assert (await refused(c["alice"].actions_invoke("arm-1", "move", {"x": 1}))).bhms_code == "LEASE_REQUIRED"
    assert (await refused(c["alice"].actions_invoke("arm-1", "move", {"x": 1}, lease_id="lease-nope"))
            ).bhms_code == "LEASE_EXPIRED"
    released = (await c["alice"].leases_acquire(["arm-1/motion"], 3000)).lease
    await c["alice"].leases_release(released.lease_id)
    assert (await refused(c["alice"].actions_invoke("arm-1", "move", {"x": 1}, lease_id=released.lease_id))
            ).bhms_code == "LEASE_EXPIRED"
    grip = (await c["alice"].leases_acquire(["arm-1/gripper"], 3000)).lease
    err = await refused(c["alice"].actions_invoke("arm-1", "move", {"x": 1}, lease_id=grip.lease_id))
    assert err.bhms_code == "LEASE_CONFLICT" and err.bound == ["arm-1/motion"]  # does not cover
    motion = (await c["alice"].leases_acquire(["arm-1/motion"], 3000)).lease
    await c["bob"].stop("test", device_ids=["arm-1"])  # revokes every lease on the device
    assert (await refused(c["alice"].actions_invoke("arm-1", "move", {"x": 1}, lease_id=motion.lease_id))
            ).bhms_code == "FENCED"
    assert (await refused(c["alice"].leases_renew(motion.lease_id, 1000))).bhms_code == "FENCED"
    assert state["moves"] == 0


async def test_lease_expiring_before_dispatch_rejects(env):  # BHMS-OPS-041
    srv, state, c = await env()
    lease = (await c["alice"].leases_acquire(["arm-1/motion"], 300)).lease
    first = (await c["alice"].actions_invoke("arm-1", "move", {"x": 1}, lease_id=lease.lease_id,
                                             operation_key="e-1")).operation
    queued = (await c["alice"].actions_invoke("arm-1", "move", {"x": 2}, lease_id=lease.lease_id,
                                              operation_key="e-2")).operation
    assert queued.state == "accepted"
    await asyncio.sleep(0.4)  # the lease expires while e-2 is queued
    state["gate"].set()
    done = (await c["alice"].operations_wait(queued.operation_id, 2000)).operation
    assert done.state == "rejected" and done.error.bhms_code == "LEASE_EXPIRED" and done.effect == "none"
    finished = (await c["alice"].operations_wait(first.operation_id, 2000)).operation
    assert finished.state == "completed"  # onLeaseLoss finish
    assert state["moves"] == 1


async def test_same_key_retry_after_lease_expiry_returns_the_original(env):  # BHMS-OPS-033
    srv, state, c = await env()
    state["gate"].set()
    lease = (await c["alice"].leases_acquire(["arm-1/motion"], 100)).lease
    op = (await c["alice"].actions_invoke("arm-1", "move", {"x": 3}, lease_id=lease.lease_id, operation_key="r-1",
                                          wait_ms=1000)).operation
    await asyncio.sleep(0.2)
    again = await c["alice"].actions_invoke("arm-1", "move", {"x": 3}, lease_id=lease.lease_id, operation_key="r-1")
    assert again.replayed and again.operation.operation_id == op.operation_id and state["moves"] == 1


@pytest.mark.parametrize("action, expect", [("move", "completed"), ("move_careful", "canceled"),
                                            ("swing", "failed")])
async def test_on_lease_loss_policies(env, action, expect):  # BHMS-LSE-012
    srv, state, c = await env()
    lease = (await c["alice"].leases_acquire(["arm-1/motion"], 150)).lease
    op = (await c["alice"].actions_invoke("arm-1", action, {"x": 1} if action == "move" else {},
                                          lease_id=lease.lease_id, operation_key=f"l-{action}")).operation
    await asyncio.sleep(0.3)  # the lease expires while the action runs
    if action == "move":
        state["gate"].set()
    done = (await c["alice"].operations_wait(op.operation_id, 3000)).operation
    assert done.state == expect
    kinds = [h.kind for h in done.history]
    assert "lease" in kinds
    if action == "swing":
        assert done.error.bhms_code == "LEASE_EXPIRED" and done.error.may_have_acted and state["holds"] == 1
    # no new operation starts under the expired lease
    err = await refused(c["alice"].actions_invoke("arm-1", action, {"x": 1} if action == "move" else {},
                                                  lease_id=lease.lease_id))
    assert err.bhms_code == "LEASE_EXPIRED"


async def test_hazardous_action_needs_a_literal_invoke_scope(env):  # BHMS-AUTH-003
    srv, state, c = await env()
    srv.set_policy(Policy({name: {"tokens": [token_digest(t)], "scopes": ["read", "lease", "invoke:arm-1/*"]}
                           for name, t in TOKENS.items()}))
    lease = (await c["alice"].leases_acquire(["arm-1/motion"], 3000)).lease
    err = await refused(c["alice"].actions_invoke("arm-1", "swing", {}, lease_id=lease.lease_id))
    assert err.bhms_code == "UNAUTHORIZED" and "invoke:arm-1/swing" in err.hint
