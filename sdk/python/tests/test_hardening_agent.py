"""Task 7b group C: agent experience (Task 11 S1-S7, Task 6 minors)."""

from __future__ import annotations

import pytest

from bhms.bridges import AgentBridge, tool_definitions
from bhms.client.client import Client
from bhms.protocol import schema
from bhms.protocol.errors import BhmsError
from bhms.testing.conformance_device import build
from bhms.testing.memory import connect_in_process
from helpers.gateway_rig import rig as gateway_rig


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


# ---------------------------------------------------------------------------- C15: bhms_find and the devices/list text filter


async def _ids(client, **flt):
    return [d.device_id for d in (await client.devices_list(filter=flt)).devices]


async def test_the_text_filter_matches_ids_and_any_token_case_insensitively(rig):
    """Task 11 S1: ``bhms_find "facility-1"`` found nothing (ids were not searched) and a descriptive phrase found
    nothing (the whole phrase had to occur). A device matches when ANY word occurs in its id, name, summary, tags or
    capabilities."""
    _, _, client, _ = rig
    assert await _ids(client, text="AXIS-1") == ["axis-1"]                      # the device id, any case
    assert await _ids(client, text="pump-1") == ["pump-1"]
    assert await _ids(client, text="a syringe to dose my assay") == ["pump-1"]  # one word of a description is enough
    assert await _ids(client, text="a") == ["axis-1", "pump-1"]                 # a lone one-letter word is still a word
    assert await _ids(client, text="linear  SYRINGE") == ["axis-1", "pump-1"]   # OR over the words
    assert await _ids(client, text="bhms.axis") == ["axis-1"]                   # capabilities are searched
    assert await _ids(client, text="conformance") == ["axis-1", "pump-1"]       # tags, as before
    assert await _ids(client, text="spectrometer zebra") == []
    assert await _ids(client, text="syringe", capability="bhms.axis.*") == []   # filters still combine with AND


async def test_capability_star_means_any_capability(rig):  # S3: "*" was refused by a pattern error
    _, _, client, bridge = rig
    assert await _ids(client, capability="*") == ["axis-1", "pump-1"]
    found = await bridge.call("bhms_find", {"capability": "*"})
    assert not found.is_error and [d["deviceId"] for d in found.data["devices"]] == ["axis-1", "pump-1"]
    bad = await bridge.call("bhms_find", {"capability": "Not A Capability"})  # the pattern is in the tool schema now
    assert bad.error["bhmsCode"] == "INVALID_ARGUMENT" and bad.error["field"] == "capability"
    assert "pattern" in schema.load_schema()["$defs"]["AgentFindInput"]["properties"]["capability"]


async def test_find_with_no_match_says_how_many_devices_exist_and_how_to_list_them(rig):
    _, _, _, bridge = rig
    found = await bridge.call("bhms_find", {"text": "facility microscope"})
    assert not found.is_error and found.data["devices"] == [] and found.data["totalDevices"] == 2
    schema.validate("AgentFindData", found.data)
    assert found.summary.startswith("0 devices match") and "2 devices exist" in found.summary
    assert "call bhms_find with no arguments to list everything" in found.summary
    everything = await bridge.call("bhms_find", {})
    assert [d["deviceId"] for d in everything.data["devices"]] == ["axis-1", "pump-1"] and "totalDevices" not in everything.data
    # any word matches, so a phrase can match many devices ("for" occurs in "conformance"): the best match comes first
    ranked = await bridge.call("bhms_find", {"text": "the syringe pump for dosing"})
    assert [d["deviceId"] for d in ranked.data["devices"]] == ["pump-1", "axis-1"] and ranked.summary.startswith("2 devices")
    by_id = await bridge.call("bhms_find", {"text": "axis-1"})
    assert [d["deviceId"] for d in by_id.data["devices"]] == ["axis-1"]


def test_the_find_tool_says_that_no_arguments_lists_everything():
    find = next(t for t in tool_definitions() if t.name == "bhms_find")
    assert "no arguments" in find.description and "list" in find.description
    text = find.input_schema["properties"]["text"]["description"]
    assert "any" in text.lower() and "id" in text


# ---------------------------------------------------------------------------- C16: the unknown-device hint names candidates


async def test_unknown_device_hint_suggests_the_namespaced_id(tmp_path):
    """Task 11 S2: ``notice-1`` behind a gateway is ``notice/notice-1``; the refusal said only "no device"."""
    async with gateway_rig(tmp_path) as r:
        client = await r.client()
        with pytest.raises(BhmsError) as exc:
            await client.devices_describe("axis-1")
        assert exc.value.bhms_code == "UNKNOWN_DEVICE"
        assert "did you mean a/axis-1 or b/axis-1" in exc.value.hint and exc.value.bound == ["a/axis-1", "b/axis-1"]
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("AXIS-1", "move_to", {"target": 1})
        assert "a/axis-1" in exc.value.hint and exc.value.may_have_acted is False
        with pytest.raises(BhmsError) as exc:
            await client.devices_describe("nothing-like-it")
        assert "did you mean" not in exc.value.hint and exc.value.bound is None and "devices/list" in exc.value.hint
        bridge = AgentBridge(client)
        try:
            refused = await bridge.call("bhms_read", {"device_id": "axis-1", "property": "position"})
            assert refused.error["bhmsCode"] == "UNKNOWN_DEVICE" and "a/axis-1" in refused.summary
        finally:
            await bridge.aclose()


async def test_unknown_device_hint_never_names_a_device_the_principal_cannot_read(tmp_path):  # BHMS-DEV-010
    from helpers.gateway_rig import principals

    async with gateway_rig(tmp_path, principals_doc=principals(agent_scopes=["lease"])) as r:
        client = await r.client()
        with pytest.raises(BhmsError) as exc:
            await client.devices_describe("axis-1")
        assert exc.value.bhms_code == "UNKNOWN_DEVICE" and "a/axis-1" not in str(exc.value.to_operation_error())


async def test_unknown_device_hint_on_a_device_server(rig):
    _, _, client, _ = rig
    with pytest.raises(BhmsError) as exc:
        await client.devices_describe("Axis-1")
    assert exc.value.bhms_code == "UNKNOWN_DEVICE" and "did you mean axis-1" in exc.value.hint


# ---------------------------------------------------------------------------- C20: what a summary never cuts

from bhms.bridges import render  # noqa: E402


def _failed(**over):
    op = {"operationId": "op-0123456789abcdef0123456789abcdef", "kind": "action", "deviceId": "liquid-handler-on-bench-seven",
          "action": "aspirate_from_reservoir_slowly", "state": "failed", "cancel": {"state": "none"}, "effect": "unverified",
          "createdAt": "2026-11-14T10:00:00.000Z", "updatedAt": "2026-11-14T10:00:02.100Z",
          "error": {"bhmsCode": "DEVICE_FAULT", "message": "air detected in the tip " * 12, "mayHaveActed": True,
                    "retry": "after-reconcile", "hint": "read the tip volume sensor before deciding " * 6}}
    op.update(over)
    return op


@pytest.mark.parametrize("state, code", [("failed", "DEVICE_FAULT"), ("failed", "OUT_OF_RANGE"), ("rejected", "LEASE_EXPIRED"),
                                         ("failed", "DEADLINE_EXCEEDED")])
def test_a_failed_summary_never_cuts_the_bhms_code(state, code):
    """Task 6 minor: the code sat in the part of the summary that is shortened to fit 200 characters."""
    op = _failed(state=state)
    op["error"]["bhmsCode"] = code
    for replayed in (False, True):
        for keyed in (True, False):
            text = render.summarize_operation(op, replayed=replayed, keyed=keyed, show_key=True)
            assert len(text) <= render.SUMMARY_LIMIT and "\n" not in text
            assert f" {code}" in text, text
            assert state in text and op["operationId"] in text and "outcome unknown" in text


def test_a_short_failed_summary_reads_as_before():
    op = _failed(deviceId="pump-1", action="dispense", operationId="op-7f3a")
    op["error"].update(message="over-pressure", hint="vent the line")
    assert render.summarize_operation(op) == (
        'pump-1.dispense op-7f3a failed: DEVICE_FAULT: "over-pressure" Next: vent the line '
        "(effect unverified, 2.1 s; outcome unknown — check before retrying)")


async def test_the_cancel_pending_summary_keeps_its_whole_next_step(rig):
    """Task 6 minor: for a long device/action name the instruction to call bhms_operation was cut mid-call."""
    srv, _, client, bridge = rig
    lease = (await client.leases_acquire(["axis-1/motion"], 30_000)).lease
    op = (await client.actions_invoke("axis-1", "guard_cancel", {"duration_ms": 5000}, lease_id=lease.lease_id)).operation
    execution = srv.executor._running[op.operation_id]
    hold = execution.cancelled  # the handler would stop at once: keep the cancel pending by not letting it see the request
    execution.cancelled = __import__("asyncio").Event()
    try:
        result = await bridge.call("bhms_cancel", {"operation_id": op.operation_id, "reason": "x" * 400})
        assert not result.is_error and result.data["operation"]["cancel"]["state"] == "requested"
        assert f'Next: call bhms_operation(operation_id="{op.operation_id}", wait_ms=5000)' in result.summary
        assert len(result.summary) <= render.SUMMARY_LIMIT
    finally:
        hold.set()
        execution.cancelled = hold
        await client.operations_wait(op.operation_id, 5000)
    long_names = {"operationId": op.operation_id, "deviceId": "a-device-with-a-very-long-identifier-for-a-test/axis-1",
                  "action": "an_action_with_a_long_name", "state": "running", "effect": "unknown", "cancel": {"state": "requested"}}
    text = render.summarize_cancel(long_names)
    assert f'Next: call bhms_operation(operation_id="{op.operation_id}", wait_ms=5000)' in text
    assert len(text) <= render.SUMMARY_LIMIT and "cancel requested, not yet acknowledged" in text and "running" in text
    long_id = "op-" + "f" * 60  # an id too long to state twice: the instruction is still whole
    text = render.summarize_cancel({**long_names, "operationId": long_id})
    assert text.endswith("Next: call bhms_operation with this operation_id") and long_id in text
    assert len(text) <= render.SUMMARY_LIMIT


# ---------------------------------------------------------------------------- C21: the program grammar through bhms_describe


async def test_bhms_describe_serves_the_program_grammar_as_a_topic(rig):
    """Task 6 minor: function-tool hosts cannot read the MCP resource bhms://grammar/program that the tool text named."""
    from bhms.bridges.grammar import PROGRAM_GRAMMAR

    _, _, _, bridge = rig
    result = await bridge.call("bhms_describe", {"topic": "program-grammar"})
    assert not result.is_error and result.data == {"topic": "program-grammar", "text": PROGRAM_GRAMMAR}
    schema.validate("AgentTopicData", result.data)
    schema.validate("AgentDescribeData", result.data)
    assert result.block == PROGRAM_GRAMMAR and "\n" not in result.summary and "bhms_run_program" in result.summary
    output = result.function_output()  # what an OpenAI function tool returns: the grammar is in it, no resource needed
    schema.validate("AgentFunctionResult", output)
    assert output["signature"] == PROGRAM_GRAMMAR
    # device descriptions are unchanged, and exactly one of the two members is required
    device = await bridge.call("bhms_describe", {"device_id": "axis-1"})
    assert not device.is_error and device.data["description"]["deviceId"] == "axis-1"
    schema.validate("AgentDescribeData", device.data)
    for bad in ({}, {"device_id": "axis-1", "topic": "program-grammar"}, {"topic": "something-else"}):
        refused = await bridge.call("bhms_describe", bad)
        assert refused.error["bhmsCode"] == "INVALID_ARGUMENT", bad


def test_the_tool_texts_point_at_the_describe_topic_and_stay_within_the_token_budget():
    tools = {t.name: t for t in tool_definitions()}
    describe, run = tools["bhms_describe"], tools["bhms_run_program"]
    assert describe.input_schema["properties"]["topic"]["enum"] == ["program-grammar"]
    assert "required" not in describe.input_schema and "oneOf" not in describe.input_schema  # BHMS-AGT-051
    assert 'bhms_describe {"topic":"program-grammar"}' in run.description
    assert 'bhms_describe {"topic":"program-grammar"}' in run.input_schema["properties"]["program"]["description"]


async def test_a_malformed_program_refusal_names_the_describe_topic(rig):
    _, _, _, bridge = rig
    refused = await bridge.call("bhms_run_program", {"program": {"steps": "nope"}, "arguments": {}})
    assert refused.error["bhmsCode"] == "INVALID_ARGUMENT" and 'bhms_describe {"topic":"program-grammar"}' in refused.error["hint"]


async def test_the_topic_is_unsupported_where_programs_are_not_offered(tmp_path):
    from bhms import DeviceServer

    srv = DeviceServer("no-programs", state_dir=str(tmp_path), programs=False)
    srv.device("d-1", name="D").report_alive()
    await srv.start()
    client = await Client.from_transport(await connect_in_process(srv.rpc), strict=True)
    bridge = AgentBridge(client)
    try:
        refused = await bridge.call("bhms_describe", {"topic": "program-grammar"})
        assert refused.error["bhmsCode"] == "UNSUPPORTED" and "programs" in refused.error["message"]
    finally:
        await bridge.aclose()
        await client.close()
        await srv.close()


def test_programs_are_searched_with_the_same_word_rule_as_devices():
    """Fix round 1: bhms_find re-implemented any-word matching for programs and lacked the one-letter rule."""
    from bhms.server.handlers import text_score, word_score

    assert word_score("a homing routine", ("go_home", "Move every axis to its homing position.")) == 1  # "a" is ignored
    assert word_score("a", ("go_home", "Move every axis.")) == 1 and word_score("zebra", ("go_home", "Move.")) == 0
    summary = {"name": "Axis", "summary": "Linear axis", "tags": ["bench"], "capabilities": ["bhms.axis.linear"]}
    assert text_score("a LINEAR thing", summary, "axis-1") == word_score("a LINEAR thing", ("axis-1", "Axis", "Linear axis",
                                                                                           "bench", "bhms.axis.linear")) == 1
    import inspect

    from bhms.bridges.core import AgentBridge
    assert "word_score(" in inspect.getsource(AgentBridge._programs) and "casefold" not in inspect.getsource(AgentBridge._programs)


async def test_find_filters_programs_by_any_word_ignoring_one_letter_words(rig):
    _, _, client, bridge = rig
    program = {"bhmsProgram": "2026-11-13", "name": "go_home", "description": "Move the axis to zero.", "maxDurationMs": 10_000,
               "input": {"type": "object", "additionalProperties": False, "properties": {}},
               "steps": [{"kind": "invoke", "deviceId": "axis-1", "action": "move_to", "arguments": {"position": 0}}]}
    await client.programs_register(program)
    found = await bridge.call("bhms_find", {"text": "a routine to go_home"})
    assert [p["name"] for p in found.data["programs"]] == ["go_home"]
    none = await bridge.call("bhms_find", {"text": "a spectrometer"})  # "a" alone must not match "axis"
    assert none.data["programs"] == []
