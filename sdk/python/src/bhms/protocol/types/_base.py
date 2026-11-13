"""Wire base classes, primitive definitions, _meta, errors and generic JSON-RPC envelopes."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, ClassVar, Literal, Optional, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, model_validator
from pydantic.alias_generators import to_camel

from bhms.protocol.errors import CODES, OPERATION_ONLY_CODES, RETRY_VALUES


# --------------------------------------------------------------------------- base


class _Wire(BaseModel):
    """Closed, strict wire object with camelCase aliases and null discipline."""

    model_config = ConfigDict(strict=True, extra="forbid", populate_by_name=True, alias_generator=to_camel,
                              regex_engine="python-re")

    # Aliases whose value may be JSON null (in addition to members typed ``Any``).
    _NULLABLE: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="before")
    @classmethod
    def _reject_null(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        by_alias = _alias_index(cls)
        for key, value in data.items():
            if value is not None or key in cls._NULLABLE:
                continue
            field_name = by_alias.get(key)
            if field_name is None:
                continue  # unknown member: extra="forbid" reports it
            if cls.model_fields[field_name].annotation is Any:
                continue
            raise ValueError(f"{key} must not be null; omit it instead")
        return data


@lru_cache(maxsize=None)
def _alias_index(cls: type[BaseModel]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, info in cls.model_fields.items():
        out[info.alias or name] = name
        out[name] = name
    return out


class _Plain(_Wire):
    """Wire object whose member names are used verbatim (no camelCase aliasing)."""

    model_config = ConfigDict(strict=True, extra="forbid", populate_by_name=True, alias_generator=None,
                              regex_engine="python-re")


def to_wire(value: Any) -> Any:
    """Serialize a model (or any value containing models) to its JSON wire form."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return TypeAdapter(Any).dump_python(value, mode="json", by_alias=True, exclude_unset=True)


def _pattern(pattern: str, **kw: Any) -> Any:
    return Annotated[str, StringConstraints(pattern=pattern, **kw)]


def _bounded_int(ge: int | None = None, le: int | None = None) -> Any:
    return Annotated[int, Field(ge=ge, le=le)]


def _text(max_length: int, min_length: int = 0) -> Any:
    return Annotated[str, StringConstraints(min_length=min_length, max_length=max_length)]


# --------------------------------------------------------------------------- primitives

RequestId = Union[str, int]
ProtocolVersion = _pattern(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
Time = _pattern(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,9})?Z$")
Digest = _pattern(r"^sha256:[0-9a-f]{64}$")
DeviceId = _pattern(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
ResourceId = _pattern(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
Name = _pattern(r"^[a-z][a-z0-9_]{0,63}$")
EventType = _pattern(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$", max_length=64)
CapabilityId = _pattern(r"^[a-z][a-z0-9-]*(\.[a-z0-9-]+)+$", max_length=128)
Tag = _text(64, 1)
OperationKey = _pattern(r"^[A-Za-z0-9._:~-]{1,128}$")
ClientOperationKey = _pattern(r"^(?!d-)[A-Za-z0-9._:~-]{1,128}$")  # d- reserved (BHMS-OPS-037)
AgentOperationKey = _pattern(r"^(?![dg]-)[A-Za-z0-9._:~-]{1,128}$")  # d-, g- reserved for servers
Cursor = _text(512, 1)
ServerId = _text(128, 1)
VariableName = _pattern(r"^[a-z_][A-Za-z0-9_]{0,63}$")
Reference = _pattern(r"^\$\{[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+|\[[0-9]+\])*\}$")
ExtensionKey = _pattern(r"^(?!bhms/)[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)*/[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")
Extensions = dict[ExtensionKey, dict[str, Any]]
JsonSchema = Union[dict[str, Any], bool]
ResultType = Literal["complete"]
Scope = _pattern(r"^(read|lease|stop|admin|programs:run|programs:register|invoke:.+|stop:.+)$")
NonNegInt = _bounded_int(ge=0)
PosInt = _bounded_int(ge=1)
PositiveNumber = Annotated[float, Field(gt=0)]


def _check_numeric_unit(value: Any) -> Any:
    """BHMS-DEV-041: a schema of type number/integer carries x-bhms-unit (schema def NumericUnitRule)."""
    if isinstance(value, dict) and value.get("type") in ("number", "integer"):
        unit = value.get("x-bhms-unit")
        if not isinstance(unit, str) or not unit:
            raise ValueError('a number or integer schema must carry "x-bhms-unit" (use "1" for dimensionless)')
    return value


NumericUnitRule = Annotated[Any, AfterValidator(_check_numeric_unit)]


def _check_object_schema(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("type") != "object" or value.get("additionalProperties") is not False:
        raise ValueError('must be a closed object schema: {"type": "object", "additionalProperties": false, ...}')
    members = value.get("properties", {})
    if not isinstance(members, dict):
        raise ValueError("properties must be an object")
    for name, member in members.items():
        try:
            _check_numeric_unit(member)
        except ValueError as exc:
            raise ValueError(f"member {name!r}: {exc}") from None
    return value


ObjectSchema = Annotated[dict[str, Any], AfterValidator(_check_object_schema)]

BhmsErrorCode = Literal[tuple(CODES)]  # type: ignore[valid-type]  # single source: bhms.protocol.errors
RetryClass = Literal[tuple(RETRY_VALUES)]  # type: ignore[valid-type]
DeviceStatus = Literal["online", "offline", "degraded", "unknown"]
EffectClass = Literal["none", "reversible", "irreversible", "hazardous"]
Idempotency = Literal["idempotent", "absolute", "relative", "toggle"]
EvidenceKind = Literal["measured", "reported", "commanded", "estimated", "simulated"]
CompletionEvidence = Literal["measured", "reported", "none"]
CompactType = Literal["u8", "i8", "u16", "i16", "u32", "i32", "f32", "bool"]
Quality = Literal["valid", "stale", "invalid", "unknown"]
OperationState = Literal["accepted", "dispatching", "running", "completed", "failed", "canceled", "rejected",
                         "unknown"]
CancelState = Literal["none", "requested", "acknowledged", "refused", "confirmed"]
EffectCertainty = Literal["none", "verified", "unverified", "unknown"]

TERMINAL_STATES: frozenset[str] = frozenset({"completed", "failed", "canceled", "rejected"})
SETTLED_STATES: frozenset[str] = TERMINAL_STATES | {"unknown"}

# --------------------------------------------------------------------------- _meta


def _check_meta_keys(extra: dict[str, Any] | None, allowed: tuple[str, ...]) -> None:
    for key in extra or {}:
        if key.startswith("bhms/") and key not in allowed:
            allowed_text = ", ".join(allowed) if allowed else "the declared members"
            raise ValueError(f"_meta key {key!r} uses the reserved bhms/ prefix; only {allowed_text} may use it")
        if not key:
            raise ValueError("_meta keys must not be empty")


class Implementation(_Wire):
    name: _text(128, 1)
    version: _text(64, 1)
    title: Optional[_text(200)] = None


class ClientCapabilities(_Wire):
    extensions: Optional[Extensions] = None


class RequestMeta(_Wire):
    """Per-request ``_meta``; extra keys must use a non-``bhms/`` prefix."""

    model_config = ConfigDict(extra="allow")
    protocol_version: ProtocolVersion = Field(alias="bhms/protocolVersion")
    client_info: Optional[Implementation] = Field(None, alias="bhms/clientInfo")
    client_capabilities: Optional[ClientCapabilities] = Field(None, alias="bhms/clientCapabilities")
    traceparent: Optional[_text(256)] = Field(None, alias="traceparent")
    tracestate: Optional[_text(512)] = Field(None, alias="tracestate")

    @model_validator(mode="after")
    def _keys(self) -> RequestMeta:
        _check_meta_keys(self.model_extra, ())
        return self


class ResultMeta(_Wire):
    model_config = ConfigDict(extra="allow")
    server_info: Optional[Implementation] = Field(None, alias="bhms/serverInfo")
    subscription_id: Optional[RequestId] = Field(None, alias="bhms/subscriptionId")

    @model_validator(mode="after")
    def _keys(self) -> ResultMeta:
        _check_meta_keys(self.model_extra, ())
        return self


class SubscriptionMeta(_Wire):
    model_config = ConfigDict(extra="allow")
    subscription_id: RequestId = Field(alias="bhms/subscriptionId")

    @model_validator(mode="after")
    def _keys(self) -> SubscriptionMeta:
        _check_meta_keys(self.model_extra, ())
        return self


class NotificationMeta(_Wire):
    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def _keys(self) -> NotificationMeta:
        _check_meta_keys(self.model_extra, ())
        return self


class _Params(_Wire):
    meta: RequestMeta = Field(alias="_meta")


class _Result(_Wire):
    result_type: ResultType
    meta: Optional[ResultMeta] = Field(None, alias="_meta")


# --------------------------------------------------------------------------- errors


class ErrorData(_Wire):
    bhms_code: BhmsErrorCode
    field: Optional[_text(512)] = None
    bound: Any = None
    operation_id: Optional[ServerId] = None
    may_have_acted: bool
    retry: RetryClass
    hint: _text(2000)


class OperationError(_Wire):
    bhms_code: BhmsErrorCode
    message: _text(2000)
    field: Optional[_text(512)] = None
    bound: Any = None
    operation_id: Optional[ServerId] = None
    may_have_acted: bool
    retry: RetryClass
    hint: _text(2000)


_BHMS_NUMBERS = frozenset(spec.number for spec in CODES.values())


class ErrorObject(_Wire):
    code: int
    message: _text(2000)
    data: Any = None

    @model_validator(mode="after")
    def _bhms_data(self) -> ErrorObject:
        if self.code in _BHMS_NUMBERS:
            if "data" not in self.model_fields_set:
                raise ValueError(f"error code {self.code} is a BHMS code and requires data with bhmsCode")
            data = ErrorData.model_validate(self.data)
            if CODES[data.bhms_code].number != self.code:
                raise ValueError(f"{data.bhms_code} must use code {CODES[data.bhms_code].number}, not {self.code}")
            if data.bhms_code in OPERATION_ONLY_CODES:
                raise ValueError(f"{data.bhms_code} describes admitted work; report it in the operation's error")
            self.data = data
        elif isinstance(self.data, dict) and "bhmsCode" in self.data:
            raise ValueError(f"code {self.code} is not a BHMS code; data must not carry bhmsCode")
        return self


# --------------------------------------------------------------------------- generic envelopes


class _Envelope(_Plain):
    jsonrpc: Literal["2.0"]


class JSONRPCRequest(_Envelope):
    id: RequestId
    method: _text(1 << 16, 1)
    params: dict[str, Any]


class JSONRPCNotification(_Envelope):
    method: _text(1 << 16, 1)
    params: Optional[dict[str, Any]] = None


class _ResultBody(_Wire):
    model_config = ConfigDict(extra="allow")
    result_type: ResultType


class JSONRPCResultResponse(_Envelope):
    id: RequestId
    result: _ResultBody


class JSONRPCErrorResponse(_Envelope):
    _NULLABLE = frozenset({"id"})
    id: Optional[RequestId]
    error: ErrorObject
