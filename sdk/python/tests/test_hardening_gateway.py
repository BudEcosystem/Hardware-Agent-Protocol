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
from bhms.protocol.errors import BhmsError
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


# ---------------------------------------------------------------------------- A4 at the gateway: operations/resolve is forwarded


async def _unknown_through_gateway(r, client):
    op = (await client.actions_invoke("a/axis-1", "explode", {}, wait_ms=2000)).operation
    assert op.state == "unknown"
    with pytest.raises(BhmsError) as exc:
        await client.actions_invoke("a/axis-1", "move_to", {"target": 1})
    assert exc.value.bhms_code == "STALE"  # the resources are inhibited (BHMS-OPS-042)
    return op


async def test_the_gateway_forwards_an_operator_resolution_to_the_upstream(tmp_path):
    async with rig(tmp_path) as r:
        assert r.gateway.rpc.capabilities["operations"]["resolve"] is True
        agent = await r.client()
        admin = await r.client(token=TOKENS["admin"])
        op = await _unknown_through_gateway(r, agent)
        with pytest.raises(BhmsError) as exc:  # the client that started it is not an operator
            await agent.operations_resolve(op.operation_id, state="failed", basis="it looks fine to me")
        assert exc.value.bhms_code == "UNAUTHORIZED" and "operations:resolve" in exc.value.hint
        asked = (await admin.operations_resolve(op.operation_id)).operation  # only asks again: still unknown
        assert asked.state == "unknown"
        resolved = (await admin.operations_resolve(op.operation_id, state="failed",
                                                   basis="axis inspected by the operator: at rest at 0 mm")).operation
        assert resolved.state == "failed" and resolved.error.may_have_acted is True
        last = [h for h in resolved.history if h.kind == "reconciliation"][-1]
        assert last.operator.principal == "admin" and "axis inspected" in last.operator.basis
        # the device server holds the same resolution, attributed to the gateway and the gateway's principal
        theirs = r.servers["a"].journal.get(resolved.upstream.operation_id).wire(history=True)
        mark = [h for h in theirs["history"] if h["kind"] == "reconciliation"][-1]["operator"]
        assert theirs["state"] == "failed" and mark["principal"] == "gateway"
        assert "via gateway gw-test" in mark["basis"] and "principal admin" in mark["basis"]
        # the inhibition is lifted at both enforcement points
        again = (await agent.actions_invoke("a/axis-1", "move_to", {"target": 1}, wait_ms=2000)).operation
        assert again.state == "completed"
        events = (await admin.events_read(types=["operation.resolved"])).events  # the gateway's own, and the upstream's
        assert {e.operation_id for e in events} == {op.operation_id}
        assert [e.data["principal"] for e in events if e.data.get("source") == "operator" and "principal" in e.data][0] == "admin"


async def test_the_gateway_records_an_operator_resolution_itself_when_the_upstream_is_gone(tmp_path):
    """The case of Task 10 gap 5 behind a gateway: the bridge (upstream) is dead and will not answer again."""
    import asyncio

    async with rig(tmp_path, names=("a",)) as r:
        agent = await r.client()
        admin = await r.client(token=TOKENS["admin"])
        op = await _unknown_through_gateway(r, agent)
        await r.servers["a"].close()  # the upstream process dies: its connection to the gateway drops
        await r.listeners["a"].close()
        for _ in range(100):
            if not r.gateway.upstreams["a"].available:
                break
            await asyncio.sleep(0.05)
        assert not r.gateway.upstreams["a"].available
        still = (await admin.operations_resolve(op.operation_id)).operation  # nothing to ask: unchanged
        assert still.state == "unknown"
        with pytest.raises(BhmsError) as exc:  # the shared rules apply here too: "nothing happened" is one claim
            await admin.operations_resolve(op.operation_id, state="failed", basis="x", effect="unverified", may_have_acted=False)
        assert exc.value.bhms_code == "INVALID_ARGUMENT" and exc.value.field == "resolution.effect"  # R45: the member at fault
        with pytest.raises(BhmsError) as exc:  # R38: no verified from an operator, on the gateway-local path either
            await admin.request("operations/resolve", {"operationId": op.operation_id, "resolution": {
                "state": "completed", "basis": "typed in", "effect": "verified"}})
        assert exc.value.bhms_code == "INVALID_ARGUMENT" and exc.value.field == "resolution.effect"
        resolved = (await admin.operations_resolve(op.operation_id, state="failed", may_have_acted=False, effect="none",
                                                   basis="controller found powered off since 09:00; it cannot have moved")).operation
        assert resolved.state == "failed" and resolved.effect == "none" and resolved.error.may_have_acted is False
        last = [h for h in resolved.history if h.kind == "reconciliation"][-1]
        assert last.operator.principal == "admin" and "at the gateway" in last.detail and "not reachable" in last.detail
        assert resolved.evidence.kind == "reported" and resolved.evidence.observations is None
        assert op.operation_id not in r.gateway.router.unknown


async def test_a_gateway_local_completed_resolution_is_unverified_and_reported(tmp_path):
    """R38 on the gateway-local path, which used to set evidence kind measured whenever observations were supplied; the
    rules are the device server's (one shared function, bhms.runtime.resolution)."""
    import asyncio

    from bhms.gateway.journal import ForwardJournal
    from bhms.server.executor import Executor

    async with rig(tmp_path, names=("a",)) as r:
        agent = await r.client()
        admin = await r.client(token=TOKENS["admin"])
        op = await _unknown_through_gateway(r, agent)
        await r.servers["a"].close()
        await r.listeners["a"].close()
        for _ in range(100):
            if not r.gateway.upstreams["a"].available:
                break
            await asyncio.sleep(0.05)
        done = (await admin.operations_resolve(op.operation_id, state="completed", basis="operator saw it finish")).operation
        assert (done.state, done.effect, done.evidence.kind, done.evidence.observations) == ("completed", "unverified",
                                                                                             "reported", None)
        assert [h for h in done.history if h.kind == "reconciliation"][-1].operator.principal == "admin"
    import inspect

    from bhms.runtime import resolution
    for user in (ForwardJournal.resolve_locally, Executor.resolve_by_operator):  # both delegate; neither re-implements
        source = inspect.getsource(user)
        assert "record_operator_resolution(" in source and "DEVICE_FAULT" not in source and "transition(" not in source
    assert resolution.OPERATOR_EVIDENCE == {"kind": "reported"}


def test_check_policy_warns_on_resolve_without_operations_read():
    """Fix round 1: such a principal can resolve only operations it started itself (BHMS-OPS-100)."""
    policy = Policy({"half": {"uids": [1], "scopes": ["read", "operations:resolve"]},
                     "whole": {"uids": [2], "scopes": ["read", "operations:read", "operations:resolve"]}})
    report = check_policy(policy.principals, [])
    assert any("operations:read" in w for w in report.warnings["half"]) and "whole" not in report.warnings
    assert report.warning_count == 1 and "operations:resolve" in report.render()


def test_a_refused_resolution_names_only_members_a_resolution_has():
    """Fix round 2: the gateway's hint still named ``observations``, which R38 removed from ``OperatorResolution``. The
    device server and the gateway now give one hint, and it names only members the resolution carries."""
    import inspect

    from bhms.gateway.router import Router
    from bhms.protocol.types.operations import OperatorResolution
    from bhms.runtime.resolution import INVALID_RESOLUTION_HINT
    from bhms.server.executor import Executor

    named = {"state", "effect", "result"}
    assert all(word in INVALID_RESOLUTION_HINT for word in named) and "observations" not in INVALID_RESOLUTION_HINT
    assert named <= set(OperatorResolution.model_fields) and "observations" not in OperatorResolution.model_fields
    for user in (Router._resolve_unknown, Executor.resolve_by_operator):
        source = inspect.getsource(user)
        assert "hint=INVALID_RESOLUTION_HINT" in source and "observations" not in source
