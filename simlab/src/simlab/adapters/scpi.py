"""SCPI over TCP adapter: any SCPI instrument described by a command profile becomes a BHMS device.

``ScpiProfile`` lists queries (each becomes a property) and commands (each becomes an action). The adapter speaks the
SCPI session conventions rather than assuming success:

* queries return a number or string; a sentinel the profile names (``+9.9E37``, the SCPI "not a number") is an *invalid*
  reading, never passed on as a value;
* after every command the adapter reads the error queue (``SYSTem:ERRor?``) and synchronises with ``*OPC?``. A command or
  execution error (-100 to -299) proves the instrument did not execute the command: the action fails with effect ``none``
  (``mayHaveActed`` false). Any other error code, a timeout or a closed connection after the command left leaves the
  operation ``unknown``;
* the identity query (``*IDN?``) is checked once per session against the profile's expected prefix, so a bridge never talks
  to the wrong instrument unnoticed.

SCPI commands give no physical result, so actions complete ``reported`` (``*OPC?`` answered) and the effect stays
unverified unless the agent reads a measured property.

Thread-safety: one event loop; one connection, serialised by a lock.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bhms.server.decorators import Range
from bhms.server.server import DeviceServer
from simlab.adapters.common import Refused, Unreachable, declare_action, declare_property, refusal_fault
from simlab.simdevice import CommandLog, make_server, simulated_device
from simlab.world import World

_ERROR = re.compile(r'^\s*([+-]?\d+)\s*,\s*"?(.*?)"?\s*$')


@dataclass(frozen=True)
class Query:
    name: str
    command: str
    description: str
    kind: str = "number"  # "number" | "boolean" | "string"
    unit: str | None = None
    evidence: str = "reported"
    minimum: float | None = None
    maximum: float | None = None
    invalid: float | None = None  # sentinel meaning "no valid reading"


@dataclass(frozen=True)
class Command:
    name: str
    command: str  # the exact command line sent
    description: str
    effect: str = "reversible"
    idempotency: str = "absolute"
    preconditions: str | None = None
    max_duration_ms: int = 10_000


@dataclass(frozen=True)
class ScpiProfile:
    device_id: str
    name: str
    description: str
    capabilities: tuple[str, ...]
    idn_prefix: str
    queries: tuple[Query, ...]
    commands: tuple[Command, ...] = field(default_factory=tuple)
    safety_summary: str | None = None


class ScpiLink:
    """A line-oriented SCPI session over TCP."""

    def __init__(self, host: str, port: int, idn_prefix: str, timeout_s: float = 1.0) -> None:
        self.host, self.port, self.idn_prefix, self.timeout_s = host, port, idn_prefix, timeout_s
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self.sent = 0  # commands sent, numbered in send order (joined with the instrument's journal by the harness)
        self.log: CommandLog | None = None

    async def close(self) -> None:
        async with self._lock:
            self._drop()

    def _drop(self) -> None:
        if self._writer is not None:
            self._writer.close()
        self._reader = self._writer = None

    async def _line(self) -> str:
        assert self._reader is not None
        try:
            raw = await asyncio.wait_for(self._reader.readline(), self.timeout_s)
        except (asyncio.TimeoutError, OSError) as exc:
            self._drop()
            raise RuntimeError(f"SCPI instrument did not answer: {exc or 'timeout'}") from exc
        if not raw:
            self._drop()
            raise RuntimeError("SCPI instrument closed the connection")
        return raw.decode("ascii", "replace").strip()

    async def _send(self, text: str) -> None:
        assert self._writer is not None
        self._writer.write(text.encode("ascii") + b"\n")
        await self._writer.drain()

    async def _ensure(self) -> None:
        if self._writer is not None:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port),
                                                                self.timeout_s)
        except (OSError, asyncio.TimeoutError) as exc:
            raise Unreachable(f"cannot connect to the SCPI instrument: {exc or 'timeout'}") from exc
        await self._send("*IDN?")
        identity = await self._line()
        if not identity.startswith(self.idn_prefix):
            self._drop()
            raise Unreachable(f"wrong instrument: *IDN? answered {identity!r}, expected {self.idn_prefix!r}")

    async def query(self, command: str) -> str:
        async with self._lock:
            await self._ensure()
            try:
                await self._send(command)
            except OSError as exc:
                self._drop()
                raise RuntimeError(f"SCPI send failed: {exc}") from exc
            return await self._line()

    async def command(self, command: str) -> None:
        """Send a command and judge only what *it* caused: clear the error state first (a stale entry from an earlier query
        must not be blamed on this command), then synchronise with ``*OPC?``, read the event status register and the
        error queue."""
        async with self._lock:
            await self._ensure()  # failing here proves nothing was sent
            try:
                await self._send("*CLS")
                self.sent += 1  # from here the command is on its way
                await self._send(command)
                await self._send("*OPC?")
            except OSError as exc:
                self._drop()
                raise RuntimeError(f"SCPI send failed after the command left: {exc}") from exc
            await self._line()  # *OPC? -> 1
            await self._send("*ESR?")
            esr = int((await self._line()) or 0)
            await self._send("SYST:ERR?")
            match = _ERROR.match(await self._line())
            if match is None:
                raise RuntimeError("unparseable SYST:ERR? reply")
            code = int(match.group(1))
            if code != 0 or esr & 0x30:
                if -299 <= code <= -100 or (code == 0 and esr & 0x30):
                    raise Refused(f"error {code}: {match.group(2)} (ESR {esr})")
                raise RuntimeError(f"instrument error {code}: {match.group(2)} (the command may have acted)")


def build_server(world: World, profile: ScpiProfile, host: str, port: int, *, state_dir: str | Path | None,
                 durability: str = "process", name: str = "simlab-scpi-adapter", timeout_s: float = 1.0,
                 **kw: Any) -> tuple[DeviceServer, ScpiLink]:
    """The BHMS server for a SCPI instrument. The adapter never reads the world; it knows only what the instrument says."""
    srv = make_server(world, name, state_dir=state_dir, durability=durability, title=f"SCPI adapter: {profile.name}",
                      **kw)
    dev = simulated_device(srv, profile.device_id, name=profile.name, description=profile.description,
                     capabilities=list(profile.capabilities), resources=[f"{profile.device_id}/instrument"],
                     tags=["simlab", "adapter", "scpi"], safety_summary=profile.safety_summary,
                     identity={"manufacturer": "SCPI instrument", "model": profile.name, "firmwareVersion": "unknown"})
    link = ScpiLink(host, port, profile.idn_prefix, timeout_s)
    log = link.log = CommandLog()

    def schema_of(query: Query) -> Any:
        return {"boolean": bool, "string": str}.get(query.kind) or Range(query.minimum, query.maximum,
                                                                         unit=query.unit or "1")

    def reader(query: Query) -> Any:
        async def read_value() -> Any:
            text = await link.query(query.command)
            if query.kind == "string":
                return text
            if query.kind == "boolean":
                return text.strip() in ("1", "ON", "TRUE")
            number = float(text.split()[0])
            if query.invalid is not None and number == query.invalid:
                raise RuntimeError(f"{query.name}: the instrument reports no valid reading ({text})")
            return number
        return read_value

    for query in profile.queries:
        declare_property(dev, query.name, reader(query), schema_of(query), evidence=query.evidence,
                         description=f"{query.description} (SCPI {query.command})")

    def sender(command: Command) -> Any:
        async def send(ctx: Any) -> Any:
            log.begin(ctx.operation_id)
            first = link.sent
            try:
                await link.command(command.command)
            except (Refused, Unreachable) as exc:
                raise refusal_fault(exc, "SCPI") from exc
            finally:
                log.sent_range(ctx.operation_id, first, link.sent)
            return log.end(ctx.operation_id, {"acknowledged": True})
        return send

    for command in profile.commands:
        declare_action(dev, command.name, sender(command), description=command.description,
                       returns={"acknowledged": bool}, effect=command.effect, idempotency=command.idempotency,
                       completion_evidence="reported", max_duration_ms=command.max_duration_ms,
                       preconditions=command.preconditions, resources=[f"{profile.device_id}/instrument"])

    @dev.liveness
    async def alive() -> bool:
        try:
            await link.query("*OPC?")
        except (RuntimeError, Unreachable):
            return False
        return True

    return srv, link
