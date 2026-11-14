"""Chapter 12 (profile ``agent``): an MCP bridge in front of the conformance device.

The runner speaks MCP to the bridge (:mod:`bhms.conformance.agentwire`) and BHMS to the device the bridge fronts (the
``--device`` target), which is how it proves "no request reached the device" and injects faults.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from bhms.conformance.context import Context
from bhms.conformance.core import Skipped, check
from bhms.protocol import schema as bhms_schema

TOOLS = ("bhms_find", "bhms_describe", "bhms_read", "bhms_invoke", "bhms_operation", "bhms_cancel", "bhms_stop", "bhms_run_program")
NEEDS = ("agent",)
FORBIDDEN_WORDS = re.compile(r"\bdone\b|(?<!not )(?<!retry-)\b(safe|at rest)\b|finished successfully", re.I)


def _agent(c: Context) -> Any:
    if c.agent is None:
        raise Skipped("unproven: the target is not an agent bridge")
    return c.agent


def _refs(node: Any) -> list[str]:
    if isinstance(node, dict):
        out = [node["$ref"]] if isinstance(node.get("$ref"), str) else []
        for value in node.values():
            out.extend(_refs(value))
        return out
    if isinstance(node, list):
        return [r for item in node for r in _refs(item)]
    return []


@check("agent.tool-surface", ["BHMS-AGT-001", "BHMS-AGT-051", "BHMS-AGT-031"], profile="agent", needs=NEEDS)
async def tool_surface(c: Context) -> None:
    """At most the eight tools, with the published input members; self-contained schemas; safe-retry instructions."""
    tools = {t["name"]: t for t in await _agent(c).list_tools()}
    c.expect(set(tools) <= set(TOOLS), f"unexpected tools: {sorted(set(tools) - set(TOOLS))}", ("BHMS-AGT-001",))
    expected = {"bhms_find", "bhms_describe", "bhms_read", "bhms_invoke", "bhms_operation", "bhms_cancel", "bhms_stop"}
    c.expect(expected <= set(tools), f"missing tools: {sorted(expected - set(tools))}", ("BHMS-AGT-001",))
    document = bhms_schema.load_schema()
    published = document["x-bhms-agent-tools"]
    for name, tool in tools.items():
        definition = document["$defs"][published[name]["input"].rsplit("/", 1)[-1]]
        want = set(definition.get("properties", {}))
        have = set(tool["inputSchema"].get("properties", {}))
        c.expect(want == have, f"{name}: input members {sorted(have)} differ from the specification {sorted(want)}", ("BHMS-AGT-001",))
        c.expect(set(definition.get("required", [])) == set(tool["inputSchema"].get("required", [])),
                 f"{name}: required members differ from the specification", ("BHMS-AGT-001",))
        c.expect(tool["inputSchema"].get("additionalProperties") is False or definition.get("additionalProperties") is not False,
                 f"{name}: the input schema must be closed", ("BHMS-AGT-001",))
        c.expect("oneOf" not in tool["inputSchema"], f"{name}: a top-level oneOf is not self-contained", ("BHMS-AGT-051",))
        local = {r for r in _refs(tool["inputSchema"]) if r.startswith("#/$defs/")}
        c.expect(all(r[len("#/$defs/"):] in tool["inputSchema"].get("$defs", {}) for r in local), f"{name}: dangling $ref {sorted(local)}",
                 ("BHMS-AGT-051",))
        c.expect(not [r for r in _refs(tool["inputSchema"]) if not r.startswith("#/")], f"{name}: external $ref", ("BHMS-AGT-051",))
    invoke = tools["bhms_invoke"]["description"].lower()
    c.expect("bhms_operation" in invoke and "operation_key" in invoke,
             f"the bhms_invoke description must say how to retry safely (bhms_operation, operation_key): {invoke[:200]}", ("BHMS-AGT-031",))


@check("agent.no-authority-from-arguments", ["BHMS-AGT-002", "BHMS-SEC-031"], profile="agent", needs=NEEDS)
async def no_authority(c: Context) -> None:
    """Identity, scope, lease and bound members in tool arguments are refused; the device is never reached."""
    agent, axis = _agent(c), c.axis()
    base = await c.counter(axis)
    ops = await c.operations_count()
    for extra in ({"principal": "admin"}, {"scopes": ["admin"]}, {"lease_id": "lease-forged"}, {"leaseId": "lease-forged"},
                  {"bounds": {"count": {"maximum": 1000}}}, {"authorized": True}):
        outcome = await agent.call("bhms_invoke", {"device_id": axis, "action": "pulse", "arguments": {"count": 1}, **extra})
        c.expect(outcome.is_error and outcome.structured.get("error", {}).get("bhmsCode") == "INVALID_ARGUMENT",
                 f"a tool call carrying {list(extra)} must be refused by the input schema: {outcome.text[:160]}", ("BHMS-AGT-002",))
    c.expect(await c.counter(axis) == base and await c.operations_count() == ops, "a refused tool call reached the device", ("BHMS-AGT-002", "BHMS-SEC-031"))


@check("agent.results-and-summaries", ["BHMS-AGT-010", "BHMS-AGT-011", "BHMS-AGT-012", "BHMS-AGT-013", "BHMS-OPS-055"], profile="agent", needs=NEEDS)
async def summaries(c: Context) -> None:
    """One-line summary of at most 200 characters plus structured content on every result; units, state, effect,
    quality, evidence and age stated; device text quoted; the signature block complete; canceled is not safe."""
    agent, axis = _agent(c), c.axis()
    description = await c.describe(axis)
    outcomes = {
        "find": await agent.call("bhms_find", {}),
        "describe": await agent.call("bhms_describe", {"device_id": axis}),
        "read": await agent.call("bhms_read", {"device_id": axis, "property": "position"}),
        "invoke": await agent.call("bhms_invoke", {"device_id": axis, "action": "move_to", "arguments": {"position": 12.5}}),
        "refusal": await agent.call("bhms_invoke", {"device_id": axis, "action": "move_to", "arguments": {"position": 500}}),
    }
    slow = await agent.call("bhms_invoke", {"device_id": axis, "action": "slow_move", "arguments": {"duration_ms": 3000}, "wait_ms": 100})
    outcomes["running"] = slow
    for name, outcome in outcomes.items():
        c.expect(len(outcome.summary) <= 200 and "\n" not in outcome.summary and outcome.summary.strip(),
                 f"{name}: the first line must be a summary of at most 200 characters: {outcome.summary[:80]!r}", ("BHMS-AGT-010",))
        c.expect(outcome.structured, f"{name}: the result must carry structured content", ("BHMS-AGT-010",))
    read = outcomes["read"].summary
    c.expect("mm" in read and re.search(r"\bmeasured\b", read) and re.search(r"\bvalid\b", read) and re.search(r"\d+\s*(ms|s)\b", read),
             f"a read summary states the unit, evidence, quality and age: {read}", ("BHMS-AGT-011",))
    invoke = outcomes["invoke"].summary
    c.expect("completed" in invoke and "effect" in invoke and "mm" in json.dumps(outcomes["invoke"].structured) or "12.5" in invoke,
             f"an invoke summary states the state and the effect: {invoke}", ("BHMS-AGT-011",))
    running = outcomes["running"].summary
    c.expect(not FORBIDDEN_WORDS.search(running) and re.search(r"dispatching|running|accepted", running),
             f"a non-completed operation must not read as done: {running}", ("BHMS-AGT-011",))
    find = outcomes["find"].summary
    for device in await c.devices():
        c.expect(f'"{device["name"][:60]}"' in find or device["deviceId"] in find, f"device names must appear quoted: {find}", ("BHMS-AGT-012",))
    block = outcomes["describe"].text
    elided = "(elided" in block  # the bridge keeps a signature within 400 tokens by dropping details, and says so
    for action, spec in description["actions"].items():
        line = next((ln for ln in block.splitlines() if ln.startswith(f"action {action}(")), "")
        c.expect(line, f"the signature block lacks action {action}", ("BHMS-AGT-013",))
        if elided:
            continue
        for needle in ("effect=", "repeat=", "lease=", "cancel=", "evidence=", "max="):
            c.expect(needle in line, f"{action}: the signature must state {needle[:-1]}: {line}", ("BHMS-AGT-013",))
        for member, schema in (spec["input"].get("properties") or {}).items():
            c.expect(member in line and (schema.get("x-bhms-unit", "") in line or schema.get("x-bhms-unit") == "1"),
                     f"{action}: argument {member} with its unit must be in the signature: {line}", ("BHMS-AGT-013",))
    for prop in description["properties"]:
        c.expect(any(ln.startswith(f"property {prop}") for ln in block.splitlines()), f"the signature block lacks property {prop}", ("BHMS-AGT-013",))
    c.expect(elided or len(block) / 3.5 <= 400, f"the signature block should stay within 400 tokens or announce its elision, is about "
             f"{len(block) / 3.5:.0f}", ("BHMS-AGT-013",))
    op_id = slow.structured["operation"]["operationId"]
    cancelled = await agent.call("bhms_cancel", {"operation_id": op_id, "reason": "conformance"})
    await c.settle(op_id, 6)
    final = await agent.call("bhms_operation", {"operation_id": op_id})
    for outcome in (cancelled, final):
        c.expect(not FORBIDDEN_WORDS.search(outcome.summary), f"a canceled operation must not be called safe or done: {outcome.summary}", ("BHMS-OPS-055",))


@check("agent.refusals", ["BHMS-AGT-020", "BHMS-AGT-021"], profile="agent", needs=NEEDS)
async def refusals(c: Context) -> None:
    """A BHMS error becomes a refusal with every field unchanged; bad arguments are refused before any request that acts."""
    agent, axis = _agent(c), c.axis()
    base, ops = await c.counter(axis), await c.operations_count()
    outcome = await agent.call("bhms_invoke", {"device_id": axis, "action": "move_to", "arguments": {"position": 500}})
    error = outcome.structured.get("error", {})
    c.expect(outcome.is_error and all(k in error for k in ("bhmsCode", "message", "field", "bound", "mayHaveActed", "retry", "hint")),
             f"a refusal carries bhmsCode, message, field, bound, mayHaveActed, retry and hint: {error}", ("BHMS-AGT-020",))
    c.expect(error.get("bhmsCode") == "OUT_OF_RANGE" and error.get("field") == "arguments.position" and error.get("bound") == {"maximum": 200},
             f"the refusal must keep the server's values unchanged: {error}", ("BHMS-AGT-020",))
    for arguments in ({"device_id": axis, "action": "move_to", "arguments": {"position": "far"}}, {"device_id": axis, "action": "move_to"},
                      {"device_id": axis, "action": "pulse", "arguments": {"count": 1000}}, {"device_id": axis, "action": "pulse", "arguments": {"count": 1, "x": 1}}):
        refused = await agent.call("bhms_invoke", arguments)
        c.expect(refused.is_error, f"bad arguments must be refused: {arguments}", ("BHMS-AGT-021",))
        c.expect(re.search(r"e\.g\.|example|for example", refused.text, re.I), f"the refusal must show a corrected example: {refused.text[:200]}", ("BHMS-AGT-021",))
    c.expect(await c.counter(axis) == base and await c.operations_count() == ops, "an out-of-schema call reached the device", ("BHMS-AGT-021",))
    if c.has_extension:  # a fault channel to the device behind the bridge
        await c.inject("crash_next")
        unknown = await agent.call("bhms_invoke", {"device_id": axis, "action": "pulse", "arguments": {"count": 1}})
        c.expect(re.search(r"outcome unknown", unknown.summary, re.I), f"an unknown outcome must say so: {unknown.summary}", ("BHMS-AGT-020",))
        await c.reset()


@check("agent.find-no-match", ["BHMS-AGT-015"], profile="agent", needs=NEEDS)
async def find_no_match(c: Context) -> None:
    """A bhms_find that matches nothing says how many devices exist and how to list them; a device is found by its id."""
    agent = _agent(c)
    everything = await agent.call("bhms_find", {})
    total = len(everything.structured.get("devices", []))
    c.expect(not everything.is_error and total > 0, f"bhms_find with no arguments must list the devices: {everything.summary}")
    nothing = await agent.call("bhms_find", {"text": "zz-" + c.unique("nomatch").replace("-", "q")})
    c.expect(not nothing.is_error and nothing.structured.get("devices") == [], f"no match is an empty result, not a refusal: {nothing.summary}")
    c.expect(nothing.structured.get("totalDevices") == total,
             f"a find with no match must carry totalDevices = {total}: {nothing.structured.get('totalDevices')!r}")
    c.expect(str(total) in nothing.summary and "no arguments" in nothing.summary,
             f"the summary must state the number of devices and that bhms_find with no arguments lists them: {nothing.summary}")
    device = everything.structured["devices"][0]["deviceId"]
    by_id = await agent.call("bhms_find", {"text": device.upper()})
    c.expect(device in [d["deviceId"] for d in by_id.structured.get("devices", [])], f"bhms_find by device id must find {device}: {by_id.summary}")


@check("agent.freshness-and-keys", ["BHMS-AGT-014", "BHMS-AGT-030", "BHMS-AGT-041"], profile="agent", needs=NEEDS)
async def freshness_and_keys(c: Context) -> None:
    """A read after a move is the post-move reading; a call without operation_key is marked not retry-safe and sends no key;
    a keyed retry is a replay."""
    agent, axis = _agent(c), c.axis()
    await agent.call("bhms_invoke", {"device_id": axis, "action": "move_to", "arguments": {"position": 61.5}})
    read = await agent.call("bhms_read", {"device_id": axis, "property": "position"})
    c.expect(read.structured.get("observation", {}).get("value") == 61.5, f"the read after a move must be the post-move reading: {read.summary}", ("BHMS-AGT-014",))
    plain = await agent.call("bhms_invoke", {"device_id": axis, "action": "pulse", "arguments": {"count": 1}})
    c.expect("not retry-safe" in plain.summary, f"without operation_key the summary must say it is not retry-safe: {plain.summary}", ("BHMS-AGT-030",))
    stored = await c.get_op(plain.structured["operation"]["operationId"])
    c.expect(stored["keyOrigin"] == "server", "the bridge must not invent an operation key", ("BHMS-AGT-030",))
    key = c.unique("agent-key")
    first = await agent.call("bhms_invoke", {"device_id": axis, "action": "clamp", "arguments": {"force": 5}, "operation_key": key})
    second = await agent.call("bhms_invoke", {"device_id": axis, "action": "clamp", "arguments": {"force": 5}, "operation_key": key})
    c.expect(not first.is_error and not second.is_error, f"a keyed lease-requiring retry must not fail with LEASE_CONFLICT: {first.summary} / {second.summary}",
             ("BHMS-AGT-041",))
    c.expect("replayed" in second.summary.lower(), f"a retry with the same key must say replayed: {second.summary}", ("BHMS-AGT-041",))
    c.expect(first.structured["operation"]["operationId"] == second.structured["operation"]["operationId"], "the retry must return the same operation", ("BHMS-AGT-041",))


@check("agent.wait-and-leases", ["BHMS-AGT-032", "BHMS-AGT-040"], profile="agent", needs=NEEDS)
async def wait_and_leases(c: Context) -> None:
    """wait_ms defaults to 5000, is capped at 60000 and unsettled results say how to keep waiting; leases cover exactly the
    action's resources and conflicts become refusals."""
    agent, axis = _agent(c), c.axis()
    tool = next(t for t in await agent.list_tools() if t["name"] == "bhms_invoke")
    wait = tool["inputSchema"]["properties"].get("wait_ms", {})
    c.expect(wait.get("maximum", 60000) <= 60000, f"wait_ms must be capped at 60000, schema says {wait}", ("BHMS-AGT-032",))
    started = time.monotonic()
    done = await agent.call("bhms_invoke", {"device_id": axis, "action": "slow_move", "arguments": {"duration_ms": 1500}})
    c.expect("completed" in done.summary and time.monotonic() - started >= 1.3, f"the default wait must cover a 1.5 s action: {done.summary}", ("BHMS-AGT-032",))
    long = await agent.call("bhms_invoke", {"device_id": axis, "action": "slow_move", "arguments": {"duration_ms": 4000}, "wait_ms": 100})
    c.expect("bhms_operation" in long.text and re.search(r"running|dispatching", long.summary), f"an unsettled result must say how to keep waiting: {long.text[:200]}",
             ("BHMS-AGT-032",))
    over = await agent.call("bhms_invoke", {"device_id": axis, "action": "pulse", "arguments": {"count": 1}, "wait_ms": 70_000})
    c.expect(over.is_error or "completed" in over.summary, "wait_ms above 60000 must be refused or capped", ("BHMS-AGT-032",))
    await agent.call("bhms_cancel", {"operation_id": long.structured["operation"]["operationId"]})
    await c.settle(long.structured["operation"]["operationId"], 6)
    # leases: the bridge acquires exactly the needed resource; a held resource refuses, an unrelated held resource does not
    motion = await c.ok("leases/acquire", {"resources": [f"{axis}/motion"], "ttlMs": 30_000})
    try:
        ok = await agent.call("bhms_invoke", {"device_id": axis, "action": "clamp", "arguments": {"force": 7}})
        c.expect(not ok.is_error and "completed" in ok.summary, f"a lease on exactly axis-1/clamp must be acquired although axis-1/motion is held: {ok.summary}",
                 ("BHMS-AGT-040",))
    finally:
        await c.ok("leases/release", {"leaseId": motion["lease"]["leaseId"]})
    held = await c.ok("leases/acquire", {"resources": [f"{axis}/clamp"], "ttlMs": 30_000})
    try:
        blocked = await agent.call("bhms_invoke", {"device_id": axis, "action": "clamp", "arguments": {"force": 7}})
        c.expect(blocked.is_error and blocked.structured["error"]["bhmsCode"] == "LEASE_CONFLICT", f"a held resource must refuse with LEASE_CONFLICT: {blocked.summary}",
                 ("BHMS-AGT-040",))
    finally:
        await c.ok("leases/release", {"leaseId": held["lease"]["leaseId"]})
    again = await agent.call("bhms_invoke", {"device_id": axis, "action": "clamp", "arguments": {"force": 7}})
    c.expect(not again.is_error, "the bridge must release its lease so that the resource is free afterwards", ("BHMS-AGT-040",))


@check("agent.programs-and-stop", ["BHMS-AGT-001", "BHMS-OPS-055"], profile="agent", needs=NEEDS)
async def programs_and_stop(c: Context) -> None:
    """run_program validates and refuses a bad program with the failing path; stop reports honestly."""
    agent, axis = _agent(c), c.axis()
    bad = await agent.call("bhms_run_program", {"program": {"bhmsProgram": "2026-11-13", "name": "p", "description": "d", "maxDurationMs": 1000,
                                                             "input": {"type": "object", "additionalProperties": False, "properties": {}},
                                                             "steps": [{"kind": "jump"}]}, "arguments": {}})
    c.expect(bad.is_error and "steps[0]" in bad.text, f"a malformed program is refused with the failing step path: {bad.text[:200]}")
    stopped = await agent.call("bhms_stop", {"device_ids": [axis], "reason": "conformance"})
    c.expect(not FORBIDDEN_WORDS.search(stopped.summary) or "not" in stopped.summary.lower(), f"stop must not be called safe: {stopped.summary}", ("BHMS-OPS-055",))


@check("agent.function-tools-equal-mcp", ["BHMS-AGT-050"], profile="agent", needs=NEEDS)
async def function_tools_equal_mcp(c: Context) -> None:
    """A function-tool adapter emits the same names, descriptions and input schemas as the MCP bridge, and does not declare them
    strict. The adapter's definitions come from ``--function-tools FILE`` (or the built-in fixture's adapter)."""
    if c.function_tools is None:
        c.skip("no adapter definitions were given (--function-tools FILE with the OpenAI function-tool definitions)")
    mcp = {t["name"]: t for t in await _agent(c).list_tools()}
    flat = {}
    for item in c.function_tools:
        body = item.get("function", item)
        flat[body["name"]] = body
    if "bhms_run_program" not in mcp:
        flat.pop("bhms_run_program", None)
    c.expect(set(flat) == set(mcp), f"the adapter publishes {sorted(flat)}, the bridge {sorted(mcp)}")
    for name, tool in mcp.items():
        body = flat[name]
        c.expect(body.get("description") == tool["description"], f"{name}: the descriptions differ")
        c.expect(body.get("parameters") == tool["inputSchema"], f"{name}: the input schemas differ")
        c.expect(not body.get("strict"), f"{name}: the adapter must not declare the tool strict")


@check("agent.hostile-text-is-data", ["BHMS-SEC-020"], profile="agent", needs=("agent", "faults"))
async def hostile_text_is_data(c: Context) -> None:
    """Instructions injected into device text (the description of the device and its action, an error message) are shown only
    quoted and cut, never followed: no request that the text asks for reaches the device."""
    from bhms.testing.conformance_device import HOSTILE_TEXT

    agent, axis = _agent(c), c.axis()
    base_counter, base_ops = await c.counter(axis), await c.operations_count()
    stops_before = sum(1 for e in (await c.ok("events/read", {"limit": 500}))["events"] if e["type"] == "stop") if "events" in c.caps else 0
    await c.inject("hostile_text")
    try:
        outcomes = [await agent.call("bhms_find", {}), await agent.call("bhms_describe", {"device_id": axis}),
                    await agent.call("bhms_invoke", {"device_id": axis, "action": "pulse", "arguments": {"count": 1}}),
                    await agent.call("bhms_invoke", {"device_id": axis, "action": "fault", "arguments": {}})]
    finally:
        await c.inject("none")
    shown = 0
    for outcome in outcomes:
        text = outcome.text
        for start in range(len(HOSTILE_TEXT) - 60):
            c.expect(HOSTILE_TEXT[start:start + 61] not in text, f"more than 60 characters of device text are shown: {text[:160]!r}", ("BHMS-SEC-020",))
        for match in re.finditer("IGNORE", text):
            shown += 1
            c.expect(match.start() > 0 and text[match.start() - 1] == '"', f"device text must appear only quoted: {text[:160]!r}", ("BHMS-SEC-020",))
    c.expect(shown >= 1, "the injected text should have reached a summary (quoted); the fixture or the bridge changed", ("BHMS-SEC-020",))
    c.expect(await c.counter(axis) == base_counter + 2 and await c.operations_count() == base_ops + 2,
             "something other than the two requested invokes reached the device after the hostile text was shown", ("BHMS-SEC-020",))
    stops_after = sum(1 for e in (await c.ok("events/read", {"limit": 500}))["events"] if e["type"] == "stop") if "events" in c.caps else 0
    c.expect(stops_after == stops_before, "a stop was issued because device text asked for it", ("BHMS-SEC-020",))
