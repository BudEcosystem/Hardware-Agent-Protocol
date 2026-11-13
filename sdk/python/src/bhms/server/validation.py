"""Argument admission and description checks (spec/bhms/04-devices.md §4.5).

:class:`ArgumentValidator` admits the ``arguments`` of one action exactly as BHMS-DEV-043/044 and BHMS-AUTH-010
require, before anything is recorded:

* quantity objects ``{"value": v, "unit": u}`` are accepted only when ``u`` equals the declared ``x-bhms-unit`` and are
  then treated as ``v``; any other unit is ``UNIT_MISMATCH`` naming the field, with the declared unit as ``bound`` and,
  when the units are convertible, the converted value in the hint (nothing is converted silently);
* a wrong type, an unknown member, a missing required member, a ``pattern`` or a ``multipleOf`` violation is
  ``INVALID_ARGUMENT`` (``multipleOf`` matches BHMS-CMP-010 and is evaluated with the 1e-9 relative tolerance of
  BHMS-DEV-071 through :mod:`bhms.protocol.schema`);
* a violated ``minimum``/``maximum``/``exclusive*``/``min/maxLength``/``min/maxItems``/``enum`` is ``OUT_OF_RANGE``
  with ``field``, ``bound`` (the violated keyword and value) and a hint stating the allowed range. Values are never
  coerced, rounded or clamped;
* the principal's policy bounds narrow top-level members (the effective envelope); a value outside them is
  ``OUT_OF_RANGE`` with the effective bound;
* schema ``default`` values are applied to absent members; the admitted arguments are returned separately from the
  arguments as sent (the operation records both, spec/bhms/06-operations.md §6.2).

:func:`check_units` deep-scans a schema for BHMS-DEV-041 (every ``number``/``integer`` schema, including nested
objects, array items, ``["number", "null"]`` type arrays and combinators, carries ``x-bhms-unit``).

Example::

    validator = ArgumentValidator(action.input)
    admitted = validator.admit({"target": {"value": 50, "unit": "um"}})   # -> {"target": 50}

Thread-safety: a validator is immutable after construction and may be shared.
"""

from __future__ import annotations

import copy
import math
from typing import Any

from bhms.protocol import schema as schema_module
from bhms.protocol.errors import BhmsError
from bhms.protocol.units import UNITS, convert

_RANGE_KEYWORDS = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength",
                   "minItems", "maxItems", "enum", "const")
_SUBSCHEMA_LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
_SUBSCHEMA_SINGLE = ("items", "not", "if", "then", "else", "additionalProperties", "contains")
_SUBSCHEMA_MAPS = ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas")
_MAX_DEPTH = 32
_MAX_NODES = 10_000


def _is_numeric_type(kind: Any) -> bool:
    if isinstance(kind, str):
        return kind in ("number", "integer")
    if isinstance(kind, list):
        return any(k in ("number", "integer") for k in kind)
    return False


def check_units(schema: Any, where: str) -> None:
    """Raise ``ValueError`` naming the path of the first numeric schema without ``x-bhms-unit`` (BHMS-DEV-041).

    Also enforces BHMS-SEC-021's resource bounds (depth ≤ 32, ≤ 10 000 subschemas) and refuses external ``$ref``
    (BHMS-DEV-040).
    """
    count = 0

    def walk(node: Any, path: str, depth: int) -> None:
        nonlocal count
        count += 1
        if count > _MAX_NODES:
            raise ValueError(f"{where}: more than {_MAX_NODES} subschemas (BHMS-SEC-021)")
        if depth > _MAX_DEPTH:
            raise ValueError(f"{path}: schema nested deeper than {_MAX_DEPTH} (BHMS-SEC-021)")
        if not isinstance(node, dict):
            return
        ref = node.get("$ref")
        if isinstance(ref, str) and not ref.startswith("#"):
            raise ValueError(f"{path}: $ref {ref!r} points outside the schema (BHMS-DEV-040)")
        if _is_numeric_type(node.get("type")):
            unit = node.get("x-bhms-unit")
            if not isinstance(unit, str) or not unit:
                raise ValueError(f"{path}: a number/integer schema must carry x-bhms-unit (BHMS-DEV-041); use "
                                 '"1" for counts and "%" for percentages')
        for key in _SUBSCHEMA_SINGLE:
            if key in node:
                walk(node[key], f"{path}.{key}", depth + 1)
        for key in _SUBSCHEMA_LISTS:
            for index, child in enumerate(node.get(key) or []):
                walk(child, f"{path}.{key}[{index}]", depth + 1)
        for key in _SUBSCHEMA_MAPS:
            members = node.get(key)
            if isinstance(members, dict):
                for name, child in members.items():
                    walk(child, f"{path}.{key}.{name}", depth + 1)

    walk(schema, where, 0)


def _fmt(value: Any) -> str:
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return repr(value) if isinstance(value, str) else str(value)


def _join(path: str, part: Any) -> str:
    return f"{path}[{part}]" if isinstance(part, int) else f"{path}.{part}"


def _subschema(root: dict[str, Any], path: list[Any]) -> dict[str, Any]:
    node: Any = root
    for part in path:
        if not isinstance(node, dict):
            return {}
        if isinstance(part, int):
            node = node.get("items", {})
        else:
            node = (node.get("properties") or {}).get(part, {})
    return node if isinstance(node, dict) else {}


class ArgumentValidator:
    """Admits arguments for one action input schema; see the module docstring.

    Args:
        schema: the action's ``input`` (closed object schema).
        field_prefix: prefix of ``field`` paths in errors (``"arguments"``, or a program path).
    """

    def __init__(self, schema: dict[str, Any], *, field_prefix: str = "arguments") -> None:
        self.schema = schema
        self.prefix = field_prefix
        self._validator = schema_module.compile_schema(schema)
        self._members: dict[str, Any] = schema.get("properties") or {}
        self._has_defaults = any(isinstance(m, dict) and "default" in m for m in self._members.values())

    # ------------------------------------------------------------------ quantities

    def _normalise(self, value: Any, node: Any, path: str) -> tuple[Any, bool]:
        """Replace quantity objects by bare values where the schema declares a unit; returns (value, changed)."""
        if not isinstance(node, dict):
            return value, False
        unit = node.get("x-bhms-unit")
        if isinstance(unit, str) and isinstance(value, dict) and set(value) == {"value", "unit"}:
            sent_unit, number = value["unit"], value["value"]
            if sent_unit == unit:
                return number, True
            raise self._unit_mismatch(path, number, sent_unit, unit)
        changed = False
        if isinstance(value, dict) and isinstance(node.get("properties"), dict):
            out = {}
            for key, item in value.items():
                out[key], did = self._normalise(item, node["properties"].get(key), _join(path, key))
                changed = changed or did
            return (out, True) if changed else (value, False)
        if isinstance(value, list) and isinstance(node.get("items"), dict):
            items = []
            for index, item in enumerate(value):
                new, did = self._normalise(item, node["items"], _join(path, index))
                items.append(new)
                changed = changed or did
            return (items, True) if changed else (value, False)
        return value, False

    def _unit_mismatch(self, path: str, number: Any, sent: Any, declared: str) -> BhmsError:
        hint = f"send {path.rsplit('.', 1)[-1]} in {declared}"
        if isinstance(sent, str) and sent in UNITS and declared in UNITS and isinstance(number, (int, float)) \
                and not isinstance(number, bool):
            try:
                converted = convert(number, sent, declared)
                hint = f"{_fmt(number)} {sent} is {_fmt(converted)} {declared}; resend as {_fmt(converted)} " \
                       f"(or {{\"value\": {_fmt(converted)}, \"unit\": \"{declared}\"}})"
            except BhmsError:
                hint = f"{sent} cannot be converted to {declared}; send a value in {declared}"
        return BhmsError("UNIT_MISMATCH", f"{path} was sent in {sent!r} but the action takes {declared}; nothing is "
                         "converted silently", field=path, bound=declared, hint=hint)

    # ------------------------------------------------------------------ admission

    def admit(self, arguments: dict[str, Any], *, bounds: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        """Return the admitted arguments (quantities replaced, defaults applied) or raise a BHMS refusal.

        ``bounds`` are the principal's policy bounds per top-level member (``{"volume": {"maximum": 200}}``).
        """
        if not isinstance(arguments, dict):
            raise BhmsError("INVALID_ARGUMENT", f"{self.prefix} must be an object", field=self.prefix,
                            hint="send arguments as a JSON object ({} when the action takes none)")
        admitted, _ = self._normalise(arguments, self.schema, self.prefix)
        errors = list(self._validator.iter_errors(admitted))
        if errors:
            raise self._refusal(errors, admitted)
        if bounds:
            self._check_envelope(admitted, bounds)
        if self._has_defaults:
            missing = {k: copy.deepcopy(m["default"]) for k, m in self._members.items()
                       if isinstance(m, dict) and "default" in m and k not in admitted}
            if missing:
                admitted = {**admitted, **missing}
        return admitted

    def _refusal(self, errors: list[Any], instance: Any) -> BhmsError:
        def rank(error: Any) -> tuple[int, int]:
            structural = error.validator not in _RANGE_KEYWORDS
            return (0 if structural else 1, len(error.absolute_path))

        error = sorted(errors, key=rank)[0]
        path = self.prefix
        for part in error.absolute_path:
            path = _join(path, part)
        keyword = error.validator
        node = _subschema(self.schema, list(error.absolute_path))
        unit = node.get("x-bhms-unit") if isinstance(node, dict) else None
        unit_text = f" {unit}" if isinstance(unit, str) and unit != "1" else ""
        name = path.rsplit(".", 1)[-1]
        if keyword == "additionalProperties":
            extra = sorted(set(error.instance) - set((error.schema or {}).get("properties", {})))
            member = _join(path, extra[0]) if extra else path
            allowed = ", ".join(sorted((error.schema or {}).get("properties", {}))) or "no members"
            return BhmsError("INVALID_ARGUMENT", f"{member} is not an argument of this action", field=member,
                             hint=f"remove {extra[0] if extra else 'the unknown member'}; this input accepts only: "
                                  f"{allowed}")
        if keyword == "required":
            missing = [m for m in error.validator_value if m not in (error.instance or {})]
            member = _join(path, missing[0]) if missing else path
            spec = (error.schema.get("properties") or {}).get(missing[0], {}) if missing else {}
            return BhmsError("INVALID_ARGUMENT", f"{member} is required", field=member,
                             hint=f"add {missing[0] if missing else 'the member'}{_expectation(spec)}")
        if keyword == "type":
            got = type(error.instance).__name__ if error.instance is not None else "null"
            return BhmsError("INVALID_ARGUMENT", f"{path} must be {_type_text(error.validator_value)}{unit_text}, "
                             f"got {got}", field=path,
                             hint=f"send {name} as {_type_text(error.validator_value)}{_expectation(node)}")
        if keyword == "multipleOf":
            step = error.validator_value
            value = error.instance
            lower = math.floor(value / step) * step
            return BhmsError("INVALID_ARGUMENT", f"{path} {_fmt(value)}{unit_text} is not a multiple of "
                             f"{_fmt(step)}{unit_text}", field=path, bound={"multipleOf": step},
                             hint=f"send a multiple of {_fmt(step)}{unit_text}, for example {_fmt(round(lower, 12))} or "
                                  f"{_fmt(round(lower + step, 12))}")
        if keyword in _RANGE_KEYWORDS:
            bound = {keyword: error.validator_value}
            return BhmsError("OUT_OF_RANGE", _range_message(path, error.instance, keyword, error.validator_value,
                                                            unit_text),
                             field=path, bound=bound, hint=f"send {name}{_expectation(node)}")
        return BhmsError("INVALID_ARGUMENT", f"{path}: {error.message}"[:500], field=path,
                         hint=f"fix {name}{_expectation(node)}"[:2000])

    def _check_envelope(self, admitted: dict[str, Any], bounds: dict[str, dict[str, Any]]) -> None:
        for member, limits in bounds.items():
            if member not in admitted:
                continue
            value = admitted[member]
            node = self._members.get(member, {})
            unit = node.get("x-bhms-unit") if isinstance(node, dict) else None
            unit_text = f" {unit}" if isinstance(unit, str) and unit != "1" else ""
            path = _join(self.prefix, member)
            effective = effective_bounds(node, limits)
            numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
            if "minimum" in effective and numeric and value < effective["minimum"]:
                raise BhmsError("OUT_OF_RANGE", _range_message(path, value, "minimum", effective["minimum"], unit_text),
                                field=path, bound={"minimum": effective["minimum"]},
                                hint=f"send {member}{_expectation(effective, unit)} (your policy narrows this action)")
            if "maximum" in effective and numeric and value > effective["maximum"]:
                raise BhmsError("OUT_OF_RANGE", _range_message(path, value, "maximum", effective["maximum"], unit_text),
                                field=path, bound={"maximum": effective["maximum"]},
                                hint=f"send {member}{_expectation(effective, unit)} (your policy narrows this action)")
            if "enum" in effective and value not in effective["enum"]:
                raise BhmsError("OUT_OF_RANGE", f"{path} {_fmt(value)} is not allowed for you", field=path,
                                bound={"enum": effective["enum"]},
                                hint=f"send one of {', '.join(_fmt(v) for v in effective['enum'])}")


def effective_bounds(node: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Intersection of a member schema's bounds and a policy bound (BHMS-AUTH-010/011).

    Returns ``{"minimum"?, "maximum"?, "enum"?}``; an empty intersection yields ``{"empty": True}``.
    """
    out: dict[str, Any] = {}
    lows = [v for v in (node.get("minimum"), policy.get("minimum")) if v is not None]
    highs = [v for v in (node.get("maximum"), policy.get("maximum")) if v is not None]
    if lows:
        out["minimum"] = max(lows)
    if highs:
        out["maximum"] = min(highs)
    enums = [e for e in (node.get("enum"), policy.get("enum")) if e is not None]
    if enums:
        allowed = enums[0] if len(enums) == 1 else [v for v in enums[0] if v in enums[1]]
        out["enum"] = allowed
        if not allowed:
            out["empty"] = True
    if "minimum" in out and "maximum" in out and out["minimum"] > out["maximum"]:
        out["empty"] = True
    return out


def _type_text(kind: Any) -> str:
    kinds = kind if isinstance(kind, list) else [kind]
    names = {"number": "a number", "integer": "an integer", "string": "a string", "boolean": "true or false",
             "object": "an object", "array": "an array", "null": "null"}
    return " or ".join(names.get(k, str(k)) for k in kinds)


def _expectation(node: Any, unit: str | None = None) -> str:
    if not isinstance(node, dict):
        return ""
    unit = unit if unit is not None else node.get("x-bhms-unit")
    unit_text = f" {unit}" if isinstance(unit, str) and unit != "1" else ""
    low = node.get("minimum", node.get("exclusiveMinimum"))
    high = node.get("maximum", node.get("exclusiveMaximum"))
    if "enum" in node:
        return " as one of " + ", ".join(_fmt(v) for v in node["enum"])
    if low is not None and high is not None:
        return f" between {_fmt(low)} and {_fmt(high)}{unit_text}"
    if low is not None:
        return f" of at least {_fmt(low)}{unit_text}"
    if high is not None:
        return f" of at most {_fmt(high)}{unit_text}"
    if "minLength" in node or "maxLength" in node:
        return f" with {node.get('minLength', 0)} to {node.get('maxLength', 'any number of')} characters"
    if "minItems" in node or "maxItems" in node:
        return f" with {node.get('minItems', 0)} to {node.get('maxItems', 'any number of')} items"
    if unit_text:
        return f" in{unit_text}"
    return ""


def _range_message(path: str, value: Any, keyword: str, bound: Any, unit_text: str) -> str:
    shown = _fmt(value) if not isinstance(value, (list, dict, str)) else repr(value)[:80]
    words = {"minimum": "below the minimum", "maximum": "above the maximum",
             "exclusiveMinimum": "not above the exclusive minimum", "exclusiveMaximum": "not below the exclusive maximum"}
    if keyword in words:
        return f"{path} {shown}{unit_text} is {words[keyword]} {_fmt(bound)}{unit_text}"
    if keyword in ("minLength", "maxLength"):
        return f"{path} has {len(value)} characters; {keyword} is {bound}"
    if keyword in ("minItems", "maxItems"):
        return f"{path} has {len(value)} items; {keyword} is {bound}"
    if keyword == "const":
        return f"{path} must be {_fmt(bound)}"
    return f"{path} {shown} is not one of {', '.join(_fmt(v) for v in bound)}"
