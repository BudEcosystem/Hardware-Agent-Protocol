"""OPC UA adapter: an OPC UA server described by a node profile becomes a BHMS device (asyncua client).

``OpcUaProfile`` lists the variables to expose as properties and the methods to expose as actions. Variables are read with
the OPC UA Read service (a bad status code or an unreachable server is an *invalid* observation, never a stale value
passed off as current); methods are called with the Call service.

A method that follows the common ``(Ok, Message)`` convention is treated as an interlock: ``Ok = false`` proves the unit
refused the command before acting, so the action fails with effect ``none`` (``mayHaveActed`` false). A bad service status
that names a malformed or unsupported request proves the same; any other failure after the call left (a communication
status, a timeout, a dropped session) leaves the operation ``unknown``, and the ``confirm`` variable named by the profile is
read back to resolve it: when the profile's predicate holds, the operation is reconciled as completed (effect unverified,
because the variable is the unit's own report).

Completion evidence is ``reported`` for every method: OPC UA methods return when the unit has *accepted* the call, which is
not evidence about the physical result. Measured properties (a tachometer) are available separately for the agent to check.

Thread-safety: one event loop; one session per adapter.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from asyncua import Client, ua
from asyncua.ua.uaerrors import UaStatusCodeError

from bhms.server.context import Reconciled
from bhms.server.decorators import Range
from bhms.server.server import DeviceServer
from simlab.adapters.common import Refused, next_token, Unreachable, declare_action, declare_property, refusal_fault
from simlab.simdevice import CommandLog, make_server, simulated_device
from simlab.world import World

REFUSING_STATUS = {ua.StatusCodes.BadInvalidArgument, ua.StatusCodes.BadMethodInvalid, ua.StatusCodes.BadNotImplemented,
                   ua.StatusCodes.BadUserAccessDenied, ua.StatusCodes.BadArgumentsMissing,
                   ua.StatusCodes.BadTooManyArguments, ua.StatusCodes.BadNodeIdUnknown}


@dataclass(frozen=True)
class Variable:
    name: str
    path: tuple[str, ...]  # browse names below Objects, e.g. ("Centrifuge", "Speed")
    description: str
    kind: str = "number"  # "number" | "boolean" | "string"
    unit: str | None = None
    evidence: str = "reported"
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class Argument:
    name: str
    unit: str
    minimum: float
    maximum: float


@dataclass(frozen=True)
class Method:
    name: str  # the BHMS action name
    object_path: tuple[str, ...]
    method: str  # browse name of the OPC UA method
    description: str
    arguments: tuple[Argument, ...] = ()
    effect: str = "reversible"
    idempotency: str = "absolute"
    max_duration_ms: int = 10_000
    confirm: tuple[str, Callable[[Any, dict[str, Any]], bool]] | None = None  # (variable name, predicate)
    requires_lease: bool = False  # must be True for effect "hazardous" (BHMS-DEV-033); the adapter declares it

    def __post_init__(self) -> None:
        if self.effect == "hazardous" and not self.requires_lease:
            raise ValueError(f"OPC UA method {self.name!r}: a hazardous method must set requires_lease=True (BHMS-DEV-033)")


@dataclass(frozen=True)
class OpcUaProfile:
    device_id: str
    name: str
    description: str
    capabilities: tuple[str, ...]
    namespace_uri: str
    variables: tuple[Variable, ...]
    methods: tuple[Method, ...] = field(default_factory=tuple)
    safety_summary: str | None = None
    tag_method: tuple[tuple[str, ...], str] | None = None  # (object path, method name) that takes the command token


class OpcUaLink:
    """An asyncua session with failures classified for the honesty rules in the module docstring."""

    def __init__(self, endpoint: str, namespace_uri: str, timeout_s: float = 2.0) -> None:
        self._client = Client(endpoint, timeout=timeout_s)
        self._namespace_uri = namespace_uri
        self._index: int | None = None
        self._lock = asyncio.Lock()
        self._connected = False
        self.tokens: list[int] = []  # one token per command sent, delivered in-band (see instruments/journal.py)
        self.tag_method: tuple[tuple[str, ...], str] | None = None
        self.log: CommandLog | None = None

    async def close(self) -> None:
        if self._connected:
            await self._client.disconnect()
            self._connected = False

    async def _ensure(self) -> None:
        if self._connected:
            return
        try:
            await self._client.connect()
            self._index = await self._client.get_namespace_index(self._namespace_uri)
        except (OSError, asyncio.TimeoutError, UaStatusCodeError, ua.UaError) as exc:
            raise Unreachable(f"cannot open an OPC UA session: {exc}") from exc
        self._connected = True

    def _drop(self) -> None:
        self._connected = False

    async def _node(self, path: tuple[str, ...]) -> Any:
        assert self._index is not None
        return await self._client.nodes.objects.get_child([f"{self._index}:{part}" for part in path])

    async def read(self, variable: Variable) -> Any:
        async with self._lock:
            await self._ensure()
            try:
                node = await self._node(variable.path)
                return await node.read_value()
            except (OSError, asyncio.TimeoutError, UaStatusCodeError, ua.UaError) as exc:
                self._drop()
                raise RuntimeError(f"OPC UA read of {variable.name} failed: {exc}") from exc

    async def call(self, method: Method, args: list[Any]) -> Any:
        async with self._lock:
            await self._ensure()
            try:
                parent = await self._node(method.object_path)
                assert self._index is not None
                if self.tag_method is not None:
                    token = next_token()
                    self.tokens.append(token)
                    tagger = await self._node(self.tag_method[0])
                    await tagger.call_method(f"{self._index}:{self.tag_method[1]}", float(token))
                return await parent.call_method(f"{self._index}:{method.method}", *args)
            except UaStatusCodeError as exc:
                if exc.code in REFUSING_STATUS:
                    raise Refused(f"status {exc}") from exc
                self._drop()
                raise RuntimeError(f"OPC UA call {method.method} failed after it was sent: {exc}") from exc
            except (OSError, asyncio.TimeoutError, ua.UaError) as exc:
                self._drop()
                raise RuntimeError(f"OPC UA call {method.method} failed after it was sent: {exc}") from exc


def build_server(world: World, profile: OpcUaProfile, endpoint: str, *, state_dir: str | Path | None,
                 durability: str = "process", name: str = "simlab-opcua-adapter", timeout_s: float = 2.0,
                 **kw: Any) -> tuple[DeviceServer, OpcUaLink]:
    """The BHMS server for an OPC UA server. The adapter never reads the world; it knows only what the server says."""
    srv = make_server(world, name, state_dir=state_dir, durability=durability,
                      title=f"OPC UA adapter: {profile.name}", **kw)
    dev = simulated_device(srv, profile.device_id, name=profile.name, description=profile.description,
                     capabilities=list(profile.capabilities), resources=[f"{profile.device_id}/program"],
                     tags=["simlab", "adapter", "opcua"], safety_summary=profile.safety_summary,
                     identity={"manufacturer": "OPC UA server", "model": profile.name, "firmwareVersion": "unknown"})
    link = OpcUaLink(endpoint, profile.namespace_uri, timeout_s)
    link.tag_method = profile.tag_method
    log = link.log = CommandLog()
    variables = {v.name: v for v in profile.variables}
    resource = f"{profile.device_id}/program"

    def reader(variable: Variable) -> Any:
        async def read_value() -> Any:
            value = await link.read(variable)
            if value is None:
                raise RuntimeError(f"{variable.name}: the server returned no value")
            return value
        return read_value

    def schema_of(variable: Variable) -> Any:
        return {"boolean": bool, "string": str}.get(variable.kind) or Range(variable.minimum, variable.maximum,
                                                                            unit=variable.unit or "1")

    for variable in profile.variables:
        declare_property(dev, variable.name, reader(variable), schema_of(variable), evidence=variable.evidence,
                         description=f"{variable.description} (OPC UA {'/'.join(variable.path)})")

    def caller(method: Method) -> Any:
        async def call(ctx: Any, **arguments: Any) -> Any:
            log.begin(ctx.operation_id)
            first = len(link.tokens)
            try:
                result = await link.call(method, [float(arguments[a.name]) for a in method.arguments])
            except (Refused, Unreachable) as exc:
                raise refusal_fault(exc, "OPC UA") from exc
            finally:
                log.sent[ctx.operation_id] = link.tokens[first:]
            ok, message = (result if isinstance(result, (list, tuple)) else (True, str(result)))
            if not ok:
                raise refusal_fault(Refused(str(message)), "OPC UA")
            return log.end(ctx.operation_id, {"message": str(message)})
        return call

    for method in profile.methods:
        declare_action(dev, method.name, caller(method), description=method.description,
                       params={a.name: Range(a.minimum, a.maximum, unit=a.unit) for a in method.arguments},
                       returns={"message": str}, effect=method.effect, idempotency=method.idempotency,
                       completion_evidence="reported", max_duration_ms=method.max_duration_ms, resources=[resource],
                       requires_lease=method.requires_lease)

    @dev.reconcile
    async def reconcile(op: dict[str, Any]) -> Reconciled | None:
        method = next((m for m in profile.methods if m.name == op.get("action")), None)
        if method is None or method.confirm is None:
            return None
        variable_name, predicate = method.confirm
        try:
            value = await link.read(variables[variable_name])
        except (RuntimeError, Unreachable):
            return None
        if predicate(value, op.get("arguments", {})):
            return Reconciled("completed", evidence=f"read back {variable_name} = {value!r}",
                              result={"message": "confirmed by read-back"}, effect="unverified")
        return None

    @dev.liveness
    async def alive() -> bool:
        try:
            await link.read(profile.variables[0])
        except (RuntimeError, Unreachable):
            return False
        return True

    return srv, link
