"""Programs, gateway policy and agent-tool inputs (08-programs.md, 13-security.md, 12-agent-surface.md)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import Field, model_validator

from bhms.protocol.types._base import (
    AgentOperationKey, ClientOperationKey, Cursor, DeviceId, DeviceStatus, Digest, EffectClass, Name, NonNegInt,
    ObjectSchema, OperationError, PosInt, ProtocolVersion, Reference, ResourceId, Scope, ServerId, Tag, VariableName,
    _bounded_int, _Params, _pattern, _Plain, _Result, _text, _Wire,
)
from bhms.protocol.types.devices import Budget, CapabilityFilter, DevicesDescribeResult, DeviceSummary
from bhms.protocol.types.operations import Operation


# --------------------------------------------------------------------------- programs


class ComparisonPredicate(_Wire):
    op: Literal["eq", "ne", "lt", "le", "gt", "ge"]
    left: Any
    right: Any


class WithinPredicate(_Wire):
    op: Literal["within"]
    left: Any
    right: Any
    tolerance: Any


class AllPredicate(_Wire):
    all_: Annotated[list[Predicate], Field(min_length=1, max_length=16)] = Field(alias="all")


class AnyPredicate(_Wire):
    any_: Annotated[list[Predicate], Field(min_length=1, max_length=16)] = Field(alias="any")


class NotPredicate(_Wire):
    not_: Predicate = Field(alias="not")


Predicate = Union[ComparisonPredicate, WithinPredicate, AllPredicate, AnyPredicate, NotPredicate]


class InvokeStep(_Wire):
    kind: Literal["invoke"]
    id: Optional[Name] = None
    device_id: DeviceId
    action: Name
    arguments: dict[str, Any]
    save_as: Optional[VariableName] = None


class ReadStep(_Wire):
    kind: Literal["read"]
    id: Optional[Name] = None
    device_id: DeviceId
    property: Name
    max_age_ms: Optional[NonNegInt] = None
    fresh: Optional[bool] = None
    timeout_ms: Optional[_bounded_int(1, 60_000)] = None
    save_as: VariableName


class WaitUntilStep(_Wire):
    kind: Literal["waitUntil"]
    id: Optional[Name] = None
    device_id: DeviceId
    property: Name
    predicate: Predicate
    timeout_ms: _bounded_int(1, 3_600_000)
    poll_ms: Optional[_bounded_int(ge=10)] = None
    save_as: Optional[VariableName] = None


class AssertStep(_Wire):
    kind: Literal["assert"]
    id: Optional[Name] = None
    predicate: Predicate
    message: _text(500, 1)


class SleepStep(_Wire):
    kind: Literal["sleep"]
    id: Optional[Name] = None
    duration_ms: _bounded_int(1, 3_600_000)


class RepeatStep(_Wire):
    kind: Literal["repeat"]
    id: Optional[Name] = None
    times: Union[_bounded_int(1, 1000), Reference]
    as_: Optional[VariableName] = Field(None, alias="as")
    steps: Annotated[list[Step], Field(min_length=1, max_length=256)]


Step = Annotated[Union[InvokeStep, ReadStep, WaitUntilStep, AssertStep, SleepStep, RepeatStep],
                 Field(discriminator="kind")]


class Program(_Wire):
    bhms_program: ProtocolVersion
    name: Name
    description: _text(1000)
    input: ObjectSchema
    max_duration_ms: _bounded_int(1, 86_400_000)
    steps: Annotated[list[Step], Field(min_length=1, max_length=256)]
    output: Optional[dict[VariableName, Any]] = None


class ProgramInfo(_Wire):
    digest: Digest
    name: Name
    description: _text(1000)
    input: ObjectSchema
    effect: EffectClass
    worst_case_duration_ms: NonNegInt
    max_duration_ms: PosInt
    step_count: PosInt
    max_executed_steps: NonNegInt
    devices: list[DeviceId]
    resources: list[ResourceId]
    requires_lease: bool


class ProgramsRunParams(_Params):
    program: Optional[Program] = None
    digest: Optional[Digest] = None
    arguments: dict[str, Any]
    operation_key: Optional[ClientOperationKey] = None
    lease_id: Optional[ServerId] = None
    deadline_ms: Optional[PosInt] = None
    wait_ms: Optional[NonNegInt] = None

    @model_validator(mode="after")
    def _one_source(self) -> ProgramsRunParams:
        if (self.program is None) == (self.digest is None):
            raise ValueError("give exactly one of program or digest")
        return self


class ProgramsRunResult(_Result):
    operation: Operation
    replayed: bool


class ProgramsRegisterParams(_Params):
    program: Program


class ProgramsRegisterResult(_Result):
    info: ProgramInfo


class ProgramsGetParams(_Params):
    digest: Digest


class ProgramsGetResult(_Result):
    program: Program
    info: ProgramInfo


class ProgramsListParams(_Params):
    cursor: Optional[Cursor] = None
    limit: Optional[_bounded_int(1, 1000)] = None


class ProgramsListResult(_Result):
    programs: list[ProgramInfo]
    next_cursor: Optional[Cursor] = None


# --------------------------------------------------------------------------- gateway policy


class ArgumentBound(_Wire):
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    enum: Optional[Annotated[list[Any], Field(min_length=1)]] = None


PolicyActionKey = _pattern(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}/[a-z][a-z0-9_]{0,63}$")


class PolicyPrincipal(_Wire):
    tokens: Optional[list[Digest]] = None
    uids: Optional[list[NonNegInt]] = None
    scopes: list[Scope]
    bounds: Optional[dict[PolicyActionKey, dict[Name, ArgumentBound]]] = None
    budgets: Optional[Annotated[list[Budget], Field(max_length=64)]] = None

    @model_validator(mode="after")
    def _distinct_budgets(self) -> PolicyPrincipal:
        ids = [b.id for b in self.budgets or ()]
        if len(ids) != len(set(ids)):
            raise ValueError("budget ids must be unique per principal (7.4.1)")
        return self


class GatewayPolicy(_Wire):
    principals: dict[_pattern(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"), PolicyPrincipal]


# --------------------------------------------------------------------------- agent tools (snake_case wire)

AgentWait = _bounded_int(0, 60_000)


class AgentFindInput(_Plain):
    text: Optional[_text(200, 1)] = None
    capability: Optional[CapabilityFilter] = None
    tag: Optional[Tag] = None
    status: Optional[DeviceStatus] = None
    cursor: Optional[Cursor] = None


AgentTopic = Literal["program-grammar"]


class AgentDescribeInput(_Plain):
    device_id: Optional[DeviceId] = None
    topic: Optional[AgentTopic] = None

    @model_validator(mode="after")
    def _one_subject(self) -> AgentDescribeInput:
        if (self.device_id is None) == (self.topic is None):
            raise ValueError("give exactly one of device_id or topic")
        return self


class AgentReadInput(_Plain):
    device_id: DeviceId
    property: Name
    max_age_ms: Optional[NonNegInt] = None
    fresh: Optional[bool] = None


class AgentInvokeInput(_Plain):
    device_id: DeviceId
    action: Name
    arguments: dict[str, Any]
    operation_key: Optional[AgentOperationKey] = None
    wait_ms: Optional[AgentWait] = None
    require_verified: Optional[bool] = None


class AgentOperationInput(_Plain):
    operation_id: ServerId
    wait_ms: Optional[AgentWait] = None


class AgentCancelInput(_Plain):
    operation_id: ServerId
    reason: Optional[_text(500)] = None


class AgentStopInput(_Plain):
    device_ids: Optional[Annotated[list[DeviceId], Field(min_length=1, max_length=256)]] = None
    all: Optional[Literal[True]] = None
    reason: _text(500, 1)

    @model_validator(mode="after")
    def _one_target(self) -> AgentStopInput:
        if (self.device_ids is None) == (self.all is None):
            raise ValueError("give exactly one of device_ids or all: true")
        return self


class AgentRunProgramInput(_Plain):
    program: Optional[Program] = None
    program_digest: Optional[Digest] = None
    arguments: dict[str, Any]
    operation_key: Optional[AgentOperationKey] = None
    wait_ms: Optional[AgentWait] = None

    @model_validator(mode="after")
    def _one_source(self) -> AgentRunProgramInput:
        if (self.program is None) == (self.program_digest is None):
            raise ValueError("give exactly one of program or program_digest")
        return self


class AgentFindData(_Wire):
    devices: list[DeviceSummary]
    programs: Optional[list[ProgramInfo]] = None
    next_cursor: Optional[Cursor] = None
    total_devices: Optional[NonNegInt] = None


class AgentTopicData(_Wire):
    topic: AgentTopic
    text: str = Field(max_length=4000)


AgentDescribeData = Union[DevicesDescribeResult, AgentTopicData]


class AgentFunctionResult(_Wire):
    summary: _pattern(r"^[^\n]*$", max_length=200)
    signature: Optional[str] = Field(default=None, max_length=4000)
    data: Optional[dict[str, Any]] = None
    error: Optional[OperationError] = None

    @model_validator(mode="after")
    def _one_payload(self) -> AgentFunctionResult:
        if (self.data is None) == (self.error is None):
            raise ValueError("give exactly one of data or error")
        return self


for _model in (AllPredicate, AnyPredicate, NotPredicate, RepeatStep, WaitUntilStep, AssertStep, Program,
               ProgramsRunParams, ProgramsRegisterParams, ProgramsGetResult, AgentRunProgramInput):
    _model.model_rebuild()
