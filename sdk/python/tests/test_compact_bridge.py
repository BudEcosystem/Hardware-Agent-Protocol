"""The compact bridge against the native C endpoint over a real socket (spec/bhms/11-compact-binding.md).

Every test boots ``sim_device`` (the LedAnalog example) or ``sim_bench`` (sdk/c/tests/host) from the C library built with cmake
and drives it through a bridge exactly as a gateway does: JSON-RPC to the bridge's device server, compact frames to the
endpoint.
"""

from __future__ import annotations

import asyncio
import copy

import pytest
from helpers.compact_rig import BENCH, LED, compact_rig, effects

from bhms.gateway.compact_bridge import CompactBridge
from bhms.protocol.errors import BhmsError
from bhms.testing.compact_endpoint import TO_DEVICE, TO_GATEWAY
from bhms.transport import compact as cp

pytestmark = pytest.mark.usefixtures("native")


def _queries(rig, handle):
    return [s for s in rig.wire.sent(cp.Query, TO_DEVICE) if s.message.handle == handle]


# ------------------------------------------------------------------------------------------------ HELLO and sidecar


async def test_hello_serves_the_device_with_the_sidecar_digest(tmp_path, native):  # BHMS-DEV-021, spec 11.2
    async with compact_rig(tmp_path, native, binary="sim_device") as rig:
        description = (await rig.client.devices_describe("bench-led")).description
        assert description.digest == "sha256:" + cp.digest8_of(LED).hex() + description.digest[len("sha256:") + 16:]
        assert description.digest.startswith("sha256:238ae39cebf1188c")  # what the LedAnalog firmware reports in HELLO
        hello = rig.bridge.hello
        assert hello.persistent and hello.epoch == 1 and hello.ring >= 4
        listed = [d.device_id async for d in rig.client.iter_devices()]
        assert listed == ["bench-led"]
        # the HELLO exchange on the wire: HELLO_REQ with session 0 first, then a byte-exact HELLO reply
        first = rig.wire.log[0]
        assert isinstance(first.message, cp.HelloReq) and first.session == 0
        reply = next(s for s in rig.wire.log if isinstance(s.message, cp.Hello))
        assert reply.message.digest8 == cp.digest8_of(LED) and reply.message.nonce == first.message.nonce


async def test_a_digest_mismatch_is_never_served(tmp_path, native, caplog):  # requirement 1
    other = copy.deepcopy(LED)
    other["description"] += " (a different firmware)"
    with caplog.at_level("ERROR", logger="bhms.gateway.compact"):
        async with compact_rig(tmp_path, native, binary="sim_device", sidecar=other, served=False) as rig:
            await rig.wait_for(lambda: rig.bridge.mismatch, what="the digest check")
            await asyncio.sleep(0.3)  # HELLO is repeated; still not served
            assert rig.bridge.device is None and not rig.bridge.up
            assert [d async for d in rig.client.iter_devices()] == []
            assert "not served" in caplog.text and cp.digest8_of(LED).hex() in caplog.text
            with pytest.raises(BhmsError) as refused:
                await rig.client.actions_invoke("bench-led", "led_set", {"on": True})
            assert refused.value.bhms_code == "UNKNOWN_DEVICE"
    assert rig.endpoint.count("LED") == 0


async def test_a_sidecar_that_breaks_the_layout_rules_is_refused_at_construction(tmp_path):  # DEV-070/071
    broken = copy.deepcopy(BENCH)
    broken["actions"]["move"]["compact"]["args"] = broken["actions"]["move"]["compact"]["args"][:1]
    with pytest.raises(ValueError, match="BHMS-DEV-070"):
        CompactBridge("x", "unix:/nonexistent", broken)


# ------------------------------------------------------------------------------------------------ invoke


async def test_invoke_completes_with_the_endpoints_result_and_exact_frames(tmp_path, native):
    async with compact_rig(tmp_path, native, binary="sim_device") as rig:
        op = await rig.invoke("led_set", {"on": True})
        assert op["state"] == "completed" and op["result"] == {"writes": 1}
        assert effects(rig, "LED") == ["LED 1"]
        sent = rig.wire.sent(cp.Invoke, TO_DEVICE)
        assert len(sent) == 1 and sent[0].message.handle == 1 and sent[0].message.args == b"\x01"
        assert len(sent[0].wire) == 24 + 10 + 1  # no padding (BHMS-CMP-003)
        assert sent[0].session == rig.bridge.epoch  # the frame carries the endpoint's boot epoch
        result = rig.wire.sent(cp.Result, TO_GATEWAY)[0]
        assert result.message == cp.Result(1, cp.ST_COMPLETED, cp.EVIDENCE_REPORTED, 0, b"\x01")
        second = await rig.invoke("led_set", {"on": False})
        assert second["result"] == {"writes": 2}
        assert [s.message.handle for s in rig.wire.sent(cp.Invoke)] == [1, 2]  # strictly increasing (CMP-030)


async def test_the_handle_is_journaled_with_its_epoch_before_the_invoke_is_sent(tmp_path, native):  # CMP-030
    async with compact_rig(tmp_path, native, binary="sim_device") as rig:
        rig.wire.hold(TO_DEVICE)  # the INVOKE reaches the wire but not the endpoint
        task = asyncio.ensure_future(rig.invoke("led_set", {"on": True}, key="k1", wait_ms=100))
        await rig.wait_for(lambda: rig.wire.sent(cp.Invoke), what="the INVOKE on the wire")
        op_id = (await rig.client.operations_list(device_id="bench-led")).operations[0].operation_id
        info = rig.bridge._info(op_id)
        assert (info.handle, info.epoch, info.persistent) == (1, 1, True)
        rig.wire.release(TO_DEVICE)
        assert (await task)["state"] in ("running", "dispatching", "completed")


async def test_args_the_wire_cannot_carry_are_refused_before_anything_is_sent(tmp_path, native):  # CMP-010
    async with compact_rig(tmp_path, native) as rig:
        for args, code in (({"value": 50.05}, "INVALID_ARGUMENT"), ({"value": 100.5}, "OUT_OF_RANGE")):
            with pytest.raises(BhmsError) as refused:
                await rig.invoke("set_level", args)
            assert refused.value.bhms_code == code  # caught by the description's multipleOf / bounds (DEV-071) already
        assert not rig.wire.sent(cp.Invoke)
        # past the description's validator: the codec's own refusal is a proven failure, nothing on the wire
        spec = rig.bridge.device.actions["set_level"]
        assert spec.input["properties"]["value"]["multipleOf"] == 0.1
        assert effects(rig, "SET") == []


async def test_scaled_values_cross_the_wire_exactly_and_results_decode_with_the_scale(tmp_path, native):  # CMP-010, 11.4
    async with compact_rig(tmp_path, native) as rig:
        op = await rig.invoke("set_level", {"value": 50.1})
        assert op["state"] == "completed" and op["result"] == {"writes": 1}
        assert effects(rig, "SET") == ["SET 501 0"]
        assert rig.wire.sent(cp.Invoke)[0].message.args == (501).to_bytes(2, "little")
        lease = await rig.lease("bench-rig/axis")
        moved = await rig.invoke("move", {"duration_ms": 30, "target": -12.34}, lease=lease)
        assert moved["state"] == "completed" and moved["result"] == {"reached": -12.34}
        assert rig.wire.sent(cp.Invoke)[1].message.args == (30).to_bytes(2, "little") + (-1234).to_bytes(2, "little", signed=True)


async def test_failures_and_refusals_are_reported_with_the_right_proof(tmp_path, native):  # ERROR table, 11.2
    async with compact_rig(tmp_path, native) as rig:
        failed = await rig.invoke("probe", {"mode": 1})
        assert failed["state"] == "failed" and failed["error"]["bhmsCode"] == "DEVICE_FAULT"
        assert failed["error"]["mayHaveActed"] is True and "fault 7" in failed["error"]["message"]
        rejected = await rig.invoke("probe", {"mode": 2})  # ERROR PRECONDITION: guaranteed not started
        assert rejected["state"] == "failed" and rejected["error"]["bhmsCode"] == "STALE"
        assert rejected["error"]["mayHaveActed"] is False and rejected["effect"] == "none"
        assert "PRECONDITION" in rejected["error"]["message"] and "detail 9" in rejected["error"]["message"]
        done = await rig.invoke("probe", {"mode": 0})
        assert done["state"] == "completed" and done["result"] == {"n": 1}


async def test_a_retransmitted_invoke_is_answered_from_the_ring_not_run_twice(tmp_path, native):  # CMP-031/032/033/035
    async with compact_rig(tmp_path, native) as rig:
        # The RESULT is lost; the endpoint is persistent, so the bridge retransmits the same handle with an identical payload.
        rig.wire.drop(TO_GATEWAY, match=lambda m: isinstance(m, cp.Result))
        op = await rig.invoke("set_level", {"value": 10.0})
        assert op["state"] == "completed" and op["result"] == {"writes": 1}
        invokes = rig.wire.sent(cp.Invoke, TO_DEVICE)
        assert len(invokes) == 2 and invokes[0].message == invokes[1].message  # same handle, identical payload
        assert effects(rig, "SET") == ["SET 100 0"]  # executed once
        results = rig.wire.sent(cp.Result, TO_GATEWAY)
        assert len(results) == 2 and results[0].message == results[1].message  # sent again from the ring
        assert not rig.wire.sent(cp.Query)


async def test_a_non_persistent_endpoint_is_never_sent_the_invoke_again(tmp_path, native):  # CMP-033
    async with compact_rig(tmp_path, native, epoch=False) as rig:
        assert not rig.bridge.persistent
        rig.wire.drop(TO_GATEWAY, match=lambda m: isinstance(m, cp.Result))
        op = await rig.invoke("set_level", {"value": 10.0})
        # QUERY instead of a retransmit: the endpoint's ring still has the handle, so the RESULT is found
        assert len(rig.wire.sent(cp.Invoke, TO_DEVICE)) == 1
        assert rig.wire.sent(cp.Query, TO_DEVICE)[0].message.handle == 1
        assert op["state"] in ("running", "dispatching", "completed")
        done = await rig.client.operations_wait(op["operationId"], 3000)
        assert done.operation.state == "completed" and done.operation.result == {"writes": 1}
        assert effects(rig, "SET") == ["SET 100 0"]


async def test_lost_replies_without_end_leave_the_operation_unknown_after_bounded_retransmits(tmp_path, native):  # OPS-004
    async with compact_rig(tmp_path, native) as rig:
        rig.wire.hold(TO_GATEWAY)  # nothing the endpoint says reaches the bridge
        op = await rig.invoke("set_level", {"value": 20.0}, wait_ms=4000)
        assert op["state"] == "unknown" and op["error"]["bhmsCode"] == "DEADLINE_EXCEEDED"
        assert op["error"]["mayHaveActed"] is True and op["effect"] == "unknown"
        invokes = rig.wire.sent(cp.Invoke, TO_DEVICE)
        assert len(invokes) == 1 + rig.bridge.timing.retries  # persistent endpoint: bounded identical retransmits
        assert len({s.message for s in invokes}) == 1 and not _queries(rig, 1)
        assert effects(rig, "SET") == ["SET 200 0"]  # the ring answered the retransmits without running it again
        # unknown inhibits new work on its resources (BHMS-OPS-042)
        with pytest.raises(BhmsError) as inhibited:
            await rig.invoke("set_level", {"value": 30.0})
        assert inhibited.value.bhms_code == "STALE" and op["operationId"] in inhibited.value.message


async def test_silence_from_a_non_persistent_endpoint_is_only_ever_asked_about_never_resent(tmp_path, native):  # CMP-033
    async with compact_rig(tmp_path, native, epoch=False) as rig:
        rig.wire.hold(TO_GATEWAY)
        op = await rig.invoke("set_level", {"value": 20.0}, wait_ms=4000)
        assert op["state"] == "unknown"
        assert len(rig.wire.sent(cp.Invoke, TO_DEVICE)) == 1  # never retransmitted
        assert len(_queries(rig, 1)) >= rig.bridge.timing.retries  # it asked instead
        assert effects(rig, "SET") == ["SET 200 0"]


async def test_unknown_is_reconciled_by_query_in_the_same_epoch(tmp_path, native):  # CMP-034, OPS-005
    async with compact_rig(tmp_path, native, epoch=False) as rig:
        rig.wire.hold(TO_GATEWAY)
        op = await rig.invoke("set_level", {"value": 20.0}, wait_ms=4000)
        assert op["state"] == "unknown"
        queries_before = len(rig.wire.sent(cp.Query, TO_DEVICE))
        rig.wire.release(TO_GATEWAY, deliver=False)  # the earlier replies are lost for good
        rig.bridge._kick_reconcile()
        settled = await rig.wait_for(lambda: _settled(rig, op["operationId"]), what="reconciliation")
        assert settled["state"] == "completed" and settled["result"] == {"writes": 1}
        history = rig.bridge.server.journal.get(op["operationId"]).wire(history=True)["history"]
        assert any(h["kind"] == "reconciliation" and "RESULT" in h.get("detail", "") for h in history)
        assert len(rig.wire.sent(cp.Query, TO_DEVICE)) > queries_before
        assert effects(rig, "SET") == ["SET 200 0"]  # still executed exactly once


async def _settled(rig, op_id):
    op = await rig.operation(op_id)
    return op if op["state"] not in ("unknown", "running", "dispatching") else None


# ------------------------------------------------------------------------------------------------ reads


async def test_reads_decode_values_with_quality_epoch_and_sequence(tmp_path, native):  # CMP-060
    async with compact_rig(tmp_path, native) as rig:
        first = (await rig.client.properties_read("bench-rig", "level", fresh=True)).observation
        assert first.value == 0 and first.quality == "valid" and first.evidence == "reported"
        assert first.epoch == "compact:1" and first.sequence == 1 and first.age_ms is not None
        await rig.invoke("set_level", {"value": 12.5})
        second = (await rig.client.properties_read("bench-rig", "level", fresh=True)).observation
        assert second.value == 125 and second.sequence == 2
        scaled = (await rig.client.properties_read("bench-rig", "offset", fresh=True)).observation
        assert scaled.value == -12.3 and scaled.unit == "%"
        temp = (await rig.client.properties_read("bench-rig", "temp", fresh=True)).observation
        assert temp.value == 21.5 and temp.quality == "valid"


async def test_a_disconnected_sensor_reads_invalid_without_a_substituted_value(tmp_path, native):  # CMP-060
    async with compact_rig(tmp_path, native) as rig:
        await rig.invoke("sensor", {"connected": False})
        temp = (await rig.client.properties_read("bench-rig", "temp", fresh=True)).observation
        assert temp.quality == "invalid" and temp.value is None
        value = rig.wire.sent(cp.Value, TO_GATEWAY)[-1].message
        assert value.quality == cp.Q_INVALID and value.raw == b""  # no value bytes on the wire
        await rig.invoke("sensor", {"connected": True})
        again = (await rig.client.properties_read("bench-rig", "temp", fresh=True)).observation
        assert again.quality == "valid" and again.value == 21.5
