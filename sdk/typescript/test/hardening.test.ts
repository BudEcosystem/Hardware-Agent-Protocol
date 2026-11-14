// Task 7b hardening, followed by the TypeScript SDK (spec/bhms/CHANGELOG.md "Unreleased", "TS SDK to follow"): every test
// pins one wire-visible rule the Python reference enforces since that round.
import assert from "node:assert/strict";
import { test } from "node:test";
import { BhmsError } from "../src/errors.js";
import { Client } from "../src/client.js";
import { memoryPair } from "../src/transport/memory.js";
import { DeviceServer, type DeviceServerOptions } from "../src/server/server.js";
import { DescriptionError, type Device } from "../src/server/device.js";
import { range, int } from "../src/server/schemas.js";
import type { Peer } from "../src/jsonrpc/session.js";
import type { Operation } from "../src/generated/types.js";
import { counters, inject, key, rig } from "./harness.js";
import { sleep } from "./helpers.js";

const code = (c: string, extra?: (e: BhmsError) => boolean) => (e: unknown): boolean => {
  if (!(e instanceof BhmsError)) return false;
  if (e.bhmsCode !== c) assert.fail(`expected ${c}, got ${e.bhmsCode}: ${e.message}`);
  return extra ? extra(e) : true;
};

/** A server with devices declared by `declare`, started, plus a connect function for principals. */
async function custom(declare: (srv: DeviceServer) => void, options: DeviceServerOptions = {}): Promise<{ srv: DeviceServer; client: Client; connect(peer?: Partial<Peer>): Promise<Client>; close(): Promise<void> }> {
  const srv = new DeviceServer("hardening", { store: "memory", log: () => undefined, cancelGraceMs: 100, ...options });
  declare(srv);
  await srv.start();
  const clients: Client[] = [];
  const connect = async (peer?: Partial<Peer>): Promise<Client> => {
    const [c, s] = memoryPair({ serverPeer: peer });
    srv.serve(s);
    const client = await Client.fromTransport(c, { strict: true });
    clients.push(client);
    return client;
  };
  const keepAlive = setInterval(() => undefined, 1000);
  const client = await connect();
  return {
    srv, client, connect,
    async close() {
      clearInterval(keepAlive);
      for (const c of clients) await c.close().catch(() => undefined);
      await srv.close(500);
    },
  };
}

const until = async (what: string, probe: () => Promise<boolean> | boolean, ms = 3000): Promise<void> => {
  const end = Date.now() + ms;
  while (!(await probe())) {
    if (Date.now() > end) assert.fail(`timed out waiting for ${what}`);
    await sleep(10);
  }
};

const historyKinds = (op: Operation): Array<[string, string | undefined]> => (op.history ?? []).map((h) => [h.kind, h.state]);

// ------------------------------------------------------------------------------------------------ BHMS-LSE-014

test("LSE-014: a held lease refuses every request that does not present it, the holder included, and never names the holder", async () => {
  const r = await rig();
  try {
    const other = await r.connect({ principal: "other", scopes: ["read", "invoke:*/*", "lease"] });
    const motion = (await r.client.leasesAcquire(["axis-1/motion"], 30_000)).lease;
    const base = (await counters(r.client)).counter;
    for (const [who, c] of [["the holder", r.client], ["another principal", other]] as const) {
      await assert.rejects(c.actionsInvoke("axis-1", "pulse", { count: 1 }), code("LEASE_CONFLICT", (e) => {
        assert.equal(e.field, "leaseId", who);
        assert.deepEqual(e.bound, ["axis-1/motion"], who);
        assert.equal(e.mayHaveActed, false);
        assert.ok(!e.message.includes(motion.leaseId) && !e.hint.includes(motion.leaseId), "the refusal must not disclose the lease");
        assert.ok(!e.message.includes("memory:client") && !e.hint.includes("memory:client"), "the refusal must not name the holder");
        assert.match(e.hint, /BHMS-LSE-014/);
        return true;
      }));
    }
    await assert.rejects(other.actionsInvoke("axis-1", "pulse", { count: 1 }, { leaseId: motion.leaseId }), code("LEASE_CONFLICT"), "another principal's lease is not its own");
    assert.equal((await counters(r.client)).counter, base, "a refused request reached the device");
    const done = (await r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { leaseId: motion.leaseId, waitMs: 2000 })).operation;
    assert.equal(done.state, "completed");
    assert.equal(done.leaseId, motion.leaseId);
    assert.equal(done.fence, motion.fence);
    await r.client.leasesRelease(motion.leaseId);
    assert.equal((await r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 2000 })).operation.state, "completed", "after the lease ended no lease is needed");
  } finally { await r.close(); }
});

test("LSE-014 with LSE-007/010: a lease supplied with an action that does not require one is always validated", async () => {
  const r = await rig();
  try {
    await assert.rejects(r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { leaseId: "lease-fabricated" }), code("LEASE_EXPIRED", (e) => e.field === "leaseId"), "a made-up lease while nothing is leased");
    const clamp = (await r.client.leasesAcquire(["axis-1/clamp"], 30_000)).lease;
    await assert.rejects(r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { leaseId: clamp.leaseId }), code("LEASE_CONFLICT", (e) => e.field === "leaseId"), "a lease on another resource");
    await r.client.leasesRelease(clamp.leaseId);
    await assert.rejects(r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { leaseId: clamp.leaseId }), code("LEASE_EXPIRED"), "a released lease");
  } finally { await r.close(); }
});

test("LSE-014 before dispatch: an operation queued while the resource was free is rejected when a lease holds it at dispatch", async () => {
  const r = await rig();
  try {
    const slow = (await r.client.actionsInvoke("axis-1", "slow_move", { duration_ms: 150 }, { operationKey: key("slow") })).operation;
    const queued = (await r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: key("queued") })).operation;
    assert.equal(queued.state, "accepted");
    const lease = (await r.client.leasesAcquire(["axis-1/motion"], 30_000)).lease;
    const after = (await r.client.operationsWait(queued.operationId, 3000)).operation;
    assert.equal(after.state, "rejected");
    assert.equal(after.effect, "none");
    assert.equal(after.error?.bhmsCode, "LEASE_CONFLICT");
    assert.equal(after.error?.mayHaveActed, false);
    assert.equal((await r.client.operationsWait(slow.operationId, 3000)).operation.state, "completed", "running work continues");
    await r.client.leasesRelease(lease.leaseId);
  } finally { await r.close(); }
});

test("LSE-014: stop needs no lease and is not blocked by one", async () => {
  const r = await rig();
  try {
    const stopper = await r.connect({ principal: "stopper", scopes: ["stop"] });
    const lease = (await r.client.leasesAcquire(["axis-1/motion", "axis-1/clamp"], 30_000)).lease;
    const stop = await stopper.stop("lease test", { deviceIds: ["axis-1"], waitMs: 1000 });
    assert.equal(stop.stops[0].outcome, "confirmed");
    assert.deepEqual(stop.stops[0].revokedLeases, [lease.leaseId]);
  } finally { await r.close(); }
});

test("LSE-014 in programs: a step on a resource the program's lease holds presents that lease; without one it is refused", async () => {
  const r = await rig();
  try {
    const program = {
      bhmsProgram: "2026-11-13", name: "pulse_twice", description: "two pulses",
      input: { type: "object", additionalProperties: false, properties: {} }, maxDurationMs: 10_000,
      steps: [{ kind: "invoke", deviceId: "axis-1", action: "pulse", arguments: { count: 1 } }, { kind: "invoke", deviceId: "axis-1", action: "pulse", arguments: { count: 1 } }],
    } as never;
    const lease = (await r.client.leasesAcquire(["axis-1/motion"], 30_000)).lease;
    const base = (await counters(r.client)).counter;
    const leased = (await r.client.programsRun({ program, arguments: {}, leaseId: lease.leaseId, waitMs: 5000 })).operation;
    assert.equal(leased.state, "completed", JSON.stringify(leased.error));
    const children = (await r.client.operationsList({ parentOperationId: leased.operationId })).operations;
    assert.deepEqual(children.map((c) => c.leaseId), [lease.leaseId, lease.leaseId], "each step presents the program's lease");
    const bare = (await r.client.programsRun({ program, arguments: {}, waitMs: 5000 })).operation;
    assert.equal(bare.state, "failed");
    assert.equal(bare.error?.bhmsCode, "LEASE_CONFLICT");
    assert.equal((await counters(r.client)).counter, base + 2, "only the leased program's steps reached the device");
  } finally { await r.close(); }
});

test("PRG-006 with LSE-014: a program whose lease covers only part of a step's resources is refused at programs/run, naming the step", async () => {
  const t = await custom((srv) => {
    const d = srv.device("rig-1", { resources: ["rig-1/a", "rig-1/b"] });
    d.action("grip", { effect: "reversible", idempotency: "absolute", maxDurationMs: 1000, requiresLease: true, resources: ["rig-1/a"] }, () => undefined);
    d.action("both", { effect: "reversible", idempotency: "absolute", maxDurationMs: 1000, resources: ["rig-1/a", "rig-1/b"] }, () => undefined);
  });
  try {
    const program = {
      bhmsProgram: "2026-11-13", name: "grip_then_both", description: "grip, then act on both resources",
      input: { type: "object", additionalProperties: false, properties: {} }, maxDurationMs: 10_000,
      steps: [{ kind: "invoke", deviceId: "rig-1", action: "grip", arguments: {} }, { kind: "invoke", deviceId: "rig-1", action: "both", arguments: {} }],
    } as never;
    const partial = (await t.client.leasesAcquire(["rig-1/a"], 30_000)).lease;
    await assert.rejects(t.client.programsRun({ program, arguments: {}, leaseId: partial.leaseId }), code("LEASE_CONFLICT", (e) => {
      assert.equal(e.field, "leaseId");
      assert.deepEqual(e.bound, ["rig-1/b"]);
      assert.match(e.message, /program\.steps\[1\] \(both\)/);
      return true;
    }));
    assert.equal((await t.client.operationsList()).operations.length, 0, "nothing was recorded");
    await t.client.leasesRelease(partial.leaseId);
    const whole = (await t.client.leasesAcquire(["rig-1/a", "rig-1/b"], 30_000)).lease;
    const ran = (await t.client.programsRun({ program, arguments: {}, leaseId: whole.leaseId, waitMs: 5000 })).operation;
    assert.equal(ran.state, "completed", JSON.stringify(ran.error));
  } finally { await t.close(); }
});

// ------------------------------------------------------------------------------------------------ BHMS-DEV-033

test("DEV-033: a hazardous action without requiresLease is refused when it is declared", () => {
  const srv = new DeviceServer("dev033", { store: "memory" });
  const d = srv.device("spinner-1", { resources: ["spinner-1/rotor"] });
  assert.throws(() => d.action("spin", { effect: "hazardous", idempotency: "relative", maxDurationMs: 1000 }, () => undefined),
    (e: unknown) => e instanceof DescriptionError && /hazardous/.test(e.message) && /requiresLease/.test(e.message) && /BHMS-DEV-033/.test(e.message));
  d.action("spin", { effect: "hazardous", idempotency: "relative", maxDurationMs: 1000, requiresLease: true }, () => undefined);
  assert.equal(d.description().actions.spin.requiresLease, true);
});

// ------------------------------------------------------------------------------------------------ BHMS-OPS-008

function balance(srv: DeviceServer, returned: () => unknown): Device {
  const d = srv.device("pipette-1", { resources: ["pipette-1/plunger"] });
  d.property("volume", { unit: "uL", evidence: "measured" }, () => 200.138);
  d.action("aspirate", {
    effect: "reversible", idempotency: "absolute", maxDurationMs: 1000, completionEvidence: "measured", verifiedBy: ["volume"],
    input: {}, output: { volume: range(0, 200, "uL") },
  }, async (ctx) => {
    await ctx.verify("volume", () => true);
    return returned();
  });
  return d;
}

test("OPS-008: a result outside its declared output range ends failed with OUT_OF_RANGE naming result.<member>, the value kept as evidence", async () => {
  const t = await custom((srv) => { balance(srv, () => ({ volume: 200.138 })); });
  try {
    const op = (await t.client.actionsInvoke("pipette-1", "aspirate", {}, { waitMs: 2000 })).operation;
    assert.equal(op.state, "failed");
    assert.equal(op.error?.bhmsCode, "OUT_OF_RANGE");
    assert.equal(op.error?.field, "result.volume");
    assert.deepEqual(op.error?.bound, { maximum: 200 });
    assert.equal(op.error?.mayHaveActed, true);
    assert.equal(op.error?.retry, "after-reconcile");
    assert.match(op.error!.message, /200\.138/);
    assert.equal(op.effect, "verified", "the effect is what the completion evidence supports");
    assert.equal(op.evidence?.kind, "measured");
    assert.equal(op.result, undefined);
    const full = (await t.client.operationsGet(op.operationId)).operation;
    assert.ok((full.history ?? []).some((h) => h.kind === "evidence" && (h.detail ?? "").includes("200.138")), "the returned value is in an evidence entry");
  } finally { await t.close(); }
});

test("OPS-008: a result of the wrong shape stays INTERNAL", async () => {
  const t = await custom((srv) => { balance(srv, () => ({ volume: "lots" })); });
  try {
    const op = (await t.client.actionsInvoke("pipette-1", "aspirate", {}, { waitMs: 2000 })).operation;
    assert.equal(op.state, "failed");
    assert.equal(op.error?.bhmsCode, "INTERNAL");
    assert.match(op.error!.message, /does not match the declared output schema/);
  } finally { await t.close(); }
});

// ------------------------------------------------------------------------------------------------ BHMS-DEV-013 / DEV-014

test("DEV-013: the text filter is an any-word search over id, name, summary, tags and capabilities; capability * lists everything", async () => {
  const r = await rig();
  try {
    const ids = async (filter: Record<string, unknown>): Promise<string[]> => (await r.client.devicesList({ filter })).devices.map((d) => d.deviceId);
    assert.deepEqual(await ids({ text: "zz-nothing-here" }), []);
    assert.deepEqual(await ids({ text: "AXIS-1 zz-nothing" }), ["axis-1"], "the id, ignoring case, with any word");
    assert.deepEqual(await ids({ text: "zz-nothing SYRINGE" }), ["pump-1"], "a word of the summary");
    assert.deepEqual(await ids({ text: "bhms.liquid.dispense" }), ["pump-1"], "a capability id");
    assert.deepEqual(await ids({ text: "conformance" }), ["axis-1", "pump-1"], "a tag");
    assert.deepEqual(await ids({ text: "x syringe" }), ["pump-1"], "a one-character word is ignored beside a longer one");
    assert.deepEqual(await ids({ capability: "*" }), ["axis-1", "pump-1"]);
    assert.deepEqual(await ids({ capability: "*", text: "pump" }), ["pump-1"], "filters combine with AND");
  } finally { await r.close(); }
});

test("DEV-014: UNKNOWN_DEVICE names the visible ids that differ only in case or by a namespace, never an invisible one", async () => {
  const t = await custom((srv) => {
    srv.device("bench/axis-1", { resources: ["bench/axis-1/m"] });
    srv.device("Pump-2", {});
  });
  try {
    await assert.rejects(t.client.devicesDescribe("pump-2"), code("UNKNOWN_DEVICE", (e) => {
      assert.deepEqual(e.bound, ["Pump-2"]);
      assert.match(e.hint, /did you mean Pump-2\?/);
      return e.field === "deviceId";
    }));
    await assert.rejects(t.client.devicesDescribe("AXIS-1"), code("UNKNOWN_DEVICE", (e) => JSON.stringify(e.bound) === '["bench/axis-1"]'));
    await assert.rejects(t.client.actionsInvoke("pump-2", "x", {}), code("UNKNOWN_DEVICE", (e) => JSON.stringify(e.bound) === '["Pump-2"]'), "admission says the same");
    await assert.rejects(t.client.devicesDescribe("nothing"), code("UNKNOWN_DEVICE", (e) => e.bound === undefined && e.hint === "devices/list shows the devices you can use"));
    const blind = await t.connect({ principal: "blind", scopes: ["stop"] });
    await assert.rejects(blind.devicesDescribe("pump-2"), code("UNKNOWN_DEVICE", (e) => e.bound === undefined && !e.hint.includes("Pump-2")), "a caller that may read nothing learns nothing");
  } finally { await t.close(); }
});

// ------------------------------------------------------------------------------------------------ BHMS-OPS-082 and liveness

async function lostPulse(c: Client): Promise<Operation> {
  await inject(c, "crash_next");
  const op = (await c.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 2000 })).operation;
  assert.equal(op.state, "unknown");
  return op;
}

test("OPS-082: when a device returns to online its unknown operations are reconciled from device evidence, once, and audited", async () => {
  const r = await rig();
  try {
    const op = await lostPulse(r.client);
    await inject(r.client, "offline");
    await inject(r.client, "online");
    let final = op;
    await until("reconciliation on return", async () => (final = (await r.client.operationsGet(op.operationId)).operation).state !== "unknown");
    assert.equal(final.state, "failed", "the command log says started, not finished");
    const kinds = historyKinds(final);
    assert.deepEqual(kinds.slice(-1)[0], ["reconciliation", "failed"]);
    assert.ok(kinds.some(([k, s]) => k === "state" && s === "unknown"));
    const events = (await r.client.eventsRead({ types: ["operation.resolved"] })).events.filter((e) => e.operationId === op.operationId);
    assert.deepEqual(events.map((e) => e.data), [{ state: "failed", source: "device" }]);
    assert.equal((await r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 2000 })).operation.state, "completed", "the resource admits new work");
  } finally { await r.close(); }
});

test("OPS-082: a device that cannot say what happened (amnesia) leaves the operation unknown; nothing is assumed", async () => {
  const r = await rig();
  try {
    await inject(r.client, "amnesia");
    const op = await lostPulse(r.client);
    await inject(r.client, "offline");
    await inject(r.client, "online");
    await sleep(200);
    assert.equal((await r.client.operationsGet(op.operationId)).operation.state, "unknown");
  } finally { await r.close(); }
});

test("OPS-082: the reconcile hook runs once per return and a hook that hangs is bounded by reconcileTimeoutS", async () => {
  let calls = 0;
  let hang = true;
  const t = await custom((srv) => {
    const d = srv.device("relay-1", { resources: ["relay-1/coil"] });
    d.reportAlive();
    d.action("toggle", { effect: "reversible", idempotency: "toggle", maxDurationMs: 1000 }, () => { throw new Error("link dropped"); });
    d.reconcile(async () => {
      calls += 1;
      if (hang) await new Promise<void>(() => undefined);
      return { state: "completed", evidence: "relay readback" };
    });
  }, { reconcileTimeoutS: 0.05 });
  try {
    const op = (await t.client.actionsInvoke("relay-1", "toggle", {}, { waitMs: 2000 })).operation;
    assert.equal(op.state, "unknown");
    const dev = t.srv.devices.get("relay-1")!;
    calls = 0;
    dev.setStatus("offline");
    dev.setStatus(undefined);
    await sleep(200);
    assert.equal(calls, 1, "one return, one call");
    assert.equal((await t.client.operationsGet(op.operationId)).operation.state, "unknown", "no answer in time leaves it unknown");
    hang = false;
    dev.setStatus("offline");
    dev.setStatus(undefined);
    await until("the second return to reconcile", async () => (await t.client.operationsGet(op.operationId)).operation.state === "completed");
    assert.equal(calls, 2);
  } finally { await t.close(); }
});

test("B9: a failed liveness probe makes the device offline (new work DEVICE_UNAVAILABLE) until evidence of life brings it back", async () => {
  let answer: "yes" | "no" | "throw" | "hang" = "no";
  const t = await custom((srv) => {
    const d = srv.device("bridge-1", { resources: ["bridge-1/out"] });
    d.liveness(async () => {
      if (answer === "throw") throw new Error("no route to host");
      if (answer === "hang") await new Promise<void>(() => undefined);
      return answer === "yes";
    }, { intervalS: 0.03, timeoutS: 0.03 });
    d.action("set", { effect: "reversible", idempotency: "absolute", maxDurationMs: 1000 }, () => undefined);
  });
  try {
    const status = async (): Promise<string> => (await t.client.devicesList()).devices[0].status;
    assert.equal(await status(), "offline", "the start-up probe failed");
    await assert.rejects(t.client.actionsInvoke("bridge-1", "set", {}), code("DEVICE_UNAVAILABLE", (e) => e.mayHaveActed === false));
    answer = "yes";
    await until("online after a successful periodic probe", async () => (await status()) === "online");
    for (const failure of ["throw", "hang"] as const) {
      answer = failure;
      await until(`offline after a probe that ${failure}s`, async () => (await status()) === "offline");
      answer = "yes";
      await until("online again", async () => (await status()) === "online");
    }
    const types = (await t.client.eventsRead({ deviceId: "bridge-1", types: ["device.online", "device.offline"] })).events.map((e) => e.type);
    assert.deepEqual(types.slice(0, 2), ["device.offline", "device.online"]);
  } finally { await t.close(); }
});

test("B9: periodic liveness probing is off unless an interval is given", async () => {
  let probes = 0;
  const t = await custom((srv) => { srv.device("quiet-1", {}).liveness(() => { probes += 1; return true; }); });
  try {
    await sleep(100);
    assert.equal(probes, 1, "only the start-up probe");
  } finally { await t.close(); }
});

// ------------------------------------------------------------------------------------------------ operations/resolve (BHMS-OPS-100..102)

const RESOLVER = { principal: "resolver", scopes: ["read", "operations:read", "operations:resolve"] };
const AGENT = { principal: "agent", scopes: ["read", "invoke:*/*", "lease", "stop"] };

test("OPS-100: operations/resolve is advertised and needs operations:resolve (or admin); the owner and a reader are refused", async () => {
  const r = await rig();
  try {
    assert.equal(r.client.discovered!.capabilities.operations.resolve, true);
    const agent = await r.connect(AGENT);
    const reader = await r.connect({ principal: "reader", scopes: ["read", "operations:read"] });
    await inject(r.client, "amnesia");
    const op = await lostPulse(agent);
    for (const c of [agent, reader]) {
      await assert.rejects(c.operationsResolve(op.operationId, { state: "failed", basis: "inspected" }), code("UNAUTHORIZED", (e) => e.hint.includes("operations:resolve")));
    }
    const resolver = await r.connect(RESOLVER);
    const asked = (await resolver.operationsResolve(op.operationId)).operation;
    assert.equal(asked.state, "unknown", "without a resolution only the device is asked");
    assert.ok(!(asked.history ?? []).some((h) => h.kind === "reconciliation"));
    const program = (await r.client.programsRun({ program: { bhmsProgram: "2026-11-13", name: "p", description: "p", input: { type: "object", additionalProperties: false, properties: {} }, maxDurationMs: 1000, steps: [{ kind: "read", deviceId: "axis-1", property: "counter", saveAs: "c" }] } as never, arguments: {}, waitMs: 2000 })).operation;
    await assert.rejects(r.client.operationsResolve(program.operationId, { state: "failed", basis: "x" }), code("INVALID_ARGUMENT", (e) => e.field === "operationId"));
  } finally { await r.close(); }
});

test("OPS-102: an operator's resolution is a report after the unchanged history, marked with the operator, audited, and final", async () => {
  const r = await rig();
  try {
    const agent = await r.connect(AGENT);
    const resolver = await r.connect(RESOLVER);
    await inject(r.client, "amnesia");
    const op = await lostPulse(agent);
    const before = (await r.client.operationsGet(op.operationId)).operation.history!;
    const basis = "axis inspected at rest; treating the pulse as not completed";
    await assert.rejects(resolver.operationsResolve(op.operationId, { state: "failed", basis, mayHaveActed: false, effect: "unverified" }), code("INVALID_ARGUMENT", (e) => e.field === "resolution.effect"));
    await assert.rejects(resolver.operationsResolve(op.operationId, { state: "completed", basis, effect: "verified", result: { pulses: 1 } } as never), code("INVALID_ARGUMENT"), "verified is never an operator's to state");
    const done = (await resolver.operationsResolve(op.operationId, { state: "failed", basis })).operation;
    assert.equal(done.state, "failed");
    assert.equal(done.error?.bhmsCode, "DEVICE_FAULT");
    assert.equal(done.error?.mayHaveActed, true);
    assert.equal(done.error?.message, basis);
    assert.equal(done.effect, "unknown");
    assert.deepEqual(done.evidence, { kind: "reported" });
    assert.deepEqual(done.history!.slice(0, before.length), before, "earlier entries are untouched");
    const last = done.history!.at(-1)!;
    assert.equal(last.kind, "reconciliation");
    assert.deepEqual(last.operator, { principal: "resolver", basis });
    const events = (await r.client.eventsRead({ types: ["operation.resolved"] })).events.filter((e) => e.operationId === op.operationId);
    assert.deepEqual(events.map((e) => [e.severity, e.data]), [["warning", { state: "failed", source: "operator", principal: "resolver" }]]);
    const again = (await resolver.operationsResolve(op.operationId, { state: "failed", basis: "a second opinion" })).operation;
    assert.deepEqual(again.history, done.history, "a settled operation is returned unchanged");
    assert.equal((await agent.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 2000 })).operation.state, "completed", "the resource admits new work");
  } finally { await r.close(); }
});

test("OPS-102: completed resolutions carry a checked result and at most an unverified effect; proof of no effect goes with effect none", async () => {
  const r = await rig();
  try {
    const resolver = await r.connect(RESOLVER);
    await inject(r.client, "amnesia");
    const a = await lostPulse(r.client);
    await assert.rejects(resolver.operationsResolve(a.operationId, { state: "completed", basis: "b" }), code("INVALID_ARGUMENT", (e) => e.field === "resolution.result"));
    await assert.rejects(resolver.operationsResolve(a.operationId, { state: "completed", basis: "b", result: { pulses: -1 } }), code("OUT_OF_RANGE", (e) => e.field === "resolution.result.pulses" && JSON.stringify(e.bound) === '{"minimum":0}'));
    await assert.rejects(resolver.operationsResolve(a.operationId, { state: "completed", basis: "b", result: { pulses: "many" } }), code("INVALID_ARGUMENT", (e) => e.field === "resolution.result"));
    const done = (await resolver.operationsResolve(a.operationId, { state: "completed", basis: "counter read by hand", result: { pulses: 7 } })).operation;
    assert.equal(done.state, "completed");
    assert.deepEqual(done.result, { pulses: 7 });
    assert.equal(done.effect, "unverified");
    assert.deepEqual(done.evidence, { kind: "reported" });
    const b = await lostPulse(r.client);
    const none = (await resolver.operationsResolve(b.operationId, { state: "failed", basis: "the controller log shows the command was dropped", mayHaveActed: false, effect: "none" })).operation;
    assert.equal(none.state, "failed");
    assert.equal(none.effect, "none");
    assert.equal(none.error?.mayHaveActed, false);
    await inject(r.client, "crash_next");
    const verified = (await r.client.actionsInvoke("axis-1", "move_to", { position: 3 }, { require: { effect: "verified" }, waitMs: 2000 })).operation;
    assert.equal(verified.state, "unknown");
    await assert.rejects(resolver.operationsResolve(verified.operationId, { state: "completed", basis: "looks right", result: { position: 3 } }), code("INVALID_ARGUMENT", (e) => e.field === "resolution.state"), "a required verified effect is never an operator's to establish");
  } finally { await r.close(); }
});

test("OPS-101: the device is asked first and its evidence wins over the operator's statement", async () => {
  const r = await rig();
  try {
    const resolver = await r.connect(RESOLVER);
    await inject(r.client, "amnesia");
    const op = await lostPulse(r.client);
    await inject(r.client, "none");
    const won = (await resolver.operationsResolve(op.operationId, { state: "completed", basis: "the operator believes it finished", result: { pulses: 1 } })).operation;
    assert.equal(won.state, "failed", "started, not finished: the device's command log");
    const entry = won.history!.filter((h) => h.kind === "reconciliation").at(-1)!;
    assert.equal(entry.operator, undefined);
    const sources = (await r.client.eventsRead({ types: ["operation.resolved"] })).events.filter((e) => e.operationId === op.operationId).map((e) => (e.data as { source: string }).source);
    assert.deepEqual(sources, ["device"]);
  } finally { await r.close(); }
});

test("the conformance device declares the amnesia fault after hostile_schema, as the Python device does", async () => {
  const r = await rig();
  try {
    const faults = (r.client.discovered!.capabilities.extensions!["org.bhms/conformance"] as { faults: string[] }).faults;
    assert.deepEqual(faults.slice(-2), ["hostile_schema", "amnesia"]);
    const c = await counters(r.client);
    assert.equal(typeof c.counter, "number");
  } finally { await r.close(); }
});

test("an int output bound is kept when the result is in range", async () => {
  const t = await custom((srv) => {
    const d = srv.device("count-1", { resources: ["count-1/r"] });
    d.action("count", { effect: "reversible", idempotency: "relative", maxDurationMs: 1000, output: { n: int("1", { minimum: 0, maximum: 10 }) } }, () => ({ n: 10 }));
  });
  try {
    const op = (await t.client.actionsInvoke("count-1", "count", {}, { waitMs: 2000 })).operation;
    assert.equal(op.state, "completed");
    assert.deepEqual(op.result, { n: 10 });
  } finally { await t.close(); }
});
