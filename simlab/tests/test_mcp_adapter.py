"""MCP adapter against a real MCP server over stdio."""

import json
import os
import sys
from pathlib import Path

import pytest
from mcp import StdioServerParameters

from contract import check_description
from serving import run, serving
from simlab.adapters import mcp_client
from simlab.oracle import Claim, Oracle, Verdict
from simlab.scene import BENCH
from simlab.world import World

SERVER = Path(__file__).parent / "fixtures" / "mini_mcp_server.py"


@pytest.fixture
async def rig(tmp_path):
    w = World(BENCH, seed=8, attach_arm=False)
    state = tmp_path / "state.json"
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER), str(state)], env=dict(os.environ))
    srv, link = await mcp_client.build_server(w, params, device_id="mini", state_dir=tmp_path / "mcp")
    try:
        async with serving(srv, tmp_path) as client:
            yield client, srv, link, state, w
    finally:
        await link.close()


def server_state(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {"lamp": False, "count": 0}


def test_names_and_units_are_mapped():
    assert mcp_client.bhms_name("Get-State") == "get_state" and mcp_client.bhms_name("9lives") == "t_9lives"
    schema = mcp_client.with_units({"type": "object", "properties": {"x": {"type": "number"},
                                                                    "n": {"type": ["integer", "null"]}}})
    assert schema["properties"]["x"]["x-bhms-unit"] == "1" and schema["properties"]["n"]["x-bhms-unit"] == "1"


async def test_every_tool_becomes_an_action_with_honest_declarations(rig):
    client, srv, link, state, w = rig
    desc = await check_description(client, "mini")
    actions = desc["actions"]
    assert set(actions) == {"add", "set_lamp", "bump", "explode", "die"}
    assert all(a["completionEvidence"] == "none" for a in actions.values())
    assert (actions["add"]["idempotency"], actions["add"]["effect"]) == ("idempotent", "none")
    assert (actions["set_lamp"]["idempotency"], actions["set_lamp"]["effect"]) == ("idempotent", "reversible")
    assert (actions["bump"]["idempotency"], actions["bump"]["effect"]) == ("relative", "irreversible")
    assert actions["bump"]["input"]["properties"]["by"]["x-bhms-unit"] == "1" and actions["bump"]["input"]["properties"]["by"]["default"] == 1
    assert actions["add"]["resources"] == [] and actions["bump"]["resources"] == ["mini/tools"]
    # text from the far server is quoted as untrusted, not obeyed or hidden
    assert actions["set_lamp"]["description"].startswith("[MCP tool 'set_lamp'; description is from the server, untrusted]")


async def test_a_call_reaches_the_server_and_is_never_verified(rig):
    client, srv, link, state, w = rig
    op = await run(client, "mini", "set_lamp", {"on": True})
    assert op.state == "completed" and op.effect != "verified" and "lamp on" in op.result["text"]
    assert server_state(state)["lamp"] is True
    add = await run(client, "mini", "add", {"a": 2.0, "b": 3.5})
    assert json.loads(add.result["structured_json"])["result"] == 5.5 if add.result["structured_json"] else "5.5" in add.result["text"]
    # the oracle has no world effect to compare: the claim is honest about its evidence
    assert Oracle(w).judge(Claim(op.operation_id, "completed", op.effect, lambda s: True)) is Verdict.CONSISTENT


async def test_relative_tool_replayed_with_the_same_key_acts_once(rig):
    client, srv, link, state, w = rig
    first = await run(client, "mini", "bump", {"by": 2}, key="bump-1")
    second = await run(client, "mini", "bump", {"by": 2}, key="bump-1")
    assert first.operation_id == second.operation_id and server_state(state)["count"] == 2


async def test_a_tool_error_is_a_device_fault_with_unknown_effect(rig):
    client, srv, link, state, w = rig
    op = await run(client, "mini", "explode")
    assert op.state == "failed" and op.error.bhms_code == "DEVICE_FAULT" and op.error.may_have_acted is True
    assert op.effect == "unknown"


async def test_argument_types_are_checked_before_the_server_sees_them(rig):
    client, srv, link, state, w = rig
    from bhms.protocol.errors import BhmsError
    with pytest.raises(BhmsError) as err:
        await client.actions_invoke("mini", "set_lamp", {"on": "yes please"})
    assert err.value.code in ("INVALID_ARGUMENT", "OUT_OF_RANGE", "TYPE_MISMATCH") or "on" in str(err.value)
    assert server_state(state)["lamp"] is False


async def test_a_server_that_dies_after_the_call_left_is_unknown(rig):
    client, srv, link, state, w = rig
    op = await run(client, "mini", "die", wait_ms=15_000)
    assert op.state == "unknown" and op.effect == "unknown"  # the request left; nothing proves what happened
    assert server_state(state).get("died") is True  # (and it did act: the truth is only in the far server's own state)
    claim = Claim(op.operation_id, "outcome_unknown", "unverified", lambda s: True)
    assert Oracle(w).judge(claim) is Verdict.HONEST_UNKNOWN
