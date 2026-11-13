"""Whole-run observers: they validate every message the runner saw, whichever check provoked it.

A server that is wrong only in a corner a check did not enter would escape a purely scripted suite; the observers close
that gap by applying invariants of the specification to *all* traffic: every result carries ``resultType`` (BHMS-LIF-012),
every error has the shape and number of §10 (BHMS-ERR-001/006/010), operations obey the state machine (BHMS-OPS-001/002/006/
008/009), observations carry the schema unit (BHMS-OBS-005), time fields are RFC 3339 UTC (BHMS-LIF-003) and so on.
With ``strict`` every message is also validated against the JSON Schema (``bhms.protocol.schema``).

Each observer finding is attributed to requirement IDs; an ID that was observed and never violated passes.

Thread-safety: pure functions over a finished recording.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from bhms.conformance.core import Observation
from bhms.conformance.wire import Recorder, Seen
from bhms.protocol import schema as bhms_schema
from bhms.protocol.canonical import canonical

TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?Z$")
TIME_KEYS = {"time", "acquiredAt", "receivedAt", "createdAt", "updatedAt", "deadlineAt", "expiresAt", "requestedAt", "at"}
NOT_BHMS_RANGE = (-32700, -32600, -32601, -32603)
RETRY_ORDER = {"backoff": 0, "after-reconcile": 1, "never": 2}
SUCCESSORS = {
    "accepted": {"dispatching", "rejected", "canceled"},
    "dispatching": {"running", "completed", "failed", "canceled", "unknown"},
    "running": {"completed", "failed", "canceled", "unknown"},
    "unknown": {"running", "completed", "failed", "canceled"},
}
TERMINAL = {"completed", "failed", "canceled", "rejected"}
OPERATION_METHODS = {"actions/invoke", "operations/get", "operations/wait", "operations/cancel", "programs/run"}


def _walk(value: Any, path: str = "") -> Iterator[tuple[str, str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield path, key, item
            yield from _walk(item, f"{path}/{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}/{index}")


def _inbound(recorder: Recorder) -> Iterator[Seen]:
    for item in recorder.seen:
        if item.direction == "in":
            yield item


def _operations(seen: Seen) -> Iterator[dict[str, Any]]:
    """Every operation object inside a message."""
    message = seen.message
    if not isinstance(message, dict):
        return
    if "result" in message and isinstance(message["result"], dict):
        result = message["result"]
        if isinstance(result.get("operation"), dict):
            yield result["operation"]
        for op in result.get("operations") or []:
            if isinstance(op, dict):
                yield op
    params = message.get("params")
    if message.get("method") == "notifications/operation" and isinstance(params, dict) and isinstance(params.get("operation"), dict):
        yield params["operation"]


def observe(recorder: Recorder, descriptions: dict[str, dict[str, Any]], *, strict: bool = False,
            stdio: bool = False) -> Observation:
    """Apply every observer to the recording."""
    obs = Observation()
    steps = (
        (lambda: _framing(recorder, obs, stdio), ("BHMS-TRN-001", "BHMS-LIF-052")),
        (lambda: _responses(recorder, obs, strict), ("BHMS-LIF-012",)),
        (lambda: _times(recorder, obs), ("BHMS-LIF-003",)),
        (lambda: _errors(recorder, obs), ("BHMS-ERR-001", "BHMS-ERR-010")),
        (lambda: _summaries(recorder, obs), ("BHMS-DEV-011",)),
        (lambda: _observations(recorder, obs, descriptions), ("BHMS-OBS-005", "BHMS-OBS-001")),
        (lambda: _operation_invariants(recorder, obs, descriptions), ("BHMS-OPS-001", "BHMS-OPS-008", "BHMS-OPS-009")),
        (lambda: _stops(recorder, obs), ("BHMS-AUTH-022",)),
        (lambda: _notifications(recorder, obs), ("BHMS-LIF-041", "BHMS-EVT-030")),
    )
    for step, ids in steps:
        try:
            step()
        except Exception as exc:  # a response of an unforeseen shape is a finding about the target, never a crash of the runner
            for rid in ids:
                obs.bad(rid, f"a non-conforming message made the observer fail ({type(exc).__name__}: {exc})")
    return obs


def _framing(recorder: Recorder, obs: Observation, stdio: bool) -> None:
    obs.ok("BHMS-TRN-001")
    obs.ok("BHMS-LIF-052")
    for seen in _inbound(recorder):
        if seen.frame_error:
            obs.bad("BHMS-TRN-010" if stdio else "BHMS-LIF-001", f"{seen.wire}: {seen.frame_error}")
        msg = seen.message
        if isinstance(msg, dict) and "method" in msg:
            if "id" in msg:
                obs.bad("BHMS-TRN-001", f"the server sent a request {msg.get('method')!r}")
            if msg.get("method") == "notifications/cancelled":
                obs.bad("BHMS-LIF-052", "the server sent notifications/cancelled")
    if stdio:
        obs.ok("BHMS-TRN-010")


def _responses(recorder: Recorder, obs: Observation, strict: bool) -> None:
    obs.ok("BHMS-LIF-012")
    methods = bhms_schema.load_schema().get("x-bhms-methods", {})
    for seen in _inbound(recorder):
        msg = seen.message
        if not isinstance(msg, dict) or "method" in msg:
            continue
        if "result" in msg:
            result = msg["result"]
            method = (seen.request or {}).get("method")
            if not isinstance(result, dict) or result.get("resultType") not in ("complete", "incomplete", "partial") and not (
                    isinstance(result, dict) and "resultType" in result):
                if method in methods or method == "subscriptions/listen":
                    obs.bad("BHMS-LIF-012", f"{method}: the result carries no resultType")
            if strict and method in methods:
                _validate(obs, methods[method]["response"].rsplit("/", 1)[-1], msg, "BHMS-LIF-012")
        elif "error" in msg and strict:
            _validate(obs, "JSONRPCErrorResponse", msg, "BHMS-ERR-001")


def _validate(obs: Observation, definition: str, message: Any, rid: str) -> None:
    try:
        bhms_schema.validate(definition, message)
    except Exception as exc:  # BhmsError from the validator, or KeyError for an unknown definition
        obs.bad(rid, f"schema {definition}: {str(exc)[:240]}")
    else:
        obs.ok(rid)


def _times(recorder: Recorder, obs: Observation) -> None:
    obs.ok("BHMS-LIF-003")
    for seen in _inbound(recorder):
        msg = seen.message
        if not isinstance(msg, dict):
            continue
        body = msg.get("result") if "result" in msg else msg.get("params")
        for path, key, value in _walk(body):
            if key in TIME_KEYS and isinstance(value, str) and not TIME.match(value):
                obs.bad("BHMS-LIF-003", f"{path}/{key} = {value!r} is not an RFC 3339 UTC time ending in Z")


def _errors(recorder: Recorder, obs: Observation) -> None:
    table = bhms_schema.load_schema()["x-bhms-errors"]
    numbers = {name: spec["code"] for name, spec in table.items()}
    for rid in ("BHMS-ERR-001", "BHMS-ERR-003", "BHMS-ERR-005", "BHMS-ERR-006", "BHMS-ERR-010", "BHMS-ERR-012"):
        obs.ok(rid)
    for seen in _inbound(recorder):
        msg = seen.message
        if not isinstance(msg, dict) or not isinstance(msg.get("error"), dict):
            continue
        err = msg["error"]
        code, data = err.get("code"), err.get("data")
        if code in NOT_BHMS_RANGE:
            if isinstance(data, dict) and "bhmsCode" in data:
                obs.bad("BHMS-ERR-006", f"JSON-RPC error {code} carries data.bhmsCode")
            continue
        bhms = data.get("bhmsCode") if isinstance(data, dict) else None
        if bhms is None:
            if code == -32602 or (isinstance(code, int) and -32019 <= code <= -32001):
                obs.bad("BHMS-ERR-001", f"error {code} has no data.bhmsCode")
            continue
        if bhms not in numbers:
            obs.bad("BHMS-ERR-010", f"unknown bhmsCode {bhms!r}")
            continue
        if numbers[bhms] != code:
            obs.bad("BHMS-ERR-010", f"{bhms} must be JSON-RPC code {numbers[bhms]}, got {code}")
        missing = [k for k in ("mayHaveActed", "retry", "hint") if k not in data]
        if missing:
            obs.bad("BHMS-ERR-001", f"{bhms} error lacks data.{', data.'.join(missing)}")
        if not isinstance(data.get("hint"), str) or not data.get("hint", "").strip():
            obs.bad("BHMS-ERR-003", f"{bhms} error has an empty hint ({err.get('message')!r})")
        if not isinstance(err.get("message"), str) or not err["message"].strip():
            obs.bad("BHMS-ERR-003", f"{bhms} error has an empty message")
        retry, default = data.get("retry"), table[bhms]["retry"]
        if retry != default and not (retry == "same-key" and bhms in ("BUSY", "DEVICE_UNAVAILABLE")) and (
                RETRY_ORDER.get(retry, -1) < RETRY_ORDER[default]):
            obs.bad("BHMS-ERR-005", f"{bhms}: retry {retry!r} is less conservative than the default {default!r}")
        if bhms in ("DEVICE_FAULT", "UNVERIFIED"):
            obs.bad("BHMS-ERR-012", f"{bhms} appeared as a JSON-RPC error; it may only appear inside an operation")


def _summaries(recorder: Recorder, obs: Observation) -> None:
    obs.ok("BHMS-DEV-011")
    for seen in _inbound(recorder):
        msg = seen.message
        if isinstance(msg, dict) and (seen.request or {}).get("method") == "devices/list" and isinstance(msg.get("result"), dict):
            for summary in msg["result"].get("devices", []):
                size = len(canonical(summary))
                if size > 4096:
                    obs.bad("BHMS-DEV-011", f"{summary.get('deviceId')}: DeviceSummary is {size} bytes (MUST be at most 4096)")


def _observations(recorder: Recorder, obs: Observation, descriptions: dict[str, dict[str, Any]]) -> None:
    obs.ok("BHMS-OBS-005")
    obs.ok("BHMS-OBS-001")

    def check(device: str | None, prop: str | None, observation: Any) -> None:
        if not isinstance(observation, dict):
            return
        value, unit = observation.get("value"), observation.get("unit")
        if observation.get("quality") in ("invalid", "unknown") and value is not None:
            obs.bad("BHMS-OBS-001", f"{device}.{prop}: quality {observation['quality']} with value {value!r} (MUST be null)")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            declared = ((descriptions.get(device or "", {}).get("properties", {}).get(prop or "", {})).get("schema") or {}).get("x-bhms-unit")
            if unit is None:
                obs.bad("BHMS-OBS-005", f"{device}.{prop}: numeric observation without unit")
            elif declared is not None and unit != declared:
                obs.bad("BHMS-OBS-005", f"{device}.{prop}: unit {unit!r} differs from the schema unit {declared!r}")

    for seen in _inbound(recorder):
        msg = seen.message
        if not isinstance(msg, dict):
            continue
        if isinstance(msg.get("result"), dict) and isinstance(msg["result"].get("observation"), dict):
            params = (seen.request or {}).get("params", {})
            check(params.get("deviceId"), params.get("property"), msg["result"]["observation"])
        elif msg.get("method") == "notifications/observation" and isinstance(msg.get("params"), dict):
            p = msg["params"]
            check(p.get("deviceId"), p.get("property"), p.get("observation"))


def _operation_invariants(recorder: Recorder, obs: Observation, descriptions: dict[str, dict[str, Any]]) -> None:
    for rid in ("BHMS-OPS-001", "BHMS-OPS-002", "BHMS-OPS-006", "BHMS-OPS-008", "BHMS-OPS-009", "BHMS-OPS-004"):
        obs.ok(rid)
    snapshots: dict[str, list[dict[str, Any]]] = {}
    for seen in _inbound(recorder):
        for op in _operations(seen):
            ident = op.get("operationId", "?")
            state = op.get("state")
            if (state == "completed") != ("result" in op):
                obs.bad("BHMS-OPS-008", f"{ident}: state {state} {'has' if 'result' in op else 'lacks'} a result")
            if state in ("failed", "rejected", "unknown") and not isinstance(op.get("error"), dict):
                obs.bad("BHMS-OPS-009", f"{ident}: state {state} carries no error")
            if state == "rejected" and op.get("effect") != "none":
                obs.bad("BHMS-OPS-006", f"{ident}: rejected with effect {op.get('effect')!r}")
            if op.get("effect") == "verified" and (op.get("evidence") or {}).get("kind") != "measured":
                obs.bad("BHMS-OPS-006", f"{ident}: effect verified without measured evidence")
            if state == "unknown":
                err = op.get("error") or {}
                if (err.get("bhmsCode"), err.get("mayHaveActed"), err.get("retry")) != ("DEADLINE_EXCEEDED", True, "after-reconcile"):
                    obs.bad("BHMS-OPS-004", f"{ident}: unknown operation error is {err.get('bhmsCode')}/{err.get('mayHaveActed')}/"
                                            f"{err.get('retry')}, expected DEADLINE_EXCEEDED/true/after-reconcile")
            if state == "completed" and op.get("kind") == "action":
                _check_output(obs, op, descriptions)
            snapshots.setdefault(ident, []).append(op)
            if isinstance(op.get("history"), list):
                _history(obs, op)
    # Snapshots reach the client by two routes (responses and notifications), so arrival order proves nothing: order them by
    # updatedAt and compare only snapshots whose timestamps differ.
    for ident, ops in snapshots.items():
        ordered = sorted(ops, key=lambda o: str(o.get("updatedAt", "")))
        for before, after in zip(ordered, ordered[1:]):
            if before.get("updatedAt") == after.get("updatedAt"):
                continue
            b, a = before.get("state"), after.get("state")
            if b in TERMINAL:
                for member in ("state", "result", "effect"):
                    if before.get(member) != after.get(member):
                        obs.bad("BHMS-OPS-002", f"{ident}: terminal {member} changed from {before.get(member)!r} to {after.get(member)!r}")
            elif a != b and a not in SUCCESSORS.get(b, set()) and not (b == "accepted" and a in TERMINAL | {"running", "unknown"}):
                obs.bad("BHMS-OPS-001", f"{ident}: state went {b} -> {a}")


def _check_output(obs: Observation, op: dict[str, Any], descriptions: dict[str, dict[str, Any]]) -> None:
    action = ((descriptions.get(op.get("deviceId") or "", {}).get("actions") or {}).get(op.get("action") or ""))
    if not action:
        return
    output = action.get("output")
    if output is None:
        return
    errors = list(bhms_schema.compile_schema(output).iter_errors(op.get("result")))
    if errors:
        obs.bad("BHMS-OPS-008", f"{op.get('operationId')}: result violates the action's output schema: {errors[0].message[:160]}")


def _history(obs: Observation, op: dict[str, Any]) -> None:
    ident, history = op.get("operationId"), op["history"]
    seqs = [h.get("seq") for h in history]
    if seqs != list(range(1, len(history) + 1)):
        obs.bad("BHMS-OPS-001", f"{ident}: history seq is {seqs}, expected 1..n")
    state = None
    for entry in history:
        if entry.get("kind") == "reconciliation":
            obs.ok("BHMS-OPS-005")
            if not str(entry.get("detail", "")).strip():
                obs.bad("BHMS-OPS-005", f"{ident}: a reconciliation history entry names no evidence")
            if state != "unknown":
                obs.bad("BHMS-OPS-005", f"{ident}: a reconciliation entry while the state was {state}, not unknown")
        if entry.get("kind") in ("state", "reconciliation") and entry.get("state"):
            new = entry["state"]
            if state is None and new != "accepted":
                obs.bad("BHMS-OPS-001", f"{ident}: history starts at {new}, not accepted")
            elif state is not None and new != state and new not in SUCCESSORS.get(state, set()):
                obs.bad("BHMS-OPS-001", f"{ident}: history transition {state} -> {new} is not in the §6.3 table")
            elif state in TERMINAL:
                obs.bad("BHMS-OPS-002", f"{ident}: history changes state after terminal {state}")
            state = new
    if state is not None and op.get("state") != state:
        obs.bad("BHMS-OPS-001", f"{ident}: state {op.get('state')} has no matching history entry (last is {state})")
    if op.get("state") == "canceled" and [h.get("state") for h in history if h.get("kind") == "state"] == ["accepted", "canceled"] \
            and op.get("effect") != "none":
        obs.bad("BHMS-OPS-006", f"{ident}: canceled before dispatch with effect {op.get('effect')!r}")


def _stops(recorder: Recorder, obs: Observation) -> None:
    obs.ok("BHMS-AUTH-022")
    for seen in _inbound(recorder):
        msg = seen.message
        if isinstance(msg, dict) and (seen.request or {}).get("method") == "stop" and isinstance(msg.get("result"), dict):
            stops = msg["result"].get("stops")
            if not isinstance(stops, list):
                obs.bad("BHMS-AUTH-022", "a stop result without a stops array")
                continue
            for stop in stops:
                if stop.get("outcome") == "confirmed" and stop.get("evidence") not in ("reported", "measured"):
                    obs.bad("BHMS-AUTH-022", f"{stop.get('deviceId')}: outcome confirmed with evidence {stop.get('evidence')!r}")


def _notifications(recorder: Recorder, obs: Observation) -> None:
    obs.ok("BHMS-EVT-030")
    obs.ok("BHMS-LIF-041")
    for seen in _inbound(recorder):
        msg = seen.message
        if not isinstance(msg, dict) or "method" not in msg:
            continue
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        if "bhms/subscriptionId" not in meta:
            obs.bad("BHMS-LIF-041", f"notification {msg.get('method')} is not tagged with _meta[\"bhms/subscriptionId\"]")
        if msg.get("method") == "notifications/observation":
            size = len(json.dumps(params.get("observation"), separators=(",", ":")).encode())
            if size > 65536:
                obs.bad("BHMS-EVT-030", f"observation notification of {size} bytes exceeds 64 KiB")


def observed_ids() -> tuple[str, ...]:
    """The requirement IDs :func:`observe` reports on (an ID with no finding was observed and is fine)."""
    return ("BHMS-TRN-001", "BHMS-LIF-052", "BHMS-TRN-010", "BHMS-LIF-012", "BHMS-LIF-003", "BHMS-ERR-001", "BHMS-ERR-003",
            "BHMS-ERR-005", "BHMS-ERR-006", "BHMS-ERR-010", "BHMS-ERR-012", "BHMS-DEV-011", "BHMS-OBS-005", "BHMS-OBS-001",
            "BHMS-OPS-001", "BHMS-OPS-002", "BHMS-OPS-004", "BHMS-OPS-005", "BHMS-OPS-006", "BHMS-OPS-008", "BHMS-OPS-009", "BHMS-AUTH-022",
            "BHMS-EVT-030", "BHMS-LIF-041")
