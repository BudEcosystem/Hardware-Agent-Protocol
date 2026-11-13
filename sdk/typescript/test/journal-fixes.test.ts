// Fix round 1: journal compaction never loses committed state, exclusive lock, strict UTF-8, EVT-002, stop history,
// OBS-006 transaction exception, SEC-001 (no credential-less TCP), OPS-033 ordering.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PassThrough } from "node:stream";
import { test } from "node:test";
import { BhmsError } from "../src/errors.js";
import { Session } from "../src/jsonrpc/session.js";
import { JournalStore, StoreError, type StoredOperation } from "../src/server/store.js";
import { LineTransport } from "../src/transport/stream.js";
import { connectSocket, listenTcp } from "../src/transport/socket.js";
import { build } from "../src/testing/conformanceDevice.js";
import { counters, inject, key, rig } from "./harness.js";
import { sleep } from "./helpers.js";

const code = (c: string) => (e: unknown): boolean => e instanceof BhmsError && e.bhmsCode === c;
const FILE = "conformance-device.journal.jsonl";

function diskState(file: string): { ops: Map<string, string>; fence: number } {
  const ops = new Map<string, string>();
  let fence = 0;
  for (const line of readFileSync(file, "utf8").split("\n")) {
    if (!line) continue;
    const r = JSON.parse(line) as { k: string; rec?: { id: string; op: { state: string } }; n?: number };
    if (r.k === "op") ops.set(r.rec!.id, r.rec!.op.state);
    if (r.k === "fence") fence = Math.max(fence, r.n!);
  }
  return { ops, fence };
}

test("CRITICAL 1: after a write failure and recovery the committed operations and fences survive a restart", async () => {
  const first = await rig({ durable: true, keepState: true });
  const stateDir = first.stateDir!;
  try {
    const kQ = key("kQ");
    const q = (await first.client.actionsInvoke("axis-1", "move_to", { position: 5 }, { operationKey: kQ, waitMs: 2000 })).operation;
    const lease1 = (await first.client.leasesAcquire(["axis-1/clamp"], 5000)).lease;
    // an I/O failure: the next write fails and marks the journal broken
    (first.server.store as unknown as { fd: number }).fd = 99_999; // EBADF on the next write
    await assert.rejects(first.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: "during-failure" }), code("BUSY"));
    // the next request probes the journal: recovery compacts from the LIVE state, not from the open-time snapshot
    const after = (await first.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: "after-recovery", waitMs: 2000 })).operation;
    assert.equal(after.state, "completed");
    const disk = diskState(join(stateDir, FILE));
    assert.equal(disk.ops.get(q.operationId), "completed", "the completed operation is still on disk");
    assert.ok(disk.fence >= lease1.fence, "the fence counter did not go backwards");
    await first.close();

    const second = await rig({ durable: true, stateDir, keepState: true });
    try {
      const replay = await second.client.actionsInvoke("axis-1", "move_to", { position: 5 }, { operationKey: kQ });
      assert.equal(replay.replayed, true, "the same key and request return the original operation");
      assert.equal(replay.operation.operationId, q.operationId);
      assert.equal((await counters(second.client)).counter, 0, "the device did not act twice");
      const lease2 = (await second.client.leasesAcquire(["axis-1/clamp"], 5000)).lease;
      assert.ok(lease2.fence > lease1.fence, "fences stay strictly monotonic (BHMS-LSE-003)");
    } finally { await second.close(); }
  } finally { rmSync(stateDir, { recursive: true, force: true }); }
});

function oldRecord(id: string, key: string, state: string, updatedAt: string): StoredOperation {
  const op = {
    operationId: id, operationKey: key, keyOrigin: "client", kind: "action", deviceId: "axis-1", action: "pulse", arguments: { count: 1 },
    requestDigest: "sha256:" + "0".repeat(64), state, cancel: { state: "none" }, effect: state === "running" ? "unknown" : "unverified",
    createdAt: updatedAt, updatedAt,
    ...(state === "completed" ? { result: {} } : {}),
  } as unknown as StoredOperation["op"];
  const history = [{ seq: 1, at: updatedAt, kind: "state", state: "accepted" }, { seq: 2, at: updatedAt, kind: "state", state: "dispatching" }];
  return { id, principal: "memory:client", op, history: history as StoredOperation["history"], resources: ["axis-1/motion"], effectClass: "reversible", cancelSupported: false, onLeaseLoss: "finish", completionEvidence: "reported", maxDurationMs: 1000, admitted: { count: 1 } };
}

test("CRITICAL 2: startup prune keeps the recovery writes and removes pruned keys from memory", async () => {
  const stateDir = mkdtempSync(join(tmpdir(), "bhms-ts-prune-"));
  try {
    const old = new Date(Date.now() - 30 * 86_400_000).toISOString();
    const fresh = new Date().toISOString();
    const lines = [
      { k: "hdr", epoch: "e1", v: 1 }, { k: "fence", n: 7 },
      { k: "op", rec: oldRecord("op-old", "old-key", "completed", old) },
      { k: "op", rec: oldRecord("op-flight", "flight-key", "running", fresh) },
    ].map((l) => JSON.stringify(l));
    writeFileSync(join(stateDir, FILE), lines.join("\n") + "\n");
    const r = await rig({ durable: true, stateDir, keepState: true, peer: { principal: "memory:client" } });
    try {
      const flight = (await r.client.operationsGet("op-flight")).operation;
      assert.ok(["unknown", "failed"].includes(flight.state), `recovered in memory: ${flight.state}`);
      const disk = diskState(join(stateDir, FILE));
      assert.equal(disk.ops.get("op-flight"), flight.state, "the recovery write is on disk (prune's compaction did not revert it)");
      assert.ok(!disk.ops.has("op-old"), "the pruned operation is gone from disk");
      assert.equal(disk.fence, 7);
      await assert.rejects(r.client.operationsGet("op-old"), code("INVALID_ARGUMENT"));
      const again = await r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: "old-key", waitMs: 2000 });
      assert.equal(again.replayed, false, "the pruned key no longer maps to the old operation");
    } finally { await r.close(); }
    const reopened = diskState(join(stateDir, FILE));
    assert.ok(reopened.ops.has("op-flight"));
  } finally { rmSync(stateDir, { recursive: true, force: true }); }
});

test("IMPORTANT 3: a second server on the same state directory is refused; a stale lock is taken over", async () => {
  const first = await rig({ durable: true, keepState: true });
  const stateDir = first.stateDir!;
  try {
    const { server } = build({ stateDir, log: () => undefined });
    await assert.rejects(server.start(), (e: unknown) => e instanceof StoreError && /in use by process/.test(e.message));
    await first.close();
    assert.ok(!existsSync(join(stateDir, FILE + ".lock")), "the lock is released on close");
    writeFileSync(join(stateDir, FILE + ".lock"), "999999999\n"); // a dead owner
    const again = build({ stateDir, log: () => undefined });
    await again.server.start();
    await again.server.close(100);
    // a corrupt middle line fails loudly; only a torn final line is tolerated
    const lines = readFileSync(join(stateDir, FILE), "utf8").split("\n").filter(Boolean);
    writeFileSync(join(stateDir, FILE), [lines[0], "{not json", ...lines.slice(1)].join("\n") + "\n");
    const broken = build({ stateDir, log: () => undefined });
    await assert.rejects(broken.server.start(), (e: unknown) => e instanceof StoreError && /corrupt at line 2/.test(e.message));
    assert.ok(!existsSync(join(stateDir, FILE + ".lock")), "a refused start does not leave the lock behind");
  } finally { rmSync(stateDir, { recursive: true, force: true }); }
});

test("a JournalStore keeps its live state: recovery after a failed write does not lose earlier commits", () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-ts-store-"));
  try {
    const store = new JournalStore(join(dir, "j.jsonl"));
    store.load();
    store.writeFence(3);
    store.writeOp(oldRecord("op-a", "ka", "completed", new Date().toISOString()));
    (store as unknown as { fd: number }).fd = 99_999; // EBADF on the next write
    assert.throws(() => store.writeOp(oldRecord("op-b", "kb", "completed", new Date().toISOString())), StoreError);
    assert.equal(store.writable, false);
    assert.equal(store.probeWritable(), true);
    store.close();
    const reopened = new JournalStore(join(dir, "j.jsonl"));
    const loaded = reopened.load();
    assert.deepEqual(loaded.ops.map((o) => o.id), ["op-a"]);
    assert.equal(loaded.fence, 3);
    reopened.close();
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("IMPORTANT 4 (BHMS-LIF-001): invalid UTF-8 is a parse error, not U+FFFD", async () => {
  const up = new PassThrough();
  const down = new PassThrough();
  const session = new Session(new LineTransport(up, down, { principal: "t", kind: "stdio", scopes: ["admin"] }), { role: "server", handler: async () => ({ resultType: "complete" }), log: () => undefined }).start();
  const out: string[] = [];
  down.on("data", (d: Buffer) => out.push(...d.toString().split("\n").filter(Boolean)));
  up.write(Buffer.concat([Buffer.from('{"jsonrpc":"2.0","id":1,"method":"x","params":{"s":"'), Buffer.from([0xff, 0xfe]), Buffer.from('"}}\n')]));
  up.write(Buffer.from('{"jsonrpc":"2.0","id":2,"method":"x","params":{"s":"é"}}\n'));
  await sleep(50);
  const msgs = out.map((l) => JSON.parse(l) as { id: unknown; error?: { code: number } });
  assert.deepEqual([msgs[0].id, msgs[0].error?.code], [null, -32700]);
  assert.equal(msgs[1].id, 2, "valid UTF-8 still works afterwards");
  void session;
});

test("IMPORTANT 5 (BHMS-EVT-002): a device.epoch event per device at start", async () => {
  const r = await rig();
  try {
    const ev = await r.client.eventsRead({ types: ["device.epoch"] });
    assert.deepEqual(ev.events.map((e) => e.deviceId).sort(), ["axis-1", "pump-1"]);
    assert.ok(ev.events.every((e) => typeof (e.data as { epoch: string }).epoch === "string"));
  } finally { await r.close(); }
});

test("IMPORTANT 6: stop writes a stop history entry on the queued operations it cancels", async () => {
  const r = await rig();
  try {
    await r.client.actionsInvoke("axis-1", "slow_move", { duration_ms: 5000 }, { operationKey: key() });
    const queued = (await r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: key() })).operation;
    assert.equal(queued.state, "accepted");
    await r.client.stop("queued history", { deviceIds: ["axis-1"] });
    const got = (await r.client.operationsGet(queued.operationId)).operation;
    assert.equal(got.state, "canceled");
    assert.ok(got.history!.some((h) => h.kind === "stop"), JSON.stringify(got.history));
  } finally { await r.close(); }
});

test("IMPORTANT 7 (OBS-006): a transaction property keeps its retained sample after an effectful operation settles", async () => {
  const r = await rig();
  try {
    const { lease } = await r.client.leasesAcquire(["axis-1/motion"], 5000);
    const first = (await r.client.propertiesRead("axis-1", "fifo", { fresh: true })).observation;
    await r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 1000 });
    const plain = (await r.client.propertiesRead("axis-1", "fifo")).observation;
    assert.equal(plain.sequence, first.sequence, "a plain read stays a retained read");
    assert.equal((await counters(r.client)).fifo_reads, 1);
    // while an on-demand non-transaction property is acquired anew
    const p1 = (await r.client.propertiesRead("axis-1", "position")).observation;
    await r.client.actionsInvoke("axis-1", "move_to", { position: 9 }, { waitMs: 2000 });
    assert.ok((await r.client.propertiesRead("axis-1", "position")).observation.sequence > p1.sequence);
    await r.client.leasesRelease(lease.leaseId);
  } finally { await r.close(); }
});

test("IMPORTANT 8 (SEC-001): no credential-less TCP: servers refuse tcp://, the raw listener grants read only", async () => {
  const { server } = build({ memory: true, log: () => undefined });
  await assert.rejects(server.run("tcp://127.0.0.1:0"), /TCP carries no credential/);
  await server.close(100);
  const seen: string[][] = [];
  const sessions: Session[] = [];
  const listener = await listenTcp("127.0.0.1", 0, (t) => sessions.push(new Session(t, { role: "server", handler: async (ctx) => { seen.push(ctx.peer.scopes ?? []); return { resultType: "complete" }; }, log: () => undefined }).start()));
  try {
    const client = new Session(await connectSocket(`tcp:${listener.address}`), { role: "client" }).start();
    await client.request("x", {});
    assert.deepEqual(seen, [["read"]]);
    await client.close();
  } finally { await Promise.all(sessions.map((s) => s.close())); await listener.close(); }
});

test("OPS-033: the key lookup precedes the waitMs range check, and a refused range creates no operation", async () => {
  const r = await rig();
  try {
    const k = key();
    const a = await r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: k, waitMs: 1000 });
    const replay = await r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: k, waitMs: 10 ** 7 });
    assert.equal(replay.replayed, true);
    assert.equal(replay.operation.operationId, a.operation.operationId);
    await assert.rejects(r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { operationKey: key(), waitMs: 10 ** 7 }), code("OUT_OF_RANGE"));
    assert.equal((await r.client.operationsList()).operations.length, 1);
    await inject(r.client, "none");
  } finally { await r.close(); }
});
