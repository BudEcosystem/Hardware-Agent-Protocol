"""The OpenAI adapter: both tool shapes, flattened schemas, and the agent loop on recorded responses (no network)."""

from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path

import pytest

from bhms.bridges import AgentBridge, tool_definitions
from bhms.bridges.openai_tools import SYSTEM_PROMPT, load_api_key, run_agent, tools_for_openai
from bhms.client.client import Client
from bhms.protocol import schema
from bhms.testing.conformance_device import build
from bhms.testing.memory import connect_in_process

RECORDED = Path(__file__).parent / "recorded"


def recording(name: str) -> list[dict]:
    return json.loads((RECORDED / name).read_text())


class FakeLLM:
    """Replays recorded responses and records every request it receives (the SDK surface the loop needs)."""

    def __init__(self, responses: list[dict]) -> None:
        self.queue = copy.deepcopy(responses)
        self.requests: list[dict] = []
        outer = self

        class Responses:
            async def create(self, **kw):
                return outer._next("responses", kw)

        class Completions:
            async def create(self, **kw):
                return outer._next("chat", kw)

        class Chat:
            completions = Completions()

        self.responses, self.chat = Responses(), Chat()

    def _next(self, api: str, request: dict) -> dict:
        self.requests.append(copy.deepcopy(request))
        assert self.queue, f"unexpected extra {api} request"
        return self.queue.pop(0)


@pytest.fixture
async def rig(tmp_path):
    srv, sim = build(state_dir=str(tmp_path))
    await srv.start()
    client = await Client.from_transport(await connect_in_process(srv.rpc), strict=True)
    yield srv, sim, client
    await client.close()
    await srv.close()


# ---------------------------------------------------------------------------------------------- shapes

def test_both_api_shapes_carry_the_same_names_descriptions_and_schemas():  # AGT-050
    flat = tools_for_openai()
    nested = tools_for_openai(api="chat")
    mcp_like = tool_definitions()
    assert [t["name"] for t in flat] == [t.name for t in mcp_like] and len(flat) == 8
    for responses_tool, chat_tool, ref in zip(flat, nested, mcp_like, strict=True):
        assert set(responses_tool) == {"type", "name", "description", "parameters", "strict"} and responses_tool["type"] == "function"
        assert chat_tool["type"] == "function" and set(chat_tool) == {"type", "function"}
        fn = chat_tool["function"]
        assert (fn["name"], fn["description"], fn["parameters"]) == (ref.name, ref.description, ref.input_schema)
        assert (responses_tool["name"], responses_tool["description"], responses_tool["parameters"]) == (
            ref.name, ref.description, ref.input_schema)
        assert responses_tool["strict"] is False and fn["strict"] is False  # free-form arguments/program: never strict
        assert "oneOf" not in responses_tool["parameters"] and "anyOf" not in responses_tool["parameters"]
        assert responses_tool["parameters"]["type"] == "object"
    with pytest.raises(ValueError, match="api must be"):
        tools_for_openai(api="legacy")


async def test_tools_follow_the_server_capabilities(rig, tmp_path):
    srv, sim, client = rig
    assert len(tools_for_openai(client)) == 8 and len(tools_for_openai(AgentBridge(client))) == 8
    client.server.capabilities.programs = None
    assert [t["name"] for t in tools_for_openai(client)] == [t.name for t in tool_definitions()][:7]


def test_the_exactly_one_rule_survives_flattening_in_the_description_and_is_enforced():
    stop = next(t for t in tools_for_openai() if t["name"] == "bhms_stop")
    assert "exactly one of device_ids or all" in stop["description"]
    run = next(t for t in tools_for_openai() if t["name"] == "bhms_run_program")
    assert "exactly one of program or program_digest" in run["description"]


# ---------------------------------------------------------------------------------------------- loops

async def test_responses_loop_runs_three_tool_calls_and_threads_results_back(rig):
    srv, sim, client = rig
    llm = FakeLLM(recording("openai_responses_3step.json"))
    run = await run_agent(client, "gpt-5.4-mini", "Move axis-1 to 25 mm.", budget=20_000, llm=llm)
    assert run.stopped == "final" and run.final_text == "axis-1 is at 25 mm (effect verified by the encoder)."
    assert [s.tool for s in run.steps] == ["bhms_find", "bhms_describe", "bhms_invoke"] and not any(s.is_error for s in run.steps)
    assert run.requests == 4 and run.tokens == 1960 + 2130 + 2945 + 3320
    assert "completed: position 25 mm (effect verified" in run.steps[2].summary
    assert (await client.request("x-conformance/counters"))["counter"] == 1  # the device moved exactly once
    first, second, third, fourth = llm.requests
    assert first["input"] == [{"role": "user", "content": "Move axis-1 to 25 mm."}] and first["instructions"] == SYSTEM_PROMPT
    assert first["tools"] == tools_for_openai(client) and "previous_response_id" not in first
    assert first["parallel_tool_calls"] is False and first["model"] == "gpt-5.4-mini"
    for request, previous in ((second, "resp_a1"), (third, "resp_a2"), (fourth, "resp_a3")):
        assert request["previous_response_id"] == previous and request["tools"] == first["tools"]
    outputs = [r["input"][0] for r in (second, third, fourth)]
    assert [o["call_id"] for o in outputs] == ["call_a1", "call_a2", "call_a3"] and all(
        o["type"] == "function_call_output" for o in outputs)
    for output in outputs:
        parsed = json.loads(output["output"])
        schema.validate("AgentFunctionResult", parsed)
        assert "\n" not in parsed["summary"]
    described = json.loads(outputs[1]["output"])
    assert described["signature"].startswith('axis-1 "Conformance axis"') and "data" in described


async def test_chat_loop_uses_the_chat_completions_shape(rig):
    srv, sim, client = rig
    llm = FakeLLM(recording("openai_chat_3step.json"))
    run = await run_agent(client, "gpt-4.1-mini", "Move axis-1 to 25 mm.", budget=20_000, llm=llm, api="chat")
    assert run.stopped == "final" and run.final_text.startswith("axis-1 is at 25 mm") and run.api == "chat"
    assert [s.tool for s in run.steps] == ["bhms_find", "bhms_describe", "bhms_invoke"] and run.requests == 4
    first, *_, last = llm.requests
    assert first["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT} and first["tools"] == tools_for_openai(client, api="chat")
    roles = [m["role"] for m in last["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "tool", "assistant", "tool"]
    assistant = last["messages"][-2]
    assert assistant["tool_calls"][0]["function"]["name"] == "bhms_invoke" and assistant["tool_calls"][0]["id"] == "call_b3"
    tool = last["messages"][-1]
    assert tool["tool_call_id"] == "call_b3" and json.loads(tool["content"])["data"]["operation"]["state"] == "completed"
    assert "max_completion_tokens" in first and "max_output_tokens" not in first


async def test_the_budget_is_a_ceiling_never_exceeded(rig):
    srv, sim, client = rig
    for api, name in (("responses", "openai_responses_3step.json"), ("chat", "openai_chat_3step.json")):
        for budget in range(200, 12_000, 150):
            llm = FakeLLM(recording(name))
            run = await run_agent(client, "m", "Move axis-1.", budget=budget, llm=llm, api=api)
            assert run.tokens <= budget, (api, budget, run.tokens, run.stopped)
            for request in llm.requests:  # the output cap never lets a request alone pass what is left
                assert request.get("max_output_tokens", request.get("max_completion_tokens")) <= budget
    llm = FakeLLM(recording("openai_responses_3step.json"))
    tiny = await run_agent(client, "m", "x", budget=1000, llm=llm)  # cannot even pay for the tools: no request, no action
    assert tiny.stopped == "budget" and tiny.requests == 0 and tiny.steps == [] and llm.requests == []


async def test_a_budget_stop_never_executes_a_call_it_cannot_afford_to_see(rig):
    srv, sim, client = rig
    llm = FakeLLM(recording("openai_responses_3step.json"))
    run = await run_agent(client, "gpt-5.4-mini", "Move axis-1.", budget=5000, llm=llm)
    assert run.stopped == "budget" and run.tokens <= 5000 and (await client.request("x-conformance/counters"))["counter"] == 0
    assert [s.tool for s in run.steps] == ["bhms_find", "bhms_describe"]


async def test_the_output_cap_follows_the_remaining_budget(rig):
    srv, sim, client = rig
    llm = FakeLLM(recording("openai_responses_3step.json"))
    await run_agent(client, "gpt-5.4-mini", "Move axis-1.", budget=20_000, llm=llm, max_output_tokens=5000)
    caps = [r["max_output_tokens"] for r in llm.requests]
    assert caps[0] == 5000 and all(0 < c <= 5000 for c in caps)
    low = FakeLLM(recording("openai_responses_3step.json"))
    await run_agent(client, "gpt-5.4-mini", "Move axis-1.", budget=7000, llm=low, max_output_tokens=5000)
    assert low.requests[0]["max_output_tokens"] < 5000  # what is left after the estimated input of tools and task


async def test_max_steps_stops_before_acting_again(rig):
    srv, sim, client = rig
    run = await run_agent(client, "gpt-5.4-mini", "Move axis-1.", budget=20_000, llm=FakeLLM(recording("openai_responses_3step.json")),
                          max_steps=2)
    assert run.stopped == "max_steps" and len(run.steps) == 2 and (await client.request("x-conformance/counters"))["counter"] == 0


async def test_refusals_reach_the_model_as_errors_and_the_loop_continues(rig):
    srv, sim, client = rig
    responses = recording("openai_responses_3step.json")
    responses[2]["output"][0]["arguments"] = json.dumps({"device_id": "axis-1", "action": "move_to", "arguments": {"position": 900}})
    llm = FakeLLM(responses)
    run = await run_agent(client, "gpt-5.4-mini", "Move axis-1.", budget=20_000, llm=llm)
    assert run.steps[2].is_error and run.steps[2].summary.startswith("Refused:") and run.stopped == "final"
    sent = json.loads(llm.requests[3]["input"][0]["output"])
    schema.validate("AgentFunctionResult", sent)
    assert sent["error"]["bhmsCode"] == "OUT_OF_RANGE" and "data" not in sent
    assert (await client.request("x-conformance/counters"))["counter"] == 0


async def test_malformed_tool_arguments_become_a_refusal_not_a_crash(rig):
    srv, sim, client = rig
    responses = recording("openai_responses_3step.json")
    responses[1]["output"][0]["arguments"] = "{not json"
    run = await run_agent(client, "gpt-5.4-mini", "Move axis-1.", budget=20_000, llm=FakeLLM(responses))
    assert run.steps[1].is_error and "Refused:" in run.steps[1].summary


async def test_an_unknown_tool_name_is_refused_with_the_valid_names(rig):
    srv, sim, client = rig
    responses = recording("openai_responses_3step.json")
    responses[0]["output"][-1]["name"] = "bhms_teleport"
    run = await run_agent(client, "gpt-5.4-mini", "x", budget=20_000, llm=FakeLLM(responses))
    assert run.steps[0].is_error and "bhms_find" in run.steps[0].summary


async def test_leases_acquired_for_the_model_are_released_when_the_loop_ends(rig):
    srv, sim, client = rig
    responses = recording("openai_responses_3step.json")
    responses[2]["output"][0]["arguments"] = json.dumps({"device_id": "pump-1", "action": "dispense", "arguments": {"volume": 5},
                                                         "operation_key": "agent-pump"})
    run = await run_agent(client, "gpt-5.4-mini", "Dispense.", budget=20_000, llm=FakeLLM(responses))
    assert "completed: dispensed 5 uL" in run.steps[2].summary
    lease = (await client.leases_acquire(["pump-1/plunger"], 5000)).lease  # free: released by the bridge
    await client.leases_release(lease.lease_id)


# ---------------------------------------------------------------------------------------------- the key

def test_the_api_key_comes_from_the_environment_or_the_file_and_never_leaks(tmp_path, caplog):
    secret = "sk-test-0123456789SECRET"
    assert load_api_key({"OPENAI_API_KEY": secret}, tmp_path / "none") == secret
    for text in (f"OPENAI_API_KEY={secret}\n", f"export OPENAI_API_KEY='{secret}'\n", f'# c\nOPENAI_API_KEY = "{secret}"  \n'):
        path = tmp_path / "k.env"
        path.write_text(text)
        assert load_api_key({}, path) == secret
    (tmp_path / "empty.env").write_text("OPENAI_API_KEY=\nOTHER=1\n")
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError) as err:
        load_api_key({}, tmp_path / "empty.env")
    assert "OPENAI_API_KEY" in str(err.value) and secret not in str(err.value) and secret not in caplog.text


async def test_the_default_client_is_built_from_the_key_and_the_loop_never_logs_it(rig, monkeypatch, caplog):
    srv, sim, client = rig
    secret = "sk-test-NEVER-LOG-ME"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    made = []

    class Fake(FakeLLM):
        def __init__(self, *a, api_key=None, **kw):
            super().__init__(recording("openai_responses_3step.json"))
            made.append(api_key)

    import bhms.bridges.openai_tools as module

    openai = pytest.importorskip("openai")

    monkeypatch.setattr(openai, "AsyncOpenAI", Fake)
    with caplog.at_level(logging.DEBUG):
        run = await module.run_agent(client, "gpt-5.4-mini", "Move axis-1.", budget=20_000)
    assert made == [secret] and run.stopped == "final"
    assert secret not in caplog.text and secret not in repr(run) and secret not in json.dumps([s.summary for s in run.steps])


# ---------------------------------------------------------------------------------------------- live (opt-in)

@pytest.mark.skipif(os.environ.get("BHMS_LIVE_OPENAI") != "1", reason="opt-in: BHMS_LIVE_OPENAI=1 (spends a few thousand tokens)")
async def test_live_gpt_5_4_mini_completes_a_three_step_task_under_the_budget(rig):
    srv, sim, client = rig
    run = await run_agent(client, "gpt-5.4-mini", "Find the linear axis, check its description, move it to 25 mm, then report the "
                          "position you verified.", budget=20_000)
    print(f"live: {run.requests} requests, {run.tokens} tokens ({run.input_tokens} in / {run.output_tokens} out), "
          f"steps {[s.tool for s in run.steps]}, stopped {run.stopped}")
    assert run.stopped == "final" and run.tokens < 20_000
    moves = [s for s in run.steps if s.tool == "bhms_invoke" and "completed" in s.summary]
    assert moves and "25" in run.final_text
    assert (await client.request("x-conformance/counters"))["counter"] >= 1
