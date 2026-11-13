"""Token budgets of the agent surface (Global Constraints: at most 8 tools, device summary <= 400 tokens).

Tokens are estimated as UTF-8 bytes / 4 (tiktoken's encodings need a download and are not assumed present); the
pessimistic ``render.estimate_tokens`` (3 characters per token) bounds the signature block.
"""

from __future__ import annotations

import json

from bhms.bridges import AgentBridge, render, tool_definitions
from bhms.client.client import Client
from bhms.protocol.types import to_wire
from bhms.testing.conformance_device import build
from bhms.testing.memory import connect_in_process

# Measured on 2026-11-13 with bytes/4 (compact JSON of {name, description, parameters}); a regression guard, not a target.
TOOL_TOKEN_CEILING = {"bhms_find": 200, "bhms_describe": 120, "bhms_read": 200, "bhms_invoke": 350, "bhms_operation": 150,
                      "bhms_cancel": 130, "bhms_stop": 160, "bhms_run_program": 1800}
ALL_TOOLS_CEILING = 3200


def tokens(text: str) -> int:
    return len(text.encode()) // 4


def definition_tokens() -> dict[str, int]:
    return {t.name: tokens(json.dumps({"name": t.name, "description": t.description, "parameters": t.input_schema},
                                      separators=(",", ":"), ensure_ascii=False)) for t in tool_definitions()}


def test_at_most_eight_tools_and_each_definition_stays_within_its_ceiling():
    sizes = definition_tokens()
    assert len(sizes) == 8
    for name, size in sizes.items():
        assert size <= TOOL_TOKEN_CEILING[name], (name, size)
    assert sum(sizes.values()) <= ALL_TOOLS_CEILING, sizes
    print("tool definition tokens (bytes/4):", sizes, "total", sum(sizes.values()))


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
