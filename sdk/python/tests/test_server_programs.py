"""Bounded programs: validation before any step, execution over child operations, registry (BHMS-PRG-0xx)."""

from __future__ import annotations

import asyncio
import copy
import hashlib

import pytest

from bhms import Canceled, DeviceFault, DeviceServer, Policy, Range, token_digest
from bhms.client.client import Client
from bhms.protocol.canonical import digest
from bhms.protocol.errors import BhmsError

TOKENS = {"admin": "admin-token", "runner": "runner-token", "limited": "limited-token"}


def build(state_dir, **kw):
    policy = Policy({
        "admin": {"tokens": [token_digest(TOKENS["admin"])], "scopes": ["admin"]},
        "runner": {"tokens": [token_digest(TOKENS["runner"])],
                   "scopes": ["read", "lease", "programs:run", "invoke:focus-1/*"],
                   "bounds": {"focus-1/move_to": {"position": {"maximum": 1000}}}},
        "limited": {"tokens": [token_digest(TOKENS["limited"])],
                    "scopes": ["read", "programs:run", "invoke:focus-1/move_to"]},
    })
    srv = DeviceServer("programs", state_dir=state_dir, policy=policy, **kw)
    state = {"pos": 0.0, "calls": [], "sensor_ok": True, "gate": asyncio.Event()}
    focus = srv.device("focus-1", resources=["focus-1"])
    focus.report_alive()

    @focus.property(unit="um", evidence="measured")
    def position() -> float:
        return state["pos"]

    @focus.property(evidence="measured")
    def sharpness() -> Range(0, 1, unit="1"):
        if not state["sensor_ok"]:
            raise RuntimeError("camera unavailable")
        return max(0.0, 1 - abs(state["pos"] - 500) / 1000)

    @focus.action(effect="reversible", idempotency="absolute", max_duration_ms=2000)
    async def move_to(ctx, position: Range(0, 5000, unit="um")) -> {"position": "um"}:  # noqa: F821
        state["calls"].append(("move_to", position))
        state["pos"] = position
        return {"position": position}

    @focus.action(effect="reversible", idempotency="relative", max_duration_ms=2000)
    async def move_by(ctx, distance: Range(-100, 100, unit="um")) -> {"position": "um"}:  # noqa: F821
        state["calls"].append(("move_by", distance))
        state["pos"] += distance
        return {"position": state["pos"]}

    @focus.action(effect="irreversible", idempotency="relative", max_duration_ms=2000)
    async def mark(ctx) -> None:
        state["calls"].append(("mark",))

    @focus.action(effect="reversible", idempotency="relative", max_duration_ms=2000)
    async def jam(ctx) -> None:
        state["calls"].append(("jam",))
        raise DeviceFault("the focus drive jammed", partial="moved 3 um")

    @focus.action(effect="reversible", idempotency="relative", max_duration_ms=3000, cancel="supported")
    async def creep(ctx) -> None:
        state["calls"].append(("creep",))
        if await ctx.wait_cancelled(2.5):
            raise Canceled(effect="unverified", detail=ctx.cancel_reason)

    @focus.on_stop
    async def halt(ctx):
        state["calls"].append(("stop",))

    return srv, state


@pytest.fixture
async def env(tmp_path):
    made = []

    async def make(**kw):
        srv, state = build(tmp_path / f"st{len(made)}", **kw)
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


def program(**overrides):
    prog = {
        "bhmsProgram": "2026-11-13", "name": "focus_scan",
        "description": "Step the focus axis and record sharpness at each position.",
        "input": {"type": "object", "additionalProperties": False, "required": ["start", "steps"],
                  "properties": {"start": {"type": "number", "x-bhms-unit": "um", "minimum": 0, "maximum": 1000},
                                 "steps": {"type": "integer", "x-bhms-unit": "1", "minimum": 1, "maximum": 5}}},
        "maxDurationMs": 60000,
        "steps": [
            {"kind": "invoke", "deviceId": "focus-1", "action": "move_to", "arguments": {"position": "${start}"}},
            {"kind": "repeat", "times": "${steps}", "as": "i", "steps": [
                {"kind": "invoke", "deviceId": "focus-1", "action": "move_by", "arguments": {"distance": 10},
                 "saveAs": "moved"},
                {"kind": "read", "deviceId": "focus-1", "property": "sharpness", "fresh": True, "saveAs": "s"},
                {"kind": "assert", "predicate": {"op": "ne", "left": "${s.quality}", "right": "invalid"},
                 "message": "sharpness unavailable"}]}],
        "output": {"lastSharpness": "${s.value}", "position": "${moved.position}"},
    }
    prog.update(overrides)
    return prog


async def refused(coro) -> BhmsError:
    with pytest.raises(BhmsError) as info:
        await coro
    return info.value


async def test_program_runs_children_in_order_with_derived_keys(env):  # BHMS-PRG-010, PRG-015, PRG-016
    srv, state, c = await env()
    res = await c["runner"].programs_run(program=program(), arguments={"start": 480, "steps": 3},
                                         operation_key="scan-1", wait_ms=5000)
    op = res.operation
    assert op.state == "completed" and op.kind == "program" and op.program_digest == digest(program())
    assert op.result == {"lastSharpness": pytest.approx(0.99), "position": 510.0}
    # progress: steps completed and the worst-case total (inputs allow steps up to 5)
    assert op.effect == "unverified" and (op.progress.steps_completed, op.progress.steps_total) == (10, 16)
    assert state["calls"] == [("move_to", 480), ("move_by", 10), ("move_by", 10), ("move_by", 10)]
    full = (await c["runner"].operations_get(op.operation_id)).operation
    steps = [h for h in full.history if h.kind == "step"]
    assert len(steps) == 10 and steps[0].child_operation_id
    children = (await c["runner"].operations_list(parent_operation_id=op.operation_id)).operations
    assert len(children) == 4
    paths = ["0", "1/0/0", "1/1/0", "1/2/0"]
    expected = {"d-" + hashlib.sha256(f"{op.operation_id}/{p}".encode()).hexdigest()[:40] for p in paths}
    assert {ch.operation_key for ch in children} == expected
    assert all(ch.key_origin == "derived" and ch.parent_operation_id == op.operation_id for ch in children)


@pytest.mark.parametrize("mutate, code, field", [
    (lambda p: p["steps"][0].update(deviceId="ghost"), "UNKNOWN_DEVICE", "program.steps[0].deviceId"),
    (lambda p: p["steps"][0].update(action="fly"), "UNKNOWN_ACTION", "program.steps[0].action"),
    (lambda p: p["steps"][1]["steps"][1].update(property="nope"), "INVALID_ARGUMENT",
     "program.steps[1].steps[1].property"),
    (lambda p: p["steps"][0]["arguments"].update(position="${nowhere}"), "INVALID_ARGUMENT",
     "program.steps[0].arguments.position"),
    (lambda p: p["steps"][0]["arguments"].update(position="${moved.position}"), "INVALID_ARGUMENT",
     "program.steps[0].arguments.position"),  # defined later
    (lambda p: p["steps"][1]["steps"][0].update(saveAs="start"), "INVALID_ARGUMENT",
     "program.steps[1].steps[0].saveAs"),  # shadows an input
    (lambda p: p["steps"][1]["steps"][2].update(predicate={"not": {"not": {"not": {"not": {
        "op": "eq", "left": 1, "right": 1}}}}}), "INVALID_ARGUMENT", "program.steps[1].steps[2].predicate.not.not.not.not"),
    (lambda p: p["steps"][1]["steps"][0]["arguments"].update(distance=500), "OUT_OF_RANGE",
     "program.steps[1].steps[0].arguments.distance"),  # literal out of range
    (lambda p: p["input"]["properties"]["start"].update(maximum=5000), "OUT_OF_RANGE",
     "program.steps[0].arguments.position"),  # input exceeds the runner's envelope (policy max 1000)
    (lambda p: p["input"]["properties"]["steps"].update(maximum=2000), "OUT_OF_RANGE", "program.steps[1].times"),
    (lambda p: p["input"]["properties"]["steps"].update(minimum=0), "OUT_OF_RANGE", "program.steps[1].times"),
    (lambda p: p["input"]["properties"]["steps"].update(type="number"), "INVALID_ARGUMENT", "program.steps[1].times"),
    (lambda p: p["input"].update(required=["start"]), "OUT_OF_RANGE", "program.steps[1].times"),
    (lambda p: p.update(maxDurationMs=2000 + 5 * (2000 + 1000) - 1), "OUT_OF_RANGE", "program.maxDurationMs"),
    (lambda p: p["steps"].append({"kind": "frobnicate"}), "INVALID_ARGUMENT", "program.steps[2]"),
])
async def test_invalid_programs_are_refused_before_any_step(env, mutate, code, field):  # BHMS-PRG-001..005
    srv, state, c = await env()
    prog = copy.deepcopy(program())
    mutate(prog)
    err = await refused(c["runner"].request("programs/run", {"program": prog, "arguments": {"start": 1, "steps": 1},
                                                            "operationKey": "bad"}))
    assert err.code == code and err.may_have_acted is False
    assert err.field is not None and err.field.startswith(field)
    if field == "program.maxDurationMs":
        assert err.bound == 2000 + 5 * (2000 + 1000)  # the computed worst case
    assert state["calls"] == [] and (await c["runner"].operations_list()).operations == []


async def test_limits_are_enforced(env):  # BHMS-PRG-002 (§8.1 limits)
    srv, state, c = await env(program_limits={"maxSteps": 3})
    err = await refused(c["runner"].programs_run(program=program(), arguments={"start": 1, "steps": 1}))
    assert (err.code, err.field) == ("OUT_OF_RANGE", "program.steps")


async def test_authority_is_checked_before_the_first_step(env):  # BHMS-PRG-006, PRG-021
    srv, state, c = await env()
    err = await refused(c["limited"].programs_run(program=program(), arguments={"start": 1, "steps": 1}))
    assert err.code == "UNAUTHORIZED" and err.field == "program.steps[1].steps[0].action"
    info = (await c["admin"].programs_register(program())).info
    err = await refused(c["limited"].programs_run(digest=info.digest, arguments={"start": 1, "steps": 1}))
    assert err.code == "UNAUTHORIZED"  # registration grants nothing
    srv2_policy = {"tokens": [token_digest(TOKENS["runner"])], "scopes": ["read", "invoke:focus-1/*"]}
    srv.set_policy(Policy({"runner": srv2_policy}))
    err = await refused(c["runner"].programs_run(program=program(), arguments={"start": 1, "steps": 1}))
    assert err.code == "UNAUTHORIZED" and "programs:run" in err.hint
    assert state["calls"] == []


async def test_arguments_are_validated_against_the_program_input(env):  # BHMS-PRG-001
    srv, state, c = await env()
    err = await refused(c["runner"].programs_run(program=program(), arguments={"start": 1, "steps": 9}))
    assert (err.code, err.field) == ("OUT_OF_RANGE", "arguments.steps")


async def test_failing_step_records_partial_effects_and_stops(env):  # BHMS-PRG-011 (Task 4 acceptance)
    srv, state, c = await env()
    prog = program(steps=[
        {"kind": "invoke", "deviceId": "focus-1", "action": "move_to", "arguments": {"position": 100}},
        {"kind": "invoke", "deviceId": "focus-1", "action": "mark", "arguments": {}},
        {"kind": "invoke", "deviceId": "focus-1", "action": "jam", "arguments": {}},
        {"kind": "invoke", "deviceId": "focus-1", "action": "move_by", "arguments": {"distance": 1}},
        {"kind": "sleep", "durationMs": 10}], output={})
    op = (await c["runner"].programs_run(program=prog, arguments={"start": 1, "steps": 1}, wait_ms=5000)).operation
    assert op.state == "failed" and op.error.bhms_code == "DEVICE_FAULT" and op.error.may_have_acted
    assert "jammed" in op.error.message
    assert state["calls"] == [("move_to", 100), ("mark",), ("jam",)]  # steps 4-5 never started
    assert op.effect == "unknown"  # the jammed child's effect is unknown
    children = (await c["runner"].operations_list(parent_operation_id=op.operation_id)).operations
    assert sorted(ch.state for ch in children) == ["completed", "completed", "failed"]
    full = (await c["runner"].operations_get(op.operation_id)).operation
    assert len([h for h in full.history if h.kind == "step"]) == 3
    jam_child = next(ch for ch in children if ch.action == "jam")
    jam_full = (await c["runner"].operations_get(jam_child.operation_id)).operation
    assert any("moved 3 um" in (h.detail or "") for h in jam_full.history)


async def test_assert_and_wait_until(env):  # BHMS-PRG-013
    srv, state, c = await env()
    prog = program(steps=[{"kind": "assert", "predicate": {"op": "gt", "left": "${start}", "right": 10},
                           "message": "start must exceed 10"}], output={})
    op = (await c["runner"].programs_run(program=prog, arguments={"start": 5, "steps": 1}, wait_ms=2000)).operation
    assert op.state == "failed" and op.error.bhms_code == "STALE" and op.error.hint == "start must exceed 10"
    assert op.error.may_have_acted is False
    state["sensor_ok"] = False
    prog = program(steps=[{"kind": "waitUntil", "deviceId": "focus-1", "property": "sharpness", "timeoutMs": 200,
                           "pollMs": 20, "predicate": {"op": "ge", "left": "${observed.value}", "right": 0}}],
                   output={})
    op = (await c["runner"].programs_run(program=prog, arguments={"start": 5, "steps": 1}, wait_ms=3000)).operation
    assert op.state == "failed" and op.error.bhms_code == "DEADLINE_EXCEEDED"  # invalid samples never satisfy
    state["sensor_ok"] = True
    op = (await c["runner"].programs_run(program={**prog, "steps": [{**prog["steps"][0], "saveAs": "w"}],
                                                  "output": {"v": "${w.quality}"}},
                                         arguments={"start": 5, "steps": 1}, wait_ms=3000)).operation
    assert op.state == "completed" and op.result == {"v": "valid"}


async def test_program_deadline_is_enforced_at_run_time(env):  # BHMS-PRG-012
    srv, state, c = await env()
    prog = program(steps=[{"kind": "invoke", "deviceId": "focus-1", "action": "creep", "arguments": {}},
                          {"kind": "invoke", "deviceId": "focus-1", "action": "mark", "arguments": {}}],
                   output={}, maxDurationMs=60000)
    op = (await c["runner"].programs_run(program=prog, arguments={"start": 1, "steps": 1}, deadline_ms=200,
                                         wait_ms=5000)).operation
    assert op.state == "failed" and op.error.bhms_code == "DEADLINE_EXCEEDED"
    assert ("mark",) not in state["calls"]


async def test_cancel_and_stop_end_a_running_program(env):  # BHMS-PRG-014
    srv, state, c = await env()
    prog = program(steps=[{"kind": "invoke", "deviceId": "focus-1", "action": "creep", "arguments": {}},
                          {"kind": "invoke", "deviceId": "focus-1", "action": "mark", "arguments": {}}], output={})
    op = (await c["runner"].programs_run(program=prog, arguments={"start": 1, "steps": 1}, wait_ms=100)).operation
    assert op.state == "running"
    await c["runner"].operations_cancel(op.operation_id, reason="enough")
    done = (await c["runner"].operations_wait(op.operation_id, 5000)).operation
    assert done.state == "canceled" and done.cancel.state == "confirmed"
    child = (await c["runner"].operations_list(parent_operation_id=op.operation_id)).operations[0]
    assert child.state == "canceled" and ("mark",) not in state["calls"]
    op2 = (await c["runner"].programs_run(program=prog, arguments={"start": 1, "steps": 1}, wait_ms=100)).operation
    await c["admin"].stop("halt", device_ids=["focus-1"], wait_ms=1000)
    done2 = (await c["runner"].operations_wait(op2.operation_id, 5000)).operation
    assert done2.state == "canceled" and any(h.kind == "stop" for h in done2.history)
    assert state["calls"].count(("mark",)) == 0


async def test_registry_digest_and_replay_across_forms(env):  # BHMS-PRG-007, PRG-020, PRG-022
    srv, state, c = await env()
    err = await refused(c["runner"].programs_get("sha256:" + "0" * 64))
    assert (err.code, err.field) == ("INVALID_ARGUMENT", "digest")
    err = await refused(c["runner"].programs_run(digest="sha256:" + "0" * 64, arguments={}))
    assert (err.code, err.field) == ("INVALID_ARGUMENT", "digest")
    info = (await c["admin"].programs_register(program())).info
    assert info.digest == digest(program()) and info.effect == "reversible" and info.devices == ["focus-1"]
    assert info.worst_case_duration_ms == 2000 + 5 * (2000 + 1000) and info.max_executed_steps == 1 + 5 * 3
    again = (await c["admin"].programs_register(program())).info
    assert again == info
    got = await c["runner"].programs_get(info.digest)
    assert digest(got.program.model_dump(by_alias=True, exclude_unset=True)) == info.digest
    listed = (await c["runner"].programs_list()).programs
    assert [p.digest for p in listed] == [info.digest]
    first = await c["runner"].programs_run(program=program(), arguments={"start": 1, "steps": 1},
                                           operation_key="same", wait_ms=5000)
    by_digest = await c["runner"].programs_run(digest=info.digest, arguments={"start": 1, "steps": 1},
                                               operation_key="same")
    assert by_digest.replayed and by_digest.operation.operation_id == first.operation.operation_id
