import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { BhmsError } from "../src/errors.js";
import { Principal } from "../src/server/authority.js";
import { DeviceFault } from "../src/server/context.js";
import type { Budget, Program } from "../src/generated/types.js";
import { digest } from "../src/canonical.js";
import { rig, type Rig, counters } from "./harness.js";

const budget: Budget = { id: "total", action: "axis-1/*", quantity: "/count", unit: "1", total: 3 };
const denied = (e: unknown) => e instanceof BhmsError && e.bhmsCode === "OUT_OF_RANGE" && !e.mayHaveActed;
async function setup(b: Budget = budget, stateDir?: string): Promise<Rig> {
  return rig({ durable: !!stateDir, stateDir, policy: (peer) => new Principal(peer.principal, peer.scopes ?? ["admin"], {}, false,
    peer.principal === "budgeted" ? [b] : []) });
}
const connect = (r: Rig, scopes = ["read", "invoke:axis-1/*"]) => r.connect({ principal: "budgeted", scopes });

test("budget admission is atomic across racing calls and same-key replay never charges twice", async () => {
  const r = await setup();
  try {
    const c = await connect(r);
    const results = await Promise.allSettled(["one", "two"].map((operationKey) => c.actionsInvoke("axis-1", "pulse", { count: 2 }, { operationKey, waitMs: 2000 })));
    assert.equal(results.filter((x) => x.status === "fulfilled").length, 1);
    const rejected = results.find((x) => x.status === "rejected") as PromiseRejectedResult;
    assert.ok(denied(rejected.reason));
    const accepted = results.find((x) => x.status === "fulfilled") as PromiseFulfilledResult<any>;
    const key = accepted.value.operation.operationKey;
    assert.equal((await c.actionsInvoke("axis-1", "pulse", { count: 2 }, { operationKey: key })).operation.operationId,
      accepted.value.operation.operationId);
    assert.equal((await counters(r.client)).pulses, 2);
    await c.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 2000 });
    await assert.rejects(c.actionsInvoke("axis-1", "pulse", { count: 1 }), denied);
  } finally { await r.close(); }
});

test("lifetime budgets survive history pruning, key reuse and restart", async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-budget-"));
  let r = await setup(budget, dir);
  try {
    const c = await connect(r);
    await c.actionsInvoke("axis-1", "pulse", { count: 2 }, { operationKey: "old", waitMs: 2000 });
    r.server.journal.forget(r.server.store.prune(Date.now() + 1000));
    await r.close();
    r = await setup(budget, dir);
    const again = await connect(r);
    await assert.rejects(again.actionsInvoke("axis-1", "pulse", { count: 2 }, { operationKey: "old" }), denied);
    await again.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: "old", waitMs: 2000 });
    await assert.rejects(again.actionsInvoke("axis-1", "pulse", { count: 1 }), denied);
  } finally { await r.close(); rmSync(dir, { recursive: true, force: true }); }
});

test("only proven no-effect outcomes release a budget; unknown outcomes remain charged", async () => {
  const r = await setup({ ...budget, total: 1 });
  try {
    const dev = r.server.devices.get("axis-1")!;
    let outcome = "refuse";
    dev.action("dose", { effect: "reversible", idempotency: "relative", maxDurationMs: 1000,
      input: { count: { type: "number", "x-bhms-unit": "1" } }, resources: [] }, () => {
      if (outcome === "refuse") throw new DeviceFault("no delivery", { proof: "valve remained shut" });
      throw new Error("connection lost after dispatch");
    });
    const c = await connect(r);
    const first = (await c.actionsInvoke("axis-1", "dose", { count: 1 }, { waitMs: 1000 })).operation;
    assert.equal(first.error?.mayHaveActed, false);
    outcome = "lost";
    assert.equal((await c.actionsInvoke("axis-1", "dose", { count: 1 }, { waitMs: 1000 })).operation.state, "unknown");
    await assert.rejects(c.actionsInvoke("axis-1", "dose", { count: 1 }), denied);
  } finally { await r.close(); }
});

test("program grants retain budgets on each derived step", async () => {
  const program: Program = { bhmsProgram: "2026-11-13", name: "twice", description: "two pulses", maxDurationMs: 10_000,
    input: { type: "object", properties: {}, additionalProperties: false },
    steps: [1, 2].map(() => ({ kind: "invoke", deviceId: "axis-1", action: "pulse", arguments: { count: 2 } })) };
  const r = await setup();
  try {
    const c = await connect(r, ["read", `programs:run:${digest(program)}`]);
    const ran = (await c.programsRun({ program, arguments: {}, waitMs: 5000 })).operation;
    assert.equal(ran.state, "failed");
    assert.equal(ran.error?.bhmsCode, "OUT_OF_RANGE");
    assert.equal((await counters(r.client)).pulses, 2);
  } finally { await r.close(); }
});

test("unmeasurable quantities fail closed and absolute unit conversions count", async () => {
  const r = await setup({ ...budget, quantity: "/dose/volume", unit: "uL", total: 1000 });
  try {
    const dev = r.server.devices.get("axis-1")!;
    dev.action("dose", { effect: "reversible", idempotency: "relative", maxDurationMs: 1000,
      input: { dose: { type: "object", properties: { volume: { type: "number", "x-bhms-unit": "mL" } }, required: ["volume"] } } }, () => ({}));
    const c = await connect(r);
    await assert.rejects(c.actionsInvoke("axis-1", "pulse", { count: 1 }), (e: unknown) => e instanceof BhmsError && e.bhmsCode === "UNAUTHORIZED");
    await c.actionsInvoke("axis-1", "dose", { dose: { volume: -0.75 } }, { waitMs: 1000 });
    await assert.rejects(c.actionsInvoke("axis-1", "dose", { dose: { volume: 0.5 } }), denied);
    await c.actionsInvoke("axis-1", "dose", { dose: { volume: 0.25 } }, { waitMs: 1000 });
  } finally { await r.close(); }
});

test("rolling budgets expire at the admission window boundary; changing a total preserves prior usage", async () => {
  const rolling = { ...budget, total: 2, windowMs: 1000 };
  const r = await setup(rolling);
  try {
    const c = await connect(r);
    await c.actionsInvoke("axis-1", "pulse", { count: 2 }, { waitMs: 1000 });
    const row = r.server.store.budgetReservations()[0];
    assert.equal(r.server.budgets.state("budgeted", rolling, row.atMs + 999).remaining, 0);
    assert.equal(r.server.budgets.state("budgeted", rolling, row.atMs + 1000).remaining, 2);
    assert.equal(r.server.budgets.state("budgeted", { ...rolling, total: 3 }, row.atMs).remaining, 1);
    assert.equal(r.server.budgets.state("another", rolling, row.atMs).remaining, 2);
  } finally { await r.close(); }
});

test("policy budgets reject duplicate IDs, bad units, and unmeasurable known actions", async () => {
  assert.throws(() => new Principal("a", [], {}, false, [budget, budget]));
  assert.throws(() => new Principal("a", [], {}, false, [{ ...budget, unit: "__proto__" }]));
  assert.throws(() => new Principal("a", [], {}, false, [{ ...budget, total: Infinity }]));
  const r = await rig();
  try {
    assert.throws(() => r.server.setPolicy({ principals: { a: { scopes: ["read"], budgets: [
      { ...budget, action: "axis-1/pulse", quantity: "/missing" },
    ] } } }), /cannot measure/);
  } finally { await r.close(); }
});
