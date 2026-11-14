"""Task 7b group C, gateway side: the default agent policy includes stop (S5), admins see the upstream operation id (S6),
and ``bhms gateway check-policy`` shows what each scope matches (S7)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bhms.cli.main import app
from bhms.gateway import load_config
from bhms.gateway.policy_check import check_policy
from bhms.runtime.authority import Policy, agent_scopes
from helpers.gateway_rig import TOKENS, principals, rig

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bhms"
SDK_EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

# ---------------------------------------------------------------------------- C17: the default agent policy includes stop


def test_agent_scopes_grant_stop_on_exactly_the_devices_the_agent_may_use():
    assert agent_scopes("bench/*", "pump/pump-1") == ("read", "lease", "invoke:bench/*/*", "stop:bench/*",
                                                      "invoke:pump/pump-1/*", "stop:pump/pump-1")
    with pytest.raises(ValueError):
        agent_scopes()
    principal = Policy({"agent": {"uids": [1], "scopes": list(agent_scopes("bench/*"))}}).principals[0]
    assert principal.can_stop("bench/stage-z") and not principal.can_stop("pump/pump-1")
    assert principal.can_invoke("bench/stage-z", "move_to", ()) and not principal.can_invoke("bench/stage-z", "burn", (), True)
    assert not principal.admin and not principal.operations_all


async def test_an_agent_with_the_default_policy_can_stop_its_devices_and_no_others(tmp_path):
    """Task 11 S5: on a fault the agent called bhms_stop and was refused (scope:stop): it had no safe action left."""
    from bhms.bridges import AgentBridge

    doc = principals(agent_scopes=list(agent_scopes("a/*")))
    async with rig(tmp_path, principals_doc=doc) as r:
        client = await r.client()
        bridge = AgentBridge(client)
        try:
            moving = await bridge.call("bhms_invoke", {"device_id": "a/axis-1", "action": "slow", "arguments": {}, "wait_ms": 0})
            assert not moving.is_error
            stopped = await bridge.call("bhms_stop", {"device_ids": ["a/axis-1"], "reason": "the slide dropped"})
            assert not stopped.is_error and stopped.data["stops"][0]["outcome"] == "confirmed"
            other = await bridge.call("bhms_stop", {"device_ids": ["b/axis-1"], "reason": "not mine"})
            assert other.data["stops"][0]["outcome"] == "failed"
            assert other.data["stops"][0]["error"]["bhmsCode"] in ("UNAUTHORIZED", "UNKNOWN_DEVICE")
        finally:
            await bridge.aclose()


def test_the_example_agent_principal_can_stop_the_devices_it_can_act_on():
    config = load_config(EXAMPLES / "gateway.toml")
    scopes = config.principals["agent"]["scopes"]
    assert set(agent_scopes("bench/*", "pump/*")) <= set(scopes)


# ---------------------------------------------------------------------------- C18: the upstream operation id, for admins only


async def test_only_admins_see_the_upstream_operation_id(tmp_path):
    """Task 11 S6: joining a gateway record to the device server's own log needed gateway internals."""
    async with rig(tmp_path) as r:
        agent = await r.client()
        admin = await r.client(token=TOKENS["admin"])
        invoked = await agent.actions_invoke("a/axis-1", "move_to", {"target": 3}, wait_ms=2000)
        op_id = invoked.operation.operation_id
        upstream_row = next(row for row in r.servers["a"].store.list_operations(principal=None, limit=10))
        seen = (await admin.operations_get(op_id)).operation
        assert seen.upstream.server == "a" and seen.upstream.operation_id == upstream_row.id
        assert (await admin.operations_wait(op_id, 100)).operation.upstream.operation_id == upstream_row.id
        listed = (await admin.operations_list(device_id="a/axis-1")).operations
        assert [o.upstream.operation_id for o in listed] == [upstream_row.id]
        for mine in (invoked.operation, (await agent.operations_get(op_id)).operation,
                     (await agent.operations_wait(op_id, 100)).operation, *(await agent.operations_list()).operations):
            assert mine.upstream is None  # the owner without admin learns nothing about the topology behind the gateway
        reader_doc = principals()
        reader_doc["agent-b"]["scopes"] = ["read", "operations:read"]
        r.gateway.set_policy(Policy(reader_doc))
        reader = await r.client(token=TOKENS["agent-b"])
        assert (await reader.operations_get(op_id)).operation.upstream is None  # operations:read is not admin


# ---------------------------------------------------------------------------- C19: bhms gateway check-policy

runner = CliRunner()


def _example(tmp_path, agent_scopes_line: str | None = None) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(EXAMPLES, root / "examples" / "bhms", ignore=shutil.ignore_patterns("state", "__pycache__", "*.sock"))
    shutil.copytree(SDK_EXAMPLES, root / "sdk" / "python" / "examples", ignore=shutil.ignore_patterns("__pycache__"))
    config = root / "examples" / "bhms" / "gateway.toml"
    if agent_scopes_line is not None:
        lines = config.read_text().splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith("scopes = ") and "invoke:bench" in line)
        lines[index] = agent_scopes_line
        config.write_text("\n".join(lines) + "\n")
    return config


def test_check_policy_reports_what_each_scope_matches_for_namespaced_devices():
    """Task 11 S7: with namespaced devices ``invoke:knob/*`` matches nothing (the pattern splits at the last "/") and fails
    closed, silently."""
    devices = [
        {"deviceId": "knob/knob-1", "capabilities": ["bhms.input.knob"], "actions": {"turn": {"effect": "reversible"},
                                                                                     "burn": {"effect": "hazardous"}},
         "properties": {"angle": {"readEffect": "none"}, "fifo": {"readEffect": "transaction"}}},
        {"deviceId": "pump/pump-1", "capabilities": ["bhms.liquid.dispense"], "actions": {"dispense": {"effect": "irreversible"}},
         "properties": {}},
    ]
    policy = Policy({"agent": {"uids": [1], "scopes": ["read", "lease", "invoke:knob/*", "invoke:knob/*/*", "invoke:knob/knob-1/burn",
                                                         "invoke:cap:bhms.liquid.*", "stop:knob/*", "stop:oven/*"]},
                     "operator": {"uids": [2], "scopes": ["admin"]}})
    assert pytest.raises(ValueError, Policy, {"x": {"uids": [3], "scopes": ["frobnicate"]}})  # refused when the policy loads
    report = check_policy(policy.principals, devices)
    agent = {row.scope: row for row in report.principals["agent"]}
    assert agent["invoke:knob/*"].matches == [] and "splits at the last" in agent["invoke:knob/*"].warning
    assert "invoke:knob/*/*" in agent["invoke:knob/*"].warning  # the fix is named
    assert agent["invoke:knob/*/*"].matches == ["knob/knob-1/fifo (fresh transaction read)", "knob/knob-1/turn"]
    assert "burn" in agent["invoke:knob/*/*"].note and "hazardous" in agent["invoke:knob/*/*"].note  # BHMS-AUTH-003
    assert agent["invoke:knob/knob-1/burn"].matches == ["knob/knob-1/burn (hazardous)"]
    assert agent["invoke:cap:bhms.liquid.*"].matches == ["pump/pump-1/dispense"]
    assert agent["stop:knob/*"].matches == ["knob/knob-1"]
    assert agent["stop:oven/*"].matches == [] and "matches no device" in agent["stop:oven/*"].warning
    from bhms.runtime.authority import Principal

    direct = check_policy([Principal("embedded", ("frobnicate",))], devices)  # a Principal built in code is not validated
    assert "not a BHMS scope" in direct.principals["embedded"][0].warning
    assert agent["read"].matches == ["knob/knob-1", "pump/pump-1"] and agent["lease"].warning is None
    assert any("pump/pump-1" in w and "stop" in w for w in report.warnings["agent"])  # may act on it but cannot stop it (S5)
    assert report.principals["operator"][0].scope == "admin" and not report.warnings.get("operator")
    assert report.warning_count == 3
    text = report.render()
    assert "agent" in text and "invoke:knob/*" in text and "WARNING" in text and "knob/knob-1/turn" in text


def test_check_policy_cli_runs_against_the_example_gateway(tmp_path):
    config = _example(tmp_path)
    result = runner.invoke(app, ["gateway", "check-policy", str(config)], env={"COLUMNS": "200"}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "principal agent" in result.output and "invoke:bench/*/*" in result.output and "bench/stage-z/move_to" in result.output
    assert "stop:bench/*" in result.output and "0 warnings" in result.output
    as_json = runner.invoke(app, ["gateway", "check-policy", str(config), "--json"], catch_exceptions=False)
    document = json.loads(as_json.output)
    assert document["warnings"] == 0 and "agent" in document["principals"]
    assert not list(config.parent.glob("*.sock")) and not list(config.parent.glob("state/*.sqlite3"))  # nothing is served or journaled


def test_check_policy_cli_warns_and_strict_fails_on_a_scope_that_matches_nothing(tmp_path):
    config = _example(tmp_path, 'scopes = ["read", "lease", "invoke:bench/*", "stop:bench/*"]')
    result = runner.invoke(app, ["gateway", "check-policy", str(config)], env={"COLUMNS": "200"}, catch_exceptions=False)
    assert result.exit_code == 0 and "WARNING" in result.output and "invoke:bench/*/*" in result.output
    strict = runner.invoke(app, ["gateway", "check-policy", str(config), "--strict"], catch_exceptions=False)
    assert strict.exit_code == 1
    missing = runner.invoke(app, ["gateway", "check-policy"], catch_exceptions=False)
    assert missing.exit_code == 2
    bad = runner.invoke(app, ["gateway", "check-policy", str(tmp_path / "nope.toml")], catch_exceptions=False)
    assert bad.exit_code == 2


def test_the_agent_surface_says_that_stop_is_the_safe_action_on_a_fault():
    from bhms.bridges import tool_definitions
    from bhms.bridges.mcp import BRIDGE_INSTRUCTIONS

    stop = next(t for t in tool_definitions() if t.name == "bhms_stop")
    assert "safe action when something goes wrong" in stop.description and "Not an emergency stop" in stop.description
    assert "bhms_stop" in BRIDGE_INSTRUCTIONS and "unexpected" in BRIDGE_INSTRUCTIONS
    spec = (Path(__file__).resolve().parents[3] / "spec" / "bhms" / "12-agent-surface.md").read_text()
    assert "## 12.7 Faults: stop is the safe action" in spec
