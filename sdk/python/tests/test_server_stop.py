"""The stop fast path (BHMS-AUTH-020..026, SEC-040/041, OPS-042)."""

from __future__ import annotations

import asyncio
import time

import pytest

from bhms import DeviceServer, Policy, token_digest
from bhms.client.client import Client
from bhms.protocol import types
from bhms.protocol.errors import BhmsError
from helpers.devices import build, connect, serve


@pytest.fixture
async def env(tmp_path):
    made = []

    async def make(**kw):
        srv, axis = build(tmp_path / f"st{len(made)}", **kw)
        url, listener = await serve(srv, tmp_path, name=f"s{len(made)}.sock")
        client = await connect(url)
        made.append((srv, listener, [client]))
        return srv, axis, client, url, made[-1][2]

    yield make
    for srv, listener, clients in made:
        for c in clients:
            await c.close()
        await listener.close()
        await srv.close()


async def test_stop_runs_the_procedure_and_requests_cancellation_of_running_work(env):  # BHMS-AUTH-021
    srv, axis, client, url, _ = await env()
    running = (await client.actions_invoke("axis-1", "slow", {}, operation_key="run")).operation
    res = await client.stop("operator pressed stop", device_ids=["axis-1"], wait_ms=1000)
    stop = res.stops[0]
    types.DeviceStop.model_validate(types.to_wire(stop))
    assert (stop.outcome, stop.evidence) == ("confirmed", "reported") and axis.stops == 1
    assert running.operation_id in stop.cancel_requested_operations
    done = (await client.operations_wait(running.operation_id, 2000)).operation
    assert done.state in ("completed", "canceled")  # the stop procedure opened the gate: completion may win
    kinds = [h.kind for h in done.history]
    assert "stop" in kinds and "cancel" in kinds
    events = (await client.events_read(types=["stop"])).events
    assert events and events[0].device_id == "axis-1" and events[0].data["reason"] == "operator pressed stop"


async def test_stop_cancels_queued_operations_and_revokes_leases(env):  # BHMS-AUTH-021
    srv, axis, client, url, _ = await env()
    lease = (await client.leases_acquire(["axis-1"], 5000)).lease
    held = {"lease_id": lease.lease_id}  # work on a leased resource presents the lease (BHMS-LSE-014)
    first = (await client.actions_invoke("axis-1", "slow", {}, operation_key="a", **held)).operation
    queued = (await client.actions_invoke("axis-1", "move_to", {"target": 1}, operation_key="b", **held)).operation
    assert queued.state == "accepted"
    stop = (await client.stop("clear the cell", device_ids=["axis-1"], wait_ms=1000)).stops[0]
    assert queued.operation_id in stop.canceled_operations and stop.revoked_leases == [lease.lease_id]
    canceled = (await client.operations_get(queued.operation_id)).operation
    assert (canceled.state, canceled.effect) == ("canceled", "none")
    await client.operations_wait(first.operation_id, 2000)
    assert axis.commands["move_to"] == 0
    revoked = (await client.events_read(types=["lease.revoked"])).events
    assert revoked[-1].data == {"leaseId": lease.lease_id}


async def test_confirmed_stop_lifts_the_unknown_inhibition(env):  # BHMS-OPS-042
    srv, axis, client, url, _ = await env()
    op = (await client.actions_invoke("axis-1", "explode", {}, wait_ms=1000)).operation
    err = None
    try:
        await client.actions_invoke("axis-1", "move_to", {"target": 1})
    except BhmsError as exc:
        err = exc
    assert err is not None and err.bhms_code == "STALE"
    stop = (await client.stop("reset", device_ids=["axis-1"], wait_ms=1000)).stops[0]
    assert op.operation_id in stop.cancel_requested_operations
    ok = (await client.actions_invoke("axis-1", "move_to", {"target": 1}, wait_ms=2000)).operation
    assert ok.state == "completed"
    unknown = (await client.operations_get(op.operation_id)).operation
    assert unknown.state == "unknown" and unknown.cancel.state == "requested"  # recorded; outcome still unknown
    assert [h.kind for h in unknown.history].count("stop") == 2  # the stop entry and the lifted inhibition


async def test_stop_with_unknown_device_does_not_fail_the_request(env):  # BHMS-AUTH-023
    srv, axis, client, url, _ = await env()
    stops = (await client.stop("test", device_ids=["axis-1", "ghost"], wait_ms=1000)).stops
    by_id = {s.device_id: s for s in stops}
    assert by_id["axis-1"].outcome == "confirmed"
    assert by_id["ghost"].outcome == "failed" and by_id["ghost"].error.bhms_code == "UNKNOWN_DEVICE"


async def test_scope_all_and_unsupported_devices(tmp_path):  # BHMS-AUTH-021, DEV-060
    srv = DeviceServer("plain", state_dir=tmp_path)
    srv.device("lamp", resources=["lamp"])
    srv.device("fan", resources=["fan"])
    listener = await srv.listen(f"unix:{tmp_path}/p.sock")
    client = await Client.connect(f"unix:{tmp_path}/p.sock")
    try:
        stops = (await client.stop("everything", scope="all")).stops
        assert [(s.device_id, s.outcome, s.evidence) for s in stops] == [("fan", "unsupported", "none"),
                                                                         ("lamp", "unsupported", "none")]
    finally:
        await client.close()
        await listener.close()
        await srv.close()


async def test_stop_returns_initiated_promptly_and_reports_later(tmp_path):  # BHMS-AUTH-022, AUTH-024
    srv = DeviceServer("slow-stop", state_dir=tmp_path)
    dev = srv.device("press", resources=["press"])
    release = asyncio.Event()

    @dev.on_stop(evidence="measured")
    async def halt(ctx):
        await release.wait()

    listener = await srv.listen(f"unix:{tmp_path}/p.sock")
    client = await Client.connect(f"unix:{tmp_path}/p.sock")
    try:
        start = time.monotonic()
        stop = (await client.stop("stop now", device_ids=["press"])).stops[0]
        assert stop.outcome == "initiated" and stop.evidence == "none" and time.monotonic() - start < 0.5
        sub = await client.subscribe(events={"types": ["stop"]})
        release.set()
        item = await asyncio.wait_for(sub.__anext__(), 2)
        assert item.params.event.data == {"outcome": "confirmed", "reason": "stop now"}
        await sub.cancel()
    finally:
        await client.close()
        await listener.close()
        await srv.close()


async def test_stop_is_not_blocked_by_leases_or_a_saturated_queue(env):  # BHMS-AUTH-020
    srv, axis, client, url, _ = await env(queue_limit=8)
    held = {"lease_id": (await client.leases_acquire(["axis-1"], 60_000)).lease.lease_id}  # BHMS-LSE-014
    await client.actions_invoke("axis-1", "slow", {}, **held)
    for _ in range(8):
        await client.actions_invoke("axis-1", "move_to", {"target": 1}, **held)
    with pytest.raises(BhmsError) as busy:
        await client.actions_invoke("axis-1", "move_to", {"target": 1}, **held)
    assert busy.value.bhms_code == "BUSY"
    start = time.monotonic()
    stop = (await client.stop("now", device_ids=["axis-1"], wait_ms=1000)).stops[0]
    assert stop.outcome == "confirmed" and time.monotonic() - start < 0.5
    assert len(stop.canceled_operations) + len(stop.cancel_requested_operations or []) == 9 and axis.commands["move_to"] == 0


async def test_stop_scope_is_independent(tmp_path):  # BHMS-SEC-040, AUTH-020
    tokens = {"stopper": "s-token", "worker": "w-token"}
    policy = Policy({"stopper": {"tokens": [token_digest(tokens["stopper"])], "scopes": ["stop:axis-*"]},
                     "worker": {"tokens": [token_digest(tokens["worker"])], "scopes": ["read", "invoke:*/*"]}})
    srv, axis = build(tmp_path, policy=policy)
    listener = await srv.listen("ws://127.0.0.1:0")
    url = f"ws://127.0.0.1:{listener.address[1]}"
    stopper = await Client.connect(url, token=tokens["stopper"])
    worker = await Client.connect(url, token=tokens["worker"])
    try:
        with pytest.raises(BhmsError) as info:
            await worker.stop("no", device_ids=["axis-1"])
        assert info.value.bhms_code == "UNAUTHORIZED"
        with pytest.raises(BhmsError) as info:
            await stopper.actions_invoke("axis-1", "move_to", {"target": 1})
        assert info.value.bhms_code == "UNKNOWN_DEVICE"  # no read scope: the device is not even visible
        stop = (await stopper.stop("yes", device_ids=["axis-1"], wait_ms=1000)).stops[0]
        assert stop.outcome == "confirmed"
    finally:
        await stopper.close()
        await worker.close()
        await listener.close()
        await srv.close()


async def test_stop_with_an_unwritable_journal_is_degraded_audit(env):  # BHMS-AUTH-025, SEC-041, OPS-003
    srv, axis, client, url, _ = await env()
    running = (await client.actions_invoke("axis-1", "slow", {})).operation
    srv.store.set_writable(False)
    stop = (await client.stop("journal broken", device_ids=["axis-1"], wait_ms=1000)).stops[0]
    assert stop.outcome == "confirmed" and stop.detail == "degraded-audit" and axis.stops == 1
    with pytest.raises(BhmsError) as info:
        await client.actions_invoke("axis-1", "move_to", {"target": 1})
    assert info.value.bhms_code == "BUSY" and info.value.may_have_acted is False
    assert axis.commands["move_to"] == 0
    srv.store.set_writable(True)
    ok = (await client.actions_invoke("axis-1", "move_to", {"target": 1}, wait_ms=2000)).operation
    assert ok.state == "completed"
    assert running.operation_id
