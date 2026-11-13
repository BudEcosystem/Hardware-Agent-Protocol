"""A scripted SCPI balance over TCP: the balance twin's load cell behind the standard command set.

A small SCPI instrument as a lab would meet it: line-oriented ASCII over a TCP socket, ``\\n`` terminated, commands
case-insensitive with the usual short forms. It serves the shared ``BalanceModel`` (the same load cell, settling, noise and
tare the native twin uses), so mass readings come from the ledger.

Commands::

    *IDN?          SIMLAB,BALANCE-220,SN0001,1.0
    *OPC?          1
    *CLS           clear the error queue
    MEASure:MASS?  net mass in g, e.g. +4.020300E+01; +9.9E37 when overloaded or the load cell is disconnected
    MEASure:STABle?  1 when the reading has settled, else 0
    UNIT?          G
    CAPacity?      +2.200000E+02
    SYSTem:TAG n   label the next command with token n (journalled on receipt, before any power check)
    TARE           zero the display against the present (possibly still settling) reading; no reply
    SYSTem:ERRor?  0,"No error" | -113,"Undefined header" | -330,"Self-test failed"

Unknown commands push -113 to the error queue. TARE does *not* wait for the reading to settle (as most balances): taring
a moving display leaves a wrong zero, and the only warning is ``MEASure:STABle?``. While the instrument has no power
(``power_loss`` fault) it closes the connection without a reply.

Thread-safety: runs on the world's event loop.
"""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from typing import Any

from simlab.instruments.journal import CommandJournal
from simlab.twins.balance import CAPACITY_G, BalanceModel
from simlab.world import World

OVERLOAD = "+9.9E37"
IDN = "SIMLAB,BALANCE-220,SN0001,1.0"


_SHORT = {"MEASURE": "MEAS", "STABLE": "STAB", "CAPACITY": "CAP", "SYSTEM": "SYST", "ERROR": "ERR"}


def _tag_of(line: str) -> int | None:
    """The token of a ``SYSTem:TAG n`` line, or ``None`` for any other line."""
    parts = line.strip().upper().split()
    if len(parts) == 2 and _normalize(parts[0]) == "SYST:TAG":
        try:
            return int(parts[1])
        except ValueError:
            return None
    return None


def _normalize(command: str) -> str:
    """Upper-case and reduce each header node to its short form (``MEASure:MASS?`` -> ``MEAS:MASS?``)."""
    nodes = []
    for node in command.strip().upper().split(":"):
        query = node.endswith("?")
        word = node.rstrip("?")
        nodes.append(_SHORT.get(word, word) + ("?" if query else ""))
    return ":".join(nodes)


class ScpiBalanceInstrument:
    """Serves a ``BalanceModel`` over SCPI/TCP."""

    def __init__(self, world: World, model: BalanceModel, *, host: str = "127.0.0.1", port: int = 0,
                 device: str = "balance-1") -> None:
        self.world, self.model, self.device = world, model, device
        self.host, self.port = host, port
        self._server: asyncio.AbstractServer | None = None
        self._errors: list[tuple[int, str]] = []
        self._esr = 0
        self.journal = CommandJournal(world)

    def execute(self, line: str) -> str | None:
        """Run one command line; returns the reply, or ``None`` for a command with no reply."""
        command = _normalize(line)
        faults = self.world.faults
        if command == "*IDN?":
            return IDN
        if command == "*OPC?":
            return "1"
        if command == "*CLS":
            self._errors.clear()
            self._esr = 0
            return None
        if _tag_of(line) is not None:
            return None  # accepted; the journal took it on receipt
        if command == "*ESR?":
            esr, self._esr = self._esr, 0
            return str(esr)
        if command == "SYST:ERR?":
            code, text = self._errors.pop(0) if self._errors else (0, "No error")
            return f'{code},"{text}"'
        if command == "MEAS:MASS?":
            if faults.active(self.device, "sensor_disconnect"):
                self._errors.append((-330, "Self-test failed"))
                return OVERLOAD
            reading = self.model.reading_g()
            return OVERLOAD if reading is None else f"{reading:+.6E}"
        if command == "MEAS:STAB?":
            return "1" if self.model.settled() else "0"
        if command == "UNIT?":
            return "G"
        if command == "CAP?":
            return f"{CAPACITY_G:+.6E}"
        if command == "TARE":
            self.model.tare(None)
            return None
        self._errors.append((-113, "Undefined header"))
        self._esr |= 32  # command error
        return None

    def _journal(self, line: str) -> Any:
        """A journal entry for commands that can change something (not queries, ``*CLS`` or tags)."""
        command = _normalize(line)
        if command.endswith("?") or command == "*CLS" or _tag_of(line) is not None:
            return nullcontext()
        return self.journal.command(command)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while line := await reader.readline():
                text = line.decode("ascii", "replace")
                token = _tag_of(text)
                if token is not None:
                    self.journal.tag(token)  # receipt is journalled before any power check
                if self.world.faults.active(self.device, "power_loss"):
                    break  # no power: the connection just dies; a command not yet read is not journalled
                with self._journal(text):
                    reply = self.execute(text)
                if reply is not None:
                    writer.write(reply.encode("ascii") + b"\n")
                    await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._serve, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
