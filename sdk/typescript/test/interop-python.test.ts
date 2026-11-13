// Interop: the TypeScript client drives the Python reference conformance device over stdio.
import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { BhmsError } from "../src/errors.js";
import { Client } from "../src/client.js";
import { descriptionDigest } from "../src/canonical.js";
import { pythonAvailable, pythonDeviceTarget, pythonEnv, sleep } from "./helpers.js";

const available = pythonAvailable();
const skip = available ? false : "python3 with the bhms reference SDK is not available";
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
