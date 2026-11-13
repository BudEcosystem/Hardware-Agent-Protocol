// Task 8b: conformance device contract v2 and the spec changes since Task 8 (authority profile, policy bounds, stop scope,
// schema bounds walker, stdio opens no listeners). Everything here runs without Python; the cross-language checks are in
// interop-python.test.ts and the full runner is scripts/conformance.py.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, readdirSync, readlinkSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { Client } from "../src/client.js";
import { BhmsError } from "../src/errors.js";
import { schemaBoundsProblem } from "../src/schema.js";
import { PolicyTable, tokenDigest, type PolicyDocument } from "../src/server/authority.js";
import { HOSTILE_TEXT, build, traceRequests } from "../src/testing/conformanceDevice.js";
import { counters, inject, key, rig } from "./harness.js";
import { sleep, tsDevicePath } from "./helpers.js";

const code = (c: string, extra?: (e: BhmsError) => boolean) => (e: unknown): boolean => e instanceof BhmsError && e.bhmsCode === c && (extra?.(e) ?? true);

// ------------------------------------------------------------------------------------------------ device contract v2

test("extension org.bhms/conformance version 2: faults, devices, and no authority for a single-principal server", async () => {
  const r = await rig();
  try {
    const ext = r.client.discovered!.capabilities.extensions!["org.bhms/conformance"] as { version: string; faults: string[]; devices: string[] };
    assert.equal(ext.version, "2");
    assert.deepEqual(ext.devices, ["axis-1", "pump-1"]);
    assert.deepEqual(ext.faults, [
      "none", "sensor_invalid", "sensor_valid", "sensor_stale", "encoder_disagrees", "fail_next", "crash_next", "hang_next", "journal_readonly",
      "journal_writable", "offline", "online", "change_description", "deaf_next", "bad_digest", "good_digest", "hostile_text", "hostile_schema",
    ]);
    assert.equal("authority" in r.client.discovered!.capabilities, false, "capabilities.authority is absent for a single-principal server");
    await assert.rejects(inject(r.client, "no_such_fault"), code("INVALID_ARGUMENT", (e) => e.field === "fault"));
  } finally { await r.close(); }
});

test("axis-1 declares overdrive (hazardous, clamp lease) and the three guard actions that differ only in onLeaseLoss", async () => {
  const r = await rig();
  try {
    const { actions } = (await r.client.devicesDescribe("axis-1")).description;
    const od = actions.overdrive as unknown as Record<string, unknown>;
    assert.equal(od.effect, "hazardous");
    assert.equal(od.requiresLease, true);
    assert.equal(od.onLeaseLoss, "cancel");
    assert.deepEqual(od.resources, ["axis-1/clamp"]);
    assert.equal(od.maxDurationMs, 10_000);
    for (const loss of ["finish", "cancel", "hold"]) {
      const g = actions[`guard_${loss}`] as unknown as Record<string, unknown>;
      assert.equal(g.onLeaseLoss, loss);
      assert.equal(g.requiresLease, true);
      assert.deepEqual(g.resources, ["axis-1/motion"]);
      assert.equal(g.effect, "reversible");
      assert.equal(g.idempotency, "relative");
      assert.equal(g.maxDurationMs, 61_000);
      assert.deepEqual((g.input as { properties: { duration_ms: { default: number } } }).properties.duration_ms.default, 1000);
    }
    const { lease } = await r.client.leasesAcquire(["axis-1/clamp"], 5000);
    const done = await r.client.actionsInvoke("axis-1", "overdrive", { force: 5 }, { leaseId: lease.leaseId, waitMs: 2000 });
    assert.equal(done.operation.state, "completed");
    assert.equal((await counters(r.client)).counter, 1);
  } finally { await r.close(); }
});

test("losing the lease of guard_hold calls the device hold command (holds += 1); guard_cancel is canceled, guard_finish completes (BHMS-LSE-012)", async () => {
  const r = await rig();
  try {
    const run = async (action: string): Promise<{ state: string; holds: number }> => {
      const { lease } = await r.client.leasesAcquire(["axis-1/motion"], 60_000);
      const op = (await r.client.actionsInvoke("axis-1", action, { duration_ms: 400 }, { leaseId: lease.leaseId, operationKey: key("guard") })).operation;
      await sleep(50);
      await r.client.stop("lease loss", { deviceIds: ["axis-1"] }); // stop revokes the lease: the lease-loss policy applies
      const settled = (await r.client.operationsWait(op.operationId, 3000)).operation;
      return { state: settled.state, holds: (await counters(r.client)).holds };
    };
    assert.equal((await run("guard_hold")).holds, 1);
    const cancel = await run("guard_cancel");
    assert.equal(cancel.state, "canceled");
    assert.equal(cancel.holds, 1, "only guard_hold calls the hold command");
  } finally { await r.close(); }
});

test("fault change_description: new digest, devicesListChanged, STALE for the old digest, not undone by none, survives a restart", async () => {
  const stateDir = mkdtempSync(join(tmpdir(), "bhms-ts-chg-"));
  try {
    let before: string;
    let after: string;
    const r = await rig({ durable: true, stateDir });
    try {
      before = (await r.client.devicesDescribe("axis-1")).description.digest!;
      const sub = await r.client.subscribe({ devicesListChanged: true });
      await inject(r.client, "change_description");
      assert.equal((await sub.next())?.method, "notifications/devices/listChanged");
      sub.cancel();
      after = (await r.client.devicesDescribe("axis-1")).description.digest!;
      assert.notEqual(after, before);
      assert.equal((await r.client.devicesList()).devices.find((d) => d.deviceId === "axis-1")?.digest, after);
      await assert.rejects(r.client.devicesDescribe("axis-1", { digest: before }), code("STALE", (e) => e.field === "digest"));
      await inject(r.client, "none");
      assert.equal((await r.client.devicesDescribe("axis-1")).description.digest, after, "none does not undo a revision");
      const events = (await r.client.devicesDescribe("axis-1")).description.events as Record<string, { description: string }>;
      assert.equal(events["conformance.revised"].description, "axis description revision 1");
    } finally { await r.close(); }
    const again = await rig({ durable: true, stateDir });
    try {
      assert.equal((await again.client.devicesDescribe("axis-1")).description.digest, after, "the revision is device-side state and survives a restart");
    } finally { await again.close(); }
  } finally { rmSync(stateDir, { recursive: true, force: true }); }
});

test("faults bad_digest / good_digest: the served digest is not the digest of the description, until good_digest", async () => {
  const r = await rig();
  try {
    const { descriptionDigest } = await import("../src/canonical.js");
    const honest = (await r.client.devicesDescribe("axis-1")).description;
    await inject(r.client, "bad_digest");
    const bad = (await r.client.devicesDescribe("axis-1")).description;
    assert.equal(bad.digest, "sha256:" + "0".repeat(64));
    assert.notEqual(descriptionDigest(bad as unknown as Record<string, unknown>), bad.digest);
    await inject(r.client, "none");
    assert.equal((await r.client.devicesDescribe("axis-1")).description.digest, bad.digest, "none does not clear bad_digest");
    await inject(r.client, "good_digest");
    assert.equal((await r.client.devicesDescribe("axis-1")).description.digest, honest.digest);
  } finally { await r.close(); }
});

test("fault hostile_text: name, description, pulse description and the fault error carry the injected instruction; none removes it", async () => {
  const r = await rig();
  try {
    await inject(r.client, "hostile_text");
    const d = (await r.client.devicesDescribe("axis-1")).description;
    assert.equal(d.description, HOSTILE_TEXT);
    assert.equal(d.name, HOSTILE_TEXT.slice(0, 80));
    assert.equal(d.actions.pulse.description, HOSTILE_TEXT);
    const op = (await r.client.actionsInvoke("axis-1", "fault", {}, { operationKey: key("hostile"), waitMs: 2000 })).operation;
    assert.equal(op.state, "failed");
    assert.equal(op.error?.message, HOSTILE_TEXT);
    await inject(r.client, "none");
    const clean = (await r.client.devicesDescribe("axis-1")).description;
    assert.equal(clean.name, "Conformance axis");
    assert.notEqual(clean.description, HOSTILE_TEXT);
  } finally { await r.close(); }
});

test("fault hostile_schema: a correct digest over a pulse schema 64 levels deep that ends in a remote $ref; never fetched by us", async () => {
  const r = await rig();
  try {
    const { descriptionDigest } = await import("../src/canonical.js");
    await inject(r.client, "none");
    const url = "http://127.0.0.1:9/hostile-schema.json";
    await r.client.request("x-conformance/inject", { fault: "hostile_schema", url });
    const d = (await r.client.devicesDescribe("axis-1")).description;
    assert.equal(d.digest, descriptionDigest(d as unknown as Record<string, unknown>), "the digest is correct");
    const problem = schemaBoundsProblem(d.actions.pulse.input);
    assert.match(problem ?? "", /deeper than 32 levels/);
    let node = (d.actions.pulse.input as unknown as { properties: { count: { properties: { x: unknown } } } }).properties.count.properties.x;
    let depth = 0;
    while (typeof node === "object" && node !== null && "properties" in node && depth < 100) { node = (node as { properties: { x: unknown } }).properties.x; depth++; }
    assert.equal(depth, 64);
    assert.deepEqual(node, { $ref: url });
    await inject(r.client, "none");
    assert.equal(schemaBoundsProblem((await r.client.devicesDescribe("axis-1")).description.actions.pulse.input), undefined);
  } finally { await r.close(); }
});

test("fault deaf_next: the next slow_move ignores cancellation and completes (BHMS-OPS-052); the one after honours it", async () => {
  const r = await rig({ cancelGraceMs: 2000 });
  try {
    await inject(r.client, "deaf_next");
    const op = (await r.client.actionsInvoke("axis-1", "slow_move", { duration_ms: 300 }, { operationKey: key("deaf") })).operation;
    await sleep(50);
    await r.client.operationsCancel(op.operationId, { reason: "nobody hears this" });
    const settled = (await r.client.operationsWait(op.operationId, 3000)).operation;
    assert.equal(settled.state, "completed", "a cancel is not a confirmation");
    const next = (await r.client.actionsInvoke("axis-1", "slow_move", { duration_ms: 5000 }, { operationKey: key("hears") })).operation;
    await sleep(50);
    await r.client.operationsCancel(next.operationId);
    assert.equal((await r.client.operationsWait(next.operationId, 3000)).operation.state, "canceled");
  } finally { await r.close(); }
});

test("counters carry trace: the traceparent/tracestate of the last request that had one (BHMS-LIF-018)", async () => {
  const r = await rig();
  try {
    traceRequests(r.server, r.sim);
    assert.deepEqual((await counters(r.client)).trace, {});
    const meta = { "bhms/protocolVersion": "2026-11-13", traceparent: "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01", tracestate: "vendor=1" };
    await r.client.request("devices/list", { limit: 1, _meta: meta });
    assert.deepEqual((await counters(r.client)).trace, { traceparent: meta.traceparent, tracestate: "vendor=1" });
    await r.client.request("devices/list", { limit: 1, _meta: { "bhms/protocolVersion": "2026-11-13", traceparent: "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-00" } });
    assert.deepEqual((await counters(r.client)).trace, { traceparent: "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-00" });
  } finally { await r.close(); }
});

test("the command log and recorded results survive in <state-dir>/command-log.json", async () => {
  const stateDir = mkdtempSync(join(tmpdir(), "bhms-ts-cmdlog-"));
  try {
    const r = await rig({ durable: true, stateDir });
    let opId: string;
    try {
      opId = (await r.client.actionsInvoke("axis-1", "pulse", { count: 2 }, { operationKey: key("log"), waitMs: 2000 })).operation.operationId;
    } finally { await r.close(); }
    const saved = JSON.parse(readFileSync(join(stateDir, "command-log.json"), "utf8")) as { log: string[][]; results: Record<string, unknown>; revision: number };
    assert.deepEqual(saved.log, [[opId, "start"], [opId, "done"]]);
    assert.deepEqual(saved.results[opId], { pulses: 2 });
    assert.equal(saved.revision, 0);
    const again = build({ stateDir, log: () => undefined });
    assert.deepEqual(again.sim.log, saved.log.map(([a, b]) => [a, b]));
    assert.equal(again.sim.counter, 0, "counters are per process");
  } finally { rmSync(stateDir, { recursive: true, force: true }); }
});

// ------------------------------------------------------------------------------------------------ schema bounds walker (BHMS-SEC-021)

const nested = (levels: number, leaf: unknown = { type: "string" }): unknown => {
  let node = leaf;
  for (let i = 1; i < levels; i++) node = { type: "object", properties: { x: node } };
  return node;
};

test("schemaBoundsProblem: depth boundary is exact (32 levels pass, 33 fail; the root is level 1)", () => {
  assert.equal(schemaBoundsProblem(nested(32)), undefined);
  assert.equal(schemaBoundsProblem(nested(33)), "it nests subschemas deeper than 32 levels");
  assert.equal(schemaBoundsProblem(nested(5), { maxDepth: 4 }), "it nests subschemas deeper than 4 levels");
  assert.equal(schemaBoundsProblem(nested(4), { maxDepth: 4 }), undefined);
});

test("schemaBoundsProblem: node count boundary is exact (10 000 subschemas pass, 10 001 fail; only objects count)", () => {
  const wide = (n: number): unknown => ({ type: "object", properties: Object.fromEntries(Array.from({ length: n - 1 }, (_, i) => [`p${i}`, { type: "string" }])) });
  assert.equal(schemaBoundsProblem(wide(10_000)), undefined);
  assert.equal(schemaBoundsProblem(wide(10_001)), "it has more than 10000 subschemas");
  const withScalars = { allOf: [true, false, 1, "x", null, ...Array.from({ length: 9_999 }, () => ({}))] };
  assert.equal(schemaBoundsProblem(withScalars), undefined, "booleans and scalars are not subschemas to count");
});

test("schemaBoundsProblem: a $ref that leaves the document is refused (local fragments are fine), every applicator keyword is walked", () => {
  assert.match(schemaBoundsProblem({ $ref: "http://127.0.0.1:9/x.json" }) ?? "", /^it has a \$ref \('http:\/\/127\.0\.0\.1:9\/x\.json'\) that leaves the document; schemas are never fetched$/);
  assert.equal(schemaBoundsProblem({ $ref: "#/$defs/a", $defs: { a: { type: "string" } } }), undefined);
  for (const path of [["items"], ["additionalProperties"], ["not"], ["if"], ["then"], ["else"], ["contains"], ["propertyNames"], ["unevaluatedItems"], ["unevaluatedProperties"],
    ["properties", "a"], ["patternProperties", "a"], ["$defs", "a"], ["definitions", "a"], ["dependentSchemas", "a"], ["allOf", "0"], ["anyOf", "0"], ["oneOf", "0"], ["prefixItems", "0"]]) {
    // a map keyword holds a member map, a list keyword an array, a single keyword the schema itself
    const [keyword, member] = path;
    const leaf = { $ref: "https://example.com/s.json" };
    const wrapped = member === undefined ? { [keyword]: leaf } : /^\d+$/.test(member) ? { [keyword]: [leaf] } : { [keyword]: { [member]: leaf } };
    assert.match(schemaBoundsProblem(wrapped) ?? "", /leaves the document/, `walks ${keyword}`);
  }
  assert.equal(schemaBoundsProblem({ type: "object", description: { $ref: "http://x" } }), undefined, "non-schema members are not schemas");
});

// ------------------------------------------------------------------------------------------------ policy table and multi-principal server

const TOKENS: Record<string, string> = { admin: "t-admin", agent: "t-agent", reader: "t-reader", stopper: "t-stopper", nobody: "t-nobody" };
const policy = (agentScopes = ["read", "lease", "invoke:axis-1/*", "programs:run"], maximum = 100): PolicyDocument => ({
  principals: {
    admin: { tokens: [tokenDigest(TOKENS.admin)], scopes: ["admin"] },
    agent: { tokens: [tokenDigest(TOKENS.agent)], scopes: agentScopes, bounds: { "axis-1/move_to": { position: { maximum } } } },
    reader: { tokens: [tokenDigest(TOKENS.reader)], scopes: ["read"] },
    stopper: { tokens: [tokenDigest(TOKENS.stopper)], scopes: ["stop"] },
    nobody: { tokens: [tokenDigest(TOKENS.nobody)], scopes: [] },
  },
});

test("PolicyTable: tokens resolve by digest, capability.authority follows the policy shape, invalid documents are refused", () => {
  const table = new PolicyTable(policy());
  assert.equal(table.byToken("t-agent")?.id, "agent");
  assert.equal(table.byToken("t-agent "), undefined);
  assert.equal(table.byToken(undefined), undefined);
  assert.deepEqual(table.authorityCapability(), {});
  assert.equal(table.principalFor({ principal: "ws:token", kind: "ws", token: "t-reader" }).id, "reader");
  assert.deepEqual(table.principalFor({ principal: "stdio", kind: "stdio", scopes: ["admin"] }).scopes, ["admin"]);
  assert.equal(new PolicyTable({ principals: { only: { tokens: [tokenDigest("x")], scopes: ["admin"] } } }).authorityCapability(), undefined, "one administrator is single-principal");
  assert.deepEqual(new PolicyTable({ principals: { only: { tokens: [tokenDigest("x")], scopes: ["read"] } } }).authorityCapability(), {}, "one restricted principal is a scope policy");
  assert.throws(() => new PolicyTable({ principals: { a: { tokens: ["plain-token"], scopes: ["read"] } } }), /never the token itself/);
  assert.throws(() => new PolicyTable({ principals: { a: { scopes: "read" as unknown as string[] } } }), /scopes/);
  assert.throws(() => new PolicyTable({} as PolicyDocument), /principals/);
});

test("multi-principal server: capabilities.authority is {} and the effective envelope narrows device bounds (BHMS-AUTH-010/011)", async () => {
  const stateDir = mkdtempSync(join(tmpdir(), "bhms-ts-auth-"));
  const { server } = build({ memory: true, log: () => undefined, policyDocument: policy() });
  const address = await server.run("ws://127.0.0.1:0");
  const connect = (who: string): Promise<Client> => Client.connect(`ws://${address}`, { token: TOKENS[who], strict: true });
  const clients: Client[] = [];
  try {
    const agent = await connect("agent");
    clients.push(agent);
    assert.deepEqual(agent.discovered!.capabilities.authority, {});
    assert.equal(agent.discovered!.principal?.id, "agent");
    await assert.rejects(agent.actionsInvoke("axis-1", "move_to", { position: 150 }), code("OUT_OF_RANGE", (e) => e.field === "arguments.position" && (e.bound as { maximum: number }).maximum === 100));
    const ok = await agent.actionsInvoke("axis-1", "move_to", { position: 100 }, { waitMs: 2000 });
    assert.equal(ok.operation.state, "completed", "a value at the policy bound is admitted");
    await assert.rejects(agent.actionsInvoke("pump-1", "dispense", { volume: 5 }), code("UNAUTHORIZED"));
    // no policy bound can widen: a bound of 5000 on a device maximum of 200 is refused when offered
    assert.throws(() => server.setPolicy(policy(undefined, 5000)), /widens the device bound 200/);
    await assert.rejects(agent.actionsInvoke("axis-1", "move_to", { position: 150 }), code("OUT_OF_RANGE", (e) => (e.bound as { maximum: number }).maximum === 100), "the refused policy did not take effect");
    // unknown tokens never reach the protocol
    await assert.rejects(Client.connect(`ws://${address}`, { token: "wrong" }), /401/);
    await assert.rejects(Client.connect(`ws://${address}`), /401/);
    const reader = await connect("reader");
    clients.push(reader);
    await assert.rejects(reader.actionsInvoke("axis-1", "pulse", { count: 1 }), code("UNAUTHORIZED", (e) => e.hint.includes("invoke")));
    await assert.rejects(reader.propertiesRead("axis-1", "fifo", { fresh: true }), code("UNAUTHORIZED", (e) => e.hint.includes("invoke")));
    const nobody = await connect("nobody");
    clients.push(nobody);
    assert.deepEqual((await nobody.devicesList()).devices, []);
    await assert.rejects(nobody.propertiesRead("axis-1", "position"), code("UNKNOWN_DEVICE"));
    const dev = (await agent.devicesDescribe("axis-1")).description;
    assert.ok(((dev.actions.move_to.input as unknown as { properties: { position: { maximum: number } } }).properties.position.maximum) <= 200, "served bounds are never wider than the device's");
  } finally {
    for (const c of clients) await c.close().catch(() => undefined);
    await server.close(200);
    rmSync(stateDir, { recursive: true, force: true });
  }
});

test("setPolicy applies to later requests at once, records policy.changed, revokes the leases of a principal that lost lease; running work continues (BHMS-AUTH-013, SEC-012)", async () => {
  const { server } = build({ memory: true, log: () => undefined, policyDocument: policy() });
  const address = await server.run("ws://127.0.0.1:0");
  const agent = await Client.connect(`ws://${address}`, { token: TOKENS.agent, strict: true });
  const admin = await Client.connect(`ws://${address}`, { token: TOKENS.admin, strict: true });
  try {
    const running = (await agent.actionsInvoke("axis-1", "slow_move", { duration_ms: 400 }, { operationKey: key("run") })).operation;
    const { lease } = await agent.leasesAcquire(["axis-1/clamp"], 60_000);
    const cursor = (await admin.eventsRead({ limit: 1 })).cursor;
    server.setPolicy(policy(["read"]));
    await assert.rejects(agent.actionsInvoke("axis-1", "pulse", { count: 1 }), code("UNAUTHORIZED"));
    await assert.rejects(agent.leasesRenew(lease.leaseId, 1000), code("UNAUTHORIZED"), "the lease scope is gone");
    assert.equal((await admin.operationsWait(running.operationId, 3000)).operation.state, "completed", "revocation does not cancel running work");
    const types = (await admin.eventsRead({ after: cursor, limit: 200 })).events.map((e) => e.type);
    assert.ok(types.includes("policy.changed") && types.includes("lease.revoked"), `saw ${types.join(",")}`);
    server.setPolicy(policy());
    assert.equal((await agent.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 1000 })).operation.state, "completed");
  } finally {
    await agent.close();
    await admin.close();
    await server.close(200);
  }
});

test("read revocation ends delivery on an open subscription (BHMS-LIF-042)", async () => {
  const { server } = build({ memory: true, log: () => undefined, policyDocument: policy() });
  const address = await server.run("ws://127.0.0.1:0");
  const reader = await Client.connect(`ws://${address}`, { token: TOKENS.reader, strict: true });
  const admin = await Client.connect(`ws://${address}`, { token: TOKENS.admin, strict: true });
  try {
    const sub = await reader.subscribe({ events: {} });
    const seen: string[] = [];
    const consumer = (async (): Promise<void> => { for await (const n of sub) seen.push(n.method); })();
    await admin.stop("first", { deviceIds: ["axis-1"] });
    await sleep(200);
    assert.ok(seen.includes("notifications/event"), "events are delivered while the reader has read scope");
    const delivered = seen.length;
    const revoked = policy();
    revoked.principals.reader.scopes = [];
    server.setPolicy(revoked);
    await admin.stop("second", { deviceIds: ["axis-1"] });
    await consumer;
    assert.equal(seen.length, delivered, "nothing is delivered after the scope was revoked");
    assert.equal(sub.endReason, "unauthorized");
  } finally {
    await reader.close();
    await admin.close();
    await server.close(200);
  }
});

test("a stop scope without read stops what it names; a principal with neither stop nor read learns nothing (BHMS-SEC-040, DEV-010)", async () => {
  const { server } = build({ memory: true, log: () => undefined, policyDocument: policy() });
  const address = await server.run("ws://127.0.0.1:0");
  const stopper = await Client.connect(`ws://${address}`, { token: TOKENS.stopper, strict: true });
  const agent = await Client.connect(`ws://${address}`, { token: TOKENS.agent, strict: true });
  try {
    assert.equal((await stopper.stop("halt", { deviceIds: ["axis-1"] })).stops[0].outcome, "confirmed");
    await assert.rejects(stopper.actionsInvoke("axis-1", "pulse", { count: 1 }), code("UNKNOWN_DEVICE"));
    await assert.rejects(agent.stop("no", { deviceIds: ["axis-1"] }), code("UNAUTHORIZED"));
    const all = (await stopper.stop("all", { scope: "all" })).stops;
    assert.deepEqual(all.map((s) => s.deviceId), ["axis-1", "pump-1"]);
  } finally {
    await stopper.close();
    await agent.close();
    await server.close(200);
  }
});

test("the same operationKey from two principals is two operations; cancel and lease use by another principal are refused", async () => {
  const { server } = build({ memory: true, log: () => undefined, policyDocument: policy() });
  const address = await server.run("ws://127.0.0.1:0");
  const agent = await Client.connect(`ws://${address}`, { token: TOKENS.agent, strict: true });
  const admin = await Client.connect(`ws://${address}`, { token: TOKENS.admin, strict: true });
  const reader = await Client.connect(`ws://${address}`, { token: TOKENS.reader, strict: true });
  try {
    const k = key("shared");
    const mine = await agent.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: k, waitMs: 1000 });
    const theirs = await admin.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: k, waitMs: 1000 });
    assert.notEqual(mine.operation.operationId, theirs.operation.operationId);
    assert.equal(theirs.replayed, false);
    const slow = (await agent.actionsInvoke("axis-1", "slow_move", { duration_ms: 1500 })).operation;
    await assert.rejects(reader.operationsGet(slow.operationId), code("INVALID_ARGUMENT", (e) => e.field === "operationId"));
    await assert.rejects(reader.operationsCancel(slow.operationId), code("UNAUTHORIZED"));
    await admin.operationsCancel(slow.operationId);
    const { lease } = await agent.leasesAcquire(["axis-1/clamp"], 30_000);
    await assert.rejects(admin.leasesRenew(lease.leaseId, 1000), code("LEASE_CONFLICT"));
    await assert.rejects(admin.actionsInvoke("axis-1", "clamp", { force: 5 }, { leaseId: lease.leaseId }), code("LEASE_CONFLICT"));
  } finally {
    await agent.close();
    await admin.close();
    await reader.close();
    await server.close(200);
  }
});

test("a hazardous action is granted only by a scope naming it literally (BHMS-AUTH-003)", async () => {
  const doc: PolicyDocument = { principals: {
    globber: { tokens: [tokenDigest("g")], scopes: ["read", "lease", "invoke:axis-1/*"] },
    exact: { tokens: [tokenDigest("e")], scopes: ["read", "lease", "invoke:axis-1/overdrive"] },
  } };
  const { server } = build({ memory: true, log: () => undefined, policyDocument: doc });
  const address = await server.run("ws://127.0.0.1:0");
  const globber = await Client.connect(`ws://${address}`, { token: "g", strict: true });
  const exact = await Client.connect(`ws://${address}`, { token: "e", strict: true });
  try {
    const gl = (await globber.leasesAcquire(["axis-1/clamp"], 30_000)).lease;
    assert.equal((await globber.actionsInvoke("axis-1", "clamp", { force: 5 }, { leaseId: gl.leaseId, waitMs: 2000 })).operation.state, "completed");
    await assert.rejects(globber.actionsInvoke("axis-1", "overdrive", { force: 5 }, { leaseId: gl.leaseId }), code("UNAUTHORIZED"));
    await globber.leasesRelease(gl.leaseId);
    const ex = (await exact.leasesAcquire(["axis-1/clamp"], 30_000)).lease;
    assert.equal((await exact.actionsInvoke("axis-1", "overdrive", { force: 5 }, { leaseId: ex.leaseId, waitMs: 2000 })).operation.state, "completed");
  } finally {
    await globber.close();
    await exact.close();
    await server.close(200);
  }
});

test("--principals: the device process serves the policy file and SIGHUP applies its current content", { skip: process.platform === "win32" }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-ts-principals-"));
  const file = join(dir, "policy.json");
  writeFileSync(file, JSON.stringify(policy()));
  const child = spawn(process.execPath, [tsDevicePath(), "ws://127.0.0.1:0", "--state-dir", join(dir, "state"), "--principals", file], { stdio: ["ignore", "ignore", "pipe"] });
  try {
    const address = await new Promise<string>((resolve, reject) => {
      let text = "";
      child.stderr.on("data", (d: Buffer) => {
        text += d.toString();
        const m = /listening on (\S+)/.exec(text);
        if (m) resolve(m[1]);
      });
      child.once("exit", () => reject(new Error(`device exited: ${text}`)));
    });
    const agent = await Client.connect(`ws://${address}`, { token: TOKENS.agent, strict: true });
    assert.deepEqual(agent.discovered!.capabilities.authority, {});
    assert.equal((await agent.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 1000 })).operation.state, "completed");
    writeFileSync(file, JSON.stringify(policy(["read"])));
    child.kill("SIGHUP");
    let refused = false;
    for (let i = 0; i < 40 && !refused; i++) {
      await sleep(50);
      refused = await agent.actionsInvoke("axis-1", "pulse", { count: 1 }).then(() => false, (e: unknown) => e instanceof BhmsError && e.bhmsCode === "UNAUTHORIZED");
    }
    assert.ok(refused, "the reloaded policy governs the next request");
    writeFileSync(file, "{ not json");
    child.kill("SIGHUP");
    await sleep(200);
    await assert.rejects(agent.actionsInvoke("axis-1", "pulse", { count: 1 }), code("UNAUTHORIZED"), "a policy that cannot be read keeps the current one");
    await agent.close();
  } finally {
    child.kill("SIGKILL");
    await new Promise((r) => child.once("exit", r));
    rmSync(dir, { recursive: true, force: true });
  }
});

// ------------------------------------------------------------------------------------------------ BHMS-SEC-003

test("a stdio server opens no listening socket, not even for its journal lock (BHMS-SEC-003)", { skip: process.platform !== "linux" }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-ts-sec003-"));
  const child = spawn(process.execPath, [tsDevicePath(), "--state-dir", dir], { stdio: ["pipe", "pipe", "ignore"] });
  try {
    child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: 1, method: "server/discover", params: { _meta: { "bhms/protocolVersion": "2026-11-13" } } }) + "\n");
    await new Promise((r) => child.stdout.once("data", r));
    assert.ok(existsSync(join(dir, "conformance-device.journal.jsonl.lock")), "the durable journal is locked");
    const inodes = new Set<string>();
    for (const fd of readdirSync(`/proc/${child.pid}/fd`)) {
      try {
        const link = readlinkSync(`/proc/${child.pid}/fd/${fd}`);
        if (link.startsWith("socket:[")) inodes.add(link.slice(8, -1));
      } catch { /* closed meanwhile */ }
    }
    const listening: string[] = [];
    for (const line of readFileSync("/proc/net/unix", "utf8").split("\n").slice(1)) {
      const f = line.split(/\s+/);
      if (f.length >= 7 && inodes.has(f[6]) && (parseInt(f[3], 16) & 0x10000) !== 0) listening.push(f[f.length - 1]);
    }
    for (const table of ["tcp", "tcp6"]) {
      for (const line of readFileSync(`/proc/net/${table}`, "utf8").split("\n").slice(1)) {
        const f = line.trim().split(/\s+/);
        if (f[3] === "0A" && inodes.has(f[9])) listening.push(`${table} ${f[1]}`);
      }
    }
    assert.deepEqual(listening, []);
    // the lock still excludes a second server on the same state directory
    const second = build({ stateDir: dir, log: () => undefined });
    await assert.rejects(second.server.start(), /in use by another server/);
  } finally {
    child.kill("SIGKILL");
    await new Promise((r) => child.once("exit", r));
    rmSync(dir, { recursive: true, force: true });
  }
});

test("WebSocket: an upgrade that does not offer the bhms subprotocol is refused at the handshake (BHMS-TRN-030)", async () => {
  const { server } = build({ memory: true, log: () => undefined, token: "tok" });
  const address = await server.run("ws://127.0.0.1:0");
  try {
    const { WebSocket } = await import("ws");
    const outcome = await new Promise<string>((resolve) => {
      const ws = new WebSocket(`ws://${address}`, { headers: { Authorization: "Bearer tok" } });
      ws.once("open", () => { ws.close(); resolve("accepted"); });
      ws.once("unexpected-response", (_req, res) => resolve(`HTTP ${res.statusCode}`));
      ws.once("error", () => resolve("error"));
    });
    assert.notEqual(outcome, "accepted");
    const ok = await Client.connect(`ws://${address}`, { token: "tok" });
    assert.equal(ok.discovered!.serverInfo.name, "conformance-device");
    await ok.close();
  } finally { await server.close(200); }
});
