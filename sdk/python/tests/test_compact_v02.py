"""BHMS-Compact in v0.2 (spec/bhms/11-compact-binding.md; Rulings R52, R53 and the Task 9b deferrals).

* BHMS-CMP-052: an action's ``maxDurationMs`` is the endpoint's execution bound; the bridge bounds the operation by it plus
  a link allowance (computed from its link or configured), so a slow link no longer ends a successful action ``failed``
  (Ruling R41, Task 14 learning 3's neighbour).
* BHMS-CMP-036: a RESULT with ``evidence: measured`` makes the effect ``verified`` through fresh ``verifiedBy`` readings
  (Task 14 learning 3: ``move_joints``/``enable`` always completed ``unverified``).
* BHMS-OPS-072: a RESULT that contradicts an operation the bridge already ended is journaled and surfaced as an
  ``operation.late_report`` event.
* BHMS-CMP-050: a STOP token whose stop is unresolved is never reused before the next HELLO; a STOP sent again after a
  HELLO carries that HELLO's session.
"""

from __future__ import annotations

import asyncio
import copy
import math
import struct

from helpers.compact_rig import BENCH, FAST
from helpers.compact_script import Scripted, scripted_rig

from bhms.gateway.compact_bridge import MAX_WIRE_FRAME_BYTES, CompactBridge, Timing
from bhms.protocol.types import to_wire
from bhms.transport import compact as cp

PERSISTENT = cp.FLAG_PERSISTENT_EPOCH | cp.FLAG_FENCING | cp.FLAG_STOP_SUPPORTED


def sidecar(*, max_ms: int | None = None, measured: bool = False) -> dict:
    out = copy.deepcopy(BENCH)
    action = out["actions"]["set_level"]
    if max_ms is not None:
        action["maxDurationMs"] = max_ms
    if measured:
        action["completionEvidence"], action["verifiedBy"] = "measured", ["temp"]
    return out


def answer_after(delay: float, *, evidence: int = cp.EVIDENCE_REPORTED, state: int = cp.ST_COMPLETED):
    async def behave(ep, m):
        ep.say(cp.Status(m.handle, cp.ST_RUNNING, 0, cp.PROGRESS_UNKNOWN))
        await asyncio.sleep(delay)
        fields = struct.pack("<B", 1) if state == cp.ST_COMPLETED else b""
        ep.say(cp.Result(m.handle, state, evidence, 0, fields), kind=cp.TELEMETRY)

    return behave


async def invoke(client, wait_ms=5000):
    return to_wire(await client.actions_invoke("bench-rig", "set_level", {"value": 10}, wait_ms=wait_ms))["operation"]


def test_the_link_allowance_is_computed_from_the_link():  # BHMS-CMP-052
    timing = Timing()
    frame = MAX_WIRE_FRAME_BYTES * 10 / 9600
    assert timing.link_allowance_ms(9600) == math.ceil(1000 * (2 * 4 * (1.0 + 2 * frame) + 2.0))
    assert timing.link_allowance_ms(9600) > timing.link_allowance_ms(115200)  # a slower link is allowed more
    assert CompactBridge("x", "unix:/unused", BENCH, link_allowance_ms=1234).link_allowance_ms == 1234


async def test_a_result_after_max_duration_but_within_the_allowance_completes(tmp_path):  # BHMS-CMP-052
    script = Scripted(cp.digest8_of(sidecar(max_ms=200)), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=sidecar(max_ms=200), scripted=script) as (client, bridge, ep):
        assert bridge.device.bound_allowance_ms == FAST.link_allowance_ms(115200) > 400
        ep.on[cp.Invoke] = answer_after(0.6)  # 3x the endpoint's bound: link latency, not a slow action
        op = await invoke(client)
        assert op["state"] == "completed", op


async def test_a_measured_result_is_verified_by_a_fresh_verified_by_reading(tmp_path):  # BHMS-CMP-036
    description = sidecar(measured=True)
    script = Scripted(cp.digest8_of(description), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=description, scripted=script) as (client, bridge, ep):
        reads = []

        def value(e, m):
            reads.append(m)
            e.say(cp.Value(m.request, m.prop, cp.Q_VALID, 0, len(reads), 0, struct.pack("<f", 21.5)))

        ep.on[cp.Read] = value
        ep.on[cp.Invoke] = answer_after(0.01, evidence=cp.EVIDENCE_MEASURED)
        op = await invoke(client)
        assert op["state"] == "completed" and op["effect"] == "verified" and op["evidence"]["kind"] == "measured"
        assert "temp" in op["evidence"]["observations"] and reads and reads[-1].fresh
        ep.on[cp.Invoke] = answer_after(0.01, evidence=cp.EVIDENCE_REPORTED)  # the endpoint did not measure
        assert (await invoke(client))["effect"] == "unverified"


async def test_a_contradicting_result_after_the_end_is_a_late_report(tmp_path):  # BHMS-OPS-072
    script = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=script) as (client, bridge, ep):
        handles = []

        def refuse_then_complete(e, m):
            handles.append(m.handle)
            e.say(cp.Result(m.handle, cp.ST_FAILED, cp.EVIDENCE_REPORTED, 3))

        ep.on[cp.Invoke] = refuse_then_complete
        op = await invoke(client)
        assert op["state"] == "failed"
        ep.say(cp.Result(handles[0], cp.ST_COMPLETED, cp.EVIDENCE_MEASURED, 0, struct.pack("<B", 1)), kind=cp.TELEMETRY)
        for _ in range(100):
            events = to_wire(await client.events_read(types=["operation.late_report"]))["events"]
            if events:
                break
            await asyncio.sleep(0.02)
        assert events and events[0]["operationId"] == op["operationId"]
        assert events[0]["data"] == {"outcome": "completed", "evidence": "measured", "state": "failed"}
        again = to_wire(await client.operations_get(op["operationId"]))["operation"]
        assert again["state"] == "failed" and again["history"][-1]["kind"] == "correction"  # never changed (OPS-071)


async def test_an_unresolved_stops_token_is_not_reused_before_a_hello(tmp_path):  # BHMS-CMP-050
    script = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=script) as (client, bridge, ep):
        first: list[int] = []

        async def endpoint(e, m):
            e.say(cp.StopAck(cp.STOPACK_INITIATED, cp.EVIDENCE_NONE, 0, m.token))
            if not first:
                first.append(m.token)  # A is never confirmed in its bound
            elif m.token == first[0]:  # had the token been reused, A's late confirmation would confirm B
                e.say(cp.StopAck(cp.STOPACK_CONFIRMED, cp.EVIDENCE_MEASURED, 0, m.token), kind=cp.TELEMETRY)

        ep.on[cp.Stop] = endpoint
        a = to_wire(await client.stop("a", device_ids=["bench-rig"], wait_ms=3000))["stops"][0]
        assert a["outcome"] != "confirmed"
        bridge._stop_token = first[0] - 1 if first[0] > 1 else 255  # the counter has wrapped round to A's token
        b = to_wire(await client.stop("b", device_ids=["bench-rig"], wait_ms=3000))["stops"][0]
        tokens = [m.token for m in ep.of(cp.Stop)]
        assert tokens[-1] != first[0] and b["outcome"] != "confirmed"


async def test_a_stop_sent_again_after_a_hello_carries_that_hellos_session(tmp_path):  # BHMS-CMP-050
    script = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=script) as (client, bridge, ep):
        async def endpoint(e, m):
            e.say(cp.StopAck(cp.STOPACK_INITIATED, cp.EVIDENCE_NONE, 0, m.token))
            if e.epoch == 8:
                e.say(cp.StopAck(cp.STOPACK_CONFIRMED, cp.EVIDENCE_MEASURED, 0, m.token), kind=cp.TELEMETRY)

        ep.on[cp.Stop] = endpoint
        call = asyncio.create_task(client.stop("t", device_ids=["bench-rig"], wait_ms=4000))
        for _ in range(100):
            if ep.of(cp.Stop):
                break
            await asyncio.sleep(0.02)
        ep.epoch = 8  # the endpoint's persistent epoch advanced: its next HELLO says 8
        ep.say(cp.Status(1, cp.ST_RUNNING, 0, 0), session=8)
        stop = to_wire(await call)["stops"][0]
        sessions = [f.session for f in ep.frames if isinstance(f.message, cp.Stop)]
        assert stop["outcome"] == "confirmed" and sessions[0] == 7 and sessions[-1] == 8, sessions
