"""Modbus TCP adapter: any Modbus slave described by a register profile becomes a BHMS device.

``ModbusProfile`` is data: which registers exist, their scaling and units, which are writable and which are measurements.
``build_server`` turns it into a ``DeviceServer`` (properties for every register, a ``set_<name>`` action for every
writable one) and talks Modbus TCP with pymodbus 3.8.6 (pinned: the 3.9+ API differs).

Evidence and completion follow ``simlab.adapters.common``: register values are ``reported`` unless the profile marks them
``measured``; a write is read back and completes ``reported`` (the read-back is the same register, so the effect stays
unverified; no Modbus profile can claim a measurement it does not have). An exception response with an illegal
function/address/value code (1 to 3) proves the write was not executed; a server failure code (4 and above), a timeout or a
dropped connection after the write left leaves the operation ``unknown``, which the reconcile hook resolves by reading the
register back (equal to the target: completed, unverified; anything else: stays unknown).

Thread-safety: one event loop; one TCP connection per adapter, serialised by a lock.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from bhms.server.context import DeviceFault, Reconciled
from bhms.server.decorators import Range
from bhms.server.server import DeviceServer
from simlab.adapters.common import Refused, Unreachable, declare_action, declare_property, refusal_fault
from simlab.simdevice import CommandLog, make_server
from simlab.world import World

ILLEGAL_CODES = {1, 2, 3}  # illegal function, address, value: the request was rejected, not executed


@dataclass(frozen=True)
class Register:
    """One Modbus register (or a scaled value in one): ``value = (raw - offset) * scale`` in ``unit``."""

    name: str
    address: int
    table: Literal["holding", "input"]
    unit: str | None
    description: str
    scale: float = 1.0
    signed: bool = False
    evidence: str = "reported"
    minimum: float | None = None
    maximum: float | None = None
    writable: bool = False
    boolean: bool = False
    invalid_raw: int | None = None  # a sentinel raw value meaning "sensor open / no reading"


@dataclass(frozen=True)
class ModbusProfile:
    device_id: str
    name: str
    description: str
    capabilities: tuple[str, ...]
    registers: tuple[Register, ...]
    slave: int = 1
    safety_summary: str | None = None


class ModbusLink:
    """A pymodbus async client with Modbus failures mapped to ``Refused``, ``Unreachable`` or a plain ``RuntimeError``
    (the last meaning: the command may have been executed, the outcome is unknown)."""

    def __init__(self, host: str, port: int, slave: int, timeout_s: float = 1.0) -> None:
        self._client = AsyncModbusTcpClient(host, port=port, timeout=timeout_s, retries=0)
        self.slave = slave
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        self._client.close()

    async def _ensure(self) -> None:
        if not self._client.connected and not await self._client.connect():
            raise Unreachable("cannot connect to the Modbus slave")

    async def read(self, register: Register) -> int:
        async with self._lock:
            await self._ensure()
            try:
                call = (self._client.read_holding_registers if register.table == "holding"
                        else self._client.read_input_registers)
                response = await call(register.address, count=1, slave=self.slave)
            except (ModbusException, OSError, asyncio.TimeoutError) as exc:
                raise RuntimeError(f"Modbus read failed: {exc}") from exc
            if response.isError():
                raise RuntimeError(f"Modbus exception on read of {register.name}: {response}")
            return int(response.registers[0])

    async def write(self, register: Register, raw: int) -> None:
        async with self._lock:
            await self._ensure()  # failing here proves nothing was sent
            try:
                response = await self._client.write_register(register.address, raw, slave=self.slave)
            except (ModbusException, OSError, asyncio.TimeoutError) as exc:
                raise RuntimeError(f"Modbus write may or may not have been executed: {exc}") from exc
            if response.isError():
                code = getattr(response, "exception_code", None)
                if code in ILLEGAL_CODES:
                    raise Refused(f"exception code {code} on write of {register.name}")
                raise RuntimeError(f"Modbus exception code {code} on write of {register.name}: the unit may have acted")


def _decode(register: Register, raw: int) -> float | bool:
    if register.invalid_raw is not None and raw == register.invalid_raw:
        raise RuntimeError(f"{register.name}: the instrument reports no reading (sentinel {raw:#x})")
    if register.boolean:
        return bool(raw)
    value = raw - 0x10000 if register.signed and raw >= 0x8000 else raw
    return round(value * register.scale, 6)


def _encode(register: Register, value: float | bool) -> int:
    raw = round(float(value) / register.scale) if not register.boolean else int(bool(value))
    return raw & 0xFFFF


def build_server(world: World, profile: ModbusProfile, host: str, port: int, *, state_dir: str | Path | None,
                 durability: str = "process", name: str = "simlab-modbus-adapter",
                 timeout_s: float = 1.0, **kw: Any) -> tuple[DeviceServer, ModbusLink]:
    """The BHMS server for a Modbus slave. ``world`` supplies the SimLab clock for the device's command log only; the
    adapter never reads the world (it can only know what the instrument tells it over Modbus)."""
    srv = make_server(world, name, state_dir=state_dir, durability=durability,
                      title=f"Modbus adapter: {profile.name}", **kw)
    dev = srv.device(profile.device_id, name=profile.name, description=profile.description,
                     capabilities=list(profile.capabilities), resources=[f"{profile.device_id}/registers"],
                     tags=["simlab", "adapter", "modbus"], safety_summary=profile.safety_summary,
                     identity={"manufacturer": "Modbus slave", "model": profile.name, "firmwareVersion": "unknown"})
    link = ModbusLink(host, port, profile.slave, timeout_s)
    log = CommandLog()
    by_name = {r.name: r for r in profile.registers}
    registers = f"{profile.device_id}/registers"

    def schema_of(register: Register) -> Any:
        return bool if register.boolean else Range(register.minimum, register.maximum, unit=register.unit or "1")

    def reader(register: Register) -> Any:
        async def read_value() -> Any:
            return _decode(register, await link.read(register))
        return read_value

    def writer(register: Register) -> Any:
        async def write_value(ctx: Any, value: Any) -> Any:
            log.begin(ctx.operation_id)
            try:
                await link.write(register, _encode(register, value))
            except (Refused, Unreachable) as exc:
                raise refusal_fault(exc, "Modbus") from exc
            back = _decode(register, await link.read(register))
            if (back != value) if register.boolean else abs(back - value) > register.scale:
                raise DeviceFault(f"{register.name} reads back {back} after writing {value}",
                                  partial="the write was accepted but the register differs",
                                  hint="read the register before retrying")
            return log.end(ctx.operation_id, {"value": back})
        return write_value

    for register in profile.registers:
        declare_property(dev, register.name, reader(register), schema_of(register), evidence=register.evidence,
                         description=f"{register.description} (Modbus {register.table} register {register.address})")

    for register in (r for r in profile.registers if r.writable):
        declare_action(dev, f"set_{register.name}", writer(register), description=f"Write {register.description}.",
                       params={"value": schema_of(register)}, returns={"value": bool if register.boolean else
                                                                       (register.unit or "1")},
                       effect="reversible", idempotency="absolute", completion_evidence="reported",
                       max_duration_ms=10_000, resources=[registers])

    @dev.reconcile
    async def reconcile(op: dict[str, Any]) -> Reconciled | None:
        action = op.get("action", "")
        register = by_name.get(action.removeprefix("set_"))
        if register is None or "value" not in op.get("arguments", {}):
            return None
        try:
            back = _decode(register, await link.read(register))
        except RuntimeError:
            return None  # cannot read the instrument: stay unknown
        target = op["arguments"]["value"]
        same = back == target if register.boolean else abs(back - target) <= register.scale
        if same:
            return Reconciled("completed", evidence=f"read back {register.name} = {back}", result={"value": back},
                              effect="unverified")
        return None

    @dev.liveness
    async def alive() -> bool:
        first = next((r for r in profile.registers if r.table == "input" or not r.writable), profile.registers[0])
        try:
            await link.read(first)
        except (RuntimeError, Unreachable):
            return False
        return True

    return srv, link
