# Wrapping a real instrument (SCPI, Modbus, OPC UA)

This guide shows how to put a BHMS device server in front of an instrument that already speaks an industrial or lab
protocol, so that agents and programs get bounds, units, durable operations and honest evidence without the instrument
changing. It builds a complete SCPI adapter step by step (executed by the docs test against a simulated SCPI balance),
then gives the Modbus TCP and OPC UA mappings, with SimLab's tested adapters as the full worked references.

The adapter is an ordinary `DeviceServer`: its handlers talk the instrument's protocol. The work is in deciding, for each
protocol answer, what BHMS may honestly say about it.

## The rules every adapter follows

These come from building and fault-testing the SimLab adapters (`simlab/src/simlab/adapters/`, rules in
[`common.py`](../../../simlab/src/simlab/adapters/common.py)):

| Situation | What the adapter reports | How, in the Python SDK |
|---|---|---|
| A value read over the protocol | `evidence="reported"`, unless the channel is an independent measurement (an encoder, a load cell): then `measured` | the property's `evidence=` |
| A sentinel meaning "no reading" (`+9.9E37` in SCPI, `0x7FFF` in a register, `Bad*` status in OPC UA) | `quality: invalid`, `value: null`, never the sentinel and never the last good value | raise in the getter |
| A command the instrument explicitly refused (SCPI error -100..-299, Modbus exception 1 to 3, an OPC UA `BadInvalidArgument`, an interlock returning `Ok = false`) | `failed`, `effect: none`, `mayHaveActed: false`: the refusal is proof nothing happened | `raise DeviceFault(msg, proof=..., effect="none")` |
| The instrument could not be reached before anything was sent | the same: proof nothing was sent | `DeviceFault(..., proof=..., effect="none")` |
| A timeout, a dropped connection or a server-side failure after the command left | `unknown`: it may have acted | `raise DeviceLost(...)` (or let `ConnectionError`/`TimeoutError` propagate) |
| The protocol call returned | `completed` with `completionEvidence: reported` and effect `unverified`: Modbus writes, SCPI commands and OPC UA method calls return when the instrument *accepted* the command, not when the physical effect happened | `completion_evidence="reported"` |
| An unknown operation, later | read the instrument back; report `completed` only when the read-back proves it, otherwise leave it `unknown` | `@device.reconcile` returning `Reconciled` or `None` |
| Which instrument answered | check its identity once per session (`*IDN?`, a vendor register, the OPC UA server URI) before sending commands | in the link's connect |

Two more lessons from SimLab: bridged protocols cannot carry a BHMS operation id to the instrument, so keep a
correlation record (operation id, the command you sent, when) in the adapter's own log if you will ever need to
attribute effects after an incident; and if a reading can be meaningless (an empty field, an unstable balance), return
a validity indicator with it rather than a plausible number (BHMS-DEV-035).

## SCPI over TCP, step by step

### The instrument

A stand-in for a real precision balance on the standard SCPI raw-socket port. It answers `*IDN?`, measures with
`MEAS:MASS?` (`+9.9E37` while the pan is overloaded), tares with `TARE`, keeps the SCPI error queue, and can be told to
swallow replies (the file `hang`), which is what a cable fault looks like. Save as `scpi_balance.py`:

```python file=scpi_balance.py
"""A simulated SCPI balance on TCP (a stand-in for a real instrument; not part of BHMS)."""
import asyncio
import random
import sys
from pathlib import Path

state = {"gross_g": 12.5, "tare_g": 0.0, "errors": [], "esr": 0}


async def session(reader, writer):
    while line := (await reader.readline()).decode().strip():
        upper = line.upper()
        if Path("hang").exists() and upper == "*OPC?":
            continue                                     # the command was received, the reply never comes
        if upper == "*IDN?":
            reply = "BudLab,PB-220,SN0001,1.4"
        elif upper == "MEAS:MASS?":
            reply = "+9.9E37" if Path("overload").exists() else f"{state['gross_g'] - state['tare_g'] + random.uniform(-0.0005, 0.0005):.4f}"
        elif upper == "TARE":
            state["tare_g"] = state["gross_g"]
            continue
        elif upper == "*CLS":
            state["errors"].clear()
            state["esr"] = 0
            continue
        elif upper == "*OPC?":
            reply = "1"
        elif upper == "*ESR?":
            reply, state["esr"] = str(state["esr"]), 0
        elif upper == "SYST:ERR?":
            reply = state["errors"].pop(0) if state["errors"] else '0,"No error"'
        else:
            state["errors"].append('-113,"Undefined header"')
            state["esr"] |= 0x20                         # command error bit
            continue
        writer.write(reply.encode() + b"\n")
        await writer.drain()
    writer.close()


async def main(port):
    server = await asyncio.start_server(session, "127.0.0.1", port)
    async with server:
        await server.serve_forever()


asyncio.run(main(int(sys.argv[1])))
```

```sh run background wait=tcp:127.0.0.1:5025
python scpi_balance.py 5025
```

### The adapter

The link opens a TCP session, checks the identity, and for every command clears the error state, sends the command,
synchronises with `*OPC?` and then reads the event status register and the error queue, so that a refusal is told
apart from a lost reply. Save as `balance_adapter.py`:

```python file=balance_adapter.py
"""BHMS adapter for a SCPI balance: the patterns of simlab/src/simlab/adapters/scpi.py in one file."""
import asyncio
import re
import sys

from bhms import DeviceFault, DeviceServer, Range
from bhms.server import DeviceLost

HOST, PORT, IDENTITY = "127.0.0.1", 5025, "BudLab,PB-220"
NO_READING = 9.9e37                                    # the SCPI "not a number"


class Refused(Exception):
    """The instrument refused the command: proof that nothing was executed."""


class ScpiLink:
    def __init__(self, host, port, identity, timeout_s=1.0):
        self.host, self.port, self.identity, self.timeout_s = host, port, identity, timeout_s
        self.reader = self.writer = None
        self.lock = asyncio.Lock()

    async def _connect(self):
        if self.writer is not None:
            return
        try:
            self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), self.timeout_s)
        except (OSError, asyncio.TimeoutError) as exc:
            raise Refused(f"cannot connect to the balance: {exc or 'timeout'}") from None  # nothing was sent
        await self._send("*IDN?")
        answer = await self._line()
        if not answer.startswith(self.identity):
            self._drop()
            raise Refused(f"wrong instrument: *IDN? answered {answer!r}")

    def _drop(self):
        if self.writer is not None:
            self.writer.close()
        self.reader = self.writer = None

    async def _send(self, text):
        self.writer.write(text.encode() + b"\n")
        await self.writer.drain()

    async def _line(self):
        try:
            raw = await asyncio.wait_for(self.reader.readline(), self.timeout_s)
        except (OSError, asyncio.TimeoutError):
            self._drop()
            raise DeviceLost("the balance did not answer") from None
        if not raw:
            self._drop()
            raise DeviceLost("the balance closed the connection")
        return raw.decode().strip()

    async def query(self, command):
        async with self.lock:
            await self._connect()
            await self._send(command)
            return await self._line()

    async def command(self, command):
        async with self.lock:
            await self._connect()                      # a failure up to here proves nothing was sent
            for line in ("*CLS", command, "*OPC?"):
                await self._send(line)
            await self._line()                         # a lost *OPC? reply: DeviceLost, the outcome is unknown
            await self._send("*ESR?")
            esr = int(await self._line() or 0)
            await self._send("SYST:ERR?")
            code, _, text = (await self._line()).partition(",")
            if int(code) != 0 or esr & 0x30:
                if -299 <= int(code) <= -100 or int(code) == 0:
                    raise Refused(f"SCPI error {code}: {text.strip(chr(34))}")
                raise DeviceLost(f"instrument error {code} after the command: it may have acted")


link = ScpiLink(HOST, PORT, IDENTITY)
srv = DeviceServer("balance-adapter", title="SCPI adapter: PB-220 balance")
balance = srv.device("balance-1", name="PB-220 balance", description="Precision balance behind a SCPI adapter.",
                     capabilities=["bhms.sensor.mass"], resources=["balance-1/pan"],
                     identity={"manufacturer": "BudLab", "model": "PB-220"})


@balance.property(unit="g", evidence="measured", timeout_ms=2000)
async def mass() -> Range(-220, 220, unit="g"):
    """Net mass on the pan (SCPI MEAS:MASS?; negative below the tare). A load cell: an independent measurement."""
    value = float(await link.query("MEAS:MASS?"))
    if value >= NO_READING:
        raise RuntimeError("the balance reports no valid reading (overload)")   # -> quality invalid, value null
    return value


async def send(command):
    try:
        await link.command(command)
    except Refused as exc:
        raise DeviceFault(f"{exc} (the balance refused the command)", proof=f"SCPI: {exc}", effect="none",
                          hint="fix the command named in the message, then retry") from None


@balance.action(effect="reversible", idempotency="idempotent", completion_evidence="reported", max_duration_ms=3000)
async def tare(ctx) -> {"acknowledged": bool}:  # noqa: F821
    """Tare the balance: the current load becomes zero."""
    await send("TARE")
    return {"acknowledged": True}


@balance.action(effect="none", idempotency="idempotent", max_duration_ms=3000)
async def raw_command(ctx, command: str) -> {"acknowledged": bool}:  # noqa: F821
    """Send one raw SCPI command (for commissioning; do not expose it to agents in production)."""
    await send(command)
    return {"acknowledged": True}


@balance.liveness(interval_s=5)
async def alive():
    try:  # the identity query is answered whatever a command in progress does: liveness is not a command's reply
        return (await link.query("*IDN?")).startswith("BudLab,")
    except (Refused, DeviceLost):
        return False


if __name__ == "__main__":
    srv.run(sys.argv[1] if len(sys.argv) > 1 else None)
```

Three declarations carry the honesty rules: the mass is `measured` (a load cell is an independent sensor, unlike a
driver echo), an overload raises in the getter (so it becomes `quality: invalid` with `value: null`), and `tare`
completes `reported` (the instrument accepted it; nothing measured the effect).

### Try it

```sh run background wait=balance.sock
BHMS_STATE_DIR=$PWD/adapter-state python balance_adapter.py unix:balance.sock
```

```sh run
bhms describe unix:balance.sock balance-1
bhms read unix:balance.sock balance-1 mass
bhms call unix:balance.sock balance-1 tare --key tare-1
bhms read unix:balance.sock balance-1 mass
```

```text output
action tare() effect=reversible repeat=idempotent lease=no cancel=no evidence=reported max=3s -> {acknowledged: boolean}
property mass: number g -220..220 measured observable
balance-1.mass = 12... g (measured, valid, ... old)
balance-1.tare op-... completed: acknowledged true (effect unverified, ...)
balance-1.mass = ... g (measured, valid, ... old)
```

A value outside the declared schema is never passed on: had the range been `Range(0, 220)`, a net reading of
-0.0003 g after the tare would come back `invalid`. Declare the range the instrument can really report.

An overload is an invalid reading, not a number (`--fresh` asks for a new acquisition; without it a reading up to a
second old may be served, with its age):

```sh run
touch overload
bhms read unix:balance.sock balance-1 mass --fresh
```

```text output
balance-1.mass has no usable value (measured, invalid, ... old); do not act on it; check the device or read again with fresh=true
```

A command the instrument rejects is a failure with proof that nothing happened (`effect none`):

```sh run exit=1
rm overload
bhms call unix:balance.sock balance-1 raw_command command=CALIBRATE:NOW --key cal-1
```

```text output
balance-1.raw_command op-... failed: DEVICE_FAULT: "SCPI error -113: Undefined header ... (effect none, ...)
```

The one-line summary is cut to fit a model's context; `--json` prints the whole record, with the proof in the history:

```sh run exit=1
bhms call unix:balance.sock balance-1 raw_command command=CALIBRATE:NOW --key cal-1 --json
```

```text output
"message": "SCPI error -113: Undefined header (the balance refused the command)",
"mayHaveActed": false,
```

A reply that never comes after the command left is an unknown outcome (exit status 3), and the resource is blocked until
someone finds out what happened:

```sh run exit=3
touch hang
bhms call unix:balance.sock balance-1 tare --key tare-2
```

```text output
balance-1.tare op-... unknown: ...
```

```sh run
rm hang
bhms ops unix:balance.sock --state unknown
```

```text output
op-... balance-1.tare unknown unknown ...
```

For `tare` a reconcile hook cannot read back anything that proves the tare happened (a later reading near zero could
equally mean an empty pan), so this adapter has none, and an operator resolves the operation with what they checked
(`bhms resolve ... --state completed --basis ...`; [leases and safety](leases-and-safety.md)). For writes that can be
read back (a setpoint register), write the hook: see the Modbus adapter's `reconcile` below.

The full SimLab version, [`simlab/src/simlab/adapters/scpi.py`](../../../simlab/src/simlab/adapters/scpi.py), is
driven by a profile (queries become properties, commands become actions) and tags each command for correlation with the
instrument's journal; its tests are [`simlab/tests/test_scpi_adapter.py`](../../../simlab/tests/test_scpi_adapter.py).

## Modbus TCP

SimLab's [`adapters/modbus.py`](../../../simlab/src/simlab/adapters/modbus.py) turns a register profile into a device
with pymodbus 3.8.6 (fault-tested in [`simlab/tests/test_modbus_adapter.py`](../../../simlab/tests/test_modbus_adapter.py),
against a pymodbus thermal block; it needs pymodbus and the SimLab world, so it is not run by the docs test). The
mapping:

| Modbus | BHMS |
|---|---|
| Holding or input register, scaled: `value = (raw - offset) * scale` | a property in the register's unit, `reported` unless the profile marks it `measured` |
| A sentinel raw value (sensor open) | the getter raises: `quality: invalid` |
| Writable holding register | an action `set_<name>`, `effect="reversible"`, `idempotency="absolute"`, `completion_evidence="reported"`, then read back |
| Exception response 1, 2 or 3 (illegal function, address, value) | `DeviceFault(..., proof=..., effect="none")`: the request was rejected, not executed |
| Exception 4 and above, a timeout or a dropped connection after the write | unknown (the unit may have acted) |
| Reconcile | read the register back: equal to the target is `completed` (`unverified`), anything else stays unknown |

The code is in [`simlab/src/simlab/adapters/modbus.py`](../../../simlab/src/simlab/adapters/modbus.py) (not copied
here, so it cannot drift): the `Register` dataclass (address, table, scale, unit, evidence, bounds, `invalid_raw`
sentinel), `ILLEGAL_CODES = {1, 2, 3}` and `ModbusLink.write` (an exception response with one of those codes raises
`Refused`, which `refusal_fault` turns into `DeviceFault(..., effect="none")`; any other code, a timeout or a lost
connection after the write is left to become `unknown`), `_decode` (scale, sign, sentinel), and the `reconcile` hook
inside `build_server` (read the register back; equal within one scale step is `Reconciled("completed", ...,
effect="unverified")`, anything else returns `None`).

## OPC UA

SimLab's [`adapters/opcua.py`](../../../simlab/src/simlab/adapters/opcua.py) (asyncua; tested in
[`simlab/tests/test_opcua_adapter.py`](../../../simlab/tests/test_opcua_adapter.py) against an asyncua centrifuge server)
maps a node profile:

| OPC UA | BHMS |
|---|---|
| Variable (Read service) | a property; a bad status code or an unreachable server is `quality: invalid`, never a stale value passed off as current |
| Method (Call service) | an action, `completion_evidence="reported"`: a method returns when the unit accepted the call |
| A method following the `(Ok, Message)` interlock convention, returning `Ok = false` | `DeviceFault(..., effect="none")`: the unit refused before acting |
| `BadInvalidArgument`, `BadMethodInvalid`, `BadNotImplemented`, `BadUserAccessDenied`, `BadArgumentsMissing`, `BadTooManyArguments`, `BadNodeIdUnknown` | the same: a malformed or refused request |
| Any other failure after the call left (a communication status, a timeout, a dropped session) | unknown; the profile's `confirm` variable is read back to reconcile |
| A tachometer or other sensor node | a separate `measured` property for the agent to check |

OPC UA Programs (Part 10) map to BHMS operations; [spec 15.3](../../../spec/bhms/15-mappings.md#153-bhms--opc-ua-methods-and-programs-part-10)
says what the mapping preserves and loses.

## Checklist for your adapter

- Run `bhms conformance <your-adapter-target>` ([running conformance](conformance.md)): the generic checks use only
  your descriptions and refuse to execute effectful actions unless you allow it.
- Describe the device so an agent understands it ([designing descriptions](descriptions.md)).
- Put it behind a gateway with a policy before an agent can reach it ([deploying a gateway](gateway.md)).
