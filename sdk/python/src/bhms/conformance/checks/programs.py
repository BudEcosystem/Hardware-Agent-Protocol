"""Chapter 8: programs (profile ``programs``) and the registry (profile ``registry``)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from bhms.conformance.checks._util import vectors
from bhms.conformance.context import SETTLED, Context
from bhms.conformance.core import check
from bhms.protocol.canonical import digest


def _program(c: Context, template: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(template).replace("{{axis}}", c.axis()))


async def _run(c: Context, program: dict[str, Any], arguments: dict[str, Any] | None = None, **members: Any) -> dict[str, Any]:
    response = await c.call("programs/run", {"program": program, "arguments": arguments or {}, **members}, timeout=60)
    op = c.result(response, "programs/run")["operation"]
    return op if op["state"] in SETTLED else await c.settle(op["operationId"], 30)


@check("programs.validation-refusals", ["BHMS-PRG-001", "BHMS-PRG-002", "BHMS-PRG-003", "BHMS-PRG-004", "BHMS-PRG-005"], profile="programs")
async def validation_refusals(c: Context) -> None:
    """Every class of invalid program is refused before any step, naming the program path, creating no operation."""
    base_ops = await c.operations_count()
    counter = await c.counter(c.axis())
    problems = []
    for case in vectors("programs")["invalid"]:
        response = await c.call("programs/run", {"program": _program(c, case["program"]), "arguments": case["arguments"]})
        expect = case["expect"]
        if response.code not in expect["codes"]:
            problems.append(f"{case['name']}: expected {expect['codes']}, got {response.describe()}")
            continue
        if response.data.get("mayHaveActed") is not False:
            problems.append(f"{case['name']}: mayHaveActed must be false")
        field = response.data.get("field", "")
        if "field" in expect and not (field == expect["field"] or field.startswith(expect["field"]) or expect["field"].startswith(field) and field.startswith("program")):
            problems.append(f"{case['name']}: field {field!r}, expected {expect['field']!r}")
        if "bound" in expect and response.data.get("bound") != expect["bound"]:
            problems.append(f"{case['name']}: bound {response.data.get('bound')!r}, expected {expect['bound']!r}")
    c.expect(not problems, "; ".join(problems[:6]))
    c.expect(await c.operations_count() == base_ops, "a refused program created an operation")
    c.expect(await c.counter(c.axis()) == counter, "a refused program reached the device")


@check("programs.execution-order-and-effects", ["BHMS-PRG-007", "BHMS-PRG-010", "BHMS-PRG-015", "BHMS-PRG-016"], profile="programs")
async def execution(c: Context) -> None:
    """Steps run in order as derived-key child operations; history and progress describe them; digest and effect hold."""
    templates = vectors("programs")["valid"]
    program = _program(c, templates["ordered"])
    op = await _run(c, program)
    c.expect(op["state"] == "completed", f"program ended {op['state']}: {op.get('error')}")
    c.expect(op["programDigest"] == digest(program), "the program digest must be the BHMS digest of the program object (BHMS-PRG-007)")
    full = await c.get_op(op["operationId"])
    steps = [h for h in full["history"] if h.get("kind") == "step"]
    c.expect([h["stepIndex"] for h in steps] == [0, 1, 2, 3], f"history needs one step entry per started step, in order: {[h.get('stepIndex') for h in steps]}")
    children = [o for o in (await c.ok("operations/list", {"parentOperationId": op["operationId"], "limit": 50}))["operations"]]
    c.expect(len(children) == 2, f"two invoke steps must create two child operations, found {len(children)}")
    by_created = sorted(children, key=lambda o: o["createdAt"])
    for position, child in zip((0, 2), by_created):
        c.expect(child["parentOperationId"] == op["operationId"] and child["keyOrigin"] == "derived", "a child carries parentOperationId and keyOrigin derived")
        expected = "d-" + hashlib.sha256(f"{op['operationId']}/{position}".encode()).hexdigest()[:40]
        c.expect(child["operationKey"] == expected, f"derived key must be d- + sha256(parent/path)[:40]: {child['operationKey']} != {expected}")
    c.expect(by_created[0]["createdAt"] <= by_created[1]["createdAt"] and by_created[0]["state"] == by_created[1]["state"] == "completed", "children ran in order")
    c.expect(full["progress"] == {"stepsCompleted": 4, "stepsTotal": 4}, f"progress {full['progress']}")
    c.expect(op["effect"] == "unverified", f"every child effect reported-only: program effect must be unverified, is {op['effect']}")
    none = await _run(c, _program(c, templates["no_effect"]))
    c.expect(none["state"] == "completed" and none["effect"] == "none", f"a program with no effectful child has effect none: {none['state']}/{none['effect']}")


@check("programs.step-failure-stops", ["BHMS-PRG-011", "BHMS-PRG-016"], profile="programs")
async def step_failure(c: Context) -> None:
    """A failing step ends the program with its error; no later step starts; earlier effects stay recorded."""
    axis = c.axis()
    base = await c.counter(axis)
    op = await _run(c, _program(c, vectors("programs")["valid"]["failing"]))
    err = op.get("error") or {}
    c.expect(op["state"] == "failed" and err.get("bhmsCode") == "DEVICE_FAULT" and err.get("mayHaveActed") is True, f"program: {op['state']} {err}")
    full = await c.get_op(op["operationId"])
    c.expect([h["stepIndex"] for h in full["history"] if h.get("kind") == "step"] == [0, 1], "no step may start after the failing one")
    c.expect(await c.counter(axis) == base + 2, "exactly the first two steps reached the device")
    c.expect(full["progress"]["stepsCompleted"] == 1, f"progress after a failure at step 1: {full['progress']}")


@check("programs.assert-and-wait-until", ["BHMS-PRG-013"], profile="programs", needs=("faults",))
async def assert_and_wait(c: Context) -> None:
    """A false assert fails with STALE and the message as hint; waitUntil never accepts invalid samples and times out."""
    templates = vectors("programs")["valid"]
    op = await _run(c, _program(c, templates["assert_false"]))
    err = op.get("error") or {}
    c.expect(op["state"] == "failed" and err.get("bhmsCode") == "STALE" and "conformance assert message" in err.get("hint", ""), f"false assert: {op['state']} {err}")
    await c.inject("sensor_invalid")
    op = await _run(c, _program(c, templates["wait_until_invalid"]))
    err = op.get("error") or {}
    c.expect(op["state"] == "failed" and err.get("bhmsCode") == "DEADLINE_EXCEEDED", f"waitUntil on an invalid sensor must time out: {op['state']} {err}")


@check("programs.cancel", ["BHMS-PRG-014"], profile="programs")
async def cancel(c: Context) -> None:
    """Cancelling a program stops further steps and forwards the cancellation to the running child."""
    axis = c.axis()
    base = await c.counter(axis)
    response = await c.call("programs/run", {"program": _program(c, vectors("programs")["valid"]["long"]), "arguments": {}})
    op = c.result(response)["operation"]
    for _ in range(100):  # the first step is running: its child exists and its command has reached the device
        kids = (await c.ok("operations/list", {"parentOperationId": op["operationId"]}))["operations"]
        if kids and await c.counter(axis) > base:
            break
        await asyncio.sleep(0.02)
    c.expect(kids, "the program never started its first step")
    await c.ok("operations/cancel", {"operationId": op["operationId"], "reason": "conformance"})
    final = await c.settle(op["operationId"], 8)
    c.expect(final["state"] == "canceled", f"a cancelled program ends canceled, ended {final['state']}")
    child = await c.settle(kids[0]["operationId"], 8)
    c.expect(child["state"] == "canceled", f"the running child must be cancelled too, ended {child['state']}")
    c.expect(await c.counter(axis) == base + 1, "no further step may start after the cancellation")


@check("programs.restart-never-resumes", ["BHMS-PRG-017"], profile="programs", needs=("restart", "durable"), timeout=60)
async def restart_never_resumes(c: Context) -> None:
    """A program running at a kill is settled failed (INTERNAL) from its step history after restart; never resumed."""
    op = (await c.ok("programs/run", {"program": _program(c, vectors("programs")["valid"]["interrupted"]), "arguments": {}}))["operation"]
    for _ in range(100):
        current = await c.get_op(op["operationId"])
        if (current.get("progress") or {}).get("stepsCompleted", 0) >= 1:
            break
        await asyncio.sleep(0.02)
    await c.reconnect_base(await c.target.restart(kill=True))
    await c.locate()
    settled = await c.get_op(op["operationId"])
    err = settled.get("error") or {}
    c.expect(settled["state"] == "failed" and err.get("bhmsCode") == "INTERNAL", f"a program interrupted between steps must end failed/INTERNAL: {settled['state']} {err}")
    c.expect("server restarted" in err.get("message", ""), f"the message should say the server restarted: {err.get('message')!r}")
    await asyncio.sleep(0.3)
    c.expect(await c.counter(c.axis()) == 0, "the restarted server resumed the program")
    final = await c.get_op(op["operationId"])
    c.expect(final["state"] == "failed", "a program must stay failed after restart")


@check("programs.registry", ["BHMS-PRG-020", "BHMS-PRG-022", "BHMS-PRG-007"], profile="registry")
async def registry(c: Context) -> None:
    """Registration is content-addressed and immutable; unregistered digests are refused; inline and digest runs share
    one intent."""
    program = _program(c, vectors("programs")["valid"]["no_effect"])
    program["name"] = "conf_registry_" + c.unique("p").replace("-", "_")
    info = (await c.ok("programs/register", {"program": program}))["info"]
    c.expect(info["digest"] == digest(program), "the registered digest must equal the digest of the program object")
    again = (await c.ok("programs/register", {"program": program}))["info"]
    c.expect(again == info, "registering an already registered digest must return the same info")
    got = await c.ok("programs/get", {"digest": info["digest"]})
    c.expect(got["program"] == program and got["info"]["digest"] == info["digest"], "programs/get must return the registered program unchanged")
    listed = [p["digest"] async for p in _paged(c)]
    c.expect(info["digest"] in listed, "programs/list must include the registered program")
    unknown = "sha256:" + "ab" * 32
    c.refused(await c.call("programs/get", {"digest": unknown}), "INVALID_ARGUMENT", field="digest", what="programs/get of an unregistered digest")
    c.refused(await c.call("programs/run", {"digest": unknown, "arguments": {}}), "INVALID_ARGUMENT", field="digest", what="programs/run of an unregistered digest")
    key = c.unique("prog-key")
    inline = (await c.ok("programs/run", {"program": program, "arguments": {}, "operationKey": key, "waitMs": 2000}))
    byte = (await c.ok("programs/run", {"digest": info["digest"], "arguments": {}, "operationKey": key, "waitMs": 2000}))
    c.expect(byte["replayed"] is True and byte["operation"]["operationId"] == inline["operation"]["operationId"],
             "an inline program and its registered digest with the same arguments are the same intent")


async def _paged(c: Context):
    cursor = None
    while True:
        page = await c.ok("programs/list", {"limit": 50, **({"cursor": cursor} if cursor else {})})
        for item in page["programs"]:
            yield item
        cursor = page.get("nextCursor")
        if not cursor:
            return


@check("programs.max-duration-enforced", ["BHMS-PRG-012"], profile="programs")
async def program_max_duration(c: Context) -> None:
    """The program's own maxDurationMs is enforced while a step waits behind busy work: it ends failed DEADLINE_EXCEEDED, the
    waiting step never starts."""
    import asyncio

    axis = c.axis()
    base = await c.counter(axis)
    busy = await c.invoke_op(axis, "slow_move", {"duration_ms": 2500})
    op = await _run(c, _program(c, vectors("programs")["valid"]["queued"]))
    err = op.get("error") or {}
    c.expect(op["state"] in ("failed", "unknown") and err.get("bhmsCode") == "DEADLINE_EXCEEDED",
             f"a program that exceeded its maxDurationMs must end failed/DEADLINE_EXCEEDED: {op['state']} {err}")
    await c.settle(busy["operationId"], 8)
    await asyncio.sleep(0.2)
    c.expect(await c.counter(axis) == base + 1, "the waiting step must not start after the program's time ran out")
