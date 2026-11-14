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


async def test_a_journal_written_before_incarnations_existed_is_never_asked_about_the_endpoint(tmp_path):  # CMP-034 migration
    """Pre-fix state: link `{epoch: 7}` and an operation of epoch 6 handle 1, neither with an incarnation. Epoch 7 repeats handle 1."""
    import json

    from helpers.compact_rig import LED

    from bhms.runtime.store import Store

    first = Scripted(cp.digest8_of(LED), epoch=6, flags=PERSISTENT)
    async with scripted_rig(tmp_path, scripted=first) as (client, bridge, ep):
        ep.on[cp.Invoke] = lambda e, m: None
        x = await op(client)
        done = to_wire(await client.operations_wait(x["operationId"], 6000))["operation"]
        assert done["state"] == "unknown"
    store = Store(str(tmp_path / "bridge" / "compact-script.sqlite3"))
    try:
        prefix = "compact/bench-led/"
        store.meta_set(prefix + "link", json.dumps({"epoch": 7, "persistent": True, "next_handle": 2}), barrier=True)
        info = json.loads(store.meta_get(f"{prefix}ops/{x['operationId']}"))
        assert info["epoch"] == 6 and info["handle"] == 1
        info.pop("inc", None)
        store.meta_set(f"{prefix}ops/{x['operationId']}", json.dumps(info), barrier=True)
    finally:
        store.close()
    second = Scripted(cp.digest8_of(LED), epoch=7, flags=PERSISTENT)
    second.on[cp.Query] = lambda e, m: e.say(cp.Result(m.handle, cp.ST_COMPLETED, cp.EVIDENCE_REPORTED, 0, b"\x05"))
    async with scripted_rig(tmp_path, scripted=second) as (client, bridge, ep):
        await asyncio.sleep(1.5)
        still = to_wire(await client.operations_get(x["operationId"]))["operation"]
        assert still["state"] == "unknown"  # epoch 7's handle 1 is another operation's: not evidence
        assert not [q for q in ep.of(cp.Query) if q.handle == 1]
        assert bridge.incarnation >= 1


async def test_the_incarnation_never_goes_backwards_when_the_saved_state_is_behind(tmp_path):
    """A link-state save that failed leaves the durable counter behind the one in memory: the next HELLO continues the larger."""
    from helpers.compact_rig import LED

    script = Scripted(cp.digest8_of(LED), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, scripted=script) as (client, bridge, ep):
        bridge.incarnation = 50  # as if 48 more incarnations were counted but their saves failed
        await reboot(ep, bridge, epoch=8, flags=PERSISTENT)
        assert bridge.incarnation == 51


async def test_a_purge_proof_names_at_most_a_bounded_number_of_operations_and_says_so(tmp_path):  # spec 9.2
    from helpers.compact_rig import BENCH

    script = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=script) as (client, bridge, ep):
        ep.on[cp.Invoke] = lambda e, m: None
        ids = []
        for action, arguments in (("lock", {"duration_ms": 20}), ("set_level", {"value": 1.0})):  # different resources: both dispatch
            got = to_wire(await client.actions_invoke("bench-rig", action, arguments, wait_ms=0))["operation"]
            ids.append(got["operationId"])
        for _ in range(100):
            if len(ep.of(cp.Invoke)) >= 2:
                break
            await asyncio.sleep(0.02)
        await reboot(ep, bridge, epoch=8, flags=PERSISTENT)
        listed, more = bridge._purged_operation_ids(limit=1)
        assert len(listed) == 1 and more is True
        listed, more = bridge._purged_operation_ids()
        assert sorted(listed) == sorted(ids) and more is False
