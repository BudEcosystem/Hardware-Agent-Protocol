# Writing programs

This guide shows how to write a bounded program (a validated sequence of device steps that runs as one operation),
have the server check it before anything moves, register it so it can be run by digest, and offer it to an agent as a
tool. Programs are defined in [spec 8](../../../spec/bhms/08-programs.md); every block below is executed by the docs test.

A program is the right tool when several steps must run back to back with no round trip to a client in between (a
focus scan, a dispense-then-measure sequence), and when you want a reviewed sequence that a model can call by name
without composing it itself. A program runs inside one server: all its devices must be served by that server.

## A server with two devices

A focus axis and a camera that measures sharpness (simulated: sharpness peaks when the focus is at 2500 um). Save as
`scan_server.py`:

```python file=scan_server.py
import math
import sys

from bhms import DeviceServer, Range


def build(**options) -> DeviceServer:
    srv = DeviceServer("scan-bench", **options)
    focus = srv.device("focus-1", name="Focus axis", capabilities=["bhms.axis.linear"], resources=["focus-1/axis"])
    camera = srv.device("camera-1", name="Camera", capabilities=["bhms.sensor.image"])
    for device in (focus, camera):
        device.report_alive()
    z = {"um": 0.0}

    @focus.property(unit="um", evidence="simulated")
    def position() -> float:
        return z["um"]

    @focus.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
    async def move_to(ctx, position: Range(0, 5000, unit="um")) -> {"position": "um"}:  # noqa: F821
        """Move the focus to an absolute position."""
        z["um"] = position
        return {"position": position}

    @focus.action(effect="reversible", idempotency="relative", max_duration_ms=2000)
    async def move_by(ctx, distance: Range(-100, 100, unit="um")) -> {"position": "um"}:  # noqa: F821
        """Move the focus by a relative distance."""
        z["um"] = min(max(z["um"] + distance, 0.0), 5000.0)
        return {"position": z["um"]}

    @camera.property(unit="1", evidence="simulated")
    def sharpness() -> float:
        """Image sharpness, 0 to 1."""
        return round(math.exp(-((z["um"] - 2500.0) / 40.0) ** 2), 4)

    return srv


if __name__ == "__main__":
    build().run(sys.argv[1])
```

```sh run background wait=scan.sock
BHMS_STATE_DIR=$PWD/scan-state python scan_server.py unix:scan.sock
```

## The program

Steps are JSON objects. Values written exactly as `"${name}"` are references to inputs or saved results; there is no
string interpolation and no code. `deviceId`, `action` and `property` are always literals, so the server knows every
device, resource and duration before it starts. Save as `focus_scan.json`:

```json file=focus_scan.json
{
  "bhmsProgram": "2026-11-13",
  "name": "focus_scan",
  "description": "Move the focus to start, then step it up and record the sharpness after each step.",
  "input": {
    "type": "object", "additionalProperties": false, "required": ["start", "steps"],
    "properties": {
      "start": {"type": "number", "x-bhms-unit": "um", "minimum": 2000, "maximum": 3000},
      "steps": {"type": "integer", "x-bhms-unit": "1", "minimum": 1, "maximum": 20}
    }
  },
  "maxDurationMs": 120000,
  "steps": [
    {"kind": "invoke", "deviceId": "focus-1", "action": "move_to", "arguments": {"position": "${start}"}},
    {"kind": "repeat", "times": "${steps}", "as": "i", "steps": [
      {"kind": "invoke", "deviceId": "focus-1", "action": "move_by", "arguments": {"distance": 10}},
      {"kind": "read", "deviceId": "camera-1", "property": "sharpness", "fresh": true, "saveAs": "s"},
      {"kind": "assert", "predicate": {"op": "ne", "left": "${s.quality}", "right": "invalid"},
       "message": "sharpness unavailable"}
    ]}
  ],
  "output": {"lastSharpness": "${s.value}"}
}
```

Rules worth knowing before you write your own (all checked by the server):

- `repeat.times` is a literal (1 to 1000) or a reference to a required integer input whose schema has `minimum >= 1` and
  a `maximum`: the maximum is what the worst case is computed with.
- An argument that references an input is checked against the action's bounds through the input's own bounds: `start`
  above may range 2000 to 3000 um, inside `move_to`'s 0 to 5000 um. A wider input is refused at validation.
- The worst-case duration is the sum of the steps' bounds with every repeat multiplied out (an `invoke` counts its
  action's `maxDurationMs`, a `read` its `timeoutMs`, default 1000). Here: 5000 + 20 x (2000 + 1000) = 65000 ms, inside
  the declared 120000.
- A `saveAs` inside a `repeat` holds the last iteration's value after it; inputs and saved names share one namespace.

## Validation happens before the first step

A program that cannot fit its declared duration is refused with the computed bound, and nothing runs:

```python run
import asyncio
import json

from bhms import BhmsError
from bhms.client import Client


async def main():
    program = json.load(open("focus_scan.json"))
    program["maxDurationMs"] = 30_000
    async with await Client.connect("unix:scan.sock") as client:
        try:
            await client.programs_run(program=program, arguments={"start": 2400, "steps": 5})
        except BhmsError as refusal:
            print(refusal.bhms_code, refusal.field, refusal.bound, refusal.may_have_acted)
        print(len([op async for op in client.iter_operations()]), "operations")


asyncio.run(main())
```

```text output
OUT_OF_RANGE program.maxDurationMs 65000 False
0 operations
```

## Register and run by digest

Registration validates exactly as a run would and stores the program under its digest (sha256 over its canonical JSON).
Running by digest re-checks the caller's scopes, bounds and lease every time: registering grants nothing.

```python run
import asyncio
import json

from bhms.client import Client


async def main():
    program = json.load(open("focus_scan.json"))
    async with await Client.connect("unix:scan.sock") as client:
        info = (await client.programs_register(program)).info
        print(info.name, info.effect, info.worst_case_duration_ms, info.devices)
        run = await client.programs_run(digest=info.digest, arguments={"start": 2450, "steps": 5},
                                        operation_key="scan-1", wait_ms=10_000)
        op = run.operation
        print(op.kind, op.state, op.effect, op.result, op.progress)
        steps = [child async for child in client.iter_operations(parent_operation_id=op.operation_id)]
        print(len(steps), "step operations, keys", {s.key_origin for s in steps})


asyncio.run(main())
```

```text output
focus_scan reversible 65000 ['camera-1', 'focus-1']
program completed unverified {'lastSharpness': 1.0} steps_completed=16 steps_total=61
6 step operations, keys {'derived'}
```

`progress` counts executed steps against the worst case: 1 + 5 x 3 of at most 1 + 20 x 3. The registered `effect` is the most severe step effect; each `invoke` step is its own operation with a derived key, so
the run is idempotent as a whole (the same `operation_key` returns the same run) and every step is in the journal.
Steps run strictly in order; a failing step (or a false `assert`) ends the program `failed` and completed effects are
not rolled back: compensation is a new program.

## Programs as tools for agents

The agent bridge offers `bhms_run_program` when the server advertises programs, and `bhms_find` lists registered
programs next to devices. A model can fetch the grammar with `bhms_describe {"topic": "program-grammar"}`; a malformed
program is refused with the failing step's path and the grammar.

```python run
import asyncio

from bhms.bridges import AgentBridge
from bhms.client import Client


async def main():
    async with await Client.connect("unix:scan.sock") as client:
        bridge = AgentBridge(client)
        try:
            found = await bridge.call("bhms_find", {"text": "focus"})
            print(found.summary)
            program = found.data["programs"][0]
            print(program["name"], program["digest"][:15])
            digest = program["digest"]
            ran = await bridge.call("bhms_run_program", {"program_digest": digest, "arguments": {"start": 2480, "steps": 2},
                                                         "operation_key": "agent-scan-1", "wait_ms": 10_000})
            print(ran.summary)
            grammar = await bridge.call("bhms_describe", {"topic": "program-grammar"})
            print(grammar.summary)
        finally:
            await bridge.aclose()


asyncio.run(main())
```

```text output
1 device, 1 program: focus-1 "Focus axis" online Next: bhms_describe a device before acting
focus_scan sha256:...
program ... completed: lastSharpness 1 (effect unverified, ...)
program-grammar: the format of the program member of bhms_run_program follows
```

## Leases in programs

When a step's action requires a lease, pass `lease_id` to `programs_run`: the lease must be the caller's, active, and
cover the union of those steps' resources. A step whose action does not require a lease but uses a resource the lease
holds runs under it too, and the lease must then cover all of that step's resources. `stop` of any device a running
program uses stops the program. See [leases and safety](leases-and-safety.md).

## Limits

The server advertises its program limits in `server/discover` (`capabilities.programs.limits`): at most 256 steps, a
repeat bound of 1000, nesting depth 4, 4096 executed steps in the worst case, 64 variables and 64 KiB of canonical JSON,
and a server-chosen largest `maxDurationMs` (the Python SDK's default is one hour; `DeviceServer(program_limits=...)`
lowers it). A gateway does not offer `programs/*` in this version: run programs on the server that hosts their devices.
