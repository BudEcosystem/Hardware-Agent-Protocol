"""Centrifuge twin: lid interlock, spin programs and imbalance refusal.

The rotor has ``POSITIONS`` slots; tubes are ledger containers at the sites ``centrifuge_rotor_<n>``. The rotor speed is a
pure function of world time and the running program (ramp up at ``ACCEL_HZ_S``, hold for the requested time, ramp down at
``DECEL_HZ_S``), like the thermal block: exact and deterministic.

Rules the twin enforces, not the agent: the lid is locked while the rotor turns faster than ``LOCK_HZ`` (an open request
is refused with proof that nothing moved); a spin is refused with the lid open; a spin is refused when opposite rotor
positions differ by more than ``IMBALANCE_LIMIT_G`` (an empty opposite position counts as zero mass), which is the check a
real unit makes before it spins up. Tube mass is taken from the ledger (``TUBE_MASS_G`` plus liquid at 1 g/mL).

The SDK's unit registry has no revolutions per minute, so speeds are in Hz (rotations per second; 10 000 rpm = 166.7 Hz);
see the report under "SDK gaps".

Sensing: ``speed`` is ``measured`` (tachometer, noise sigma ``TACH_SIGMA_HZ``); ``lid_open`` is a ``measured`` switch;
``lid_locked`` is ``reported`` by the interlock. ``CentrifugeModel`` is shared with the OPC UA instrument
(``instruments/opcua_centrifuge``).

Thread-safety: belongs to its world's thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bhms.server.context import DeviceFault
from bhms.server.decorators import Range
from bhms.server.server import DeviceServer
from simlab.simdevice import TwinHost, make_server, simulated_device
from simlab.world import World

POSITIONS = 8
ACCEL_HZ_S = 10.0
DECEL_HZ_S = 8.0
LOCK_HZ = 0.5
MAX_HZ = 250.0
IMBALANCE_LIMIT_G = 1.0
TUBE_MASS_G = 10.0
TACH_SIGMA_HZ = 0.05
LID_S = 1.5


def rotor_site(position: int) -> str:
    return f"centrifuge_rotor_{position}"


@dataclass(frozen=True)
class _Program:
    started_s: float
    speed_hz: float
    hold_s: float

    def ramp_up_s(self) -> float:
        return self.speed_hz / ACCEL_HZ_S

    def total_s(self) -> float:
        return self.ramp_up_s() + self.hold_s + self.speed_hz / DECEL_HZ_S


class CentrifugeModel:
    """Lid, rotor and program state over the ledger."""

    def __init__(self, world: World, *, device: str = "centrifuge-1") -> None:
        self.world, self.device = world, device
        self.lid_open = False
        self._program: _Program | None = None

    # ------------------------------------------------------------------ rotor

    def speed_hz(self) -> float:
        """The true rotor speed now."""
        program = self._program
        if program is None:
            return 0.0
        t = self.world.time_s - program.started_s
        if t >= program.total_s():
            return 0.0
        if t < program.ramp_up_s():
            return ACCEL_HZ_S * t
        if t < program.ramp_up_s() + program.hold_s:
            return program.speed_hz
        return max(0.0, program.speed_hz - DECEL_HZ_S * (t - program.ramp_up_s() - program.hold_s))

    def running(self) -> bool:
        return self._program is not None and self.world.time_s - self._program.started_s < self._program.total_s()

    def lid_locked(self) -> bool:
        return self.running() or self.speed_hz() > LOCK_HZ

    def program_seconds(self) -> float:
        return 0.0 if self._program is None else self._program.total_s()

    def tube_mass_g(self, position: int) -> float:
        ledger = self.world.ledger
        total = 0.0
        for container in ledger.containers_at(rotor_site(position)):
            total += TUBE_MASS_G + sum(ledger.well(container, w).volume_ul for w in ledger.wells(container)) * 1e-3
        return total

    def imbalance_g(self) -> float:
        half = POSITIONS // 2
        return max(abs(self.tube_mass_g(n) - self.tube_mass_g(n + half)) for n in range(1, half + 1))

    # ------------------------------------------------------------------ commands

    def set_lid(self, open_: bool, cause: str | None) -> None:
        """Open or close the lid. Refused (``PermissionError``) while the rotor turns."""
        if open_ and self.lid_locked():
            raise PermissionError("the lid is locked while the rotor is turning")
        self.lid_open = open_
        self.world.record(self.device, "lid_opened" if open_ else "lid_closed", {}, cause)

    def start(self, speed_hz: float, hold_s: float, cause: str | None) -> float:
        """Start a spin program; returns its total duration in world seconds. Refusals raise ``PermissionError`` (lid
        open, already spinning) or ``ValueError`` (imbalance)."""
        if self.lid_open:
            raise PermissionError("the lid is open")
        if self.running():
            raise PermissionError("a spin program is already running")
        if self.imbalance_g() > IMBALANCE_LIMIT_G:
            raise ValueError(f"rotor imbalance {self.imbalance_g():.2f} g exceeds {IMBALANCE_LIMIT_G} g")
        self._program = _Program(self.world.time_s, speed_hz, hold_s)
        self.world.record(self.device, "spin_started", {"speed_hz": speed_hz, "hold_s": hold_s,
                                                        "imbalance_g": round(self.imbalance_g(), 4)}, cause)
        return self._program.total_s()

    def abort(self, cause: str | None) -> None:
        """Brake: the rotor decelerates from its present speed (the lid stays locked until it is below ``LOCK_HZ``)."""
        if not self.running():
            self.world.record(self.device, "spin_abort_ignored", {"running": False}, cause)  # nothing to brake: no execution
            return
        self.world.record(self.device, "spin_abort_requested", {"running": True}, cause)
        speed, now = self.speed_hz(), self.world.time_s
        self._program = _Program(now - speed / ACCEL_HZ_S, speed, 0.0)
        self.world.record(self.device, "spin_aborted", {"speed_hz": round(speed, 3)}, cause)

    def record_speed(self, cause: str | None) -> float:
        """Record the true rotor speed now (the achieved truth the oracle judges a claim against)."""
        speed = self.speed_hz()
        self.world.record(self.device, "spin_reached", {"speed_hz": round(speed, 4)}, cause)
        return speed

    def finish(self, cause: str | None) -> None:
        self.world.record(self.device, "spin_finished", {}, cause)


def build_server(world: World, model: CentrifugeModel | None = None, *, state_dir: str | Path | None,
                 durability: str = "process", name: str = "simlab-centrifuge", device_id: str = "centrifuge-1",
                 **kw: Any) -> tuple[DeviceServer, CentrifugeModel]:
    """The centrifuge as a native BHMS device server (the OPC UA adapter reaches the same model over TCP)."""
    fuge = model or CentrifugeModel(world, device=device_id)
    srv = make_server(world, name, state_dir=state_dir, durability=durability, title="SimLab centrifuge", **kw)
    dev = simulated_device(srv, device_id, name="Benchtop centrifuge", capabilities=["bhms.centrifuge"],
                     resources=[f"{device_id}/rotor", f"{device_id}/lid"], tags=["simlab", "centrifuge"],
                     description="Eight-position benchtop centrifuge with a lid interlock and imbalance check.",
                     identity={"manufacturer": "SimLab", "model": "centrifuge twin", "firmwareVersion": "1"},
                     safety_summary="Hazardous when spinning: the lid locks above 0.5 Hz and an unbalanced rotor is "
                                    "refused before it spins up.")
    host = TwinHost(world, dev)

    @dev.property(unit="Hz", evidence="measured", max_rate_hz=10)
    def speed() -> float:
        """Rotor speed (Hz = rotations per second) from the tachometer."""
        return max(0.0, host.measure("tach", fuge.speed_hz(), TACH_SIGMA_HZ))

    @dev.property(evidence="measured")
    def lid_open() -> bool:
        """Lid switch: true when the lid is open."""
        host.check_sensor("lid_switch")
        return fuge.lid_open

    @dev.property(evidence="reported")
    def lid_locked() -> bool:
        """Interlock state: true while the rotor turns and the lid cannot be opened."""
        return fuge.lid_locked()

    def refuse(exc: Exception) -> DeviceFault:
        return DeviceFault(str(exc), proof="the unit's interlock refused the command before anything moved",
                           effect="none", hint="fix the cause named in the message, then retry")

    @dev.action(effect="reversible", idempotency="absolute", completion_evidence="measured",
                verified_by=["lid_open"], cancel="unsupported", max_duration_ms=10_000, typical_duration_ms=1500,
                resources=[f"{device_id}/lid"])
    async def open_lid(ctx) -> None:
        """Open the lid (refused while the rotor is turning)."""
        host.begin(ctx)
        try:
            fuge.set_lid(True, ctx.operation_id)
        except PermissionError as exc:
            raise refuse(exc) from exc
        await host.elapse(ctx, LID_S)
        await ctx.verify("lid_open", lambda v: v is True)
        host.log.end(ctx.operation_id, {})

    @dev.action(effect="reversible", idempotency="absolute", completion_evidence="measured",
                verified_by=["lid_open"], cancel="unsupported", max_duration_ms=10_000, typical_duration_ms=1500,
                resources=[f"{device_id}/lid"])
    async def close_lid(ctx) -> None:
        """Close the lid."""
        host.begin(ctx)
        fuge.set_lid(False, ctx.operation_id)
        await host.elapse(ctx, LID_S)
        await ctx.verify("lid_open", lambda v: v is False)
        host.log.end(ctx.operation_id, {})

    @dev.action(effect="hazardous", idempotency="relative", completion_evidence="measured",
                verified_by=["speed"], cancel="supported", max_duration_ms=3_700_000, typical_duration_ms=300_000,
                resources=[f"{device_id}/rotor"], preconditions="lid closed; rotor balanced within 1 g")
    async def spin(ctx, speed: Range(1.5, MAX_HZ, unit="Hz"), duration: Range(1, 3600, unit="s")  # noqa: F821
                   ) -> {"peak_speed": Range(0, MAX_HZ, unit="Hz", nullable=True)}:  # noqa: F821
        """Spin at ``speed`` for ``duration`` seconds at speed (plus ramp up and down)."""
        host.begin(ctx)
        try:
            total = fuge.start(float(speed), float(duration), ctx.operation_id)
        except (PermissionError, ValueError) as exc:
            raise refuse(exc) from exc
        ramp_up = speed / ACCEL_HZ_S
        if await host.elapse(ctx, ramp_up + 0.25, chunk_s=0.5):
            fuge.abort(ctx.operation_id)
            await world.advance(speed / DECEL_HZ_S + 0.5)  # braking continues after the cancel
            raise host.canceled(ctx, "spin aborted and braked")
        fuge.record_speed(ctx.operation_id)
        peak = await ctx.verify("speed", lambda v: abs(v - speed) <= 0.5)
        if await host.elapse(ctx, total - ramp_up - 0.25 + 0.1, chunk_s=0.5):
            fuge.abort(ctx.operation_id)
            await world.advance(speed / DECEL_HZ_S + 0.5)  # braking continues after the cancel
            raise host.canceled(ctx, "spin aborted and braked")
        fuge.finish(ctx.operation_id)
        return host.log.end(ctx.operation_id, {"peak_speed": None if peak is None else round(peak, 3)})

    @dev.on_stop(evidence="reported", max_duration_ms=500)
    async def halt(ctx: Any) -> None:
        fuge.abort(None)  # brake; the lid stays locked until the rotor is slow

    return srv, fuge
