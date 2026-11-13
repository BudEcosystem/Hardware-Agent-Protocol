"""The fault plane: inject device and world faults at a time or on an event.

A fault is data: ``Fault(target, kind, when, params)``. ``when`` is ``At(time_s)`` or ``OnEvent(kind, device=None)``
(an effect of that kind appears in the log; ``params["delay_s"]`` postpones the fault after the trigger, so
``OnEvent("move_started")`` with ``delay_s=0.5`` drops an object half a second into a carry). The kinds implemented
here are the V1 set of the validation plan; they correspond to the classes of validation plan §3.3 that act *inside the
world*:

=================== ===== =========================================================================================
kind                class effect
=================== ===== =========================================================================================
``drop_object``     F14   the container ``target`` is lost (``params["require_location"]`` limits it to e.g. a carry)
``joint_stall``     F8    the joint ``target`` of the arm cannot move until cleared
``knob_slip``       F8    a knob train loses ``params["slip_rad"]`` of rotation (axis moves less than the knob)
``stale_camera``    F6    the camera ``target`` keeps returning its last frame until cleared
``sensor_disconnect`` F7  the sensor/device ``target`` returns invalid readings until cleared
``manual_move``     F9    a human turns the knob joint ``target`` by ``params["delta_rad"]`` (``cause=None``)
``power_loss``      F3    the device ``target`` loses power: its actions fail and it reports offline until cleared
=================== ===== =========================================================================================

Persistent kinds stay *active* until ``clear``; the others act once when they fire. Every injection and firing is an
effect on the ``fault`` device, so the oracle and the report can see exactly what was done to the world.

Message-level faults (F1, F2, F4, F10-F13, F15, F16) belong to the transport and runtime layers; ``simlab.runs`` drives
them around the twins.

Thread-safety: owned by one world.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from simlab.world import Effect, World

PERSISTENT = frozenset({"joint_stall", "stale_camera", "sensor_disconnect", "power_loss"})
ONE_SHOT = frozenset({"drop_object", "knob_slip", "manual_move"})
KINDS = PERSISTENT | ONE_SHOT


@dataclass(frozen=True)
class At:
    """Fire when the world clock reaches ``time_s``."""

    time_s: float


@dataclass(frozen=True)
class OnEvent:
    """Fire when an effect of ``kind`` (optionally from ``device``) is recorded."""

    kind: str
    device: str | None = None


@dataclass(frozen=True)
class Fault:
    target: str
    kind: str
    when: At | OnEvent
    params: dict[str, Any] = field(default_factory=dict)


class FaultPlane:
    """Injects faults into one world and answers 'is this fault active?' for the twins."""

    def __init__(self, world: World) -> None:
        self.world = world
        self._ids = itertools.count(1)
        self._pending: dict[str, tuple[Fault, float | None]] = {}  # id -> (fault, fire time once triggered)
        self._active: dict[str, Fault] = {}
        self._listeners: list[Callable[[str, Fault], None]] = []

    def inject(self, fault: Fault) -> str:
        """Arm a fault; returns its id."""
        if fault.kind not in KINDS:
            raise ValueError(f"unknown fault kind {fault.kind!r}; use one of {sorted(KINDS)}")
        fault_id = f"fault-{next(self._ids)}"
        fire = fault.when.time_s if isinstance(fault.when, At) else None
        self._pending[fault_id] = (fault, fire)
        self.world.record("fault", "fault_injected", {"id": fault_id, "target": fault.target, "kind": fault.kind}, None)
        return fault_id

    def clear(self, fault_id: str) -> None:
        """Remove a fault (pending or active); a persistent fault's consequences end, one-shot ones are not undone."""
        was_active = self._active.pop(fault_id, None)
        fault = was_active or (self._pending.pop(fault_id, (None, None))[0])
        if fault is None:
            raise KeyError(f"no fault {fault_id!r}")
        if was_active is not None:
            for listener in self._listeners:
                listener("cleared", fault)
        if fault.kind == "joint_stall":
            self.world.record("world", "joint_released", {"joint": fault.target}, None)
        self.world.record("fault", "fault_cleared", {"id": fault_id, "target": fault.target, "kind": fault.kind}, None)

    def subscribe(self, listener: Callable[[str, Fault], None]) -> None:
        """Call ``listener("active" | "cleared", fault)`` when a persistent fault starts or ends (twins use it to
        report power loss as device status)."""
        self._listeners.append(listener)

    def active(self, target: str, kind: str) -> bool:
        """Whether a persistent fault of ``kind`` is active on ``target`` (twins consult this)."""
        return any(f.target == target and f.kind == kind for f in self._active.values())

    def stalled_joints(self) -> frozenset[str]:
        return frozenset(f.target for f in self._active.values() if f.kind == "joint_stall")

    def snapshot(self) -> dict[str, Any]:
        return {"pending": sorted(self._pending), "active": sorted(self._active)}

    # ------------------------------------------------------------------ triggers

    def on_time(self, time_s: float) -> None:
        for fault_id, (fault, fire) in list(self._pending.items()):
            if fire is not None and time_s + 1e-9 >= fire:
                self._fire(fault_id, fault)

    def on_effect(self, effect: Effect) -> None:
        for fault_id, (fault, fire) in list(self._pending.items()):
            when = fault.when
            if fire is None and isinstance(when, OnEvent) and when.kind == effect.kind \
                    and (when.device is None or when.device == effect.device) and self._eligible(fault):
                delay = float(fault.params.get("delay_s", 0.0))
                if delay <= 0:
                    self._fire(fault_id, fault)
                else:
                    self._pending[fault_id] = (fault, effect.time_s + delay)

    def _eligible(self, fault: Fault) -> bool:
        required = fault.params.get("require_location")
        return required is None or self.world.ledger.location(fault.target) == required

    # ------------------------------------------------------------------ consequences

    def _fire(self, fault_id: str, fault: Fault) -> None:
        self._pending.pop(fault_id, None)
        world = self.world
        if fault.kind in PERSISTENT:
            self._active[fault_id] = fault
            for listener in self._listeners:
                listener("active", fault)
        if fault.kind == "drop_object":
            if world.ledger.location(fault.target) == "lost":
                return
            world.record("world", "object_dropped", {"container": fault.target,
                                                     "from": world.ledger.location(fault.target)}, None)
            world.ledger.move(fault.target, "lost", None)
        elif fault.kind == "manual_move":
            world.turn_joint(fault.target, float(fault.params["delta_rad"]), cause=None)
        elif fault.kind == "knob_slip":
            slip = float(fault.params["slip_rad"])
            world.knobs[fault.target].slip_offset -= slip
            world.record("world", "knob_slipped", {"joint": fault.target, "slip_rad": slip}, None)
        elif fault.kind == "joint_stall":
            world.record("world", "joint_stalled", {"joint": fault.target}, None)
        world.record("fault", "fault_fired", {"id": fault_id, "target": fault.target, "kind": fault.kind}, None)
