"""The stop fast path (BHMS-AUTH-020..026, SEC-040/041, OPS-042)."""

from __future__ import annotations

import asyncio
import logging
import time

import pytest

from bhms import DeviceServer, Policy, token_digest
from bhms.client.client import Client
from bhms.protocol import types
from bhms.protocol.errors import BhmsError
from bhms.server.decorators import DescriptionError
from bhms.server.device import Device
from pydantic import ValidationError
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


async def test_close_ends_a_stop_procedure_that_never_reports_and_records_it(tmp_path):  # BHMS-AUTH-024
    """A stop procedure still running when the server closes is waited for (bounded), then abandoned: its task ends with the
    server (none is left pending on a closed event loop) and the abandonment is recorded, since the device may or may not
    have stopped."""
    srv = DeviceServer("hung-stop", state_dir=tmp_path)
    dev = srv.device("press", resources=["press"])
    entered = asyncio.Event()

    @dev.on_stop(evidence="measured")
    async def halt(ctx):
        entered.set()
        await asyncio.Event().wait()

    listener = await srv.listen(f"unix:{tmp_path}/h.sock")
    srv.stopper.close_timeout = 0.2
    seen: list[dict] = []
    srv.events.listen(lambda event, seq: seen.append(event))
    client = await Client.connect(f"unix:{tmp_path}/h.sock")
    try:
        stop = (await client.stop("stop now", device_ids=["press"], wait_ms=50)).stops[0]
        assert stop.outcome == "initiated" and entered.is_set()
        tasks = list(srv.stopper.tasks)
        assert tasks
    finally:
        await client.close()
        await listener.close()
    start = time.monotonic()
    await srv.close()
    assert time.monotonic() - start < 2.0
    assert all(t.done() for t in tasks) and not srv.stopper.tasks
    abandoned = [e for e in seen if e["type"] == "stop" and e["data"]["outcome"] == "failed"]
    assert len(abandoned) == 1 and abandoned[0]["deviceId"] == "press", seen
    assert "closed" in abandoned[0]["message"] and "may" in abandoned[0]["message"]


async def _stop_then_close(tmp_path, halt_body, *, max_duration_ms, **server_kw):
    """Serve one device whose stop procedure is ``halt_body``, stop it, close the server at once; return (seconds the
    close took, the stop events recorded, the procedure's log)."""
    srv = DeviceServer("closing", state_dir=tmp_path, **server_kw)
    dev = srv.device("press", resources=["press"])
    log: list[str] = []

    @dev.on_stop(evidence="measured", max_duration_ms=max_duration_ms)
    async def halt(ctx):
        await halt_body(log)

    listener = await srv.listen(f"unix:{tmp_path}/c.sock")
    srv.stopper.close_timeout = 0.2
    seen: list[dict] = []
    srv.events.listen(lambda event, seq: seen.append(event))
    client = await Client.connect(f"unix:{tmp_path}/c.sock")
    try:
        assert (await client.stop("stop now", device_ids=["press"], wait_ms=50)).stops[0].outcome == "initiated"
    finally:
        await client.close()
        await listener.close()
    start = time.monotonic()
    await srv.close()
    return time.monotonic() - start, [e for e in seen if e["type"] == "stop"], log


async def test_close_lets_a_stop_finish_within_its_declared_bound(tmp_path):  # BHMS-AUTH-024
    """A ramp-down that takes longer than the server's own close wait but stays inside the device's declared stop bound
    is never cut by a server shutdown: it finishes and its confirmation is recorded."""
    async def ramp(log):
        log.append("ramp start")
        try:
            await asyncio.sleep(1.2)
            log.append("ramp done")
        except asyncio.CancelledError:
            log.append("ramp cancelled")
            raise

    took, events, log = await _stop_then_close(tmp_path, ramp, max_duration_ms=3000)
    assert log == ["ramp start", "ramp done"]
    assert 1.0 < took < 2.5
    assert [e["data"]["outcome"] for e in events] == ["initiated", "confirmed"]


async def test_close_ends_a_hung_stop_after_its_declared_bound(tmp_path):  # BHMS-AUTH-024
    async def hung(log):
        log.append("start")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            log.append("cancelled")
            raise

    took, events, log = await _stop_then_close(tmp_path, hung, max_duration_ms=1000)
    assert log == ["start", "cancelled"]
    assert 0.8 < took < 2.0  # the bound runs from when the stop began, not from the close
    assert [e["data"]["outcome"] for e in events] == ["initiated", "failed"]
    assert "closed before the stop procedure reported" in events[-1]["message"]


async def _ramp(log):
    log.append("ramp start")
    await asyncio.sleep(0.6)
    log.append("ramp done")


async def _hung(log):
    log.append("start")
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        log.append("cancelled")
        raise


async def test_close_says_which_stop_it_waits_for_when_it_waits_past_close_timeout(tmp_path, caplog):  # Task 12b
    """A shutdown that waits longer than ``close_timeout`` for a stop says so at WARNING, naming the device and its bound:
    an operator (or a supervisor's log) sees why the process has not exited."""
    caplog.set_level(logging.WARNING, logger="bhms.stop")
    took, events, log = await _stop_then_close(tmp_path, _ramp, max_duration_ms=3000)
    assert log == ["ramp start", "ramp done"] and [e["data"]["outcome"] for e in events] == ["initiated", "confirmed"]
    waits = [r for r in caplog.records if r.levelno == logging.WARNING and "press" in r.getMessage()]
    assert len(waits) == 1 and "3000 ms" in waits[0].getMessage(), [r.getMessage() for r in caplog.records]


async def test_close_does_not_warn_when_it_waits_no_longer_than_close_timeout(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="bhms.stop")
    took, events, log = await _stop_then_close(tmp_path, _ramp, max_duration_ms=100)
    assert not [r for r in caplog.records if r.name == "bhms.stop"]


async def test_close_honours_its_ceiling_and_records_the_stop_it_ends(tmp_path, caplog):  # Task 12b, BHMS-AUTH-024
    """A declared bound can be up to a day; a supervisor kills a process long before that. With a ceiling below the bound,
    close waits until the ceiling, logs an ERROR naming the device, ends the procedure and records the ``failed`` stop
    event, so the outcome is on record before any kill."""
    caplog.set_level(logging.WARNING, logger="bhms.stop")
    took, events, log = await _stop_then_close(tmp_path, _hung, max_duration_ms=60_000, stop_shutdown_ceiling_s=0.5)
    assert log == ["start", "cancelled"]
    assert 0.4 < took < 2.0
    assert [e["data"]["outcome"] for e in events] == ["initiated", "failed"]
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1 and "press" in errors[0] and "60000 ms" in errors[0] and "0.5 s" in errors[0], errors


def test_the_shutdown_ceiling_must_be_positive(tmp_path):
    with pytest.raises(ValueError, match="stop_shutdown_ceiling_s"):
        DeviceServer("bad", state_dir=tmp_path, stop_shutdown_ceiling_s=0)


def test_a_stop_bound_is_at_most_one_day():  # Task 12b: stopMaxDurationMs is capped like a program's maxDurationMs
    dev = Device(None, "press", resources=["press"])
    for bad in (86_400_001, -1, 1.5):
        with pytest.raises(DescriptionError, match="max_duration_ms"):
            dev.on_stop(lambda ctx: None, evidence="measured", max_duration_ms=bad)
    dev.on_stop(lambda ctx: None, evidence="measured", max_duration_ms=86_400_000)
    assert dev.description()["safety"]["stopMaxDurationMs"] == 86_400_000
    safety = {"stop": "supported", "stopEvidence": "measured", "onDisconnect": "stop", "summary": "s",
              "stopMaxDurationMs": 86_400_001}
    with pytest.raises(ValidationError):
        types.parse("SafetyDescription", safety)


async def test_a_ceiling_below_close_timeout_also_reports_unbounded_procedures(tmp_path, caplog):  # fix round 1
    caplog.set_level(logging.WARNING, logger="bhms.stop")
    srv = DeviceServer("closing", state_dir=tmp_path, stop_shutdown_ceiling_s=0.3)
    dev = srv.device("press", resources=["press"])
    log: list[str] = []

    @dev.on_stop(evidence="measured")  # no declared bound
    async def halt(ctx):
        await _hung(log)

    listener = await srv.listen(f"unix:{tmp_path}/c.sock")
    seen: list[dict] = []
    srv.events.listen(lambda event, seq: seen.append(event))
    client = await Client.connect(f"unix:{tmp_path}/c.sock")
    try:
        assert (await client.stop("stop now", device_ids=["press"], wait_ms=50)).stops[0].outcome == "initiated"
    finally:
        await client.close()
        await listener.close()
    start = time.monotonic()
    await srv.close()  # close_timeout is 5 s; the ceiling, 0.3 s, wins
    assert time.monotonic() - start < 2.0 and log == ["start", "cancelled"]
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1 and "press" in errors[0] and "no declared bound" in errors[0], errors
    assert [e["data"]["outcome"] for e in seen if e["type"] == "stop"] == ["initiated", "failed"]
