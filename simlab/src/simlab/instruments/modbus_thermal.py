"""A Modbus TCP temperature controller whose registers are the thermal block twin's state.

This is the *instrument* a vendor would ship: a Modbus TCP slave with a register map. It is a real pymodbus 3.8.6 server on
a TCP port; every register read computes its value from the shared ``ThermalModel`` at the world's present time, and
every write drives the model, so the BHMS Modbus adapter talks to it exactly as it would to hardware. (It runs inside the
SimLab process because it must read and write the one shared world; the protocol boundary is the TCP socket.)

Register map (slave 1, zero-based addresses)::

    holding 0  setpoint, 0.1 C units          read/write, 40..990
    holding 1  enable, 0 or 1                 read/write
    input   0  temperature, 0.01 C units      read-only, signed 16 bit (thermistor with noise)
    input   1  status word: bit0 = enabled, bit1 = within 0.5 C of the setpoint

Faults: while the controller has lost power (``power_loss`` fault on its device) every access fails with a Modbus
SERVER_DEVICE_FAILURE exception; a disconnected thermistor (``sensor_disconnect``) reads the sentinel 0x7FFF (the
conventional "sensor open" value) in input register 0.

Thread-safety: runs on the world's event loop.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusSlaveContext
from pymodbus.server import ModbusTcpServer

from simlab.instruments.journal import CommandJournal
from simlab.twins.thermal import SENSOR_SIGMA_C, SETPOINT_RANGE_C, ThermalModel
from simlab.world import World

SENSOR_OPEN = 0x7FFF
HR_SETPOINT, HR_ENABLE = 0, 1
IR_TEMPERATURE, IR_STATUS = 0, 1


class _PowerFault(Exception):
    """Raised inside a data block to make pymodbus answer with an exception response."""


class _Block(ModbusSequentialDataBlock):
    """A register block whose values are computed on read and applied on write. pymodbus 3.8 hands its datastore
    1-based addresses (``ModbusSlaveContext`` adds 1 per section 4.4 of the specification); the block converts back."""

    def __init__(self, size: int, read: Any, write: Any = None) -> None:
        super().__init__(0, [0] * size)
        self._read, self._write = read, write

    def validate(self, address: int, count: int = 1) -> bool:
        return 1 <= address and address - 1 + count <= len(self.values)

    def getValues(self, address: int, count: int = 1) -> list[int]:  # noqa: N802 - pymodbus API
        return [self._read(address - 1 + i) for i in range(count)]

    def setValues(self, address: int, values: Any) -> None:  # noqa: N802 - pymodbus API
        if self._write is None:
            raise _PowerFault("read-only block")
        for i, value in enumerate(values if isinstance(values, (list, tuple)) else [values]):
            self._write(address - 1 + i, int(value))


class ModbusThermalInstrument:
    """Serves a ``ThermalModel`` over Modbus TCP."""

    def __init__(self, world: World, model: ThermalModel, *, host: str = "127.0.0.1", port: int = 0,
                 device: str = "thermal-1") -> None:
        self.world, self.model, self.device = world, model, device
        self.host, self.port = host, port
        self.journal = CommandJournal(world)
        self._server: ModbusTcpServer | None = None
        self._task: asyncio.Task[None] | None = None
        holding = _Block(2, self._read_holding, self._write_holding)
        inputs = _Block(2, self._read_input)
        self._context = ModbusServerContext(slaves=ModbusSlaveContext(hr=holding, ir=inputs), single=True)

    # ------------------------------------------------------------------ register semantics

    def _check_power(self) -> None:
        if self.world.faults.active(self.device, "power_loss"):
            raise _PowerFault("controller has no power")

    def _read_holding(self, address: int) -> int:
        self._check_power()
        return round(self.model.setpoint_c * 10) if address == HR_SETPOINT else int(self.model.enabled)

    def _write_holding(self, address: int, value: int) -> None:
        with self.journal.command(f"write holding {address} = {value}"):  # numbered even when it fails: the adapter counts it
            self._check_power()
            if address == HR_SETPOINT:
                low, high = (round(c * 10) for c in SETPOINT_RANGE_C)
                if not low <= value <= high:
                    raise _PowerFault("setpoint out of range")  # answered as an exception: the write is refused
                self.model.command(value / 10.0, self.model.enabled, None)
            else:
                self.model.command(None, bool(value), None)

    def _read_input(self, address: int) -> int:
        self._check_power()
        if address == IR_TEMPERATURE:
            if self.world.faults.active(self.device, "sensor_disconnect"):
                return SENSOR_OPEN
            noise = float(self.world.rng_for(f"{self.device}.modbus").normal(0.0, SENSOR_SIGMA_C))
            return round((self.model.temperature_c() + noise) * 100) & 0xFFFF
        within = abs(self.model.temperature_c() - self.model.setpoint_c) <= 0.5
        return int(self.model.enabled) | (int(self.model.enabled and within) << 1)

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> int:
        """Listen on the configured port (0 = pick a free one); returns the port."""
        self._server = ModbusTcpServer(self._context, address=(self.host, self.port))
        self._task = asyncio.ensure_future(self._server.serve_forever())
        for _ in range(200):
            await asyncio.sleep(0.01)
            if self._server.transport and self._server.transport.sockets:
                break
        self.port = self._server.transport.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.shutdown()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._server = self._task = None
