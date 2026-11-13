"""The ``stop`` fast path (spec/bhms/07-leases-and-authority.md §7.5, 13-security.md §13.5).

:class:`StopController` never waits for, or is blocked by, a lease, a queue, an in-flight operation or a held resource
(BHMS-AUTH-020): it takes no lock, dispatches each device's commissioned stop procedure (``@device.on_stop``)
first (a synchronous handler has run before any journal write; a coroutine handler takes its first step before one),
and only then does the bookkeeping of BHMS-AUTH-021 in this order:

1. dispatch the stop procedure (when ``safety.stop`` is ``supported``);
2. move the device's ``accepted`` operations (queued, or in their pre-dispatch checks) to ``canceled``
   (``effect: none``; listed in ``canceledOperations``);
3. append a ``stop`` history entry and a cancellation request to its ``dispatching``/``running``/``unknown`` operations
   (setting ``ctx.cancelled`` of running handlers; listed in ``cancelRequestedOperations``: only requested, not
   confirmed) and stop programs with steps on it (BHMS-PRG-014);
4. revoke every active lease covering its resources, raising their fences;
5. record a ``stop`` event.

The result reports ``confirmed`` only when the stop procedure returned (``reported``/``measured`` evidence per the
device's ``stopEvidence``, BHMS-AUTH-022), ``initiated`` when it has not finished within ``waitMs`` (a later ``stop``
event carries the outcome, BHMS-AUTH-024), ``unsupported`` without a procedure, and ``failed`` for unknown devices
(the request itself still succeeds, BHMS-AUTH-023) or a procedure that raised. A confirmed stop lifts the
unknown-operation inhibition of the device's operations (BHMS-OPS-042).

When the journal cannot be written the stop still runs, the result says ``detail: "degraded-audit"`` and ordinary
operations are refused until the journal is writable again (BHMS-AUTH-025). Stop takes no motion parameters
(BHMS-AUTH-026: ``StopParams`` is closed).

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bhms.protocol.errors import BhmsError
from bhms.runtime.store import StoreError

if TYPE_CHECKING:
    from bhms.runtime.authority import Principal
    from bhms.server.device import Device
    from bhms.server.server import DeviceServer

log = logging.getLogger("bhms.stop")


@dataclass(frozen=True)
class StopContext:
    """What a stop procedure receives: the device and the stop reason (no motion parameters, BHMS-AUTH-026)."""

    device: Device
    reason: str


class StopController:
    """Executes ``stop`` for one server; see the module docstring."""

    def __init__(self, server: DeviceServer) -> None:
        self.server = server
        self.tasks: set[asyncio.Task[Any]] = set()

    async def stop(self, principal: Principal, params: Any) -> list[dict[str, Any]]:
        srv = self.server
        wait_ms = params.wait_ms or 0
        if wait_ms > srv.max_wait_ms:
            raise BhmsError("OUT_OF_RANGE", f"waitMs {wait_ms} is above limits.maxWaitMs {srv.max_wait_ms}",
                            field="waitMs", bound={"maximum": srv.max_wait_ms},
                            hint=f"send waitMs of at most {srv.max_wait_ms}; later outcomes arrive as stop events")
        if not principal.may_stop_any:
            raise BhmsError("UNAUTHORIZED", "stop needs the stop scope",
                            hint="missing scope stop or stop:<deviceGlob> (BHMS-AUTH-020)")
        if params.scope == "all":
            targets = [d for d in sorted(srv.devices) if principal.can_stop(d)]
        else:
            targets = list(dict.fromkeys(params.device_ids))
        # 1. dispatch every stop procedure before any bookkeeping
        procedures: dict[str, asyncio.Future[Any] | None] = {}
        for device_id in targets:
            dev = srv.devices.get(device_id)
            if dev is not None and principal.can_stop(device_id) and dev.stop_spec is not None:
                procedures[device_id] = self._begin_procedure(dev, params.reason)
            else:
                procedures[device_id] = None
        await asyncio.sleep(0)  # coroutine procedures take their first step before any journal write (AUTH-025)
        results = []
        for device_id in targets:
            results.append(self._settle_device(principal, device_id, params.reason, procedures[device_id]))
        pending = [t for t in procedures.values() if t is not None and not t.done()]
        if pending and wait_ms:
            await asyncio.wait(pending, timeout=wait_ms / 1000)
        else:
            await asyncio.sleep(0)  # let procedures that finish synchronously report
        out = []
        for device_id, (result, degraded) in zip(targets, results, strict=True):
            out.append(self._outcome(device_id, result, procedures[device_id], params.reason, degraded))
        return out

    def _begin_procedure(self, dev: Device, reason: str) -> asyncio.Future[Any]:
        """Call the stop handler now: a synchronous one has run (or raised) when this returns, with no journal write
        before it; an awaitable one is spawned as a task. The returned future carries the outcome."""
        assert dev.stop_spec is not None
        done: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        try:
            outcome = dev.stop_spec.handler(StopContext(dev, reason))
        except Exception as exc:  # noqa: BLE001 - reported as outcome "failed"
            done.set_exception(exc)
            return done
        if inspect.isawaitable(outcome):
            return self._spawn(_await(outcome))
        done.set_result(outcome)
        return done

    def _spawn(self, coro: Any) -> asyncio.Task[Any]:
        task = asyncio.get_running_loop().create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def _settle_device(self, principal: Principal, device_id: str, reason: str,
                       procedure: asyncio.Future[Any] | None) -> tuple[dict[str, Any], bool]:
        srv = self.server
        dev = srv.devices.get(device_id)
        if dev is None or not principal.can_stop(device_id):
            code, text = ("UNAUTHORIZED", f"you may not stop {device_id}") if dev is not None and principal.can_read \
                else ("UNKNOWN_DEVICE", f"no device {device_id!r}")
            error = BhmsError(code, text, hint="nothing was stopped on this device; check the id and your stop scope")
            return {"deviceId": device_id, "outcome": "failed", "evidence": "none", "canceledOperations": [],
                    "revokedLeases": [], "error": error.to_operation_error()}, False
        degraded = False
        canceled: list[str] = []  # moved to ``canceled`` (they had not dispatched)
        requested: list[str] = []  # in flight or unknown: a cancellation was requested, the outcome is not yet known
        journal = srv.journal
        # 2. accepted (queued) operations: canceled without dispatch
        for rec in srv.executor.queued_for(device_id):
            try:
                journal.annotate(rec, "stop", f"stop: {reason}")
                srv.executor.cancel_queued(rec, f"canceled by stop before dispatch: {reason}")
                canceled.append(rec.id)
            except StoreError as exc:
                degraded = True
                srv.journal_failed(exc)
        # 3. in-flight and unknown operations: stop entry and a cancellation request
        for rec in self._operations_on(dev):
            try:
                journal.annotate(rec, "stop", f"stop: {reason}")
                if rec.op["cancel"]["state"] in ("none", "refused"):
                    journal.set_cancel(rec, "requested", reason=f"stop: {reason}")
                requested.append(rec.id)
            except StoreError as exc:
                degraded = True
                srv.journal_failed(exc)
            srv.executor.signal(rec, "stop")
        degraded = srv.programs.stop_device(device_id, reason) or degraded
        # 4. leases on its resources
        revoked = [lease.lease_id for lease in srv.leases.revoke_covering(dev.resources, reason="stop")]
        # 5. event
        try:
            srv.events.append("stop", severity="warning", device_id=device_id, message=reason[:1000],
                              data={"outcome": "initiated" if procedure is not None else "unsupported",
                                    "reason": reason})
        except StoreError as exc:
            degraded = True
            srv.journal_failed(exc)
        if procedure is not None:
            procedure.add_done_callback(lambda task: self._finished(dev, reason, task))
        partial: dict[str, Any] = {"deviceId": device_id, "canceledOperations": canceled, "revokedLeases": revoked}
        if requested:
            partial["cancelRequestedOperations"] = requested
        return partial, degraded

    def _operations_on(self, dev: Device) -> list[Any]:
        srv = self.server
        found = {rec.id: rec for rec in srv.journal.live()
                 if rec.op.get("deviceId") == dev.device_id and rec.op["kind"] == "action"
                 and rec.state in ("dispatching", "running")}
        for row in srv.store.operations_in_states(["unknown"]):
            if row.record.get("deviceId") == dev.device_id and row.record.get("kind") == "action":
                rec = srv.journal.get(row.id)
                if rec is not None:
                    found[rec.id] = rec
        return list(found.values())

    def _outcome(self, device_id: str, partial: dict[str, Any], procedure: asyncio.Future[Any] | None, reason: str,
                 degraded: bool) -> dict[str, Any]:
        srv = self.server
        if "outcome" in partial:
            return partial
        dev = srv.devices[device_id]
        result = {"deviceId": device_id, **partial}
        if procedure is None:
            result.update(outcome="unsupported", evidence="none",
                          detail="no commissioned stop procedure; operations were cancelled and leases revoked")
        elif not procedure.done():
            result.update(outcome="initiated", evidence="none")
        elif procedure.exception() is not None:
            exc = procedure.exception()
            result.update(outcome="failed", evidence="none", error=BhmsError(
                "DEVICE_FAULT", f"the stop procedure failed: {exc}"[:2000], may_have_acted=True,
                hint="the device may not be stopped: use the installation's independent emergency stop if needed "
                     "and check the device").to_operation_error())
        else:
            assert dev.stop_spec is not None
            result.update(outcome="confirmed", evidence=dev.stop_spec.evidence)
        if degraded or not srv.journal_ok:
            result["detail"] = "degraded-audit"
        return result

    def _finished(self, dev: Device, reason: str, task: asyncio.Future[Any]) -> None:
        srv = self.server
        if task.cancelled():
            return
        exc = task.exception()
        outcome = "failed" if exc is not None else "confirmed"
        if outcome == "confirmed":
            self._lift(dev)
        with contextlib.suppress(StoreError):
            srv.events.append("stop", severity="warning" if outcome == "confirmed" else "error",
                              device_id=dev.device_id,
                              message=reason[:1000] if exc is None else f"stop procedure failed: {exc}"[:1000],
                              data={"outcome": outcome, "reason": reason})

    def _lift(self, dev: Device) -> None:
        """A confirmed stop lifts the unknown-operation inhibition of the device (BHMS-OPS-042)."""
        srv = self.server
        for rec in self._operations_on(dev):
            if rec.state == "unknown":
                srv.executor.lift_inhibition(rec)
                with contextlib.suppress(StoreError):
                    srv.journal.mark_private(rec, inhibitionLifted=True)
                    srv.journal.annotate(rec, "stop", "a confirmed stop lifted the resource inhibition; the outcome "
                                                      "is still unknown")
        srv.executor.pump()

    async def close(self) -> None:
        if self.tasks:
            await asyncio.wait(list(self.tasks), timeout=5.0)


async def _await(outcome: Any) -> Any:
    return await outcome


__all__ = ["StopContext", "StopController"]
