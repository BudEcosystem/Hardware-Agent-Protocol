/**
 * Admission and execution of action operations (spec/bhms/06-operations.md §6.5-6.9, 04-devices.md BHMS-DEV-030).
 *
 * {@link Executor} turns an admitted request into physical work and records every outcome in the {@link Journal}:
 *
 * - **Key lookup first** (BHMS-OPS-033): after shape validation and authentication, `(principal, operationKey)` is looked
 *   up before the device, authorization, pin, arguments, lease or state are looked at; concurrent requests with the same
 *   key produce one operation (BHMS-OPS-032).
 * - **Admission** (§6.5 steps 3-10): resolve device/action (`UNKNOWN_DEVICE`, `UNKNOWN_ACTION`), authorize
 *   (`UNAUTHORIZED`), description pin (`STALE`), arguments and envelope (`INVALID_ARGUMENT`, `OUT_OF_RANGE`,
 *   `UNIT_MISMATCH`), `require` (`UNSUPPORTED`), lease (BHMS-LSE-010, BHMS-LSE-014), journal health and device reachability
 *   (`BUSY`, `DEVICE_UNAVAILABLE`), unresolved `unknown` operations on the same resources (`STALE` naming the operation,
 *   BHMS-OPS-042), `requiresFresh` (BHMS-OBS-030) and capacity (`BUSY`). Only then is the operation written.
 * - **Queueing**: operations whose resources are in use wait in `accepted`, FIFO per resource (they can be cancelled
 *   without effect, BHMS-OPS-050). A deadline that passes while queued rejects them (BHMS-OPS-070).
 * - **Dispatch**: time-dependent checks are repeated immediately before dispatch (BHMS-OPS-041; failure -> `rejected`,
 *   `effect: none`); `dispatching` is committed with fsync before the handler starts (BHMS-OPS-003); when that write fails
 *   nothing is dispatched.
 * - **Execution**: the handler runs as a task that no request owns, so a client disconnect never cancels it
 *   (BHMS-LIF-050). A return is `completed` (result validated against `output`, BHMS-OPS-008; `verified` only with measured
 *   evidence from `ctx.verify`, BHMS-OPS-006/007); {@link Canceled} is `canceled`; {@link DeviceFault} is `failed` with
 *   `DEVICE_FAULT`; anything else is `unknown` (BHMS-OPS-004).
 * - **Duration bounds** (BHMS-DEV-030, BHMS-OPS-071): at the earlier of `maxDurationMs` and the client deadline a cancellable
 *   action gets `ctx.cancelled` and a grace period, then ends `failed`/`DEADLINE_EXCEEDED`; without observed termination
 *   (or without cancel support) it becomes `unknown`, and a later handler return is recorded as a reconciliation to
 *   `failed`, never `completed`.
 * - **Lease loss** (BHMS-LSE-012) applies the action's `onLeaseLoss`. **Recovery** (BHMS-OPS-080) moves every operation found
 *   in `dispatching`/`running` to `unknown` before any request is answered, then asks the device's `reconcile` hook.
 *
 * Thread-safety: single event loop.
 */
import { randomBytes } from "node:crypto";
import { BhmsError } from "../errors.js";
import { digest } from "../canonical.js";
import type { ActionsInvokeParams, Observation, Operation } from "../generated/types.js";
import { Canceled, DeviceFault, type ActionContext, type Reconciled } from "./context.js";
import type { Device, ActionSpec } from "./device.js";
import { admitArguments, emptyEnvelopeMember } from "./validation.js";
import { emptyEnvelope, type Principal } from "./authority.js";
import type { DeviceServer } from "./server.js";
import { StoreError, type StoredOperation } from "./store.js";
import { InvalidTransition, OperationRecord, unknownError, type Effect, type TransitionOptions } from "./operations.js";
import type { Lease } from "./leases.js";
import { iso, mono, newId, sleep } from "./time.js";
import { checkResult } from "./results.js";
import { INVALID_RESOLUTION_HINT, recordOperatorResolution, type OperatorResolution } from "./resolution.js";

const INTENT_KEYS = ["deviceId", "action", "arguments", "deadlineMs", "require", "descriptionDigest"] as const;

/** `requestDigest` of an `actions/invoke` (§6.4): the intent with arguments exactly as sent, absent members omitted. */
export function intentDigest(params: Record<string, unknown>): string {
  const intent: Record<string, unknown> = { method: "actions/invoke" };
  for (const k of INTENT_KEYS) if (params[k] !== undefined && params[k] !== null) intent[k] = params[k];
  return digest(intent);
}

const srvMaxWait = (srv: DeviceServer): number => srv.opts.maxWaitMs;

interface Execution {
  rec: OperationRecord;
  device: Device;
  spec: ActionSpec;
  admitted: Record<string, unknown>;
  abort: AbortController;
  cancelReason?: string;
  deadlineHit: boolean;
  leaseLossFail: boolean;
  evidence: Record<string, Observation>;
  confirmed: boolean[];
  deadlineMono?: number;
  boundMono: number;
  timer?: NodeJS.Timeout;
  grace?: NodeJS.Timeout;
  done?: Promise<void>;
}

type Outcome = { kind: "return"; value: unknown } | { kind: "throw"; error: unknown };

export class Executor {
  private waiting: OperationRecord[] = [];
  private readonly queuedTimers = new Map<string, NodeJS.Timeout>();
  private readonly busy = new Map<string, string>();
  private readonly running = new Map<string, Execution>();
  private readonly reserving = new Map<string, Promise<void>>();
  private pumping = false;
  readonly tasks = new Set<Promise<void>>();

  constructor(private readonly server: DeviceServer, private readonly queueLimit: number, private readonly cancelGraceMs: number) {
    server.journal.onUnknown.push((rec) => { if (rec.op.kind === "action") this.server.events.append("operation.state", { severity: "warning", deviceId: rec.op.deviceId, operationId: rec.id, message: rec.op.error?.message, data: { state: "unknown", previousState: "running" } }); });
  }

  // ------------------------------------------------------------------------------------------------ invoke

  /** `actions/invoke` from key lookup to admission (§6.5). Returns the operation and whether it was replayed. */
  async invoke(principal: Principal, params: ActionsInvokeParams): Promise<{ rec: OperationRecord; replayed: boolean }> {
    const requestDigest = intentDigest(params as unknown as Record<string, unknown>);
    return this.keyed(principal, params.operationKey, requestDigest, params.waitMs, (key, origin) => this.admit(principal, params, key, origin, requestDigest));
  }

  /**
   * The idempotency envelope shared by `actions/invoke` and `programs/run` (BHMS-OPS-030..033): look up
   * `(principal, operationKey)` first, coalesce concurrent requests with one key, then (only when the key is new) check the
   * `waitMs` range and create the operation with `create`.
   */
  async keyed(
    principal: Principal, key: string | undefined, requestDigest: string, waitMs: number | undefined,
    create: (key: string, origin: "client" | "server") => Promise<OperationRecord>,
  ): Promise<{ rec: OperationRecord; replayed: boolean }> {
    const journal = this.server.journal;
    if (key !== undefined && key.startsWith("g-") && !principal.gateway) {
      throw new BhmsError("INVALID_ARGUMENT", "operationKey prefix g- is reserved for gateways", {
        field: "operationKey", hint: "use a key that does not start with d- or g- (BHMS-OPS-037)",
      });
    }
    const lock = key === undefined ? undefined : `${principal.id}\0${key}`;
    if (key !== undefined) {
      for (;;) {
        const existing = journal.byKey(principal.id, key);
        if (existing) return { rec: existing, replayed: this.sameIntent(existing, requestDigest, key) };
        const pending = this.reserving.get(lock!);
        if (!pending) break;
        await pending; // a concurrent first request with this key: then answer from its record (BHMS-OPS-032)
      }
    }
    if (waitMs !== undefined && waitMs > srvMaxWait(this.server)) {
      throw new BhmsError("OUT_OF_RANGE", `waitMs ${waitMs} is above the maximum ${srvMaxWait(this.server)}`, {
        field: "waitMs", bound: { maximum: srvMaxWait(this.server) }, hint: `use waitMs of at most ${srvMaxWait(this.server)}`,
      });
    }
    let release: () => void = () => undefined;
    if (lock !== undefined) this.reserving.set(lock, new Promise<void>((r) => { release = r; }));
    try {
      const rec = await create(key ?? `s-${randomBytes(12).toString("hex")}`, key === undefined ? "server" : "client");
      return { rec, replayed: false };
    } finally {
      if (lock !== undefined) this.reserving.delete(lock);
      release();
    }
  }

  private sameIntent(rec: OperationRecord, requestDigest: string, key: string): true {
    if (rec.op.requestDigest === requestDigest) return true;
    const mayHaveActed = rec.op.error?.mayHaveActed ?? rec.dispatched;
    throw new BhmsError("KEY_CONFLICT", `operationKey ${JSON.stringify(key)} was used for a different request`, {
      field: "operationKey", operationId: rec.id, mayHaveActed, hint: "use a new operationKey for a different intent, or repeat the original request exactly",
    });
  }

  /**
   * Admission steps 3-10 (§6.5) for one action. `extra` is used by programs: a child operation names its parent and carries
   * the program's absolute deadline, with `origin: "derived"` and the derived key (BHMS-PRG-010).
   */
  async admit(
    principal: Principal, p: ActionsInvokeParams, key: string, origin: "client" | "server" | "derived", requestDigest: string,
    extra: { parentId?: string; deadlineAtMs?: number } = {},
  ): Promise<OperationRecord> {
    const srv = this.server;
    const device = srv.visibleDevice(principal, p.deviceId);
    const spec = device.actions.get(p.action);
    if (!spec) {
      throw new BhmsError("UNKNOWN_ACTION", `${p.deviceId} has no action ${JSON.stringify(p.action)}`, { field: "action", bound: [...device.actions.keys()].sort(), hint: `the actions are: ${[...device.actions.keys()].sort().join(", ") || "(none)"}` });
    }
    if (!principal.canInvoke(device.deviceId, spec.name, device.capabilities, spec.effect)) {
      throw new BhmsError("UNAUTHORIZED", `the principal may not invoke ${p.deviceId}/${p.action}`, { field: "action", hint: `missing scope invoke:${p.deviceId}/${p.action}` });
    }
    const description = device.description();
    if (p.descriptionDigest !== undefined && p.descriptionDigest !== description.digest) {
      throw new BhmsError("STALE", `${p.deviceId}'s description changed`, { field: "descriptionDigest", bound: description.digest, hint: "describe the device again and replan against the new description" });
    }
    const policyBounds = principal.boundsFor(device.deviceId, spec.name);
    if (policyBounds) {
      const empty = emptyEnvelopeMember(spec.input, policyBounds);
      if (empty !== undefined) throw emptyEnvelope(device.deviceId, spec.name, empty, `arguments.${empty}`);
    }
    const { admitted, differs } = admitArguments(spec.input, p.arguments, "arguments", policyBounds);
    if (p.require?.effect === "verified" && spec.completionEvidence !== "measured") {
      throw new BhmsError("UNSUPPORTED", `${p.action} cannot be verified: its completionEvidence is ${spec.completionEvidence}`, { field: "require", hint: "drop require, or use an action whose completionEvidence is measured (BHMS-OPS-007)" });
    }
    const lease = srv.leases.admit(principal.id, p.leaseId, spec.resources, spec.requiresLease); // BHMS-LSE-010, BHMS-LSE-014
    srv.requireJournal();
    if (device.status === "offline") {
      throw new BhmsError("DEVICE_UNAVAILABLE", `${p.deviceId} is offline`, { hint: "retry later with the same operationKey" });
    }
    this.assertNotInhibited(spec.resources);
    if (spec.requiresFresh.length > 0) await srv.observations.requireFresh(device, spec.requiresFresh, principal);
    if (this.waiting.filter((r) => r.op.deviceId === device.deviceId).length >= this.queueLimit) {
      throw new BhmsError("BUSY", `${p.deviceId} has ${this.queueLimit} operations queued`, { hint: "retry later with the same operationKey" });
    }
    const now = Date.now();
    const op: Operation = {
      operationId: newId("op"), operationKey: key, keyOrigin: origin, kind: "action", deviceId: p.deviceId, action: p.action,
      arguments: p.arguments, requestDigest, state: "accepted", cancel: { state: "none" }, effect: "none",
      createdAt: iso(now), updatedAt: iso(now),
    };
    if (differs) op.admittedArguments = admitted;
    if (p.require) op.require = p.require;
    if (lease) { op.leaseId = lease.leaseId; op.fence = lease.fence; }
    const bounds: StoredOperation = {
      id: op.operationId, principal: principal.id, op, history: [], resources: [...spec.resources], effectClass: spec.effect,
      cancelSupported: spec.cancel === "supported", onLeaseLoss: spec.onLeaseLoss ?? "finish", completionEvidence: spec.completionEvidence,
      maxDurationMs: spec.maxDurationMs, admitted,
    };
    if (extra.parentId !== undefined) op.parentOperationId = extra.parentId;
    const deadlineAt = p.deadlineMs !== undefined ? now + p.deadlineMs : extra.deadlineAtMs;
    if (deadlineAt !== undefined) {
      bounds.deadlineMs = deadlineAt;
      op.deadlineAt = iso(deadlineAt);
    }
    let rec: OperationRecord;
    try {
      rec = srv.journal.create(bounds); // the intent is durable before anything is dispatched (BHMS-OPS-003)
    } catch (e) {
      if (e instanceof StoreError) { srv.journalFailed(e); throw srv.journalBusy(); }
      throw e;
    }
    this.enqueue(rec);
    return rec;
  }

  private assertNotInhibited(resources: readonly string[], except?: string): void {
    const set = new Set(resources);
    for (const rec of this.server.journal.records.values()) {
      if (rec.state === "unknown" && rec.op.kind === "action" && rec.id !== except && rec.data.effectClass !== "none" && !rec.data.inhibitionLifted && rec.data.resources.some((r) => set.has(r))) {
        throw new BhmsError("STALE", `operation ${rec.id} is unknown and uses the same resources`, {
          field: "operationId", operationId: rec.id, hint: `reconcile ${rec.id} with operations/get, or stop the device, before starting new work (BHMS-OPS-042)`,
        });
      }
    }
  }

  // ------------------------------------------------------------------------------------------------ queue and dispatch

  private enqueue(rec: OperationRecord): void {
    this.waiting.push(rec);
    if (rec.data.deadlineMs !== undefined) {
      const t = setTimeout(() => this.rejectQueued(rec, new BhmsError("DEADLINE_EXCEEDED", "the deadline passed before the operation could be dispatched", { hint: "retry with a later deadline or when the device is free" })), Math.max(0, rec.data.deadlineMs - Date.now()));
      t.unref();
      this.queuedTimers.set(rec.id, t);
    }
    this.pump();
  }

  private dequeue(rec: OperationRecord): void {
    this.waiting = this.waiting.filter((r) => r !== rec);
    const t = this.queuedTimers.get(rec.id);
    if (t) { clearTimeout(t); this.queuedTimers.delete(rec.id); }
  }

  private rejectQueued(rec: OperationRecord, e: BhmsError): void {
    if (rec.state !== "accepted") return;
    this.dequeue(rec);
    this.reject(rec, e);
    this.pump();
  }

  private reject(rec: OperationRecord, e: BhmsError): void {
    const clean = new BhmsError(e.bhmsCode, e.message, { field: e.field, bound: e.bound, operationId: e.operationId, retry: e.retry, hint: e.hint, mayHaveActed: false });
    this.server.journal.transition(rec, "rejected", { error: clean.toOperationError(), detail: e.message });
  }

  /** Start every queued operation whose resources are free, in FIFO order per resource. */
  pump(): void {
    if (this.pumping || this.server.closing) return;
    this.pumping = true;
    try {
      const reserved = new Set<string>();
      for (const rec of [...this.waiting]) {
        if (rec.state !== "accepted") { this.dequeue(rec); continue; }
        const res = rec.data.resources;
        if (res.some((r) => this.busy.has(r) || reserved.has(r))) { for (const r of res) reserved.add(r); continue; }
        this.dequeue(rec);
        for (const r of res) this.busy.set(r, rec.id);
        const task = this.dispatch(rec).catch((e: unknown) => { this.server.log(`dispatch of ${rec.id} failed: ${String(e)}`); });
        this.tasks.add(task);
        void task.finally(() => this.tasks.delete(task));
      }
    } finally {
      this.pumping = false;
    }
  }

  private release(rec: OperationRecord): void {
    for (const r of rec.data.resources) if (this.busy.get(r) === rec.id) this.busy.delete(r);
  }

  private async dispatch(rec: OperationRecord): Promise<void> {
    const srv = this.server;
    const device = srv.devices.get(rec.op.deviceId!);
    const spec = device?.actions.get(rec.op.action!);
    try {
      if (!device || !spec) throw new BhmsError("UNKNOWN_ACTION", `${rec.op.deviceId}/${rec.op.action} is no longer available`, { hint: "describe the device again" });
      // BHMS-OPS-041: everything that depends on time is checked again immediately before dispatch.
      if (rec.data.deadlineMs !== undefined && Date.now() >= rec.data.deadlineMs) {
        throw new BhmsError("DEADLINE_EXCEEDED", "the deadline passed before the operation could be dispatched", { hint: "retry with a later deadline" });
      }
      srv.leases.admit(rec.principal, rec.op.leaseId, spec.resources, spec.requiresLease); // a lease taken while it queued refuses it
      if (device.status === "offline") throw new BhmsError("DEVICE_UNAVAILABLE", `${device.deviceId} is offline`, { hint: "retry later" });
      this.assertNotInhibited(spec.resources, rec.id);
      if (spec.requiresFresh.length > 0) await srv.observations.requireFresh(device, spec.requiresFresh, undefined);
      if (rec.state !== "accepted") { this.release(rec); this.pump(); return; } // cancelled while checking
      if (rec.data.deadlineMs !== undefined && Date.now() >= rec.data.deadlineMs) {
        throw new BhmsError("DEADLINE_EXCEEDED", "the deadline passed before the operation could be dispatched", { hint: "retry with a later deadline" });
      }
    } catch (e) {
      if (e instanceof BhmsError) {
        if (rec.state === "accepted") this.reject(rec, e);
        this.release(rec);
        this.pump();
        return;
      }
      throw e;
    }
    try {
      srv.journal.transition(rec, "dispatching", { strict: true }); // durable before the command can reach the device
    } catch (e) {
      if (e instanceof StoreError) {
        srv.journalFailed(e);
        this.reject(rec, new BhmsError("INTERNAL", "the dispatch record could not be written, so nothing was sent", { hint: "retry with the same operationKey when the journal is writable" }));
        this.release(rec);
        this.pump();
        return;
      }
      throw e;
    }
    this.start(rec, device!, spec!);
  }

  // ------------------------------------------------------------------------------------------------ execution

  private start(rec: OperationRecord, device: Device, spec: ActionSpec): void {
    const now = mono();
    const remaining = rec.data.deadlineMs !== undefined ? Math.max(0, rec.data.deadlineMs - Date.now()) : Infinity;
    const bound = Math.min(spec.maxDurationMs, remaining);
    const exec: Execution = {
      rec, device, spec, admitted: rec.data.admitted, abort: new AbortController(), deadlineHit: false, leaseLossFail: false,
      evidence: {}, confirmed: [], boundMono: now + bound, deadlineMono: Number.isFinite(remaining) ? now + remaining : undefined,
    };
    this.running.set(rec.id, exec);
    exec.timer = setTimeout(() => this.onBound(exec), bound);
    exec.done = this.execute(exec).catch((e: unknown) => { this.server.log(`execution of ${rec.id} failed: ${String(e)}`); });
    this.tasks.add(exec.done);
    void exec.done.finally(() => this.tasks.delete(exec.done!));
  }

  private onBound(exec: Execution): void {
    const rec = exec.rec;
    if (rec.terminal) return;
    exec.deadlineHit = true;
    exec.cancelReason = "duration bound exceeded";
    exec.abort.abort();
    if (rec.data.cancelSupported) {
      this.server.journal.setCancel(rec, "requested", { reason: "duration bound exceeded" });
      exec.grace = setTimeout(() => this.markUnknown(exec, "the duration bound passed and termination was not observed"), this.cancelGraceMs);
    } else {
      this.markUnknown(exec, "the duration bound passed and the action cannot be cancelled");
    }
  }

  private markUnknown(exec: Execution, message: string): void {
    const rec = exec.rec;
    if (rec.state !== "dispatching" && rec.state !== "running") return;
    this.server.journal.transition(rec, "unknown", { error: unknownError(message), detail: message });
  }

  private async execute(exec: Execution): Promise<void> {
    let outcome: Outcome;
    try {
      const ctx = this.contextFor(exec);
      const value = await exec.spec.handler(ctx, structuredClone(exec.admitted));
      outcome = { kind: "return", value };
    } catch (error) {
      outcome = { kind: "throw", error };
    }
    if (exec.timer) clearTimeout(exec.timer);
    if (exec.grace) clearTimeout(exec.grace);
    try {
      this.settle(exec, outcome);
    } finally {
      this.running.delete(exec.rec.id);
      this.release(exec.rec);
      if (exec.spec.effect !== "none") this.server.observations.afterSettled(exec.device);
      this.pump();
    }
  }

  private contextFor(exec: Execution): ActionContext {
    const { rec, device } = exec;
    const srv = this.server;
    const markRunning = (detail?: string): void => {
      if (rec.state === "dispatching") srv.journal.transition(rec, "running", { detail });
    };
    return {
      operationId: rec.id, deviceId: device.deviceId, action: exec.spec.name,
      cancelled: exec.abort.signal,
      get cancelReason() { return exec.cancelReason; },
      get remainingMs() { return Math.max(0, Math.min(exec.boundMono, exec.deadlineMono ?? Infinity) - mono()); },
      running: async (detail) => { markRunning(detail); },
      waitCancelled: async (ms) => { markRunning(); await sleep(ms, exec.abort.signal); return exec.abort.signal.aborted; },
      verify: async (property, check) => {
        markRunning();
        const spec = device.properties.get(property);
        let obs: Observation;
        try {
          obs = await srv.observations.read(device, property, { fresh: true, internal: true });
        } catch {
          exec.confirmed.push(false);
          return null;
        }
        const ok = spec?.evidence === "measured" && obs.quality === "valid" && check(obs.value);
        exec.evidence[property] = obs;
        exec.confirmed.push(ok);
        return obs.quality === "valid" ? obs.value : null;
      },
      read: async (property) => { markRunning(); return srv.observations.read(device, property, { internal: true }); },
      publish: (property, value, options) => device.publish(property, value, options),
      emit: (type, data, options) => { device.emit(type, data, { ...options, operationId: rec.id }); },
    };
  }

  private fail(exec: Execution, code: ConstructorParameters<typeof BhmsError>[0], message: string, o: { effect: Effect; hint: string; mayHaveActed?: boolean; proof?: string }): void {
    const err = new BhmsError(code, message, { mayHaveActed: o.mayHaveActed ?? true, hint: o.hint });
    this.apply(exec, "failed", { error: err.toOperationError(), effect: o.effect, detail: message, proof: o.proof });
  }

  /** Apply a terminal outcome; a late outcome of an `unknown` operation is a reconciliation (BHMS-OPS-005). */
  private apply(exec: Execution, state: "completed" | "failed" | "canceled", o: TransitionOptions = {}): void {
    const rec = exec.rec;
    if (rec.terminal) return;
    if (rec.state === "unknown") {
      this.server.journal.transition(rec, state, { ...o, kind: "reconciliation", detail: `the handler finished after the operation was marked unknown: ${o.detail ?? state}` });
      this.server.journal.liftInhibition(rec);
    } else {
      this.server.journal.transition(rec, state, o);
    }
  }

  private settle(exec: Execution, outcome: Outcome): void {
    const { rec, spec, device } = exec;
    const srv = this.server;
    if (rec.terminal) return;
    if (outcome.kind === "throw") {
      const e = outcome.error;
      if (e instanceof Canceled) {
        if (exec.leaseLossFail) {
          this.fail(exec, "LEASE_EXPIRED", "the lease ended while the action ran and the device was held", { effect: e.effect, hint: "reacquire the lease, check the device state, then retry" });
        } else if (exec.deadlineHit) {
          this.fail(exec, "DEADLINE_EXCEEDED", `the action did not finish within its ${spec.maxDurationMs} ms bound or deadline and was cancelled`, { effect: e.effect, hint: "read the device state before retrying" });
        } else {
          this.apply(exec, "canceled", { effect: e.effect, detail: e.detail ?? "canceled" });
        }
        return;
      }
      if (e instanceof DeviceFault) {
        const proven = e.proof !== undefined;
        device.emit("device.fault", { code: "DEVICE_FAULT" }, { severity: "error", message: e.message, operationId: rec.id });
        this.fail(exec, "DEVICE_FAULT", e.message, {
          effect: proven ? "none" : "unknown", mayHaveActed: !proven, proof: e.proof,
          hint: e.partial ? `${e.partial}; inspect the device before acting again` : "inspect the device before acting again",
        });
        return;
      }
      srv.log(`action ${device.deviceId}/${spec.name} (${rec.id}) raised an unexpected error: ${e instanceof Error ? e.stack ?? e.message : String(e)}`);
      if (rec.state === "dispatching" || rec.state === "running") {
        this.markUnknown(exec, "the action handler failed unexpectedly after the command may have reached the device");
      }
      return;
    }
    if (exec.deadlineHit) {
      this.fail(exec, "DEADLINE_EXCEEDED", `the action ran past its ${spec.maxDurationMs} ms bound or deadline`, { effect: "unknown", hint: "read the device state before retrying" });
      return;
    }
    let result = outcome.value;
    if (result === undefined || result === null) result = {};
    const defect = checkResult(result, spec.output !== undefined ? device.validator(`output:${spec.name}`, spec.output) : undefined);
    if (defect?.kind === "out-of-range") {
      // the device acted and reported a value: a measurement outside its declared range, not a result that "cannot be
      // recorded" (BHMS-OPS-008); the value is kept in the message and in an evidence entry
      const { effect, evidence } = this.completionEffect(exec);
      const err = new BhmsError("OUT_OF_RANGE", `${spec.name} acted and returned ${defect.member} = ${JSON.stringify(defect.instance)}, outside its declared output range (${defect.keyword} ${JSON.stringify(defect.bound![defect.keyword!])})`, {
        field: defect.member, bound: defect.bound, mayHaveActed: true, retry: "after-reconcile",
        hint: `the device acted; the returned value is in this message and in the operation's history. Read ${device.deviceId}'s state before deciding what to do; the declared range may be too narrow for the instrument's tolerance`,
      });
      srv.journal.annotate(rec, "evidence", `result as returned (not recorded as result: ${defect.member} is outside the declared output range): ${JSON.stringify(result)}`);
      this.apply(exec, "failed", { error: err.toOperationError(), effect, evidence, detail: err.message });
      return;
    }
    if (defect) {
      this.fail(exec, "INTERNAL", `${spec.name} returned a result that cannot be recorded: ${defect.message}`, {
        effect: "unknown", hint: "the device acted but the server cannot report a valid result; read the device state",
      });
      return;
    }
    const { effect, evidence } = this.completionEffect(exec);
    if (rec.op.require?.effect === "verified" && effect !== "verified") {
      this.fail(exec, "UNVERIFIED", `${spec.name} finished but its effect could not be verified by measurement`, {
        effect: "unverified", hint: "inspect the device before acting again; the effect may have happened",
      });
      return;
    }
    this.apply(exec, "completed", { result, hasResult: true, effect, evidence, detail: "completed" });
    device.reportAlive(); // a completed action is evidence that the device answers (BHMS-DEV-012)
  }

  /** The `effect` and `evidence` of a handler that returned (BHMS-OPS-006): `verified` only when every `ctx.verify` agreed. */
  private completionEffect(exec: Execution): { effect: Effect; evidence?: Operation["evidence"] } {
    if (exec.spec.effect === "none") return { effect: "none" };
    const observed = Object.keys(exec.evidence).length > 0;
    if (observed && exec.confirmed.length > 0 && exec.confirmed.every(Boolean)) {
      return { effect: "verified", evidence: { kind: "measured", observations: { ...exec.evidence } } };
    }
    if (observed) return { effect: "unverified", evidence: { kind: "measured", observations: { ...exec.evidence } } };
    return { effect: "unverified", evidence: exec.spec.completionEvidence === "none" ? undefined : { kind: "reported" } };
  }

  // ------------------------------------------------------------------------------------------------ cancel, stop, leases

  /** `operations/cancel` semantics (§6.6); authorization is the caller's. */
  cancel(rec: OperationRecord, reason: string | undefined): void {
    const j = this.server.journal;
    if (rec.terminal) return; // BHMS-OPS-053: returned unchanged
    if (rec.state === "accepted") {
      this.dequeue(rec);
      j.setCancel(rec, "requested", { reason });
      j.transition(rec, "canceled", { detail: "canceled before dispatch" });
      this.pump();
      return;
    }
    if (!rec.data.cancelSupported) {
      j.setCancel(rec, "refused", { detail: "the action does not support cancellation" });
      return;
    }
    j.setCancel(rec, "requested", { reason });
    const exec = this.running.get(rec.id);
    if (exec) {
      exec.cancelReason = reason;
      exec.abort.abort();
    }
  }

  /** Stop, step 2: move this device's `accepted` operations to `canceled` (no effect); returns their ids. */
  cancelAccepted(deviceId: string, reason: string): string[] {
    const ids: string[] = [];
    for (const rec of [...this.waiting]) {
      if (rec.op.deviceId !== deviceId || rec.state !== "accepted") continue;
      this.dequeue(rec);
      this.server.journal.annotate(rec, "stop", `stop: ${reason}`);
      this.server.journal.setCancel(rec, "requested", { reason });
      this.server.journal.transition(rec, "canceled", { detail: `canceled by stop: ${reason}` });
      ids.push(rec.id);
    }
    this.pump();
    return ids;
  }

  /** Stop, step 3: record a stop entry and request cancellation on `dispatching`/`running`/`unknown` operations. */
  requestCancelOn(deviceId: string, reason: string): string[] {
    const ids: string[] = [];
    for (const rec of this.server.journal.records.values()) {
      if (rec.op.deviceId !== deviceId || !(rec.state === "dispatching" || rec.state === "running" || rec.state === "unknown")) continue;
      this.server.journal.annotate(rec, "stop", `stop requested: ${reason}`);
      if (rec.data.cancelSupported) {
        this.server.journal.setCancel(rec, "requested", { reason });
        const exec = this.running.get(rec.id);
        if (exec) { exec.cancelReason = reason; exec.abort.abort(); }
      }
      ids.push(rec.id);
    }
    return ids;
  }

  /** A confirmed stop lifts the unknown-operation inhibition of the device's operations (BHMS-OPS-042). */
  confirmStop(deviceId: string): void {
    for (const rec of this.server.journal.records.values()) {
      if (rec.state === "unknown" && rec.op.deviceId === deviceId) this.server.journal.liftInhibition(rec);
    }
  }

  /** BHMS-LSE-012: apply `onLeaseLoss` to operations admitted under the ended lease. */
  onLeaseEnded(lease: Lease, reason: "expired" | "revoked"): void {
    for (const exec of [...this.running.values()]) {
      const rec = exec.rec;
      if (rec.op.leaseId !== lease.leaseId || rec.terminal) continue;
      const policy = rec.data.onLeaseLoss;
      this.server.journal.annotate(rec, "lease", `lease ${lease.leaseId} ${reason}; onLeaseLoss=${policy}`);
      if (policy === "finish") continue;
      if (policy === "hold") {
        exec.leaseLossFail = true;
        void Promise.resolve().then(() => exec.device.holdHandler?.()).catch((e: unknown) => this.server.log(`hold handler failed: ${String(e)}`));
      }
      if (rec.data.cancelSupported || policy === "hold") {
        this.server.journal.setCancel(rec, "requested", { reason: `lease ${reason}` });
        exec.cancelReason = `lease ${reason}`;
        exec.abort.abort();
      }
    }
  }

  // ------------------------------------------------------------------------------------------------ recovery

  /** BHMS-OPS-080: operations found in flight after a restart become `unknown`; then reconcile where the device can. */
  async recover(): Promise<void> {
    const j = this.server.journal;
    for (const rec of j.inFlight()) {
      if (rec.op.kind !== "action") continue;
      j.transition(rec, "unknown", { error: unknownError("the server restarted while the operation was in flight (BHMS-OPS-080)"), detail: "server restart" });
    }
    // A child of a program is never dispatched after a restart: programs are not resumed (BHMS-PRG-017).
    for (const rec of [...j.records.values()]) {
      if (rec.state === "accepted" && rec.op.kind === "action" && rec.op.parentOperationId !== undefined) {
        this.reject(rec, new BhmsError("INTERNAL", "the server restarted before this program step was dispatched; nothing was sent to the device", { hint: "programs are never resumed; run the program again" }));
      }
    }
    await this.reconcileAll();
    this.server.programs?.recoverAfterRestart();
  }

  /** Resume `accepted` operations that survived a restart (their time-dependent checks run again before dispatch). */
  resume(): void {
    for (const rec of this.server.journal.records.values()) {
      if (rec.state === "accepted" && rec.op.kind === "action") this.enqueue(rec);
    }
  }

  async reconcileAll(): Promise<void> {
    for (const rec of [...this.server.journal.records.values()]) {
      if (rec.state === "unknown" && rec.op.kind === "action") await this.reconcileOne(rec);
    }
  }

  /** Ask `device`'s reconcile hook about each of its `unknown` operations (a return to `online`, BHMS-OPS-082); the changed ones. */
  async reconcileDevice(device: Device): Promise<OperationRecord[]> {
    const changed: OperationRecord[] = [];
    if (!device.reconcileHandler) return changed;
    for (const rec of [...this.server.journal.records.values()]) {
      if (rec.state === "unknown" && rec.op.kind === "action" && rec.op.deviceId === device.deviceId && await this.reconcileOne(rec)) changed.push(rec);
    }
    return changed;
  }

  /**
   * Ask the device's `reconcile` hook about one `unknown` operation and record what its evidence proves (BHMS-OPS-005); true when
   * an answer was recorded. The call is bounded by the server's `reconcileTimeoutS`; no answer, `undefined`, a failing hook or an
   * answer the journal refuses (a result that fails {@link checkResult}, a transition its rules forbid) leaves it `unknown`:
   * success is never assumed.
   */
  async reconcileOne(rec: OperationRecord): Promise<boolean> {
    const srv = this.server;
    const device = srv.devices.get(rec.op.deviceId ?? "");
    if (!device?.reconcileHandler || rec.state !== "unknown" || this.running.has(rec.id)) return false;
    const bound = srv.opts.reconcileTimeoutS * 1000;
    let answer: Reconciled | undefined;
    let timer: NodeJS.Timeout | undefined;
    try {
      const noAnswer = new Promise<"timeout">((resolve) => { timer = setTimeout(() => resolve("timeout"), bound); timer.unref(); });
      const got = await Promise.race([Promise.resolve(device.reconcileHandler(rec.wire(true))), noAnswer]);
      if (got === "timeout") {
        srv.log(`reconcile of ${rec.id} by ${device.deviceId} got no answer in ${srv.opts.reconcileTimeoutS} s; it stays unknown`);
        return false;
      }
      answer = got;
    } catch (e) {
      srv.log(`reconcile hook of ${device.deviceId} failed for ${rec.id}: ${String(e)}; it stays unknown`);
      return false;
    } finally {
      if (timer) clearTimeout(timer);
    }
    if (!answer || rec.state !== "unknown" || srv.closing) return false; // the device cannot say, or it settled meanwhile
    try {
      this.applyReconciliation(rec, device, answer);
    } catch (e) {
      if (!(e instanceof InvalidTransition)) throw e;
      srv.log(`reconcile answer of ${device.deviceId} for ${rec.id} was refused (${e.message}); it stays unknown`);
      return false;
    }
    this.afterResolved(rec, "device");
    return true;
  }

  /** Record a {@link Reconciled} answer (device evidence); the journal's invariants apply as to any completion. */
  private applyReconciliation(rec: OperationRecord, device: Device, answer: Reconciled): void {
    const j = this.server.journal;
    const detail = answer.evidence;
    if (answer.state === "completed") {
      const result = answer.result ?? {};
      const spec = device.actions.get(rec.op.action ?? "");
      const defect = checkResult(result, spec?.output !== undefined ? device.validator(`output:${spec.name}`, spec.output) : undefined);
      if (defect) throw new InvalidTransition(`the reconciled result of ${rec.id} cannot be recorded: ${defect.message}`);
      const effect: Effect = answer.effect ?? (rec.data.effectClass === "none" ? "none" : "unverified");
      j.transition(rec, "completed", { kind: "reconciliation", detail, result, hasResult: true, effect, evidence: effect === "verified" ? rec.op.evidence : undefined });
    } else if (answer.state === "canceled") {
      j.transition(rec, "canceled", { kind: "reconciliation", detail, effect: answer.effect });
    } else {
      const mayHaveActed = answer.mayHaveActed ?? true;
      const err = mayHaveActed
        ? new BhmsError("DEVICE_FAULT", answer.message ?? "the command was interrupted", { mayHaveActed: true, hint: "inspect the device before acting again; a partial effect is possible" })
        : new BhmsError("DEVICE_UNAVAILABLE", answer.message ?? "the command never reached the device", { mayHaveActed: false, hint: "the device has no record of it; retry with a new operationKey if the intent still stands" });
      j.transition(rec, "failed", { kind: "reconciliation", detail, error: err.toOperationError(), effect: answer.effect ?? (mayHaveActed ? "unknown" : "none"), proof: mayHaveActed ? undefined : detail });
    }
  }

  /**
   * Record an operator's resolution of the `unknown` operation `rec` (`operations/resolve`, BHMS-OPS-102); the rules are those
   * of {@link recordOperatorResolution}. A resolution the journal cannot record is `INVALID_ARGUMENT` naming `resolution`.
   */
  resolveByOperator(rec: OperationRecord, principal: string, resolution: OperatorResolution): void {
    const device = this.server.devices.get(rec.op.deviceId ?? "");
    const spec = device?.actions.get(rec.op.action ?? "");
    const validator = device && spec?.output !== undefined ? device.validator(`output:${spec.name}`, spec.output) : undefined;
    try {
      recordOperatorResolution(this.server.journal, rec, resolution, principal, validator);
    } catch (e) {
      if (!(e instanceof InvalidTransition)) throw e;
      throw new BhmsError("INVALID_ARGUMENT", `the resolution cannot be recorded: ${e.message}`.slice(0, 2000), { field: "resolution", hint: INVALID_RESOLUTION_HINT });
    }
    this.afterResolved(rec, "operator", principal);
  }

  /**
   * After an `unknown` operation was resolved: lift its inhibition (BHMS-OPS-042), let its program settle, and record the
   * resolution as an `operation.resolved` event, the audit trail of every resolution (BHMS-OPS-102).
   */
  private afterResolved(rec: OperationRecord, source: "device" | "operator", principal?: string): void {
    const srv = this.server;
    srv.journal.liftInhibition(rec);
    if (rec.op.parentOperationId !== undefined) srv.programs?.settleAfterReconcile(rec.op.parentOperationId);
    srv.events.append("operation.resolved", {
      severity: source === "operator" ? "warning" : "info", deviceId: rec.op.deviceId, operationId: rec.id,
      data: { state: rec.state, source, ...(principal !== undefined ? { principal } : {}) },
      message: `${rec.id} left unknown: ${rec.state} (resolved by ${source})`,
    });
  }

  /** Wait for every started handler to finish (used by tests and graceful shutdown). */
  async idle(timeoutMs: number): Promise<void> {
    if (this.tasks.size === 0) return;
    await Promise.race([Promise.allSettled([...this.tasks]), sleep(timeoutMs)]);
  }

  get runningCount(): number { return this.running.size; }
  get queuedCount(): number { return this.waiting.length; }
}
