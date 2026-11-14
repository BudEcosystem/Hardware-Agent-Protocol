"""Bounded programs: validation before the first step and execution over the operation machinery (spec/bhms/08).

Validation (:class:`_Validator`, BHMS-PRG-001..007) checks the whole program before anything runs and refuses with a
JSON-RPC error whose ``field`` is a path into the program (``program.steps[1].steps[0].arguments.distance``): size and
step/depth/repeat/variable/executed-step limits (§8.1), devices, actions and properties, references (undefined, defined
later, defined twice or shadowing an input), predicate depth ≤ 4, ``repeat.times`` references (a required integer
input with ``minimum ≥ 1`` and ``maximum ≤ maxRepeat``), literal arguments against the action ``input`` and the caller's
envelope, input references whose bounds must lie inside the action envelope, worst-case duration against the declared
``maxDurationMs``, and authority (``programs:run``, every ``invoke`` scope, fresh ``transaction`` reads) plus a lease
covering every lease-requiring step (BHMS-PRG-006).

Execution (:class:`ProgramRunner`, BHMS-PRG-010..016): one task per run executes steps strictly in order. Each
``invoke`` step creates a child operation through :meth:`bhms.server.executor.Executor.admit` (so every admission
check applies again, including arguments built from saved results) with ``keyOrigin: derived`` and the key of
:func:`~bhms.runtime.operations.derived_key`. A failing step stops the program (``failed`` with the step's error,
``mayHaveActed`` true if an effectful child was dispatched; ``unknown`` if the child is unknown); completed effects are
never rolled back. ``maxDurationMs`` (and ``deadlineMs``) is enforced at run time; ``operations/cancel`` and ``stop``
end the run after cancelling the running child. Programs are never resumed after a restart (BHMS-PRG-017, handled by
:meth:`~bhms.runtime.operations.Journal.recover`).

The registry (``programs/register|get|list``) stores validated programs by digest in the
:class:`~bhms.runtime.store.Store`; registration grants no authority (BHMS-PRG-021).

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from bhms.protocol import types
from bhms.protocol.canonical import canonical, digest
from bhms.protocol.errors import BhmsError
from bhms.runtime.operations import (OperationRecord, derived_key, intent_digest, key_conflict_error, most_severe,
                                     now_ns, program_outcome, server_key, unknown_error)
from bhms.runtime.store import StoreError
from bhms.server.validation import ArgumentValidator, check_units, effective_bounds

if TYPE_CHECKING:
    from bhms.runtime.authority import Principal
    from bhms.runtime.leases import Lease
    from bhms.server.server import DeviceServer

log = logging.getLogger("bhms.programs")

REFERENCE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)((?:\.[A-Za-z0-9_]+|\[[0-9]+\])*)\}$")
_SELECTOR = re.compile(r"\.([A-Za-z0-9_]+)|\[([0-9]+)\]")
_MAX_PREDICATE_DEPTH = 4


# --------------------------------------------------------------------------- values and predicates


def reference(value: Any) -> tuple[str, str] | None:
    """``(variable, selectors)`` when ``value`` is exactly a ``${path}`` reference (§8.2)."""
    if isinstance(value, str):
        match = REFERENCE.match(value)
        if match:
            return match.group(1), match.group(2)
    return None


def _references(value: Any) -> list[str]:
    found = reference(value)
    if found is not None:
        return [found[0]]
    if isinstance(value, dict):
        return [name for item in value.values() for name in _references(item)]
    if isinstance(value, list):
        return [name for item in value for name in _references(item)]
    return []


def resolve(value: Any, variables: dict[str, Any]) -> Any:
    """Replace every reference by the referenced value (type preserved); ``"$${x}"`` is the literal ``"${x}"``."""
    found = reference(value)
    if found is not None:
        name, selectors = found
        current = variables[name]
        for member, index in _SELECTOR.findall(selectors):
            current = current[int(index)] if index else current[member]
        return current
    if isinstance(value, str) and value.startswith("$${"):
        return value[1:]
    if isinstance(value, dict):
        return {k: resolve(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, variables) for v in value]
    return value


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def evaluate(predicate: dict[str, Any], variables: dict[str, Any]) -> bool:
    """Evaluate a predicate (§8.2); ordering and ``within`` on non-numbers are false."""
    if "all" in predicate:
        return all(evaluate(p, variables) for p in predicate["all"])
    if "any" in predicate:
        return any(evaluate(p, variables) for p in predicate["any"])
    if "not" in predicate:
        return not evaluate(predicate["not"], variables)
    left, right = resolve(predicate["left"], variables), resolve(predicate["right"], variables)
    op = predicate["op"]
    if op in ("eq", "ne"):
        same = canonical(left) == canonical(right)
        return same if op == "eq" else not same
    if not (_number(left) and _number(right)):
        return False
    if op == "within":
        tolerance = resolve(predicate["tolerance"], variables)
        return _number(tolerance) and abs(left - right) <= tolerance
    return {"lt": left < right, "le": left <= right, "gt": left > right, "ge": left >= right}[op]


# --------------------------------------------------------------------------- validation


@dataclass
class Step:
    """A validated step: its raw object, flattened index, resolved device/spec and body (repeat)."""

    raw: dict[str, Any]
    index: int
    path: str
    device: Any = None
    spec: Any = None
    body: list[Step] = field(default_factory=list)
    times_input: str | None = None


@dataclass
class Plan:
    """A validated program ready to run."""

    program: dict[str, Any]
    digest: str
    steps: list[Step]
    info: dict[str, Any]
    lease_resources: tuple[str, ...]
    input_validator: ArgumentValidator


class _Validator:
    def __init__(self, server: DeviceServer, principal: Principal, program: dict[str, Any]) -> None:
        self.srv, self.principal, self.program = server, principal, program
        self.limits = server.program_limits
        self.count = 0
        self.executed = 0
        self.ids: set[str] = set()
        self.names: set[str] = set()
        self.effects: list[str] = []
        self.devices: set[str] = set()
        self.resources: set[str] = set()
        self.lease_resources: set[str] = set()
        self.inputs: dict[str, Any] = {}
        self.required: set[str] = set()

    def fail(self, code: str, field: str, message: str, hint: str, bound: Any = None) -> BhmsError:
        return BhmsError(code, message, field=field, bound=bound, hint=hint)

    def run(self) -> Plan:
        program, limits = self.program, self.limits
        size = len(canonical(program))
        if size > limits["maxProgramBytes"]:
            raise self.fail("OUT_OF_RANGE", "program", f"the program is {size} bytes of canonical JSON",
                            f"keep programs under {limits['maxProgramBytes']} bytes", {"maximum": limits["maxProgramBytes"]})
        try:
            types.Program.model_validate(program)
        except Exception as exc:  # noqa: BLE001 - pydantic ValidationError mapped to a program path
            from bhms.protocol.schema import from_pydantic_error

            error = from_pydantic_error(exc, what="program")
            raise self.fail("INVALID_ARGUMENT", f"program.{error.field}" if error.field else "program",
                            error.message, error.hint) from None
        if program["bhmsProgram"] not in self.srv.rpc.supported_versions:  # type: ignore[union-attr]
            raise self.fail("INVALID_ARGUMENT", "program.bhmsProgram", f"programs for {program['bhmsProgram']} are not "
                            "served", "write the program for a supported protocol version",
                            list(self.srv.rpc.supported_versions))  # type: ignore[union-attr]
        try:
            check_units(program["input"], "program.input")
        except ValueError as exc:
            raise self.fail("INVALID_ARGUMENT", "program.input", str(exc), "give every numeric input x-bhms-unit") \
                from None
        if program["maxDurationMs"] > limits["maxDurationMs"]:
            raise self.fail("OUT_OF_RANGE", "program.maxDurationMs", f"maxDurationMs {program['maxDurationMs']} is "
                            f"above this server's limit {limits['maxDurationMs']}",
                            f"declare at most {limits['maxDurationMs']} ms", {"maximum": limits["maxDurationMs"]})
        self.inputs = program["input"].get("properties", {})
        self.required = set(program["input"].get("required", []))
        self.names = set(self.inputs)
        defined = set(self.inputs)
        steps, worst = self._steps(program["steps"], "program.steps", 0, 1, defined, set())
        if self.count > limits["maxSteps"]:
            raise self.fail("OUT_OF_RANGE", "program.steps", f"the program has {self.count} steps",
                            f"use at most {limits['maxSteps']} step objects", {"maximum": limits["maxSteps"]})
        if self.executed > limits["maxExecutedSteps"]:
            raise self.fail("OUT_OF_RANGE", "program.steps", f"the program can execute {self.executed} steps",
                            f"keep worst-case executions at or below {limits['maxExecutedSteps']}",
                            {"maximum": limits["maxExecutedSteps"]})
        if len(self.names) > limits["maxVariables"]:
            raise self.fail("OUT_OF_RANGE", "program", f"the program uses {len(self.names)} variables",
                            f"use at most {limits['maxVariables']} inputs, saveAs names and repeat indices",
                            {"maximum": limits["maxVariables"]})
        for name, value in (program.get("output") or {}).items():
            self._refs(value, f"program.output.{name}", defined, set())
        if worst > program["maxDurationMs"]:
            raise self.fail("OUT_OF_RANGE", "program.maxDurationMs", f"the worst-case duration is {worst} ms, above "
                            f"the declared {program['maxDurationMs']} ms",
                            f"declare maxDurationMs of at least {worst} or shorten the program", worst)
        program_digest = digest(program)
        info = {"digest": program_digest, "name": program["name"], "description": program["description"],
                "input": program["input"], "effect": most_severe(self.effects), "worstCaseDurationMs": worst,
                "maxDurationMs": program["maxDurationMs"], "stepCount": self.count,
                "maxExecutedSteps": self.executed, "devices": sorted(self.devices),
                "resources": sorted(self.resources), "requiresLease": bool(self.lease_resources)}
        return Plan(program, program_digest, steps, info, tuple(sorted(self.lease_resources)),
                    ArgumentValidator(program["input"], field_prefix="arguments"))

    def _define(self, name: str, path: str) -> None:
        if name in self.names:
            raise self.fail("INVALID_ARGUMENT", path, f"variable {name!r} is defined twice",
                            "give every input, saveAs and repeat index a distinct name (BHMS-PRG-002)")
        self.names.add(name)

    def _refs(self, value: Any, path: str, defined: set[str], local: set[str]) -> None:
        for name in _references(value):
            if name not in defined and name not in local:
                raise self.fail("INVALID_ARGUMENT", path, f"${{{name}}} is undefined here or defined later",
                                "reference only inputs, earlier saveAs names and enclosing repeat indices")

    def _predicate(self, predicate: dict[str, Any], path: str, defined: set[str], local: set[str],
                   depth: int = 1) -> None:
        if depth > _MAX_PREDICATE_DEPTH:
            raise self.fail("INVALID_ARGUMENT", path, "predicates nest deeper than 4",
                            "flatten the predicate (all/any/not at most 4 levels, BHMS-PRG-002)")
        for key in ("all", "any"):
            if key in predicate:
                for index, child in enumerate(predicate[key]):
                    self._predicate(child, f"{path}.{key}[{index}]", defined, local, depth + 1)
                return
        if "not" in predicate:
            self._predicate(predicate["not"], f"{path}.not", defined, local, depth + 1)
            return
        for member in ("left", "right", "tolerance"):
            if member in predicate:
                self._refs(predicate[member], f"{path}.{member}", defined, local)

    def _steps(self, raw_steps: list[dict[str, Any]], base: str, depth: int, multiplier: int, defined: set[str],
               local: set[str]) -> tuple[list[Step], int]:
        out, worst = [], 0
        for position, raw in enumerate(raw_steps):
            path = f"{base}[{position}]"
            step = Step(raw, self.count, path)
            self.count += 1
            if "id" in raw:
                if raw["id"] in self.ids:
                    raise self.fail("INVALID_ARGUMENT", f"{path}.id", f"step id {raw['id']!r} is used twice",
                                    "step ids must be unique")
                self.ids.add(raw["id"])
            worst += self._step(step, depth, multiplier, defined, local)
            out.append(step)
        return out, worst

    def _step(self, step: Step, depth: int, multiplier: int, defined: set[str], local: set[str]) -> int:
        raw, path, kind = step.raw, step.path, step.raw["kind"]
        if kind == "repeat":
            return self._repeat(step, depth, multiplier, defined, local)
        self.executed += multiplier
        if kind == "invoke":
            dev, spec = self.srv.executor.resolve(self.principal, raw["deviceId"], raw["action"],
                                                  field_prefix=f"{path}.")
            step.device, step.spec = dev, spec
            self._arguments(dev, spec, raw["arguments"], f"{path}.arguments", defined, local)
            self.effects.append(spec.effect)
            self.devices.add(dev.device_id)
            self.resources.update(spec.resources)
            if spec.requires_lease:
                self.lease_resources.update(spec.resources)
            if raw.get("saveAs"):
                self._define(raw["saveAs"], f"{path}.saveAs")
                defined.add(raw["saveAs"])
            return spec.max_duration_ms
        if kind in ("read", "waitUntil"):
            dev = self.srv.visible_device(self.principal, raw["deviceId"], field=f"{path}.deviceId")
            spec = self.srv.observations.spec(dev, raw["property"], field=f"{path}.property")
            step.device, step.spec = dev, spec
            self.devices.add(dev.device_id)
            acquires = kind == "waitUntil" or raw.get("fresh") or raw.get("maxAgeMs") is not None
            if spec.read_effect == "transaction" and acquires:
                if not self.principal.can_invoke(dev.device_id, spec.name, dev.capabilities):
                    raise self.fail("UNAUTHORIZED", f"{path}.property", f"a fresh read of {dev.device_id}."
                                    f"{spec.name} starts a device transaction",
                                    f"missing scope invoke:{dev.device_id}/{spec.name} (BHMS-PRG-006)")
                if spec.requires_lease:
                    self.lease_resources.update(spec.resources or dev.resources)
            if kind == "waitUntil":
                self._predicate(raw["predicate"], f"{path}.predicate", defined, local | {"observed"})
            if raw.get("saveAs"):
                self._define(raw["saveAs"], f"{path}.saveAs")
                defined.add(raw["saveAs"])
            return raw["timeoutMs"] if kind == "waitUntil" else raw.get("timeoutMs", 1000)
        if kind == "assert":
            self._predicate(raw["predicate"], f"{path}.predicate", defined, local)
            return 0
        return raw["durationMs"]  # sleep

    def _repeat(self, step: Step, depth: int, multiplier: int, defined: set[str], local: set[str]) -> int:
        raw, path = step.raw, step.path
        if depth + 1 > self.limits["maxDepth"]:
            raise self.fail("OUT_OF_RANGE", path, f"repeat nesting exceeds {self.limits['maxDepth']}",
                            "flatten nested repeats", {"maxDepth": self.limits["maxDepth"]})
        times = raw["times"]
        max_repeat = self.limits["maxRepeat"]
        if isinstance(times, str):
            found = reference(times)
            name = found[0] if found and not found[1] else None
            spec = self.inputs.get(name) if name else None
            if spec is None or name not in self.required or spec.get("type") != "integer" \
                    or spec.get("minimum", 0) < 1 or spec.get("maximum", max_repeat + 1) > max_repeat:
                raise self.fail("INVALID_ARGUMENT" if spec is None or spec.get("type") != "integer" else "OUT_OF_RANGE",
                                f"{path}.times", f"repeat.times {times} must name a required integer input with "
                                f"minimum >= 1 and maximum <= {max_repeat}",
                                f"declare the input as {{\"type\": \"integer\", \"minimum\": 1, \"maximum\": "
                                f"{max_repeat}, \"x-bhms-unit\": \"1\"}} and list it in required (BHMS-PRG-003)",
                                {"minimum": 1, "maximum": max_repeat})
            step.times_input = name
            count = spec["maximum"]
        else:
            if times > max_repeat:
                raise self.fail("OUT_OF_RANGE", f"{path}.times", f"repeat.times {times} is above {max_repeat}",
                                f"repeat at most {max_repeat} times", {"maximum": max_repeat})
            count = times
        inner_local = set(local)
        if raw.get("as"):
            self._define(raw["as"], f"{path}.as")
            inner_local.add(raw["as"])
        step.body, body_worst = self._steps(raw["steps"], f"{path}.steps", depth + 1, multiplier * count, defined,
                                            inner_local)
        return count * body_worst

    def _arguments(self, dev: Any, spec: Any, args: dict[str, Any], path: str, defined: set[str],
                   local: set[str]) -> None:
        members = spec.input.get("properties", {})
        bounds = self.principal.bounds_for(dev.device_id, spec.name) or {}
        for name in args:
            if name not in members:
                raise self.fail("INVALID_ARGUMENT", f"{path}.{name}", f"{name} is not an argument of {spec.name}",
                                f"{spec.name} accepts only: {', '.join(sorted(members)) or 'no members'}")
        for name in spec.input.get("required", []):
            if name not in args:
                raise self.fail("INVALID_ARGUMENT", f"{path}.{name}", f"{path}.{name} is required",
                                f"add {name} to the step arguments")
        for name, value in args.items():
            self._refs(value, f"{path}.{name}", defined, local)
            found = reference(value)
            if found is not None:
                if found[0] in self.inputs and not found[1]:
                    self._input_envelope(members[name], bounds.get(name, {}), self.inputs[found[0]], f"{path}.{name}")
                continue  # saved results and nested references are checked when the step is admitted
            if _references(value):
                continue
            single = {"type": "object", "additionalProperties": False, "properties": {name: members[name]}}
            ArgumentValidator(single, field_prefix=path).admit({name: value},
                                                               bounds={name: bounds[name]} if name in bounds else None)

    def _input_envelope(self, node: dict[str, Any], policy: dict[str, Any], source: dict[str, Any],
                        path: str) -> None:
        """An argument that is exactly an input reference: the input's bounds must lie inside the envelope."""
        unit = node.get("x-bhms-unit")
        if unit is not None and source.get("x-bhms-unit") != unit:
            raise self.fail("UNIT_MISMATCH", path, f"the input feeding {path} is in {source.get('x-bhms-unit')!r}, "
                            f"the action takes {unit}", f"declare the input in {unit}", unit)
        envelope = effective_bounds(node, policy)
        problems = []
        if "minimum" in envelope and not ("minimum" in source and source["minimum"] >= envelope["minimum"]):
            problems.append("minimum")
        if "maximum" in envelope and not ("maximum" in source and source["maximum"] <= envelope["maximum"]):
            problems.append("maximum")
        if "enum" in envelope and not ("enum" in source and all(v in envelope["enum"] for v in source["enum"])):
            problems.append("enum")
        if problems:
            bound = {k: v for k, v in envelope.items() if k in problems}
            raise self.fail("OUT_OF_RANGE", path, f"the input feeding {path} allows values outside the action's "
                            f"envelope ({', '.join(problems)})", "narrow the input's bounds to "
                            + ", ".join(f"{k} {v}" for k, v in bound.items()) + " (BHMS-PRG-005)", bound)


# --------------------------------------------------------------------------- execution


class _StepFailed(Exception):
    def __init__(self, error: dict[str, Any]) -> None:
        super().__init__(error.get("message", "step failed"))
        self.error = error


class _StepUnknown(Exception):
    pass


class _Halted(Exception):  # noqa: N818 - control flow: cancel or stop observed between steps
    pass


@dataclass
class _Run:
    rec: OperationRecord
    plan: Plan
    principal: Principal
    lease_id: str | None
    variables: dict[str, Any]
    deadline: float
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    halted: bool = False
    child: OperationRecord | None = None
    done: int = 0
    task: asyncio.Task[None] | None = None


class ProgramRunner:
    """``programs/*`` for one server; see the module docstring."""

    def __init__(self, server: DeviceServer) -> None:
        self.server = server
        self._runs: dict[str, _Run] = {}

    # ------------------------------------------------------------------ validation and registry

    def validate(self, principal: Principal, program: dict[str, Any]) -> Plan:
        return _Validator(self.server, principal, program).run()

    async def register(self, principal: Principal, program: dict[str, Any]) -> dict[str, Any]:
        if not principal.has("programs:register"):
            raise BhmsError("UNAUTHORIZED", "programs/register needs the programs:register scope",
                            hint="missing scope programs:register")
        plan = self.validate(principal, program)
        self.server.store.put_program(plan.digest, program, plan.info, now_ns())
        stored = self.server.store.get_program(plan.digest)
        return stored[1] if stored else plan.info

    def get(self, principal: Principal, program_digest: str) -> tuple[dict[str, Any], dict[str, Any]]:
        if not principal.can_read:
            raise BhmsError("UNAUTHORIZED", "programs/get needs the read scope", hint="missing scope read")
        stored = self.server.store.get_program(program_digest)
        if stored is None:
            raise BhmsError("INVALID_ARGUMENT", f"no registered program {program_digest}", field="digest",
                            hint="register it with programs/register, or run it inline (BHMS-PRG-020)")
        return stored

    def list(self, principal: Principal, cursor: str | None, limit: int) -> tuple[list[dict[str, Any]], str | None]:
        from bhms.server.server import decode_cursor, encode_cursor

        if not principal.can_read:
            raise BhmsError("UNAUTHORIZED", "programs/list needs the read scope", hint="missing scope read")
        after = decode_cursor("p", cursor) if cursor is not None else None
        rows = self.server.store.list_programs(after=after, limit=limit + 1)
        more = len(rows) > limit
        rows = rows[:limit]
        return rows, encode_cursor("p", rows[-1]["digest"]) if more and rows else None

    # ------------------------------------------------------------------ run

    async def run(self, principal: Principal, params: Any, raw: dict[str, Any]) -> tuple[OperationRecord, bool]:
        """``programs/run`` from key lookup to the start of execution; returns (operation, replayed)."""
        srv = self.server
        key = params.operation_key
        if key is not None and key.startswith("g-") and not principal.gateway:
            raise BhmsError("INVALID_ARGUMENT", "operationKey prefix g- is reserved for gateways", field="operationKey",
                            hint="use a key that does not start with d- or g- (BHMS-OPS-037)")
        program = raw.get("program")
        program_digest = params.digest if params.digest is not None else digest(program)
        request_digest = intent_digest("programs/run", {"digest": program_digest, "arguments": raw["arguments"],
                                                        "deadlineMs": raw.get("deadlineMs")})
        if key is None:
            return await self._admit(principal, params, raw, program, program_digest, server_key(), "server",
                                     request_digest), False
        async with srv.journal.admission(principal.id, key):
            existing = srv.journal.lookup_key(principal.id, key)
            if existing is not None:
                if existing.op["requestDigest"] != request_digest:
                    raise key_conflict_error(existing, key)
                return existing, True
            return await self._admit(principal, params, raw, program, program_digest, key, "client",
                                     request_digest), False

    async def _admit(self, principal: Principal, params: Any, raw: dict[str, Any], program: dict[str, Any] | None,
                     program_digest: str, key: str, origin: str, request_digest: str) -> OperationRecord:
        srv = self.server
        if program is None:
            stored = srv.store.get_program(program_digest)
            if stored is None:
                raise BhmsError("INVALID_ARGUMENT", f"no registered program {program_digest}", field="digest",
                                hint="register it with programs/register, or send it inline (BHMS-PRG-020)")
            program = stored[0]
        if not principal.has("programs:run"):
            raise BhmsError("UNAUTHORIZED", "programs/run needs the programs:run scope",
                            hint="missing scope programs:run")
        plan = self.validate(principal, program)
        admitted = plan.input_validator.admit(raw["arguments"])
        lease: Lease | None = None
        if plan.lease_resources or params.lease_id is not None:
            lease = srv.leases.check(principal, params.lease_id, plan.lease_resources)
        srv.require_journal()
        deadline_ns = now_ns() + params.deadline_ms * 1_000_000 if params.deadline_ms is not None else None
        try:
            rec = srv.journal.create(
                principal=principal.id, key=key, key_origin=origin, kind="program", program_digest=program_digest,
                arguments=raw["arguments"], admitted=admitted, request_digest=request_digest,
                lease_id=lease.lease_id if lease else None, fence=lease.fence if lease else None,
                deadline_ns=deadline_ns, progress={"stepsCompleted": 0, "stepsTotal": plan.info["maxExecutedSteps"]},
                private={"resources": list(plan.info["resources"]), "effectClass": plan.info["effect"],
                         "devices": plan.info["devices"]})
        except StoreError as exc:
            srv.journal_failed(exc)
            raise BhmsError("BUSY", "the operation journal cannot be written; nothing was recorded or run",
                            retry="same-key", hint="retry later with the same operationKey") from None
        bound = plan.program["maxDurationMs"] / 1000
        if deadline_ns is not None:
            bound = min(bound, (deadline_ns - now_ns()) / 1e9)
        run = _Run(rec, plan, principal, lease.lease_id if lease else None, dict(admitted), time.monotonic() + bound)
        self._runs[rec.id] = run
        run.task = asyncio.get_running_loop().create_task(self._execute(run), name=f"bhms-program-{rec.id}")
        return rec

    # ------------------------------------------------------------------ execution

    async def _execute(self, run: _Run) -> None:
        journal = self.server.journal
        try:
            try:
                await self._steps(run, run.plan.steps, "")
                output = resolve(run.plan.program.get("output") or {}, run.variables)
                journal.transition(run.rec, "completed", result=output, **self._outcome(run))
            except _Halted:
                self._halt(run)
            except _StepUnknown:
                journal.transition(run.rec, "unknown", error=unknown_error(
                    f"step outcome unknown (child {run.child.id if run.child else '?'}); the program stopped"))
            except _StepFailed as failure:
                self._fail(run, failure.error)
        except asyncio.CancelledError:
            raise  # server shutdown: the program stays in flight and is settled at restart (BHMS-PRG-017)
        except StoreError as exc:
            self.server.journal_failed(exc)
            log.error("could not record the outcome of program %s; it is settled at restart", run.rec.id)
        except Exception:  # noqa: BLE001 - a coordinator bug must still settle the program honestly
            log.exception("program %s failed unexpectedly", run.rec.id)
            with contextlib.suppress(Exception):
                if run.rec.state == "accepted":
                    journal.transition(run.rec, "rejected", error=BhmsError(
                        "INTERNAL", "the program could not start", hint="this is a server bug").to_operation_error())
                elif not run.rec.settled:
                    journal.transition(run.rec, "unknown", error=unknown_error("the program coordinator failed"))
        finally:
            self._runs.pop(run.rec.id, None)

    def _children(self, run: _Run) -> list[OperationRecord]:
        return self.server.journal.children(run.rec.id)

    def _outcome(self, run: _Run) -> dict[str, Any]:
        return program_outcome(self._children(run))

    def _acted(self, run: _Run) -> bool:
        return any(c.dispatched and c.private.get("effectClass", "none") != "none" for c in self._children(run))

    def _fail(self, run: _Run, error: dict[str, Any]) -> None:
        journal = self.server.journal
        acted = self._acted(run)
        payload = {**error, "mayHaveActed": acted}
        if payload.get("bhmsCode") in ("DEVICE_FAULT", "UNVERIFIED") and not acted:
            payload["bhmsCode"] = "INTERNAL"
        if run.rec.state == "accepted":
            journal.transition(run.rec, "rejected", error={**payload, "mayHaveActed": False})
            return
        journal.transition(run.rec, "failed", error=payload, **self._outcome(run),
                           proof=None if acted else "no effectful step was dispatched")

    def _halt(self, run: _Run) -> None:
        journal = self.server.journal
        if run.rec.settled:
            return
        if run.rec.state == "accepted":
            journal.transition(run.rec, "canceled", detail="canceled before the first step")
        else:
            journal.transition(run.rec, "canceled", **self._outcome(run),
                               detail=f"no further steps after {run.done} completed step(s)")

    def _check_boundary(self, run: _Run) -> None:
        if run.halted:
            raise _Halted
        if time.monotonic() >= run.deadline:
            raise _StepFailed(BhmsError("DEADLINE_EXCEEDED", "the program exceeded its maxDurationMs or deadline; no "
                                        "further step started", may_have_acted=True,
                                        hint="inspect the child operations before running a compensating program")
                              .to_operation_error())
        if run.lease_id is not None:
            try:
                self.server.leases.check(run.principal, run.lease_id, run.plan.lease_resources)
            except BhmsError as exc:
                raise _StepFailed(exc.to_operation_error()) from None

    def _begin(self, run: _Run) -> None:
        """Move the program to ``running`` (a barrier commit via ``dispatching``) before its first step can act."""
        if run.rec.state == "accepted":
            self.server.journal.transition(run.rec, "dispatching")
            self.server.journal.transition(run.rec, "running", detail="first step started")

    def _start_step(self, run: _Run, step: Step, path: str, child: OperationRecord | None = None) -> None:
        journal = self.server.journal
        self._begin(run)
        journal.annotate(run.rec, "step", f"{step.raw['kind']} {path}", step_index=step.index,
                         child_operation_id=child.id if child is not None else None)

    def _finish_step(self, run: _Run) -> None:
        run.done += 1
        self.server.journal.set_progress(run.rec, {"stepsCompleted": run.done,
                                                   "stepsTotal": run.plan.info["maxExecutedSteps"]})

    async def _steps(self, run: _Run, steps: list[Step], prefix: str) -> None:
        for position, step in enumerate(steps):
            path = f"{prefix}{position}"
            kind = step.raw["kind"]
            if kind == "repeat":
                times = run.variables[step.times_input] if step.times_input else step.raw["times"]
                name = step.raw.get("as")
                for iteration in range(times):
                    if name:
                        run.variables[name] = iteration
                    await self._steps(run, step.body, f"{path}/{iteration}/")
                if name:
                    run.variables.pop(name, None)
                continue
            self._check_boundary(run)
            if kind == "invoke":
                await self._invoke(run, step, path)
            else:
                self._start_step(run, step, path)
                if kind == "read":
                    await self._read(run, step)
                elif kind == "waitUntil":
                    await self._wait_until(run, step)
                elif kind == "assert":
                    if not evaluate(step.raw["predicate"], run.variables):
                        raise _StepFailed(BhmsError("STALE", f"assert failed: {step.raw['message']}",
                                                    hint=step.raw["message"]).to_operation_error())
                else:
                    await self._sleep(run, step.raw["durationMs"] / 1000)
            self._finish_step(run)

    async def _sleep(self, run: _Run, seconds: float) -> None:
        """Sleep the full duration (bounded by the program deadline); cancellation or stop ends it early."""
        truncated = time.monotonic() + seconds > run.deadline
        end = min(time.monotonic() + seconds, run.deadline)
        while (remaining := end - time.monotonic()) > 0:
            run.wake.clear()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(run.wake.wait(), remaining)
            if run.halted:
                raise _Halted
        if truncated:
            self._check_boundary(run)

    def _step_lease(self, run: _Run, spec: Any) -> str | None:
        """The lease an invoke step presents: the program's lease when the step requires one or when that lease covers
        every resource the step uses (a held lease refuses a request that does not present it, BHMS-LSE-014)."""
        if run.lease_id is None or spec.requires_lease:
            return run.lease_id if spec.requires_lease else None
        lease = self.server.leases.get(run.lease_id)
        if lease is not None and spec.resources and set(spec.resources).issubset(lease.resources):
            return run.lease_id
        return None

    async def _invoke(self, run: _Run, step: Step, path: str) -> None:
        srv, journal = self.server, self.server.journal
        try:
            arguments = resolve(step.raw["arguments"], run.variables)
        except (KeyError, IndexError, TypeError) as exc:
            raise _StepFailed(BhmsError("INVALID_ARGUMENT", f"step {path}: a reference could not be resolved ({exc})",
                                        field=f"program.steps[{path}].arguments",
                                        hint="check the saved value the step refers to").to_operation_error()) from None
        params = SimpleNamespace(device_id=step.device.device_id, action=step.spec.name, arguments=arguments,
                                 lease_id=self._step_lease(run, step.spec), deadline_ms=None,
                                 require=None, description_digest=None)
        key = derived_key(run.rec.id, path)
        request_digest = intent_digest("actions/invoke", {"deviceId": params.device_id, "action": params.action,
                                                          "arguments": arguments})
        deadline_ns = now_ns() + int(max(0.0, run.deadline - time.monotonic()) * 1e9)
        # The program is durably dispatching before its first child exists, so a crash never leaves a dispatched child
        # under a program that still reads accepted (BHMS-PRG-017, BHMS-OPS-080).
        self._begin(run)
        try:
            child = await srv.executor.admit(run.principal, params, key, "derived", request_digest,
                                             parent_id=run.rec.id, deadline_ns=deadline_ns)
        except BhmsError as exc:
            raise _StepFailed(exc.to_operation_error()) from None
        run.child = child
        self._start_step(run, step, path, child)
        while not child.settled:
            remaining = run.deadline - time.monotonic()
            if remaining <= 0 and child.op["cancel"]["state"] == "none":
                srv.executor.cancel(child, "program maxDurationMs exceeded")
                remaining = srv.cancel_grace_ms / 1000
            await journal.wait(child, max(0.01, remaining))
            if not child.settled and run.deadline + srv.cancel_grace_ms / 1000 < time.monotonic():
                break
        if child.state == "completed":
            if step.raw.get("saveAs"):
                run.variables[step.raw["saveAs"]] = child.op.get("result")
            return
        if child.state == "unknown" or not child.settled:
            raise _StepUnknown
        if run.halted and child.state == "canceled":
            raise _Halted
        if time.monotonic() >= run.deadline:
            self._check_boundary(run)
        error = child.op.get("error") or BhmsError("INTERNAL", f"step {path} ended {child.state}",
                                                   may_have_acted=child.dispatched,
                                                   hint="inspect the child operation").to_operation_error()
        raise _StepFailed({**error, "message": f"step {path} ({step.spec.name}): {error['message']}"[:2000]})

    async def _read(self, run: _Run, step: Step) -> None:
        raw = step.raw
        timeout = min(raw.get("timeoutMs", 1000) / 1000, max(0.0, run.deadline - time.monotonic()))
        try:
            observation = await asyncio.wait_for(self.server.observations.read(
                step.device, step.spec.name, max_age_ms=raw.get("maxAgeMs"), fresh=raw.get("fresh"),
                principal=run.principal, lease_id=run.lease_id), timeout)
        except asyncio.TimeoutError:
            raise _StepFailed(BhmsError("DEADLINE_EXCEEDED", f"read of {step.device.device_id}.{step.spec.name} "
                                        "timed out", may_have_acted=True, hint="check the sensor")
                              .to_operation_error()) from None
        except BhmsError as exc:
            raise _StepFailed(exc.to_operation_error()) from None
        run.variables[raw["saveAs"]] = observation

    async def _wait_until(self, run: _Run, step: Step) -> None:
        raw = step.raw
        poll = max(10, raw.get("pollMs", 100)) / 1000
        until = min(time.monotonic() + raw["timeoutMs"] / 1000, run.deadline)
        fresh = step.spec.getter is not None
        while True:
            try:
                observation = await self.server.observations.read(step.device, step.spec.name, fresh=fresh or None,
                                                                  principal=run.principal, lease_id=run.lease_id)
            except BhmsError:
                observation = None
            if observation is not None and observation["quality"] == "valid" and \
                    evaluate(raw["predicate"], {**run.variables, "observed": observation}):
                if raw.get("saveAs"):
                    run.variables[raw["saveAs"]] = observation
                return
            if time.monotonic() + poll > until:
                raise _StepFailed(BhmsError("DEADLINE_EXCEEDED", f"waitUntil on {step.device.device_id}."
                                            f"{step.spec.name} timed out after {raw['timeoutMs']} ms",
                                            may_have_acted=True, hint="the condition never held on a valid "
                                                                      "observation (BHMS-PRG-013)")
                                  .to_operation_error())
            run.wake.clear()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(run.wake.wait(), poll)
            if run.halted:
                raise _Halted

    # ------------------------------------------------------------------ cancel, stop, lease loss

    async def cancel(self, rec: OperationRecord, reason: str | None) -> None:
        """``operations/cancel`` on a program: no further steps; the running child is cancelled (BHMS-PRG-014)."""
        journal = self.server.journal
        if rec.terminal:
            return
        if rec.op["cancel"]["state"] in ("none", "refused"):
            journal.set_cancel(rec, "requested", reason=reason)
        run = self._runs.get(rec.id)
        if run is None:
            return
        run.halted = True
        run.wake.set()
        if run.child is not None and not run.child.settled:
            self.server.executor.cancel(run.child, reason or "program canceled")

    def stop_device(self, device_id: str, reason: str) -> bool:
        """Stop every running program with steps on ``device_id``; returns True if the journal could not be written."""
        degraded = False
        for run in list(self._runs.values()):
            if device_id not in run.plan.info["devices"] or run.rec.settled:
                continue
            try:
                self.server.journal.annotate(run.rec, "stop", f"stop of {device_id}: {reason}")
                if run.rec.op["cancel"]["state"] in ("none", "refused"):
                    self.server.journal.set_cancel(run.rec, "requested", reason=f"stop: {reason}")
            except StoreError as exc:
                degraded = True
                self.server.journal_failed(exc)
            run.halted = True
            run.wake.set()
        return degraded

    def on_lease_end(self, lease: Lease, reason: str) -> None:
        """No new step starts under an ended lease (BHMS-LSE-012): wake runs so their boundary check fails."""
        for run in self._runs.values():
            if run.lease_id == lease.lease_id:
                run.wake.set()

    async def close(self) -> None:
        tasks = [run.task for run in self._runs.values() if run.task is not None and not run.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


__all__ = ["Plan", "ProgramRunner", "evaluate", "reference", "resolve"]
