"""An endpoint incarnation is not its epoch value: every HELLO of a non-persistent endpoint may follow a reset, and an
epoch value can recur (BHMS-CMP-020, CMP-022, CMP-033, CMP-034). Scripted endpoint, so the flaky counters can be played."""

from __future__ import annotations

import asyncio

from helpers.compact_script import Scripted, scripted_rig

from bhms.protocol.types import to_wire
from bhms.transport import compact as cp

ON = {"on": True}
NON_PERSISTENT = cp.FLAG_FENCING
PERSISTENT = cp.FLAG_PERSISTENT_EPOCH | cp.FLAG_FENCING


async def reboot(ep: Scripted, bridge, *, epoch: int, flags: int) -> None:
    """The endpoint comes back with ``epoch``/``flags``; a frame of the new session makes the bridge ask for HELLO."""
    ep.epoch, ep.flags = epoch, flags
    before = len(ep.of(cp.HelloReq))
    ep.say(cp.Value(0, 0, cp.Q_VALID, 0, 1, 0, b"\x01\x00"), kind=cp.TELEMETRY, session=epoch + 100)  # not the bridge's epoch
    for _ in range(200):
        if len(ep.of(cp.HelloReq)) > before and bridge.ready and bridge.epoch == epoch and bridge.persistent == bool(
                flags & cp.FLAG_PERSISTENT_EPOCH):
            return
        await asyncio.sleep(0.02)
    raise AssertionError("the bridge never adopted the new HELLO")


async def op(client, wait_ms=0):
    return to_wire(await client.actions_invoke("bench-led", "led_set", ON, wait_ms=wait_ms))["operation"]


async def test_an_invoke_dispatched_to_a_non_persistent_endpoint_is_never_resent_after_it_turns_persistent(tmp_path):  # CMP-033
    """The epoch store failed at boot 1 (epoch 8, no persistence) and worked at boot 2 (still 8, now persistent)."""
    ep = Scripted(b"", epoch=8, flags=NON_PERSISTENT)
    from helpers.compact_rig import LED

    ep.digest8 = cp.digest8_of(LED)
    async with scripted_rig(tmp_path, scripted=ep) as (client, bridge, ep):
        ep.on[cp.Invoke] = lambda e, m: None  # the command vanishes; nothing answers
        started = await op(client)
        await asyncio.sleep(0.1)
        await reboot(ep, bridge, epoch=8, flags=PERSISTENT)
        done = to_wire(await client.operations_wait(started["operationId"], 4000))["operation"]
        assert done["state"] == "unknown" and done["error"]["mayHaveActed"] is True
        assert len(ep.of(cp.Invoke)) == 1  # the INVOKE that may have executed is never sent again


async def test_a_recurring_epoch_value_never_lets_a_new_operations_result_settle_an_old_unknown_one(tmp_path):  # CMP-022/034
    """Epoch 7, then 8, then 7 again (a flaky counter): handle 1 is used by two different operations."""
    from helpers.compact_rig import LED

    ep = Scripted(cp.digest8_of(LED), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, scripted=ep) as (client, bridge, ep):
        ep.on[cp.Invoke] = lambda e, m: None  # X's INVOKE is lost for good
        x = await op(client)
        done = to_wire(await client.operations_wait(x["operationId"], 6000))["operation"]
        assert done["state"] == "unknown"
        await reboot(ep, bridge, epoch=8, flags=PERSISTENT)
        await reboot(ep, bridge, epoch=7, flags=PERSISTENT)
        ep.on[cp.Invoke] = lambda e, m: e.say(cp.Result(m.handle, cp.ST_COMPLETED, cp.EVIDENCE_REPORTED, 0, b"\x05"))
        ep.on[cp.Query] = lambda e, m: e.say(cp.Result(m.handle, cp.ST_COMPLETED, cp.EVIDENCE_REPORTED, 0, b"\x05"))
        y = await op(client, wait_ms=3000)
        assert y["state"] == "completed"
        await asyncio.sleep(1.0)  # time for reconciliation to try X
        still = to_wire(await client.operations_get(x["operationId"]))["operation"]
        assert still["state"] == "unknown"  # Y's RESULT is not evidence about X


async def test_late_acknowledgements_of_an_earlier_stop_are_not_taken_for_the_next_one(tmp_path):  # CMP-050/051
    """STOP_ACK names no STOP: the acks still due to the first attempt's STOPs are skipped, in order."""
    from helpers.compact_rig import BENCH

    script = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=script) as (client, bridge, ep):
        stops = {"n": 0}

        async def on_stop(e, m):
            stops["n"] += 1
            if stops["n"] == bridge.timing.retries + 2:  # the first STOP of the second attempt
                for _ in range(bridge.timing.retries + 1):  # the delayed answers to the first attempt's STOPs
                    e.say(cp.StopAck(cp.STOPACK_CONFIRMED, cp.EVIDENCE_MEASURED))

        ep.on[cp.Stop] = on_stop
        first = to_wire(await client.stop("t", device_ids=["bench-rig"], wait_ms=4000))["stops"][0]
        assert first["outcome"] != "confirmed"  # nothing answered
        second = to_wire(await client.stop("t", device_ids=["bench-rig"], wait_ms=4000))["stops"][0]
        assert second["outcome"] != "confirmed"  # the stale acks are not evidence that THIS stop worked


async def test_a_read_refused_with_session_mismatch_is_stale_not_an_invalid_argument(tmp_path):
    from helpers.compact_rig import LED

    from bhms.protocol.errors import BhmsError

    script = Scripted(cp.digest8_of(LED), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, scripted=script) as (client, bridge, ep):
        ep.on[cp.Read] = lambda e, m: e.say(cp.Error(cp.READ, m.request, cp.E_SESSION_MISMATCH))
        try:  # the device server folds a failed read into an invalid observation; the bridge's own error is what is mapped
            await bridge._property_getter("analog0")()
        except BhmsError as exc:
            assert exc.code == "STALE"
        else:
            raise AssertionError("the read should have been refused")


async def test_an_ordinary_hello_with_another_epoch_is_never_credited_as_an_accepted_new_session(tmp_path):  # CMP-023
    from helpers.compact_rig import LED

    script = Scripted(cp.digest8_of(LED), epoch=7, flags=NON_PERSISTENT)
    async with scripted_rig(tmp_path, scripted=script) as (client, bridge, ep):
        await reboot(ep, bridge, epoch=9, flags=NON_PERSISTENT)  # a different value, but nobody asked for NEW_SESSION
        events = to_wire(await client.events_read(types=["device.epoch"]))["events"]
        assert events and all(e["data"]["purged"] is False for e in events)
