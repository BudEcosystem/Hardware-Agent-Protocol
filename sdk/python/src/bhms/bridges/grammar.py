"""The program grammar on demand, and program validation with the failing step path (spec 12, 08).

``bhms_run_program`` publishes ``program`` only as ``{"type": "object"}`` plus a pointer (the full ``Program`` schema is
about 1,300 tokens, most of a request's tool budget). A model learns the grammar here: :data:`PROGRAM_GRAMMAR` is served as
the MCP resource ``bhms://grammar/program`` and attached to every refusal of a malformed program, and :func:`check_program`
validates a program against the normative schema step by step, so the refusal names the step (``program.steps[1].arguments``).

Thread-safety: pure functions.
"""

from __future__ import annotations

from typing import Any

from bhms.protocol import schema
from bhms.protocol.errors import BhmsError

GRAMMAR_URI = "bhms://grammar/program"
GRAMMAR_TOPIC = "program-grammar"
GRAMMAR_CALL = 'bhms_describe {"topic":"program-grammar"}'
"""How any host fetches the grammar: a tool call. (MCP hosts may also read the resource :data:`GRAMMAR_URI`; function-tool
hosts have no resources, which is why the tool texts name the call.)"""
PROGRAM_GRAMMAR = """\
BHMS program (JSON object). Validated whole before step 1 runs; no loops except repeat, no code.
{"bhmsProgram":"2026-11-15","name":snake_case,"description":str,"input":{"type":"object","additionalProperties":false,"properties":{...},"required":[...]},"maxDurationMs":int,"steps":[Step,...],"output":{var:"${ref}"}?}
Every number in input needs "x-bhms-unit". maxDurationMs must cover the declared worst case. Values may be "${input_name}" or "${saved_var}" references.
Step kinds ("id" snake_case optional on all):
 {"kind":"invoke","deviceId":str,"action":str,"arguments":{...},"saveAs":var?}
 {"kind":"read","deviceId":str,"property":str,"saveAs":var,"maxAgeMs":int?,"fresh":bool?,"timeoutMs":1..60000?}
 {"kind":"waitUntil","deviceId":str,"property":str,"predicate":P,"timeoutMs":1..3600000,"pollMs":>=10?,"saveAs":var?}
 {"kind":"assert","predicate":P,"message":str}
 {"kind":"sleep","durationMs":1..3600000}
 {"kind":"repeat","times":1..1000|"${ref}","as":var?,"steps":[Step,...]}
Predicate P: {"op":"eq|ne|lt|le|gt|ge","left":v,"right":v} | {"op":"within","left":v,"right":v,"tolerance":v} | {"all":[P..]} | {"any":[P..]} | {"not":P}
Example: {"bhmsProgram":"2026-11-15","name":"go_home","description":"Move to 0.","input":{"type":"object","additionalProperties":false,"properties":{}},"maxDurationMs":10000,"steps":[{"kind":"invoke","deviceId":"axis-1","action":"move_to","arguments":{"position":0}}]}
Prefer registering a program once and running it by program_digest (see bhms_find)."""

_STEP_DEFS = {"invoke": "InvokeStep", "read": "ReadStep", "waitUntil": "WaitUntilStep", "assert": "AssertStep",
              "sleep": "SleepStep", "repeat": "RepeatStep"}


def _path(parts: list[Any]) -> str:
    out = "program"
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def _refuse(message: str, path: str, hint: str) -> BhmsError:
    return BhmsError("INVALID_ARGUMENT", f"{path}: {message}"[:500], field=path,
                     hint=f"{hint}. Grammar: call {GRAMMAR_CALL} (MCP resource {GRAMMAR_URI}) or read it below.\n{PROGRAM_GRAMMAR}"[:2000])


def _step(step: Any, where: list[Any]) -> None:
    if not isinstance(step, dict) or step.get("kind") not in _STEP_DEFS:
        kinds = ", ".join(_STEP_DEFS)
        raise _refuse("not a step with a known kind", _path(where), f"each step needs \"kind\" (one of {kinds})")
    if step["kind"] == "repeat" and isinstance(step.get("steps"), list):
        for index, child in enumerate(step["steps"]):
            _step(child, [*where, "steps", index])
        shallow = {**step, "steps": [{"kind": "sleep", "durationMs": 1}] * max(len(step["steps"]), 1)}
    else:
        shallow = step
    try:
        schema.validate(_STEP_DEFS[step["kind"]], shallow)
    except BhmsError as exc:
        member = (exc.field or "").lstrip("/").replace("/", ".")
        path = _path(where) + (f".{member}" if member else "")
        detail = exc.message.split(": ", 1)[-1]
        raise _refuse(f"{step['kind']} step: {detail}", path, f"fix {path}") from None


def check_program(program: Any) -> None:
    """Refuse a malformed inline program with the failing path (``program.steps[1].arguments``) and the grammar."""
    if not isinstance(program, dict):
        raise _refuse("the program must be a JSON object", "program", "send the program as an object")
    steps = program.get("steps")
    if isinstance(steps, list):
        for index, step in enumerate(steps):
            _step(step, ["steps", index])
    try:
        schema.validate("Program", program)
    except BhmsError as exc:
        member = (exc.field or "").lstrip("/").replace("/", ".")
        path = _path([p for p in member.split(".") if p]) if member else "program"
        raise _refuse(exc.message.split(": ", 1)[-1], path, f"fix {path}") from None
