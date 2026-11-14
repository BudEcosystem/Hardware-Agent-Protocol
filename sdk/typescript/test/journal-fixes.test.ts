// Fix round 1: journal compaction never loses committed state, exclusive lock, strict UTF-8, EVT-002, stop history,
// OBS-006 transaction exception, SEC-001 (no credential-less TCP), OPS-033 ordering.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chmodSync, mkdirSync, readdirSync, realpathSync, statSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
import { sleep, tsDevicePath } from "./helpers.js";
import { EventLog } from "../src/server/events.js";

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
    await assert.rejects(server.start(), (e: unknown) => e instanceof StoreError && /in use by another server/.test(e.message));
    await first.close();
    const again = build({ stateDir, log: () => undefined });
    await again.server.start();
    await again.server.close(100);
    // a corrupt middle line fails loudly; only a torn final line is tolerated
    const lines = readFileSync(join(stateDir, FILE), "utf8").split("\n").filter(Boolean);
    writeFileSync(join(stateDir, FILE), [lines[0], "{not json", ...lines.slice(1)].join("\n") + "\n");
    const broken = build({ stateDir, log: () => undefined });
    await assert.rejects(broken.server.start(), (e: unknown) => e instanceof StoreError && /corrupt at line 2/.test(e.message));
    const free = new JournalStore(join(stateDir, "other.jsonl"));
    await free.acquire(); // a refused start released its lock: a different journal is unaffected, and this one can be re-locked after repair
    await free.close();
  } finally { rmSync(stateDir, { recursive: true, force: true }); }
});

test("a JournalStore keeps its live state: recovery after a failed write does not lose earlier commits", async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-ts-store-"));
  try {
    const store = new JournalStore(join(dir, "j.jsonl"));
    await store.acquire();
    store.load();
    store.writeFence(3);
    store.writeOp(oldRecord("op-a", "ka", "completed", new Date().toISOString()));
    (store as unknown as { fd: number }).fd = 99_999; // EBADF on the next write
    assert.throws(() => store.writeOp(oldRecord("op-b", "kb", "completed", new Date().toISOString())), StoreError);
    assert.equal(store.writable, false);
    assert.equal(store.probeWritable(), true);
    await store.close();
    const reopened = new JournalStore(join(dir, "j.jsonl"));
    await reopened.acquire();
    const loaded = reopened.load();
    assert.deepEqual(loaded.ops.map((o) => o.id), ["op-a"]);
    assert.equal(loaded.fence, 3);
    await reopened.close();
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
    // the holder presents its lease on axis-1/motion (BHMS-LSE-014)
    await r.client.actionsInvoke("axis-1", "pulse", { count: 1 }, { leaseId: lease.leaseId, waitMs: 1000 });
    const plain = (await r.client.propertiesRead("axis-1", "fifo")).observation;
    assert.equal(plain.sequence, first.sequence, "a plain read stays a retained read");
    assert.equal((await counters(r.client)).fifo_reads, 1);
    // while an on-demand non-transaction property is acquired anew
    const p1 = (await r.client.propertiesRead("axis-1", "position")).observation;
    await r.client.actionsInvoke("axis-1", "move_to", { position: 9 }, { leaseId: lease.leaseId, waitMs: 2000 });
    assert.ok((await r.client.propertiesRead("axis-1", "position")).observation.sequence > p1.sequence);
    await r.client.leasesRelease(lease.leaseId);
  } finally { await r.close(); }
});

test("IMPORTANT 8 / N2 / N3 (SEC-001): no credential-less TCP; refusal happens before the store is opened", async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-ts-tcp-"));
  try {
    const { server } = build({ stateDir: dir, log: () => undefined });
    await assert.rejects(server.run("tcp://127.0.0.1:0"), /TCP carries no credential/);
    assert.ok(!existsSync(join(dir, FILE)), "N2: run() refused the URL before start() opened the journal");
    await assert.rejects(listenTcp("127.0.0.1", 0, () => undefined, {} as never), /without a bearer token/);
    const seen: string[][] = [];
    const sessions: Session[] = [];
    const listener = await listenTcp("127.0.0.1", 0, (t) => sessions.push(new Session(t, { role: "server", handler: async (ctx) => { seen.push(ctx.peer.scopes ?? []); return { resultType: "complete" }; }, log: () => undefined }).start()), { token: "tcp-secret" });
    try {
      const client = new Session(await connectSocket(`tcp:${listener.address}`), { role: "client" }).start();
      const meta = { "bhms/protocolVersion": "2026-11-13" };
      await client.request("server/discover", { _meta: meta }); // discover needs no credential
      await assert.rejects(client.request("devices/list", { _meta: meta }), code("UNAUTHORIZED"));
      await assert.rejects(client.request("devices/list", { _meta: { ...meta, "org.bhms.sdk/bearer": "wrong" } }), code("UNAUTHORIZED"));
      assert.equal((await client.request("devices/list", { _meta: { ...meta, "org.bhms.sdk/bearer": "tcp-secret" } })).resultType, "complete");
      assert.deepEqual(seen, [["admin"], ["admin"]], "only discover and the credentialed request reached the session");
      await client.close();
    } finally { await Promise.all(sessions.map((s) => s.close())); await listener.close(); }
  } finally { rmSync(dir, { recursive: true, force: true }); }
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

const holder = (path: string): string => `const net=require("net");const s=net.createServer().listen(${JSON.stringify(path)},()=>console.log("up"));setInterval(()=>{},1000);`;

test("N1: the journal lock is a kernel-held socket: live holder refused, concurrent starters yield one winner, SIGKILL frees it", async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-ts-lock-"));
  try {
    const file = join(dir, "j.jsonl");
    // two simultaneous starters: exactly one wins
    const a = new JournalStore(file);
    const b = new JournalStore(file);
    const results = await Promise.allSettled([a.acquire(), b.acquire()]);
    assert.deepEqual(results.map((r) => r.status).sort(), ["fulfilled", "rejected"]);
    const loser = results.find((r) => r.status === "rejected") as PromiseRejectedResult;
    assert.match((loser.reason as Error).message, /in use by another server/);
    await (results[0].status === "fulfilled" ? a : b).close();
    // after the winner closes, the lock is free again
    const c = new JournalStore(file);
    await c.acquire();
    await c.close();
    // a real server process holding the state dir is refused; after SIGKILL the next start succeeds (the same pid is irrelevant)
    const child = spawn(process.execPath, [tsDevicePath(), "--state-dir", dir], { stdio: ["pipe", "ignore", "ignore"] });
    child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: 1, method: "server/discover", params: { _meta: { "bhms/protocolVersion": "2026-11-13" } } }) + "\n");
    await sleep(500);
    const dev = build({ stateDir: dir, log: () => undefined });
    await assert.rejects(dev.server.start(), /in use by another server/);
    child.kill("SIGKILL");
    await new Promise((r) => child.once("exit", r));
    const next = build({ stateDir: dir, log: () => undefined });
    await next.server.start();
    await next.server.close(100);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

/** Run `body` with `flock` resolved from a directory of our own (a fake script, or nothing at all), capturing what goes to stderr. */
async function withFakeFlock<T>(script: string | undefined, body: (dir: string) => Promise<T>): Promise<{ result: T; warnings: string }> {
  const dir = mkdtempSync(join(tmpdir(), "bhms-ts-fakeflock-"));
  const bin = join(dir, "bin");
  mkdirSync(bin);
  const sh = realpathSync("/bin/sh");
  if (script !== undefined) { writeFileSync(join(bin, "flock"), `#!${sh}\n${script}\n`); chmodSync(join(bin, "flock"), 0o755); }
  const savedPath = process.env.PATH;
  const realWrite = process.stderr.write.bind(process.stderr);
  let warnings = "";
  process.env.PATH = bin;
  (process.stderr as { write: unknown }).write = (chunk: string | Uint8Array): boolean => { warnings += String(chunk); return true; };
  try { return { result: await body(dir), warnings }; } finally {
    process.env.PATH = savedPath;
    (process.stderr as { write: unknown }).write = realWrite;
    rmSync(dir, { recursive: true, force: true });
  }
}

test("N1 flock capability: no flock(1) at all (ENOENT) warns that SEC-003 does not hold, then locks with the socket (second starter refused)", async () => {
  const { result, warnings } = await withFakeFlock(undefined, async (dir) => {
    const file = join(dir, "j.jsonl");
    const a = new JournalStore(file);
    await a.acquire();
    const b = new JournalStore(file);
    const refused = await b.acquire().then(() => "acquired", (e: Error) => e.message);
    await a.close();
    return refused;
  });
  assert.match(result, /in use by another server/);
  assert.match(warnings, /warning: flock\(1\) is not installed; locking the journal with a listening socket instead/);
  assert.match(warnings, /BHMS-SEC-003/);
});

test("N1 flock capability: a flock that rejects its arguments (no -n, an unknown option) is detected without -E and falls back with a warning", async () => {
  const { result, warnings } = await withFakeFlock('echo "flock: unrecognized option \'-n\'" >&2\necho "Usage: flock [options] file command" >&2\nexit 1', async (dir) => {
    const store = new JournalStore(join(dir, "j.jsonl"));
    await store.acquire();
    await store.close();
    return "ok";
  });
  assert.equal(result, "ok");
  assert.match(warnings, /warning: flock\(1\) refused its arguments: flock: unrecognized option/);
});

test("N1 flock capability: a held lock (silent exit 1, as util-linux and busybox both do) is retried for about two seconds, then reported as in use", async () => {
  const started = Date.now();
  const { result, warnings } = await withFakeFlock("exit 1", async (dir) => new JournalStore(join(dir, "j.jsonl")).acquire().then(() => "acquired", (e: Error) => e.message));
  const took = Date.now() - started;
  assert.match(result, /in use by another server/);
  assert.ok(took >= 1900 && took < 5000, `retried for the bounded window (${took} ms)`);
  assert.equal(warnings, "", "a busy lock is not a capability problem: no fallback, no warning");
});

test("N1 flock capability: a lock whose previous holder is still tearing down is acquired inside the retry window", async () => {
  const real = "/usr/bin/flock";
  if (!existsSync(real)) return;
  const { result } = await withFakeFlock(`m="$(dirname "$0")/seen"\nif [ ! -e "$m" ]; then : > "$m"; exit 1; fi\nexec ${real} "$@"`, async (dir) => {
    const store = new JournalStore(join(dir, "j.jsonl"));
    await store.acquire();
    await store.close();
    return "acquired";
  });
  assert.equal(result, "acquired");
});

test("N1: path mode (macOS fallback): a dead holder's socket file is taken over, our own stale file included; a live holder is refused", async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-ts-lockp-"));
  try {
    const file = join(dir, "j.jsonl");
    // find the lock file name by creating a stale one: a child binds it, is SIGKILLed and leaves the file behind
    const hash = (await import("node:crypto")).createHash("sha256").update(realpathSync(dir) + "/j.jsonl").digest("hex").slice(0, 24);
    const lockFile = join(tmpdir(), `bhms-lock-${hash}.sock`);
    const child = spawn(process.execPath, ["-e", holder(lockFile)], { stdio: ["ignore", "pipe", "ignore"] });
    await new Promise((r) => child.stdout.once("data", r));
    const live = new JournalStore(file, "path");
    await assert.rejects(live.acquire(), /in use by another server/);
    child.kill("SIGKILL");
    await new Promise((r) => child.once("exit", r));
    assert.ok(existsSync(lockFile), "the dead holder left its socket file behind");
    const taker = new JournalStore(file, "path");
    await taker.acquire();
    await taker.close();
    assert.ok(!existsSync(lockFile), "released on close");
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("N4: event retention prunes the store's events too, and compaction drops them from the journal", async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-ts-ev-"));
  try {
    const file = join(dir, "j.jsonl");
    const store = new JournalStore(file);
    await store.acquire();
    store.load();
    const log = new EventLog(store, 0.05, []);
    for (let i = 0; i < 5; i++) log.append("x.test", { message: `old ${i}` });
    await sleep(120);
    log.append("x.test", { message: "fresh" });
    log.prune(Date.now());
    const live = (store as unknown as { events: Array<{ message: string }> }).events;
    assert.deepEqual(live.map((e) => e.message), ["fresh"]);
    const onDisk = readFileSync(file, "utf8").split("\n").filter((l) => l.includes('"k":"ev"'));
    assert.equal(onDisk.length, 1, "the journal file no longer carries the expired events");
    // the log prunes itself every 256 appends, so a long-running server stays bounded
    const bounded = new EventLog(store, 0.01, []);
    for (let i = 0; i < 300; i++) { bounded.append("y.test"); if (i === 100) await sleep(30); }
    assert.ok((store as unknown as { events: unknown[] }).events.length < 300);
    await store.close();
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
