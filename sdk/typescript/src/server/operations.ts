/**
 * The operation journal: durable records of physical intents and their legal state changes
 * (spec/bhms/06-operations.md §6.2-6.3, §6.10-6.11).
 *
 * {@link Journal} is the only code that changes an operation. Every change goes through one of {@link Journal.transition},
 * {@link Journal.setCancel}, {@link Journal.setEffect} or {@link Journal.annotate}; each appends exactly one history entry
 * (BHMS-OPS-001), writes the full record to the {@link Store} and notifies subscribers and waiters. The legality rules:
 *
 * - `state` changes only along the table of §6.3; terminal states never change (BHMS-OPS-002);
 * - entering `unknown` needs `DEADLINE_EXCEEDED`, `mayHaveActed: true`, `retry: "after-reconcile"` (BHMS-OPS-004) and sets
 *   `effect: "unknown"`; leaving it needs a `reconciliation` entry naming evidence (BHMS-OPS-005);
 * - `rejected` is `effect: "none"` with `mayHaveActed: false`; `canceled` from `accepted` is `effect: "none"`
 *   (BHMS-OPS-006); `completed` carries a `result` and `effect: "verified"` only with `measured` evidence;
 * - `failed`, `rejected` and `unknown` carry an `error`; a dispatched failure has `mayHaveActed: true` unless device
 *   evidence (`proof`) says otherwise (BHMS-OPS-009).
 *
 * `dispatching` is committed with fsync *before* the command can reach the device (BHMS-OPS-003): `transition(...,
 * {strict: true})` writes first and applies the change only when the write succeeded, throwing {@link StoreError}
 * otherwise. Other changes are applied in memory first; a failed write marks the record dirty and the server refuses
 * ordinary new work until the journal is writable again (BHMS-AUTH-025).
 *
 * Thread-safety: single event loop.
 */
import { BhmsError, type ErrorData } from "../errors.js";
import { canonicalString } from "../canonical.js";
import type { HistoryEntry, Operation } from "../generated/types.js";
import { StoreError, StoreSyncError, TERMINAL, type Store, type StoredOperation } from "./store.js";
import { iso } from "./time.js";

export type OperationState = Operation["state"];
export type CancelState = Operation["cancel"]["state"];
export type Effect = Operation["effect"];

export const TRANSITIONS: Readonly<Record<OperationState, readonly OperationState[]>> = {
  accepted: ["dispatching", "rejected", "canceled"],
  dispatching: ["running", "completed", "failed", "canceled", "unknown"],
  running: ["completed", "failed", "canceled", "unknown"],
  unknown: ["running", "completed", "failed", "canceled"],
  completed: [], failed: [], canceled: [], rejected: [],
};

const SETTLED: ReadonlySet<OperationState> = new Set(["completed", "failed", "canceled", "rejected", "unknown"]);

export class InvalidTransition extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidTransition";
  }
}

export type OperationErrorWire = ErrorData & { message: string };

/** The error of every transition into `unknown`, whatever the cause (BHMS-OPS-004). */
export function unknownError(message: string): OperationErrorWire {
  return new BhmsError("DEADLINE_EXCEEDED", message, {
    mayHaveActed: true, retry: "after-reconcile",
    hint: "the outcome is unknown; read the device state or the operation with operations/get and reconcile before acting again",
  }).toOperationError();
}

/** Operation evidence that proves an effect: kind `measured` with at least one observation, every one measured and valid (BHMS-OPS-006). */
function provesEffect(evidence: Operation["evidence"] | undefined): boolean {
  const observations = Object.values(evidence?.observations ?? {});
  return evidence?.kind === "measured" && observations.length > 0 && observations.every((o) => o.evidence === "measured" && o.quality === "valid");
}

export class OperationRecord {
  /** Runtime only: wake `wait()` callers. */
  readonly waiters = new Set<() => void>();
  dirty = false;
  constructor(public data: StoredOperation) {}

  get id(): string { return this.data.id; }
  get op(): Operation { return this.data.op; }
  get state(): OperationState { return this.data.op.state; }
  get terminal(): boolean { return TERMINAL.has(this.state); }
  get settled(): boolean { return SETTLED.has(this.state); }
  get principal(): string { return this.data.principal; }
  get dispatched(): boolean { return this.data.history.some((h) => h.state === "dispatching"); }

  /** The wire `Operation` (a deep copy so later changes never alter a message already built). */
  wire(withHistory = false): Operation {
    const op = structuredClone(this.data.op);
    if (withHistory) op.history = structuredClone(this.data.history);
    return op;
  }
}

export interface TransitionOptions {
  error?: OperationErrorWire;
  result?: unknown;
  hasResult?: boolean;
  effect?: Effect;
  evidence?: Operation["evidence"];
  detail?: string;
  /** History entry kind: `reconciliation` is the only way out of `unknown`. */
  kind?: "state" | "reconciliation";
  /** Commit before applying (used for `dispatching`); throws StoreError when the write fails. */
  strict?: boolean;
  /** Device evidence that no effect occurred (allows `mayHaveActed: false` on a dispatched failure). */
  proof?: string;
  cancel?: CancelState;
  /**
   * Marks a `reconciliation` entry that rests on an operator's statement (`operations/resolve`, BHMS-OPS-102) rather than on
   * device evidence; only a reconciliation entry can carry it.
   */
  operator?: { principal: string; basis: string };
}

export type ChangeKind = "state" | "cancel" | "effect";
/** `wire` is the operation as it was when the change was made (a change announced later, once durable, carries it). */
export type Listener = (rec: OperationRecord, changed: ChangeKind[], wire?: Operation) => void;

export class Journal {
  readonly records = new Map<string, OperationRecord>();
  private readonly keys = new Map<string, string>();
  readonly listeners = new Set<Listener>();
  /** Called with each record that enters `unknown`. */
  readonly onUnknown: Array<(rec: OperationRecord) => void> = [];
  readonly onSettled: Array<(rec: OperationRecord) => void> = [];
  /** Called when a write fails (the server then degrades). */
  onWriteFailure?: (e: StoreError) => void;

  /** New records not yet durable: their `accepted` notification waits (Ruling R57). */
  private readonly unannounced = new Map<string, Operation>();

  constructor(private readonly store: Store) {}

  static keyOf(principal: string, key: string): string { return `${principal}\0${key}`; }

  /** Load the records recovered from the store. */
  adopt(stored: StoredOperation[]): void {
    for (const data of stored) {
      const rec = new OperationRecord(data);
      this.records.set(rec.id, rec);
      this.keys.set(Journal.keyOf(rec.principal, rec.op.operationKey), rec.id);
    }
  }

  /** Drop pruned operations (and their keys) from memory, mirroring what the store removed. */
  forget(ids: readonly string[]): void {
    for (const id of ids) {
      const rec = this.records.get(id);
      if (!rec) continue;
      this.records.delete(id);
      this.keys.delete(Journal.keyOf(rec.principal, rec.op.operationKey));
    }
  }

  byKey(principal: string, key: string): OperationRecord | undefined {
    const id = this.keys.get(Journal.keyOf(principal, key));
    return id === undefined ? undefined : this.records.get(id);
  }

  get(id: string): OperationRecord | undefined { return this.records.get(id); }

  /**
   * Record a new `accepted` operation; throws StoreError when it cannot be written. It is not yet durable, and nobody hears
   * of it: its notification waits until it is (the `dispatching` fsync of an immediate dispatch covers it, or
   * {@link makeDurable} for an operation that stays queued). The caller answers only after one of the two (Ruling R57).
   */
  create(data: StoredOperation): OperationRecord {
    data.history = [{ seq: 1, at: data.op.createdAt, kind: "state", state: "accepted" }];
    this.store.writeOp(data, false);
    const rec = new OperationRecord(data);
    this.records.set(rec.id, rec);
    this.keys.set(Journal.keyOf(rec.principal, rec.op.operationKey), rec.id);
    this.unannounced.set(rec.id, rec.wire());
    return rec;
  }

  /** Make a new record durable (fsync) and announce it, if it is not already; throws StoreError when the sync fails. */
  makeDurable(rec: OperationRecord): void {
    if (!this.unannounced.has(rec.id)) return;
    this.store.sync();
    this.announce(rec);
  }

  private announce(rec: OperationRecord): void {
    const wire = this.unannounced.get(rec.id);
    if (wire === undefined) return;
    this.unannounced.delete(rec.id);
    this.notify(rec, ["state"], wire);
  }

  private commit(rec: OperationRecord, next: StoredOperation, strict: boolean): void {
    const sync = next.op.state === "dispatching" && rec.state !== "dispatching"; // the intent, before dispatch (BHMS-OPS-003)
    if (strict) {
      try {
        this.store.writeOp(next, sync);
      } catch (e) {
        if (e instanceof StoreSyncError) { rec.data = next; rec.dirty = false; } // written, not durable: it is the record now
        throw e;
      }
      rec.data = next;
      rec.dirty = false;
      if (sync) this.announce(rec); // its accepted line is durable now too
      return;
    }
    rec.data = next;
    try {
      this.store.writeOp(next, sync);
      rec.dirty = false;
    } catch (e) {
      if (!(e instanceof StoreError)) throw e;
      rec.dirty = true;
      this.onWriteFailure?.(e);
    }
  }

  /** Re-write records whose last write failed; true when none remain dirty. */
  flushDirty(): boolean {
    for (const rec of this.records.values()) {
      if (!rec.dirty) continue;
      try {
        this.store.writeOp(rec.data, false); // never a dispatching record: that write is strict (applied only once written)
        rec.dirty = false;
      } catch {
        return false;
      }
    }
    return true;
  }

  private entry(rec: OperationRecord, next: StoredOperation, e: Omit<HistoryEntry, "seq" | "at">): void {
    next.history.push({ seq: next.history.length + 1, at: iso(Date.now()), ...e });
    next.op.updatedAt = iso(Date.now());
    void rec;
  }

  /** Move `rec` to `state`; see the module docs for the rules. */
  transition(rec: OperationRecord, state: OperationState, o: TransitionOptions = {}): void {
    const current = rec.state;
    if (!TRANSITIONS[current].includes(state)) throw new InvalidTransition(`${rec.id}: ${current} -> ${state} is not allowed (BHMS-OPS-001/002)`);
    const kind = o.kind ?? "state";
    if (o.operator !== undefined && kind !== "reconciliation") throw new InvalidTransition(`${rec.id}: only a reconciliation entry can carry an operator mark`);
    if (current === "unknown" && (kind !== "reconciliation" || !o.detail)) {
      throw new InvalidTransition(`${rec.id}: leaving unknown needs a reconciliation entry naming its evidence (BHMS-OPS-005)`);
    }
    const next = structuredClone(rec.data);
    const op = next.op;
    let effect: Effect | undefined = o.effect;
    let cancel = o.cancel;
    if (state === "unknown") {
      const e = o.error;
      if (!e || e.bhmsCode !== "DEADLINE_EXCEEDED" || e.mayHaveActed !== true || e.retry !== "after-reconcile") {
        throw new InvalidTransition(`${rec.id}: entering unknown needs DEADLINE_EXCEEDED with mayHaveActed true and retry after-reconcile (BHMS-OPS-004)`);
      }
      effect = "unknown";
    } else if (state === "failed" || state === "rejected") {
      if (!o.error) throw new InvalidTransition(`${rec.id}: ${state} needs an error (BHMS-OPS-009)`);
      if (state === "rejected") {
        if (o.error.mayHaveActed) throw new InvalidTransition(`${rec.id}: rejected means no dispatch; mayHaveActed must be false`);
        effect = "none";
      } else if (rec.dispatched && !o.error.mayHaveActed && !o.proof) {
        throw new InvalidTransition(`${rec.id}: a dispatched operation fails with mayHaveActed true unless device evidence proves no effect (BHMS-OPS-009); pass proof`);
      }
    } else if (state === "canceled") {
      if (current === "accepted") effect = "none";
      cancel = "confirmed";
    } else if (state === "completed") {
      if (!o.hasResult) throw new InvalidTransition(`${rec.id}: completed needs a result (BHMS-OPS-008)`);
      if (effect === undefined) effect = next.effectClass === "none" ? "none" : "unverified";
    } else if (state === "dispatching" && next.effectClass !== "none" && effect === undefined) {
      effect = "unknown";
    }
    if (state === "completed") {
      try { canonicalString(o.result); } catch (e) { throw new InvalidTransition(`${rec.id}: the result is not JSON-serialisable: ${(e as Error).message}`); }
      if (op.require?.effect === "verified" && effect !== "verified") {
        throw new InvalidTransition(`${rec.id}: the intent requires a verified effect; completed needs effect verified with measured evidence (BHMS-OPS-006)`);
      }
      op.result = o.result;
    }
    if (effect === "verified" && !provesEffect(o.evidence ?? op.evidence)) {
      throw new InvalidTransition(`${rec.id}: effect verified needs evidence of kind measured whose observations are all measured and valid (BHMS-OPS-006)`);
    }
    if (state === "failed" || state === "rejected" || state === "unknown") op.error = o.error;
    else delete op.error;
    const entry: Omit<HistoryEntry, "seq" | "at"> = { kind, state };
    if (effect !== undefined && effect !== op.effect) { op.effect = effect; entry.effect = effect; }
    if (cancel !== undefined && cancel !== op.cancel.state) { op.cancel = { ...op.cancel, state: cancel }; entry.cancel = cancel; }
    if (o.evidence !== undefined) op.evidence = o.evidence;
    if (o.detail || o.proof) entry.detail = (o.detail ?? o.proof ?? "").slice(0, 1000);
    if (o.operator !== undefined) entry.operator = { principal: o.operator.principal.slice(0, 128), basis: o.operator.basis.slice(0, 2000) };
    op.state = state;
    this.entry(rec, next, entry);
    const changed: ChangeKind[] = ["state"];
    if (entry.cancel) changed.push("cancel");
    if (entry.effect) changed.push("effect");
    this.commit(rec, next, o.strict ?? state === "dispatching");
    this.notify(rec, changed);
    if (state === "unknown") for (const h of this.onUnknown) h(rec);
    if (SETTLED.has(state)) for (const h of this.onSettled) h(rec);
  }

  /** Change `cancel.state`; a late change never touches a terminal `state` (BHMS-OPS-052). */
  setCancel(rec: OperationRecord, cancelState: CancelState, o: { reason?: string; detail?: string } = {}): void {
    if (rec.op.cancel.state === cancelState) return;
    const next = structuredClone(rec.data);
    const cancel: Operation["cancel"] = { state: cancelState };
    if (cancelState === "requested") {
      if (o.reason) cancel.reason = o.reason.slice(0, 500);
      cancel.requestedAt = iso(Date.now());
    } else {
      Object.assign(cancel, { ...next.op.cancel, state: cancelState });
    }
    next.op.cancel = cancel;
    const entry: Omit<HistoryEntry, "seq" | "at"> = { kind: "cancel", cancel: cancelState };
    if (o.detail) entry.detail = o.detail.slice(0, 1000);
    this.entry(rec, next, entry);
    this.commit(rec, next, false);
    this.notify(rec, ["cancel"]);
  }

  /** Change `effect` (and optionally `evidence`) of a non-terminal operation. */
  setEffect(rec: OperationRecord, effect: Effect, o: { detail?: string; evidence?: Operation["evidence"] } = {}): void {
    if (rec.terminal) throw new InvalidTransition(`${rec.id}: the effect of a terminal operation never changes; append a correction (BHMS-OPS-002)`);
    const next = structuredClone(rec.data);
    const entry: Omit<HistoryEntry, "seq" | "at"> = { kind: o.evidence !== undefined ? "evidence" : "effect" };
    const changed: ChangeKind[] = [];
    if (effect !== next.op.effect) { next.op.effect = effect; entry.effect = effect; changed.push("effect"); }
    if (o.evidence !== undefined) next.op.evidence = o.evidence;
    if (o.detail) entry.detail = o.detail.slice(0, 1000);
    this.entry(rec, next, entry);
    this.commit(rec, next, false);
    if (changed.length > 0) this.notify(rec, changed);
  }

  /** Append a non-state entry (`stop`, `lease`, `correction`, `evidence`) without changing state, result or effect. */
  annotate(rec: OperationRecord, kind: "stop" | "lease" | "correction" | "evidence" | "step", detail?: string, extra: { stepIndex?: number; childOperationId?: string } = {}): void {
    const next = structuredClone(rec.data);
    const entry: Omit<HistoryEntry, "seq" | "at"> = { kind };
    if (detail) entry.detail = detail.slice(0, 1000);
    if (extra.stepIndex !== undefined) entry.stepIndex = extra.stepIndex;
    if (extra.childOperationId !== undefined) entry.childOperationId = extra.childOperationId;
    this.entry(rec, next, entry);
    this.commit(rec, next, false);
  }

  /** Record the progress of a program (BHMS-PRG-015); not a history change, so no notification. */
  setProgress(rec: OperationRecord, progress: { stepsCompleted: number; stepsTotal: number }): void {
    const next = structuredClone(rec.data);
    next.op.progress = progress;
    next.op.updatedAt = iso(Date.now());
    this.commit(rec, next, false);
  }

  /** The child operations of a program, oldest first. */
  children(parentId: string): OperationRecord[] {
    return [...this.records.values()].filter((r) => r.op.parentOperationId === parentId)
      .sort((a, b) => (a.op.createdAt < b.op.createdAt ? -1 : a.op.createdAt > b.op.createdAt ? 1 : a.id < b.id ? -1 : 1));
  }

  /** Mark the inhibition of an `unknown` operation lifted (confirmed stop or reconciliation, BHMS-OPS-042). */
  liftInhibition(rec: OperationRecord): void {
    if (rec.data.inhibitionLifted) return;
    const next = structuredClone(rec.data);
    next.inhibitionLifted = true;
    this.commit(rec, next, false);
  }

  private notify(rec: OperationRecord, changed: ChangeKind[], wire?: Operation): void {
    if (this.unannounced.has(rec.id)) this.announce(rec); // a change after a failed sync: say accepted first
    for (const l of [...this.listeners]) {
      try { l(rec, changed, wire); } catch { /* a subscriber must not break the journal */ }
    }
    const w = [...rec.waiters];
    rec.waiters.clear();
    for (const f of w) f();
  }

  /** Wait until `rec` is settled, `ms` elapse or `signal` aborts (BHMS-OPS-060); never fails because time ran out. */
  async wait(rec: OperationRecord, ms: number, signal?: AbortSignal): Promise<OperationRecord> {
    if (rec.settled || ms <= 0 || signal?.aborted) return rec;
    await new Promise<void>((resolve) => {
      const done = (): void => { clearTimeout(t); rec.waiters.delete(check); signal?.removeEventListener("abort", done); resolve(); };
      const check = (): void => { if (rec.settled) done(); else rec.waiters.add(check); };
      const t = setTimeout(done, ms);
      rec.waiters.add(check);
      signal?.addEventListener("abort", done, { once: true });
    });
    return rec;
  }

  /** `operations/list` ordering (BHMS-LIF-062): `createdAt` descending, then `operationId` ascending; keyset cursor. */
  list(o: { principal?: string; limit: number; after?: string; deviceId?: string; state?: string; parentId?: string }): { page: Operation[]; cursor?: string } {
    const matches = [...this.records.values()]
      .filter((r) => (o.principal === undefined || r.principal === o.principal)
        && (o.deviceId === undefined || r.op.deviceId === o.deviceId)
        && (o.state === undefined || r.state === o.state)
        && (o.parentId === undefined || r.op.parentOperationId === o.parentId))
      .sort((a, b) => (a.op.createdAt < b.op.createdAt ? 1 : a.op.createdAt > b.op.createdAt ? -1 : a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    let start = 0;
    if (o.after !== undefined) {
      const m = /^op:(.+)\|(.+)$/.exec(o.after);
      if (!m) throw new BhmsError("INVALID_ARGUMENT", "malformed or foreign cursor", { field: "cursor", hint: "pass the nextCursor of a previous operations/list" });
      start = matches.findIndex((r) => r.op.createdAt < m[1] || (r.op.createdAt === m[1] && r.id > m[2]));
      if (start < 0) start = matches.length;
    }
    const slice = matches.slice(start, start + o.limit);
    const more = start + o.limit < matches.length;
    const last = slice[slice.length - 1];
    return { page: slice.map((r) => r.wire()), cursor: more && last ? `op:${last.op.createdAt}|${last.id}` : undefined };
  }

  /** Records that were mid-flight when the previous process ended. */
  inFlight(): OperationRecord[] {
    return [...this.records.values()].filter((r) => r.state === "dispatching" || r.state === "running");
  }
}
