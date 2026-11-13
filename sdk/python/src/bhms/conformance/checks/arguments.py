"""Chapter 4.5 and 6.5: argument validation, units, bounds, no silent coercion, no authority from arguments."""

from __future__ import annotations

import math
from typing import Any

from bhms.conformance.checks._util import numeric_inputs, vectors
from bhms.conformance.context import Context
from bhms.conformance.core import check


def _valid_value(schema: dict[str, Any]) -> Any:
    """A value that satisfies ``schema`` (numbers: inside the bounds, on the step), or ``KeyError`` when unknown."""
    kind = schema.get("type")
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    if kind in ("number", "integer"):
        low, high = schema.get("minimum", 0), schema.get("maximum", 1)
        step = schema.get("multipleOf")
        value = low if "minimum" in schema else min(max(low, 0), high)
        if step and kind == "number":
            value = round(math.ceil(value / step) * step, 10)
        return int(value) if kind == "integer" else value
    if kind == "boolean":
        return False
    if kind == "string":
        return "x" * schema.get("minLength", 1)
    raise KeyError(kind)


def _base_arguments(input_schema: dict[str, Any]) -> dict[str, Any] | None:
    out = {}
    for member in input_schema.get("required") or []:
        try:
            out[member] = _valid_value((input_schema.get("properties") or {})[member])
        except KeyError:
            return None
    return out


async def _count_ops(c: Context) -> int:
    return await c.operations_count()


@check("arguments.refusals-from-description", ["BHMS-DEV-043", "BHMS-DEV-044", "BHMS-OPS-040", "BHMS-ERR-003", "BHMS-ERR-011"], generic=True, effects=True)
async def refusals_from_description(c: Context) -> None:
    """Out-of-range, wrong-type, wrong-unit, unknown and missing members derived from every declared input are refused
    with the right code, naming the field, with mayHaveActed false, and no operation is created."""
    problems: list[str] = []
    tried = 0
    before = await _count_ops(c)
    for device, description in (await c.descriptions()).items():
        for action_name, member, schema, _required in numeric_inputs(description):
            action = description["actions"][action_name]
            base = _base_arguments(action.get("input") or {})
            if base is None:
                continue
            field = f"arguments.{member}"
            unit = schema.get("x-bhms-unit", "1")
            cases: list[tuple[str, Any, set[str]]] = [("string for a number", "5", {"INVALID_ARGUMENT"}),
                                                       ("null", None, {"INVALID_ARGUMENT"}),
                                                       ("boolean", True, {"INVALID_ARGUMENT"})]
            wrong = "s" if unit != "s" else "mm"
            cases.append(("incompatible unit", {"value": 1, "unit": wrong}, {"UNIT_MISMATCH"}))
            if "maximum" in schema:
                over = math.nextafter(float(schema["maximum"]), math.inf)
                cases.append(("one ulp above maximum", over if schema["type"] == "number" else schema["maximum"] + 1, {"OUT_OF_RANGE"}))
            if "minimum" in schema:
                under = math.nextafter(float(schema["minimum"]), -math.inf)
                cases.append(("one ulp below minimum", under if schema["type"] == "number" else schema["minimum"] - 1, {"OUT_OF_RANGE"}))
            if schema["type"] == "integer":
                cases.append(("fractional integer", 1.5, {"INVALID_ARGUMENT"}))
            for label, value, codes in cases:
                tried += 1
                response = await c.invoke(device, action_name, {**base, member: value})
                where = f"{device}.{action_name} {label}"
                if response.code not in codes:
                    problems.append(f"{where}: expected {sorted(codes)}, got {response.describe()}")
                    continue
                if response.data.get("mayHaveActed") is not False:
                    problems.append(f"{where}: mayHaveActed must be false")
                if response.data.get("field") != field:
                    problems.append(f"{where}: field should be {field!r}, is {response.data.get('field')!r}")
                if response.code in ("OUT_OF_RANGE", "UNIT_MISMATCH") and response.data.get("bound") in (None, ""):
                    problems.append(f"{where}: {response.code} carries no bound")
                text = (response.error.get("message", "") + " " + response.data.get("hint", ""))
                if member not in text:
                    problems.append(f"{where}: message and hint do not name {member!r}")
            tried += 2
            unknown = await c.invoke(device, action_name, {**base, "undeclared_member": 1})
            if unknown.code != "INVALID_ARGUMENT" or unknown.data.get("field") != "arguments.undeclared_member":
                problems.append(f"{device}.{action_name} unknown member: {unknown.describe()}")
            if base and member in base:
                missing = await c.invoke(device, action_name, {k: v for k, v in base.items() if k != member})
                if missing.code != "INVALID_ARGUMENT" or missing.data.get("field") != field:
                    problems.append(f"{device}.{action_name} missing {member}: {missing.describe()}")
    if tried == 0:
        c.not_applicable("no action with a numeric input whose other members can be derived from the description")
    after = await _count_ops(c)
    c.expect(after == before, f"refused invokes created {after - before} operations (BHMS-OPS-040)")
    c.expect(not problems, "; ".join(problems[:6]))


@check("arguments.unexecutable-refusals", ["BHMS-OPS-040", "BHMS-ERR-004", "BHMS-DEV-044"], generic=True)
async def unexecutable_refusals(c: Context) -> None:
    """Requests that name no existing device or action are refused, create no operation and cannot execute even on a server
    that validates nothing: unknown action, unknown device, malformed device id, arguments of the wrong JSON type."""
    summaries = await c.devices()
    real = summaries[0]["deviceId"] if summaries else "no_such_device"
    before = await _count_ops(c)
    cases = [("unknown action", real, "no_such_action", {}, {"UNKNOWN_ACTION"}),
             ("unknown device", "no_such_device", "no_such_action", {}, {"UNKNOWN_DEVICE"}),
             ("arguments not an object", "no_such_device", "no_such_action", ["not", "an", "object"], {"INVALID_ARGUMENT", "UNKNOWN_DEVICE"}),
             ("arguments a string", real, "no_such_action", "x", {"INVALID_ARGUMENT", "UNKNOWN_ACTION"})]
    for label, device, action, arguments, codes in cases:
        response = await c.call("actions/invoke", {"deviceId": device, "action": action, "arguments": arguments})
        c.expect(response.code in codes and response.data.get("mayHaveActed") is False,
                 f"{label}: expected {sorted(codes)} with mayHaveActed false, got {response.describe()}", ("BHMS-ERR-004", "BHMS-DEV-044"))
    bad_id = await c.call("actions/invoke", {"deviceId": "bad id/with spaces", "action": "no_such_action", "arguments": {}})
    c.expect(bad_id.code in ("INVALID_ARGUMENT", "UNKNOWN_DEVICE"), f"a malformed deviceId: {bad_id.describe()}", ("BHMS-DEV-044",))
    c.expect(await _count_ops(c) == before, "a refused request created an operation (BHMS-OPS-040)", ("BHMS-OPS-040",))


def _codes(expected: Any) -> set[str]:
    return set(expected) if isinstance(expected, list) else {expected}


def _device_for(c: Context, name: str) -> str:
    return c.axis() if name == "axis-1" else c.pump() if name == "pump-1" else name


@check("arguments.vectors-refusals", ["BHMS-DEV-043", "BHMS-DEV-044", "BHMS-SEC-030", "BHMS-OPS-040", "BHMS-ERR-004"])
async def vector_refusals(c: Context) -> None:
    """The shared argument vectors for the conformance device: each refusal exact, no operation, no device effect."""
    ops_before = await _count_ops(c)
    counter_before = await c.counter(c.axis())
    problems = []
    for case in vectors("arguments")["refused"]:
        expect = case["expect"]
        response = await c.invoke(_device_for(c, case["device"]), case["action"], case["arguments"])
        if response.code not in _codes(expect["code"]):
            problems.append(f"{case['name']}: expected {expect['code']}, got {response.describe()}")
            continue
        if "field" in expect and response.data.get("field") != expect["field"]:
            problems.append(f"{case['name']}: field {response.data.get('field')!r}, expected {expect['field']!r}")
        if response.data.get("mayHaveActed") is not False:
            problems.append(f"{case['name']}: mayHaveActed must be false")
        if "bound" in expect and not (isinstance(response.data.get("bound"), dict) and expect["bound"] in response.data["bound"]):
            problems.append(f"{case['name']}: bound should carry {expect['bound']!r}, is {response.data.get('bound')!r}")
    c.expect(not problems, "; ".join(problems[:6]))
    c.expect(await _count_ops(c) == ops_before, "a refused invoke created an operation (BHMS-OPS-040)")
    c.expect(await c.counter(c.axis()) == counter_before, "a refused invoke reached the device (the device-side counter moved)")


@check("arguments.vectors-accepted", ["BHMS-DEV-043", "BHMS-DEV-044"])
async def vector_accepted(c: Context) -> None:
    """A quantity in the declared unit is accepted and unwrapped; bounds are inclusive; the step is tolerant."""
    for case in vectors("arguments")["accepted"]:
        op = await c.run(_device_for(c, case["device"]), case["action"], case["arguments"])
        c.expect(op["state"] == "completed", f"{case['name']}: ended {op['state']} {op.get('error')}")
        admitted = case["expect"].get("admitted")
        if admitted is not None:
            c.expect(op.get("admittedArguments") == admitted, f"{case['name']}: admittedArguments {op.get('admittedArguments')} != {admitted}")
            c.expect(op["arguments"] == case["arguments"], f"{case['name']}: arguments must be recorded exactly as sent")
