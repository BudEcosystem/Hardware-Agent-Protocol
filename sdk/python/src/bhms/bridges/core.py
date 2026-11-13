"""The agent surface (spec 12): eight tools over one :class:`~bhms.client.client.Client`.

:class:`AgentBridge` is the single implementation behind the MCP bridge (:mod:`bhms.bridges.mcp`), the OpenAI adapter
(:mod:`bhms.bridges.openai_tools`) and the ``bhms`` CLI: ``tool_definitions()`` lists the tools (names, descriptions and
input schemas from the schema's ``x-bhms-agent-tools``, references inlined and top-level ``oneOf`` flattened for
function-calling compatibility, the bridge enforces exactly-one itself), and ``await bridge.call(name, arguments)`` runs
one tool and returns a :class:`ToolResult`: a one-line summary plus the BHMS result object, or a refusal.

Rules implemented here (spec IDs): AGT-001 (at most these eight tools; ``bhms_run_program`` only with ``programs``),
AGT-002 (the bridge uses its own principal; tool arguments carry no identity, scopes, leases or bounds), AGT-010/011/012
(summary then structured content), AGT-013 (signature block), AGT-020/021 (every error becomes a refusal; arguments are
checked against the action's input before any request that could act), AGT-030..032 (operation keys, ``wait_ms``),
AGT-040/041 (leases: acquired on exactly the needed resources, renewed while the operation is unsettled, released when it
settles; with an ``operation_key`` the first request carries no lease).

Thread-safety: one event loop; ``call`` may be awaited concurrently.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import logging
from dataclasses import dataclass
from typing import Any

from bhms.bridges import render
from bhms.client.client import Client
from bhms.protocol import schema
from bhms.protocol.errors import BhmsError
from bhms.protocol.types import SETTLED_STATES, to_wire
from bhms.server.validation import ArgumentValidator
from bhms.transport.base import TransportClosed

log = logging.getLogger("bhms.bridge")

DEFAULT_WAIT_MS = 5000
MAX_WAIT_MS = 60_000
LEASE_TTL_MS = 15_000
SIGNATURE_KEY = "signature"

_ANNOTATIONS: dict[str, dict[str, bool]] = {
    "bhms_find": {"readOnlyHint": True, "idempotentHint": True},
    "bhms_describe": {"readOnlyHint": True, "idempotentHint": True},
    "bhms_read": {"readOnlyHint": True},
    "bhms_invoke": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False},
    "bhms_operation": {"readOnlyHint": True, "idempotentHint": True},
    "bhms_cancel": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True},
    "bhms_stop": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True},
    "bhms_run_program": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False},
}
_EXACTLY_ONE = {
    "bhms_stop": ("device_ids", "all", "Give exactly one of device_ids or all."),
    "bhms_run_program": ("program", "program_digest", "Give exactly one of program or program_digest."),
}


@dataclass(frozen=True, slots=True)
class ToolDef:
    """One tool as every bridge publishes it."""

    name: str
    description: str
    input_schema: dict[str, Any]
    annotations: dict[str, bool]


@dataclass(slots=True)
class ToolResult:
    """The outcome of one tool call: ``summary`` (one line), ``data`` (BHMS result object) or ``error`` (a refusal)."""

    summary: str
    data: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    block: str | None = None  # the signature block of bhms_describe
    failed: bool = False  # an admitted operation that failed or is unknown: isError without a refusal object

    @property
    def is_error(self) -> bool:
        return self.error is not None or self.failed

    @property
    def text(self) -> str:
        return self.summary if self.block is None else f"{self.summary}\n{self.block}"

    @property
    def structured(self) -> dict[str, Any]:
        """MCP ``structuredContent``: the BHMS result, or ``{error}`` for a refusal."""
        return {"error": self.error} if self.error is not None else (self.data or {})

    def function_output(self) -> dict[str, Any]:
        """Function-tool output: ``{summary, data}`` or ``{summary, error}`` (BHMS-AGT-010, AGT-020)."""
        out: dict[str, Any] = {"summary": self.summary}
        if self.block is not None:
            out[SIGNATURE_KEY] = self.block
        if self.error is not None:
            out["error"] = self.error
        else:
            out["data"] = self.data
        return out


# ---------------------------------------------------------------------------------------------- tool definitions

def _inline(node: Any, defs: dict[str, Any], stack: tuple[str, ...], shared: set[str], used: set[str],
            counts: dict[str, int]) -> Any:
    """Resolve ``$ref`` in place. A definition in ``shared`` (or one that refers to itself) stays a ``$ref`` and is
    collected in ``used``; every other reference is inlined and counted."""
    if isinstance(node, list):
        return [_inline(n, defs, stack, shared, used, counts) for n in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        name = ref[len("#/$defs/"):]
        extra = {k: _inline(v, defs, stack, shared, used, counts) for k, v in node.items() if k != "$ref"}
        counts[name] = counts.get(name, 0) + 1
        if name in stack or name in shared:
            used.add(name)
            return {"$ref": ref, **extra}
        return {**_inline(defs[name], defs, (*stack, name), shared, used, counts), **extra}
    return {k: _inline(v, defs, stack, shared, used, counts) for k, v in node.items()}


def input_schema_for(tool: str) -> dict[str, Any]:
    """The tool's input schema, self-contained: ``$ref`` inlined, large definitions used more than once (and recursive
    ones) kept once under ``$defs``, and no top-level ``oneOf`` (BHMS-AGT-050 keeps both bridges identical)."""
    document = schema.load_schema()
    defs = document["$defs"]
    name = document["x-bhms-agent-tools"][tool]["input"].rsplit("/", 1)[-1]
    counts: dict[str, int] = {}
    used: set[str] = set()
    _inline(copy.deepcopy(defs[name]), defs, (name,), set(), used, counts)
    shared = used | {n for n, c in counts.items() if c > 1 and len(str(defs[n])) > 200}
    used = set()
    out = _inline(copy.deepcopy(defs[name]), defs, (name,), shared, used, {})
    out.pop("oneOf", None)
    bodies: dict[str, Any] = {}
    pending = sorted(used)
    while pending:  # shared bodies may refer to other shared definitions
        current = pending.pop()
        if current in bodies:
            continue
        more: set[str] = set()
        bodies[current] = _inline(copy.deepcopy(defs[current]), defs, (current,), shared, more, {})
        pending += sorted(more - set(bodies))
    if bodies:
        out["$defs"] = {k: bodies[k] for k in sorted(bodies)}
    return out


def tool_definitions(capabilities: Any | None = None) -> list[ToolDef]:
    """The tools a bridge exposes for a server (BHMS-AGT-001): ``bhms_run_program`` only when ``programs`` is advertised.

    ``capabilities`` is the server's ``capabilities`` (model or dict); ``None`` lists all eight.
    """
    document = schema.load_schema()
    tools = []
    for name, spec in document["x-bhms-agent-tools"].items():
        if name == "bhms_run_program" and capabilities is not None and not _has(capabilities, "programs"):
            continue
        description = spec["description"]
        if name in _EXACTLY_ONE:
            description += " " + _EXACTLY_ONE[name][2]
        tools.append(ToolDef(name, description, input_schema_for(name), dict(_ANNOTATIONS[name], openWorldHint=True)))
    return tools


def _has(capabilities: Any, member: str) -> bool:
    value = capabilities.get(member) if isinstance(capabilities, dict) else getattr(capabilities, member, None)
    return value is not None


# ---------------------------------------------------------------------------------------------- the bridge

@dataclass(slots=True)
class _Held:
    lease_id: str
    resources: list[str]
    task: asyncio.Task[None] | None = None


@dataclass(slots=True)
class BridgeStats:
    calls: int = 0
    refusals: int = 0
    leases_acquired: int = 0
    leases_released: int = 0


class AgentBridge:
    """Runs the eight agent tools against ``client`` (a device server or a gateway).

    Args:
        client: a connected :class:`Client`; the bridge never opens or closes it.
        lease_ttl_ms: TTL of leases the bridge acquires for a lease-requiring action (clamped to the server's limits).
    """

    def __init__(self, client: Client, *, lease_ttl_ms: int = LEASE_TTL_MS) -> None:
        self.client = client
        self.lease_ttl_ms = lease_ttl_ms
        self._descriptions: dict[str, dict[str, Any]] = {}
        self._held: dict[str, _Held] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self.stats = BridgeStats()

    # ------------------------------------------------------------------ definitions

    @property
    def capabilities(self) -> Any:
        return self.client.server.capabilities if self.client.server is not None else None

    def tool_definitions(self) -> list[ToolDef]:
        return tool_definitions(self.capabilities)

    @property
    def max_wait_ms(self) -> int:
        limits = self.client.server.limits if self.client.server is not None else None
        return min(MAX_WAIT_MS, limits.max_wait_ms if limits is not None else MAX_WAIT_MS)

    async def aclose(self) -> None:
        """Stop lease renewal. Leases of unsettled operations are left to expire (their TTL) rather than released."""
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    # ------------------------------------------------------------------ dispatch

    async def call(self, name: str, arguments: dict[str, Any] | None) -> ToolResult:
        """Run one tool; never raises: every failure is a refusal (BHMS-AGT-020)."""
        self.stats.calls += 1
        arguments = {} if arguments is None else arguments
        try:
            tools = {t.name for t in self.tool_definitions()}
            if name not in tools:
                raise BhmsError("UNSUPPORTED", f"{name!r} is not a tool of this bridge", field="name", bound=sorted(tools),
                                hint=f"call one of: {', '.join(sorted(tools))}")
            self._check_input(name, arguments)
            handler = getattr(self, "_" + name)
            return await handler(arguments)
        except BhmsError as exc:
            return self._refuse(exc, name, arguments)
        except (TransportClosed, ConnectionError, OSError) as exc:
            acting = name in ("bhms_invoke", "bhms_run_program", "bhms_stop", "bhms_cancel")
            return self._refuse(BhmsError("DEVICE_UNAVAILABLE", f"the connection to the BHMS server was lost: {exc}",
                                          may_have_acted=acting, hint="reconnect the bridge, then check the operation "
                                          "with bhms_operation before retrying"), name, arguments)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # a bridge bug must still be a refusal, never a crash of the host
            log.exception("bridge failure in %s", name)
            return self._refuse(BhmsError("INTERNAL", f"bridge error: {type(exc).__name__}: {exc}"[:500],
                                          may_have_acted=name in ("bhms_invoke", "bhms_run_program"),
                                          hint="report this bridge bug; check with bhms_operation before retrying"),
                                name, arguments)

    def _refuse(self, exc: BhmsError, tool: str, arguments: dict[str, Any]) -> ToolResult:
        self.stats.refusals += 1
        error = exc.to_operation_error()
        if exc.code == "LEASE_CONFLICT":
            error["hint"] = ("that resource is in use by another principal; " + error["hint"]).strip()[:2000]
        elif exc.code == "DEADLINE_EXCEEDED" and exc.may_have_acted and tool in ("bhms_invoke", "bhms_run_program"):
            key = arguments.get("operation_key")
            error["hint"] = (f'repeat {tool} with the same operation_key "{key}" and identical arguments (it returns the '
                             "original operation instead of acting again)" if key else
                             "no operation_key was given, so a repeat could act twice: read the device's properties to "
                             "see whether it acted")
        elif exc.code in ("UNKNOWN_DEVICE", "STALE") and exc.field in ("deviceId", "device_id", None):
            self._descriptions.pop(str(arguments.get("device_id", "")), None)
        return ToolResult(render.summarize_refusal(error), error=error)

    def _check_input(self, name: str, arguments: dict[str, Any]) -> None:
        """Validate against the normative schema before anything is sent (BHMS-AGT-021)."""
        if not isinstance(arguments, dict):
            raise BhmsError("INVALID_ARGUMENT", "tool arguments must be a JSON object", field="",
                            hint=f"call {name} with an object such as {_example_call(name)}")
        spec = schema.load_schema()["x-bhms-agent-tools"][name]["input"].rsplit("/", 1)[-1]
        if name in _EXACTLY_ONE:
            first, second, _ = _EXACTLY_ONE[name]
            given = [k for k in (first, second) if k in arguments]
            if len(given) != 1:
                raise BhmsError("INVALID_ARGUMENT", f"give exactly one of {first} or {second}"
                                + (", not both" if len(given) == 2 else ""), field=first, bound=[first, second],
                                hint=f"send {first} or {second}, for example {_example_call(name)}")
        try:
            schema.validate(spec, arguments)
        except BhmsError as exc:
            pointer = exc.field or ""
            raise BhmsError("INVALID_ARGUMENT", _short(exc.message), field=pointer.lstrip("/").replace("/", "."),
                            bound=None, hint=f"fix {pointer.lstrip('/').replace('/', '.') or 'the arguments'}; example: "
                            f"{_example_call(name)}") from None

    # ------------------------------------------------------------------ discovery

    async def description(self, device_id: str, *, refresh: bool = False) -> dict[str, Any]:
        """The device description as a wire dict, cached until the server says it changed."""
        cached = self._descriptions.get(device_id)
        if cached is not None and not refresh:
            return cached
        result = await self.client.devices_describe(device_id)
        desc = to_wire(result.description)
        self._descriptions[device_id] = desc
        return desc

    async def _bhms_find(self, args: dict[str, Any]) -> ToolResult:
        filt = {k: args[k] for k in ("text", "capability", "tag", "status") if k in args}
        page = await self.client.devices_list(filter=filt or None, cursor=args.get("cursor"))
        data: dict[str, Any] = {"devices": [to_wire(d) for d in page.devices]}
        programs: list[dict[str, Any]] | None = None
        caps = self.capabilities
        registry = getattr(getattr(caps, "programs", None), "registry", False)
        if registry and "cursor" not in args:
            programs = await self._programs(args.get("text"))
            if programs is not None:
                data["programs"] = programs
        if page.next_cursor:
            data["nextCursor"] = page.next_cursor
        return ToolResult(render.summarize_find(data["devices"], programs, page.next_cursor), data)

    async def _programs(self, text: str | None) -> list[dict[str, Any]] | None:
        try:
            page = await self.client.programs_list(limit=50)
        except BhmsError as exc:
            if exc.code in ("UNAUTHORIZED", "UNSUPPORTED"):
                return None  # this principal cannot see the registry: omit, not an error (BHMS-AGT-001)
            raise
        items = [to_wire(p) for p in page.programs]
        if text:
            words = text.lower().split()
            items = [p for p in items if all(w in f"{p['name']} {p['description']}".lower() for w in words)]
        return items

    async def _bhms_describe(self, args: dict[str, Any]) -> ToolResult:
        result = await self.client.devices_describe(args["device_id"])
        desc = to_wire(result.description)
        self._descriptions[args["device_id"]] = desc
        return ToolResult(render.summarize_describe(desc), to_wire(result), block=render.signature_block(desc))

    async def _bhms_read(self, args: dict[str, Any]) -> ToolResult:
        device, prop = args["device_id"], args["property"]
        kw = {"max_age_ms": args.get("max_age_ms"), "fresh": args.get("fresh")}
        try:
            result = await self.client.properties_read(device, prop, **kw)
        except BhmsError as exc:
            if exc.code != "LEASE_REQUIRED":
                raise
            desc = await self.description(device)
            spec = (desc.get("properties") or {}).get(prop) or {}
            resources = spec.get("resources") or desc.get("resources") or []
            if not resources:
                raise
            lease = await self._acquire(resources)
            try:
                result = await self.client.properties_read(device, prop, **kw)
            finally:
                await self._release(lease.lease_id)
        return ToolResult(render.summarize_observation(device, prop, to_wire(result.observation)), to_wire(result))

    # ------------------------------------------------------------------ operations

    def _wait(self, args: dict[str, Any]) -> int:
        return max(0, min(int(args.get("wait_ms", DEFAULT_WAIT_MS)), self.max_wait_ms, MAX_WAIT_MS))

    async def _desc_for_op(self, op: dict[str, Any]) -> dict[str, Any] | None:
        device = op.get("deviceId")
        if not device:
            return None
        try:
            return await self.description(device)
        except BhmsError:
            return None

    async def _operation_result(self, result: Any, *, tool: str, replayed: bool = False, keyed: bool = True) -> ToolResult:
        data = to_wire(result)
        op = data["operation"]
        desc = await self._desc_for_op(op) if op.get("state") == "completed" else None
        summary = render.summarize_operation(op, replayed=replayed, description=desc, keyed=keyed,
                                             show_key=tool in ("bhms_invoke", "bhms_run_program"))
        failed = op.get("state") in ("failed", "rejected", "unknown")
        return ToolResult(summary, data, failed=failed)

    async def _bhms_invoke(self, args: dict[str, Any]) -> ToolResult:
        device, action = args["device_id"], args["action"]
        desc = await self.description(device)
        spec = (desc.get("actions") or {}).get(action)
        if spec is None:
            names = sorted(desc.get("actions") or {})
            raise BhmsError("UNKNOWN_ACTION", f"{device} has no action {action!r}", field="action", bound=names,
                            hint=f"use one of: {', '.join(names) or 'none (this device has no actions)'}")
        arguments = args["arguments"]
        try:
            ArgumentValidator(spec["input"]).admit(arguments)
        except BhmsError as exc:
            example = render.example_arguments(spec["input"])
            exc.hint = f"{exc.hint}; e.g. arguments {render._json(example)}"[:2000]
            raise
        key = args.get("operation_key")
        require = {"effect": "verified"} if args.get("require_verified") else None
        wait_ms = self._wait(args)

        async def send(lease_id: str | None) -> Any:
            return await self.client.actions_invoke(device, action, arguments, operation_key=key, lease_id=lease_id,
                                                    wait_ms=wait_ms, require=require, description_digest=desc.get("digest"))

        result = await self._with_lease(send, spec.get("requiresLease", False), spec.get("resources") or [],
                                        has_key=key is not None)
        return await self._operation_result(result, tool="bhms_invoke", replayed=result.replayed,
                                            keyed=result.operation.key_origin != "server")

    async def _bhms_run_program(self, args: dict[str, Any]) -> ToolResult:
        key, wait_ms = args.get("operation_key"), self._wait(args)
        resources: list[str] = []
        if "program_digest" in args:
            try:
                info = (await self.client.programs_get(args["program_digest"])).info
                resources = list(getattr(info, "resources", None) or [])
            except BhmsError:
                resources = []

        async def send(lease_id: str | None) -> Any:
            return await self.client.programs_run(arguments=args["arguments"], program=args.get("program"),
                                                  digest=args.get("program_digest"), operation_key=key,
                                                  lease_id=lease_id, wait_ms=wait_ms)

        result = await self._with_lease(send, bool(resources), resources, has_key=key is not None, discover=True)
        return await self._operation_result(result, tool="bhms_run_program", replayed=result.replayed,
                                            keyed=result.operation.key_origin != "server")

    async def _bhms_operation(self, args: dict[str, Any]) -> ToolResult:
        wait_ms = self._wait(args)
        op_id = args["operation_id"]
        result = (await self.client.operations_wait(op_id, wait_ms)) if wait_ms else await self.client.operations_get(op_id)
        return await self._operation_result(result, tool="bhms_operation")

    async def _bhms_cancel(self, args: dict[str, Any]) -> ToolResult:
        result = await self.client.operations_cancel(args["operation_id"], reason=args.get("reason"))
        data = to_wire(result)
        op = data["operation"]
        cancel = (op.get("cancel") or {}).get("state", "none")
        subject = f"{op.get('deviceId')}.{op.get('action')}" if op.get("deviceId") else "program"
        words = {"requested": "cancel requested, not yet acknowledged", "acknowledged": "cancel acknowledged, still stopping",
                 "confirmed": "cancel confirmed", "refused": "cancel refused by the device", "none": "no cancel recorded"}
        summary = render.compose(f"{subject} {op['operationId']} {op['state']}: {words.get(cancel, cancel)}"
                                 f" (effect {op.get('effect')}).",
                                 next_step="" if op["state"] in render.SETTLED else
                                 f'call bhms_operation(operation_id="{op["operationId"]}", wait_ms=5000) to see it stop')
        return ToolResult(summary, data)

    async def _bhms_stop(self, args: dict[str, Any]) -> ToolResult:
        if args.get("all"):
            result = await self.client.stop(args["reason"], scope="all")
        else:
            result = await self.client.stop(args["reason"], device_ids=list(args["device_ids"]))
        data = to_wire(result)
        return ToolResult(render.summarize_stop(data["stops"]), data,
                          failed=any(s.get("outcome") == "failed" for s in data["stops"]))

    # ------------------------------------------------------------------ leases (BHMS-AGT-040, AGT-041)

    def _ttl(self) -> int:
        leases = getattr(self.capabilities, "leases", None)
        lo = leases.min_ttl_ms if leases else 1
        hi = leases.max_ttl_ms if leases else self.lease_ttl_ms
        return max(lo, min(hi, self.lease_ttl_ms))

    async def _acquire(self, resources: list[str]) -> Any:
        acquired = await self.client.leases_acquire(resources, self._ttl(), wait_ms=0)
        self.stats.leases_acquired += 1
        lease = acquired.lease
        self._held[lease.lease_id] = _Held(lease.lease_id, list(resources))
        return lease

    async def _release(self, lease_id: str) -> None:
        self._held.pop(lease_id, None)
        with contextlib.suppress(BhmsError, TransportClosed, ConnectionError, OSError):
            await asyncio.shield(self.client.leases_release(lease_id))
            self.stats.leases_released += 1

    async def _with_lease(self, send: Any, needs_lease: bool, resources: list[str], *, has_key: bool,
                          discover: bool = False) -> Any:
        """Send with the lease protocol of BHMS-AGT-040/041.

        With an ``operation_key`` the first request carries no lease: a retry of an existing operation then returns it
        even while this bridge still holds the lease of the original call (BHMS-OPS-033, LSE-002). Only on
        ``LEASE_REQUIRED`` is the lease acquired and the identical request resent. ``discover`` lets a program whose
        resources are unknown learn them from the refusal.
        """
        if not needs_lease and not discover:
            return await send(None)
        if needs_lease and not has_key:
            return await self._leased(send, resources)
        try:
            return await send(None)
        except BhmsError as exc:
            if exc.code != "LEASE_REQUIRED":
                raise
            needed = resources or (exc.bound if isinstance(exc.bound, list) else [])
            if not needed:
                raise
            return await self._leased(send, list(needed))

    async def _leased(self, send: Any, resources: list[str]) -> Any:
        lease = await self._acquire(resources)
        try:
            result = await send(lease.lease_id)
        except BhmsError as exc:
            if not exc.may_have_acted:
                await self._release(lease.lease_id)  # nothing was admitted: nothing to protect
            raise  # may have acted: keep the lease until its TTL, never release under a possibly running operation
        except BaseException:
            raise
        op = result.operation
        if op.state in SETTLED_STATES:
            await self._release(lease.lease_id)
        else:
            self._watch(op.operation_id, lease.lease_id)
        return result

    def _watch(self, operation_id: str, lease_id: str) -> None:
        ttl = self._ttl()
        task = asyncio.get_running_loop().create_task(self._renew_until_settled(operation_id, lease_id, ttl),
                                                      name=f"bhms-lease-{lease_id}")
        self._held[lease_id].task = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _renew_until_settled(self, operation_id: str, lease_id: str, ttl: int) -> None:
        """Renew every ttl/3 while the operation is unsettled, then release (BHMS-AGT-040)."""
        try:
            while True:
                op = (await self.client.operations_wait(operation_id, max(ttl // 3, 1))).operation
                if op.state in SETTLED_STATES:
                    break
                await self.client.leases_renew(lease_id, ttl)
        except (BhmsError, TransportClosed, ConnectionError, OSError) as exc:
            log.warning("lease %s is no longer renewed (%s); it expires on its own", lease_id, exc)
            self._held.pop(lease_id, None)
            return
        await self._release(lease_id)


def _short(message: str) -> str:
    return message if len(message) <= 200 else message[:199] + "…"


def _example_call(name: str) -> str:
    examples = {
        "bhms_find": '{"text": "pump"}', "bhms_describe": '{"device_id": "pump-1"}',
        "bhms_read": '{"device_id": "pump-1", "property": "pressure"}',
        "bhms_invoke": '{"device_id": "pump-1", "action": "dispense", "arguments": {"volume": 50}}',
        "bhms_operation": '{"operation_id": "op-7f3a", "wait_ms": 5000}',
        "bhms_cancel": '{"operation_id": "op-7f3a"}',
        "bhms_stop": '{"device_ids": ["pump-1"], "reason": "operator request"}',
        "bhms_run_program": '{"program_digest": "sha256:...", "arguments": {}}',
    }
    return examples.get(name, "{}")


__all__ = ["AgentBridge", "ToolDef", "ToolResult", "input_schema_for", "tool_definitions"]
