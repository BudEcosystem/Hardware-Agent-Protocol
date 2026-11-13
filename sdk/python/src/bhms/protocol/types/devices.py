"""Discovery, device descriptions and observations (03-lifecycle.md, 04-devices.md, 05-observations.md)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import AfterValidator, Field, model_validator

from bhms.protocol.types._base import (
    CapabilityId, CompactType, CompletionEvidence, Cursor, DeviceId, DeviceStatus, Digest, EffectClass, EventType,
    EvidenceKind, Extensions, Idempotency, Implementation, JsonSchema, Name, NonNegInt, ObjectSchema, PositiveNumber,
    PosInt, ProtocolVersion, Quality, ResourceId, Scope, Tag, Time, _bounded_int, _check_numeric_unit, _Params,
    _pattern, _Result, _text, _Wire,
)


# --------------------------------------------------------------------------- discovery


class ProgramLimits(_Wire):
    max_steps: _bounded_int(1, 256)
    max_repeat: _bounded_int(1, 1000)
    max_depth: _bounded_int(1, 4)
    max_executed_steps: _bounded_int(1, 4096)
    max_variables: _bounded_int(1, 64)
    max_program_bytes: _bounded_int(1024, 65536)
    max_duration_ms: _bounded_int(1, 86_400_000)


class DevicesCapability(_Wire):
    list_changed: bool


class ObservationsCapability(_Wire):
    subscribe: bool
    min_interval_ms: NonNegInt


class OperationsCapability(_Wire):
    durable: bool
    cancel: bool
    key_retention_s: NonNegInt


class StopCapability(_Wire):
    pass


class SubscriptionsCapability(_Wire):
    max_observations: NonNegInt
    max_operation_ids: NonNegInt


class LeasesCapability(_Wire):
    min_ttl_ms: PosInt
    max_ttl_ms: PosInt
    max_wait_ms: NonNegInt


class EventsCapability(_Wire):
    retention_s: NonNegInt
    max_page_size: PosInt


class ProgramsCapability(_Wire):
    registry: bool
    limits: ProgramLimits


class CompactCapability(_Wire):
    links: NonNegInt


class GatewayCapability(_Wire):
    cross_device_leases: bool
    upstreams: NonNegInt


class AuthorityCapability(_Wire):
    principals: PosInt


class ServerCapabilities(_Wire):
    devices: Optional[DevicesCapability] = None
    observations: Optional[ObservationsCapability] = None
    operations: OperationsCapability
    stop: StopCapability
    subscriptions: SubscriptionsCapability
    leases: Optional[LeasesCapability] = None
    events: Optional[EventsCapability] = None
    programs: Optional[ProgramsCapability] = None
    compact: Optional[CompactCapability] = None
    gateway: Optional[GatewayCapability] = None
    authority: Optional[AuthorityCapability] = None
    extensions: Optional[Extensions] = None


class Limits(_Wire):
    max_message_bytes: _bounded_int(ge=1_048_576)
    max_page_size: PosInt
    max_wait_ms: NonNegInt


class Principal(_Wire):
    id: _text(128, 1)
    scopes: list[Scope]


class DiscoverParams(_Params):
    pass


class DiscoverResult(_Result):
    supported_versions: Annotated[list[ProtocolVersion], Field(min_length=1)]
    server_info: Implementation
    capabilities: ServerCapabilities
    epoch: _text(128, 1)
    limits: Limits
    instructions: Optional[_text(8000)] = None
    principal: Optional[Principal] = None


# --------------------------------------------------------------------------- devices


class DeviceSummary(_Wire):
    device_id: DeviceId
    name: _text(80, 1)
    summary: _text(280)
    capabilities: list[CapabilityId]
    tags: list[Tag]
    status: DeviceStatus
    digest: Digest
    actions: list[Name]
    properties: list[Name]


class DevicesListFilter(_Wire):
    capability: Optional[_pattern(r"^[a-z][a-z0-9-]*(\.[a-z0-9-]+)*(\.\*)?$", max_length=128)] = None
    tag: Optional[Tag] = None
    text: Optional[_text(200, 1)] = None
    status: Optional[DeviceStatus] = None


class DevicesListParams(_Params):
    filter: Optional[DevicesListFilter] = None
    cursor: Optional[Cursor] = None
    limit: Optional[_bounded_int(1, 1000)] = None


class DevicesListResult(_Result):
    devices: list[DeviceSummary]
    next_cursor: Optional[Cursor] = None


class CompactField(_Wire):
    name: Name
    type: CompactType
    scale: Optional[PositiveNumber] = None


class CompactActionLayout(_Wire):
    index: _bounded_int(0, 255)
    args: list[CompactField]
    result: list[CompactField]


class CompactValue(_Wire):
    index: _bounded_int(0, 255)
    type: CompactType
    scale: Optional[PositiveNumber] = None


class PropertyDescription(_Wire):
    description: _text(1000)
    schema_: Annotated[JsonSchema, AfterValidator(_check_numeric_unit)] = Field(alias="schema")
    evidence: EvidenceKind
    observable: bool
    max_rate_hz: Optional[PositiveNumber] = None
    read_effect: Literal["none", "transaction"]
    requires_lease: Optional[bool] = None
    resources: Optional[list[ResourceId]] = None
    compact: Optional[CompactValue] = None


class FreshnessRequirement(_Wire):
    property: Name
    max_age_ms: NonNegInt


class ActionDescription(_Wire):
    description: _text(1000)
    input: ObjectSchema
    output: Optional[JsonSchema] = None
    effect: EffectClass
    idempotency: Idempotency
    cancel: Literal["supported", "unsupported"]
    completion_evidence: CompletionEvidence
    verified_by: Optional[list[Name]] = None
    typical_duration_ms: Optional[NonNegInt] = None
    max_duration_ms: PosInt
    requires_lease: bool
    resources: list[ResourceId]
    on_lease_loss: Optional[Literal["finish", "cancel", "hold"]] = None
    requires_fresh: Optional[Annotated[list[FreshnessRequirement], Field(max_length=16)]] = None
    preconditions: Optional[_text(500)] = None
    compact: Optional[CompactActionLayout] = None


class EventTypeDescription(_Wire):
    description: _text(1000)
    data: Optional[JsonSchema] = None


class SafetyDescription(_Wire):
    stop: Literal["supported", "unsupported"]
    stop_evidence: CompletionEvidence
    stop_max_duration_ms: Optional[NonNegInt] = None
    on_disconnect: Literal["continue", "hold", "stop", "unknown"]
    summary: _text(1000)


class DeviceIdentity(_Wire):
    manufacturer: Optional[_text(128)] = None
    model: Optional[_text(128)] = None
    serial_number: Optional[_text(128)] = None
    hardware_revision: Optional[_text(128)] = None
    firmware_version: Optional[_text(128)] = None


class DeviceDescription(_Wire):
    device_id: DeviceId
    name: _text(80, 1)
    description: _text(4000)
    capabilities: list[CapabilityId]
    tags: list[Tag]
    resources: list[ResourceId]
    identity: Optional[DeviceIdentity] = None
    properties: dict[Name, PropertyDescription]
    actions: dict[Name, ActionDescription]
    events: Optional[dict[EventType, EventTypeDescription]] = None
    safety: SafetyDescription
    extensions: Optional[Extensions] = None
    digest: Digest


class DevicesDescribeParams(_Params):
    device_id: DeviceId
    digest: Optional[Digest] = None


class DevicesDescribeResult(_Result):
    description: DeviceDescription


# --------------------------------------------------------------------------- observations


class Observation(_Wire):
    _NULLABLE = frozenset({"acquiredAt", "ageMs"})
    value: Any
    unit: Optional[_text(32, 1)] = None
    evidence: EvidenceKind
    quality: Quality
    acquired_at: Optional[Time]
    received_at: Time
    age_ms: Optional[NonNegInt]
    uncertainty: Optional[Annotated[float, Field(ge=0)]] = None
    sequence: NonNegInt
    epoch: _text(128, 1)
    source: Optional[_text(128)] = None

    @model_validator(mode="after")
    def _honest(self) -> Observation:
        if self.quality in ("invalid", "unknown") and self.value is not None:
            raise ValueError(f"quality {self.quality} requires value null (never a substituted value)")
        if isinstance(self.value, (int, float)) and not isinstance(self.value, bool) and self.unit is None:
            raise ValueError("a numeric value requires unit")
        return self


class PropertiesReadParams(_Params):
    device_id: DeviceId
    property: Name
    max_age_ms: Optional[NonNegInt] = None
    fresh: Optional[bool] = None


class PropertiesReadResult(_Result):
    observation: Observation
