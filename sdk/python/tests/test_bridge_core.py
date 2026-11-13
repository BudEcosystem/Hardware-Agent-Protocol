"""The eight agent tools over a real device server (BHMS-AGT-001..050): results, refusals, keys and leases."""

from __future__ import annotations

import asyncio
import json

import pytest

from bhms import Canceled, DeviceServer, Policy, Range, token_digest
from bhms.bridges import AgentBridge, render, tool_definitions
from bhms.bridges.core import input_schema_for
from bhms.client.client import Client
from bhms.protocol import schema
from bhms.protocol.errors import BhmsError
from bhms.testing.conformance_device import build
from bhms.testing.memory import connect_in_process

RESULT_DEFS = {"bhms_describe": "DevicesDescribeResult", "bhms_read": "PropertiesReadResult", "bhms_find": "AgentFindData",
               "bhms_invoke": "ActionsInvokeResult", "bhms_operation": "OperationsWaitResult",
               "bhms_cancel": "OperationsCancelResult", "bhms_stop": "StopResult", "bhms_run_program": "ProgramsRunResult"}


@pytest.fixture
async def rig(tmp_path):
    srv, sim = build(state_dir=str(tmp_path))
    await srv.start()
    client = await Client.from_transport(await connect_in_process(srv.rpc), strict=True)
    bridge = AgentBridge(client, lease_ttl_ms=200)
    yield srv, sim, client, bridge
    await bridge.aclose()
    await client.close()
    await srv.close()


async def counter(client):
    return (await client.request("x-conformance/counters"))["counter"]


def check_result(name, result):
    """Every summary is one short line; successful results validate against the schema (BHMS-AGT-010)."""
    assert "\n" not in result.summary and len(result.summary) <= 200, result.summary
    if result.error is None:
        schema.validate(RESULT_DEFS[name], result.data)
        assert result.structured == result.data
    else:
        schema.validate("OperationError", result.error)
        assert result.structured == {"error": result.error} and result.is_error
        assert result.summary.startswith("Refused:") and result.error["hint"].split()[0] in result.summary


# ---------------------------------------------------------------------------------------------- tool set

def test_exactly_eight_tools_with_the_spec_names_and_annotations():  # AGT-001
    tools = tool_definitions()
    assert [t.name for t in tools] == ["bhms_find", "bhms_describe", "bhms_read", "bhms_invoke", "bhms_operation",
                                       "bhms_cancel", "bhms_stop", "bhms_run_program"]
    by = {t.name: t.annotations for t in tools}
    assert by["bhms_find"]["readOnlyHint"] and by["bhms_find"]["idempotentHint"]
    assert by["bhms_invoke"]["destructiveHint"] and by["bhms_invoke"]["idempotentHint"] is False
    assert by["bhms_stop"]["destructiveHint"] and by["bhms_stop"]["idempotentHint"]
    assert by["bhms_cancel"]["idempotentHint"] and by["bhms_operation"]["readOnlyHint"]


def test_input_schemas_are_the_normative_ones_without_top_level_one_of():  # AGT-001, AGT-050
    doc = schema.load_schema()
    for tool in tool_definitions():
        flat = tool.input_schema
        original = doc["$defs"][doc["x-bhms-agent-tools"][tool.name]["input"].rsplit("/", 1)[-1]]
        assert "oneOf" not in flat and flat["additionalProperties"] is False
        assert flat.get("required") == original.get("required") and set(flat["properties"]) == set(original["properties"])
        json.dumps(flat)  # self-contained: no dangling $ref outside its own $defs
        text = json.dumps(flat)
        for ref in {r.split("/")[-1] for r in __import__("re").findall(r'"\$ref": "([^"]+)"', text)}:
            assert ref in flat.get("$defs", {}), (tool.name, ref)
    assert "exactly one" in input_schema_for("bhms_stop").get("description", "") or "exactly one of" in next(
        t.description for t in tool_definitions() if t.name == "bhms_stop")


async def test_run_program_is_omitted_when_the_server_has_no_programs(tmp_path):  # AGT-001
    srv = DeviceServer("no-programs", state_dir=tmp_path, programs=False)
    d = srv.device("d-1", resources=["d-1"])
    d.report_alive()
    await srv.start()
    client = await Client.from_transport(await connect_in_process(srv.rpc))
    try:
        names = [t.name for t in AgentBridge(client).tool_definitions()]
        assert "bhms_run_program" not in names and len(names) == 7
        refused = await AgentBridge(client).call("bhms_run_program", {"program_digest": "sha256:" + "a" * 64, "arguments": {}})
        assert refused.is_error and refused.error["bhmsCode"] == "UNSUPPORTED"
    finally:
        await client.close()
        await srv.close()


async def test_programs_are_listed_only_with_the_registry(rig):  # AGT-001
    srv, sim, client, bridge = rig
    found = await bridge.call("bhms_find", {})
    check_result("bhms_find", found)
    assert found.data["programs"] == [] and "0 programs" in found.summary


# ---------------------------------------------------------------------------------------------- reading tools

async def test_find_describe_read_round_trip(rig):
    srv, sim, client, bridge = rig
    found = await bridge.call("bhms_find", {"capability": "bhms.liquid.*"})
    check_result("bhms_find", found)
    assert [d["deviceId"] for d in found.data["devices"]] == ["pump-1"] and "pump-1" in found.summary
    described = await bridge.call("bhms_describe", {"device_id": "pump-1"})
    check_result("bhms_describe", described)
    assert described.block.startswith('pump-1 "Conformance pump"') and "lease=required" in described.block
    assert render.estimate_tokens(described.block) <= 400
    assert described.text == f"{described.summary}\n{described.block}"
    read = await bridge.call("bhms_read", {"device_id": "pump-1", "property": "pressure"})
    check_result("bhms_read", read)
    assert read.summary.startswith("pump-1.pressure = 101.3 kPa (measured, valid,")
    fresh = await bridge.call("bhms_read", {"device_id": "pump-1", "property": "pressure", "fresh": True})
    assert fresh.error is None and "valid" in fresh.summary
    too_old = await bridge.call("bhms_read", {"device_id": "pump-1", "property": "pressure", "max_age_ms": 0})
    check_result("bhms_read", too_old)
    assert too_old.error["bhmsCode"] == "STALE" and "maxAgeMs" in too_old.summary


async def test_invalid_sensor_reads_say_not_to_act_on_them(rig):
    srv, sim, client, bridge = rig
    await client.request("x-conformance/inject", {"fault": "sensor_invalid"})
    read = await bridge.call("bhms_read", {"device_id": "pump-1", "property": "pressure"})
    assert read.error is None and "no usable value" in read.summary and "invalid" in read.summary and "do not act" in read.summary


async def test_unknown_device_and_property_are_refusals_with_hints(rig):
    srv, sim, client, bridge = rig
    for name, args in [("bhms_describe", {"device_id": "nope"}), ("bhms_read", {"device_id": "pump-1", "property": "nope"}),
                       ("bhms_operation", {"operation_id": "op-nope"})]:
        result = await bridge.call(name, args)
        check_result(name, result)
        assert result.error["hint"]


async def test_a_fresh_read_of_a_transaction_property_acquires_and_releases_its_lease(rig):  # AUTH-012, AGT-040
    srv, sim, client, bridge = rig
    read = await bridge.call("bhms_read", {"device_id": "axis-1", "property": "fifo", "fresh": True})
    assert read.error is None, read.summary
    assert bridge.stats.leases_acquired == 1 and bridge.stats.leases_released == 1 and not bridge._held


# ---------------------------------------------------------------------------------------------- invoke

async def test_invoke_completes_with_a_verified_summary_and_structured_result(rig):
    srv, sim, client, bridge = rig
    result = await bridge.call("bhms_invoke", {"device_id": "axis-1", "action": "move_to", "arguments": {"position": 12.5},
                                               "operation_key": "m-1"})
    check_result("bhms_invoke", result)
    assert result.summary == "axis-1.move_to " + result.data["operation"]["operationId"] + \
        " completed: position 12.5 mm (effect verified, " + result.summary.split("effect verified, ")[1]
    assert not result.is_error and result.data["replayed"] is False


async def test_without_an_operation_key_the_bridge_invents_none_and_says_not_retry_safe(rig):  # AGT-030
    srv, sim, client, bridge = rig
    result = await bridge.call("bhms_invoke", {"device_id": "axis-1", "action": "pulse", "arguments": {"count": 2}})
    assert result.data["operation"]["keyOrigin"] == "server" and result.summary.endswith("(not retry-safe: no operation_key)")


async def test_same_key_and_arguments_replay_without_acting_again(rig):  # AGT-031, AGT-011
    srv, sim, client, bridge = rig
    args = {"device_id": "axis-1", "action": "pulse", "arguments": {"count": 3}, "operation_key": "once"}
    first = await bridge.call("bhms_invoke", args)
    again = await bridge.call("bhms_invoke", args)
    assert again.data["replayed"] is True and "replayed" in again.summary
    assert again.data["operation"]["operationId"] == first.data["operation"]["operationId"]
    assert (await client.request("x-conformance/counters"))["pulses"] == 3
    changed = await bridge.call("bhms_invoke", {**args, "arguments": {"count": 4}})
    assert changed.error["bhmsCode"] == "KEY_CONFLICT" and "inspect" in changed.error["hint"]


async def test_bad_arguments_are_refused_before_any_request_that_could_act(rig):  # AGT-021
    srv, sim, client, bridge = rig
    before = await counter(client)
    ops_before = [o async for o in client.iter_operations()]
    cases = [({"position": 500}, "OUT_OF_RANGE", "arguments.position"), ({"position": 10, "extra": 1}, "INVALID_ARGUMENT",
                                                                        "extra"), ({}, "INVALID_ARGUMENT", "position"),
             ({"position": "far"}, "INVALID_ARGUMENT", "position"), ({"position": 10.05}, "INVALID_ARGUMENT", "position")]
    for arguments, code, field in cases:
        result = await bridge.call("bhms_invoke", {"device_id": "axis-1", "action": "move_to", "arguments": arguments})
        check_result("bhms_invoke", result)
        assert result.error["bhmsCode"] == code and field in result.error["field"] and "e.g. arguments" in result.error["hint"]
        assert result.error["mayHaveActed"] is False
    assert await counter(client) == before and [o async for o in client.iter_operations()] == ops_before
    unit = await bridge.call("bhms_invoke", {"device_id": "axis-1", "action": "move_to", "arguments": {
        "position": {"value": 1, "unit": "m"}}})
    assert unit.error["bhmsCode"] == "UNIT_MISMATCH" and "converted" in unit.error["message"]
    nothing = await bridge.call("bhms_invoke", {"device_id": "axis-1", "action": "levitate", "arguments": {}})
    assert nothing.error["bhmsCode"] == "UNKNOWN_ACTION" and "move_to" in nothing.error["hint"]


async def test_tool_arguments_are_validated_against_the_normative_schema(rig):  # AGT-021, AGT-002
    srv, sim, client, bridge = rig
    for name, args, needle in [
            ("bhms_invoke", {"device_id": "axis-1", "action": "pulse"}, "arguments"),
            ("bhms_invoke", {"device_id": "axis-1", "action": "pulse", "arguments": {"count": 1}, "lease_id": "lease-1"},
             "lease_id"),
            ("bhms_invoke", {"device_id": "axis-1", "action": "pulse", "arguments": {"count": 1}, "principal": "root"},
             "principal"),
            ("bhms_invoke", {"device_id": "axis-1", "action": "pulse", "arguments": {"count": 1}, "operation_key": "g-x"},
             "operation_key"),
            ("bhms_invoke", {"device_id": "axis-1", "action": "pulse", "arguments": {"count": 1}, "wait_ms": 99999}, "wait_ms"),
            ("bhms_find", {"text": ""}, "text"), ("bhms_read", {"device_id": "axis-1"}, "property")]:
        result = await bridge.call(name, args)
        assert result.is_error and result.error["bhmsCode"] == "INVALID_ARGUMENT" and needle in result.error["field"] + result.error[
            "message"], (name, args, result.error)
        assert "example" in result.error["hint"]
    assert await counter(client) == 0
    wrong = await bridge.call("bhms_invoke", [1])
    assert wrong.error["bhmsCode"] == "INVALID_ARGUMENT"


async def test_stop_and_run_program_need_exactly_one_selector(rig):
    srv, sim, client, bridge = rig
    both = await bridge.call("bhms_stop", {"device_ids": ["axis-1"], "all": True, "reason": "r"})
    none = await bridge.call("bhms_stop", {"reason": "r"})
    assert both.error["bhmsCode"] == none.error["bhmsCode"] == "INVALID_ARGUMENT" and "exactly one" in both.error["message"]
    assert (await bridge.call("bhms_run_program", {"arguments": {}})).error["bhmsCode"] == "INVALID_ARGUMENT"


async def test_require_verified_fails_an_unverified_effect(rig):
    srv, sim, client, bridge = rig
    await client.request("x-conformance/inject", {"fault": "encoder_disagrees"})
    result = await bridge.call("bhms_invoke", {"device_id": "axis-1", "action": "move_to", "arguments": {"position": 30},
                                               "operation_key": "v-1", "require_verified": True})
    assert result.is_error and result.data["operation"]["state"] == "failed"
    assert result.data["operation"]["error"]["bhmsCode"] == "UNVERIFIED"
    schema.validate("ActionsInvokeResult", result.data)


async def test_a_device_fault_says_outcome_unknown_and_includes_the_hint(rig):  # AGT-020
    srv, sim, client, bridge = rig
    result = await bridge.call("bhms_invoke", {"device_id": "axis-1", "action": "fault", "arguments": {}, "operation_key": "f-1"})
    assert result.is_error and result.data["operation"]["state"] == "failed" and result.data["operation"]["error"][
        "mayHaveActed"] is True
    assert "outcome unknown — check before retrying" in result.summary and "Next:" in result.summary
    assert "success" not in result.summary.lower() and "done" not in result.summary.lower()
    schema.validate("ActionsInvokeResult", result.data)  # structured content is the BHMS result, unchanged


async def test_wait_ms_defaults_and_is_capped(rig):  # AGT-032
    srv, sim, client, bridge = rig
    sent = []
    real = client.actions_invoke

    async def spy(*a, **kw):
        sent.append(kw["wait_ms"])
        return await real(*a, **kw)

    client.actions_invoke = spy
    for wait in (None, 60_000, 0):
        args = {"device_id": "axis-1", "action": "pulse", "arguments": {"count": 1}}
        if wait is not None:
            args["wait_ms"] = wait
        await bridge.call("bhms_invoke", args)
    assert sent == [5000, 60_000, 0] and bridge._wait({"wait_ms": 60_000}) == 60_000
    client.server.limits.max_wait_ms = 1500
    assert bridge._wait({"wait_ms": 60_000}) == 1500 and bridge._wait({}) == 1500


async def test_running_operations_tell_the_model_how_to_keep_waiting_and_cancel_is_a_request(rig):  # AGT-032
    srv, sim, client, bridge = rig
    started = await bridge.call("bhms_invoke", {"device_id": "axis-1", "action": "slow_move", "arguments": {"duration_ms": 5000},
                                                "operation_key": "slow", "wait_ms": 50})
    op_id = started.data["operation"]["operationId"]
    assert started.data["operation"]["state"] in ("dispatching", "running") and "bhms_operation" in started.summary
    assert op_id in started.summary and "wait_ms=30000" in started.summary
    waited = await bridge.call("bhms_operation", {"operation_id": op_id, "wait_ms": 10})
    check_result("bhms_operation", waited)
    canceled = await bridge.call("bhms_cancel", {"operation_id": op_id, "reason": "test"})
    check_result("bhms_cancel", canceled)
    assert "cancel" in canceled.summary
    final = await bridge.call("bhms_operation", {"operation_id": op_id, "wait_ms": 2000})
    assert final.data["operation"]["state"] == "canceled" and "canceled" in final.summary and not final.is_error


async def test_stop_reports_each_device_and_only_claims_confirmed(rig):
    srv, sim, client, bridge = rig
    stop = await bridge.call("bhms_stop", {"all": True, "reason": "test"})
    check_result("bhms_stop", stop)
    assert "axis-1 confirmed" in stop.summary and "pump-1 unsupported" in stop.summary and "stopped" not in stop.summary.split("(")[0]
    one = await bridge.call("bhms_stop", {"device_ids": ["axis-1"], "reason": "again"})
    assert one.summary.startswith("stop: axis-1 confirmed")
    missing = await bridge.call("bhms_stop", {"device_ids": ["ghost"], "reason": "x"})
    assert missing.is_error


async def test_transport_loss_is_a_refusal_not_an_exception(rig):
    srv, sim, client, bridge = rig
    await client.close()
    result = await bridge.call("bhms_invoke", {"device_id": "axis-1", "action": "pulse", "arguments": {"count": 1}})
    assert result.is_error and result.error["mayHaveActed"] is True and "outcome unknown" in result.summary


async def test_a_lost_result_is_recoverable_with_the_same_key(rig):  # AGT-031
    srv, sim, client, bridge = rig
    real = client.actions_invoke

    async def lost(*a, **kw):
        await real(*a, **kw)  # the server acted; the answer is lost
        raise BhmsError("DEADLINE_EXCEEDED", "no answer in time", may_have_acted=True, hint="reconcile")

    client.actions_invoke = lost
    args = {"device_id": "axis-1", "action": "pulse", "arguments": {"count": 7}, "operation_key": "lost-1"}
    result = await bridge.call("bhms_invoke", args)
    assert "outcome unknown" in result.summary and 'same operation_key "lost-1"' in result.error["hint"]
    client.actions_invoke = real
    again = await bridge.call("bhms_invoke", args)
    assert again.data["replayed"] is True and (await client.request("x-conformance/counters"))["pulses"] == 7
    keyless = await _keyless_lost(bridge, client, real)
    assert "no operation_key was given" in keyless.error["hint"]


async def _keyless_lost(bridge, client, real):
    async def lost(*a, **kw):
        raise BhmsError("DEADLINE_EXCEEDED", "no answer in time", may_have_acted=True, hint="reconcile")

    client.actions_invoke = lost
    try:
        return await bridge.call("bhms_invoke", {"device_id": "axis-1", "action": "pulse", "arguments": {"count": 1}})
    finally:
        client.actions_invoke = real


# ---------------------------------------------------------------------------------------------- leases

async def test_a_lease_is_acquired_on_exactly_the_needed_resources_and_released_when_settled(rig):  # AGT-040
    srv, sim, client, bridge = rig
    acquired = []
    real = client.leases_acquire

    async def spy(resources, ttl, **kw):
        acquired.append((list(resources), kw.get("wait_ms")))
        return await real(resources, ttl, **kw)

    client.leases_acquire = spy
    result = await bridge.call("bhms_invoke", {"device_id": "pump-1", "action": "dispense", "arguments": {"volume": 10}})
    assert result.error is None and result.data["operation"]["state"] == "completed", result.summary
    assert acquired == [(["pump-1/plunger"], 0)] and not bridge._held
    assert bridge.stats.leases_released == 1
    lease = (await real(["pump-1/plunger"], 5000)).lease  # free again: the bridge released its lease
    await client.leases_release(lease.lease_id)


async def test_the_lease_is_renewed_while_the_operation_runs_then_released(rig):  # AGT-040
    srv, sim, client, bridge = rig
    await client.request("x-conformance/inject", {"fault": "hang_next"})
    renewals = []
    real = client.leases_renew

    async def spy(lease_id, ttl, **kw):
        renewals.append(lease_id)
        return await real(lease_id, ttl, **kw)

    client.leases_renew = spy
    result = await bridge.call("bhms_invoke", {"device_id": "pump-1", "action": "dispense", "arguments": {"volume": 10},
                                               "operation_key": "hang", "wait_ms": 10})
    assert result.data["operation"]["state"] in ("dispatching", "running")
    await asyncio.sleep(0.7)  # several TTLs (200 ms): without renewal the lease would have expired
    assert len(renewals) >= 2 and bridge._held
    op_id = result.data["operation"]["operationId"]
    state = (await client.operations_get(op_id)).operation
    assert state.state in ("running", "dispatching") and state.lease_id
    await client.operations_cancel(op_id)
    await asyncio.sleep(0.5)
    assert not bridge._held and bridge.stats.leases_released == 1


async def test_with_a_key_the_first_request_carries_no_lease_and_a_retry_replays_under_a_held_lease(rig):  # AGT-041
    srv, sim, client, bridge = rig
    await client.request("x-conformance/inject", {"fault": "hang_next"})
    sent = []
    real = client.actions_invoke

    async def spy(*a, **kw):
        sent.append(kw.get("lease_id"))
        return await real(*a, **kw)

    client.actions_invoke = spy
    args = {"device_id": "pump-1", "action": "dispense", "arguments": {"volume": 10}, "operation_key": "k-41", "wait_ms": 10}
    first = await bridge.call("bhms_invoke", args)
    assert sent[0] is None and sent[1] is not None and len(sent) == 2  # LEASE_REQUIRED, then the identical request with the lease
    held = list(bridge._held)
    assert len(held) == 1 and first.data["operation"]["state"] in ("dispatching", "running")
    retry = await bridge.call("bhms_invoke", args)  # the bridge's own lease is still held: acquiring first would conflict
    assert retry.error is None and retry.data["replayed"] is True and "replayed" in retry.summary
    assert sent[2] is None and len(sent) == 3 and list(bridge._held) == held
    assert retry.data["operation"]["operationId"] == first.data["operation"]["operationId"]
    await client.request("x-conformance/inject", {"fault": "none"})
    await client.stop("test", scope="all")


async def test_a_refusal_before_admission_releases_the_lease(rig):
    srv, sim, client, bridge = rig
    await client.request("x-conformance/inject", {"fault": "sensor_invalid"})  # requiresFresh pressure is not met
    result = await bridge.call("bhms_invoke", {"device_id": "pump-1", "action": "dispense", "arguments": {"volume": 10},
                                               "operation_key": "no-pressure"})
    assert result.is_error and not bridge._held
    lease = (await client.leases_acquire(["pump-1/plunger"], 5000)).lease
    await client.leases_release(lease.lease_id)


# a two-principal device for contention

TOKENS = {"alice": "alice-token", "bob": "bob-token"}


async def test_a_lease_conflict_says_the_resource_is_in_use_and_when_it_expires(tmp_path):  # AGT-040
    policy = Policy({n: {"tokens": [token_digest(t)], "scopes": ["read", "lease", "invoke:arm-1/*", "stop"]}
                     for n, t in TOKENS.items()})
    srv = DeviceServer("contend", state_dir=tmp_path, policy=policy, lease_min_ttl_ms=50)
    arm = srv.device("arm-1", resources=["arm-1/motion"])
    arm.report_alive()

    @arm.action(effect="reversible", idempotency="absolute", requires_lease=True, max_duration_ms=1000, cancel="supported")
    async def move(ctx, x: Range(0, 100, unit="mm")) -> None:
        if await ctx.wait_cancelled(0.01):
            raise Canceled(effect="unverified")

    listener = await srv.listen("ws://127.0.0.1:0")
    url = f"ws://127.0.0.1:{listener.address[1]}"
    alice = await Client.connect(url, token=TOKENS["alice"])
    bob = await Client.connect(url, token=TOKENS["bob"])
    bridge = AgentBridge(bob)
    try:
        await alice.leases_acquire(["arm-1/motion"], 30_000)
        for key in (None, "ck-1"):
            args = {"device_id": "arm-1", "action": "move", "arguments": {"x": 5}}
            if key:
                args["operation_key"] = key
            result = await bridge.call("bhms_invoke", args)
            assert result.is_error and result.error["bhmsCode"] == "LEASE_CONFLICT", result.summary
            assert "in use by another principal" in result.error["hint"] and "expires" in result.error["hint"]
            assert not bridge._held
    finally:
        await bridge.aclose()
        await alice.close()
        await bob.close()
        await listener.close()
        await srv.close()


async def test_describe_and_programs_through_a_registered_program(rig):
    srv, sim, client, bridge = rig
    program = {"bhmsProgram": "2026-11-13", "name": "two_moves", "description": "Move twice.", "input": {
        "type": "object", "additionalProperties": False, "properties": {}}, "maxDurationMs": 20000, "steps": [
        {"kind": "invoke", "id": "a", "deviceId": "axis-1", "action": "move_to", "arguments": {"position": 5}},
        {"kind": "invoke", "id": "b", "deviceId": "axis-1", "action": "move_to", "arguments": {"position": 6}}]}
    registered = await client.programs_register(program)
    digest = registered.info.digest
    found = await bridge.call("bhms_find", {"text": "twice"})
    assert [p["digest"] for p in found.data["programs"]] == [digest] and "1 program" in found.summary
    run = await bridge.call("bhms_run_program", {"program_digest": digest, "arguments": {}, "operation_key": "prog-1"})
    check_result("bhms_run_program", run)
    assert run.data["operation"]["state"] == "completed" and "program" in run.summary
    # regression (found by this test): a program of verified steps carries the children's measured evidence (OPS-006)
    assert run.data["operation"]["effect"] == "verified" and set(run.data["operation"]["evidence"]["observations"]) == {
        "s1_position", "s2_position"}
    again = await bridge.call("bhms_run_program", {"program_digest": digest, "arguments": {}, "operation_key": "prog-1"})
    assert again.data["replayed"] is True and "replayed" in again.summary
    assert (await client.request("x-conformance/counters"))["counter"] == 2


# ---------------------------------------------------------------------------------------------- reading after acting

async def test_a_read_after_an_effect_is_the_post_effect_reading(tmp_path):  # BHMS-OBS-006 (found by the inspector pty test)
    srv = DeviceServer("stage", state_dir=tmp_path)
    dev = srv.device("stage-1", resources=["stage-1"])
    dev.report_alive()
    where = {"um": 0.0}

    @dev.property(unit="um", evidence="simulated")
    def position() -> float:
        return where["um"]

    @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=1000)
    async def move_to(ctx, target: Range(0, 200, unit="um")) -> None:  # the handler does not re-read the property itself
        where["um"] = target

    await srv.start()
    client = await Client.from_transport(await connect_in_process(srv.rpc))
    bridge = AgentBridge(client)
    try:
        before = (await client.properties_read("stage-1", "position")).observation
        assert before.value == 0
        done = await bridge.call("bhms_invoke", {"device_id": "stage-1", "action": "move_to", "arguments": {"target": 42.5},
                                                 "operation_key": "obs-6"})
        assert not done.is_error
        plain = (await client.properties_read("stage-1", "position")).observation  # no options
        assert plain.value == 42.5 and plain.sequence > before.sequence  # not the retained pre-move sample
        read = await bridge.call("bhms_read", {"device_id": "stage-1", "property": "position"})
        assert read.summary.startswith("stage-1.position = 42.5 um (simulated, valid,")
    finally:
        await bridge.aclose()
        await client.close()
        await srv.close()


async def test_push_only_properties_keep_their_retained_sample_after_an_effect(tmp_path):  # BHMS-OBS-006
    srv = DeviceServer("push-only", state_dir=tmp_path)
    dev = srv.device("d-1", resources=["d-1"])
    dev.report_alive()
    dev.property(name="level", schema=Range(0, 100, unit="%"), evidence="reported")

    @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=1000)
    async def poke(ctx) -> None:
        return None

    await srv.start()
    client = await Client.from_transport(await connect_in_process(srv.rpc))
    try:
        await dev.publish("level", 40)
        first = (await client.properties_read("d-1", "level")).observation
        assert (await client.actions_invoke("d-1", "poke", {}, wait_ms=1000)).operation.state == "completed"
        again = (await client.properties_read("d-1", "level")).observation
        assert again.value == 40 and again.sequence == first.sequence  # not re-acquirable: its age says how old it is
    finally:
        await client.close()
        await srv.close()


async def test_a_default_read_asks_for_a_recent_value_except_for_transaction_properties(rig):  # BHMS-AGT-014
    srv, sim, client, bridge = rig
    sent = []
    real = client.properties_read

    async def spy(device, prop, **kw):
        sent.append((prop, kw))
        return await real(device, prop, **kw)

    client.properties_read = spy
    await bridge.call("bhms_read", {"device_id": "pump-1", "property": "pressure"})
    await bridge.call("bhms_read", {"device_id": "pump-1", "property": "pressure", "max_age_ms": 5000})
    await bridge.call("bhms_read", {"device_id": "pump-1", "property": "pressure", "fresh": True})
    await bridge.call("bhms_read", {"device_id": "axis-1", "property": "fifo"})  # transaction: never made fresh by default
    assert sent[0] == ("pressure", {"max_age_ms": 1000, "fresh": None})
    assert sent[1] == ("pressure", {"max_age_ms": 5000, "fresh": None}) and sent[2] == ("pressure", {"max_age_ms": None, "fresh": True})
    assert sent[3] == ("fifo", {"max_age_ms": None, "fresh": None})
    assert "at most 1000 ms old" in next(t for t in bridge.tool_definitions() if t.name == "bhms_read").description


async def test_a_push_only_property_falls_back_to_its_retained_observation_with_its_age(tmp_path):  # BHMS-AGT-014
    srv = DeviceServer("push-only", state_dir=tmp_path)
    dev = srv.device("d-1", resources=["d-1"])
    dev.report_alive()
    dev.property(name="level", schema=Range(0, 100, unit="%"), evidence="reported")
    await srv.start()
    client = await Client.from_transport(await connect_in_process(srv.rpc))
    bridge = AgentBridge(client)
    try:
        await dev.publish("level", 40)
        await asyncio.sleep(1.2)
        read = await bridge.call("bhms_read", {"device_id": "d-1", "property": "level"})
        assert read.error is None and read.summary.startswith("d-1.level = 40 % (reported,") and " s old)" in read.summary
        explicit = await bridge.call("bhms_read", {"device_id": "d-1", "property": "level", "max_age_ms": 100})
        assert explicit.error["bhmsCode"] == "STALE"  # an explicit requirement is never silently relaxed
    finally:
        await client.close()
        await srv.close()
