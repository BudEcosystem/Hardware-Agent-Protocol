"""What every twin's BHMS device server shares: power, world time, a device-side command log, honest sensing.

A twin is a ``DeviceServer`` (Python SDK) whose handlers read and write the shared ``World``. ``TwinHost`` gives a
handler four things:

* ``elapse(ctx, seconds)``: let world time pass (paced or instant per the world's mode) while honouring cancellation and
  power loss; the device's physical work takes world time, not wall time, so a stepped world runs far faster than real
  time and a realtime world exactly at real time.
* a **command log** kept by the device itself (like the conformance device's): ``begin`` before acting, ``end`` after.
  The ``reconcile`` hook answers an ``unknown`` operation from it: ``completed`` (with the recorded result) when the
  command finished, ``failed`` with ``mayHaveActed`` when it started but did not finish, ``failed`` with effect ``none``
  when it never reached the device. The log is the device's evidence; it is not the world's effect log (the oracle's).
* **power**: a ``power_loss`` fault on the device sets its status offline (new work is refused before dispatch) and makes a
  running action raise ``PowerLost`` (an unexpected exception: the operation ends ``unknown``, exactly as a real power
  cut would leave it).
* **honest sensing**: ``measure(name, value, sigma)`` adds the sensor's noise from the world's per-sensor generator and
  raises ``SensorFault`` when the device's sensor is disconnected (the SDK then reports ``quality: invalid`` and
  ``value: null``, never a substitute value).

Evidence labels: a SimLab device reports ``measured`` only for readings that come through a modelled sensor with its own
noise (encoders, optical sensors, balances, thermistors) and ``simulated`` for anything it reads straight from the
world's bookkeeping. Every twin documents which is which.

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from bhms.server.context import ActionContext, Canceled, DeviceFault, Reconciled
from bhms.server.device import Device
from bhms.server.server import DeviceServer
from simlab.faults import Fault
from simlab.world import World

_CHUNK_S = 0.05


class PowerLost(RuntimeError):
    """The device lost power while acting; the SDK turns an unexpected exception into an ``unknown`` operation."""


class SensorFault(RuntimeError):
    """The sensor is disconnected; a getter that raises yields an invalid reading."""


class CommandLog:
    """The device-side record of commands: what reached the device, and what finished."""

    def __init__(self) -> None:
        self._state: dict[str, str] = {}
        self._results: dict[str, Any] = {}

    def begin(self, operation_id: str) -> None:
        self._state[operation_id] = "started"

    def end(self, operation_id: str, result: Any) -> Any:
        self._state[operation_id] = "done"
        self._results[operation_id] = result
        return result

    def state(self, operation_id: str) -> str:
        return self._state.get(operation_id, "none")

    def result(self, operation_id: str) -> Any:
        return self._results.get(operation_id)


class TwinHost:
    """Per-device helpers for a twin's server handlers; see the module docstring."""

    def __init__(self, world: World, device: Device) -> None:
        self.world, self.device, self.log = world, device, CommandLog()
        self.target = device.device_id
        device.reconcile(self._reconcile)
        device.liveness(self.powered)
        world.faults.subscribe(self._fault_event)
        device.set_status(None if self.powered() else "offline")
        device.report_alive()

    # ------------------------------------------------------------------ power and sensors

    def powered(self) -> bool:
        return not self.world.faults.active(self.target, "power_loss")

    def _fault_event(self, event: str, fault: Fault) -> None:
        if fault.kind == "power_loss" and fault.target == self.target:
            self.device.set_status("offline" if event == "active" else None)
            if event == "cleared":
                self.device.report_alive()

    def check_sensor(self, name: str) -> None:
        """Raise ``SensorFault`` when the sensor cannot produce a reading (disconnected or unpowered)."""
        if self.world.faults.active(self.target, "sensor_disconnect"):
            raise SensorFault(f"{self.target}: sensor {name} is disconnected")
        if not self.powered():
            raise SensorFault(f"{self.target}: no power")

    def measure(self, name: str, value: float, sigma: float = 0.0) -> float:
        """A modelled sensor reading: ``value`` plus Gaussian noise from this sensor's own generator."""
        self.check_sensor(name)
        return value + (float(self.world.rng_for(f"{self.target}.{name}").normal(0.0, sigma)) if sigma else 0.0)

    # ------------------------------------------------------------------ actions

    def begin(self, ctx: ActionContext) -> None:
        """A command reached the device: refuse it when unpowered (nothing happened: proof), else log it."""
        if not self.powered():
            raise DeviceFault(f"{self.target} has no power", proof="power rail is off; the command was not delivered",
                              effect="none", hint="restore power, then retry")
        self.log.begin(ctx.operation_id)

    async def elapse(self, ctx: ActionContext, seconds: float, *, chunk_s: float = _CHUNK_S) -> bool:
        """Let ``seconds`` of world time pass, checking for cancel and power every ``chunk_s``. Returns True if
        cancelled early; raises ``PowerLost`` on a power cut."""
        deadline = self.world.time_s + seconds
        while self.world.time_s < deadline - 1e-9:
            if ctx.cancelled.is_set():
                return True
            if not self.powered():
                raise PowerLost(f"{self.target} lost power")
            await self.world.until(min(deadline, self.world.time_s + chunk_s))
        return ctx.cancelled.is_set()

    @staticmethod
    def canceled(ctx: ActionContext, partial: str) -> Canceled:
        return Canceled(effect="unverified", detail=f"{partial} ({ctx.cancel_reason})")

    # ------------------------------------------------------------------ reconcile

    async def _reconcile(self, op: dict[str, Any]) -> Reconciled:
        op_id = op["operationId"]
        state = self.log.state(op_id)
        if state == "done":
            return Reconciled("completed", evidence="device command log: done", result=self.log.result(op_id))
        if state == "started":
            return Reconciled("failed", evidence="device command log: started, not finished",
                              message="interrupted; a partial effect is possible", may_have_acted=True)
        return Reconciled("failed", evidence="device command log has no record of this command", effect="none",
                          message="the command never reached the device", may_have_acted=False)


def make_server(world: World, name: str, *, state_dir: str | Path | None, durability: str = "process",
                title: str | None = None, **kw: Any) -> DeviceServer:
    """A ``DeviceServer`` for a twin. ``durability="process"`` (the default here) survives a process kill but not power
    loss of the host; it is the honest choice for a simulator (the SDK documents it as opt-in for simulators), while
    ``"dispatch"`` is what a physical device must use. State lives under ``state_dir`` (a fresh directory per run)."""
    return DeviceServer(name, title=title or name, state_dir=state_dir, durability=durability,
                        instructions="SimLab twin: a simulated device on a shared simulated bench; nothing is physical.",
                        **kw)


async def settle_world(world: World, seconds: float) -> None:
    """Advance world time without a command (idle time between agent steps)."""
    await asyncio.sleep(0)
    await world.advance(seconds)
