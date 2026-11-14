/**
 * Durable state of a device server: an append-only JSON-lines journal with `fsync` on every commit that matters.
 *
 * What is stored: the server `epoch`, every operation record (full `Operation`, history and the private admission data a
 * restart needs), the server-wide lease **fence counter**, and the event log. A file line is one record
 * `{"k": "hdr"|"op"|"fence"|"ev", ...}`; for operations the last line of an id wins.
 *
 * Durability boundary (BHMS-OPS-003, BHMS-LSE-003): `writeOp` appends and `fsync`s the file before it returns, so the
 * server calls it for `accepted` (the intent) and for `dispatching` *before* a command can reach the device; a thrown
 * {@link StoreError} means nothing was committed and the caller must not dispatch. The fence counter is fsynced before the
 * lease that uses it exists. Events are appended without fsync (they are hints and are re-derivable from operations; a
 * crash can lose the last few). A torn final line (crash mid-write) is ignored and truncated on the next open; the file
 * is compacted (latest record per operation, pruned by retention) on every open through write-temp, fsync, rename.
 *
 * {@link MemoryStore} has the same interface and no persistence: a server using it is `durable: false` and presents a
 * new epoch on every start (BHMS-OPS-034).
 *
 * Thread-safety: single event loop; all calls are synchronous.
 */
import { spawn } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { closeSync, existsSync, fsyncSync, mkdirSync, openSync, readFileSync, realpathSync, renameSync, unlinkSync, writeSync } from "node:fs";
import net from "node:net";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import type { Event, HistoryEntry, Operation } from "../generated/types.js";

export class StoreError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StoreError";
  }
}

/** Everything about an operation that must survive a restart. */
export interface StoredOperation {
  id: string;
  principal: string;
  /** The wire `Operation` without `history`. */
  op: Operation;
  history: HistoryEntry[];
  resources: string[];
  /** `effect` class of the action (`none`, `reversible`, ...): decides inhibition (BHMS-OPS-042). */
  effectClass: string;
  cancelSupported: boolean;
  onLeaseLoss: "finish" | "cancel" | "hold";
  completionEvidence: string;
  maxDurationMs: number;
  /** Arguments as admitted (defaults applied, quantities unwrapped); what the handler receives. */
  admitted: Record<string, unknown>;
  inhibitionLifted?: boolean;
  /** Absolute wall-clock deadline in epoch milliseconds. */
  deadlineMs?: number;
}

/** A registered program (BHMS-PRG-020): immutable, content-addressed. */
export interface StoredProgram {
  digest: string;
  program: Record<string, unknown>;
  info: Record<string, unknown>;
}

export interface LoadedState {
  programs: StoredProgram[];
  ops: StoredOperation[];
  events: Event[];
  fence: number;
}

export interface Store {
  readonly durable: boolean;
  readonly epoch: string;
  /** Whether writes can currently be committed (false after `setWritable(false)` or an I/O failure). */
  readonly writable: boolean;
  /** Take any exclusive ownership of the underlying storage; awaited before `load()`. */
  acquire?(): Promise<void>;
  load(): LoadedState;
  writeOp(rec: StoredOperation): void;
  writeFence(n: number): void;
  writeProgram(p: StoredProgram): void;
  writeEvent(ev: Event): void;
  setWritable(writable: boolean): void;
  /** True when a write can be committed now (retries after an I/O failure). */
  probeWritable(): boolean;
  /** Drop settled operations last updated before `cutoffMs` and events recorded before it; returns ids dropped. */
  prune(cutoffMs: number): string[];
  /** Drop events recorded before `cutoffMs` (the event log's retention, BHMS-EVT-012). */
  pruneEvents(cutoffMs: number): void;
  close(): void | Promise<void>;
}

function newEpoch(): string {
  return randomBytes(8).toString("hex");
}

export class MemoryStore implements Store {
  readonly durable = false;
  readonly epoch = newEpoch();
  private ops = new Map<string, StoredOperation>();
  private events: Event[] = [];
  private fence = 0;
  private _writable = true;

  get writable(): boolean { return this._writable; }
  private programs = new Map<string, StoredProgram>();
  load(): LoadedState { return { programs: [...this.programs.values()], ops: [], events: [], fence: this.fence }; }
  writeProgram(p: StoredProgram): void {
    if (!this._writable) throw new StoreError("the journal is read-only");
    this.programs.set(p.digest, structuredClone(p));
  }
  writeOp(rec: StoredOperation): void {
    if (!this._writable) throw new StoreError("the journal is read-only");
    this.ops.set(rec.id, structuredClone(rec));
  }
  writeFence(n: number): void {
    if (!this._writable) throw new StoreError("the journal is read-only");
    this.fence = n;
  }
  writeEvent(ev: Event): void { this.events.push(ev); }
  setWritable(w: boolean): void { this._writable = w; }
  probeWritable(): boolean { return this._writable; }
  prune(): string[] { return []; }
  pruneEvents(cutoffMs: number): void { this.events = this.events.filter((e) => Date.parse(e.time) >= cutoffMs); }
  close(): void { this.ops.clear(); this.events = []; }
}

/** The terminal operation states (BHMS §6.3): the one definition in the package. */
export const TERMINAL: ReadonlySet<string> = new Set(["completed", "failed", "canceled", "rejected"]);

export type LockMode = "auto" | "path";

/** How long a start waits for a lock that its previous holder is still releasing (helper teardown, a restart racing a shutdown). */
const LOCK_RETRY_MS = 2000;
const LOCK_RETRY_STEP_MS = 50;

type FlockOutcome = { kind: "held"; release: () => Promise<void> } | { kind: "busy" } | { kind: "unavailable"; why: string };

/** One attempt: `flock -n <file> sh -c 'echo held; exec cat'`. No `-E`: util-linux and busybox both exit 1 for a held lock and
 * say nothing, while an unsupported flag or option prints a usage message on stderr, which is how the two are told apart. */
function flockOnce(lockFile: string): Promise<FlockOutcome> {
  return new Promise((resolve) => {
    const child = spawn("flock", ["-n", lockFile, "sh", "-c", "echo held; exec cat"], { stdio: ["pipe", "pipe", "pipe"] });
    let stderr = "";
    child.stderr.on("data", (d: Buffer) => { if (stderr.length < 400) stderr += d.toString(); });
    child.once("error", (e: NodeJS.ErrnoException) => resolve({ kind: "unavailable", why: e.code === "ENOENT" ? "flock(1) is not installed" : `flock(1) cannot run: ${e.message}` }));
    child.once("exit", () => {
      // exited before "held": the lock is somebody else's (silent exit) or this flock does not understand the command line
      setTimeout(() => resolve(stderr.trim() === "" ? { kind: "busy" } : { kind: "unavailable", why: `flock(1) refused its arguments: ${stderr.trim().split("\n")[0]}` }), 20);
    });
    child.stdout.once("data", () => {
      child.unref();
      for (const s of [child.stdin, child.stdout, child.stderr]) (s as unknown as { unref(): void }).unref();
      let released: Promise<void> | undefined;
      resolve({
        kind: "held",
        release: () => released ??= new Promise<void>((done) => {
          if (child.exitCode !== null || child.signalCode !== null) { done(); return; }
          child.ref(); // the loop must stay alive until the helper is really gone (the lock is free only then)
          for (const pipe of [child.stdout, child.stderr]) (pipe as unknown as { ref(): void }).ref();
          child.once("exit", () => done());
          child.stdin.end();
        }),
      });
    });
  });
}

/**
 * Linux: a kernel `flock(2)` on `<journal>.lock`, held by a small `flock(1)` helper process that lives exactly as long as
 * this process keeps its stdin pipe open. Node has no flock binding, and the alternative (a listening socket) makes a stdio
 * server a listener, which BHMS-SEC-003 forbids. The kernel drops the lock when the helper exits, and the helper exits when
 * the pipe closes: on `release()` and also when this process dies by SIGKILL, so no stale state exists and a reused pid is
 * irrelevant. A held lock is retried for {@link LOCK_RETRY_MS} (a restart can race the previous helper's teardown) before it
 * is reported as in use. Returns `undefined`, after a warning on stderr, when `flock(1)` is missing or incompatible: the caller
 * falls back to the socket lock, and BHMS-SEC-003 then does not hold for a stdio server.
 */
async function acquireFlock(journalPath: string): Promise<(() => Promise<void>) | undefined> {
  const lockFile = `${journalPath}.lock`;
  const deadline = Date.now() + LOCK_RETRY_MS;
  for (;;) {
    const r = await flockOnce(lockFile);
    if (r.kind === "held") return r.release;
    if (r.kind === "unavailable") {
      process.stderr.write(`[bhms] warning: ${r.why}; locking the journal with a listening socket instead. A stdio server then holds a listening socket, which BHMS-SEC-003 forbids: install util-linux or busybox flock.\n`);
      return undefined;
    }
    if (Date.now() >= deadline) throw new StoreError(`the journal ${journalPath} is in use by another server; one server owns a state directory`);
    await new Promise((resolve) => setTimeout(resolve, LOCK_RETRY_STEP_MS));
  }
}

/**
 * The exclusive lock on a journal (macOS, other Unix, Windows, or Linux without a usable `flock(1)`). It does NOT exclude a
 * server that uses the flock lock (and vice versa): never run two SDK builds with different lock kinds on one state directory. a listening socket whose name is derived from the journal's real path, held open for as
 * long as the store is. The kernel frees it when the holder dies (SIGKILL, power loss, pid reuse in a container are all
 * harmless), and `bind` is atomic, so two simultaneous starters cannot both win.
 *
 * - Linux (`auto`): an abstract-namespace Unix socket (`\0bhms-lock-<hash>`): no file at all, so no stale state exists.
 * - Windows (`auto`): a named pipe `\\.\pipe\bhms-lock-<hash>`, freed by the kernel on process death.
 * - macOS and other Unix (`auto`), or `path` mode: a socket file `<tmpdir>/bhms-lock-<hash>.sock`. A leftover file from a dead
 *   holder is detected by connecting (ECONNREFUSED means stale) and replaced after re-probing; two starters racing on that
 *   very takeover window on such systems could in theory both win (documented limit; Linux and Windows have no such window).
 */
async function acquireLock(journalPath: string, mode: LockMode): Promise<() => Promise<void>> {
  if (process.platform === "linux" && mode === "auto") {
    const held = await acquireFlock(journalPath);
    if (held) return held;
  }
  const hash = createHash("sha256").update(realpathSync(dirname(journalPath)) + "/" + basename(journalPath)).digest("hex").slice(0, 24);
  let name: string;
  let file: string | undefined;
  if (process.platform === "win32") name = `\\\\.\\pipe\\bhms-lock-${hash}`;
  else if (process.platform === "linux" && mode === "auto") name = `\0bhms-lock-${hash}`;
  else name = file = join(tmpdir(), `bhms-lock-${hash}.sock`);
  const listen = (): Promise<net.Server> => new Promise((resolve, reject) => {
    const server = net.createServer((sock) => sock.destroy()); // a probe connects, then is dropped
    server.once("error", reject);
    server.listen(name, () => { server.off("error", reject); resolve(server); });
  });
  const probe = (): Promise<boolean> => new Promise((resolve) => {
    const sock = net.connect(name);
    sock.once("connect", () => { sock.destroy(); resolve(true); });
    sock.once("error", () => resolve(false)); // ECONNREFUSED / ENOENT: nobody listens
  });
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const server = await listen();
      server.unref();
      let released: Promise<void> | undefined;
      // Resolves once the kernel has really dropped the name, so the next acquire() cannot race a half-closed listener.
      return () => released ??= new Promise<void>((resolve) => {
        server.close(() => resolve());
        if (file) { try { unlinkSync(file); } catch { /* already gone */ } }
      });
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code !== "EADDRINUSE") throw new StoreError(`cannot lock the journal ${journalPath}: ${(e as Error).message}`);
      if (await probe()) throw new StoreError(`the journal ${journalPath} is in use by another server; one server owns a state directory`);
      if (file === undefined) continue; // abstract names and pipes are freed by the kernel: just retry
      if (await probe()) throw new StoreError(`the journal ${journalPath} is in use by another server; one server owns a state directory`);
      try { unlinkSync(file); } catch { /* raced with another takeover */ }
    }
  }
  throw new StoreError(`cannot lock the journal ${journalPath}`);
}

export class JournalStore implements Store {
  readonly durable = true;
  epoch = "";
  private fd = -1;
  private _writable = true;
  private broken = false;
  private release?: () => Promise<void>;
  /** The live content of the journal: every committed write is applied here, so compaction never loses state. */
  private readonly ops = new Map<string, StoredOperation>();
  private events: Event[] = [];
  private fence = 0;
  private readonly programs = new Map<string, StoredProgram>();

  /** @param path journal file; its directory is created. */
  constructor(private readonly path: string, private readonly lockMode: LockMode = "auto") {}

  /** Take the exclusive lock (see {@link acquireLock}); must complete before `load()`. Idempotent. */
  async acquire(): Promise<void> {
    if (this.release) return;
    mkdirSync(dirname(this.path), { recursive: true });
    this.release = await acquireLock(this.path, this.lockMode);
  }

  get writable(): boolean { return this._writable && !this.broken; }

  load(): LoadedState {
    if (!this.release) throw new StoreError("the journal is not locked: await store.acquire() before load()");
    try {
      return this.read();
    } catch (e) {
      void this.release();
      this.release = undefined;
      throw e;
    }
  }

  private read(): LoadedState {
    let epoch = "";
    if (existsSync(this.path)) {
      const lines = readFileSync(this.path, "utf8").split("\n");
      let last = lines.length - 1;
      while (last >= 0 && lines[last] === "") last--;
      for (let i = 0; i <= last; i++) {
        let rec: { k: string; [key: string]: unknown };
        try {
          rec = JSON.parse(lines[i]);
        } catch {
          if (i === last) break; // a torn final line (crash mid-write) is dropped
          throw new StoreError(`the journal ${this.path} is corrupt at line ${i + 1}; refusing to start (restore it or move it aside)`);
        }
        if (rec.k === "hdr") epoch = rec.epoch as string;
        else if (rec.k === "op") this.ops.set((rec.rec as StoredOperation).id, rec.rec as StoredOperation);
        else if (rec.k === "fence") this.fence = Math.max(this.fence, rec.n as number);
        else if (rec.k === "ev") this.events.push(rec.ev as Event);
        else if (rec.k === "prog") this.programs.set((rec.p as StoredProgram).digest, rec.p as StoredProgram);
        else throw new StoreError(`the journal ${this.path} has an unknown record at line ${i + 1}`);
      }
    }
    this.epoch = epoch || newEpoch(); // a lost or missing journal is a new epoch (BHMS-OPS-034)
    this.rewrite();
    return { programs: [...this.programs.values()], ops: [...this.ops.values()], events: [...this.events], fence: this.fence };
  }

  /** Compact: write the live state to a temporary file, fsync, rename over the journal, reopen for append. */
  private rewrite(): void {
    const tmp = `${this.path}.tmp`;
    const lines = [JSON.stringify({ k: "hdr", epoch: this.epoch, v: 1 }), JSON.stringify({ k: "fence", n: this.fence })];
    for (const rec of this.ops.values()) lines.push(JSON.stringify({ k: "op", rec }));
    for (const p of this.programs.values()) lines.push(JSON.stringify({ k: "prog", p }));
    for (const ev of this.events) lines.push(JSON.stringify({ k: "ev", ev }));
    const fd = openSync(tmp, "w", 0o600);
    try {
      writeSync(fd, lines.join("\n") + "\n");
      fsyncSync(fd);
    } finally {
      closeSync(fd);
    }
    renameSync(tmp, this.path);
    this.syncDirectory();
    if (this.fd >= 0) {
      try { closeSync(this.fd); } catch { /* a descriptor the failure already invalidated */ }
    }
    this.fd = -1; // never keep a closed descriptor number: it may be reused by another file
    try {
      this.fd = openSync(this.path, "a", 0o600);
    } catch (e) {
      this.broken = true;
      throw e;
    }
  }

  private syncDirectory(): void {
    try {
      const dfd = openSync(dirname(this.path), "r");
      try { fsyncSync(dfd); } finally { closeSync(dfd); }
    } catch { /* directory fsync is best effort (not supported everywhere) */ }
  }

  private append(record: object, sync: boolean): void {
    if (!this.writable) throw new StoreError("the journal is read-only");
    try {
      writeSync(this.fd, JSON.stringify(record) + "\n");
      if (sync) fsyncSync(this.fd);
    } catch (e) {
      this.broken = true;
      throw new StoreError(`journal write failed: ${(e as Error).message}`);
    }
  }

  writeOp(rec: StoredOperation): void {
    this.append({ k: "op", rec }, true);
    this.ops.set(rec.id, structuredClone(rec)); // only a committed write is part of the live state
  }

  writeFence(n: number): void {
    this.append({ k: "fence", n }, true);
    this.fence = Math.max(this.fence, n);
  }

  writeProgram(p: StoredProgram): void {
    this.append({ k: "prog", p }, true);
    this.programs.set(p.digest, structuredClone(p));
  }

  writeEvent(ev: Event): void {
    this.events.push(ev); // kept even while the file is degraded, so that recovery re-writes them
    if (!this.writable) return;
    try { writeSync(this.fd, JSON.stringify({ k: "ev", ev }) + "\n"); } catch { this.broken = true; }
  }

  setWritable(w: boolean): void { this._writable = w; }

  probeWritable(): boolean {
    if (!this._writable) return false;
    if (!this.broken) return true;
    try {
      this.rewrite();
      this.broken = false;
      return true;
    } catch {
      return false;
    }
  }

  pruneEvents(cutoffMs: number): void {
    const before = this.events.length;
    this.events = this.events.filter((e) => Date.parse(e.time) >= cutoffMs);
    if (this.events.length < before && this.writable) {
      try { this.rewrite(); } catch { /* compaction is retried by the next prune or recovery */ }
    }
  }

  prune(cutoffMs: number): string[] {
    const dropped: string[] = [];
    for (const [id, r] of this.ops) {
      if (TERMINAL.has(r.op.state) && Date.parse(r.op.updatedAt) < cutoffMs) { dropped.push(id); this.ops.delete(id); }
    }
    this.events = this.events.filter((e) => Date.parse(e.time) >= cutoffMs);
    if (dropped.length > 0) this.rewrite();
    return dropped;
  }

  close(): Promise<void> {
    if (this.fd >= 0) {
      try { fsyncSync(this.fd); } catch { /* ignore */ }
      try { closeSync(this.fd); } catch { /* ignore */ }
      this.fd = -1;
    }
    const released = this.release?.() ?? Promise.resolve();
    this.release = undefined;
    return released;
  }
}
