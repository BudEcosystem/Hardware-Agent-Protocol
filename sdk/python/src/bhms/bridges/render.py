"""Text for models and people: one-line summaries, signature blocks and example arguments (spec 12.2, 12.3).

Everything here is a pure function of BHMS wire objects (camelCase dicts), so the MCP bridge, the OpenAI adapter and the
``bhms`` CLI print the same words:

* :func:`summarize_operation`, :func:`summarize_observation`, :func:`summarize_stop`, :func:`summarize_find`,
  :func:`summarize_refusal` build the one-line summary (at most :data:`SUMMARY_LIMIT` characters, no newline).
  Device-provided text is always quoted and cut to 60 characters (BHMS-AGT-012); ``replayed`` and the retry-safety suffix
  are never truncated away (BHMS-AGT-011, AGT-030).
* :func:`signature_block` is the compact device description of BHMS-AGT-013 (at most :data:`SIGNATURE_TOKENS` tokens,
  measured with the conservative :func:`estimate_tokens`; larger devices are elided level by level and say so).
* :func:`example_arguments` builds a valid example from an action's input schema, used in refusal hints (AGT-021).

Thread-safety: pure functions.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

SUMMARY_LIMIT = 200
SIGNATURE_TOKENS = 400
DEVICE_TEXT_LIMIT = 60
SETTLED = frozenset({"completed", "failed", "canceled", "rejected", "unknown"})
OUTCOME_UNKNOWN = "outcome unknown — check before retrying"


def estimate_tokens(text: str) -> int:
    """A deliberately pessimistic token estimate (3 characters per token) used for budgets; tests measure with tiktoken."""
    return (len(text) + 2) // 3


# ---------------------------------------------------------------------------------------------- small formatting

def clean(text: Any) -> str:
    """One line: control characters and runs of whitespace collapse to a single space."""
    return re.sub(r"\s+", " ", str(text)).strip()


def cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(limit - 1, 0)].rstrip() + "…"


def quote(text: Any, limit: int = DEVICE_TEXT_LIMIT) -> str:
    """Device-provided text, quoted and truncated so it cannot read as an instruction (BHMS-AGT-012, SEC-020)."""
    return '"' + cut(clean(text).replace('"', "'"), limit) + '"'


def num(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.6g}"
    return str(value)


def with_unit(value: Any, unit: str | None) -> str:
    text = num(value) if isinstance(value, (int, float)) else (quote(value) if isinstance(value, str)
                                                               else clean(_json(value)))
    return f"{text} {unit}" if unit and unit != "1" and isinstance(value, (int, float)) else text


def _json(value: Any) -> str:
    import json

    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)


def duration(ms: float) -> str:
    if ms < 1000:
        return f"{int(round(ms))} ms"
    if ms < 60_000:
        return f"{ms / 1000:.1f} s"
    if ms < 3_600_000:
        return f"{ms / 60_000:.1f} min"
    return f"{ms / 3_600_000:.1f} h"


def short_duration(ms: float) -> str:
    """Compact: ``250ms``, ``61s``, ``5min``, ``2h``."""
    if ms < 1000:
        return f"{int(ms)}ms"
    for limit, unit, div in ((120_000, "s", 1000), (7_200_000, "min", 60_000), (float("inf"), "h", 3_600_000)):
        if ms < limit:
            return f"{ms / div:.3g}{unit}"
    raise AssertionError("unreachable")


def _parse_time(text: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def op_duration_ms(op: dict[str, Any]) -> float | None:
    start, end = _parse_time(op.get("createdAt")), _parse_time(op.get("updatedAt"))
    return None if start is None or end is None else max((end - start).total_seconds() * 1000, 0.0)


def compose(head: str, body: str = "", next_step: str = "", suffix: str = "", limit: int = SUMMARY_LIMIT, *,
            next_first: bool = False) -> str:
    """Join the parts within ``limit``: head and suffix are kept, then the next step, and the body takes what is left
    (``next_first``: the next step is kept whole, the body shrinks instead)."""
    head, body, next_step, suffix = clean(head), clean(body), clean(next_step), clean(suffix)
    room = limit - len(head) - (len(suffix) + 1 if suffix else 0)
    if room < 0:  # head alone is too long: cut the head, never the suffix
        head = cut(head, limit - (len(suffix) + 1 if suffix else 0))
        room = 0
    cap = room - 1 if next_first else max(room * 55 // 100, min(room - 1, 40))
    nxt = cut(next_step, cap) if next_step and room > 1 else ""
    room_body = room - (len(nxt) + 1 if nxt else 0)
    bod = cut(body, room_body - 1) if body and room_body > 2 else ""
    return " ".join(p for p in (head, bod, nxt, suffix) if p)


# ---------------------------------------------------------------------------------------------- schemas

def type_text(node: dict[str, Any]) -> str:
    kind = node.get("type")
    if "enum" in node:
        return "|".join(num(v) for v in node["enum"][:8]) + ("|..." if len(node["enum"]) > 8 else "")
    if "const" in node:
        return num(node["const"])
    if isinstance(kind, list):
        kind = "/".join(str(k) for k in kind)
    return str(kind or "any")


def bounds_text(node: dict[str, Any]) -> str:
    low = node.get("minimum", node.get("exclusiveMinimum"))
    high = node.get("maximum", node.get("exclusiveMaximum"))
    parts = []
    if low is not None or high is not None:
        parts.append(f"{'' if low is None else num(low)}..{'' if high is None else num(high)}")
    if node.get("multipleOf") is not None:
        parts.append(f"step {num(node['multipleOf'])}")
    if "minLength" in node or "maxLength" in node:
        parts.append(f"len {node.get('minLength', 0)}..{node.get('maxLength', '')}")
    if "minItems" in node or "maxItems" in node:
        parts.append(f"items {node.get('minItems', 0)}..{node.get('maxItems', '')}")
    return " ".join(parts)


def argument_text(name: str, node: dict[str, Any], required: bool, *, detail: bool = True) -> str:
    unit = node.get("x-bhms-unit")
    text = f"{name}{'' if required else '?'}: {type_text(node)}"
    if not detail:
        return text
    if isinstance(unit, str) and unit != "1":
        text += f" {unit}"
    bounds = bounds_text(node)
    if bounds:
        text += f" {bounds}"
    if "default" in node:
        text += f" ={num(node['default']) if not isinstance(node['default'], (dict, list)) else _json(node['default'])}"
    return text


def example_value(node: Any, depth: int = 0) -> Any:
    """A valid example value for a JSON Schema node (lower bound, first enum member, smallest array)."""
    if not isinstance(node, dict) or depth > 6:
        return None
    if "const" in node:
        return node["const"]
    if "default" in node:
        return node["default"]
    if "enum" in node and node["enum"]:
        return node["enum"][0]
    kind = node.get("type")
    kind = kind[0] if isinstance(kind, list) and kind else kind
    if kind in ("number", "integer"):
        low, high = node.get("minimum"), node.get("maximum")
        value: Any = low if low is not None else (high if high is not None and high < 0 else 0)
        if low is None and node.get("exclusiveMinimum") is not None:
            value = node["exclusiveMinimum"] + 1
        step = node.get("multipleOf")
        if step and isinstance(value, (int, float)) and abs(value / step - round(value / step)) > 1e-9:
            value = round(value / step + 0.5) * step
        if kind == "integer":
            value = int(value)
        elif isinstance(value, float) and value == int(value):
            value = int(value) if "multipleOf" not in node else value
        return value
    if kind == "string":
        return "x" * max(int(node.get("minLength", 1)), 1) if "pattern" not in node else "example"
    if kind == "boolean":
        return True
    if kind == "array":
        count = int(node.get("minItems", 1) or 0)
        return [example_value(node.get("items"), depth + 1) for _ in range(count)]
    if kind == "object" or "properties" in node:
        required = node.get("required") or []
        props = node.get("properties") or {}
        return {k: example_value(props.get(k), depth + 1) for k in required}
    return None


def example_arguments(input_schema: dict[str, Any]) -> dict[str, Any]:
    """Example arguments for an action ``input`` schema: every required member."""
    value = example_value({**input_schema, "type": "object"})
    return value if isinstance(value, dict) else {}


def output_text(output: Any) -> str:
    props = (output or {}).get("properties") if isinstance(output, dict) else None
    if not props:
        return ""
    return ", ".join(f"{k}: {type_text(v)}{' ' + v['x-bhms-unit'] if v.get('x-bhms-unit', '1') != '1' else ''}"
                     for k, v in props.items() if isinstance(v, dict))


# ---------------------------------------------------------------------------------------------- signature block

def _action_line(name: str, action: dict[str, Any], level: int) -> str:
    inp = action.get("input") or {}
    required = set(inp.get("required") or [])
    args = ", ".join(argument_text(k, v, k in required, detail=level < 2) for k, v in (inp.get("properties") or {}).items()
                     if isinstance(v, dict))
    line = f"action {name}({args})"
    if level >= 2:
        return line
    ev = action.get("completionEvidence", "reported")
    if action.get("verifiedBy"):
        ev += f"({','.join(action['verifiedBy'])})"
    line += (f" effect={action.get('effect')} repeat={action.get('idempotency')}"
             f" lease={'required' if action.get('requiresLease') else 'no'}"
             f" cancel={'yes' if action.get('cancel') == 'supported' else 'no'} evidence={ev}"
             f" max={short_duration(action.get('maxDurationMs', 0))}")
    if level == 0:
        out = output_text(action.get("output"))
        if out:
            line += f" -> {{{out}}}"
        fresh = action.get("requiresFresh") or []
        if fresh:
            line += " fresh=" + ",".join(f"{f['property']}<={f.get('maxAgeMs', 0)}ms" for f in fresh)
    return line


def _property_line(name: str, prop: dict[str, Any], level: int) -> str:
    node = prop.get("schema") or {}
    unit = node.get("x-bhms-unit")
    text = f"property {name}"
    if level >= 2:
        return text
    text += f": {type_text(node)}"
    if isinstance(unit, str) and unit != "1":
        text += f" {unit}"
    text += f" {prop.get('evidence', 'reported')}"
    if prop.get("observable"):
        text += " observable"
    if prop.get("readEffect") == "transaction":
        text += " read=transaction"
    return text


def signature_block(description: dict[str, Any], *, max_tokens: int = SIGNATURE_TOKENS) -> str:
    """The compact device description (BHMS-AGT-013): every action and property, within ``max_tokens``.

    Elision levels: 0 full; 1 drops outputs and freshness; 2 keeps argument names and types only; 3 lists names only.
    The last line says what was elided and that ``structuredContent`` carries the full description.
    """
    notes = {1: "elided: action outputs and freshness preconditions", 2: "elided: bounds, units, effects and "
             "lease/cancel details", 3: "elided: all details, only names are listed"}
    for level in range(4):
        text = _block(description, level)
        if level:
            text += f"\n({notes[level]}; the full description is in the structured result)"
        if estimate_tokens(text) <= max_tokens:
            return text
    return text


def _block(d: dict[str, Any], level: int) -> str:
    caps = ",".join(d.get("capabilities") or [])
    lines = [f"{d.get('deviceId')} {quote(d.get('name', ''))} [{caps}]"]
    actions, props = d.get("actions") or {}, d.get("properties") or {}
    if level >= 3:
        lines.append("actions: " + (", ".join(actions) or "none"))
        lines.append("properties: " + (", ".join(props) or "none"))
    else:
        lines += [_action_line(n, a, level) for n, a in actions.items()]
        lines += [_property_line(n, p, level) for n, p in props.items()]
    safety = d.get("safety") or {}
    stop = safety.get("stop", "unsupported")
    lines.append(f"stop: {stop}{' (' + safety.get('stopEvidence', 'none') + ')' if stop == 'supported' else ''}; "
                 f"on disconnect: {safety.get('onDisconnect', 'unknown')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------- summaries

def age_text(age_ms: Any) -> str:
    return "age unknown" if age_ms is None else f"{duration(age_ms)} old"


def summarize_observation(device_id: str, prop: str, obs: dict[str, Any]) -> str:
    """``pump-1.pressure = 101.3 kPa (measured, valid, 120 ms old)`` (BHMS-AGT-011)."""
    quality, evidence = obs.get("quality"), obs.get("evidence")
    meta = f"{evidence}, {quality}, {age_text(obs.get('ageMs'))}"
    subject = f"{device_id}.{prop}"
    if obs.get("value") is None or quality in ("invalid", "unknown"):
        return compose(f"{subject} has no usable value ({meta});", next_step="do not act on it; check the device or read again with fresh=true")
    value = with_unit(obs["value"], obs.get("unit"))
    if obs.get("uncertainty") is not None:
        value += f" ±{num(obs['uncertainty'])}"
    nxt = "read again with fresh=true before acting on it" if quality == "stale" else ""
    return compose(f"{subject} = {value} ({meta})", next_step=nxt)


def _result_text(result: Any, output: Any) -> str:
    props = (output or {}).get("properties") if isinstance(output, dict) else {}
    if isinstance(result, dict):
        return ", ".join(f"{k} {with_unit(v, (props or {}).get(k, {}).get('x-bhms-unit'))}" for k, v in result.items())
    return "" if result is None else with_unit(result, None)


def _error_text(error: dict[str, Any]) -> tuple[str, str]:
    """(code and message, hint). The message is the flexible part: it is cut, never the protected clauses."""
    message = clean(error.get("message", ""))
    if error.get("bhmsCode") in ("DEVICE_FAULT", "INTERNAL"):
        message = quote(message, 120)
    code = error.get("bhmsCode", "ERROR")
    return (f"{code}: {message}" if message else code), clean(error.get("hint", ""))


def summarize_operation(op: dict[str, Any], *, replayed: bool = False, description: dict[str, Any] | None = None,
                        keyed: bool = True, show_key: bool = False, wait_hint: bool = True) -> str:
    """``pump-1.dispense op-7f3a completed: dispensed 50 uL (effect verified, 2.1 s)``.

    Protected, never truncated: the subject's operation id, ``state``, ``replayed`` (AGT-011), ``effect``, the phrase
    "outcome unknown \u2014 check before retrying" for a failure that may have acted or an unknown operation (AGT-020) and
    ``(not retry-safe: no operation_key)`` (AGT-030). Only result values, the error message and the hint are cut.
    """
    state, effect, op_id = op.get("state"), op.get("effect", "unknown"), op.get("operationId")
    if op.get("kind") == "program":
        subject = f"program {str(op.get('programDigest', ''))[7:19]}"
    else:
        subject = f"{op.get('deviceId')}.{op.get('action')}"
    err = op.get("error") or {}
    took = op_duration_ms(op)
    clauses = f"effect {effect}" + (f", {duration(took)}" if took is not None and state in SETTLED else "")
    unknown = state == "unknown" or (state in ("failed", "rejected") and bool(err.get("mayHaveActed")))
    if unknown:
        clauses += f"; {OUTCOME_UNKNOWN}"
    if state == "canceled":
        clauses += f", cancel {(op.get('cancel') or {}).get('state', 'none')}"
    suffix = f"({clauses})" + ("" if keyed or not show_key else " (not retry-safe: no operation_key)")
    colon = "" if replayed else ":"
    state_text = f"replayed: {state}" if replayed else state
    fixed = len(f" {op_id} {state_text}{colon}") + len(suffix) + 1
    subject = cut(subject, 48 if fixed < 120 else 24)
    head = f"{subject} {op_id} {state_text}{colon}"
    body, nxt = "", ""
    if state == "completed":
        output = ((description or {}).get("actions", {}).get(op.get("action"), {}) or {}).get("output")
        body = _result_text(op.get("result"), output)
    elif state in ("failed", "rejected"):
        body, hint = _error_text(err) if err else (state, "")
        nxt = f"Next: {hint}" if hint else ""
    elif state == "unknown":
        hint = clean(err.get("hint", "")) or "reconcile with bhms_operation before acting again"
        nxt = f"Next: {hint}"
    elif state not in ("canceled",):  # accepted, dispatching, running
        prog = (op.get("progress") or {}).get("fraction")
        body = f"{int(prog * 100)}%" if isinstance(prog, (int, float)) else ""
        nxt = f'call bhms_operation(operation_id="{op_id}", wait_ms=30000)' if wait_hint else ""
        return compose(head, body, nxt, suffix, next_first=True)
    return compose(head, body, nxt, suffix)


def summarize_stop(stops: list[dict[str, Any]]) -> str:
    """Counts first, then every device that is *not* confirmed, then the confirmed ones as far as they fit.

    ``stop: 12 confirmed (3 operations canceled): ...`` or ``stop not confirmed on 1 of 13 devices (1 failed, 12
    confirmed) ...``. It never says "stopped" for a device whose stop is not ``confirmed`` (BHMS-AGT-011).
    """
    if not stops:
        return "stop: no device matched; nothing was confirmed"
    canceled = sum(len(s.get("canceledOperations") or []) for s in stops)
    counts: dict[str, int] = {}
    for s in stops:
        counts[s.get("outcome", "?")] = counts.get(s.get("outcome", "?"), 0) + 1
    words = {"unsupported": "unsupported (no physical stop)", "failed": "FAILED"}
    rest = [s for s in stops if s.get("outcome") != "confirmed"]
    ordered = rest + [s for s in stops if s.get("outcome") == "confirmed"]
    listing = ", ".join(f"{s.get('deviceId')} {words.get(s.get('outcome'), s.get('outcome'))}" for s in ordered)
    tally = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()) if k != "confirmed")
    suffix = f"({canceled} operation{'s' if canceled != 1 else ''} canceled)"
    if not rest:
        return compose(f"stop: {len(stops)} confirmed", listing, "", suffix)
    nxt = "Next: check them with bhms_read or stop again"
    if all(s.get("outcome") == "unsupported" for s in rest):
        nxt = "Next: stop them by other means"
    return compose(f"stop not confirmed on {len(rest)} of {len(stops)} devices ({tally}):", listing, nxt, suffix,
                   next_first=True)


def summarize_find(devices: list[dict[str, Any]], programs: list[dict[str, Any]] | None, next_cursor: str | None, *,
                   total: int | None = None, more: bool = False) -> str:
    """``total`` is given when a filter matched no device: the number of devices an unfiltered find lists (``more``: and
    further pages exist), so that "no match" is never read as "no devices"."""
    count = lambda n, what: f"{n} {what}{'s' if n != 1 else ''}"  # noqa: E731
    if total is not None:
        head = f"0 devices match; {'at least ' if more else ''}{count(total, 'device')} exist{'s' if total == 1 and not more else ''}"
        if programs:
            head += f", {count(len(programs), 'program')} match{'es' if len(programs) == 1 else ''}"
        return compose(head + ":", "", "call bhms_find with no arguments to list everything" if total else
                       "this principal can read no device")
    items = [f"{d['deviceId']} {quote(d['name'])} {d['status']}" for d in devices]
    head = count(len(devices), "device")
    if programs is not None:
        head += f", {count(len(programs), 'program')}"
    nxt = ""
    if next_cursor:
        nxt = f'more: call bhms_find with cursor="{next_cursor}"'
    elif devices:
        nxt = "Next: bhms_describe a device before acting"
    return compose(head + (":" if items else "; no device is visible to this principal"), "; ".join(items), nxt)


def summarize_describe(description: dict[str, Any]) -> str:
    n_a, n_p = len(description.get("actions") or {}), len(description.get("properties") or {})
    return compose(f"{description.get('deviceId')} {quote(description.get('name', ''))}: {n_a} action"
                   f"{'s' if n_a != 1 else ''}, {n_p} propert{'ies' if n_p != 1 else 'y'}; signature below")


def summarize_refusal(error: dict[str, Any], *, subject: str | None = None) -> str:
    """``Refused: <message>. Next: <hint>``; says "outcome unknown — check before retrying" when it may have acted."""
    message = cut(clean(error.get("message", "")).rstrip("."), 80 if error.get("mayHaveActed") else 100)
    hint = clean(error.get("hint", "")).rstrip(".")
    unknown = OUTCOME_UNKNOWN + "." if error.get("mayHaveActed") else ""
    head = f"Refused: {message}."
    if subject:
        head = f"Refused ({subject}): {message}."
    return compose(head, unknown, f"Next: {hint}." if hint else "")
