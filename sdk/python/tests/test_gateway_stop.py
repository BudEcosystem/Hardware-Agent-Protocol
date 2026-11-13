"""Gateway step 6: stop fan-out.

Spec: BHMS-AUTH-020..026, SEC-040/041, EVT-002.
"""

from __future__ import annotations

import asyncio
import os
import signal
import time

import pytest

from bhms.client.client import Client
from bhms.protocol.errors import BhmsError
from bhms.runtime.authority import token_digest
from helpers.gateway_rig import TOKENS, principals, rig
from test_gateway_isolation import HELPER, child_pid, device_log, start_gateway, stdio_upstream, until


def delay_stop(r, name, seconds):
    original = r.servers[name].rpc._handlers["stop"]

    async def slow(params, ctx):
        await asyncio.sleep(seconds)
        return await original(params, ctx)

    r.servers[name].rpc.register("stop", slow)


async def test_stop_all_reports_per_device_results_and_needs_no_other_scope(tmp_path):  # SEC-040, AUTH-020
    async with rig(tmp_path, conformance=True) as r:
        stopper = await r.client(token=TOKENS["stopper"])
        with pytest.raises(BhmsError) as exc:
            await stopper.actions_invoke("a/axis-1", "move_to", {"position": 1}, operation_key="x")
        assert exc.value.code == "UNKNOWN_DEVICE"  # with only stop it cannot even see, let alone act (AUTH-002)
        stops = (await stopper.stop("test", scope="all")).stops
        assert [(s.device_id, s.outcome) for s in stops] == [
            ("a/axis-1", "confirmed"), ("a/pump-1", "unsupported"), ("b/axis-1", "confirmed"), ("b/pump-1", "unsupported")]
        assert stops[0].evidence == "reported" and stops[1].evidence == "none"
        assert r.axes["a"].stops == 1 and r.axes["b"].stops == 1
        events = (await (await r.client(token=TOKENS["admin"])).events_read(types=["stop"])).events
        assert {e.device_id for e in events} >= {"a/axis-1", "b/axis-1"}


async def test_stop_reaches_every_upstream_concurrently(tmp_path):  # AUTH-020
    async with rig(tmp_path, names=("a", "b", "c"), conformance=True) as r:
        for name in "abc":
            delay_stop(r, name, 0.4)
        stopper = await r.client(token=TOKENS["stopper"])
        started = time.perf_counter()
        stops = (await stopper.stop("test", scope="all", wait_ms=1000)).stops
        elapsed = time.perf_counter() - started
        assert all(s.outcome in ("confirmed", "unsupported") for s in stops) and len(stops) == 6
        assert 0.35 < elapsed < 0.9, elapsed  # three 0.4 s upstreams in parallel, not in sequence


async def test_stop_returns_within_its_deadline_reporting_initiated(tmp_path):  # AUTH-024
    async with rig(tmp_path, names=("a", "b"), conformance=True, gateway_kw={"stop_deadline_ms": 300}) as r:
        delay_stop(r, "b", 2.0)
        stopper = await r.client(token=TOKENS["stopper"])
        started = time.perf_counter()
        stops = {s.device_id: s for s in (await stopper.stop("test", scope="all")).stops}
        assert time.perf_counter() - started < 1.0
        assert stops["a/axis-1"].outcome == "confirmed"
        assert stops["b/axis-1"].outcome == "initiated" and "did not answer" in stops["b/axis-1"].detail
        await asyncio.sleep(2.2)
        assert r.axes["b"].stops == 1  # the request had been sent: it ran
        events = (await (await r.client(token=TOKENS["admin"])).events_read(types=["stop"],
                                                                            device_id="b/axis-1")).events
        assert any(e.data and e.data.get("outcome") == "confirmed" for e in events)  # the late outcome is an event


async def test_unknown_and_unauthorized_devices_do_not_fail_the_request(tmp_path):  # AUTH-023
    doc = principals()
    doc["a-stopper"] = {"tokens": [token_digest("as")], "scopes": ["read", "stop:a/*"]}
    async with rig(tmp_path, conformance=True, principals_doc=doc) as r:
        client = await r.client(token="as")
        stops = {s.device_id: s for s in (await client.stop("t", device_ids=["a/axis-1", "b/axis-1", "z/none"])).stops}
        assert stops["a/axis-1"].outcome == "confirmed"
        assert stops["b/axis-1"].outcome == "failed" and stops["b/axis-1"].error.bhms_code == "UNAUTHORIZED"
        assert stops["z/none"].outcome == "failed" and stops["z/none"].error.bhms_code == "UNKNOWN_DEVICE"
        assert "scope:stop" in stops["b/axis-1"].error.hint
        assert r.axes["a"].stops == 1 and r.axes["b"].stops == 0
        wide = (await client.stop("t", scope="all")).stops  # scope all = every device this principal may stop
        assert {s.device_id for s in wide} == {"a/axis-1", "a/pump-1"}


async def test_stop_cancels_operations_and_revokes_leases_everywhere(tmp_path):  # AUTH-021
    async with rig(tmp_path, conformance=True) as r:
        client = await r.client()
        stopper = await r.client(token=TOKENS["stopper"])
        lease = (await client.leases_acquire(["a/axis-1/clamp", "b/pump-1/plunger"], 60000)).lease
        op = (await client.actions_invoke("a/axis-1", "slow_move", {"duration_ms": 30000}, operation_key="long")).operation
        await asyncio.sleep(0.2)
        stops = {s.device_id: s for s in (await stopper.stop("halt", device_ids=["a/axis-1", "b/pump-1"])).stops}
        assert lease.lease_id in stops["a/axis-1"].revoked_leases and lease.lease_id in stops["b/pump-1"].revoked_leases
        assert stops["a/axis-1"].cancel_requested_operations == [op.operation_id]
        assert r.gateway.leases.manager.get(lease.lease_id).state == "revoked"
        settled = await until(lambda: _settled(client, op.operation_id), timeout=5)
        assert settled.state == "canceled"
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/axis-1", "clamp", {"force": 1}, operation_key="c", lease_id=lease.lease_id)
        assert exc.value.code == "FENCED"
        assert r.servers["a"].leases.active() == [] and r.servers["b"].leases.active() == []


async def _settled(client, op_id):
    got = (await client.operations_get(op_id)).operation
    return got if got.state in ("canceled", "completed", "failed") else None


async def test_stop_is_not_held_up_by_a_saturated_upstream(tmp_path):  # AUTH-020, SEC-061
    async with rig(tmp_path, conformance=True, upstream_kw={"max_inflight": 1, "queue_size": 1}) as r:
        client = await r.client()
        stopper = await r.client(token=TOKENS["stopper"])
        direct = await Client.connect(f"unix:{tmp_path}/a.sock")
        try:
            await direct.leases_acquire(["axis-1/clamp", "axis-1/motion"], 20000)
            blockers = [asyncio.create_task(client.leases_acquire([res], 5000, wait_ms=2000))
                        for res in ("a/axis-1/clamp", "a/axis-1/motion")]  # fill the upstream's slot and queue
            await asyncio.sleep(0.3)
            started = time.perf_counter()
            stops = (await stopper.stop("now", device_ids=["a/axis-1"])).stops
            assert stops[0].outcome == "confirmed" and time.perf_counter() - started < 0.5
            await asyncio.gather(*blockers, return_exceptions=True)
        finally:
            await direct.close()


async def test_stop_works_with_an_unwritable_journal_and_says_so(tmp_path):  # AUTH-025, SEC-041
    async with rig(tmp_path, conformance=True) as r:
        client = await r.client()
        stopper = await r.client(token=TOKENS["stopper"])
        r.gateway.store.set_writable(False)
        try:
            stops = (await stopper.stop("now", device_ids=["a/axis-1"])).stops
            assert stops[0].outcome == "confirmed" and stops[0].detail == "degraded-audit" and r.axes["a"].stops == 1
            with pytest.raises(BhmsError) as exc:
                await client.actions_invoke("a/axis-1", "move_to", {"position": 1}, operation_key="j")
            assert exc.value.code == "BUSY" and "isolation:journal" in exc.value.hint
        finally:
            r.gateway.store.set_writable(True)
        assert (await client.actions_invoke("a/axis-1", "move_to", {"position": 1}, operation_key="j2",
                                            wait_ms=2000)).operation.state == "completed"


async def test_stop_sent_to_a_stalled_upstream_is_executed_when_it_resumes(tmp_path):  # AUTH-022, 024
    state = tmp_path / "up"
    gateway, client = await start_gateway(tmp_path, [stdio_upstream("dev", state)], stop_deadline_ms=500)
    try:
        pid = child_pid(gateway, "dev")
        os.kill(pid, signal.SIGSTOP)
        try:
            await until(lambda: _offline(client), timeout=10)
            stops = (await client.stop("now", device_ids=["dev/axis-1"])).stops
            assert stops[0].outcome == "initiated" and stops[0].evidence == "none"  # never "confirmed" (AUTH-022)
        finally:
            os.kill(pid, signal.SIGCONT)
        await until(lambda: asyncio.sleep(0, "stop" in device_log(state)), timeout=10)  # it ran when it resumed
    finally:
        await client.close()
        await gateway.close()


async def _offline(client):
    return (await client.devices_list()).devices[0].status == "offline"


_ = HELPER
