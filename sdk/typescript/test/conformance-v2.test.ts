// Task 8b: conformance device contract v2 and the spec changes since Task 8 (authority profile, policy bounds, stop scope,
// schema bounds walker, stdio opens no listeners). Everything here runs without Python; the cross-language checks are in
// interop-python.test.ts and the full runner is scripts/conformance.py.
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, readdirSync, readlinkSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { Client } from "../src/client.js";
import { BhmsError } from "../src/errors.js";
import { MAX_SCHEMA_DEPTH, MAX_SUBSCHEMAS, SchemaBoundsError, iterSubschemas, schemaBoundsProblem } from "../src/schema.js";
import { checkUnits } from "../src/server/validation.js";
import { PolicyTable, gatewayPolicy, tokenDigest, type PolicyDocument } from "../src/server/authority.js";
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
      "journal_writable", "offline", "online", "change_description", "deaf_next", "bad_digest", "good_digest", "hostile_text", "hostile_schema", "amnesia",
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

test("fault hostile_schema: each variant breaks exactly one rule, with a correct digest; an unknown or missing variant is refused", async () => {
  const r = await rig();
  try {
    const { descriptionDigest } = await import("../src/canonical.js");
    await inject(r.client, "none");
    const url = "http://127.0.0.1:9/hostile-schema.json";
    const plain = (await r.client.devicesDescribe("axis-1")).description;
    const found: Record<string, string> = {};
    for (const variant of ["deep", "wide", "remote_ref"]) {
      await r.client.request("x-conformance/inject", { fault: "hostile_schema", variant, url });
      const d = (await r.client.devicesDescribe("axis-1")).description;
      assert.equal(d.digest, descriptionDigest(d as unknown as Record<string, unknown>), `${variant}: the digest is correct`);
      found[variant] = schemaBoundsProblem(d.actions.pulse.input) ?? "";
      if (variant === "remote_ref") assert.ok(JSON.stringify(d.actions.pulse.input).includes(url));
      else assert.ok(!JSON.stringify(d.actions.pulse.input).includes("$ref"), `${variant}: no $ref anywhere`);
    }
    assert.match(found.deep, /deeper than 32 \(BHMS-SEC-021\)$/);
    assert.match(found.wide, /^schema: more than 10000 subschemas \(BHMS-SEC-021\)$/);
    assert.match(found.remote_ref, /\$ref 'http:\/\/127\.0\.0\.1:9\/hostile-schema\.json' points outside the schema; schemas are never fetched \(BHMS-DEV-040\)$/);
    for (const bad of [{}, { variant: "both" }, { variant: 3 }, { variant: "__proto__" }]) {
      await assert.rejects(r.client.request("x-conformance/inject", { fault: "hostile_schema", ...bad }), code("INVALID_ARGUMENT", (e) => e.field === "variant"));
    }
    await inject(r.client, "none");
    assert.equal(schemaBoundsProblem((await r.client.devicesDescribe("axis-1")).description.actions.pulse.input), undefined);
    assert.equal((await r.client.devicesDescribe("axis-1")).description.digest, plain.digest);
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

/** A schema whose deepest subschema is `steps` subschema steps below the root (the root is depth 0). */
const chain = (steps: number, keyword = "properties", leaf: unknown = { type: "string" }): unknown => {
  let node = leaf;
  for (let i = 0; i < steps; i++) node = keyword === "properties" ? { type: "object", properties: { x: node } } : { [keyword]: node };
  return node;
};
/** A schema of `total` schemas: the root and `total - 1` members of one anyOf. */
const wide = (total: number): unknown => ({ anyOf: Array.from({ length: total - 1 }, () => ({ type: "string" })) });
const refusal = (schema: unknown): string | undefined => {
  try { checkUnits(schema, "x"); return undefined; } catch (e) { return (e as Error).message; }
};

test("the walker's limits are the spec's: depth 32 (root = 0), 10 000 schemas including the root", () => {
  assert.deepEqual([MAX_SCHEMA_DEPTH, MAX_SUBSCHEMAS], [32, 10_000]);
  assert.equal(schemaBoundsProblem(chain(32)), undefined);
  assert.match(schemaBoundsProblem(chain(33)) ?? "", /^schema\.properties\.x[^:]*: schema nested deeper than 32 \(BHMS-SEC-021\)$/);
  assert.equal(schemaBoundsProblem(chain(4), "s", { maxDepth: 4 }), undefined);
  assert.equal(schemaBoundsProblem(chain(5), "s", { maxDepth: 4 }), "s.properties.x.properties.x.properties.x.properties.x.properties.x: schema nested deeper than 4 (BHMS-SEC-021)");
  assert.equal(schemaBoundsProblem(wide(10_000)), undefined);
  assert.equal(schemaBoundsProblem(wide(10_001)), "schema: more than 10000 subschemas (BHMS-SEC-021)");
  assert.equal(schemaBoundsProblem({ allOf: [true, false, 1, "x", null, ...Array.from({ length: 9_994 }, () => ({}))] }), undefined, "root + 9 999 members = 10 000: booleans and scalars count");
  assert.match(schemaBoundsProblem({ allOf: [true, false, 1, "x", null, ...Array.from({ length: 9_995 }, () => ({}))] }) ?? "", /more than 10000 subschemas/);
});

test("checkUnits (the server's description validation) uses the same walker: same bounds for every keyword, same wording", () => {
  assert.equal(refusal(chain(32)), undefined);
  assert.match(refusal(chain(33)) ?? "", /BHMS-SEC-021/);
  assert.equal(refusal(wide(10_000)), undefined);
  assert.match(refusal(wide(10_001)) ?? "", /^x: more than 10000 subschemas \(BHMS-SEC-021\)$/);
  for (const keyword of ["items", "additionalProperties", "not", "if", "then", "else", "contains", "propertyNames", "unevaluatedItems", "unevaluatedProperties", "contentSchema"]) {
    assert.match(refusal({ [keyword]: { $ref: "http://example.invalid/s.json" } }) ?? "", /BHMS-DEV-040/, keyword);
    assert.equal(refusal(chain(32, keyword)), undefined, keyword);
    assert.match(refusal(chain(33, keyword)) ?? "", /BHMS-SEC-021/, keyword);
  }
  for (const keyword of ["allOf", "anyOf", "oneOf", "prefixItems", "properties", "patternProperties", "$defs", "definitions", "dependentSchemas"]) {
    const child = { $ref: "http://example.invalid/s.json" };
    assert.match(refusal({ [keyword]: ["allOf", "anyOf", "oneOf", "prefixItems"].includes(keyword) ? [child] : { x: child } }) ?? "", /BHMS-DEV-040/, keyword);
  }
  assert.match(refusal({ $dynamicRef: "http://example.invalid/s" }) ?? "", /^x: \$dynamicRef 'http:\/\/example\.invalid\/s' points outside the schema/);
  for (const ref of ["s.json", "//example.invalid/s", "urn:x:y", "http://example.invalid/s.json#/$defs/name"]) assert.match(refusal({ $ref: ref }) ?? "", /BHMS-DEV-040/, ref);
  assert.equal(refusal({ type: "object", properties: { a: { $ref: "#/$defs/name" } }, $defs: { name: { type: "string" } } }), undefined);
  assert.match(refusal({ type: "number" }) ?? "", /^x: a number\/integer schema must carry x-bhms-unit \(BHMS-DEV-041\)/);
});

test("the walk is pre-order, names paths, tolerates non-schemas, is iterative and bounded by its limits", () => {
  const schema = { type: "object", properties: { a: { items: true }, b: 5 }, anyOf: [{ not: {} }], allOf: "nonsense", $defs: [] };
  assert.deepEqual([...iterSubschemas(schema, "s")].map(([path]) => path), ["s", "s.anyOf[0]", "s.anyOf[0].not", "s.properties.a", "s.properties.a.items", "s.properties.b"]);
  assert.deepEqual([...iterSubschemas(true, "s")].map(([path]) => path), ["s"]);
  assert.match(schemaBoundsProblem(chain(50_000)) ?? "", /deeper than 32/, "no recursion: 50 000 levels do not overflow the stack");
  let seen = 0;
  assert.throws(() => { for (const _ of iterSubschemas(wide(2_000_000))) { void _; seen++; } }, SchemaBoundsError);
  assert.ok(seen <= MAX_SUBSCHEMAS, "the walk stops at the count without visiting the rest");
  const hostile = schemaBoundsProblem({ properties: { ["n".repeat(1_000_000)]: { $ref: "http://example.invalid/" + "r".repeat(1_000_000) } } }) ?? "";
  assert.ok(hostile.length < 400, "a hostile name or reference is cut in the message");
});

test("the reference text of a refusal is Python's repr: quotes, escapes and non-printable characters", () => {
  const problem = (ref: string): string => schemaBoundsProblem({ $ref: ref }) ?? "";
  assert.match(problem("it's"), /\$ref "it's" points/);
  assert.match(problem(`a'b"c`), /\$ref 'a\\'b"c' points/);
  assert.match(problem("tab\there\u0001\u00a0\u200b"), /\$ref 'tab\\there\\x01\\xa0\\u200b' points/);
  assert.match(problem("back\\slash\n"), /\$ref 'back\\\\slash\\n' points/);
  assert.ok(problem("\u{1F600}\u{E0001}é").includes("$ref '\u{1F600}\\U000e0001é' points"));
});

test("the g- operationKey prefix is reserved for gateways (BHMS-OPS-037): refused for an ordinary principal, allowed under --gateway", async () => {
  const ordinary = await rig();
  try {
    await assert.rejects(ordinary.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: "g-abc" }), code("INVALID_ARGUMENT", (e) => e.field === "operationKey"));
    assert.equal((await ordinary.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: "abc-g-1", waitMs: 1000 })).operation.state, "completed");
  } finally { await ordinary.close(); }
  const gateway = await rig({ policy: gatewayPolicy });
  try {
    assert.equal((await gateway.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: "g-abc", waitMs: 1000 })).operation.state, "completed");
  } finally { await gateway.close(); }
  const refused = spawnSync(process.execPath, [tsDevicePath(), "--gateway", "--principals", "/nonexistent.json"], { encoding: "utf8" });
  assert.notEqual(refused.status, 0);
  assert.match(refused.stderr, /--gateway and --principals cannot be combined/);
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
    await assert.rejects(Client.connect(`ws://${address}`), (e: unknown) => e instanceof BhmsError && e.bhmsCode === "UNAUTHORIZED");
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
