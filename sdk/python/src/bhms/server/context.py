"""What device code receives and raises: :class:`ActionContext`, outcomes and readings.

An action handler gets an :class:`ActionContext` as its ``ctx`` parameter:

* ``ctx.cancelled`` — an :class:`asyncio.Event` set when ``operations/cancel``, a duration bound, a lease loss with
  ``onLeaseLoss: "cancel"``/``"hold"``, or ``stop`` asks the action to end. Honour it and raise :class:`Canceled` once the
  device has observably stopped (``cancel.state: "confirmed"``, BHMS-OPS-052); returning normally means the action
  completed (completion may win the race).
* ``await ctx.progress(0.5)`` / ``await ctx.progress(3, 10)`` — progress; the first call records ``running`` ("the device
  reported that it is executing", §6.3). ``await ctx.running()`` records it without progress.
* ``await ctx.verify("position", lambda v: abs(v - target) < 0.1)`` — take a fresh measurement of a property and, when
  it is ``measured``, ``valid`` and passes the check, attach it as evidence: only then is the effect ``verified``
  (BHMS-DEV-031, BHMS-OPS-006). Returns the measured value (``None`` when invalid).
* ``await ctx.read(prop, ...)``, ``await ctx.publish(prop, value)``, ``ctx.emit(type, data)``,
  ``await ctx.acknowledge_cancel()``, ``ctx.remaining_ms``.

Outcomes other than a normal return:

* ``raise Canceled(effect=...)`` — terminated after a cancel request (``canceled``);
* ``raise DeviceFault("stalled", partial="moved 2 mm")`` — the device reported a fault while acting (``failed`` with
  ``DEVICE_FAULT``, ``mayHaveActed: true`` unless ``proof`` names device evidence of no effect, BHMS-ERR-012);
* any other exception — the outcome is ``unknown`` (``DEADLINE_EXCEEDED``, BHMS-OPS-004): a handler bug after dispatch
  cannot prove what the device did.

A property getter may return a bare value (``valid``, the declared evidence, acquired now) or a :class:`Reading`; a
getter that raises, times out or returns ``None`` produces ``quality: "invalid"`` with ``value: null`` — never a
substitute value (BHMS-OBS-001).

A ``reconcile`` hook returns :class:`Reconciled` (or None to leave the operation ``unknown``).

Thread-safety: a context belongs to one operation on the server's event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bhms.server.device import Device
    from bhms.server.executor import Execution


class Canceled(Exception):  # noqa: N818 - an outcome, named after the operation state it produces
    """Raised by a handler that terminated because of a cancellation request.

    ``effect``: what is known about the partial effect (``unknown`` by default; ``unverified`` when the device moved
    without measurement; ``none`` only with proof nothing happened). ``detail`` is recorded in history.
    """

    def __init__(self, *, effect: str = "unknown", detail: str | None = None) -> None:
        if effect not in ("none", "verified", "unverified", "unknown"):
            raise ValueError("effect must be none, verified, unverified or unknown")
        super().__init__(detail or "canceled")
        self.effect, self.detail = effect, detail


class DeviceFault(Exception):
    """The device reported a fault while acting: the operation ends ``failed`` with ``DEVICE_FAULT``.

    Args:
        message: what the device reported (recorded in ``error.message``).
        partial: description of partial effects (recorded in history; BHMS-PRG-011 / "partial effects recorded").
        hint: what the caller should do next (default: read the device state before retrying).
        proof: device evidence that nothing happened; only then is ``mayHaveActed`` false (BHMS-OPS-009).
        effect: ``unknown`` (default), ``unverified`` or ``none`` (with ``proof``).
    """

    def __init__(self, message: str, *, partial: str | None = None, hint: str | None = None, proof: str | None = None,
                 effect: str = "unknown") -> None:
        super().__init__(message)
        self.message, self.partial, self.hint, self.proof, self.effect = message, partial, hint, proof, effect


@dataclass(frozen=True)
class Reading:
    """A property value with explicit quality and provenance (returned by a getter instead of a bare value).

    ``acquired_at_ns``: device timestamp (wall clock ns) when known; ``latency_ms``: bounded acquisition latency added to
    the age (BHMS-OBS-003; ``None`` = unbounded, which makes ``ageMs`` null and fails every ``maxAgeMs``).
    """

    value: Any
    quality: str = "valid"
    evidence: str | None = None
    uncertainty: float | None = None
    source: str | None = None
    latency_ms: float | None = 0.0
    acquired_at_ns: int | None = None


@dataclass(frozen=True)
class Reconciled:
    """The resolution of an ``unknown`` operation from device evidence (BHMS-OPS-005).

    ``state``: ``completed`` (with ``result``), ``failed`` (with ``message``), ``canceled`` or ``running``.
    ``evidence``: names the evidence (``"encoder reads 12.5 mm"``); recorded in the reconciliation entry.
    """

    state: str
    evidence: str
    result: Any = None
    effect: str | None = None
    message: str | None = None
    may_have_acted: bool = True
    code: str = "DEVICE_FAULT"

    def __post_init__(self) -> None:
        if self.state not in ("completed", "failed", "canceled", "running"):
            raise ValueError("Reconciled.state must be completed, failed, canceled or running")
        if not self.evidence:
            raise ValueError("Reconciled needs evidence naming what proves the outcome (BHMS-OPS-005)")


class ActionContext:
    """Per-operation handle given to action handlers; see the module docstring."""

    def __init__(self, execution: Execution) -> None:
        self._execution = execution
        self.cancelled: asyncio.Event = execution.cancelled

    @property
    def operation_id(self) -> str:
        return self._execution.rec.id

    @property
    def device(self) -> Device:
        return self._execution.device

    @property
    def action(self) -> str:
        return self._execution.spec.name

    @property
    def arguments(self) -> dict[str, Any]:
        """The admitted arguments (defaults applied, quantities replaced by values)."""
        return dict(self._execution.admitted)

    @property
    def principal(self) -> str:
        return self._execution.rec.principal

    @property
    def lease_id(self) -> str | None:
        return self._execution.rec.op.get("leaseId")

    @property
    def fence(self) -> int | None:
        """The fence the operation was admitted under; forward it to any downstream enforcement point (BHMS-LSE-011)."""
        return self._execution.rec.op.get("fence")

    @property
    def remaining_ms(self) -> float:
        """Milliseconds until the earlier of ``maxDurationMs`` and the client deadline."""
        return max(0.0, (self._execution.deadline - asyncio.get_running_loop().time()) * 1000)

    @property
    def cancel_reason(self) -> str | None:
        """Why ``cancelled`` was set (``operations/cancel``, ``deadline``, ``lease-lost``, ``stop``)."""
        return self._execution.cancel_reason

    async def running(self, detail: str | None = None) -> None:
        """Record that the device reports it is executing (``dispatching`` -> ``running``)."""
        self._execution.mark_running(detail)

    async def progress(self, done: float, total: int | None = None) -> None:
        """Report progress: a fraction in [0, 1] (stored as per-mille steps) or ``done`` of ``total`` steps."""
        if total is None:
            if not 0 <= done <= 1:
                raise ValueError("progress fraction must be in [0, 1]; pass total= for step counts")
            steps, total = round(done * 1000), 1000
        else:
            steps = int(done)
        self._execution.mark_running(None)
        self._execution.server.journal.set_progress(self._execution.rec, {"stepsCompleted": steps,
                                                                          "stepsTotal": int(total)})

    async def acknowledge_cancel(self, detail: str | None = None) -> None:
        """Record that the device received the cancellation request (``cancel.state: acknowledged``, BHMS-OPS-052)."""
        rec = self._execution.rec
        if not rec.settled and rec.op["cancel"]["state"] == "requested":
            self._execution.server.journal.set_cancel(rec, "acknowledged", detail=detail)

    async def read(self, property: str, *, max_age_ms: int | None = None, fresh: bool = True) -> dict[str, Any]:
        """An ``Observation`` of a property of this device, acquired under the operation's own authority."""
        return await self._execution.server.observations.read(self.device, property, max_age_ms=max_age_ms,
                                                              fresh=fresh, internal=True)

    async def verify(self, property: str, check: Callable[[Any], bool] | None = None, *,
                     max_age_ms: int | None = None) -> Any:
        """Measure ``property`` now and attach it as evidence when it confirms the effect; returns its value."""
        observation = await self.read(property, max_age_ms=max_age_ms, fresh=max_age_ms is None)
        value = observation.get("value")
        confirmed = observation["quality"] == "valid" and observation["evidence"] == "measured"
        if confirmed and check is not None:
            confirmed = bool(check(value))
        self._execution.add_evidence(property, observation, confirmed)
        return value

    async def publish(self, property: str, value: Any, **kw: Any) -> dict[str, Any]:
        """Record a new acquisition of a property of this device (for subscribers and later reads)."""
        return await self.device.publish(property, value, **kw)

    def emit(self, event_type: str, data: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        """Append a declared device event tied to this operation."""
        return self.device.emit(event_type, data, operation_id=self.operation_id, **kw)

    async def wait_cancelled(self, timeout: float | None = None) -> bool:
        """Sleep up to ``timeout`` seconds, waking early on cancellation; returns whether it was cancelled."""
        try:
            await asyncio.wait_for(self.cancelled.wait(), timeout)
        except asyncio.TimeoutError:
            return False
        return True


__all__ = ["ActionContext", "Canceled", "DeviceFault", "Reading", "Reconciled"]
