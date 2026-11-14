"""Epochs, reboots, restarts, stop, cancel, fences and corrupt frames against the native C endpoint (spec 11.5 to 11.8).

The question in every test is what the bridge may claim: an operation that may have executed stays ``unknown`` until
evidence says otherwise, the resource inhibition of BHMS-OPS-042 is lifted only by proof, and nothing is sent twice that
could act twice.
"""

from __future__ import annotations

import asyncio

import pytest
from helpers.compact_rig import compact_rig, effects

from bhms.protocol.errors import BhmsError
from bhms.protocol.types import to_wire
from bhms.testing.compact_endpoint import TO_DEVICE, TO_GATEWAY
from bhms.transport import compact as cp

pytestmark = pytest.mark.usefixtures("native")


async def events(rig, type_: str) -> list[dict]:
    page = to_wire(await rig.client.events_read(device_id=rig.device, limit=200))["events"]
    return [e for e in page if e["type"] == type_]


async def running(rig, op_id: str) -> bool:
    return (await rig.operation(op_id))["state"] == "running"


async def start_lock(rig, ms: int = 4000) -> str:
    op = await rig.invoke("lock", {"duration_ms": ms}, wait_ms=0)
    await rig.wait_for(lambda: running(rig, op["operationId"]), what="the lock to run")
    return op["operationId"]


# ------------------------------------------------------------------------------------------------ reboot (CMP-020/022)


async def test_persistent_reboot_makes_the_operation_unknown_lifts_the_inhibition_and_resends_nothing(tmp_path, native):
    async with compact_rig(tmp_path, native) as rig:
        op_id = await start_lock(rig)
        assert rig.bridge.epoch == 1 and rig.bridge.persistent
        await rig.wire.reboot()  # the board loses power: epoch 2, the ring is gone
        op = await rig.wait_for(lambda: _unknown(rig, op_id), what="the operation to become unknown")
        assert op["error"]["bhmsCode"] == "DEADLINE_EXCEEDED" and op["effect"] == "unknown"
        await rig.wait_for(lambda: rig.bridge.epoch == 2 and rig.bridge.up, what="the new epoch")
        assert len(rig.wire.sent(cp.Invoke, TO_DEVICE)) == 1  # never re-sent (CMP-022)
        # nothing was asked about the old-epoch handle in the new epoch (CMP-034): such a QUERY could only be refused
        assert not [s for s in rig.wire.sent(cp.Query, TO_DEVICE) if s.session == 2 and s.message.handle == 1]
        # epoch advanced on a persistent endpoint: proof of purge, so the axis is usable again (OPS-042) ...
        again = await rig.invoke("lock", {"duration_ms": 30})
        assert again["state"] == "completed"
        # ... the new epoch restarts the handles at 1 and the old operation is still unknown
        assert rig.wire.sent(cp.Invoke, TO_DEVICE)[-1].message.handle == 1 and rig.wire.sent(cp.Invoke)[-1].session == 2
        assert (await rig.operation(op_id))["state"] == "unknown"
        emitted = await events(rig, "device.epoch")
        assert emitted and emitted[-1]["data"]["epoch"] == 2 and emitted[-1]["data"]["purged"] is True


async def _unknown(rig, op_id):
    op = await rig.operation(op_id)
    return op if op["state"] == "unknown" else None


async def test_reboot_to_the_same_epoch_is_not_proof_and_keeps_the_inhibition_until_a_confirmed_stop(tmp_path, native):
    async with compact_rig(tmp_path, native, epoch=False) as rig:  # no persistent counter: the epoch repeats (CMP-020)
        op_id = await start_lock(rig)
        assert not rig.bridge.persistent
        await rig.wire.reboot()
        op = await rig.wait_for(lambda: _unknown(rig, op_id), what="unknown after a silent reboot")
        assert op["effect"] == "unknown"
        assert len(rig.wire.sent(cp.Invoke, TO_DEVICE)) == 1
        # a HELLO cannot show the old work is gone on such an endpoint: same epoch value, still inhibited (CMP-022)
        rig.bridge._needs_hello.set()
        await rig.wait_for(lambda: len(rig.wire.sent(cp.HelloReq)) >= 2 and rig.bridge.up, what="a second HELLO")
        with pytest.raises(BhmsError) as inhibited:
            await rig.invoke("lock", {"duration_ms": 30})
        assert inhibited.value.bhms_code == "STALE" and op_id in inhibited.value.message
        assert (await events(rig, "device.epoch"))  # emitted for the possible reset
        # only a confirmed stop lifts it (OPS-042)
        stop = to_wire(await rig.client.stop("recover", device_ids=[rig.device], wait_ms=2000))["stops"][0]
        assert stop["outcome"] == "confirmed" and stop["evidence"] == "measured"
        done = await rig.invoke("lock", {"duration_ms": 30})
        assert done["state"] == "completed" and (await rig.operation(op_id))["state"] == "unknown"


async def test_new_session_before_the_handles_run_out_restarts_them_and_proves_a_purge(tmp_path, native):  # CMP-023, 030
    async with compact_rig(tmp_path, native) as rig:
        rig.bridge.next_handle = 65_000  # as if 64999 operations had run in this epoch
        op = await rig.invoke("set_level", {"value": 1.0})
        assert op["state"] == "completed"
        hellos = rig.wire.sent(cp.HelloReq)
        assert hellos[-1].message.new_session and rig.bridge.epoch == 2  # an accepted new session
        last = rig.wire.sent(cp.Invoke)[-1]
        assert last.message.handle == 1 and last.session == 2  # handles restart in the new epoch
        handles = [s.message.handle for s in rig.wire.sent(cp.Invoke) if s.session == 2]
        assert handles == sorted(handles)


async def test_handles_are_never_reused_when_the_bridge_restarts_in_the_same_epoch(tmp_path, native):  # CMP-030
    async with compact_rig(tmp_path, native) as rig:
        await rig.invoke("set_level", {"value": 1.0})
        await rig.invoke("set_level", {"value": 2.0})
        await rig.restart_bridge()
        await rig.invoke("set_level", {"value": 3.0})
        assert [s.message.handle for s in rig.wire.sent(cp.Invoke)] == [1, 2, 3]


# ------------------------------------------------------------------------------------------------ gateway restart (CMP-034)


async def test_a_restarted_bridge_queries_the_current_epoch_and_reconciles_from_the_result(tmp_path, native):
    async with compact_rig(tmp_path, native) as rig:
        op_id = await start_lock(rig, 600)
        await rig.restart_bridge()  # the gateway restarts mid-operation: the journal says unknown (OPS-080)
        settled = await rig.wait_for(lambda: _terminal(rig, op_id), timeout=8, what="reconciliation from the endpoint")
        assert settled["state"] == "completed"
        history = rig.bridge.server.journal.get(op_id).wire(history=True)["history"]
        assert any(h["kind"] == "reconciliation" and "RESULT" in h.get("detail", "") for h in history)
        assert any(isinstance(s.message, cp.Query) and s.message.handle == 1 for s in rig.wire.log)
        assert effects(rig, "LOCK-start") == ["LOCK-start 1 0"] and len(rig.wire.sent(cp.Invoke, TO_DEVICE)) == 1


async def _terminal(rig, op_id):
    op = await rig.operation(op_id)
    return op if op["state"] in ("completed", "failed", "canceled") else None


async def test_a_restarted_bridge_leaves_an_operation_of_an_earlier_epoch_unknown_and_never_queries_it(tmp_path, native):
    async with compact_rig(tmp_path, native) as rig:
        op_id = await start_lock(rig, 5000)
        await rig.client.close()
        await rig.bridge.close()
        await rig.wire.reboot()  # while the gateway is down the board restarts: epoch 2
        await rig.restart_bridge()
        await rig.wait_for(lambda: rig.bridge.epoch == 2, what="the new epoch")
        await asyncio.sleep(0.6)  # long enough for several reconcile passes
        assert (await rig.operation(op_id))["state"] == "unknown"
        assert not [s for s in rig.wire.sent(cp.Query, TO_DEVICE) if s.session == 2 and s.message.handle == 1]
        # the persistent epoch advanced across the gateway restart: proof of purge, inhibition lifted
        assert (await rig.invoke("lock", {"duration_ms": 30}))["state"] == "completed"


# ------------------------------------------------------------------------------------------------ stop (CMP-050/051)


async def test_stop_is_sent_at_once_acknowledged_then_confirmed_and_ends_the_operation(tmp_path, native):
    async with compact_rig(tmp_path, native) as rig:
        op_id = await start_lock(rig)
        stop = to_wire(await rig.client.stop("test", device_ids=[rig.device], wait_ms=3000))["stops"][0]
        assert stop["outcome"] == "confirmed" and stop["evidence"] == "measured"
        sent = rig.wire.sent(cp.Stop, TO_DEVICE)
        assert len(sent) == 1 and sent[0].message.reason == 3
        acks = rig.wire.sent(cp.StopAck, TO_GATEWAY)
        assert [a.message.outcome for a in acks] == [cp.STOPACK_INITIATED, cp.STOPACK_CONFIRMED]
        assert acks[0].kind == cp.STATUS_KIND and acks[1].kind == cp.TELEMETRY  # the second ack is unsolicited
        op = await rig.wait_for(lambda: _terminal(rig, op_id), what="the stopped operation")
        assert op["state"] == "canceled"
        assert effects(rig, "STOP") == ["STOP 0 0"]


async def test_stop_with_an_immediate_confirmation_needs_no_second_ack(tmp_path, native):
    async with compact_rig(tmp_path, native, args=("--stop-immediate",)) as rig:
        stop = to_wire(await rig.client.stop("test", device_ids=[rig.device], wait_ms=1000))["stops"][0]
        assert stop["outcome"] == "confirmed"
        assert [a.message.outcome for a in rig.wire.sent(cp.StopAck)] == [cp.STOPACK_CONFIRMED]


async def test_stop_works_with_a_stale_session_and_reports_an_endpoint_without_a_stop_procedure(tmp_path, native):
    async with compact_rig(tmp_path, native, args=("--no-stop",)) as rig:
        rig.bridge.epoch = 77  # the bridge's idea of the session is wrong: STOP is accepted regardless (CMP-050)
        stop = to_wire(await rig.client.stop("test", device_ids=[rig.device], wait_ms=1500))["stops"][0]
        assert stop["outcome"] == "failed"  # the description promised a stop; the endpoint says it has none
        assert rig.wire.sent(cp.StopAck)[0].message.outcome == cp.STOPACK_UNSUPPORTED
        assert rig.wire.sent(cp.Stop)[0].session == 77


async def test_stop_whose_acknowledgements_are_lost_is_repeated_not_dropped(tmp_path, native):
    async with compact_rig(tmp_path, native) as rig:
        rig.wire.drop(TO_GATEWAY, count=2, match=lambda m: isinstance(m, cp.StopAck))  # both acks of the first STOP
        stop = to_wire(await rig.client.stop("test", device_ids=[rig.device], wait_ms=3000))["stops"][0]
        assert stop["outcome"] == "confirmed"
        assert len(rig.wire.sent(cp.Stop, TO_DEVICE)) >= 2


# ------------------------------------------------------------------------------------------------ cancel, progress


async def test_cancel_is_acknowledged_then_ended_and_progress_is_reported(tmp_path, native):
    async with compact_rig(tmp_path, native) as rig:
        lease = await rig.lease("bench-rig/axis")
        op = await rig.invoke("move", {"duration_ms": 3000, "target": 45.0}, lease=lease, wait_ms=0)
        op_id = op["operationId"]
        await rig.wait_for(lambda: running(rig, op_id), what="the move to run")
        await rig.wait_for(lambda: _progress(rig, op_id), what="progress")
        await rig.client.operations_cancel(op_id, reason="test")
        done = await rig.wait_for(lambda: _terminal(rig, op_id), what="cancellation")
        assert done["state"] == "canceled" and done["cancel"]["state"] in ("confirmed", "acknowledged")
        assert [s.message.handle for s in rig.wire.sent(cp.Cancel, TO_DEVICE)] == [1]
        history = rig.bridge.server.journal.get(op_id).wire(history=True)["history"]
        assert any(h["kind"] == "cancel" and h.get("cancel") == "acknowledged" for h in history)
        assert effects(rig, "MOVE-cancel") == ["MOVE-cancel 1 0"]


async def _progress(rig, op_id):
    return (await rig.operation(op_id)).get("progress")


async def test_an_action_that_cannot_be_cancelled_is_refused_without_sending_cancel(tmp_path, native):
    async with compact_rig(tmp_path, native) as rig:
        op_id = await start_lock(rig, 600)
        await rig.client.operations_cancel(op_id)
        assert (await rig.operation(op_id))["cancel"]["state"] == "refused"
        assert not rig.wire.sent(cp.Cancel)
        assert (await rig.wait_for(lambda: _terminal(rig, op_id), what="the lock to run out"))["state"] == "completed"


async def test_losing_the_lease_cancels_a_running_move(tmp_path, native):  # onLeaseLoss: cancel
    async with compact_rig(tmp_path, native) as rig:
        lease = await rig.lease("bench-rig/axis", ttl_ms=1000)  # expires while the move runs
        op = await rig.invoke("move", {"duration_ms": 4000, "target": 10.0}, lease=lease, wait_ms=0)
        await rig.wait_for(lambda: running(rig, op["operationId"]), what="the move to run")
        done = await rig.wait_for(lambda: _terminal(rig, op["operationId"]), timeout=5, what="cancellation by lease loss")
        assert done["state"] == "canceled" and rig.wire.sent(cp.Cancel)


# ------------------------------------------------------------------------------------------------ fences (CMP-040/041)


async def test_lease_fences_reach_the_endpoint_and_only_grow(tmp_path, native):
    async with compact_rig(tmp_path, native) as rig:
        assert rig.bridge.hello.fencing
        fences = []
        for _ in range(3):
            lease = await rig.lease("bench-rig/axis")
            assert (await rig.invoke("move", {"duration_ms": 20, "target": 1.0}, lease=lease))["state"] == "completed"
            await rig.client.leases_release(lease["leaseId"])
            fences.append(rig.wire.sent(cp.Invoke)[-1].message.fence)
        assert fences == sorted(set(fences)) and fences[0] > 0  # strictly increasing per endpoint epoch, never 0
        with pytest.raises(BhmsError) as needed:
            await rig.invoke("move", {"duration_ms": 20, "target": 1.0})  # no lease: refused before anything is sent
        assert needed.value.bhms_code == "LEASE_REQUIRED"
        assert len(rig.wire.sent(cp.Invoke)) == 3


async def test_the_endpoint_fences_an_older_lease_holder_after_stop(tmp_path, native):  # CMP-051
    async with compact_rig(tmp_path, native) as rig:
        lease = await rig.lease("bench-rig/axis")
        await rig.invoke("move", {"duration_ms": 20, "target": 1.0}, lease=lease)
        stale_fence = rig.wire.sent(cp.Invoke)[-1].message.fence
        await rig.client.stop("test", device_ids=[rig.device], wait_ms=2000)
        # a frame carrying the pre-stop fence (a lease holder that did not hear about the stop) is refused by the endpoint
        rig.wire.inject(TO_DEVICE, rig.wire.frame_for(cp.Invoke(900, 1, (5).to_bytes(2, "little") + bytes(2), stale_fence),
                                                      rig.bridge.epoch))
        error = await rig.wait_for(lambda: [s for s in rig.wire.sent(cp.Error, TO_GATEWAY) if s.message.ident == 900],
                                   what="FENCED")
        assert error[0].message.code == cp.E_FENCED
        assert effects(rig, "MOVE-start") == ["MOVE-start 1 0"]  # the stale command did not run


# ------------------------------------------------------------------------------------------------ corrupt frames (CMP-001/002)


async def test_a_corrupt_invoke_is_ignored_by_the_endpoint_and_retransmitted_once_intact(tmp_path, native):
    async with compact_rig(tmp_path, native) as rig:
        rig.wire.corrupt(TO_DEVICE, match=lambda m: isinstance(m, cp.Invoke))
        op = await rig.invoke("set_level", {"value": 7.0})
        assert op["state"] == "completed" and op["result"] == {"writes": 1}
        assert len(rig.wire.sent(cp.Invoke, TO_DEVICE)) == 2 and effects(rig, "SET") == ["SET 70 0"]


async def test_a_corrupt_result_is_discarded_and_found_again_from_the_ring(tmp_path, native):
    async with compact_rig(tmp_path, native) as rig:
        rig.wire.corrupt(TO_GATEWAY, match=lambda m: isinstance(m, cp.Result))
        op = await rig.invoke("set_level", {"value": 7.0})
        assert op["state"] == "completed" and effects(rig, "SET") == ["SET 70 0"]
        assert rig.bridge._link.stats["frame-error"] >= 1


async def test_line_noise_and_foreign_frames_do_not_disturb_the_link(tmp_path, native):
    async with compact_rig(tmp_path, native) as rig:
        foreign = rig.wire.frame_for(cp.Invoke(5, 0, b"\x00\x00"), rig.bridge.epoch, channel=2)
        for direction in (TO_DEVICE, TO_GATEWAY):
            rig.wire.inject(direction, b"\x00\xff\x7d\x7d\x01garbage\x7e\x7e\x7e" + foreign)
        op = await rig.invoke("set_level", {"value": 7.0})
        assert op["state"] == "completed" and effects(rig, "SET") == ["SET 70 0"]


async def test_a_severed_link_takes_the_device_offline_and_it_returns_with_the_same_epoch(tmp_path, native):
    async with compact_rig(tmp_path, native) as rig:
        await rig.wire.sever()
        await rig.wait_for(lambda: not rig.bridge.up, what="the link to be declared down")
        assert [d.status async for d in rig.client.iter_devices()] == ["offline"]
        with pytest.raises(BhmsError) as refused:
            await rig.invoke("set_level", {"value": 1.0})
        assert refused.value.bhms_code == "DEVICE_UNAVAILABLE" and refused.value.may_have_acted is False
        await rig.wire.wait_connected()
        await rig.wait_for(lambda: rig.bridge.up and rig.bridge.epoch == 1, timeout=8, what="the link to return")
        assert (await rig.invoke("set_level", {"value": 1.0}))["state"] == "completed"
