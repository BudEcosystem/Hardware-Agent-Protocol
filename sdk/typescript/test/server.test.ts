// The TypeScript client against the TypeScript conformance device, in process, with every result schema-validated.
import assert from "node:assert/strict";
import { test } from "node:test";
import { BhmsError, JsonRpcError } from "../src/errors.js";
import { Session } from "../src/jsonrpc/session.js";
import { Principal } from "../src/server/authority.js";
import { memoryPair } from "../src/transport/memory.js";
import { digest } from "../src/canonical.js";
import { Client, METHOD_ATTRS, KNOWN_METHODS } from "../src/client.js";
import { counters, inject, key, rig } from "./harness.js";
import { sleep } from "./helpers.js";

const code = (c: string, extra?: (e: BhmsError) => boolean) => (e: unknown): boolean => e instanceof BhmsError && e.bhmsCode === c && (extra ? extra(e) : true);

test("the client exposes every method of the schema", () => {
  assert.deepEqual(Object.keys(METHOD_ATTRS).sort(), [...KNOWN_METHODS].sort());
  for (const attr of Object.values(METHOD_ATTRS)) assert.equal(typeof (Client.prototype as unknown as Record<string, unknown>)[attr], "function", attr);
});

test("discover: capabilities, limits and epoch; programs is not advertised", async () => {
  const r = await rig();
  try {
    const d = r.client.discovered!;
    assert.equal(d.serverInfo.name, "conformance-device");
    assert.equal(d.capabilities.operations.durable, false);
    assert.equal(d.capabilities.leases?.minTtlMs, 50);
    assert.equal(d.capabilities.observations?.minIntervalMs, 20);
    assert.equal(d.capabilities.programs, undefined);
    assert.ok(d.limits.maxMessageBytes >= 1_048_576);
    await assert.rejects(r.client.programsList(), code("UNSUPPORTED", (e) => e.hint.includes("programs")));
  } finally { await r.close(); }
});

test("lifecycle: missing _meta, unknown member, unsupported version and unknown method", async () => {
  const r = await rig();
  try {
    const [c, s] = memoryPair();
    r.server.serve(s);
    const raw = new Session(c, { role: "client" }).start();
    await assert.rejects(raw.request("devices/list", {}), code("INVALID_ARGUMENT", (e) => e.field === "_meta.bhms/protocolVersion"));
    await assert.rejects(raw.request("devices/list", { _meta: { "bhms/protocolVersion": "1999-01-01" } }), code("UNSUPPORTED_VERSION", (e) => JSON.stringify(e.bound) === '["2026-11-13"]' && e.field === "_meta.bhms/protocolVersion"));
    await assert.rejects(raw.request("devices/list", { _meta: { "bhms/protocolVersion": "2026-11-13" }, bogus: 1 }), code("INVALID_ARGUMENT", (e) => e.field === "bogus"));
    await assert.rejects(raw.request("nope/nothing", { _meta: { "bhms/protocolVersion": "2026-11-13" } }), (e: unknown) => e instanceof JsonRpcError && e.code === -32601);
    const ok = await raw.request("devices/list", { _meta: { "bhms/protocolVersion": "2026-11-13" } });
    assert.equal(ok.resultType, "complete");
    await raw.close();
  } finally { await r.close(); }
});

test("devices: ordered list, filters, pagination, describe digest and STALE pin", async () => {
  const r = await rig();
  try {
    const all = await r.client.devicesList();
    assert.deepEqual(all.devices.map((d) => d.deviceId), ["axis-1", "pump-1"]);
    assert.deepEqual((await r.client.devicesList({ filter: { text: "SYRINGE" } })).devices.map((d) => d.deviceId), ["pump-1"]);
    assert.deepEqual((await r.client.devicesList({ filter: { tag: "conformance", status: "online" } })).devices.length, 2);
    const page = await r.client.devicesList({ limit: 1 });
    assert.equal(page.devices.length, 1);
    assert.ok(page.nextCursor);
    assert.deepEqual((await r.client.devicesList({ limit: 1, cursor: page.nextCursor })).devices.map((d) => d.deviceId), ["pump-1"]);
    await assert.rejects(r.client.devicesList({ cursor: "garbage" }), code("INVALID_ARGUMENT", (e) => e.field === "cursor"));
    const { description } = await r.client.devicesDescribe("axis-1");
    const { digest: d, ...body } = description as unknown as Record<string, unknown>;
    assert.equal(d, digest(body));
    assert.equal((await r.client.devicesDescribe("axis-1")).description.digest, description.digest, "immutable for its digest");
    await assert.rejects(r.client.devicesDescribe("axis-1", { digest: "sha256:" + "1".repeat(64) }), code("STALE", (e) => e.bound === description.digest));
    await assert.rejects(r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { descriptionDigest: "sha256:" + "1".repeat(64) }), code("STALE", (e) => e.field === "descriptionDigest"));
  } finally { await r.close(); }
});

test("a device declared after start changes the listing and notifies listChanged", async () => {
  const r = await rig();
  try {
    const sub = await r.client.subscribe({ devicesListChanged: true });
    const dev = r.server.device("late-1", { name: "Late", resources: ["late-1/x"] });
    dev.property("level", { unit: "1" }, () => 1);
    const n = await sub.next();
    assert.equal(n?.method, "notifications/devices/listChanged");
    dev.property("other", { unit: "1" }, () => 2); // a new digest announces again
    assert.equal((await sub.next())?.method, "notifications/devices/listChanged");
    assert.equal((await r.client.devicesList()).devices.length, 3);
    sub.cancel();
  } finally { await r.close(); }
});

test("invoke: verified completion, history, replay, KEY_CONFLICT and exactly one device effect", async () => {
  const r = await rig();
  try {
    const k = key();
    const a = await r.client.actionsInvoke("axis-1", "move_to", { position: 12.5 }, { operationKey: k, waitMs: 2000 });
    assert.equal(a.operation.state, "completed");
    assert.equal(a.operation.effect, "verified");
    assert.equal(a.operation.evidence?.kind, "measured");
    assert.deepEqual(a.operation.result, { position: 12.5 });
    assert.equal(a.operation.keyOrigin, "client");
    const before = (await counters(r.client)).counter;
    const b = await r.client.actionsInvoke("axis-1", "move_to", { position: 12.5 }, { operationKey: k });
    assert.equal(b.replayed, true);
    assert.equal(b.operation.operationId, a.operation.operationId);
    assert.equal((await counters(r.client)).counter, before, "a replay dispatches nothing");
    await assert.rejects(r.client.actionsInvoke("axis-1", "move_to", { position: 13 }, { operationKey: k }), code("KEY_CONFLICT", (e) => e.operationId === a.operation.operationId && e.mayHaveActed === true));
    const got = (await r.client.operationsGet(a.operation.operationId)).operation;
    assert.deepEqual((got.history ?? []).filter((h) => h.kind === "state").map((h) => h.state), ["accepted", "dispatching", "running", "completed"]);
    const noKey = await r.client.actionsInvoke("axis-1", "pulse", { count: 2 }, { waitMs: 1000 });
    assert.equal(noKey.operation.keyOrigin, "server");
    assert.equal(noKey.operation.effect, "unverified");
  } finally { await r.close(); }
});

test("OPS-033: the key lookup precedes everything else, even after the lease is gone", async () => {
  const r = await rig();
  try {
    const { lease } = await r.client.leasesAcquire(["axis-1/clamp"], 5000);
    const k = key();
    const a = await r.client.actionsInvoke("axis-1", "clamp", { force: 10 }, { operationKey: k, leaseId: lease.leaseId, waitMs: 2000 });
    await r.client.leasesRelease(lease.leaseId);
    const again = await r.client.actionsInvoke("axis-1", "clamp", { force: 10 }, { operationKey: k, leaseId: lease.leaseId });
    assert.equal(again.replayed, true);
    assert.equal(again.operation.operationId, a.operation.operationId);
    await assert.rejects(r.client.actionsInvoke("axis-1", "clamp", { force: 10 }, { operationKey: key(), leaseId: lease.leaseId }), code("LEASE_EXPIRED"));
  } finally { await r.close(); }
});

test("OPS-032: concurrent requests with one key make exactly one operation", async () => {
  const r = await rig();
  try {
    const k = key();
    const before = (await counters(r.client)).counter;
    const results = await Promise.all(Array.from({ length: 8 }, () => r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: k, waitMs: 1000 })));
    assert.equal(new Set(results.map((x) => x.operation.operationId)).size, 1);
    assert.equal(results.filter((x) => !x.replayed).length, 1);
    assert.equal((await counters(r.client)).counter, before + 1);
  } finally { await r.close(); }
});

test("admission errors name the field and the bound; nothing is created", async () => {
  const r = await rig();
  try {
    const c = r.client;
    await assert.rejects(c.actionsInvoke("axis-1", "move_to", { position: 500 }), code("OUT_OF_RANGE", (e) => e.field === "arguments.position" && JSON.stringify(e.bound) === '{"maximum":200}' && !e.mayHaveActed));
    await assert.rejects(c.actionsInvoke("axis-1", "move_to", { position: -1 }), code("OUT_OF_RANGE", (e) => JSON.stringify(e.bound) === '{"minimum":0}'));
    await assert.rejects(c.actionsInvoke("axis-1", "move_to", { position: { value: 5, unit: "m" } }), code("UNIT_MISMATCH", (e) => e.bound === "mm" && e.field === "arguments.position"));
    await assert.rejects(c.actionsInvoke("axis-1", "move_to", { position: 10.05 }), code("INVALID_ARGUMENT", (e) => e.field === "arguments.position"));
    await assert.rejects(c.actionsInvoke("axis-1", "move_to", { position: "10" }), code("INVALID_ARGUMENT"));
    await assert.rejects(c.actionsInvoke("axis-1", "move_to", {}), code("INVALID_ARGUMENT", (e) => e.field === "arguments.position"));
    await assert.rejects(c.actionsInvoke("axis-1", "move_to", { position: 1, extra: 1 }), code("INVALID_ARGUMENT", (e) => e.field === "arguments.extra"));
    await assert.rejects(c.actionsInvoke("axis-1", "pulse", { count: 1.5 }), code("INVALID_ARGUMENT"));
    await assert.rejects(c.actionsInvoke("axis-1", "teleport", {}), code("UNKNOWN_ACTION"));
    await assert.rejects(c.actionsInvoke("ghost", "x", {}), code("UNKNOWN_DEVICE", (e) => e.field === "deviceId"));
    await assert.rejects(c.actionsInvoke("axis-1", "clamp", { force: 10 }), code("LEASE_REQUIRED", (e) => JSON.stringify(e.bound) === '["axis-1/clamp"]'));
    await assert.rejects(c.actionsInvoke("axis-1", "pulse", { count: 1 }, { require: { effect: "verified" } }), code("UNSUPPORTED"));
    await assert.rejects(c.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: "d-forbidden" }), code("INVALID_ARGUMENT", (e) => (e.field ?? "").includes("operationKey")));
    assert.equal((await c.operationsList()).operations.length, 0, "refusals create no operation (BHMS-OPS-040)");
    const q = await c.actionsInvoke("axis-1", "move_to", { position: { value: 5, unit: "mm" } }, { waitMs: 1000 });
    assert.deepEqual(q.operation.arguments, { position: { value: 5, unit: "mm" } }, "arguments are recorded as sent");
    assert.deepEqual(q.operation.admittedArguments, { position: 5 });
    const d = await c.actionsInvoke("axis-1", "slow_move", {}, { waitMs: 0 });
    assert.deepEqual(d.operation.admittedArguments, { duration_ms: 1000 }, "defaults are applied");
    await c.operationsCancel(d.operation.operationId);
  } finally { await r.close(); }
});

test("leases: all-or-nothing, conflict, renew keeps the fence, release, fences increase, fenced after stop", async () => {
  const r = await rig();
  try {
    const other = await r.connect({ principal: "other", scopes: ["admin"] });
    const a = (await r.client.leasesAcquire(["axis-1/clamp", "axis-1/motion"], 5000)).lease;
    assert.equal(a.state, "active");
    assert.deepEqual(a.resources, ["axis-1/clamp", "axis-1/motion"]);
    await assert.rejects(other.leasesAcquire(["axis-1/clamp"], 5000), code("LEASE_CONFLICT", (e) => JSON.stringify(e.bound) === '["axis-1/clamp"]' && !JSON.stringify(e).includes("memory")));
    await assert.rejects(other.leasesRenew(a.leaseId, 5000), code("LEASE_CONFLICT"));
    await assert.rejects(r.client.leasesAcquire(["nope/x"], 5000), code("INVALID_ARGUMENT", (e) => e.field === "resources[0]"));
    await assert.rejects(r.client.leasesAcquire(["pump-1/plunger"], 10), code("OUT_OF_RANGE", (e) => e.field === "ttlMs"));
    await assert.rejects(r.client.leasesAcquire(["pump-1/plunger"], 5000, { waitMs: 99_999 }), code("OUT_OF_RANGE", (e) => e.field === "waitMs"));
    const renewed = (await r.client.leasesRenew(a.leaseId, 6000)).lease;
    assert.equal(renewed.fence, a.fence);
    assert.equal(renewed.ttlMs, 6000);
    const waited = other.leasesAcquire(["axis-1/clamp"], 5000, { waitMs: 2000 });
    await sleep(50);
    assert.equal((await r.client.leasesRelease(a.leaseId)).lease.state, "released");
    assert.equal((await r.client.leasesRelease(a.leaseId)).lease.state, "released", "release of an ended lease is unchanged");
    const b = (await waited).lease;
    assert.ok(b.fence > a.fence, "fences strictly increase");
    await assert.rejects(r.client.leasesRenew("lease-unknown", 5000), code("LEASE_EXPIRED"));
    const stop = await r.client.stop("fence test", { deviceIds: ["axis-1"] });
    assert.deepEqual(stop.stops[0].revokedLeases, [b.leaseId]);
    await assert.rejects(other.leasesRenew(b.leaseId, 5000), code("FENCED"));
    await assert.rejects(other.actionsInvoke("axis-1", "clamp", { force: 1 }, { leaseId: b.leaseId }), code("FENCED"));
  } finally { await r.close(); }
});

test("a lease that expires while clamp runs cancels it (onLeaseLoss cancel)", async () => {
  const r = await rig();
  try {
    const { lease } = await r.client.leasesAcquire(["axis-1/clamp"], 50);
    await inject(r.client, "hang_next");
    const op = (await r.client.actionsInvoke("axis-1", "clamp", { force: 5 }, { leaseId: lease.leaseId, operationKey: key() })).operation;
    const done = (await r.client.operationsWait(op.operationId, 3000)).operation;
    assert.equal(done.state, "canceled");
    assert.equal(done.cancel.state, "confirmed");
    assert.ok((done.history ?? []).some((h) => h.kind === "lease"));
    const events = await r.client.eventsRead({ types: ["lease.expired"] });
    assert.ok(events.events.length >= 1);
  } finally { await r.close(); }
});

test("properties: quality, staleness, maxAge, fresh, transaction authority, unknown property", async () => {
  const r = await rig();
  try {
    const c = r.client;
    const p = (await c.propertiesRead("axis-1", "position")).observation;
    assert.equal(p.quality, "valid");
    assert.equal(p.unit, "mm");
    assert.equal(p.evidence, "measured");
    const again = (await c.propertiesRead("axis-1", "position")).observation;
    assert.equal(again.sequence, p.sequence, "re-reading a retained observation does not acquire");
    assert.equal(again.acquiredAt, p.acquiredAt, "and never refreshes acquiredAt");
    const fresh = (await c.propertiesRead("axis-1", "position", { fresh: true })).observation;
    assert.ok(fresh.sequence > p.sequence);
    await assert.rejects(c.propertiesRead("axis-1", "nope"), code("INVALID_ARGUMENT", (e) => e.field === "property" && JSON.stringify(e.bound).includes("position")));
    await inject(c, "sensor_invalid");
    const bad = (await c.propertiesRead("axis-1", "position", { fresh: true })).observation;
    assert.equal(bad.quality, "invalid");
    assert.equal(bad.value, null);
    await inject(c, "sensor_stale");
    const stale = (await c.propertiesRead("axis-1", "temperature", { fresh: true })).observation;
    assert.equal(stale.quality, "stale");
    assert.ok(stale.ageMs! >= 10_000);
    await assert.rejects(c.propertiesRead("axis-1", "temperature", { maxAgeMs: 5000 }), code("STALE", (e) => e.field === "maxAgeMs" && e.bound === 5000));
    await inject(c, "none");
    // a transaction property: a fresh acquisition is an effect and needs the lease
    await assert.rejects(c.propertiesRead("axis-1", "fifo"), code("LEASE_REQUIRED"));
    const { lease } = await c.leasesAcquire(["axis-1/motion"], 5000);
    assert.equal((await c.propertiesRead("axis-1", "fifo")).observation.value, 1);
    assert.equal((await counters(c)).fifo_reads, 1);
    await c.leasesRelease(lease.leaseId);
    const reader = await r.connect({ principal: "reader", scopes: ["read"] });
    await assert.rejects(reader.propertiesRead("axis-1", "fifo", { fresh: true }), code("UNAUTHORIZED"));
  } finally { await r.close(); }
});

test("OBS-006: after an effectful operation settles, the next read acquires a new sample", async () => {
  const r = await rig();
  try {
    const first = (await r.client.propertiesRead("axis-1", "position")).observation;
    await r.client.actionsInvoke("axis-1", "move_to", { position: 33.3 }, { waitMs: 2000 });
    const next = (await r.client.propertiesRead("axis-1", "position")).observation;
    assert.ok(next.sequence > first.sequence);
    assert.equal(next.value, 33.3);
  } finally { await r.close(); }
});

test("requiresFresh: dispense needs a valid pressure; a stale sensor is STALE naming requiresFresh[0]", async () => {
  const r = await rig();
  try {
    const { lease } = await r.client.leasesAcquire(["pump-1/plunger"], 5000);
    const ok = await r.client.actionsInvoke("pump-1", "dispense", { volume: 5 }, { leaseId: lease.leaseId, waitMs: 2000 });
    assert.equal(ok.operation.state, "completed");
    assert.equal(ok.operation.effect, "verified");
    assert.deepEqual(ok.operation.result, { dispensed: 5 });
    await inject(r.client, "sensor_invalid");
    await assert.rejects(r.client.actionsInvoke("pump-1", "dispense", { volume: 5 }, { leaseId: lease.leaseId }), code("STALE", (e) => e.field === "requiresFresh[0]" && JSON.stringify(e.bound) === '{"property":"pressure","maxAgeMs":1000}'));
    await inject(r.client, "none");
  } finally { await r.close(); }
});

test("require verified: a disagreeing encoder fails UNVERIFIED with mayHaveActed", async () => {
  const r = await rig();
  try {
    await inject(r.client, "encoder_disagrees");
    const done = (await r.client.actionsInvoke("axis-1", "move_to", { position: 20 }, { require: { effect: "verified" }, waitMs: 2000 })).operation;
    assert.equal(done.state, "failed");
    assert.equal(done.error?.bhmsCode, "UNVERIFIED");
    assert.equal(done.error?.mayHaveActed, true);
    assert.equal(done.effect, "unverified");
    const plain = (await r.client.actionsInvoke("axis-1", "move_to", { position: 21 }, { waitMs: 2000 })).operation;
    assert.equal(plain.state, "completed");
    assert.equal(plain.effect, "unverified");
  } finally { await r.close(); }
});

test("faults: DEVICE_FAULT is an operation error, crash is unknown and inhibits until reconciled", async () => {
  const r = await rig();
  try {
    const c = r.client;
    const fault = (await c.actionsInvoke("axis-1", "fault", {}, { waitMs: 2000 })).operation;
    assert.equal(fault.state, "failed");
    assert.equal(fault.error?.bhmsCode, "DEVICE_FAULT");
    assert.equal(fault.error?.mayHaveActed, true);
    await inject(c, "fail_next");
    const failed = (await c.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 2000 })).operation;
    assert.equal(failed.error?.bhmsCode, "DEVICE_FAULT");
    await inject(c, "crash_next");
    const crashed = (await c.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 2000 })).operation;
    assert.equal(crashed.state, "unknown");
    assert.equal(crashed.effect, "unknown");
    assert.deepEqual([crashed.error?.bhmsCode, crashed.error?.mayHaveActed, crashed.error?.retry], ["DEADLINE_EXCEEDED", true, "after-reconcile"]);
    await assert.rejects(c.actionsInvoke("axis-1", "pulse", { count: 1 }), code("STALE", (e) => e.operationId === crashed.operationId));
    await assert.rejects(c.actionsInvoke("pump-1", "dispense", { volume: 1 }, { leaseId: "x" }), code("LEASE_EXPIRED"), "other resources are not inhibited");
    await r.server.reconcile();
    const settled = (await c.operationsGet(crashed.operationId)).operation;
    assert.equal(settled.state, "failed", "the device command log says it started but did not finish (the crash came before the log entry)");
    assert.equal(settled.error?.bhmsCode, "DEVICE_FAULT");
    assert.equal(settled.error?.mayHaveActed, true);
    assert.ok((settled.history ?? []).some((h) => h.kind === "reconciliation"));
    assert.ok((settled.history ?? []).some((h) => h.state === "unknown"), "the unknown entry remains");
    const ok = await c.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 1000 });
    assert.equal(ok.operation.state, "completed");
    const ev = await c.eventsRead({ types: ["device.fault", "operation.state"] });
    assert.ok(ev.events.some((e) => e.type === "device.fault"));
  } finally { await r.close(); }
});

test("cancel: queued ops cancel without effect, running ops confirm, unsupported is refused, settled unchanged", async () => {
  const r = await rig();
  try {
    const c = r.client;
    const running = (await c.actionsInvoke("axis-1", "slow_move", { duration_ms: 5000 }, { operationKey: key() })).operation;
    const queued = (await c.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: key() })).operation;
    assert.equal(queued.state, "accepted", "same resource: queued behind the slow move");
    const q = (await c.operationsCancel(queued.operationId, { reason: "not needed" })).operation;
    assert.equal(q.state, "canceled");
    assert.equal(q.effect, "none");
    assert.equal(q.cancel.state, "confirmed");
    const before = (await counters(c)).counter;
    const req = (await c.operationsCancel(running.operationId, { reason: "operator" })).operation;
    assert.ok(["requested", "acknowledged", "confirmed"].includes(req.cancel.state));
    const done = (await c.operationsWait(running.operationId, 2000)).operation;
    assert.equal(done.state, "canceled");
    assert.equal(done.cancel.state, "confirmed");
    assert.equal(done.effect, "unverified");
    assert.equal(before, 1);
    const again = (await c.operationsCancel(running.operationId)).operation;
    assert.equal(again.state, "canceled");
    const pulse = (await c.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 1000 })).operation;
    assert.equal((await c.operationsCancel(pulse.operationId)).operation.state, "completed");
    const other = await r.connect({ principal: "other", scopes: ["read", "invoke:*/*"] });
    await assert.rejects(other.operationsCancel(pulse.operationId), code("INVALID_ARGUMENT", (e) => e.field === "operationId"), "invisible to others");
    await assert.rejects(other.operationsGet(pulse.operationId), code("INVALID_ARGUMENT"));
  } finally { await r.close(); }
});

test("cancelling the invoke request does not cancel the operation (BHMS-LIF-050)", async () => {
  const r = await rig();
  try {
    const ctl = new AbortController();
    const k = key();
    const p = r.client.actionsInvoke("axis-1", "slow_move", { duration_ms: 150 }, { operationKey: k, waitMs: 5000, signal: ctl.signal });
    await sleep(30);
    ctl.abort(new Error("gave up waiting"));
    await assert.rejects(p, /gave up/);
    const again = await r.client.actionsInvoke("axis-1", "slow_move", { duration_ms: 150 }, { operationKey: k, waitMs: 3000 });
    assert.equal(again.replayed, true);
    assert.equal(again.operation.state, "completed");
    assert.equal((await counters(r.client)).counter, 1);
  } finally { await r.close(); }
});

test("operations/wait returns on settle or timeout without an error; limits are enforced", async () => {
  const r = await rig();
  try {
    const op = (await r.client.actionsInvoke("axis-1", "slow_move", { duration_ms: 300 }, { operationKey: key() })).operation;
    const t0 = Date.now();
    const waiting = (await r.client.operationsWait(op.operationId, 50)).operation;
    assert.ok(Date.now() - t0 < 250);
    assert.ok(!["completed", "canceled"].includes(waiting.state));
    const done = (await r.client.operationsWait(op.operationId, 2000)).operation;
    assert.equal(done.state, "completed");
    await assert.rejects(r.client.operationsWait(op.operationId, 10 ** 7), code("OUT_OF_RANGE", (e) => e.field === "timeoutMs"));
    const list = await r.client.operationsList({ deviceId: "axis-1", state: "completed" });
    assert.equal(list.operations.length, 1);
    assert.equal(list.operations[0].history, undefined, "lists carry no history");
  } finally { await r.close(); }
});

test("operations/list: createdAt descending, keyset pagination", async () => {
  const r = await rig();
  try {
    for (let i = 0; i < 5; i++) { await r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: key(), waitMs: 1000 }); await sleep(2); }
    const seen: string[] = [];
    for await (const op of r.client.iterOperations({ limit: 2 })) seen.push(op.createdAt);
    assert.equal(seen.length, 5);
    assert.deepEqual([...seen].sort().reverse(), seen);
    await assert.rejects(r.client.operationsList({ cursor: "junk" }), code("INVALID_ARGUMENT", (e) => e.field === "cursor"));
  } finally { await r.close(); }
});

test("deadlines: a deadline shorter than the action fails DEADLINE_EXCEEDED, never completed; an expired queue entry is rejected", async () => {
  const r = await rig();
  try {
    const c = r.client;
    const d = (await c.actionsInvoke("axis-1", "slow_move", { duration_ms: 3000 }, { deadlineMs: 100, waitMs: 3000, operationKey: key() })).operation;
    assert.equal(d.state, "failed");
    assert.equal(d.error?.bhmsCode, "DEADLINE_EXCEEDED");
    assert.equal(d.error?.mayHaveActed, true);
    assert.ok(d.deadlineAt);
    await c.actionsInvoke("axis-1", "slow_move", { duration_ms: 400 }, { operationKey: key() });
    const q = (await c.actionsInvoke("axis-1", "pulse", { count: 1 }, { deadlineMs: 50, waitMs: 2000, operationKey: key() })).operation;
    assert.equal(q.state, "rejected");
    assert.equal(q.effect, "none");
    assert.equal(q.error?.bhmsCode, "DEADLINE_EXCEEDED");
    assert.equal(q.error?.mayHaveActed, false);
  } finally { await r.close(); }
});

test("stop: confirmed with evidence, cancels queued and running work, unknown device does not fail the request", async () => {
  const r = await rig();
  try {
    const c = r.client;
    await inject(c, "hang_next");
    const hung = (await c.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: key() })).operation;
    const queued = (await c.actionsInvoke("axis-1", "pulse", { count: 2 }, { operationKey: key() })).operation;
    await sleep(20);
    const res = await c.stop("operator saw a leak", { deviceIds: ["axis-1", "pump-1", "ghost"] });
    const axis = res.stops.find((s) => s.deviceId === "axis-1")!;
    assert.equal(axis.outcome, "confirmed");
    assert.equal(axis.evidence, "reported");
    assert.deepEqual(axis.canceledOperations, [queued.operationId]);
    assert.deepEqual(axis.cancelRequestedOperations, [hung.operationId]);
    assert.equal(res.stops.find((s) => s.deviceId === "pump-1")?.outcome, "unsupported");
    const ghost = res.stops.find((s) => s.deviceId === "ghost")!;
    assert.equal(ghost.outcome, "failed");
    assert.equal(ghost.error?.bhmsCode, "UNKNOWN_DEVICE");
    assert.equal((await c.operationsWait(hung.operationId, 2000)).operation.state, "canceled");
    assert.equal((await c.operationsGet(queued.operationId)).operation.state, "canceled");
    assert.equal((await c.operationsGet(queued.operationId)).operation.effect, "none");
    const all = await c.stop("all", { scope: "all" });
    assert.equal(all.stops.length, 2);
    assert.equal((await counters(c)).stops, 2);
    const ev = await c.eventsRead({ types: ["stop"] });
    assert.ok(ev.events.length >= 2);
    const reader = await r.connect({ principal: "reader", scopes: ["read"] });
    await assert.rejects(reader.stop("nope", { deviceIds: ["axis-1"] }), code("UNAUTHORIZED"));
    const globbed = await r.connect({ principal: "g", scopes: ["read", "stop:pump-*"] });
    assert.equal((await globbed.stop("ok", { deviceIds: ["pump-1"] })).stops[0].outcome, "unsupported");
    await assert.rejects(globbed.stop("no", { deviceIds: ["axis-1"] }), code("UNAUTHORIZED"));
  } finally { await r.close(); }
});

test("authority: invoke patterns, hazardous literal rule, read-only principals, invisible devices", async () => {
  const r = await rig();
  try {
    const reader = await r.connect({ principal: "reader", scopes: ["read"] });
    await assert.rejects(reader.actionsInvoke("axis-1", "pulse", { count: 1 }), code("UNAUTHORIZED", (e) => e.hint.includes("invoke:axis-1/pulse")));
    const scoped = await r.connect({ principal: "scoped", scopes: ["read", "invoke:axis-1/pulse"] });
    assert.equal((await scoped.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 1000 })).operation.state, "completed");
    await assert.rejects(scoped.actionsInvoke("axis-1", "move_to", { position: 1 }), code("UNAUTHORIZED"));
    const none = await r.connect({ principal: "none", scopes: [] });
    assert.deepEqual((await none.devicesList()).devices, [], "BHMS-DEV-010");
    await assert.rejects(none.devicesDescribe("axis-1"), code("UNKNOWN_DEVICE"));
    await assert.rejects(none.actionsInvoke("axis-1", "pulse", { count: 1 }), code("UNKNOWN_DEVICE"));
    const nolease = await r.connect({ principal: "nl", scopes: ["read", "invoke:*/*"] });
    await assert.rejects(nolease.leasesAcquire(["axis-1/clamp"], 1000), code("UNAUTHORIZED"));
  } finally { await r.close(); }
});

test("journal read-only: ordinary work is BUSY, stop still works and says degraded-audit, inject always works", async () => {
  const r = await rig({ durable: true });
  try {
    const c = r.client;
    await inject(c, "journal_readonly");
    await assert.rejects(c.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: "ro-1" }), code("BUSY", (e) => e.retry === "same-key"));
    const stop = await c.stop("degraded", { deviceIds: ["axis-1"] });
    assert.equal(stop.stops[0].outcome, "confirmed");
    assert.equal(stop.stops[0].detail, "degraded-audit");
    await inject(c, "journal_writable");
    const ok = await c.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: "ro-1", waitMs: 1000 });
    assert.equal(ok.operation.state, "completed");
    assert.equal(ok.replayed, false, "the refused attempt created nothing");
  } finally { await r.close(); }
});

test("subscriptions: acknowledged first with refusals, tagged notifications, no unrequested types, shutdown end", async () => {
  const r = await rig();
  try {
    const c = r.client;
    const sub = await c.subscribe({
      operations: { all: true },
      observations: [{ deviceId: "axis-1", property: "position", minIntervalMs: 20 }, { deviceId: "axis-1", property: "fifo" }, { deviceId: "ghost", property: "x" }, { deviceId: "axis-1", property: "nope" }],
    });
    const refused = sub.acknowledged.refused as Array<{ path: string; bhmsCode: string }>;
    assert.deepEqual(refused.map((x) => `${x.path}:${x.bhmsCode}`).sort(), ["observations[2]:UNKNOWN_DEVICE", "observations[3]:INVALID_ARGUMENT"]);
    assert.deepEqual((sub.acknowledged.notifications as { observations: unknown[] }).observations.length, 2);
    const inv = (await c.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: key(), waitMs: 1000 })).operation;
    const methods = new Set<string>();
    const states: string[] = [];
    for await (const n of sub) {
      methods.add(n.method);
      assert.equal((n.params._meta as Record<string, unknown>)["bhms/subscriptionId"], sub.id);
      const op = n.params.operation as { operationId: string; state: string; history?: unknown } | undefined;
      if (op?.operationId === inv.operationId) { states.push(op.state); assert.equal(op.history, undefined); if (op.state === "completed") break; }
    }
    assert.deepEqual(states, ["accepted", "dispatching", "completed"]);
    assert.ok(!methods.has("notifications/event"), "events were not requested");
    assert.ok(!methods.has("notifications/devices/listChanged"));
    const closing = r.server.close(500);
    const rest: string[] = [];
    for await (const n of sub) rest.push(n.method);
    await closing;
    assert.equal(sub.endReason, "shutdown");
  } finally { await r.close(); }
});

test("subscriptions: observation rate floor, quality change delivered at once", async () => {
  const r = await rig({ observationMinIntervalMs: 50 });
  try {
    const sub = await r.client.subscribe({ observations: [{ deviceId: "pump-1", property: "pressure" }] });
    const stamps: number[] = [];
    const qualities: string[] = [];
    const t0 = Date.now();
    setTimeout(() => { void inject(r.client, "sensor_invalid"); }, 400);
    for await (const n of sub) {
      stamps.push(Date.now() - t0);
      qualities.push((n.params.observation as { quality: string }).quality);
      if (qualities.includes("invalid")) break;
    }
    sub.cancel();
    const gaps = stamps.slice(1, -1).map((t, i) => t - stamps[i]);
    assert.ok(gaps.every((g) => g >= 40), `rate floor respected: ${gaps.join(",")}`);
    assert.ok(stamps.length >= 3);
    assert.equal(qualities[qualities.length - 1], "invalid");
    assert.ok(stamps[stamps.length - 1] < 600, "the quality change arrived immediately");
  } finally { await r.close(); }
});

test("subscriptions: revoked read scope ends delivery with endReason unauthorized", async () => {
  let scopes = ["admin"];
  const rig2 = await rig({ policy: (peer) => new Principal(peer.principal, scopes) });
  try {
    const sub = await rig2.client.subscribe({ operations: { all: true } });
    scopes = ["invoke:*/*"];
    const rest: string[] = [];
    for await (const n of sub) rest.push(n.method);
    assert.equal(sub.endReason, "unauthorized");
    assert.deepEqual(rest, []);
  } finally { await rig2.close(); }
});

test("events: cursors in order, resume after, gap on a reset log, live replay without duplicates", async () => {
  const r = await rig();
  try {
    const c = r.client;
    await c.stop("e1", { deviceIds: ["axis-1"] });
    const first = await c.eventsRead();
    assert.ok(first.events.length >= 1);
    assert.equal(first.gap, false);
    const cursors = first.events.map((e) => e.cursor);
    assert.deepEqual([...cursors].sort(), cursors);
    const none = await c.eventsRead({ after: first.cursor });
    assert.equal(none.events.length, 0);
    assert.equal(none.cursor, first.cursor);
    const reset = await c.eventsRead({ after: "ev-999999" });
    assert.equal(reset.gap, true);
    await assert.rejects(c.eventsRead({ after: "bogus" }), code("INVALID_ARGUMENT"));
    const sub = await c.subscribe({ events: { after: first.cursor } });
    await c.stop("e2", { deviceIds: ["axis-1"] });
    const got = [];
    for await (const n of sub) { got.push((n.params.event as { cursor: string }).cursor); if (got.length >= 2) break; }
    sub.cancel();
    assert.equal(new Set(got).size, got.length);
    assert.ok(got.every((g) => g > first.cursor));
    const replay = await c.subscribe({ events: { after: first.cursor, types: ["stop"] } });
    const replayed = [];
    for await (const n of replay) { replayed.push((n.params.event as { cursor: string }).cursor); if (replayed.length >= got.length) break; }
    replay.cancel();
    assert.deepEqual(replayed, got);
    const gap = await c.subscribe({ events: { after: "ev-999999" } });
    assert.equal(gap.acknowledged.eventsGap, true);
    gap.cancel();
  } finally { await r.close(); }
});

test("I-JSON: a result with an unsafe integer fails INTERNAL and is never completed", async () => {
  const r = await rig();
  try {
    const dev = r.server.devices.get("pump-1")!;
    dev.action("huge", { effect: "none", idempotency: "idempotent", output: { n: { type: "integer", "x-bhms-unit": "1" } } }, async () => ({ n: 2 ** 60 }));
    const op = (await r.client.actionsInvoke("pump-1", "huge", {}, { waitMs: 1000 })).operation;
    assert.equal(op.state, "failed");
    assert.equal(op.error?.bhmsCode, "INTERNAL");
    assert.equal(op.error?.mayHaveActed, true);
    assert.ok(op.error?.message.includes("2^53"));
  } finally { await r.close(); }
});

test("output schema violations never complete", async () => {
  const r = await rig();
  try {
    const dev = r.server.devices.get("pump-1")!;
    dev.action("wrong", { effect: "none", idempotency: "idempotent", output: { n: "mm" } }, async () => ({ n: "not a number" }));
    const op = (await r.client.actionsInvoke("pump-1", "wrong", {}, { waitMs: 1000 })).operation;
    assert.equal(op.state, "failed");
    assert.equal(op.error?.bhmsCode, "INTERNAL");
  } finally { await r.close(); }
});

test("a handler crash after dispatch is unknown, and a duration bound without cancel support is unknown too", async () => {
  const r = await rig();
  try {
    const dev = r.server.devices.get("pump-1")!;
    dev.action("stubborn", { effect: "reversible", idempotency: "idempotent", maxDurationMs: 50, resources: ["pump-1/plunger"] }, async () => { await sleep(300); return {}; });
    const op = (await r.client.actionsInvoke("pump-1", "stubborn", {}, { waitMs: 1000 })).operation;
    assert.equal(op.state, "unknown");
    assert.equal(op.error?.bhmsCode, "DEADLINE_EXCEEDED");
    await sleep(400);
    const late = (await r.client.operationsGet(op.operationId)).operation;
    assert.equal(late.state, "failed", "a late return is recorded as a reconciliation to failed, never completed");
    assert.equal(late.error?.bhmsCode, "DEADLINE_EXCEEDED");
    assert.ok((late.history ?? []).some((h) => h.kind === "reconciliation"));
  } finally { await r.close(); }
});

test("offline device: DEVICE_UNAVAILABLE is retry same-key friendly and status shows in the listing", async () => {
  const r = await rig();
  try {
    await inject(r.client, "offline");
    assert.equal((await r.client.devicesList({ filter: { status: "offline" } })).devices[0].deviceId, "axis-1");
    await assert.rejects(r.client.actionsInvoke("axis-1", "pulse", { count: 1 }), code("DEVICE_UNAVAILABLE", (e) => e.retry === "backoff"));
    await inject(r.client, "online");
    assert.equal((await r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 1000 })).operation.state, "completed");
    const ev = await r.client.eventsRead({ types: ["device.offline", "device.online"] });
    assert.deepEqual(ev.events.map((e) => e.type), ["device.offline", "device.online"]);
  } finally { await r.close(); }
});
