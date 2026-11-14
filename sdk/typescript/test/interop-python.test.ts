// Interop: the TypeScript client drives the Python reference conformance device over stdio.
import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { BhmsError } from "../src/errors.js";
import { Client } from "../src/client.js";
import { descriptionDigest, digest } from "../src/canonical.js";
import { pythonDeviceTarget, pythonEnv, pythonSkip, sleep } from "./helpers.js";
import { key } from "./harness.js";

const skip = pythonSkip();
const available = skip === false;
let client: Client;

before(async () => {
  if (!available) return;
  Object.assign(process.env, { PYTHONPATH: pythonEnv().PYTHONPATH });
  client = await Client.connect(pythonDeviceTarget(), { strict: true });
});
after(async () => { if (client) await client.close(); });

test("discover: identity, capabilities, epoch and principal", { skip }, () => {
  const d = client.discovered!;
  assert.equal(d.serverInfo.name, "conformance-device");
  assert.deepEqual(d.supportedVersions, ["2026-11-13"]);
  assert.ok(d.capabilities.leases && d.capabilities.events && d.capabilities.programs);
  assert.ok(d.epoch.length > 0);
});

test("devices: list, filter, describe and verify the digest", { skip }, async () => {
  const listing = await client.devicesList();
  assert.deepEqual(listing.devices.map((x) => x.deviceId), ["axis-1", "pump-1"]);
  const pumps = await client.devicesList({ filter: { capability: "bhms.liquid.*" } });
  assert.deepEqual(pumps.devices.map((x) => x.deviceId), ["pump-1"]);
  const { description } = await client.devicesDescribe("axis-1");
  assert.equal(description.digest, descriptionDigest(description as unknown as Record<string, unknown>));
  assert.ok("move_to" in description.actions);
  await assert.rejects(client.devicesDescribe("axis-1", { digest: "sha256:" + "0".repeat(64) }), (e: BhmsError) => e.bhmsCode === "STALE" && e.field === "digest");
  await assert.rejects(client.devicesDescribe("nope"), (e: BhmsError) => e.bhmsCode === "UNKNOWN_DEVICE");
});

test("invoke: completes verified, replays on the same key, KEY_CONFLICT on another intent", { skip }, async () => {
  const key = `ts-move-${Date.now()}`;
  const a = await client.actionsInvoke("axis-1", "move_to", { position: 12.5 }, { operationKey: key, waitMs: 2000 });
  assert.equal(a.operation.state, "completed");
  assert.equal(a.operation.effect, "verified");
  assert.equal(a.replayed, false);
  const b = await client.actionsInvoke("axis-1", "move_to", { position: 12.5 }, { operationKey: key });
  assert.equal(b.replayed, true);
  assert.equal(b.operation.operationId, a.operation.operationId);
  await assert.rejects(client.actionsInvoke("axis-1", "move_to", { position: 13 }, { operationKey: key }), (e: BhmsError) => e.bhmsCode === "KEY_CONFLICT" && e.operationId === a.operation.operationId);
  const got = await client.operationsGet(a.operation.operationId);
  assert.ok((got.operation.history ?? []).length >= 2);
  const counters = await client.request<{ counter: number }>("x-conformance/counters");
  assert.ok(counters.counter >= 1);
});

test("errors: out of range, unit mismatch, unknown action, lease required", { skip }, async () => {
  await assert.rejects(client.actionsInvoke("axis-1", "move_to", { position: 500 }), (e: BhmsError) => e.bhmsCode === "OUT_OF_RANGE" && e.field === "arguments.position");
  await assert.rejects(client.actionsInvoke("axis-1", "move_to", { position: { value: 5, unit: "m" } }), (e: BhmsError) => e.bhmsCode === "UNIT_MISMATCH");
  await assert.rejects(client.actionsInvoke("axis-1", "teleport", {}), (e: BhmsError) => e.bhmsCode === "UNKNOWN_ACTION");
  await assert.rejects(client.actionsInvoke("axis-1", "clamp", { force: 10 }), (e: BhmsError) => e.bhmsCode === "LEASE_REQUIRED");
});

test("leases: acquire, use for clamp, renew, release", { skip }, async () => {
  const { lease } = await client.leasesAcquire(["axis-1/clamp"], 5000);
  assert.equal(lease.state, "active");
  const inv = await client.actionsInvoke("axis-1", "clamp", { force: 10 }, { leaseId: lease.leaseId, waitMs: 2000 });
  assert.equal(inv.operation.state, "completed");
  assert.equal(inv.operation.fence, lease.fence);
  assert.equal((await client.leasesRenew(lease.leaseId, 6000)).lease.fence, lease.fence);
  assert.equal((await client.leasesRelease(lease.leaseId)).lease.state, "released");
  await assert.rejects(client.leasesRenew(lease.leaseId, 6000), (e: BhmsError) => e.bhmsCode === "LEASE_EXPIRED");
});

test("properties, cancel of a slow move, stop", { skip }, async () => {
  const obs = (await client.propertiesRead("pump-1", "pressure")).observation;
  assert.equal(obs.quality, "valid");
  assert.equal(obs.unit, "kPa");
  const slow = await client.actionsInvoke("axis-1", "slow_move", { duration_ms: 5000 }, { operationKey: `ts-slow-${Date.now()}` });
  await sleep(50);
  const canceled = await client.operationsCancel(slow.operation.operationId, { reason: "test" });
  assert.ok(["requested", "acknowledged", "confirmed"].includes(canceled.operation.cancel.state));
  const settled = await client.operationsWait(slow.operation.operationId, 2000);
  assert.equal(settled.operation.state, "canceled");
  const stop = await client.stop("test stop", { deviceIds: ["axis-1", "ghost"] });
  assert.equal(stop.stops.find((s) => s.deviceId === "axis-1")?.outcome, "confirmed");
  assert.equal(stop.stops.find((s) => s.deviceId === "ghost")?.outcome, "failed");
});

test("subscriptions: acknowledged first, operation notifications tagged, events replayed", { skip }, async () => {
  const sub = await client.subscribe({ operations: { all: true }, events: {} });
  assert.ok(sub.id > 0);
  const inv = await client.actionsInvoke("axis-1", "pulse", { count: 3 }, { operationKey: `ts-pulse-${Date.now()}`, waitMs: 2000 });
  const seen: string[] = [];
  for await (const n of sub) {
    seen.push(n.method);
    if (n.method === "notifications/operation" && (n.params.operation as { operationId: string; state: string }).operationId === inv.operation.operationId && (n.params.operation as { state: string }).state === "completed") break;
  }
  assert.ok(seen.includes("notifications/operation"));
  sub.cancel();
  const ev = await client.eventsRead({ limit: 5 });
  assert.equal(typeof ev.cursor, "string");
});

test("programs cross-language: the TS client registers and runs a program on the Python device", { skip }, async () => {
  const program = {
    bhmsProgram: "2026-11-13", name: "ts_scan", description: "pulse n times and read the counter",
    input: { type: "object", additionalProperties: false, required: ["n"], properties: { n: { type: "integer", "x-bhms-unit": "1", minimum: 1, maximum: 3 } } },
    maxDurationMs: 60000,
    steps: [
      { kind: "repeat", times: "${n}", as: "i", steps: [{ kind: "invoke", deviceId: "axis-1", action: "pulse", arguments: { count: 1 }, saveAs: "p" }] },
      { kind: "read", deviceId: "axis-1", property: "counter", fresh: true, saveAs: "c" },
    ],
    output: { pulses: "${p.pulses}", counter: "${c.value}" },
  } as unknown as import("../src/generated/types.js").Program;
  const info = (await client.programsRegister(program)).info;
  assert.equal(info.digest, digest(program), "Python and TS agree on the program digest");
  const op = (await client.programsRun({ digest: info.digest, arguments: { n: 2 }, operationKey: key("prog"), waitMs: 5000 })).operation;
  assert.equal(op.state, "completed", JSON.stringify(op.error));
  assert.deepEqual(op.progress, { stepsCompleted: 3, stepsTotal: 4 });
  assert.equal((await client.operationsList({ parentOperationId: op.operationId })).operations.length, 2);
});

test("byte-for-byte parity: the TS and Python conformance devices describe themselves with identical digests", { skip }, async () => {
  const { rig } = await import("./harness.js");
  const r = await rig();
  try {
    for (const id of ["axis-1", "pump-1"]) {
      const py = (await client.devicesDescribe(id)).description;
      const ts = (await r.client.devicesDescribe(id)).description;
      assert.equal(ts.digest, py.digest, `${id}: JCS(description) is identical, so every schema, unit, bound and default matches`);
    }
    assert.deepEqual(r.client.discovered!.capabilities, client.discovered!.capabilities, "capabilities are identical, programs limits included");
  } finally { await r.close(); }
});

test("contract v2 parity: extension declaration, counters shape and the description digest under every description-changing fault", { skip }, async () => {
  const { rig, inject, counters } = await import("./harness.js");
  const r = await rig();
  try {
    const ext = (c: Client): unknown => c.discovered!.capabilities.extensions!["org.bhms/conformance"];
    assert.deepEqual(ext(r.client), ext(client), "version, faults and devices are declared identically");
    assert.deepEqual(Object.keys(await counters(r.client)).sort(), Object.keys(await client.request("x-conformance/counters")).sort());
    const steps: Array<[string, Record<string, unknown>?]> = [
      ["bad_digest"], ["good_digest"], ["hostile_text"], ["none"], ["hostile_schema", { variant: "remote_ref", url: "http://127.0.0.1:9/hostile-schema.json" }], ["none"],
      ["hostile_text"], ["hostile_schema", { variant: "deep" }], ["none"], ["hostile_schema", { variant: "wide" }], ["bad_digest"], ["good_digest"], ["none"], ["change_description"], ["change_description"], ["none"],
    ];
    for (const [fault, extra] of steps) {
      await Promise.all([r.client.request("x-conformance/inject", { fault, ...extra }), client.request("x-conformance/inject", { fault, ...extra })]);
      const [ts, py] = await Promise.all([r.client.devicesDescribe("axis-1"), client.devicesDescribe("axis-1")]);
      assert.equal(ts.description.digest, py.description.digest, `after ${fault}: JCS of the served description is identical`);
      const [tsList, pyList] = await Promise.all([r.client.devicesList(), client.devicesList()]);
      assert.deepEqual(tsList.devices, pyList.devices, `after ${fault}: summaries are identical`);
    }
    await inject(r.client, "none");
  } finally { await r.close(); }
});

test("Task 7b parity: word search, capability *, UNKNOWN_DEVICE hints, LSE-014 refusals and operator resolutions answer as the Python device does", { skip }, async () => {
  const { rig, inject } = await import("./harness.js");
  const r = await rig();
  try {
    for (const filter of [{ text: "AXIS-1 zz-none" }, { text: "syringe" }, { text: "x conformance" }, { text: "bhms.liquid.dispense" }, { text: "zz-none" }, { capability: "*" }, { capability: "*", text: "pump" }]) {
      const [ts, py] = await Promise.all([r.client.devicesList({ filter }), client.devicesList({ filter })]);
      assert.deepEqual(ts.devices.map((d) => d.deviceId), py.devices.map((d) => d.deviceId), `filter ${JSON.stringify(filter)}`);
    }
    const refusal = async (p: Promise<unknown>): Promise<unknown> => p.then(() => assert.fail("expected a refusal"), (e: BhmsError) => ({ code: e.bhmsCode, field: e.field, bound: e.bound, hint: e.hint, mayHaveActed: e.mayHaveActed }));
    for (const id of ["AXIS-1", "Pump-1", "nothing"]) {
      assert.deepEqual(await refusal(r.client.devicesDescribe(id)), await refusal(client.devicesDescribe(id)), `describe ${id}`);
    }
    const [tsLease, pyLease] = await Promise.all([r.client.leasesAcquire(["axis-1/motion"], 30_000), client.leasesAcquire(["axis-1/motion"], 30_000)]);
    try {
      assert.deepEqual(await refusal(r.client.actionsInvoke("axis-1", "pulse", { count: 1 })), await refusal(client.actionsInvoke("axis-1", "pulse", { count: 1 })), "LSE-014: no lease presented");
      const fabricated = { leaseId: "lease-fabricated" };
      const [a, b] = [await refusal(r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, fabricated)), await refusal(client.actionsInvoke("axis-1", "pulse", { count: 1 }, fabricated))] as Array<{ code: string; field: string }>;
      assert.deepEqual([a.code, a.field], [b.code, b.field], "LSE-007: a made-up lease");
    } finally {
      await Promise.all([r.client.leasesRelease(tsLease.lease.leaseId), client.leasesRelease(pyLease.lease.leaseId)]);
    }
    const lost = async (c: Client): Promise<string> => {
      await c.request("x-conformance/inject", { fault: "amnesia" });
      await c.request("x-conformance/inject", { fault: "crash_next" });
      return (await c.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 3000 })).operation.operationId;
    };
    const resolve = async (c: Client, id: string, resolution: Record<string, unknown>): Promise<unknown> => {
      try {
        const op = (await c.operationsResolve(id, resolution as never)).operation;
        const last = op.history!.at(-1)!;
        return { state: op.state, effect: op.effect, evidence: op.evidence, result: op.result, error: op.error && { code: op.error.bhmsCode, mayHaveActed: op.error.mayHaveActed, message: op.error.message }, last: { kind: last.kind, state: last.state, operatorBasis: last.operator?.basis } };
      } catch (e) {
        return { refused: (e as BhmsError).bhmsCode, field: (e as BhmsError).field, bound: (e as BhmsError).bound };
      }
    };
    const [tsOp, pyOp] = [await lost(r.client), await lost(client)];
    for (const resolution of [
      { state: "completed", basis: "b" }, { state: "completed", basis: "b", result: { pulses: -1 } }, { state: "completed", basis: "b", result: { pulses: "many" } },
      { state: "completed", basis: "counted by hand", result: { pulses: 7 } },
    ]) {
      assert.deepEqual(await resolve(r.client, tsOp, resolution), await resolve(client, pyOp, resolution), `resolution ${JSON.stringify(resolution)}`);
    }
    // refused by the OperatorResolution consistency rules: both name the member at fault (Ruling R45)
    for (const resolution of [{ state: "failed", basis: "b", mayHaveActed: false, effect: "unverified" }, { state: "failed", basis: "b", mayHaveActed: false }, { state: "failed", basis: "b", effect: "none" },
      { state: "failed", basis: "b", result: { pulses: 1 } }, { state: "completed", basis: "b", mayHaveActed: true, result: { pulses: 1 } }, { state: "completed", basis: "b", effect: "verified" }]) {
      assert.deepEqual(await resolve(r.client, tsOp, resolution), await resolve(client, pyOp, resolution), `resolution ${JSON.stringify(resolution)}`);
    }
    await Promise.all([inject(r.client, "none"), client.request("x-conformance/inject", { fault: "none" })]);
  } finally { await r.close(); }
});

test("schemaBoundsProblem answers exactly like bhms.protocol.schema.schema_bounds_problem on a corpus of boundary cases", { skip }, async () => {
  const { spawnSync } = await import("node:child_process");
  const { schemaBoundsProblem } = await import("../src/schema.js");
  const nest = (levels: number, leaf: unknown = { type: "string" }): unknown => { let n = leaf; for (let i = 1; i < levels; i++) n = { type: "object", properties: { x: n } }; return n; };
  const wide = (n: number): unknown => ({ type: "object", properties: Object.fromEntries(Array.from({ length: n - 1 }, (_, i) => [`p${i}`, { type: "string" }])) });
  const long = "http://example.com/" + "a".repeat(120);
  const cases: unknown[] = [
    nest(1), nest(31), nest(32), nest(33), nest(40), nest(32, { $ref: "#/$defs/a" }), nest(31, { $ref: "http://x/y" }), nest(64, { $ref: "http://127.0.0.1:9/h.json" }),
    wide(9_999), wide(10_000), wide(10_001), { $ref: "#" }, { $ref: "other.json#/a" }, { $ref: long }, { $ref: "it's.json" }, { $ref: "a\\b\"c" },
    { allOf: [true, 1, "x", null, {}, { $ref: "https://e/x" }] }, { items: [{ $ref: "https://e/x" }] }, { items: { items: { items: { not: { $ref: "ftp://q" } } } } },
    { properties: { a: { patternProperties: { b: { $defs: { c: { dependentSchemas: { d: { oneOf: [{ prefixItems: [{ $ref: "x:y" }] }] } } } } } } } } },
    { description: { $ref: "http://not-a-schema" } }, "just a string", null, [], { properties: [] }, { $ref: 5 },
    { $dynamicRef: "http://x/y" }, { $dynamicRef: "#anchor" }, { contentSchema: { $ref: "http://x" } }, { dependentSchemas: { a: { $ref: "http://x" } } },
    { $ref: "tab\there\u0001\u00a0\u200b\u{1F600}\u{E0001}" }, { $ref: "né\u2028" }, { allOf: [true, false, 1, ...Array.from({ length: 9_997 }, () => ({}))] },
    { allOf: [true, ...Array.from({ length: 9_999 }, () => false)] }, { allOf: [true, ...Array.from({ length: 10_000 }, () => false)] },
    { properties: { ["n".repeat(300)]: { $ref: "http://x" } } }, { properties: { ["n".repeat(100)]: nest(33) } },
  ];
  const script = "import json,sys\nfrom bhms.protocol.schema import schema_bounds_problem\nprint(json.dumps([schema_bounds_problem(c) for c in json.load(sys.stdin)]))\n";
  const py = spawnSync("python3", ["-c", script], { env: pythonEnv(), input: JSON.stringify(cases), encoding: "utf8" });
  assert.equal(py.status, 0, py.stderr);
  const expected = JSON.parse(py.stdout) as Array<string | null>;
  assert.deepEqual(cases.map((c) => schemaBoundsProblem(c) ?? null), expected);
});
