"""Deliberately broken BHMS servers: the conformance device with one defect each, to prove a check fails for the right reason.

``python -m bhms.testing.broken_devices <defect>`` serves the conformance device over stdio (in-memory journal) behind a
:class:`Mutator`, a transport wrapper that rewrites the JSON messages between the client and a healthy
:class:`~bhms.server.server.DeviceServer` (``--list`` names the defects; ``--expect`` prints the check each one must fail).
A defect is a pair of message transforms (and, for one, a patch of the lease manager), so the implementation under test is
the real SDK with exactly one behaviour changed; the conformance runner knows nothing about it.

Each defect records ``checks``: the runner checks that must fail (``observers.all-traffic`` is the whole-run observer, fed by
the ``drive`` checks) and ``requirements``: the requirement IDs that must come out failed.
``tests/test_conformance_broken.py`` runs the runner against every defect and asserts exactly that.

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bhms.protocol import schema as bhms_schema
from bhms.testing import conformance_device
from bhms.transport.base import Transport, TransportClosed

Message = dict[str, Any]
BOUNDS = {("move_to", "position"): (0, 200), ("pulse", "count"): (1, 100), ("slow_move", "duration_ms"): (1, 60000),
          ("clamp", "force"): (0, 100), ("dispense", "volume"): (1, 1000)}


@dataclass
class State:
    """What a defect may remember between messages."""

    keys: dict[str, Message] = field(default_factory=dict)
    listens: list[Any] = field(default_factory=list)
    completed: set[str] = field(default_factory=set)
    leases_active: int = 0
    pending_methods: dict[Any, str] = field(default_factory=dict)
    sent_extra: set[Any] = field(default_factory=set)


@dataclass(frozen=True)
class Defect:
    name: str
    description: str
    checks: tuple[str, ...]
    requirements: tuple[str, ...]
    incoming: Callable[[Any, State], Any] | None = None
    outgoing: Callable[[Message, State], list[Message]] | None = None
    patch: Callable[[Any], None] | None = None
    delay_stop_s: float = 0.0
    drive: tuple[str, ...] = ()
    """Checks to run so that the traffic that exposes the defect exists (for defects only an observer can see)."""


# ---------------------------------------------------------------------- transforms


def _clamp(msg: Any, state: State) -> Any:
    if isinstance(msg, dict) and msg.get("method") == "actions/invoke":
        params = msg["params"]
        for (action, member), (low, high) in BOUNDS.items():
            value = params.get("arguments", {}).get(member)
            if params.get("action") == action and isinstance(value, (int, float)) and not isinstance(value, bool):
                params["arguments"][member] = min(max(value, low), high)
    return msg


def _reuse_key(msg: Any, state: State) -> Any:
    if isinstance(msg, dict) and msg.get("method") == "actions/invoke":
        key = msg["params"].get("operationKey")
        if key:
            first = state.keys.setdefault(key, {"action": msg["params"]["action"], "arguments": msg["params"]["arguments"]})
            msg["params"]["action"], msg["params"]["arguments"] = first["action"], first["arguments"]
    return msg


def _unverified_completes(msg: Message, state: State) -> list[Message]:
    result = msg.get("result")
    if isinstance(result, dict) and isinstance(result.get("operation"), dict):
        op = result["operation"]
        if (op.get("error") or {}).get("bhmsCode") == "UNVERIFIED":
            op.update(state="completed", effect="verified", result={})
            op.pop("error", None)
            op.pop("evidence", None)
    return [msg]


def _drop_result_type(msg: Message, state: State) -> list[Message]:
    if isinstance(msg.get("result"), dict) and isinstance(msg["result"].get("observation"), dict):
        msg["result"].pop("resultType", None)
    return [msg]


def _extra_notification(msg: Message, state: State) -> list[Message]:
    if msg.get("method") == "notifications/subscriptions/acknowledged":
        sub = msg["params"]["_meta"]["bhms/subscriptionId"]
        extra = {"jsonrpc": "2.0", "method": "notifications/devices/listChanged",
                 "params": {"_meta": {"bhms/subscriptionId": sub}}}
        return [msg, extra]
    return [msg]


def _stale_as_fresh(msg: Any, state: State) -> Any:
    if isinstance(msg, dict) and msg.get("method") == "properties/read":
        msg["params"].pop("fresh", None)
        msg["params"].pop("maxAgeMs", None)
    return msg


def _bad_digest(msg: Message, state: State) -> list[Message]:
    result = msg.get("result")
    if isinstance(result, dict) and isinstance(result.get("description"), dict):
        result["description"]["digest"] = "sha256:" + "0" * 64
    return [msg]


def _wrong_error_number(msg: Message, state: State) -> list[Message]:
    err = msg.get("error")
    if isinstance(err, dict) and (err.get("data") or {}).get("bhmsCode") == "OUT_OF_RANGE":
        err["code"] = -32013
    return [msg]


def _no_may_have_acted(msg: Message, state: State) -> list[Message]:
    err = msg.get("error")
    if isinstance(err, dict) and isinstance(err.get("data"), dict):
        err["data"].pop("mayHaveActed", None)
    return [msg]


def _accept_fabricated_cursor(msg: Any, state: State) -> Any:
    if isinstance(msg, dict) and isinstance(msg.get("params"), dict):
        params = msg["params"]
        if isinstance(params.get("cursor"), str) and not params["cursor"].startswith(("d.", "o.", "p.")):
            params.pop("cursor")
        if isinstance(params.get("after"), str) and not params["after"].startswith("e."):
            params.pop("after")
    return msg


def _track_leases(msg: Message, state: State) -> list[Message]:
    method = state.pending_methods.pop(msg.get("id"), None)
    if method == "leases/acquire" and isinstance(msg.get("result"), dict):
        state.leases_active += 1
    return [msg]


def _remember_methods(msg: Any, state: State) -> Any:
    if isinstance(msg, dict) and "id" in msg and "method" in msg:
        state.pending_methods[msg["id"]] = msg["method"]
    return msg


def _confirmed_without_evidence(msg: Message, state: State) -> list[Message]:
    result = msg.get("result")
    if isinstance(result, dict):
        for stop in result.get("stops") or []:
            if stop.get("outcome") == "unsupported":
                stop["outcome"] = "confirmed"
    return [msg]


def _accept_batch(msg: Any, state: State) -> Any:
    return msg[0] if isinstance(msg, list) and msg and isinstance(msg[0], dict) else msg


def _accept_null_id(msg: Any, state: State) -> Any:
    if isinstance(msg, dict) and "method" in msg and ("id" in msg) and (msg["id"] is None or isinstance(msg["id"], (dict, list, bool))):
        msg["id"] = 1_000_000 + len(state.pending_methods)
    return msg


def _accept_nan(msg: Any, state: State) -> Any:
    def scrub(value: Any) -> Any:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return 1
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value

    return scrub(msg)


def _accept_any_version(msg: Any, state: State) -> Any:
    if isinstance(msg, dict) and isinstance(msg.get("params"), dict) and isinstance(msg["params"].get("_meta"), dict):
        if "bhms/protocolVersion" in msg["params"]["_meta"]:
            msg["params"]["_meta"]["bhms/protocolVersion"] = bhms_schema.load_schema()["x-bhms-protocolVersion"]
    return msg


def _no_unit(msg: Message, state: State) -> list[Message]:
    result = msg.get("result")
    if isinstance(result, dict) and isinstance(result.get("observation"), dict):
        result["observation"].pop("unit", None)
    return [msg]


def _ignore_unknown_members(msg: Any, state: State) -> Any:
    schema = bhms_schema.load_schema()
    if isinstance(msg, dict) and msg.get("method") in schema["x-bhms-methods"] and isinstance(msg.get("params"), dict):
        definition = schema["x-bhms-methods"][msg["method"]]["params"].rsplit("/", 1)[-1]
        allowed = set(schema["$defs"][definition].get("properties", {}))
        msg["params"] = {k: v for k, v in msg["params"].items() if k in allowed}
    return msg


def _ignore_unknown_arguments(msg: Any, state: State) -> Any:
    if isinstance(msg, dict) and msg.get("method") == "actions/invoke":
        params = msg["params"]
        known = {member for (action, member) in BOUNDS if action == params.get("action")}
        if known and isinstance(params.get("arguments"), dict):
            params["arguments"] = {k: v for k, v in params["arguments"].items() if k in known}
    return msg


def _terminal_reopens(msg: Message, state: State) -> list[Message]:
    result = msg.get("result")
    if isinstance(result, dict) and isinstance(result.get("operation"), dict):
        op = result["operation"]
        if op.get("state") == "completed":
            if op["operationId"] in state.completed:
                op["state"] = "running"
                op.pop("result", None)
            state.completed.add(op["operationId"])
    return [msg]


def _replayed_always_false(msg: Message, state: State) -> list[Message]:
    result = msg.get("result")
    if isinstance(result, dict) and "replayed" in result:
        result["replayed"] = False
    return [msg]


def _chain(*functions: Callable[[Message, State], list[Message]]) -> Callable[[Message, State], list[Message]]:
    def run(msg: Message, state: State) -> list[Message]:
        out = [msg]
        for function in functions:
            out = [m for item in out for m in function(item, state)]
        return out

    return run


def _lease_not_enforced(server: Any) -> None:
    from bhms.protocol.errors import BhmsError
    from bhms.runtime.leases import Lease

    original = server.leases.check

    def lenient(principal: Any, lease_id: str | None, resources: Any) -> Any:
        try:
            return original(principal, lease_id, resources)
        except BhmsError as exc:
            if exc.code in ("LEASE_REQUIRED", "LEASE_EXPIRED", "LEASE_CONFLICT", "FENCED"):
                return Lease(lease_id=lease_id or "lease-none", principal=principal.id, resources=tuple(resources), fence=1,
                             state="active", acquired_ns=0, ttl_ms=1, expires_mono=float("inf"), expires_ns=0)
            raise

    server.leases.check = lenient


DEFECTS: dict[str, Defect] = {d.name: d for d in (
    Defect("clamp-instead-of-refuse", "out-of-range arguments are clamped to the bound and executed",
           ("arguments.vectors-refusals", "arguments.refusals-from-description"), ("BHMS-DEV-044", "BHMS-OPS-040"), incoming=_clamp),
    Defect("key-reuse-across-requests", "a key reused for a different request returns the first operation instead of KEY_CONFLICT",
           ("operations.idempotency",), ("BHMS-OPS-031",), incoming=_reuse_key),
    Defect("replayed-always-false", "a replayed operation is reported as a new one",
           ("operations.idempotency", "operations.concurrent-same-key"), ("BHMS-OPS-030", "BHMS-OPS-032"), outgoing=_replayed_always_false),
    Defect("completed-without-evidence", "an unverifiable effect is reported completed and verified with no evidence",
           ("operations.require-verified", "observers.all-traffic"), ("BHMS-OPS-007", "BHMS-OPS-006"), outgoing=_unverified_completes),
    Defect("no-result-type", "properties/read results omit resultType", ("observers.all-traffic",), ("BHMS-LIF-012",),
           outgoing=_drop_result_type, drive=("observations.read-semantics",)),
    Defect("unrequested-notifications", "a subscription also delivers notification types it did not ask for",
           ("lifecycle.subscription-stream",), ("BHMS-LIF-041",), outgoing=_extra_notification),
    Defect("lease-not-enforced", "a lease-requiring action runs without a valid lease",
           ("leases.enforcement-at-admission",), ("BHMS-LSE-010",), patch=_lease_not_enforced),
    Defect("stale-served-as-fresh", "fresh and maxAgeMs are ignored: the retained sample is returned",
           ("observations.read-semantics", "observations.retained-after-effect"), ("BHMS-OBS-004", "BHMS-OBS-006"), incoming=_stale_as_fresh),
    Defect("wrong-description-digest", "the description digest is not the digest of the description",
           ("descriptions.digest-and-immutability",), ("BHMS-DEV-021",), outgoing=_bad_digest),
    Defect("wrong-error-number", "OUT_OF_RANGE is sent with another JSON-RPC code",
           ("observers.all-traffic",), ("BHMS-ERR-010",), outgoing=_wrong_error_number, drive=("arguments.vectors-refusals",)),
    Defect("no-may-have-acted", "error data omits mayHaveActed",
           ("arguments.vectors-refusals", "observers.all-traffic"), ("BHMS-ERR-001",), outgoing=_no_may_have_acted, drive=("arguments.vectors-refusals",)),
    Defect("fabricated-cursor-accepted", "a cursor the server never minted is silently ignored",
           ("lifecycle.cursors-and-ordering",), ("BHMS-LIF-060",), incoming=_accept_fabricated_cursor),
    Defect("stop-waits-for-leases", "stop is held back while a lease is active",
           ("stop.not-blocked-by-load",), ("BHMS-AUTH-020",), incoming=_remember_methods, outgoing=_track_leases, delay_stop_s=3.0),
    Defect("confirmed-without-evidence", "stop reports confirmed for a device with no stop procedure",
           ("observers.all-traffic", "stop.semantics"), ("BHMS-AUTH-022",), outgoing=_confirmed_without_evidence),
    Defect("batch-accepted", "a JSON-RPC batch is processed instead of rejected",
           ("transport.batch-rejected",), ("BHMS-TRN-002",), incoming=_accept_batch),
    Defect("null-id-accepted", "a request with a null or non-scalar id is accepted",
           ("lifecycle.request-id-rules",), ("BHMS-LIF-010",), incoming=_accept_null_id),
    Defect("nan-accepted", "NaN and Infinity tokens are accepted as numbers",
           ("lifecycle.nan-tokens",), ("BHMS-LIF-001",), incoming=_accept_nan),
    Defect("any-version-accepted", "an unserved protocolVersion is served instead of UNSUPPORTED_VERSION",
           ("lifecycle.version-negotiation",), ("BHMS-LIF-019",), incoming=_accept_any_version),
    Defect("observation-without-unit", "numeric observations carry no unit",
           ("observations.read-semantics", "observers.all-traffic"), ("BHMS-OBS-005",), outgoing=_no_unit, drive=("observations.read-semantics",)),
    Defect("unknown-members-ignored", "undeclared params members are ignored instead of refused",
           ("lifecycle.closed-params",), ("BHMS-LIF-015",), incoming=_ignore_unknown_members),
    Defect("unknown-arguments-ignored", "undeclared action arguments are ignored instead of refused (authority claims slip through)",
           ("arguments.vectors-refusals", "arguments.refusals-from-description"), ("BHMS-DEV-044", "BHMS-SEC-030"),
           incoming=_ignore_unknown_arguments),
    Defect("terminal-reopens", "a completed operation is later reported running",
           ("observers.all-traffic", "operations.completion-evidence"), ("BHMS-OPS-002",), outgoing=_terminal_reopens),
)}


# ---------------------------------------------------------------------- the wrapper


class Mutator(Transport):
    """Server-side transport whose messages pass through a :class:`Defect`."""

    def __init__(self, inner: Transport, defect: Defect) -> None:
        self.inner, self.defect, self.state = inner, defect, State()
        self.peer, self.max_message_bytes = inner.peer, inner.max_message_bytes
        self._queue: list[bytes] = []

    async def receive(self) -> bytes:
        while True:
            data = await self.inner.receive()
            try:
                msg: Any = json.loads(data)
            except ValueError:
                return data
            if self.defect.incoming is not None:
                msg = self.defect.incoming(msg, self.state)
                data = json.dumps(msg).encode()
            if self.defect.delay_stop_s and isinstance(msg, dict) and msg.get("method") == "stop" and self.state.leases_active:
                await asyncio.sleep(self.defect.delay_stop_s)
            return data

    async def send(self, data: bytes) -> None:
        try:
            msg = json.loads(data)
        except ValueError:
            await self.inner.send(data)
            return
        if self.defect.outgoing is None or not isinstance(msg, dict):
            await self.inner.send(data)
            return
        for item in self.defect.outgoing(msg, self.state):
            await self.inner.send(json.dumps(item).encode())

    async def close(self) -> None:
        await self.inner.close()

    def abort(self) -> None:
        self.inner.abort()


async def serve(defect: Defect) -> None:
    """Serve the conformance device over stdio with ``defect`` applied."""
    from bhms.transport.stdio import stdio_server_transport

    server, _ = conformance_device.build(memory=True)
    await server.start()
    if defect.patch is not None:
        defect.patch(server)
    try:
        assert server.rpc is not None
        await server.rpc.handle_connection(Mutator(await stdio_server_transport(), defect))
    except TransportClosed:
        pass
    finally:
        await server.close()


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "--list"):
        for defect in DEFECTS.values():
            print(f"{defect.name:32} {defect.description}  [fails: {', '.join(defect.requirements)}]")
        return
    if args[0] not in DEFECTS:
        raise SystemExit(f"unknown defect {args[0]!r}; --list shows them")
    asyncio.run(serve(DEFECTS[args[0]]))


if __name__ == "__main__":
    main()
