// Durability boundary: intent durable before dispatch, recovery of in-flight work, epoch and fence continuity.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { appendFileSync, existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { BhmsError } from "../src/errors.js";
import { Client } from "../src/client.js";
import { DeviceServer } from "../src/server/server.js";
import { JournalStore, MemoryStore, StoreError, StoreSyncError, type StoredOperation } from "../src/server/store.js";
import { memoryPair } from "../src/transport/memory.js";
import { counters, inject, key, rig } from "./harness.js";
import { sleep, tsDevicePath } from "./helpers.js";

const code = (c: string) => (e: unknown): boolean => e instanceof BhmsError && e.bhmsCode === c;

test("restart keeps the epoch, the operations, the keys and the fence counter", async () => {
  const first = await rig({ durable: true, keepState: true });
  const stateDir = first.stateDir!;
  try {
    const epoch = first.client.discovered!.epoch;
    assert.equal(first.client.discovered!.capabilities.operations.durable, true);
    const k = key("restart");
    const a = (await first.client.actionsInvoke("axis-1", "move_to", { position: 7 }, { operationKey: k, waitMs: 2000 })).operation;
    const lease = (await first.client.leasesAcquire(["axis-1/clamp"], 5000)).lease;
    await first.close();
    const second = await rig({ durable: true, stateDir });
    try {
      assert.equal(second.client.discovered!.epoch, epoch, "durable state kept: same epoch (BHMS-OPS-034)");
      const again = await second.client.actionsInvoke("axis-1", "move_to", { position: 7 }, { operationKey: k });
      assert.equal(again.replayed, true);
      assert.equal(again.operation.operationId, a.operationId);
      assert.equal(again.operation.state, "completed");
      assert.equal((await counters(second.client)).counter, 0, "the restarted device ran nothing (BHMS-OPS-081)");
      await assert.rejects(second.client.actionsInvoke("axis-1", "move_to", { position: 8 }, { operationKey: k }), code("KEY_CONFLICT"));
      const l2 = (await second.client.leasesAcquire(["axis-1/clamp"], 5000)).lease;
      assert.ok(l2.fence > lease.fence, "fences strictly increase across restarts (BHMS-LSE-003)");
      await assert.rejects(second.client.leasesRenew(lease.leaseId, 5000), code("LEASE_EXPIRED"), "leases do not survive a restart");
      assert.equal((await second.client.operationsGet(a.operationId)).operation.history?.length, 4);
    } finally { await second.close(); }
  } finally {
    rmSync(stateDir, { recursive: true, force: true });
  }
});

test("a memory server presents a new epoch on every start", async () => {
  const a = await rig();
  const b = await rig();
  try {
    assert.notEqual(a.client.discovered!.epoch, b.client.discovered!.epoch);
    assert.equal(a.client.discovered!.capabilities.operations.durable, false);
  } finally { await a.close(); await b.close(); }
});

test("a torn journal tail (crash mid-write) is ignored", async () => {
  const first = await rig({ durable: true, keepState: true });
  const stateDir = first.stateDir!;
  try {
    await first.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: "torn-1", waitMs: 1000 });
    await first.close();
    const file = join(stateDir, "conformance-device.journal.jsonl");
    assert.ok(existsSync(file));
    appendFileSync(file, '{"k":"op","rec":{"id":"op-torn","op":{"opera');
    const second = await rig({ durable: true, stateDir });
    try {
      assert.equal((await second.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: "torn-1" })).replayed, true);
      assert.ok(!readFileSync(file, "utf8").includes("op-torn"), "compacted on open");
    } finally { await second.close(); }
  } finally { rmSync(stateDir, { recursive: true, force: true }); }
});

class SpyStore extends MemoryStore {
  readonly order: string[] = [];
  failDispatch = false;
  failDispatchSync = false;
  override writeOp(rec: StoredOperation, sync: boolean): void {
    if (this.failDispatch && rec.op.state === "dispatching") throw new StoreError("disk full");
    if (this.failDispatchSync && rec.op.state === "dispatching") {
      super.writeOp(rec, sync); // written, then the fsync failed
      throw new StoreSyncError("journal fsync failed: EIO");
    }
    this.order.push(`write:${rec.op.state}`);
    super.writeOp(rec, sync);
  }
}

test("BHMS-OPS-003: accepted and dispatching are committed before the handler runs", async () => {
  const store = new SpyStore();
  const srv = new DeviceServer("spy", { store, log: () => undefined });
  const dev = srv.device("d-1", { resources: ["d-1/r"] });
  dev.action("go", { effect: "reversible", idempotency: "idempotent", maxDurationMs: 1000 }, async () => { store.order.push("handler"); return {}; });
  await srv.start();
  const [c, s] = memoryPair();
  srv.serve(s);
  const client = await Client.fromTransport(c, { strict: true });
  try {
    const op = (await client.actionsInvoke("d-1", "go", {}, { waitMs: 1000 })).operation;
    assert.equal(op.state, "completed");
    assert.deepEqual(store.order.slice(0, 4), ["write:accepted", "write:dispatching", "handler", "write:completed"]);
  } finally { await client.close(); await srv.close(200); }
});

class SyncCountingStore extends JournalStore {
  readonly order: string[] = [];
  override writeOp(rec: StoredOperation, sync: boolean): void {
    this.order.push(`write:${rec.op.state}`);
    super.writeOp(rec, sync);
  }
  protected override syncFile(): void {
    this.order.push("fsync");
    super.syncFile();
  }
}

test("one fsync per invoke, on the dispatching record, before the handler runs (as the Python journal: Task 12b)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-sync-"));
  const store = new SyncCountingStore(join(dir, "j.jsonl"));
  const srv = new DeviceServer("sync-count", { store, log: () => undefined });
  const dev = srv.device("d-1", { resources: ["d-1/r"] });
  dev.action("go", { effect: "reversible", idempotency: "idempotent", maxDurationMs: 1000 }, async () => { store.order.push("handler"); return {}; });
  await srv.start();
  const [c, s] = memoryPair();
  srv.serve(s);
  const client = await Client.fromTransport(c, { strict: true });
  try {
    store.order.length = 0;
    const op = (await client.actionsInvoke("d-1", "go", {}, { waitMs: 1000 })).operation;
    assert.equal(op.state, "completed");
    // the accepted line needs no fsync of its own (an accepted operation is rejected after a restart: never dispatched);
    // the dispatching fsync covers it and must precede the handler; the completion is not synced (a lost completion
    // recovers as unknown, the safe direction)
    assert.deepEqual(store.order, ["write:accepted", "write:dispatching", "fsync", "handler", "write:completed"]);
  } finally { await client.close(); await srv.close(200); rmSync(dir, { recursive: true, force: true }); }
});

test("a queued accepted is fsynced before it is answered or notified; an immediate one is covered by its dispatching fsync (Ruling R57)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-queued-"));
  const store = new SyncCountingStore(join(dir, "j.jsonl"));
  const srv = new DeviceServer("queued-sync", { store, log: () => undefined });
  const dev = srv.device("d-1", { resources: ["d-1/r"] });
  let release!: () => void;
  const gate = new Promise<void>((r) => { release = r; });
  dev.action("go", { effect: "reversible", idempotency: "idempotent", maxDurationMs: 5000 }, async () => { store.order.push("handler"); await gate; return {}; });
  await srv.start();
  srv.journal.listeners.add((_rec, _changed, wire) => { store.order.push(`notify:${(wire ?? _rec.wire()).state}`); });
  const [c, s] = memoryPair();
  srv.serve(s);
  const client = await Client.fromTransport(c, { strict: true });
  try {
    store.order.length = 0;
    const first = (await client.actionsInvoke("d-1", "go", {}, { waitMs: 0 })).operation;
    assert.equal(first.state, "dispatching");
    assert.deepEqual(store.order.slice(0, 5), ["write:accepted", "write:dispatching", "fsync", "notify:accepted", "notify:dispatching"]);
    store.order.length = 0;
    const queued = (await client.actionsInvoke("d-1", "go", {}, { waitMs: 0 })).operation;
    assert.equal(queued.state, "accepted");
    assert.deepEqual(store.order, ["write:accepted", "fsync", "notify:accepted"]); // durable before anyone hears of it
    release();
  } finally { release(); await client.close(); await srv.close(200); rmSync(dir, { recursive: true, force: true }); }
});

test("when the dispatch record cannot be written nothing is dispatched: rejected INTERNAL, mayHaveActed false", async () => {
  const store = new SpyStore();
  store.failDispatch = true;
  const srv = new DeviceServer("spy2", { store, log: () => undefined });
  const dev = srv.device("d-1", { resources: ["d-1/r"] });
  let ran = false;
  dev.action("go", { effect: "reversible", idempotency: "idempotent", maxDurationMs: 1000 }, async () => { ran = true; return {}; });
  await srv.start();
  const [c, s] = memoryPair();
  srv.serve(s);
  const client = await Client.fromTransport(c, { strict: true });
  try {
    const op = (await client.actionsInvoke("d-1", "go", {}, { waitMs: 1000 })).operation;
    assert.equal(op.state, "rejected");
    assert.equal(op.effect, "none");
    assert.equal(op.error?.bhmsCode, "INTERNAL");
    assert.equal(op.error?.mayHaveActed, false);
    assert.equal(ran, false);
  } finally { await client.close(); await srv.close(200); }
});

test("BHMS-OPS-003: a dispatching record written but not made durable sends nothing and ends failed, mayHaveActed false (Task 12b)", async () => {
  const store = new SpyStore();
  store.failDispatchSync = true;
  const srv = new DeviceServer("spy3", { store, log: () => undefined });
  const dev = srv.device("d-1", { resources: ["d-1/r"] });
  let ran = false;
  dev.action("go", { effect: "reversible", idempotency: "idempotent", maxDurationMs: 1000 }, async () => { ran = true; return {}; });
  await srv.start();
  const [c, s] = memoryPair();
  srv.serve(s);
  const client = await Client.fromTransport(c, { strict: true });
  try {
    const op = (await client.actionsInvoke("d-1", "go", {}, { waitMs: 1000 })).operation;
    assert.equal(op.state, "failed");
    assert.equal(op.effect, "none");
    assert.equal(op.error?.bhmsCode, "INTERNAL");
    assert.equal(op.error?.mayHaveActed, false);
    assert.equal(ran, false);
  } finally { await client.close(); await srv.close(200); }
});

test("kill -9 mid-operation: after restart the operation is unknown (DEADLINE_EXCEEDED), inhibits its resources until a confirmed stop", async () => {
  const stateDir = mkdtempSync(join(tmpdir(), "bhms-ts-crash-"));
  try {
    const child = spawn(process.execPath, [tsDevicePath(), "--state-dir", stateDir], { stdio: ["pipe", "pipe", "inherit"] });
    const lines: string[] = [];
    child.stdout.on("data", (d: Buffer) => lines.push(...d.toString().split("\n").filter(Boolean)));
    const meta = { "bhms/protocolVersion": "2026-11-13" };
    const send = (id: number, method: string, params: object): void => { child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params: { _meta: meta, ...params } }) + "\n"); };
    send(1, "x-conformance/inject", { fault: "hang_next" });
    send(2, "actions/invoke", { deviceId: "axis-1", action: "pulse", arguments: { count: 1 }, operationKey: "crash-1" });
    send(3, "actions/invoke", { deviceId: "axis-1", action: "pulse", arguments: { count: 2 }, operationKey: "crash-2" });
    for (let i = 0; i < 100 && lines.length < 3; i++) await sleep(20);
    assert.equal(lines.length, 3, "both invokes were admitted; the second is queued behind the first");
    const opId = (JSON.parse(lines[1]) as { result: { operation: { operationId: string; state: string } } }).result.operation.operationId;
    child.kill("SIGKILL");
    await new Promise((r) => child.once("exit", r));

    const queuedId = (JSON.parse(lines[2]) as { result: { operation: { operationId: string; state: string } } }).result.operation.operationId;
    const srv = new DeviceServer("conformance-device", { stateDir, log: () => undefined });
    const dev = srv.device("axis-1", { resources: ["axis-1/motion"] });
    dev.action("pulse", { effect: "reversible", idempotency: "relative", maxDurationMs: 1000, input: { count: { type: "integer", "x-bhms-unit": "1" } } }, async () => ({}));
    dev.onStop({ evidence: "reported" }, async () => undefined);
    await srv.start();
    const [c, s] = memoryPair({ serverPeer: { principal: "stdio" } }); // the same principal as the crashed process's stdio parent
    srv.serve(s);
    const client = await Client.fromTransport(c, { strict: true });
    try {
      const op = (await client.operationsGet(opId)).operation;
      assert.equal(op.state, "unknown");
      assert.equal(op.effect, "unknown");
      assert.deepEqual([op.error?.bhmsCode, op.error?.mayHaveActed, op.error?.retry], ["DEADLINE_EXCEEDED", true, "after-reconcile"]);
      assert.match(op.error!.message, /restart/);
      const queued = (await client.operationsGet(queuedId)).operation;
      assert.equal(queued.state, "rejected", "the operation that was only accepted is rechecked and refused: its resources are inhibited");
      assert.equal(queued.effect, "none");
      assert.equal(queued.error?.bhmsCode, "STALE");
      assert.equal(queued.error?.mayHaveActed, false);
      const replay = await client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: "crash-1" });
      assert.equal(replay.replayed, true, "a retry with the key returns the unknown operation; nothing is re-sent (BHMS-OPS-081)");
      await assert.rejects(client.actionsInvoke("axis-1", "pulse", { count: 1 }), (e: unknown) => e instanceof BhmsError && e.bhmsCode === "STALE" && e.operationId === opId);
      const stop = await client.stop("reconcile by stop", { deviceIds: ["axis-1"] });
      assert.equal(stop.stops[0].outcome, "confirmed");
      assert.equal((await client.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 1000 })).operation.state, "completed");
      assert.equal((await client.operationsGet(opId)).operation.state, "unknown", "stop lifts the inhibition; the unknown record stays honest");
    } finally { await client.close(); await srv.close(200); }
  } finally { rmSync(stateDir, { recursive: true, force: true }); }
});

test("hang_next + restart-free: inject works while the journal is read-only", async () => {
  const r = await rig({ durable: true });
  try {
    await inject(r.client, "journal_readonly");
    await inject(r.client, "hang_next");
    await inject(r.client, "journal_writable");
  } finally { await r.close(); }
});
