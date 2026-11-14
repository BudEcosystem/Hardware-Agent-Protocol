"""Admission and execution of action operations (spec/bhms/06-operations.md §6.5–6.9, 04-devices.md BHMS-DEV-030).

:class:`Executor` turns an admitted request into physical work and records every outcome in the
:class:`~bhms.runtime.operations.Journal`:

* **Admission** (§6.5 steps 3–10, after the key lookup done by the caller): resolve device/action (``UNKNOWN_DEVICE``,
  ``UNKNOWN_ACTION``), authorize (``UNAUTHORIZED``), description pin (``STALE``), arguments and envelope
  (:class:`~bhms.server.validation.ArgumentValidator`), ``require`` (``UNSUPPORTED``), lease (BHMS-LSE-010, BHMS-LSE-014), device
  reachability (``DEVICE_UNAVAILABLE``), unresolved ``unknown`` operations on the same resources (``STALE`` naming the
  operation, BHMS-OPS-042), ``requiresFresh`` (BHMS-OBS-030), capacity (``BUSY``). Only then is the operation written.
* **Queueing**: operations whose resources are in use wait in ``accepted`` in FIFO order per resource (they can be
  cancelled without effect, BHMS-OPS-050). A deadline that passes while queued rejects them (BHMS-OPS-070).
* **Dispatch**: time-dependent checks are repeated immediately before dispatch (BHMS-OPS-041; failure → ``rejected``,
  ``effect: none``); ``dispatching`` is committed with fsync before the handler starts (BHMS-OPS-003); when that write
  fails nothing is dispatched.
* **Execution**: the handler runs as a task that no request owns — a client disconnect never cancels it
  (BHMS-LIF-050). Return → ``completed`` (result validated against ``output``, BHMS-OPS-008; ``verified`` only with
  measured evidence from ``ctx.verify``, BHMS-OPS-006/007); :class:`~bhms.server.context.Canceled` → ``canceled``;
  :class:`~bhms.server.context.DeviceFault` → ``failed``/``DEVICE_FAULT``; anything else → ``unknown`` (BHMS-OPS-004).
* **Duration bounds** (BHMS-DEV-030, BHMS-OPS-071): at the earlier of ``maxDurationMs`` and the client deadline a
  cancellable action gets ``ctx.cancelled`` and a grace period, then ends ``failed``/``DEADLINE_EXCEEDED``; without
  observed termination (or without cancel support) it becomes ``unknown`` and a later handler return is recorded as a
  reconciliation to ``failed`` — never ``completed``.
* **Lease loss** (BHMS-LSE-012) applies the action's ``onLeaseLoss``.

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import math
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bhms.protocol.canonical import canonical
from bhms.protocol.errors import BhmsError
from bhms.protocol.types import to_wire
from bhms.runtime.operations import InvalidTransition, OperationRecord, now_ns, unknown_error
from bhms.runtime.store import StoreError
from bhms.server.context import DEVICE_LOSS, ActionContext, Canceled, DeviceFault, Reconciled
from bhms.server.decorators import ActionSpec

if TYPE_CHECKING:
    from bhms.runtime.authority import Principal
    from bhms.runtime.leases import Lease
    from bhms.server.device import Device
    from bhms.server.server import DeviceServer

log = logging.getLogger("bhms.executor")
_RANGE_KEYWORDS = frozenset({"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"})
"""Output-schema keywords whose violation means "a number outside its declared range" (BHMS-OPS-008)."""


@dataclass
class Execution:
    """A dispatched operation whose handler is (or was) running."""

    server: DeviceServer
    device: Device
    spec: ActionSpec
    rec: OperationRecord
    admitted: dict[str, Any]
    deadline: float
    bound_ms: int
    bound_kind: str
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)
    cancel_reason: str | None = None
    task: asyncio.Task[None] | None = None
    timer: asyncio.TimerHandle | None = None
    grace: asyncio.TimerHandle | None = None
    deadline_hit: bool = False
    stop_confirmed: bool = False  # a confirmed stop covered this operation (BHMS-OPS-042)
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    confirmed: list[bool] = field(default_factory=list)
    loop: asyncio.AbstractEventLoop = field(default_factory=asyncio.get_running_loop)
    loop_thread: int = field(default_factory=threading.get_ident)

    def mark_running(self, detail: str | None) -> None:
        if self.rec.state == "dispatching":
            self.server.journal.transition(self.rec, "running", detail=detail)

    def add_evidence(self, prop: str, observation: dict[str, Any], confirmed: bool) -> None:
        self.evidence[prop] = observation
        self.confirmed.append(confirmed)


@dataclass
class _Queued:
    device: Device
    spec: ActionSpec
    admitted: dict[str, Any]
    principal: Principal
    timer: asyncio.TimerHandle | None = None


class Executor:
    """Admission, queueing, dispatch and execution of action operations for one server."""

    def __init__(self, server: DeviceServer, *, queue_limit: int = 64, cancel_grace_ms: int = 1000) -> None:
        self.server = server
        self.queue_limit = queue_limit
        self.cancel_grace_ms = cancel_grace_ms
        self._waiting: list[OperationRecord] = []
        self._queued: dict[str, _Queued] = {}
        self._unsettled: dict[str, OperationRecord] = {}  # dispatched ops whose settlement could not be journaled
        self._retry: asyncio.TimerHandle | None = None
        self._pending: dict[str, OperationRecord] = {}  # popped from _waiting, pre-dispatch checks in flight
        self._busy: dict[str, str] = {}
        self._running: dict[str, Execution] = {}
        self._inhibited: dict[str, set[str]] = {}
        self.tasks: set[asyncio.Task[Any]] = set()
        journal = server.journal
        journal.on_unknown.append(self._on_unknown)
        journal.on_settled.append(self._on_settled)

    # ------------------------------------------------------------------ inhibition (BHMS-OPS-042)

    def load_inhibitions(self) -> None:
        """Rebuild the unknown-operation inhibition from the journal (after a restart)."""
        for row in self.server.store.operations_in_states(["unknown"]):
            if row.record.get("kind") == "action":
                rec = self.server.journal.get(row.id)
                if rec is not None:
                    self._on_unknown(rec)

    def _on_unknown(self, rec: OperationRecord) -> None:
        if rec.op["kind"] != "action" or rec.private.get("effectClass", "none") == "none" \
                or rec.private.get("inhibitionLifted"):
            return
        for resource in rec.resources:
            self._inhibited.setdefault(resource, set()).add(rec.id)

    def _on_settled(self, rec: OperationRecord) -> None:
        if rec.terminal:
            self.lift_inhibition(rec)

    def confirm_stop(self, device_id: str) -> None:
        """A confirmed stop covers the device's running operations: if one ends ``unknown``, it does not inhibit."""
        for execution in self._running.values():
            if execution.device.device_id == device_id:
                execution.stop_confirmed = True

    def lift_inhibition(self, rec: OperationRecord) -> None:
        for resource in rec.resources:
            ids = self._inhibited.get(resource)
            if ids is not None:
                ids.discard(rec.id)
                if not ids:
                    del self._inhibited[resource]

    def inhibiting(self, resources: tuple[str, ...]) -> str | None:
        """The id of an unresolved ``unknown`` operation on any of ``resources``, if one exists."""
        for resource in resources:
            ids = self._inhibited.get(resource)
            if ids:
                return sorted(ids)[0]
        return None

    def _hold_unsettled(self, rec: OperationRecord, *, lifted: bool = False) -> None:
        """A settlement could not be journaled: the device acted but the record is not durable. Keep the resources
        inhibited in memory (no new work is admitted on them) and keep trying to record ``unknown`` (BHMS-OPS-004/042)."""
        if rec.state not in ("dispatching", "running"):
            return
        self._unsettled[rec.id] = rec
        if lifted:
            rec.private = {**rec.private, "inhibitionLifted": True}  # persisted with the unknown record
        else:
            for resource in rec.resources:
                self._inhibited.setdefault(resource, set()).add(rec.id)
        if self._retry is None:
            self._retry = asyncio.get_running_loop().call_later(1.0, self._retry_unsettled)

    def _retry_unsettled(self) -> None:
        self._retry = None
        self.flush_unsettled()
        if self._unsettled:
            self._retry = asyncio.get_running_loop().call_later(1.0, self._retry_unsettled)

    def flush_unsettled(self) -> None:
        """Durably record ``unknown`` for operations held by :meth:`_hold_unsettled`, as soon as the journal allows."""
        for rec in list(self._unsettled.values()):
            if rec.state in ("dispatching", "running"):
                try:
                    self.server.journal.transition(rec, "unknown", error=unknown_error(
                        f"{rec.op.get('action')} finished (or failed) but its outcome could not be recorded in the "
                        "journal; whether the device acted as intended is unknown"))
                except StoreError as exc:
                    self.server.journal_failed(exc)
                    return
                except Exception:  # noqa: BLE001 - keep holding it; the next attempt or a restart settles it
                    log.exception("could not mark %s unknown", rec.id)
                    return
            del self._unsettled[rec.id]
            if rec.private.get("inhibitionLifted") and rec.state == "unknown":
                with contextlib.suppress(StoreError):
                    self.server.journal.mark_private(rec, inhibitionLifted=True)  # make the lift durable
            if rec.private.get("effectClass", "none") == "none" and rec.state == "unknown":
                self.lift_inhibition(rec)

    def _check_inhibition(self, resources: tuple[str, ...]) -> None:
        if self._unsettled:
            self.flush_unsettled()
        blocking = self.inhibiting(resources)
        if blocking is not None:
            raise BhmsError("STALE", f"operation {blocking} on the same resources has an unknown outcome",
                            field="operationId", operation_id=blocking,
                            hint=f"reconcile {blocking} first (operations/get, read the device state, or stop the "
                                 "device); new work on its resources is refused until then (BHMS-OPS-042)")

    # ------------------------------------------------------------------ admission

    def resolve(self, principal: Principal, device_id: str, action: str, *, field_prefix: str = ""
                ) -> tuple[Device, ActionSpec]:
        """Steps 3–4: device, action and invoke authority."""
        device = self.server.visible_device(principal, device_id, field=f"{field_prefix}deviceId")
        spec = device.actions.get(action)
        if spec is None:
            names = ", ".join(sorted(device.actions)) or "none"
            raise BhmsError("UNKNOWN_ACTION", f"{device_id} has no action {action!r}", field=f"{field_prefix}action",
                            hint=f"actions of {device_id}: {names} (devices/describe has their inputs)")
        if not principal.can_invoke(device_id, action, device.capabilities, spec.effect == "hazardous"):
            literal = " (hazardous actions need the literal action name)" if spec.effect == "hazardous" else ""
            raise BhmsError("UNAUTHORIZED", f"you may not invoke {device_id}/{action}", field=f"{field_prefix}action",
                            hint=f"missing scope invoke:{device_id}/{action}{literal}; ask an administrator")
        return device, spec

    def admit_arguments(self, principal: Principal, device: Device, spec: ActionSpec, arguments: dict[str, Any], *,
                        field_prefix: str = "arguments") -> dict[str, Any]:
        """Step 6: arguments against ``input`` and the principal's envelope (BHMS-DEV-043/044, BHMS-AUTH-010/011)."""
        bounds = principal.bounds_for(device.device_id, spec.name)
        if bounds:
            from bhms.server.validation import effective_bounds

            for member, bound in bounds.items():
                node = spec.input.get("properties", {}).get(member, {})
                if effective_bounds(node, bound).get("empty"):
                    raise BhmsError("UNAUTHORIZED", f"your policy leaves no allowed value for {member}",
                                    field=f"{field_prefix}.{member}",
                                    hint=f"{device.device_id}/{spec.name} is unavailable to you (BHMS-AUTH-011)")
        validator = device.validator(spec.name)
        if field_prefix != "arguments":
            from bhms.server.validation import ArgumentValidator

            validator = ArgumentValidator(spec.input, field_prefix=field_prefix)
        return validator.admit(arguments, bounds=bounds)

    def check_lease(self, principal: Principal, spec: ActionSpec, lease_id: str | None) -> Lease | None:
        """Step 8 (BHMS-LSE-010, BHMS-LSE-014): a lease passed for an action that does not require one must still be
        valid, and a lease held on one of the action's resources refuses a request that does not present it."""
        return self.server.leases.admit(principal, lease_id, spec.resources, required=spec.requires_lease)

    def check_state(self, device: Device, spec: ActionSpec) -> None:
        """Step 9 except ``requiresFresh``: reachability, journal, unknown inhibition, capacity."""
        if device.status == "offline":
            raise BhmsError("DEVICE_UNAVAILABLE", f"{device.device_id} is offline", field="deviceId",
                            retry="same-key", hint="retry with the same operationKey when the device is back online")
        self.server.require_journal()
        self._check_inhibition(spec.resources)
        queued = sum(1 for q in self._queued.values() if q.device is device)
        if queued >= self.queue_limit:
            raise BhmsError("BUSY", f"{device.device_id} already has {queued} queued operations", field="deviceId",
                            bound=self.queue_limit, retry="same-key",
                            hint="retry later with the same operationKey, or wait for queued work to finish")

    async def admit(self, principal: Principal, params: Any, key: str, key_origin: str, request_digest: str, *,
                    parent_id: str | None = None, deadline_ns: int | None = None,
                    admitted: dict[str, Any] | None = None, private: dict[str, Any] | None = None
                    ) -> OperationRecord:
        """Steps 3–10 for ``actions/invoke`` params (a model); returns the recorded operation."""
        device, spec = self.resolve(principal, params.device_id, params.action)
        if params.description_digest is not None and params.description_digest != device.digest:
            raise BhmsError("STALE", f"{device.device_id}'s description changed since you read it",
                            field="descriptionDigest", bound=device.digest,
                            hint="fetch devices/describe again, re-plan against the new description, and resend")
        if admitted is None:
            admitted = self.admit_arguments(principal, device, spec, params.arguments)
        require = params.require.model_dump(by_alias=True) if params.require is not None else None
        if require is not None and spec.completion_evidence != "measured":
            raise BhmsError("UNSUPPORTED", f"{device.device_id}/{spec.name} cannot verify its effect "
                            f"(completionEvidence is {spec.completion_evidence})", field="require",
                            hint="drop require, or use an action whose completionEvidence is measured")
        self.check_lease(principal, spec, params.lease_id)
        self.check_state(device, spec)
        if spec.requires_fresh:
            await self.server.observations.require_fresh(device, spec.requires_fresh, principal, params.lease_id)
        lease = self.check_lease(principal, spec, params.lease_id)  # re-check after the awaits above
        self._check_inhibition(spec.resources)
        if deadline_ns is None and params.deadline_ms is not None:
            deadline_ns = now_ns() + params.deadline_ms * 1_000_000
        immediate = self._free(spec.resources)
        try:
            rec = self.server.journal.create(
                principal=principal.id, key=key, key_origin=key_origin, kind="action", device_id=device.device_id,
                action=spec.name, parent_id=parent_id, arguments=params.arguments, admitted=admitted,
                request_digest=request_digest, require=require, lease_id=lease.lease_id if lease else None,
                fence=lease.fence if lease else None, deadline_ns=deadline_ns,
                private={"resources": list(spec.resources), "effectClass": spec.effect, **(private or {})},
                dispatch=immediate)
        except StoreError as exc:
            self.server.journal_failed(exc)
            raise BhmsError("BUSY", "the operation journal cannot be written; nothing was recorded or sent",
                            retry="same-key", hint="retry later with the same operationKey") from None
        if immediate:
            self._start(rec, device, spec, admitted)
        else:
            self._enqueue(rec, device, spec, admitted, principal)
        return rec

    # ------------------------------------------------------------------ queueing and dispatch

    def _free(self, resources: tuple[str, ...]) -> bool:
        if any(r in self._busy for r in resources):
            return False
        wanted = set(resources)
        return not any(wanted.intersection(w.resources) for w in self._waiting)

    def _enqueue(self, rec: OperationRecord, device: Device, spec: ActionSpec, admitted: dict[str, Any],
                 principal: Principal) -> None:
        queued = _Queued(device, spec, admitted, principal)
        deadline_ns = rec.private.get("deadlineNs")
        if deadline_ns is not None:
            loop = asyncio.get_running_loop()
            queued.timer = loop.call_later(max(0.0, (deadline_ns - now_ns()) / 1e9), self._queued_deadline, rec)
        self._queued[rec.id] = queued
        self._waiting.append(rec)

    def _queued_deadline(self, rec: OperationRecord) -> None:
        if rec.state == "accepted" and rec.id in self._queued:
            self._drop_queued(rec)
            self._reject(rec, BhmsError("DEADLINE_EXCEEDED", "the deadline passed before the operation could be "
                                        "dispatched; nothing was sent to the device", may_have_acted=False,
                                        hint="no effect occurred; resend with a later deadline or a new key"))
            self.pump()

    def _drop_queued(self, rec: OperationRecord) -> _Queued | None:
        queued = self._queued.pop(rec.id, None)
        if queued is not None and queued.timer is not None:
            queued.timer.cancel()
        if rec in self._waiting:
            self._waiting.remove(rec)
        return queued

    def _reject(self, rec: OperationRecord, error: BhmsError) -> None:
        payload = error.to_operation_error()
        payload["mayHaveActed"] = False
        try:
            self.server.journal.transition(rec, "rejected", error=payload)
        except StoreError as exc:
            self.server.journal_failed(exc)
            log.error("could not record the rejection of %s; it stays accepted and is rejected at restart", rec.id)

    def pump(self) -> None:
        """Dispatch queued operations whose resources became free (FIFO per resource)."""
        blocked: set[str] = set()
        for rec in list(self._waiting):
            resources = rec.resources
            if any(r in self._busy or r in blocked for r in resources):
                blocked.update(resources)
                continue
            queued = self._drop_queued(rec)
            if queued is None:
                continue
            for resource in resources:
                self._busy[resource] = rec.id  # reserved while the pre-dispatch checks run
            self._pending[rec.id] = rec  # still visible to stop and cancel until the dispatch commit
            self._spawn(self._dispatch_queued(rec, queued))

    async def _dispatch_queued(self, rec: OperationRecord, queued: _Queued) -> None:
        """Pre-dispatch checks, then the dispatch commit, for an operation taken off the queue.

        ``require_fresh`` awaits a device read, during which ``stop``, ``operations/cancel`` or a lease revocation may
        end the operation. So the synchronous checks run again after that await, with no await between them and the
        barrier commit of ``dispatching`` (BHMS-OPS-041, BHMS-AUTH-021).
        """
        try:
            error = self._recheck(rec, queued)
            if error is None and queued.spec.requires_fresh and rec.state == "accepted":
                try:
                    await self.server.observations.require_fresh(queued.device, queued.spec.requires_fresh,
                                                                 queued.principal, rec.op.get("leaseId"))
                except BhmsError as exc:
                    error = exc
                except Exception as exc:  # noqa: BLE001 - settle it: an accepted op must never be left untracked
                    log.exception("freshness check of %s failed", rec.id)
                    error = BhmsError("INTERNAL", f"the freshness check failed unexpectedly ({type(exc).__name__}: "
                                      f"{exc})"[:2000], hint="nothing was sent to the device; retry with a new key")
                else:
                    error = self._recheck(rec, queued)
            if rec.state != "accepted":
                return  # stopped or canceled while the checks ran: nothing is sent
            if error is not None:
                self._reject(rec, error)
                return
            try:
                self.server.journal.transition(rec, "dispatching")
            except StoreError as exc:
                self.server.journal_failed(exc)
                self._reject(rec, BhmsError("INTERNAL", "the dispatch record could not be written, so nothing was "
                                            "sent to the device (BHMS-OPS-003)", hint="retry later with a new key"))
                return
            self._start(rec, queued.device, queued.spec, queued.admitted, reserved=True)
            return
        finally:
            self._pending.pop(rec.id, None)
            if rec.id not in self._running:
                self._release(rec)
                self.pump()

    def _recheck(self, rec: OperationRecord, queued: _Queued) -> BhmsError | None:
        """BHMS-OPS-041: the time-dependent checks immediately before dispatch (synchronous)."""
        deadline_ns = rec.private.get("deadlineNs")
        if deadline_ns is not None and now_ns() >= deadline_ns:
            return BhmsError("DEADLINE_EXCEEDED", "the deadline passed before dispatch; nothing was sent",
                             hint="no effect occurred; resend with a later deadline")
        try:
            self.check_lease(queued.principal, queued.spec, rec.op.get("leaseId"))
            if queued.device.status == "offline":
                raise BhmsError("DEVICE_UNAVAILABLE", f"{queued.device.device_id} went offline before dispatch",
                                hint="nothing was sent; retry when the device is back")
            self._check_inhibition(queued.spec.resources)
            self.server.require_journal()
        except BhmsError as exc:
            return exc
        return None

    def _release(self, rec: OperationRecord) -> None:
        for resource in rec.resources:
            if self._busy.get(resource) == rec.id:
                del self._busy[resource]

    def _spawn(self, coro: Any) -> asyncio.Task[Any]:
        task = asyncio.get_running_loop().create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    # ------------------------------------------------------------------ execution

    def _start(self, rec: OperationRecord, device: Device, spec: ActionSpec, admitted: dict[str, Any], *,
               reserved: bool = False) -> None:
        loop = asyncio.get_running_loop()
        bound_ms, bound_kind = spec.max_duration_ms, "maxDurationMs"
        deadline_ns = rec.private.get("deadlineNs")
        if deadline_ns is not None and (deadline_ns - now_ns()) / 1e6 < bound_ms:
            bound_ms, bound_kind = max(0, int((deadline_ns - now_ns()) / 1e6)), "deadline"
        execution = Execution(self.server, device, spec, rec, admitted, loop.time() + bound_ms / 1000, bound_ms,
                              bound_kind)
        for resource in spec.resources:
            self._busy[resource] = rec.id
        self._running[rec.id] = execution
        execution.timer = loop.call_at(execution.deadline, self._on_deadline, execution)
        execution.task = self._spawn(self._run(execution))

    async def _call(self, execution: Execution) -> Any:
        spec = execution.spec
        handler = spec.handler
        kwargs = {name: execution.admitted[name] for name in spec.params if name in execution.admitted}
        args = (ActionContext(execution),) if spec.ctx_param is not None else ()
        if inspect.iscoroutinefunction(handler):
            return await handler(*args, **kwargs)
        if spec.blocking:
            return await asyncio.to_thread(handler, *args, **kwargs)
        outcome = handler(*args, **kwargs)
        if inspect.isawaitable(outcome):
            return await outcome
        return outcome

    async def _run(self, execution: Execution) -> None:
        outcome: tuple[str, Any]
        aborted = False
        try:
            outcome = ("returned", await self._call(execution))
        except Canceled as exc:
            outcome = ("canceled", exc)
        except DeviceFault as exc:
            outcome = ("fault", exc)
        except asyncio.CancelledError:
            outcome, aborted = ("crashed", RuntimeError("the server shut down while the handler was running")), True
        except DEVICE_LOSS as exc:  # expected of real hardware: one line, no traceback; the outcome is unknown all the same
            log.warning("%s lost during %s (operation %s): %s: %s", execution.device.device_id, execution.spec.name,
                        execution.rec.id, type(exc).__name__, exc)
            outcome = ("crashed", exc)
        except Exception as exc:  # noqa: BLE001 - after dispatch an unexplained failure has an unknown outcome
            log.error("handler %s/%s raised (operation %s): %s", execution.device.device_id, execution.spec.name,
                      execution.rec.id, exc, exc_info=exc)
            outcome = ("crashed", exc)
        finally:
            for handle in (execution.timer, execution.grace):
                if handle is not None:
                    handle.cancel()
            self._running.pop(execution.rec.id, None)
            self._release(execution.rec)
        try:
            self._settle(execution, outcome)
        except StoreError as exc:
            self.server.journal_failed(exc)
            log.error("could not record the outcome of %s; holding its resources and retrying as unknown",
                      execution.rec.id)
            self._hold_unsettled(execution.rec, lifted=execution.stop_confirmed)
        except Exception as exc:  # noqa: BLE001 - whatever stops the outcome being recorded must not free the device
            log.exception("could not record the outcome of %s", execution.rec.id)
            self._settle_unknown(execution, exc)
        finally:
            self.pump()
        if aborted:
            raise asyncio.CancelledError

    def _settle_unknown(self, execution: Execution, cause: BaseException) -> None:
        """The outcome could not be journaled: the operation becomes ``unknown`` (resources inhibited, BHMS-OPS-042)."""
        rec = execution.rec
        if rec.state not in ("dispatching", "running"):
            return
        try:
            self.server.journal.transition(rec, "unknown", error=unknown_error(
                f"{execution.spec.name} finished but its outcome could not be recorded "
                f"({type(cause).__name__}: {cause}); whether the device acted as intended is unknown"))
        except Exception:  # noqa: BLE001 - held and retried; recovered as unknown at restart at the latest
            log.exception("could not mark %s unknown; holding its resources and retrying", rec.id)
            self._hold_unsettled(rec, lifted=execution.stop_confirmed)

    @staticmethod
    def _claimed_effect(execution: Execution, effect: str) -> tuple[str, dict[str, Any] | None]:
        """A handler's claim of a ``verified`` effect stands only with measured, confirming evidence (BHMS-OPS-006)."""
        if effect != "verified":
            return effect, None
        if execution.confirmed and all(execution.confirmed) and execution.evidence:
            return "verified", {"kind": "measured", "observations": execution.evidence}
        return "unverified", None

    def _settle(self, execution: Execution, outcome: tuple[str, Any]) -> None:
        rec, spec = execution.rec, execution.spec
        journal = self.server.journal
        kind, value = outcome
        if spec.effect != "none":
            self.server.observations.after_effect(execution.device)  # BHMS-OBS-006: nothing retained predates the effect
        if rec.state in ("dispatching", "running"):
            if execution.deadline_hit and kind != "crashed":
                journal.transition(rec, "failed", error=self._deadline_error(execution, terminated=True),
                                   effect=self._partial_effect(kind, value),
                                   cancel="confirmed" if kind == "canceled" else None,
                                   detail=self._late_detail(kind, value))
            elif kind == "returned":
                self._complete(execution, value)
            elif kind == "canceled":
                effect, evidence = self._claimed_effect(execution, value.effect)
                journal.transition(rec, "canceled", effect=effect, evidence=evidence, detail=value.detail)
            elif kind == "fault":
                self._fault(execution, value)
            else:
                what = (f"the link to {execution.device.device_id} was lost during {spec.name}"
                        if isinstance(value, DEVICE_LOSS) else f"{spec.name} handler failed after dispatch")
                journal.transition(rec, "unknown", error=unknown_error(
                    f"{what} ({type(value).__name__}: {value}); whether the device acted is unknown"))
        elif rec.state == "unknown" and kind != "crashed":
            journal.transition(rec, "failed", error=self._deadline_error(execution, terminated=True),
                               effect=self._partial_effect(kind, value), kind="reconciliation",
                               detail=f"handler finished after the {execution.bound_kind} bound: "
                                      f"{self._late_detail(kind, value)}")
        elif rec.terminal:
            journal.annotate(rec, "correction", f"handler finished after the operation ended: "
                                                f"{self._late_detail(kind, value)}")

    def _partial_effect(self, kind: str, value: Any) -> str:
        if kind in ("canceled", "fault"):
            return value.effect if value.effect != "verified" else "unverified"
        return "unverified"

    @staticmethod
    def _late_detail(kind: str, value: Any) -> str:
        if kind == "returned":
            return f"returned {value!r}"[:900]
        if kind == "canceled":
            return f"terminated after cancellation ({value.detail or 'no detail'})"
        if kind == "fault":
            return f"device fault: {value.message}"
        return f"failed: {value}"

    def _deadline_error(self, execution: Execution, *, terminated: bool) -> dict[str, Any]:
        what = f"{execution.spec.name} exceeded its {execution.bound_kind} of {execution.bound_ms} ms"
        return BhmsError("DEADLINE_EXCEEDED", f"{what}; termination {'was' if terminated else 'was not'} observed",
                         may_have_acted=True, hint=f"read {execution.device.device_id}'s state to see what was done "
                                                   "before deciding to retry").to_operation_error()

    @staticmethod
    def _result_problem(device: Device, spec: ActionSpec, result: Any) -> str | None:
        """Why ``result`` cannot be recorded (not I-JSON, or not the declared output), else None."""
        try:
            canonical(result)
        except BhmsError as exc:
            where = _ijson_violation(result, "result")
            if where:
                return where
            return f"the result is not JSON-serialisable ({exc.message})"
        if spec.output:
            for error in device.output_validator(spec.name).iter_errors(result):
                return f"the result does not match the declared output schema: {error.message}"
        return None

    @staticmethod
    def _result_out_of_range(device: Device, spec: ActionSpec, result: Any) -> BhmsError | None:
        """The ``OUT_OF_RANGE`` operation error for a result whose only defect is a numeric value outside the range its
        ``output`` schema declares (BHMS-OPS-008), else None. The device acted and reported a value: that is a
        measurement outside its declared range, not a result that "cannot be recorded"."""
        if not spec.output:
            return None
        try:
            canonical(result)
        except BhmsError:
            return None
        errors = list(device.output_validator(spec.name).iter_errors(result))
        if not errors or any(e.validator not in _RANGE_KEYWORDS for e in errors):
            return None
        first = errors[0]
        member = ".".join(["result", *(str(part) for part in first.absolute_path)])
        bound = {first.validator: first.validator_value}
        return BhmsError(
            "OUT_OF_RANGE", f"{spec.name} acted and returned {member} = {first.instance!r}, outside its declared output "
            f"range ({first.validator} {first.validator_value!r})"[:2000], field=member, bound=bound, may_have_acted=True,
            retry="after-reconcile",
            hint=f"the device acted; the returned value is in this message and in the operation's history. Read "
                 f"{device.device_id}'s state before deciding what to do; the declared range may be too narrow for the "
                 "instrument's tolerance")

    def _completion_effect(self, execution: Execution) -> tuple[str, dict[str, Any] | None]:
        """The ``effect`` and ``evidence`` of a handler that returned (BHMS-OPS-006)."""
        spec = execution.spec
        if spec.effect == "none":
            return "none", None
        verified = bool(execution.confirmed) and all(execution.confirmed)
        kind = "measured" if verified else ("none" if spec.completion_evidence == "none" else "reported")
        evidence: dict[str, Any] = {"kind": kind}
        if execution.evidence:
            evidence["observations"] = execution.evidence
        return ("verified" if verified else "unverified"), evidence

    def _complete(self, execution: Execution, result: Any) -> None:
        rec, spec, journal = execution.rec, execution.spec, self.server.journal
        if result is None and spec.output is None:
            result = {}
        out_of_range = self._result_out_of_range(execution.device, spec, result)
        if out_of_range is not None:
            effect, evidence = self._completion_effect(execution)
            journal.annotate(rec, "evidence", f"result as returned (not recorded as result: {out_of_range.field} is "
                                              f"outside the declared output range): {canonical(result).decode()}"[:1000])
            journal.transition(rec, "failed", error=out_of_range.to_operation_error(), effect=effect, evidence=evidence,
                               detail=out_of_range.message[:1000])
            return
        problem = self._result_problem(execution.device, spec, result)
        if problem:
            journal.transition(rec, "failed", error=BhmsError(
                "INTERNAL", f"{spec.name} returned a result that cannot be recorded: {problem}"[:2000],
                may_have_acted=True,
                hint="the device acted but the server cannot report a valid result; read the device state")
                .to_operation_error(), detail=f"invalid result {result!r}"[:1000])
            return
        effect, evidence = self._completion_effect(execution)
        if rec.op.get("require") and effect != "verified":
            detail = "measurement contradicted the effect" if execution.confirmed else "no measurement was taken"
            journal.transition(rec, "failed", error=BhmsError(
                "UNVERIFIED", f"{spec.name} finished but its effect could not be verified ({detail})",
                may_have_acted=True, hint=f"read {execution.device.device_id}'s state before deciding what to do")
                .to_operation_error(), effect=effect, evidence=evidence, detail=detail)
            return
        journal.transition(rec, "completed", result=result, effect=effect, evidence=evidence)
        execution.device.report_alive()

    def _fault(self, execution: Execution, fault: DeviceFault) -> None:
        journal = self.server.journal
        if fault.partial:
            journal.annotate(execution.rec, "evidence", f"partial effect: {fault.partial}")
        error = BhmsError("DEVICE_FAULT", fault.message[:2000], may_have_acted=fault.proof is None,
                          hint=fault.hint or f"read {execution.device.device_id}'s state before retrying; partial "
                                             "effects are possible").to_operation_error()
        effect = fault.effect if fault.proof is None else "none"
        evidence = {"kind": "measured", "observations": fault.observations} if effect == "verified" else None
        journal.transition(execution.rec, "failed", error=error, effect=effect, evidence=evidence, proof=fault.proof)

    def _on_deadline(self, execution: Execution) -> None:
        rec = execution.rec
        if rec.settled or execution.task is None or execution.task.done():
            return
        execution.deadline_hit = True
        try:
            if execution.spec.cancel == "supported":
                if rec.op["cancel"]["state"] in ("none", "refused"):
                    self.server.journal.set_cancel(rec, "requested", reason=f"{execution.bound_kind} exceeded")
                execution.cancel_reason = "deadline"
                execution.cancelled.set()
                loop = asyncio.get_running_loop()
                execution.grace = loop.call_later(self.cancel_grace_ms / 1000, self._unobserved, execution)
            else:
                self._unobserved(execution)
        except StoreError as exc:
            self.server.journal_failed(exc)

    def _unobserved(self, execution: Execution) -> None:
        rec = execution.rec
        if rec.state in ("dispatching", "running") and execution.task is not None and not execution.task.done():
            with contextlib.suppress(StoreError):
                self.server.journal.transition(rec, "unknown", error=unknown_error(
                    f"{execution.spec.name} exceeded its {execution.bound_kind} of {execution.bound_ms} ms and its "
                    "termination was not observed"))

    # ------------------------------------------------------------------ cancellation

    def cancel(self, rec: OperationRecord, reason: str | None) -> None:
        """``operations/cancel`` for an action operation (BHMS-OPS-050..053)."""
        journal = self.server.journal
        if rec.terminal:
            return
        if rec.state == "accepted":
            self._drop_queued(rec)
            journal.set_cancel(rec, "requested", reason=reason)
            journal.transition(rec, "canceled", detail="canceled before dispatch; nothing was sent to the device")
            self.pump()
            return
        device = self.server.devices.get(rec.op.get("deviceId", ""))
        spec = device.actions.get(rec.op.get("action", "")) if device is not None else None
        if spec is None or spec.cancel != "supported":
            if rec.op["cancel"]["state"] in ("none", "requested"):
                journal.set_cancel(rec, "requested", reason=reason)
                journal.set_cancel(rec, "refused", detail="this action does not support cancellation; use stop to "
                                                          "halt the device")
            return
        if rec.op["cancel"]["state"] in ("none", "refused"):
            journal.set_cancel(rec, "requested", reason=reason)
        execution = self._running.get(rec.id)
        if execution is not None:
            execution.cancel_reason = execution.cancel_reason or "operations/cancel"
            execution.cancelled.set()

    def signal(self, rec: OperationRecord, reason: str) -> bool:
        """Set ``ctx.cancelled`` of a running handler (stop, lease loss); True when one was running."""
        execution = self._running.get(rec.id)
        if execution is None:
            return False
        execution.cancel_reason = execution.cancel_reason or reason
        execution.cancelled.set()
        return True

    def queued_for(self, device_id: str) -> list[OperationRecord]:
        """``accepted`` operations of a device that have not dispatched: queued, or in their pre-dispatch checks."""
        both = [*self._waiting, *self._pending.values()]
        return [rec for rec in both if rec.op.get("deviceId") == device_id and rec.state == "accepted"]

    def cancel_queued(self, rec: OperationRecord, detail: str) -> None:
        """Cancel a queued operation without dispatch (stop, BHMS-AUTH-021).

        An operation in its pre-dispatch checks sees the new state and sends nothing (see ``_dispatch_queued``).
        """
        if rec.state == "accepted":
            self._drop_queued(rec)
            self.server.journal.transition(rec, "canceled", detail=detail)

    def running(self) -> list[Execution]:
        return list(self._running.values())

    # ------------------------------------------------------------------ lease loss and reconciliation

    def on_lease_end(self, lease: Lease, reason: str) -> None:
        """Apply ``onLeaseLoss`` to running operations admitted under ``lease`` (BHMS-LSE-012)."""
        journal = self.server.journal
        for execution in list(self._running.values()):
            rec = execution.rec
            if rec.op.get("leaseId") != lease.lease_id or rec.settled:
                continue
            policy = execution.spec.lease_loss
            try:
                journal.annotate(rec, "lease", f"lease {lease.lease_id} {reason}; onLeaseLoss {policy}")
                if policy == "cancel" and execution.spec.cancel == "supported":
                    if rec.op["cancel"]["state"] in ("none", "refused"):
                        journal.set_cancel(rec, "requested", reason=f"lease {reason}")
                    execution.cancel_reason = "lease-lost"
                    execution.cancelled.set()
                elif policy == "hold":
                    execution.cancel_reason = "hold"
                    execution.cancelled.set()
                    hold = execution.device.hold_handler
                    if hold is not None:
                        self._spawn(_call_hook(hold, ActionContext(execution)))
                    journal.transition(rec, "failed", error=BhmsError(
                        "LEASE_EXPIRED", f"lease {lease.lease_id} {reason} while running; the device was commanded "
                        "to hold its current state", may_have_acted=True,
                        hint="read the device state, acquire a new lease and decide how to continue")
                        .to_operation_error(), detail="onLeaseLoss hold")
            except StoreError as exc:
                self.server.journal_failed(exc)

    async def reconcile(self, device: Device) -> list[OperationRecord]:
        """Ask ``device.reconcile`` about each of its ``unknown`` operations (BHMS-OPS-005)."""
        if device.reconcile_handler is None:
            return []
        changed = []
        for row in self.server.store.operations_in_states(["unknown"]):
            if row.record.get("kind") != "action" or row.record.get("deviceId") != device.device_id:
                continue
            rec = self.server.journal.get(row.id)
            if rec is not None and await self.reconcile_one(device, rec):
                changed.append(rec)
        return changed

    async def reconcile_one(self, device: Device, rec: OperationRecord) -> bool:
        """Ask the device's reconcile hook about one ``unknown`` operation; True when its answer was recorded. The call is
        bounded by the server's ``reconcile_timeout_s``; no answer, None or a refused answer leaves it ``unknown``."""
        if device.reconcile_handler is None or rec.state != "unknown" or rec.id in self._running:
            return False
        try:
            answer = await asyncio.wait_for(_call_hook(device.reconcile_handler, rec.wire(history=True)),
                                            self.server.reconcile_timeout_s)
        except DEVICE_LOSS as exc:  # the device is (still) not answering: the operation stays unknown
            log.warning("reconcile of %s by %s got no answer (%s: %s); it stays unknown", rec.id, device.device_id,
                        type(exc).__name__, exc or f"no answer in {self.server.reconcile_timeout_s} s")
            return False
        except Exception:  # noqa: BLE001 - a failing reconcile hook leaves the operation unknown
            log.exception("reconcile hook of %s failed for %s", device.device_id, rec.id)
            return False
        if rec.state != "unknown" or not isinstance(answer, Reconciled):  # settled meanwhile, or the device cannot say
            return False
        try:
            self.apply_reconciliation(rec, answer)
        except (ValueError, InvalidTransition):
            log.exception("reconcile answer of %s for %s was refused; it stays unknown", device.device_id, rec.id)
            return False
        self._resolved_event(rec, "device", None)
        return True

    def _resolved_event(self, rec: OperationRecord, source: str, principal: str | None) -> None:
        """Audit trail: every resolution of an ``unknown`` operation is an ``operation.resolved`` event (BHMS-OPS-102)."""
        data = {"state": rec.state, "source": source}
        if principal is not None:
            data["principal"] = principal
        with contextlib.suppress(StoreError):
            self.server.events.append("operation.resolved", severity="warning" if source == "operator" else "info",
                                      device_id=rec.op.get("deviceId"), operation_id=rec.id, data=data,
                                      message=f"{rec.id} left unknown: {rec.state} (resolved by {source})")

    def resolve_by_operator(self, rec: OperationRecord, principal: str, resolution: Any) -> None:
        """Record an operator's resolution of the ``unknown`` operation ``rec`` (``operations/resolve``, BHMS-OPS-102).

        ``resolution`` is the validated ``OperatorResolution``. The same rules as for device evidence apply (a result
        must match the action's output, ``verified`` needs measured and valid observations, "nothing happened" needs
        ``effect: none``); what breaks one is refused with the member of ``resolution`` it concerns, and nothing is
        recorded. The history entry is a ``reconciliation`` marked with the operator and the stated basis.
        """
        given = resolution.model_fields_set
        observations = {name: to_wire(obs) for name, obs in (resolution.observations or {}).items()} or None
        device = self.server.devices.get(rec.op.get("deviceId", ""))
        spec = device.actions.get(rec.op.get("action", "")) if device is not None else None
        if resolution.state == "completed" and device is not None and spec is not None:
            result = resolution.result if "result" in given else ({} if spec.output is None else None)
            refusal = self._result_out_of_range(device, spec, result)
            if refusal is not None:
                raise BhmsError("OUT_OF_RANGE", f"resolution.{refusal.field} is outside the declared output range of "
                                f"{spec.name}", field=f"resolution.{refusal.field}", bound=refusal.bound,
                                hint="state the result the device produced, or resolve the operation as failed")
            problem = self._result_problem(device, spec, result)
            if problem:
                raise BhmsError("INVALID_ARGUMENT", f"resolution.result cannot be recorded: {problem}"[:2000],
                                field="resolution.result", hint=f"state completed needs a result that matches the "
                                f"output of {spec.name} (bhms describe shows it); or resolve the operation as failed")
        try:
            answer = Reconciled(resolution.state, evidence=resolution.basis, effect=resolution.effect,
                                result=resolution.result if "result" in given else None, message=resolution.basis,
                                may_have_acted=True if resolution.may_have_acted is None else resolution.may_have_acted,
                                observations=observations)
        except ValueError as exc:
            raise BhmsError("INVALID_ARGUMENT", f"the resolution is not acceptable: {exc}"[:2000],
                            field="resolution.observations", hint="observations must be measured and valid to support "
                            "effect verified; otherwise state effect unverified") from None
        try:
            self.apply_reconciliation(rec, answer, operator={"principal": principal, "basis": resolution.basis})
        except (ValueError, InvalidTransition) as exc:
            raise BhmsError("INVALID_ARGUMENT", f"the resolution cannot be recorded: {exc}"[:2000], field="resolution",
                            hint="check state, effect and result against the operation (a required verified effect "
                                 "needs measured observations)") from None
        self._resolved_event(rec, "operator", principal)

    def apply_reconciliation(self, rec: OperationRecord, answer: Reconciled, *,
                             operator: dict[str, str] | None = None) -> None:
        """Record a ``Reconciled`` answer; the invariants of ``Journal.transition`` apply as to any completion. With
        ``operator`` the answer is an operator's statement, and the history entry says so."""
        journal = self.server.journal
        detail = (f"operator resolution by {operator['principal']}: {answer.evidence}" if operator is not None
                  else f"reconciled from device evidence: {answer.evidence}")
        device = self.server.devices.get(rec.op.get("deviceId", ""))
        spec = device.actions.get(rec.op.get("action", "")) if device is not None else None
        evidence = {"kind": "measured", "observations": answer.observations} if answer.observations else None
        if answer.state == "completed":
            result = answer.result if answer.result is not None else {}
            problem = self._result_problem(device, spec, result) if device is not None and spec is not None else None
            if problem:
                raise ValueError(f"Reconciled.result of {rec.id} cannot be recorded: {problem}")
            effect = answer.effect or ("none" if rec.private.get("effectClass") == "none" else "unverified")
            if rec.op.get("require", {}).get("effect") == "verified" and effect != "verified":
                journal.transition(rec, "failed", error=BhmsError(
                    "UNVERIFIED", f"{rec.op.get('action')} was found to have finished, but the required verified "
                    "effect could not be established", may_have_acted=True,
                    hint="read the device state before deciding what to do").to_operation_error(),
                    effect=effect, kind="reconciliation", detail=detail, operator=operator)
                return
            journal.transition(rec, "completed", result=result, effect=effect, evidence=evidence,
                               kind="reconciliation", detail=detail, operator=operator)
        elif answer.state == "failed":
            error = BhmsError(answer.code if answer.code in ("DEVICE_FAULT", "DEADLINE_EXCEEDED", "INTERNAL")
                              else "DEVICE_FAULT", (answer.message or answer.evidence)[:2000],
                              may_have_acted=answer.may_have_acted,
                              hint="read the device state before retrying").to_operation_error()
            journal.transition(rec, "failed", error=error, effect=answer.effect, evidence=evidence, kind="reconciliation",
                               detail=detail, proof=None if answer.may_have_acted else answer.evidence, operator=operator)
        else:
            journal.transition(rec, answer.state, effect=answer.effect, evidence=evidence, kind="reconciliation",
                               detail=detail, operator=operator)


def _ijson_violation(value: Any, path: str) -> str | None:
    """Name the first member of ``value`` that breaks the I-JSON number rule (BHMS-OPS-008), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and not -(2 ** 53 - 1) <= value <= 2 ** 53 - 1:
        return (f"{path} is the integer {value}, beyond +/-2^53 (9007199254740991); results are I-JSON, so numbers must "
                "be exactly representable as IEEE 754 doubles: return it as a string, or as a float if rounding is "
                "acceptable")
    if isinstance(value, float) and not math.isfinite(value):
        return f"{path} is {value}; NaN and Infinity are not JSON numbers: return null or a string"
    if isinstance(value, dict):
        for key, item in value.items():
            if found := _ijson_violation(item, f"{path}.{key}"):
                return found
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            if found := _ijson_violation(item, f"{path}[{index}]"):
                return found
    return None


async def _call_hook(hook: Any, *args: Any) -> Any:
    outcome = hook(*args)
    if inspect.isawaitable(outcome):
        return await outcome
    return outcome


__all__ = ["Execution", "Executor"]
