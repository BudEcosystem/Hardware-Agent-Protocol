"""Thermal block twin: a first-order thermal model of a heated and cooled block.

    dT/dt = (T_target - T) / tau,      T_target = setpoint while the controller is enabled, ambient otherwise

solved exactly between commands: ``T(t) = T_target + (T0 - T_target) * exp(-(t - t0) / tau)``, so the temperature is a
pure function of world time and the command history (no per-step integration, deterministic, exact at any step size).
The heater and Peltier are limited to a slew of at most ``MAX_SLEW_C_S``: while the gap is large the block ramps
linearly at the limit and then relaxes exponentially, which is what a power-limited controller does.

The setpoint is bounded to ``SETPOINT_RANGE_C`` (an over-temperature protection the twin enforces, not the agent).

Sensing: ``temperature`` is ``measured`` (a thermistor: true temperature plus Gaussian noise, sigma ``SENSOR_SIGMA_C``);
``setpoint`` and ``enabled`` are ``reported`` by the controller. ``ThermalModel`` is shared by this BHMS twin and the
Modbus instrument (``instruments/modbus_thermal``): one model, whichever protocol reaches it.

Thread-safety: belongs to its world's thread.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from bhms.server.context import DeviceFault
from bhms.server.decorators import Range
from bhms.server.server import DeviceServer
from simlab.simdevice import TwinHost, make_server
from simlab.world import World

AMBIENT_C = 22.0
TAU_S = 40.0
MAX_SLEW_C_S = 2.0
SETPOINT_RANGE_C = (4.0, 99.0)
SENSOR_SIGMA_C = 0.02
TOLERANCE_C = 0.3


class ThermalModel:
    """The block's temperature as a function of world time and the command history."""

    def __init__(self, world: World, *, device: str = "thermal-1", ambient_c: float = AMBIENT_C) -> None:
        self.world, self.device, self.ambient_c = world, device, ambient_c
        self.setpoint_c, self.enabled = ambient_c, False
        self._t0, self._temp0 = world.time_s, ambient_c

    def _target_c(self) -> float:
        return self.setpoint_c if self.enabled else self.ambient_c

    def temperature_c(self) -> float:
        """The true block temperature now."""
        elapsed, target = self.world.time_s - self._t0, self._target_c()
        gap = target - self._temp0
        # Linear ramp at the slew limit while the exponential's slope would exceed it, then exponential relaxation.
        ramp_until = max(0.0, (abs(gap) - MAX_SLEW_C_S * TAU_S) / MAX_SLEW_C_S)
        if elapsed < ramp_until:
            return self._temp0 + math.copysign(MAX_SLEW_C_S * elapsed, gap)
        start = self._temp0 + math.copysign(MAX_SLEW_C_S * ramp_until, gap)
        return target + (start - target) * math.exp(-(elapsed - ramp_until) / TAU_S)

    def command(self, setpoint_c: float | None, enabled: bool, cause: str | None) -> None:
        """Change the controller; the trajectory restarts from the present temperature."""
        if setpoint_c is not None and not SETPOINT_RANGE_C[0] <= setpoint_c <= SETPOINT_RANGE_C[1]:
            raise ValueError(f"setpoint {setpoint_c} C is outside {SETPOINT_RANGE_C[0]}..{SETPOINT_RANGE_C[1]} C")
        self._temp0, self._t0 = self.temperature_c(), self.world.time_s
        if setpoint_c is not None:
            self.setpoint_c = setpoint_c
        self.enabled = enabled
        self.world.record(self.device, "thermal_command", {"setpoint_c": self.setpoint_c, "enabled": enabled}, cause)

    def time_to_reach(self, target_c: float, tolerance_c: float = TOLERANCE_C) -> float:
        """World seconds until the block is within ``tolerance_c`` of ``target_c`` if it heads there (conservative bound)."""
        gap = abs(target_c - self.temperature_c())
        if gap <= tolerance_c:
            return 0.0
        ramp = max(0.0, (gap - MAX_SLEW_C_S * TAU_S) / MAX_SLEW_C_S)
        remaining = min(gap, MAX_SLEW_C_S * TAU_S)
        return ramp + TAU_S * math.log(remaining / tolerance_c)


def build_server(world: World, model: ThermalModel | None = None, *, state_dir: str | Path | None,
                 durability: str = "process", name: str = "simlab-thermal", device_id: str = "thermal-1",
                 **kw: Any) -> tuple[DeviceServer, ThermalModel]:
    """The thermal block as a native BHMS device server (the Modbus adapter reaches the same model over TCP)."""
    thermal = model or ThermalModel(world, device=device_id)
    srv = make_server(world, name, state_dir=state_dir, durability=durability, title="SimLab thermal block", **kw)
    dev = srv.device(device_id, name="Thermal block", capabilities=["bhms.thermal"],
                     resources=[f"{device_id}/heater"], tags=["simlab", "thermal"],
                     description="Heated and cooled block, 4 to 99 C, first-order response (time constant 40 s).",
                     identity={"manufacturer": "SimLab", "model": "thermal block twin", "firmwareVersion": "1"},
                     safety_summary="Surface up to 99 C; the controller refuses setpoints outside 4 to 99 C.")
    host = TwinHost(world, dev)

    @dev.property(unit="Cel", evidence="measured", max_rate_hz=10)
    def temperature() -> float:
        """Block temperature (C) from the thermistor."""
        return host.measure("thermistor", thermal.temperature_c(), SENSOR_SIGMA_C)

    @dev.property(unit="Cel", evidence="reported")
    def setpoint() -> float:
        """The controller's setpoint (C)."""
        return thermal.setpoint_c

    @dev.property(evidence="reported")
    def enabled() -> bool:
        """Whether the controller is driving the block."""
        return thermal.enabled

    @dev.action(effect="reversible", idempotency="absolute", completion_evidence="measured",
                verified_by=["temperature"], cancel="supported", max_duration_ms=900_000, typical_duration_ms=60_000,
                resources=[f"{device_id}/heater"])
    async def set_temperature(ctx, target: Range(4, 99, unit="Cel"),  # noqa: F821
                              tolerance: Range(0.1, 5, unit="Cel") = 0.5) -> {"temperature": "Cel"}:  # noqa: F821
        """Drive the block to ``target`` and return when the thermistor reads within ``tolerance`` of it."""
        host.begin(ctx)
        thermal.command(target, True, ctx.operation_id)
        wait = thermal.time_to_reach(target, max(0.05, tolerance - 0.2))
        if await host.elapse(ctx, wait, chunk_s=0.5):
            raise host.canceled(ctx, "heating stopped")
        reading = await ctx.verify("temperature", lambda v: abs(v - target) <= tolerance)
        if reading is not None and abs(reading - target) > tolerance:
            raise DeviceFault(f"the block reads {reading:.2f} C, not {target} C", partial="heating in progress",
                              hint="wait and read temperature before retrying")
        return host.log.end(ctx.operation_id, {"temperature": round(reading if reading is not None else -274.0, 3)})

    @dev.action(effect="reversible", idempotency="absolute", completion_evidence="reported", cancel="unsupported",
                max_duration_ms=5000, resources=[f"{device_id}/heater"])
    async def disable(ctx) -> None:
        """Switch the heater and cooler off; the block relaxes to ambient."""
        host.begin(ctx)
        thermal.command(None, False, ctx.operation_id)
        host.log.end(ctx.operation_id, {})

    @dev.on_stop(evidence="reported", max_duration_ms=100)
    async def halt(ctx: Any) -> None:
        thermal.command(None, False, None)  # stopping a heater means switching it off

    return srv, thermal
