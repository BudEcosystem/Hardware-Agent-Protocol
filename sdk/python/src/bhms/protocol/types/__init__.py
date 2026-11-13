"""Pydantic v2 models for every definition in ``spec/bhms/schema/bhms.schema.json``.

The JSON Schema is the contract; these models mirror it one-to-one (checked by
``tests/test_schema_examples.py``: same members, same required set, every
example round-trips and every invalid example is rejected).

Wire conventions:

* Attributes are snake_case; the wire uses camelCase aliases (``device_id`` ↔
  ``deviceId``) except where the schema says otherwise (``_meta``,
  ``bhms/protocolVersion``, snake_case agent-tool inputs).
* Models are strict and closed (``extra="forbid"``) wherever the schema is.
* Optional members default to ``None`` and are omitted on output: serialize with
  :func:`to_wire` (``by_alias=True, exclude_unset=True``), never with a plain
  ``model_dump()``. An explicit JSON ``null`` is accepted only where the schema
  allows it.

The models are split by area — ``_base`` (wire base, primitives, ``_meta``,
errors, envelopes), ``devices``, ``operations`` and ``programs`` — and all are
re-exported here, so ``from bhms.protocol.types import Operation`` is the API.

``DEFS`` maps every schema ``$defs`` name to its Python type; :func:`adapter`
returns a cached ``TypeAdapter`` for any of them. ``METHODS`` and
``NOTIFICATIONS`` describe the method and notification tables.

Thread-safety: models are immutable in practice (no validate_assignment); the
adapter cache is filled under the GIL with idempotent values.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel, TypeAdapter, create_model

from bhms.protocol.types._base import *  # noqa: F401,F403
from bhms.protocol.types._base import SETTLED_STATES, TERMINAL_STATES, RequestId, _Envelope, to_wire  # noqa: F401
from bhms.protocol.types.devices import *  # noqa: F401,F403
from bhms.protocol.types.operations import *  # noqa: F401,F403
from bhms.protocol.types.programs import *  # noqa: F401,F403

# --------------------------------------------------------------------------- method and notification tables


class MethodSpec(NamedTuple):
    params: type[BaseModel]
    result: type[BaseModel]
    request: type[BaseModel]
    response: type[BaseModel]
    tier: str
    capability: str | None


class NotificationSpec(NamedTuple):
    params: type[BaseModel]
    notification: type[BaseModel]
    direction: str


_METHOD_TABLE: tuple[tuple[str, str, str, str | None], ...] = (
    ("server/discover", "Discover", "core", None),
    ("devices/list", "DevicesList", "core", None),
    ("devices/describe", "DevicesDescribe", "core", None),
    ("properties/read", "PropertiesRead", "core", None),
    ("actions/invoke", "ActionsInvoke", "core", None),
    ("operations/get", "OperationsGet", "core", None),
    ("operations/wait", "OperationsWait", "core", None),
    ("operations/list", "OperationsList", "core", None),
    ("operations/cancel", "OperationsCancel", "core", None),
    ("stop", "Stop", "core", None),
    ("subscriptions/listen", "SubscriptionsListen", "core", None),
    ("leases/acquire", "LeasesAcquire", "optional", "leases"),
    ("leases/renew", "LeasesRenew", "optional", "leases"),
    ("leases/release", "LeasesRelease", "optional", "leases"),
    ("events/read", "EventsRead", "optional", "events"),
    ("programs/run", "ProgramsRun", "optional", "programs"),
    ("programs/register", "ProgramsRegister", "optional", "programs.registry"),
    ("programs/get", "ProgramsGet", "optional", "programs.registry"),
    ("programs/list", "ProgramsList", "optional", "programs.registry"),
)

_NOTIFICATION_TABLE: tuple[tuple[str, str, str], ...] = (
    ("notifications/subscriptions/acknowledged", "SubscriptionsAcknowledged", "server-to-client"),
    ("notifications/devices/listChanged", "DevicesListChanged", "server-to-client"),
    ("notifications/operation", "Operation", "server-to-client"),
    ("notifications/observation", "Observation", "server-to-client"),
    ("notifications/event", "Event", "server-to-client"),
    ("notifications/cancelled", "Cancelled", "both"),
)

METHODS: dict[str, MethodSpec] = {}
NOTIFICATIONS: dict[str, NotificationSpec] = {}
DEFS: dict[str, Any] = {}


def _envelope(name: str, **fields: Any) -> type[BaseModel]:
    return create_model(name, __base__=_Envelope, **fields)


for _method, _base, _tier, _cap in _METHOD_TABLE:
    _p, _r = globals()[_base + "Params"], globals()[_base + "Result"]
    _req = _envelope(_base + "Request", id=(RequestId, ...), method=(Literal[_method], ...), params=(_p, ...))
    _resp = _envelope(_base + "Response", id=(RequestId, ...), result=(_r, ...))
    globals()[_req.__name__], globals()[_resp.__name__] = _req, _resp
    METHODS[_method] = MethodSpec(_p, _r, _req, _resp, _tier, _cap)

for _method, _base, _direction in _NOTIFICATION_TABLE:
    _p = globals()[_base + "NotificationParams"]
    _n = _envelope(_base + "Notification", method=(Literal[_method], ...), params=(_p, ...))
    globals()[_n.__name__] = _n
    NOTIFICATIONS[_method] = NotificationSpec(_p, _n, _direction)

_DEF_NAMES = (
    "RequestId", "ProtocolVersion", "Time", "Digest", "DeviceId", "ResourceId", "Name", "EventType", "CapabilityId",
    "Tag", "OperationKey", "Cursor", "ServerId", "VariableName", "Reference", "ExtensionKey", "Extensions",
    "JsonSchema", "ObjectSchema", "Implementation", "ClientCapabilities", "ResultType", "RequestMeta", "ResultMeta",
    "SubscriptionMeta", "NotificationMeta", "BhmsErrorCode", "RetryClass", "ErrorData", "OperationError",
    "ErrorObject", "JSONRPCRequest", "JSONRPCNotification", "JSONRPCResultResponse", "JSONRPCErrorResponse",
    "ProgramLimits", "ServerCapabilities", "Limits", "Scope", "Principal", "DeviceStatus", "EffectClass",
    "Idempotency", "EvidenceKind", "CompletionEvidence", "DeviceSummary", "DevicesListFilter", "CompactType",
    "CompactField", "CompactActionLayout", "CompactValue", "PropertyDescription", "ActionDescription",
    "EventTypeDescription", "SafetyDescription", "DeviceIdentity", "DeviceDescription", "Quality", "Observation",
    "OperationState", "CancelState", "EffectCertainty", "CancelInfo", "OperationEvidence", "Requirement", "Progress",
    "HistoryEntry", "Operation", "DeviceStop", "SubscriptionFilter", "RefusedFilter", "Lease", "Event", "Predicate",
    "InvokeStep", "ReadStep", "WaitUntilStep", "AssertStep", "SleepStep", "RepeatStep", "Step", "Program",
    "ProgramInfo", "ArgumentBound", "PolicyPrincipal", "GatewayPolicy", "AgentFindInput", "AgentDescribeInput",
    "AgentReadInput", "AgentInvokeInput", "AgentOperationInput", "AgentCancelInput", "AgentStopInput",
    "AgentRunProgramInput", "AgentFindData", "AgentFunctionResult",
)
for _name in _DEF_NAMES:
    DEFS[_name] = globals()[_name]
for _method, _base, _tier, _cap in _METHOD_TABLE:
    for _suffix in ("Params", "Result", "Request", "Response"):
        DEFS[_base + _suffix] = globals()[_base + _suffix]
for _method, _base, _direction in _NOTIFICATION_TABLE:
    for _suffix in ("NotificationParams", "Notification"):
        DEFS[_base + _suffix] = globals()[_base + _suffix]


@lru_cache(maxsize=None)
def adapter(def_name: str) -> TypeAdapter[Any]:
    """Return a cached TypeAdapter for schema definition ``def_name`` (KeyError if unknown)."""
    return TypeAdapter(DEFS[def_name])


def parse(def_name: str, message: Any) -> Any:
    """Validate a JSON value as schema definition ``def_name``; raises pydantic.ValidationError."""
    return adapter(def_name).validate_python(message)


def dump(def_name: str, value: Any) -> Any:
    """Serialize a value of schema definition ``def_name`` to its JSON wire form."""
    return adapter(def_name).dump_python(value, mode="json", by_alias=True, exclude_unset=True)
