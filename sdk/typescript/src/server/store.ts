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
import { randomBytes } from "node:crypto";
import { closeSync, existsSync, fsyncSync, mkdirSync, openSync, readFileSync, renameSync, unlinkSync, writeSync } from "node:fs";
import { dirname } from "node:path";
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
  close(): void;
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
  close(): void { this.ops.clear(); this.events = []; }
}

/** The terminal operation states (BHMS §6.3): the one definition in the package. */
export const TERMINAL: ReadonlySet<string> = new Set(["completed", "failed", "canceled", "rejected"]);

/** Held while a {@link JournalStore} is open: `<journal>.lock` created with O_EXCL holding the owner's pid. */
function acquireLock(path: string): () => void {
  const lock = `${path}.lock`;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const fd = openSync(lock, "wx", 0o600);
      writeSync(fd, `${process.pid}\n`);
      closeSync(fd);
      let released = false;
      const release = (): void => {
        if (released) return;
        released = true;
        process.off("exit", release);
        try { unlinkSync(lock); } catch { /* already gone */ }
      };
      process.on("exit", release);
      return release;
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code !== "EEXIST") throw new StoreError(`cannot lock the journal: ${(e as Error).message}`);
      const pid = Number.parseInt(readFileSync(lock, "utf8"), 10);
      let alive = Number.isInteger(pid) && pid > 0;
      if (alive) {
        try { process.kill(pid, 0); } catch (k) { alive = (k as NodeJS.ErrnoException).code === "EPERM"; }
      }
      if (alive) throw new StoreError(`the journal ${path} is in use by process ${pid}; one server owns a state directory`);
      try { unlinkSync(lock); } catch { /* raced with another cleanup */ }
    }
  }
  throw new StoreError(`cannot lock the journal ${path}`);
}

export class JournalStore implements Store {
  readonly durable = true;
  epoch = "";
  private fd = -1;
  private _writable = true;
  private broken = false;
  private release?: () => void;
  /** The live content of the journal: every committed write is applied here, so compaction never loses state. */
  private readonly ops = new Map<string, StoredOperation>();
  private events: Event[] = [];
  private fence = 0;
  private readonly programs = new Map<string, StoredProgram>();

  /** @param path journal file; its directory is created. */
  constructor(private readonly path: string) {}

  get writable(): boolean { return this._writable && !this.broken; }

  load(): LoadedState {
    mkdirSync(dirname(this.path), { recursive: true });
    this.release = acquireLock(this.path);
    try {
      return this.read();
    } catch (e) {
      this.release();
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
    this.fd = openSync(this.path, "a", 0o600);
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

  prune(cutoffMs: number): string[] {
    const dropped: string[] = [];
    for (const [id, r] of this.ops) {
      if (TERMINAL.has(r.op.state) && Date.parse(r.op.updatedAt) < cutoffMs) { dropped.push(id); this.ops.delete(id); }
    }
    this.events = this.events.filter((e) => Date.parse(e.time) >= cutoffMs);
    if (dropped.length > 0) this.rewrite();
    return dropped;
  }

  close(): void {
    if (this.fd >= 0) {
      try { fsyncSync(this.fd); } catch { /* ignore */ }
      try { closeSync(this.fd); } catch { /* ignore */ }
      this.fd = -1;
    }
    this.release?.();
    this.release = undefined;
  }
}
