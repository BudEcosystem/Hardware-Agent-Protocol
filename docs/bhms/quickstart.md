# Quickstart

This page takes you from nothing to a device that an AI agent can operate safely: install the SDK, write a device server,
inspect and test it, connect Claude (or any MCP client) and an OpenAI model, and put a gateway with a policy in front.

Every command and program on this page is executed by `sdk/python/tests/test_docs_examples.py`, in this order, so what
you see is what it prints. Run the steps in one empty directory. The device is simulated; the section "For real
hardware" at the end says what to change.

## 1. Install

You need Python 3.11 or newer. From a checkout of this repository (installing is not run by the test, which uses the
checkout directly):

```sh no-run
python3 -m venv .venv && . .venv/bin/activate
pip install -e 'sdk/python[mcp,openai]'     # bhms, the MCP bridge and the OpenAI adapter
```

`bhms doctor` checks the installation (it never prints secrets; an OpenAI key is reported only as present or absent):

```sh run
bhms doctor
```

```text output
ok python ...
ok schema bhms.schema.json, protocol 2026-11-13
... checks, 0 failed; pass a target to check connectivity
```

## 2. Write a device server

A device server is a small process next to the hardware. This one has one device, `stage-z`, with one property and one
action. Save it as `stage_server.py`:

```python file=stage_server.py
"""A simulated motorised stage, served over BHMS: the quickstart's device."""
import sys

from bhms import Canceled, DeviceServer, Range


def build(**options) -> DeviceServer:
    srv = DeviceServer("quickstart-stage", instructions="One simulated linear stage, stage-z, travel 0 to 200 um.",
                       **options)
    stage = srv.device("stage-z", name="Z stage", description="Simulated motorised linear stage.",
                       capabilities=["bhms.axis.linear"], resources=["stage-z/axis"])
    stage.report_alive()  # a real driver reports life when its link is up (or declares @stage.liveness)
    z = {"um": 0.0}       # the simulation: replace with your driver

    @stage.property(unit="um", evidence="simulated", max_rate_hz=10)
    def position() -> float:
        """Current position of the stage carriage."""
        return z["um"]

    @stage.action(effect="reversible", idempotency="absolute", max_duration_ms=5000, cancel="supported")
    async def move_to(ctx, target: Range(0, 200, unit="um")) -> {"position": "um"}:  # noqa: F821
        """Move the carriage to an absolute position."""
        start = z["um"]
        for step in range(1, 11):
            if await ctx.wait_cancelled(0.01):
                raise Canceled(effect="unverified", detail=f"stopped at {z['um']:.1f} um")
            z["um"] = start + (target - start) * step / 10
            await ctx.progress(step / 10)
        return {"position": z["um"]}

    @stage.on_stop(evidence="reported", max_duration_ms=500)
    async def halt(ctx):
        """Stop motion now (the simulated motor stops between steps on its own)."""

    return srv


if __name__ == "__main__":
    build().run(sys.argv[1] if len(sys.argv) > 1 else None)  # stdio by default, or unix:<path> / ws://127.0.0.1:<port>
```

What each declaration tells a client (all of it ends up in the device description, see [concepts](concepts.md)):

- `Range(0, 200, unit="um")`: the argument's bounds and its UCUM unit. A value outside is refused before anything moves.
  Every number carries a unit; a bare `float` argument is refused when you declare the action.
- `effect="reversible"`, `idempotency="absolute"`: what the action does to the world, and what a duplicate would do.
- `max_duration_ms=5000`: the server enforces it; an action with a physical effect must declare one.
- `cancel="supported"`: the handler honours `ctx.cancelled` and says what it knows when it stops early.
- `evidence="simulated"`: how the value is known. Change it to `measured` only when a real sensor (an encoder) backs it.
- `@stage.on_stop`: the commissioned stop procedure that `stop` runs. It is not an emergency stop.

## 3. Use it from the command line

`bhms` commands take a target first: a URL, or a server script, which they start over stdio for the one command.

```sh run
bhms ls stage_server.py
```

```text output
DEVICE NAME STATUS CAPABILITIES ACTIONS PROPERTIES
stage-z Z stage online bhms.axis.linear move_to position
```

`describe` prints the one-line signature a model also sees:

```sh run
bhms describe stage_server.py stage-z
```

```text output
stage-z "Z stage": 1 action, 1 property; signature below
action move_to(target: number um 0..200) effect=reversible repeat=absolute lease=no cancel=yes evidence=reported max=5s -> {position: number um}
property position: number um simulated observable
stop: supported (reported); on disconnect: unknown
```

Invoke the action with an operation key. The key makes the request safe to retry: the same key with the same request
returns the same operation and never moves twice.

```sh run
bhms call stage_server.py stage-z move_to target=42.5 --key first-move
bhms call stage_server.py stage-z move_to target=42.5 --key first-move
```

```text output
stage-z.move_to op-... completed: position 42.5 um (effect unverified, ...)
stage-z.move_to op-... replayed: completed position 42.5 um (effect unverified, ...)
```

`effect unverified` is honest: the stage reported the move, but nothing measured it. A target outside the travel is
refused, with the bound and a correction, and exit status 1:

```sh run exit=1
bhms call stage_server.py stage-z move_to target=500
```

```text output
Refused: arguments.target 500 um is above the maximum 200 um. Next: send target between 0 and 200 um; e.g. arguments {"target":0}.
```

The operations are durable: they are in a journal under `$BHMS_STATE_DIR` (default `~/.local/state/bhms`), so a
script target started again still knows them:

```sh run
bhms ops stage_server.py
```

```text output
OPERATION WHAT STATE EFFECT UPDATED
op-... stage-z.move_to completed unverified ...
```

The simulated position, on the other hand, lived in the process that each command started and stopped. A real server
runs for a long time. Start one on a Unix socket, with its own state directory (one server owns a state directory),
and leave it running:

```sh run background wait=stage.sock
BHMS_STATE_DIR=$PWD/stage-state python stage_server.py unix:stage.sock
```

```sh run
bhms call unix:stage.sock stage-z move_to target=120 --key second-move
bhms read unix:stage.sock stage-z position
```

```text output
stage-z.move_to op-... completed: position 120 um (effect unverified, ...)
stage-z.position = 120 um (simulated, valid, ... old)
```

`bhms dev unix:stage.sock` opens the interactive inspector (devices, describe, prompts for every argument with its unit
and bounds, a live feed of operations). It reads commands line by line, so it can be scripted too:

```sh run
printf 'ls\ndescribe 1\nquit\n' | bhms dev unix:stage.sock
```

```text output
connected to quickstart-stage 0.1.0 as uid:..., protocol 2026-11-13
1 stage-z Z stage online move_to position
```

## 4. Use it from Python

The client has a typed coroutine for every protocol method. This program moves the stage, then reads the position:

```python run
import asyncio

from bhms.client import Client


async def main():
    async with await Client.connect("unix:stage.sock") as client:
        invoked = await client.actions_invoke("stage-z", "move_to", {"target": 60}, operation_key="py-move", wait_ms=5000)
        op = invoked.operation
        print(op.state, op.effect, op.result)
        observation = (await client.properties_read("stage-z", "position")).observation
        print(observation.value, observation.unit, observation.evidence, observation.quality)


asyncio.run(main())
```

```text output
completed unverified {'position': 60.0}
60.0 um simulated valid
```

## 5. Test it

`bhms.testing.connect` serves a `DeviceServer` in-process, with every message validated against the schema. `store=None`
keeps the journal in memory for tests. Save as `test_stage.py`:

```python file=test_stage.py
import asyncio

from bhms import BhmsError
from bhms.testing import connect
from stage_server import build


def test_moves_and_reports_the_position():
    async def scenario():
        async with connect(build(store=None)) as client:
            op = (await client.actions_invoke("stage-z", "move_to", {"target": 10}, operation_key="t", wait_ms=5000)).operation
            assert op.state == "completed" and op.result == {"position": 10.0}
    asyncio.run(scenario())


def test_out_of_range_is_refused_and_nothing_moves():
    async def scenario():
        async with connect(build(store=None)) as client:
            try:
                await client.actions_invoke("stage-z", "move_to", {"target": 500})
            except BhmsError as refusal:
                assert refusal.bhms_code == "OUT_OF_RANGE" and refusal.may_have_acted is False
            else:
                raise AssertionError("expected a refusal")
            assert (await client.properties_read("stage-z", "position")).observation.value == 0.0
    asyncio.run(scenario())
```

```sh run
python -m pytest -q -p no:cacheprovider test_stage.py
```

```text output
2 passed in ...
```

`bhms new <name>` writes a server, a test like this one and a README for a new project.

## 6. Connect Claude or any MCP client

`bhms mcp <target>` serves eight agent tools (`bhms_find`, `bhms_describe`, `bhms_read`, `bhms_invoke`,
`bhms_operation`, `bhms_cancel`, `bhms_stop`, `bhms_run_program`) over MCP's stdio transport. The tools handle operation
keys, leases and refusals the way a model needs ([agent tools reference](reference/agent-tools.md)).

For Claude Desktop, add the server to `claude_desktop_config.json` (not run by the test: it is Claude Desktop's file; use
absolute paths, since Claude Desktop does not start in your directory):

```json no-run
{
  "mcpServers": {
    "bench": {
      "command": "/home/you/bhms/.venv/bin/bhms",
      "args": ["mcp", "unix:/home/you/bhms/stage.sock"]
    }
  }
}
```

For Claude Code (not run by the test: it changes your Claude Code configuration):

```sh no-run
claude mcp add bench -- "$PWD/.venv/bin/bhms" mcp "unix:$PWD/stage.sock"
```

Any MCP client works the same way. This program uses the official `mcp` Python SDK to start the bridge, list the tools
and call two of them, exactly as an agent host does:

```python run
import asyncio
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    # env: the MCP SDK starts servers with a minimal environment unless told otherwise
    bridge = StdioServerParameters(command="bhms", args=["mcp", "unix:stage.sock"], env=dict(os.environ))
    async with stdio_client(bridge) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        print(sorted(tool.name for tool in (await session.list_tools()).tools))
        moved = await session.call_tool("bhms_invoke", {"device_id": "stage-z", "action": "move_to",
                                                        "arguments": {"target": 75}, "operation_key": "mcp-move"})
        print(moved.content[0].text)
        refused = await session.call_tool("bhms_invoke", {"device_id": "stage-z", "action": "move_to",
                                                          "arguments": {"target": 900}})
        print(refused.isError, refused.content[0].text)


asyncio.run(main())
```

```text output
['bhms_cancel', 'bhms_describe', 'bhms_find', 'bhms_invoke', 'bhms_operation', 'bhms_read', 'bhms_run_program', 'bhms_stop']
stage-z.move_to op-... completed: position 75 um (effect unverified, ...)
True Refused: arguments.target 900 um is above the maximum 200 um. Next: send target between 0 and 200 um; e.g. arguments {"target":0}.
```

The refusal is a tool result with `isError: true` and a correction, not a protocol failure, so a model can read it and
fix its call. The bridge checks arguments against the action's schema before it sends anything that could act.

## 7. Connect an OpenAI model

`bhms.bridges.openai_tools` gives the same eight tools as OpenAI function definitions (`api="responses"` for the
Responses API, `api="chat"` for Chat Completions) and executes the calls a model makes through the same bridge. This
part needs no network: it builds the tool list and dispatches a function call shaped exactly as the Responses API returns
it.

```python run
import asyncio
import json

from bhms.bridges import AgentBridge
from bhms.bridges.openai_tools import tools_for_openai
from bhms.client import Client


async def main():
    async with await Client.connect("unix:stage.sock") as client:
        tools = tools_for_openai(client, api="responses")
        print([tool["name"] for tool in tools][:4], tools[0]["strict"])
        # A function_call item as the model sends it: a name and a JSON string of arguments.
        call = {"type": "function_call", "call_id": "call_1", "name": "bhms_invoke",
                "arguments": json.dumps({"device_id": "stage-z", "action": "move_to", "arguments": {"target": 90},
                                         "operation_key": "llm-move-1"})}
        bridge = AgentBridge(client)
        try:
            result = await bridge.call(call["name"], json.loads(call["arguments"]))
        finally:
            await bridge.aclose()
        reply = {"type": "function_call_output", "call_id": call["call_id"],
                 "output": json.dumps(result.function_output())}
        print(result.summary)
        print(json.loads(reply["output"])["data"]["operation"]["state"])


asyncio.run(main())
```

```text output
['bhms_find', 'bhms_describe', 'bhms_read', 'bhms_invoke'] False
stage-z.move_to op-... completed: position 90 um (effect unverified, ...)
completed
```

`run_agent` is the whole loop: it sends the task, executes each tool call in order (they are physical actions, so
never in parallel), feeds the results back and stops at the model's answer or at the token budget. It reads the key from
`OPENAI_API_KEY` (or `~/.config/hms/openai.env`) and never logs it. The test runs this block only when `OPENAI_API_KEY`
is set in its environment; `OPENAI_MODEL` picks the model (GPT-6-family models accept function tools only on the
Responses API).

```python run requires=openai timeout=300
import asyncio
import os

from bhms.bridges.openai_tools import run_agent
from bhms.client import Client


async def main():
    async with await Client.connect("unix:stage.sock") as client:
        run = await run_agent(client, os.environ.get("OPENAI_MODEL", "gpt-5.4-mini"),
                              "Move stage-z to 25 um, then read its position and report it.", budget=30_000)
        for step in run.steps:
            print(step.tool, step.summary)
        print(run.stopped, run.tokens, "tokens")
        print(run.final_text)
        assert run.stopped == "final" and any(s.tool == "bhms_invoke" and not s.is_error for s in run.steps)


asyncio.run(main())
```

## 8. Put a gateway in front

A gateway serves many device servers behind one endpoint, with principals, scopes, narrowed bounds, cross-device
leases and its own journal. Clients cannot tell it from a device server, except that device ids get a namespace
(`lab/stage-z`). Save as `gateway.toml`:

```toml file=gateway.toml
[gateway]
id = "quickstart-gw"
state_dir = "gw-state"                       # the gateway's journal; relative to this file
listen = ["unix:gateway.sock", "ws://127.0.0.1:8765"]
instructions = "A quickstart bench: one simulated stage, lab/stage-z."

[[upstream]]
name = "lab"                                 # devices become lab/<deviceId>
stdio = "{python} {config_dir}/stage_server.py"
env = { BHMS_STATE_DIR = "{config_dir}/gw-state/lab" }

[principals.agent]                           # the token is demo-agent-token; only its sha256 is stored
tokens = ["sha256:b83e3e191f2acfe2c3c27f2079c5c13ea8409e9abbf31b671d421d80bbc847c9"]
scopes = ["read", "lease", "invoke:lab/*/*", "stop:lab/*"]
bounds = { "lab/stage-z/move_to" = { target = { maximum = 100 } } }
```

Token digests come from `python -c "from bhms import token_digest; print(token_digest('my-token'))"`. Peers on the Unix
socket with your own uid are `admin` (set `trust_same_uid = false` to require a listed uid). Before serving, check what
each scope grants among the devices actually served:

```sh run
bhms gateway check-policy gateway.toml
```

```text output
1 device served
principal agent
invoke:lab/*/*: lab/stage-z/move_to
stop:lab/*: lab/stage-z
```

Run it:

```sh run background wait=tcp:127.0.0.1:8765
bhms gateway gateway.toml
```

The agent principal sees the narrowed bound (100 um instead of 200) in the description, and is held to it:

```sh run
export BHMS_TOKEN=demo-agent-token
bhms describe ws://127.0.0.1:8765 lab/stage-z
bhms call ws://127.0.0.1:8765 lab/stage-z move_to target=80 --key agent-1
```

```text output
action move_to(target: number um 0..100) effect=reversible repeat=absolute lease=no cancel=yes evidence=reported max=5s -> {position: number um}
lab/stage-z.move_to op-... completed: position 80 um (effect unverified, ...)
```

```sh run exit=1
BHMS_TOKEN=demo-agent-token bhms call ws://127.0.0.1:8765 lab/stage-z move_to target=150
```

```text output
Refused: arguments.target 150 um is above the maximum 100 um. Next: send target between 0 and 100 um; e.g. arguments {"target":0}.
```

Stop is always available to a principal with the `stop` scope, and never waits behind leases or queued work:

```sh run
BHMS_TOKEN=demo-agent-token bhms stop ws://127.0.0.1:8765 lab/stage-z
```

```text output
stop: 1 confirmed lab/stage-z confirmed (0 operations canceled)
```

A wrong token is refused at the WebSocket handshake:

```sh run exit=1
BHMS_TOKEN=not-the-token bhms ls ws://127.0.0.1:8765
```

```text output
error: cannot connect to ws://127.0.0.1:8765: server rejected WebSocket connection: HTTP 401
hint: the server refused the credential: pass --token or set BHMS_TOKEN to a token its policy lists
```

An agent connects through the gateway with its own token: `bhms mcp ws://127.0.0.1:8765` with `BHMS_TOKEN` set in the
MCP server's environment (in Claude Desktop: an `"env"` member next to `"args"`).

## For real hardware

The server above is the shape of a real one; what changes when `z` becomes a motor:

- **The driver.** Replace the dictionary with your driver's calls in `move_to`, `position` and `halt`. Raise
  `DeviceLost` (from `bhms.server`) when the link drops mid-command, so the outcome becomes `unknown` instead of a guess,
  and add a `@stage.reconcile` hook that asks the controller what happened.
- **Evidence.** `evidence="simulated"` becomes `measured` only with an independent sensor (an encoder); a driver's echo
  is `reported`. With an encoder, declare `completion_evidence="measured", verified_by=["position"]` and confirm in the
  handler with `await ctx.verify("position", ...)`.
- **Limits in the device.** Keep `Range(0, 200, ...)` equal to the real travel, and enforce limits again in the
  controller; a policy can only narrow them. Totals (a dose, a reagent budget) must be enforced in the device too.
- **Liveness and stop.** Declare `@stage.liveness(interval_s=5)` so a dead link reads `offline`, make `halt` stop the
  motor and confirm it, and keep a hardware emergency stop that does not depend on software.
- **Exclusive access.** Declare `requires_lease=True` for anything hazardous, and put the server behind a gateway with
  per-principal scopes and bounds, on a loopback listener behind TLS.

The [leases and safety](guides/leases-and-safety.md) guide ends with the full checklist; [wrapping a real instrument](guides/wrap-an-instrument.md)
does all of this for a SCPI balance.

## Next

- [Concepts](concepts.md): what effects, evidence, unknown outcomes, leases and stop mean.
- [Wrapping a real instrument](guides/wrap-an-instrument.md): replace the simulation with SCPI, Modbus or OPC UA.
- [Leases and safety](guides/leases-and-safety.md) and [deploying a gateway](guides/gateway.md) before anything moves
  for real.
- [Running conformance](guides/conformance.md): prove what your server claims.
