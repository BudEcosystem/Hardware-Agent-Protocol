# Connecting agents (MCP clients, Claude, OpenAI)

This guide shows how to give an AI agent access to BHMS devices: through the MCP bridge for Claude and any other MCP
client (stdio or Streamable HTTP), and through the OpenAI function-tool adapter for the Responses and Chat Completions
APIs, including how to test an agent loop without a network. The agent surface is defined in
[spec 12](../../../spec/bhms/12-agent-surface.md); the exact tool texts are in the [agent tools reference](../reference/agent-tools.md).
Every block below is executed by the docs test (the one that calls OpenAI only when `OPENAI_API_KEY` is set).

## What the model gets

Eight tools, the same through every adapter: `bhms_find`, `bhms_describe`, `bhms_read`, `bhms_invoke`, `bhms_operation`,
`bhms_cancel`, `bhms_stop` and, when the server offers programs, `bhms_run_program`. Behind them one bridge
(`bhms.bridges.AgentBridge`) does what a model should not have to:

- every result starts with a one-line summary; a refusal is a tool result that says what to change, with an example;
- arguments are checked against the action's schema before anything is sent that could act;
- `operation_key` makes a retry return the original operation instead of acting twice;
- leases are acquired on exactly the resources an action needs, renewed while it runs, released when it settles;
- text that comes from devices (names, descriptions, instructions) is quoted as data, never as instructions;
- the bridge's own connection is the principal: tool arguments carry no identity, scopes or bounds.

The bridge never exposes `operations/resolve`: resolving an unknown outcome is for a person.

Give an agent its own principal on a gateway, with the default agent scopes (`read`, `lease`, `invoke:<glob>/*` and
`stop:<glob>` for its devices) and narrowed bounds, never `admin` ([deploying a gateway](gateway.md)). The examples below
connect to a device server directly to stay short.

## MCP over stdio

`bhms mcp <target>` is an MCP server on stdin/stdout. The target is a URL (`unix:`, `ws://`, `http://`), a device server
script or a gateway TOML file. This program drives it with the official `mcp` SDK, as an agent host does. The pump's
`dispense` requires a lease; the bridge takes care of it:

```python run
import asyncio
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    # The MCP SDK starts servers with a minimal environment (HOME, PATH, USER, ...): pass BHMS_STATE_DIR, BHMS_TOKEN
    # and the like explicitly, or the bridge and the server it starts will not see them.
    bridge = StdioServerParameters(command="bhms", args=["mcp", "examples/bhms/pump_server.py"], env=dict(os.environ))
    async with stdio_client(bridge) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        print(init.instructions.split(".")[0])
        found = await session.call_tool("bhms_find", {})
        print(found.content[0].text)
        described = await session.call_tool("bhms_describe", {"device_id": "pump-1"})
        print(described.content[1].text if len(described.content) > 1 else described.content[0].text)
        done = await session.call_tool("bhms_invoke", {"device_id": "pump-1", "action": "dispense",
                                                       "arguments": {"volume": 25}, "operation_key": "mcp-dispense-1"})
        print(done.content[0].text)
        print(done.structuredContent["operation"]["leaseId"] is not None)
        resources = await session.list_resources()
        print([str(r.uri) for r in resources.resources])


asyncio.run(main())
```

```text output
Operate physical devices through BHMS
1 device, 0 programs: pump-1 "Syringe pump" online Next: bhms_describe a device before acting
action dispense(volume: number uL 1..500 step 0.1) effect=irreversible repeat=relative lease=required cancel=no evidence=reported max=10s -> {dispensed: number uL}
pump-1.dispense op-... completed: dispensed 25 uL (effect unverified, ...)
True
['bhms://device/pump-1', 'bhms://grammar/program']
```

Each device is also an MCP resource (`bhms://device/<id>`) whose content is the full description as JSON, and
`bhms://grammar/program` is the program grammar (the same text as `bhms_describe {"topic": "program-grammar"}`, for
hosts that read resources).

### Claude Desktop, Claude Code, Cursor

These are other programs' configuration files, so the docs test does not run them; they start the same command as
above. Use absolute paths: these hosts do not start in your directory, and they pass only a minimal environment, so
put `BHMS_TOKEN` (and `BHMS_STATE_DIR` for a server script target) in `env`, never in the arguments.

Claude Desktop (`claude_desktop_config.json`) and Cursor (`.cursor/mcp.json`) use the same shape:

```json no-run
{
  "mcpServers": {
    "lab": {
      "command": "/srv/bhms/.venv/bin/bhms",
      "args": ["mcp", "ws://127.0.0.1:8765"],
      "env": { "BHMS_TOKEN": "the agent principal's token" }
    }
  }
}
```

Claude Code:

```sh no-run
claude mcp add lab --env BHMS_TOKEN="$LAB_AGENT_TOKEN" -- /srv/bhms/.venv/bin/bhms mcp ws://127.0.0.1:8765
```

## MCP over Streamable HTTP

For a host that connects over the network, serve the bridge with `--http HOST:PORT` (path `/mcp`) and require a bearer
token from MCP clients with `--http-token` or `BHMS_MCP_TOKEN` (required on a non-loopback address). This token is the
MCP client's credential to the bridge; the bridge's own credential to its BHMS target is `--token`/`BHMS_TOKEN`.

```sh run background wait=tcp:127.0.0.1:8770
export BHMS_STATE_DIR=$PWD/bridge-state    # the thermometer this bridge starts owns its own state directory
BHMS_MCP_TOKEN=bridge-secret bhms mcp examples/bhms/thermo_server.py --http 127.0.0.1:8770
```

```python run
import asyncio

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():
    async with httpx.AsyncClient(headers={"Authorization": "Bearer bridge-secret"}) as http:
        async with streamable_http_client("http://127.0.0.1:8770/mcp/", http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print(len((await session.list_tools()).tools), "tools")
                reading = await session.call_tool("bhms_read", {"device_id": "thermo-1", "property": "temperature"})
                print(reading.content[0].text)
    async with httpx.AsyncClient() as anonymous:
        print((await anonymous.post("http://127.0.0.1:8770/mcp/", json={})).status_code)


asyncio.run(main())
```

```text output
8 tools
thermo-1.temperature = ... Cel (simulated, valid, ... old)
401
```

Without the token the bridge answers 401 before any MCP traffic. The bridge speaks plain HTTP; put it behind TLS (a
reverse proxy) before it leaves the host.

## OpenAI: function tools

`tools_for_openai` returns the eight tools as function definitions in either API shape, with the MCP bridge's names,
descriptions and schemas (`strict` is false, because `arguments` and `program` are free-form objects). Pass a connected
client so that `bhms_run_program` appears only when the server offers programs (a gateway does not, in this version).

```python run
import asyncio

from bhms.bridges.openai_tools import tools_for_openai
from bhms.client import Client


async def main():
    responses_shape = tools_for_openai(api="responses")
    chat_shape = tools_for_openai(api="chat")
    print(responses_shape[3]["type"], responses_shape[3]["name"], sorted(responses_shape[3]["parameters"]["required"]))
    print(chat_shape[3]["type"], chat_shape[3]["function"]["name"])
    async with await Client.connect("stdio:python examples/bhms/thermo_server.py") as client:
        print(len(tools_for_openai(client)), "tools for this server (it offers programs)")


asyncio.run(main())
```

```text output
function bhms_invoke ['action', 'arguments', 'device_id']
function bhms_invoke
8 tools for this server (it offers programs)
```

## OpenAI: the agent loop

`run_agent(client, model, task, budget)` sends the task with the tools, executes each tool call through the bridge one
at a time and in order (they are physical actions; `parallel_tool_calls` is off), feeds back `{summary, data}` or
`{summary, error}`, and stops at the model's final answer, when the token `budget` (input plus output, across all
requests) would be exceeded, or after `max_steps` tool calls. A tool call in a response that exhausted the budget is not
executed. `api="responses"` (default) or `api="chat"`; GPT-6-family models accept function tools only on the Responses
API.

Its `llm=` parameter takes any object with the OpenAI SDK's surface, which is how you test your agent wiring without a
network or a key. This scripted model asks for one reading and then answers:

```python run
import asyncio
import json

from bhms.bridges.openai_tools import run_agent
from bhms.client import Client


class ScriptedResponses:
    """Two Responses API turns: a function call, then a final message (the shapes the API returns)."""

    def __init__(self):
        self.requests = []

    async def create(self, **request):
        self.requests.append(request)
        if len(self.requests) == 1:
            return {"id": "resp_1", "usage": {"input_tokens": 900, "output_tokens": 30}, "output": [
                {"type": "function_call", "call_id": "call_1", "name": "bhms_read",
                 "arguments": json.dumps({"device_id": "thermo-1", "property": "temperature"})}]}
        result = json.loads(request["input"][0]["output"])
        return {"id": "resp_2", "usage": {"input_tokens": 1100, "output_tokens": 20},
                "output_text": f"The bench reads {result['data']['observation']['value']:.1f} Cel."}


class ScriptedModel:
    def __init__(self):
        self.responses = ScriptedResponses()


async def main():
    model = ScriptedModel()
    async with await Client.connect("stdio:python examples/bhms/thermo_server.py") as client:
        run = await run_agent(client, "scripted", "What is the bench temperature?", budget=10_000, llm=model)
    print([(step.tool, step.is_error) for step in run.steps])
    print(run.stopped, run.tokens, run.requests)
    print(run.final_text.startswith("The bench reads"))
    first = model.responses.requests[0]
    print(first["parallel_tool_calls"], first["input"][0]["content"])


asyncio.run(main())
```

```text output
[('bhms_read', False)]
final 2050 2
True
False What is the bench temperature?
```

With a real model (runs only when `OPENAI_API_KEY` is set; `OPENAI_MODEL` picks the model). The key is read from
`OPENAI_API_KEY` or `~/.config/hms/openai.env` and handed only to the OpenAI client; it is never logged or printed:

```python run requires=openai timeout=300
import asyncio
import os

from bhms.bridges.openai_tools import run_agent
from bhms.client import Client


async def main():
    async with await Client.connect("stdio:python examples/bhms/pump_server.py") as client:
        run = await run_agent(client, os.environ.get("OPENAI_MODEL", "gpt-5.4-mini"),
                              "Dispense 20 uL with pump-1, then report the total the pump has dispensed.", budget=40_000)
    for step in run.steps:
        print(step.tool, step.is_error, step.summary[:100])
    print(run.stopped, run.tokens, "tokens")
    print(run.final_text)
    assert run.stopped == "final" and any(s.tool == "bhms_invoke" and not s.is_error for s in run.steps)


asyncio.run(main())
```

### A bound limits one call, not a total

In a live run of an earlier version of this guide, asked to "dispense 600 uL; if that is not possible, dispense
nothing", gpt-5.4-mini read the pump's 500 uL maximum and dispensed 500 uL and then 100 uL. Each call was within its
bounds and honestly reported; the total was not what the task allowed.

What controls a total today:

- **The device or its driver.** It is the only place that sees every call, whoever makes it and through whichever
  gateway. Keep the running total in the device and refuse, before acting, a call that would exceed it. This is the
  control to rely on.
- **Not the gateway policy.** `bounds` narrow each call; there is no cumulative limit or per-principal budget in this
  version. Budgets are an open gap of the specification, planned for spec v0.2.
- **A program, only on a device server.** A registered program (a reviewed sequence with fixed bounds) limits what one
  run does, but only when the agent holds `programs:run` and no `invoke:` scope on the raw action, and only on a device
  server: a gateway does not offer `programs/*` in this version ([writing programs](programs.md)).

A dispenser that enforces a batch total in its handler. The refusal is a `DeviceFault` with the code that names the
cause (`OUT_OF_RANGE`), proof that nothing was dispensed, and `effect="none"`, so the operation ends `failed` with
`mayHaveActed: false`:

```python run
import asyncio

from bhms import BhmsError, DeviceFault, DeviceServer, Range
from bhms.testing import connect

BATCH_LIMIT_UL = 500.0


def build() -> DeviceServer:
    srv = DeviceServer("dosing-bench", store=None)
    pump = srv.device("pump-1", name="Syringe pump", resources=["pump-1/plunger"])
    pump.report_alive()
    batch = {"uL": 0.0}

    @pump.property(unit="uL", evidence="reported")
    def batch_total() -> float:
        """Volume dispensed since the batch was opened."""
        return batch["uL"]

    @pump.action(effect="irreversible", idempotency="relative", requires_lease=True, max_duration_ms=10_000)
    async def dispense(ctx, volume: Range(1, 500, unit="uL", step=0.1)) -> {"dispensed": "uL", "batch_total": "uL"}:  # noqa: F821
        """Dispense a volume. The batch may total at most 500 uL; a call that would exceed it is refused, nothing moves."""
        if batch["uL"] + volume > BATCH_LIMIT_UL:
            raise DeviceFault(f"{volume} uL would bring the batch to {batch['uL'] + volume} uL, above {BATCH_LIMIT_UL} uL",
                              code="OUT_OF_RANGE", effect="none",
                              proof=f"refused before the plunger moved; batch total {batch['uL']} uL",
                              hint="open a new batch (an operator action) or dispense less")
        batch["uL"] += volume  # the real driver moves the plunger here
        return {"dispensed": volume, "batch_total": batch["uL"]}

    return srv


async def main():
    async with connect(build()) as client:
        lease = (await client.leases_acquire(["pump-1/plunger"], ttl_ms=30_000)).lease
        for key, volume in (("dose-1", 500), ("dose-2", 100)):
            op = (await client.actions_invoke("pump-1", "dispense", {"volume": volume}, lease_id=lease.lease_id,
                                              operation_key=key, wait_ms=5000)).operation
            error = (op.error.bhms_code, op.error.may_have_acted) if op.error else None
            print(volume, op.state, op.effect, error)
        print("total", (await client.properties_read("pump-1", "batch_total")).observation.value)


asyncio.run(main())
```

```text output
500 completed unverified None
100 failed none ('OUT_OF_RANGE', False)
total 500.0
```

In a real driver the total must survive a restart (keep it with the device, or in a file next to the server's state),
and opening a new batch is an operator action, not one the agent can call.

`AgentRun` records every step (`tool`, `arguments`, `summary`, `is_error`), the tokens spent and why the loop stopped
(`final`, `budget`, `max_steps`). Use it to audit what an agent did; the server's journal has the authoritative record.

## Writing your own adapter

Use `AgentBridge` directly: `tool_definitions()` for names, descriptions and input schemas, and
`await bridge.call(name, arguments)` for a `ToolResult` (`summary`, `data` or `error`, `function_output()`). Keep the
rules above: one tool call at a time, the summary first, refusals as results rather than errors, no identity in tool
arguments. Then prove it: `bhms conformance agent-bridge` checks the reference bridge, and
`bhms conformance mcp:<your bridge command> --device <target>` checks an MCP bridge of your own
([running conformance](conformance.md)).
