// The fifteen-line example works over stdio and WebSocket, like the Python example (sdk/python/examples/bench_stage.py).
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { BhmsError, Client, DeviceServer, range } from "../src/index.js";
import { PACKAGE_ROOT } from "./paths.js";

const example = join(PACKAGE_ROOT, "dist/examples/benchStage.js");

test("the example server over stdio", { timeout: 30_000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-ts-example-"));
  process.env.BHMS_STATE_DIR = dir;
  const client = await Client.connect(`stdio:node ${example}`, { strict: true });
  try {
    const desc = (await client.devicesDescribe("stage-z")).description;
    assert.equal((desc.actions.move_to.input as unknown as { properties: { target: { maximum: number } } }).properties.target.maximum, 200);
    const res = await client.actionsInvoke("stage-z", "move_to", { target: 120 }, { operationKey: "go", waitMs: 2000 });
    assert.equal(res.operation.state, "completed");
    assert.deepEqual(res.operation.result, { position: 120 });
    await assert.rejects(client.actionsInvoke("stage-z", "move_to", { target: 250 }), (e: unknown) => e instanceof BhmsError && e.bhmsCode === "OUT_OF_RANGE" && e.field === "arguments.target");
    const obs = (await client.propertiesRead("stage-z", "position")).observation;
    assert.deepEqual([obs.value, obs.evidence, obs.unit], [120, "simulated", "um"]);
  } finally {
    await client.close();
    delete process.env.BHMS_STATE_DIR;
  }
  assert.ok(existsSync(join(dir, "bench-stage.journal.jsonl")));
  rmSync(dir, { recursive: true, force: true });
});

test("a WebSocket listener without a configured token generates one (mode 0600) and requires it", { timeout: 30_000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-ts-ws-"));
  const srv = new DeviceServer("ws-stage", { stateDir: dir, log: () => undefined });
  const dev = srv.device("stage-z", { resources: ["stage-z"] });
  dev.action("move_to", { effect: "reversible", idempotency: "absolute", maxDurationMs: 1000, input: { target: range(0, 200, "um") } }, async () => ({}));
  try {
    const address = (await srv.run("ws://127.0.0.1:0"))!;
    const tokenFile = join(dir, "ws-stage.token");
    assert.equal(statSync(tokenFile).mode & 0o777, 0o600);
    await assert.rejects(Client.connect(`ws://${address}`), (e: unknown) => e instanceof BhmsError && e.bhmsCode === "UNAUTHORIZED");
    const client = await Client.connect(`ws://${address}`, { token: readFileSync(tokenFile, "utf8").trim(), strict: true });
    const op = (await client.actionsInvoke("stage-z", "move_to", { target: 33 }, { waitMs: 2000 })).operation;
    assert.equal(op.state, "completed");
    const sub = await client.subscribe({ operations: { all: true } });
    await client.actionsInvoke("stage-z", "move_to", { target: 34 }, { waitMs: 2000 });
    assert.equal(((await sub.next())!.params.operation as { state: string }).state, "accepted");
    sub.cancel();
    await client.close();
  } finally {
    await srv.close(200);
    rmSync(dir, { recursive: true, force: true });
  }
});
