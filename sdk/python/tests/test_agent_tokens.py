"""Token budgets of the agent surface (Global Constraints: at most 8 tools, device summary <= 400 tokens).

Tokens are estimated as UTF-8 bytes / 4 (tiktoken's encodings need a download and are not assumed present); the
pessimistic ``render.estimate_tokens`` (3 characters per token) bounds the signature block.
"""

from __future__ import annotations

import json

import pytest

from bhms.bridges import AgentBridge, render, tool_definitions
from bhms.client.client import Client
from bhms.protocol.types import to_wire
from bhms.testing.conformance_device import build
from bhms.testing.memory import connect_in_process

# R19 ceilings, measured with tiktoken o200k_base on 2026-11-13 (compact JSON of {name, description, parameters}).
TOTAL_CEILING = 1500
SINGLE_CEILING = 400


def encoder():
    tiktoken = pytest.importorskip("tiktoken")
    try:
        return tiktoken.get_encoding("o200k_base")
    except Exception as exc:  # the encoding file is downloaded once; skip, never fake, when it is unavailable
        pytest.skip(f"o200k_base unavailable: {exc}")


def tokens(text: str) -> int:
    return len(text.encode()) // 4


def definition_tokens() -> dict[str, int]:
    enc = encoder()
    return {t.name: len(enc.encode(json.dumps({"name": t.name, "description": t.description, "parameters": t.input_schema},
                                              separators=(",", ":"), ensure_ascii=False))) for t in tool_definitions()}


def test_at_most_eight_tools_within_the_token_ceilings():
    sizes = definition_tokens()
    assert len(sizes) == 8
    assert all(size <= SINGLE_CEILING for size in sizes.values()), sizes
    assert sum(sizes.values()) <= TOTAL_CEILING, sizes
    print("tool definition tokens (o200k_base):", sizes, "total", sum(sizes.values()))


def test_the_program_grammar_is_on_demand_and_small_enough_to_attach_to_a_refusal():
    from bhms.bridges.grammar import PROGRAM_GRAMMAR

    run = next(t for t in tool_definitions() if t.name == "bhms_run_program")
    assert run.input_schema["properties"]["program"]["type"] == "object" and "$defs" not in run.input_schema
    assert "bhms://grammar/program" in run.description
    assert len(encoder().encode(PROGRAM_GRAMMAR)) <= 600


async def test_device_summaries_and_signature_blocks_fit_their_budgets(tmp_path):
    srv, sim = build(state_dir=str(tmp_path))
    await srv.start()
    client = await Client.from_transport(await connect_in_process(srv.rpc))
    bridge = AgentBridge(client)
    try:
        report = {}
        for summary in [d async for d in client.iter_devices()]:
            text = json.dumps(to_wire(summary), separators=(",", ":"))
            described = await bridge.call("bhms_describe", {"device_id": summary.device_id})
            report[summary.device_id] = {"summary_json": tokens(text), "signature_block": tokens(described.block),
                                         "describe_summary_line": tokens(described.summary), "full_description_json": tokens(
                                             json.dumps(described.data["description"], separators=(",", ":")))}
            assert tokens(text) <= 400 and render.estimate_tokens(described.block) <= render.SIGNATURE_TOKENS
        print("device token sizes (bytes/4):", report)
        found = await bridge.call("bhms_find", {})
        print("bhms_find result text tokens:", tokens(found.summary), "structured:", tokens(json.dumps(found.data)))
    finally:
        await bridge.aclose()
        await client.close()
        await srv.close()
