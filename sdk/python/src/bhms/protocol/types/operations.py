"""Operations, stop, subscriptions, leases, events and notifications (06, 07, 09, 03 §3.7)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import Field, model_validator

from bhms.protocol.types._base import (
    SETTLED_STATES, BhmsErrorCode, CancelState, ClientOperationKey, CompletionEvidence, Cursor, DeviceId, Digest,
    EffectCertainty, EventType, Name, NonNegInt, NotificationMeta, OperationError, OperationKey, OperationState,
    PosInt, RequestId, ResourceId, ResultType, ServerId, SubscriptionMeta, Time, _bounded_int, _Params, _Result,
    _text, _Wire,
)
from bhms.protocol.types.devices import Observation


# --------------------------------------------------------------------------- operations


class CancelInfo(_Wire):
    state: CancelState
    reason: Optional[_text(500)] = None
    requested_at: Optional[Time] = None


class OperationEvidence(_Wire):
    kind: CompletionEvidence
    observations: Optional[dict[Name, Observation]] = None


class Requirement(_Wire):
    effect: Literal["verified"]


class Progress(_Wire):
    steps_completed: NonNegInt
    steps_total: NonNegInt


class OperatorMark(_Wire):
    principal: _text(128, 1)
    basis: _text(2000, 1)


class HistoryEntry(_Wire):
    seq: PosInt
    at: Time
    kind: Literal["state", "cancel", "effect", "evidence", "reconciliation", "correction", "step", "stop", "lease"]
    state: Optional[OperationState] = None
    cancel: Optional[CancelState] = None
    effect: Optional[EffectCertainty] = None
    detail: Optional[_text(1000)] = None
    step_index: Optional[NonNegInt] = None
    child_operation_id: Optional[ServerId] = None
    operator: Optional[OperatorMark] = None


class OperationUpstream(_Wire):
    server: _text(64, 1)
    operation_id: ServerId


class Operation(_Wire):
    operation_id: ServerId
    operation_key: OperationKey
    key_origin: Literal["client", "server", "derived"]
    kind: Literal["action", "program"]
    device_id: Optional[DeviceId] = None
    action: Optional[Name] = None
    program_digest: Optional[Digest] = None
    parent_operation_id: Optional[ServerId] = None
    arguments: dict[str, Any]
    admitted_arguments: Optional[dict[str, Any]] = None
    request_digest: Digest
    state: OperationState
    cancel: CancelInfo
    effect: EffectCertainty
    evidence: Optional[OperationEvidence] = None
    require: Optional[Requirement] = None
    lease_id: Optional[ServerId] = None
    fence: Optional[PosInt] = None
    deadline_at: Optional[Time] = None
    result: Any = None
    error: Optional[OperationError] = None
    progress: Optional[Progress] = None
    created_at: Time
    updated_at: Time
    upstream: Optional[OperationUpstream] = None
    history: Optional[list[HistoryEntry]] = None

    @model_validator(mode="after")
    def _state_rules(self) -> Operation:
        present = self.model_fields_set
        if self.kind == "action" and (self.device_id is None or self.action is None):
            raise ValueError("an action operation requires deviceId and action")
        if self.kind == "program" and self.program_digest is None:
            raise ValueError("a program operation requires programDigest")
        if (self.state == "completed") != ("result" in present):
            raise ValueError("result must be present exactly when state is completed")
        if self.state in ("failed", "rejected", "unknown") and self.error is None:
            raise ValueError(f"state {self.state} requires error")
        if self.state == "rejected" and self.effect != "none":
            raise ValueError("a rejected operation has effect none")
        if self.state == "unknown" and self.effect != "unknown":
            raise ValueError("an unknown operation has effect unknown")
        return self

    @property
    def settled(self) -> bool:
        """True when terminal or unknown: a waiting client stops waiting."""
        return self.state in SETTLED_STATES


class ActionsInvokeParams(_Params):
    device_id: DeviceId
    action: Name
    arguments: dict[str, Any]
    operation_key: Optional[ClientOperationKey] = None
    lease_id: Optional[ServerId] = None
    deadline_ms: Optional[PosInt] = None
    wait_ms: Optional[NonNegInt] = None
    require: Optional[Requirement] = None
    description_digest: Optional[Digest] = None


class ActionsInvokeResult(_Result):
    operation: Operation
    replayed: bool


class OperationsGetParams(_Params):
    operation_id: ServerId


class OperationsWaitParams(_Params):
    operation_id: ServerId
    timeout_ms: NonNegInt


class OperationsListParams(_Params):
    device_id: Optional[DeviceId] = None
    state: Optional[OperationState] = None
    parent_operation_id: Optional[ServerId] = None
    cursor: Optional[Cursor] = None
    limit: Optional[_bounded_int(1, 1000)] = None


class OperationsListResult(_Result):
    operations: list[Operation]
    next_cursor: Optional[Cursor] = None


class OperationsCancelParams(_Params):
    operation_id: ServerId
    reason: Optional[_text(500)] = None


class OperatorResolution(_Wire):
    state: Literal["completed", "failed"]
    basis: _text(2000, 1)
    effect: Optional[Literal["none", "unverified"]] = None
    may_have_acted: Optional[bool] = None
    result: Optional[Any] = None

    @model_validator(mode="after")
    def _consistent(self) -> OperatorResolution:
        given = self.model_fields_set
        if self.state == "failed" and "result" in given:
            raise ValueError("result belongs to state completed")
        if self.state == "completed" and "may_have_acted" in given:
            raise ValueError("mayHaveActed belongs to state failed")
        if self.state == "failed" and (self.effect == "none") != (self.may_have_acted is False):
            raise ValueError("effect none and mayHaveActed false are one claim (nothing happened): state both or neither")
        return self


class OperationsResolveParams(_Params):
    operation_id: ServerId
    resolution: Optional[OperatorResolution] = None


class _OperationResult(_Result):
    operation: Operation


class OperationsGetResult(_OperationResult):
    pass


class OperationsWaitResult(_OperationResult):
    pass


class OperationsCancelResult(_OperationResult):
    pass


class OperationsResolveResult(_OperationResult):
    pass


# --------------------------------------------------------------------------- stop


class DeviceStop(_Wire):
    device_id: DeviceId
    outcome: Literal["confirmed", "initiated", "unsupported", "failed"]
    evidence: CompletionEvidence
    canceled_operations: list[ServerId]
    cancel_requested_operations: Optional[list[ServerId]] = None
    revoked_leases: list[ServerId]
    detail: Optional[_text(1000)] = None
    error: Optional[OperationError] = None

    @model_validator(mode="after")
    def _honest(self) -> DeviceStop:
        if self.outcome == "confirmed" and self.evidence == "none":
            raise ValueError("a confirmed stop requires reported or measured evidence")
        if self.outcome == "failed" and self.error is None:
            raise ValueError("a failed stop requires error")
        return self


class StopParams(_Params):
    device_ids: Optional[Annotated[list[DeviceId], Field(min_length=1, max_length=256)]] = None
    scope: Optional[Literal["all"]] = None
    reason: _text(500, 1)
    wait_ms: Optional[NonNegInt] = None

    @model_validator(mode="after")
    def _one_target(self) -> StopParams:
        if (self.device_ids is None) == (self.scope is None):
            raise ValueError('give exactly one of deviceIds or scope: "all"')
        return self


class StopResult(_Result):
    stops: list[DeviceStop]


# --------------------------------------------------------------------------- subscriptions


class OperationsFilter(_Wire):
    operation_ids: Optional[Annotated[list[ServerId], Field(max_length=256)]] = None
    device_ids: Optional[Annotated[list[DeviceId], Field(max_length=256)]] = None
    all: Optional[bool] = None


class ObservationFilter(_Wire):
    device_id: DeviceId
    property: Name
    min_interval_ms: Optional[NonNegInt] = None


class EventsFilter(_Wire):
    device_ids: Optional[Annotated[list[DeviceId], Field(max_length=256)]] = None
    types: Optional[Annotated[list[EventType], Field(max_length=32)]] = None
    after: Optional[Cursor] = None


class SubscriptionFilter(_Wire):
    devices_list_changed: Optional[bool] = None
    operations: Optional[OperationsFilter] = None
    observations: Optional[Annotated[list[ObservationFilter], Field(max_length=256)]] = None
    events: Optional[EventsFilter] = None


class RefusedFilter(_Wire):
    path: _text(256, 1)
    bhms_code: BhmsErrorCode
    hint: _text(2000)


class SubscriptionsListenParams(_Params):
    notifications: SubscriptionFilter


class SubscriptionsListenResult(_Wire):
    """Sent only when the server ends the subscription (BHMS-LIF-044)."""

    result_type: ResultType
    meta: SubscriptionMeta = Field(alias="_meta")
    end_reason: Literal["shutdown", "overflow", "unauthorized"]


# --------------------------------------------------------------------------- leases


class Lease(_Wire):
    lease_id: ServerId
    resources: Annotated[list[ResourceId], Field(min_length=1, max_length=64)]
    fence: PosInt
    state: Literal["active", "released", "expired", "revoked"]
    acquired_at: Time
    expires_at: Time
    ttl_ms: PosInt


class LeasesAcquireParams(_Params):
    resources: Annotated[list[ResourceId], Field(min_length=1, max_length=64)]
    ttl_ms: PosInt
    wait_ms: Optional[NonNegInt] = None


class LeasesRenewParams(_Params):
    lease_id: ServerId
    ttl_ms: PosInt


class LeasesReleaseParams(_Params):
    lease_id: ServerId


class _LeaseResult(_Result):
    lease: Lease


class LeasesAcquireResult(_LeaseResult):
    pass


class LeasesRenewResult(_LeaseResult):
    pass


class LeasesReleaseResult(_LeaseResult):
    pass


# --------------------------------------------------------------------------- events


class Event(_Wire):
    cursor: Cursor
    time: Time
    type: EventType
    severity: Literal["info", "warning", "error", "critical"]
    device_id: Optional[DeviceId] = None
    operation_id: Optional[ServerId] = None
    message: Optional[_text(1000)] = None
    data: Optional[dict[str, Any]] = None


class EventsReadParams(_Params):
    after: Optional[Cursor] = None
    limit: Optional[_bounded_int(1, 1000)] = None
    device_id: Optional[DeviceId] = None
    types: Optional[Annotated[list[EventType], Field(max_length=32)]] = None


class EventsReadResult(_Result):
    events: list[Event]
    cursor: Cursor
    gap: bool


# --------------------------------------------------------------------------- notifications


class _SubscriptionNotificationParams(_Wire):
    meta: SubscriptionMeta = Field(alias="_meta")


class SubscriptionsAcknowledgedNotificationParams(_SubscriptionNotificationParams):
    notifications: SubscriptionFilter
    refused: Optional[list[RefusedFilter]] = None
    events_gap: Optional[bool] = None


class DevicesListChangedNotificationParams(_SubscriptionNotificationParams):
    pass


class OperationNotificationParams(_SubscriptionNotificationParams):
    operation: Operation


class ObservationNotificationParams(_SubscriptionNotificationParams):
    device_id: DeviceId
    property: Name
    observation: Observation


class EventNotificationParams(_SubscriptionNotificationParams):
    event: Event


class CancelledNotificationParams(_Wire):
    meta: Optional[NotificationMeta] = Field(None, alias="_meta")
    request_id: RequestId
    reason: Optional[_text(500)] = None
