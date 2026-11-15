# TypeScript SDK

This guide shows how to write a BHMS device server and a client in TypeScript with `@bhms/sdk` (`sdk/typescript`), and
how it interoperates with the Python tools: the `bhms` CLI, the MCP bridge, the gateway and the conformance runner all
work against a TypeScript server unchanged. The SDK follows the Python reference behaviour for behaviour (operations,
leases, stop, journal); its API is in the [TypeScript reference](../reference/typescript-api.md). Every block below is
executed by the docs test with Node.js 20.

## Install

The package is not published to npm yet; build it from the checkout and depend on it by path (not run by the docs
test, which uses the checkout's build directly):

```sh no-run
(cd sdk/typescript && npm ci && npm run build)        # Node.js >= 20
mkdir my-device && cd my-device
npm init -y && npm install ../sdk/typescript typescript @types/node
```

The project is ESM (`"type": "module"`) compiled with `tsc`. Save as `package.json` and `tsconfig.json`:

```json file=package.json
{ "name": "my-device", "private": true, "type": "module" }
```

```json file=tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022", "module": "NodeNext", "moduleResolution": "NodeNext",
    "strict": true, "skipLibCheck": true, "outDir": "out", "types": ["node"]
  },
  "include": ["*.ts"]
}
```

## A device server

The same stage as the [quickstart](../quickstart.md), declared with method calls instead of decorators. Schemas come from
small builders (`range`, `num`, `int`, `str`, `bool`, `arrayOf`); every number needs a unit. Save as `stage.ts`:

```ts file=stage.ts
import { Canceled, DeviceServer, range } from "@bhms/sdk";

const srv = new DeviceServer("ts-stage", { instructions: "One simulated linear stage, stage-z, travel 0 to 200 um." });
const stage = srv.device("stage-z", {
  name: "Z stage", description: "Simulated motorised linear stage.",
  capabilities: ["bhms.axis.linear"], resources: ["stage-z/axis"],
});
stage.reportAlive(); // a real driver reports life when its link is up (or declares stage.liveness(...))
const z = { um: 0 };  // the simulation: replace with your driver

stage.property("position", { unit: "um", evidence: "simulated", description: "Current position of the carriage." }, () => z.um);

stage.action("move_to", {
  description: "Move the carriage to an absolute position.",
  effect: "reversible", idempotency: "absolute", maxDurationMs: 5000, cancel: "supported",
  input: { target: range(0, 200, "um") }, output: { position: "um" },
}, async (ctx, { target }) => {
  const start = z.um;
  for (let step = 1; step <= 10; step++) {
    if (await ctx.waitCancelled(10)) throw new Canceled({ effect: "unverified", detail: `stopped at ${z.um} um` });
    z.um = start + ((target as number) - start) * step / 10;
  }
  return { position: z.um };
});

stage.onStop({ evidence: "reported", maxDurationMs: 500 }, async () => { /* halt the motor */ });

await srv.run(process.argv[2]); // stdio by default; "unix:<path>" or "ws://127.0.0.1:<port>" listen
```

Compile it, and use it with the Python CLI exactly like a Python server (`stdio:<command>` starts it for the command):

```sh run requires=node
npx tsc -p tsconfig.json
bhms describe "stdio:node out/stage.js" stage-z
bhms call "stdio:node out/stage.js" stage-z move_to target=42.5 --key ts-move-1
```

```text output
action move_to(target: number um 0..200) effect=reversible repeat=absolute lease=no cancel=yes evidence=reported max=5s -> {position: number um}
property position: number um simulated observable
stop: supported (reported); on disconnect: unknown
stage-z.move_to op-... completed: position 42.5 um (effect unverified, ...)
```

## A client

`Client.connect` takes the same targets as the Python client (`stdio:`, `unix:`, `tcp://`, `ws://`); there is a typed
method for every protocol method, and errors are `BhmsError` with `bhmsCode`, `field`, `bound`, `mayHaveActed`, `retry` and
`hint`. Save as `client.ts`:

```ts file=client.ts
import { BhmsError, Client } from "@bhms/sdk";

const client = await Client.connect("stdio:node out/stage.js", { strict: true });
try {
  const { operation } = await client.actionsInvoke("stage-z", "move_to", { target: 120 },
    { operationKey: "ts-client-1", waitMs: 5000 });
  console.log(operation.state, operation.effect, JSON.stringify(operation.result));
  const again = await client.actionsInvoke("stage-z", "move_to", { target: 120 }, { operationKey: "ts-client-1" });
  console.log("replayed:", again.replayed, again.operation.operationId === operation.operationId);
  try {
    await client.actionsInvoke("stage-z", "move_to", { target: 500 });
  } catch (error) {
    if (!(error instanceof BhmsError)) throw error;
    console.log(error.bhmsCode, error.field, error.mayHaveActed);
  }
  const { observation } = await client.propertiesRead("stage-z", "position");
  console.log(observation.value, observation.unit, observation.evidence);
} finally {
  await client.close();
}
```

```sh run requires=node
npx tsc -p tsconfig.json
node out/client.js
```

```text output
completed unverified {"position":120}
replayed: true true
OUT_OF_RANGE arguments.target false
120 um simulated
```

`strict: true` validates every result against the schema, which is what you want in tests. The server's journal is
under `$BHMS_STATE_DIR` (default `~/.local/state/bhms`), like the Python SDK's; one server owns one state directory.

## Everything else works unchanged

- **Agents**: `bhms mcp "stdio:node out/stage.js"` serves the agent tools for this server
  ([connecting agents](connecting-agents.md)).
- **Gateway**: an upstream `stdio = "node {config_dir}/out/stage.js"` ([deploying a gateway](gateway.md)).
- **Conformance**: the runner launches the SDK's conformance device with `--device-command`
  ([running conformance](conformance.md)):

```sh run requires=node timeout=300 exit=3
bhms conformance conformance-device --device-command "node sdk/typescript/dist/src/testing/conformanceDevice.js" --only lifecycle
```

```text output
requirements: ... passed, 0 failed, ... skipped, ...
claim core: NOT supported (0 MUST failed, ... MUST unproven); ...
```

A run limited with `--only` proves only part of each profile, so nothing failed but the claims are not supported, and
the exit status is 3; the full run, which supports the claims, is in [running conformance](conformance.md).

## Differences from the Python SDK

- Declarations are method calls (`device.property(name, options, getter)`, `device.action(name, options, handler)`), and
  input schemas are member maps of builders (`{ target: range(0, 200, "um") }`) or full JSON Schemas.
- On Linux the journal lock is a kernel `flock(2)` held by a `flock(1)` helper; without `flock(1)` it falls back to a
  listening socket, which breaks BHMS-SEC-003 for stdio servers. See `sdk/typescript/README.md`.
- There is no TypeScript gateway, MCP bridge or OpenAI adapter: use the Python ones in front of a TypeScript server.
- Policy documents with `uids` are validated but not enforced (Node.js cannot read a Unix-socket peer's credentials).
