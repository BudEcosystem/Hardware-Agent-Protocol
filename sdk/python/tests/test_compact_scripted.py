"""The bridge against a scripted endpoint: the replies the C endpoint never gives (error mapping, odd frames, versions).

The native tests (test_compact_bridge.py, test_compact_epochs.py) prove the bridge against the real endpoint; here a
scripted peer sends exactly the frames a test needs, so every row of the ERROR table of spec 11.2 and every
guarantee the bridge draws from it is exercised.
"""

from __future__ import annotations

import asyncio
import copy

import pytest
from helpers.compact_rig import LED
from helpers.compact_script import Scripted, scripted_rig

from bhms.gateway.compact_bridge import advanced
from bhms.protocol.types import to_wire
from bhms.transport import compact as cp

ON = {"on": True}
SLOW = copy.deepcopy(LED)  # the example's 100 ms bound would end a deliberately slow operation as unknown
SLOW["actions"]["led_set"]["maxDurationMs"] = 5000


def invoke_with(reply):
    async def behave(ep, message):
        ep.say(reply(message) if callable(reply) else reply)

    return behave


async def run(client, args=ON, wait_ms=3000):
    return to_wire(await client.actions_invoke("bench-led", "led_set", args, wait_ms=wait_ms))["operation"]


@pytest.mark.parametrize("code,expected", [
    (cp.E_MALFORMED, "INVALID_ARGUMENT"), (cp.E_UNKNOWN_ACTION, "UNKNOWN_ACTION"), (cp.E_UNKNOWN_PROPERTY, "INVALID_ARGUMENT"),
    (cp.E_OUT_OF_RANGE, "OUT_OF_RANGE"), (cp.E_FENCED, "FENCED"), (cp.E_LEASE_REQUIRED, "LEASE_REQUIRED"),
    (cp.E_BUSY, "BUSY"), (cp.E_EXPIRED, "DEADLINE_EXCEEDED"), (cp.E_UNSUPPORTED, "UNSUPPORTED"),
    (cp.E_PRECONDITION, "STALE"), (cp.E_INHIBITED, "DEVICE_UNAVAILABLE"), (cp.E_INTERNAL, "INTERNAL")])
async def test_every_error_that_proves_not_started_is_recorded_as_such(tmp_path, code, expected):  # spec 11.2 table
    async with scripted_rig(tmp_path) as (client, bridge, ep):
        ep.on[cp.Invoke] = invoke_with(lambda m: cp.Error(cp.INVOKE, m.handle, code, 4))
        op = await run(client)
        assert op["state"] == "failed" and op["error"]["bhmsCode"] == expected
        assert op["error"]["mayHaveActed"] is False and op["effect"] == "none"
        assert "detail 4" in op["error"]["message"]
        assert len(ep.of(cp.Invoke)) == 1  # a refusal is final: nothing is retransmitted


async def test_handle_unknown_and_conflict_leave_the_operation_unknown(tmp_path):
    for code in (cp.E_HANDLE_UNKNOWN, cp.E_HANDLE_CONFLICT):
        async with scripted_rig(tmp_path / str(code)) as (client, bridge, ep):
            ep.on[cp.Invoke] = invoke_with(lambda m: cp.Error(cp.INVOKE, m.handle, code))
            op = await run(client)
            assert op["state"] == "unknown" and op["error"]["mayHaveActed"] is True


async def test_session_mismatch_on_the_first_send_proves_nothing_ran_but_later_it_does_not(tmp_path):  # CMP-021
    async with scripted_rig(tmp_path / "first") as (client, bridge, ep):
        ep.on[cp.Invoke] = invoke_with(lambda m: cp.Error(cp.INVOKE, m.handle, cp.E_SESSION_MISMATCH))
        op = await run(client)
        assert op["state"] == "failed" and op["error"]["mayHaveActed"] is False and "SESSION_MISMATCH" in op["error"]["message"]
    async with scripted_rig(tmp_path / "later") as (client, bridge, ep):
        state = {"n": 0}

        async def silent_then_mismatch(ep, message):  # the first INVOKE vanishes; the retransmit meets a rebooted endpoint
            state["n"] += 1
            if state["n"] > 1:
                ep.say(cp.Error(cp.INVOKE, message.handle, cp.E_SESSION_MISMATCH))

        ep.on[cp.Invoke] = silent_then_mismatch
        op = await run(client)
        assert op["state"] == "unknown" and op["error"]["mayHaveActed"] is True


async def test_results_map_to_states_with_the_devices_fault_number(tmp_path):
    async with scripted_rig(tmp_path) as (client, bridge, ep):
        ep.on[cp.Invoke] = invoke_with(lambda m: cp.Result(m.handle, cp.ST_FAILED, cp.EVIDENCE_REPORTED, 21))
        failed = await run(client)
        assert failed["state"] == "failed" and failed["error"]["bhmsCode"] == "DEVICE_FAULT"
        assert "fault 21" in failed["error"]["message"] and failed["error"]["mayHaveActed"] is True
        ep.on[cp.Invoke] = invoke_with(lambda m: cp.Result(m.handle, cp.ST_CANCELED, cp.EVIDENCE_REPORTED, 0))
        canceled = await run(client, {"on": False})
        assert canceled["state"] == "canceled"
        ep.on[cp.Invoke] = invoke_with(lambda m: cp.Result(m.handle, cp.ST_REJECTED, 0, 0))
        rejected = to_wire(await client.actions_invoke("bench-led", "led_set", ON, wait_ms=3000, operation_key="k-rej"))["operation"]
        assert rejected["state"] == "failed" and rejected["error"]["mayHaveActed"] is False and rejected["effect"] == "none"


async def test_a_result_with_the_wrong_field_length_leaves_the_operation_unknown(tmp_path):  # CMP-002
    async with scripted_rig(tmp_path) as (client, bridge, ep):
        ep.on[cp.Invoke] = invoke_with(lambda m: cp.Result(m.handle, cp.ST_COMPLETED, cp.EVIDENCE_REPORTED, 0, b"\x01\x02"))
        assert (await run(client))["state"] == "unknown"


async def test_status_then_result_follows_the_endpoint_without_polling_too_early(tmp_path):
    async with scripted_rig(tmp_path, sidecar=SLOW) as (client, bridge, ep):
        async def two_step(ep, message):
            ep.say(cp.Status(message.handle, cp.ST_RUNNING, cp.CANCEL_NONE, 40))
            await asyncio.sleep(0.5)  # longer than the reply timeout: silence after a STATUS is not loss
            ep.say(cp.Result(message.handle, cp.ST_COMPLETED, cp.EVIDENCE_MEASURED, 0, b"\x09"), kind=cp.TELEMETRY)

        ep.on[cp.Invoke] = two_step
        op = await run(client)
        assert op["state"] == "completed" and op["result"] == {"writes": 9}
        assert len(ep.of(cp.Invoke)) == 1  # never retransmitted once it answered
        assert ep.of(cp.Query)  # it polled for a lost RESULT while waiting


async def test_a_lost_result_is_found_by_polling_a_running_operation(tmp_path):
    async with scripted_rig(tmp_path, sidecar=SLOW) as (client, bridge, ep):
        async def running_then_lost(ep, message):
            ep.say(cp.Status(message.handle, cp.ST_RUNNING, cp.CANCEL_NONE, cp.PROGRESS_UNKNOWN))

        async def answer_query(ep, message):
            ep.say(cp.Result(message.handle, cp.ST_COMPLETED, cp.EVIDENCE_REPORTED, 0, b"\x03"))

        ep.on[cp.Invoke] = running_then_lost
        ep.on[cp.Query] = answer_query
        op = await run(client)
        assert op["state"] == "completed" and op["result"] == {"writes": 3}


async def test_an_unsolicited_value_is_published_with_the_endpoints_epoch_and_sequence(tmp_path):  # CMP-060
    async with scripted_rig(tmp_path) as (client, bridge, ep):
        ep.say(cp.Value(0, 0, cp.Q_VALID, 0, 41, 5, (123).to_bytes(2, "little")), kind=cp.TELEMETRY)
        await asyncio.sleep(0.2)
        read = to_wire(await client.properties_read("bench-led", "analog0"))["observation"]
        assert read["value"] == 123 and read["sequence"] == 41 and read["epoch"] == "compact:7"
        assert read["quality"] == "valid" and read["evidence"] == "measured"
        ep.say(cp.Value(0, 0, cp.Q_INVALID, 0, 42, cp.AGE_UNKNOWN), kind=cp.TELEMETRY)
        await asyncio.sleep(0.2)
        again = to_wire(await client.properties_read("bench-led", "analog0"))["observation"]
        assert again["quality"] == "invalid" and again["value"] is None and again["sequence"] == 42


async def test_a_value_with_bytes_but_no_valid_quality_is_refused_not_trusted(tmp_path):  # CMP-060
    async with scripted_rig(tmp_path) as (client, bridge, ep):
        async def lying(ep, message):
            ep.say(cp.Value(message.request, message.prop, cp.Q_INVALID, 0, 1, 0, b"\x01\x00"))

        ep.on[cp.Read] = lying
        read = to_wire(await client.properties_read("bench-led", "analog0", fresh=True))["observation"]
        assert read["quality"] == "invalid" and read["value"] is None


async def test_a_frame_of_another_epoch_is_dropped_and_asks_for_a_new_hello(tmp_path):
    async with scripted_rig(tmp_path) as (client, bridge, ep):
        before = len(ep.of(cp.HelloReq))
        ep.say(cp.Value(0, 0, cp.Q_VALID, 0, 1, 0, b"\x01\x00"), kind=cp.TELEMETRY, session=99)
        for _ in range(100):
            if len(ep.of(cp.HelloReq)) > before:
                break
            await asyncio.sleep(0.05)
        assert len(ep.of(cp.HelloReq)) > before
        read = to_wire(await client.properties_read("bench-led", "analog0"))["observation"]
        assert read["sequence"] != 1 or read["value"] != 1  # the foreign-epoch value was not published


async def test_an_endpoint_that_speaks_another_compact_version_is_not_served(tmp_path):
    ep = Scripted(cp.digest8_of(LED), version=2)
    async with scripted_rig(tmp_path, scripted=ep, served=False) as (client, bridge, _):
        await asyncio.sleep(0.6)
        assert bridge.device is None and not bridge.up


async def test_args_larger_than_the_endpoints_limit_are_refused_before_sending(tmp_path):
    ep = Scripted(cp.digest8_of(LED), max_args=0)
    async with scripted_rig(tmp_path, scripted=ep) as (client, bridge, _):
        op = await run(client)
        assert not ep.of(cp.Invoke)
        assert op["state"] == "failed" and op["error"]["bhmsCode"] == "OUT_OF_RANGE" and op["error"]["mayHaveActed"] is False


def test_epoch_advance_is_wrap_aware_and_never_true_for_the_same_or_an_older_epoch():
    assert advanced(1, 2) and advanced(0xFFFFFFFF, 1) and advanced(7, 7 + 2**31 - 1)
    assert not advanced(5, 5) and not advanced(5, 3) and not advanced(1, 1 + 2**31)
