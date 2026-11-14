/**
 * A device on a {@link DeviceServer}: builder methods, description, digest and summary.
 *
 * A {@link Device} collects properties, actions, device events and safety hooks declared with plain method calls (no
 * decorators) and builds its `DeviceDescription` (spec/bhms/04-devices.md §4.3): checked for units (BHMS-DEV-041), with
 * `digest = "sha256:" + hex(sha256(JCS(description without digest)))` (BHMS-DEV-021). The description is cached and
 * immutable for its digest (BHMS-DEV-020); any later declaration change produces a new digest and a
 * `notifications/devices/listChanged` (BHMS-DEV-023).
 *
 * ```ts
 * const stage = srv.device("stage-z", { capabilities: ["bhms.axis.linear"], resources: ["stage-z"] });
 * stage.property("position", { unit: "um", evidence: "measured" }, () => encoder.read());
 * stage.action("move_to", {
 *   effect: "reversible", idempotency: "absolute", maxDurationMs: 5000, cancel: "supported",
 *   completionEvidence: "measured", verifiedBy: ["position"],
 *   input: { target: range(0, 200, "um") }, output: { position: "um" },
 * }, async (ctx, { target }) => {
 *   await motor.move(target as number, ctx.cancelled);
 *   return { position: await ctx.verify("position", (v) => Math.abs((v as number) - (target as number)) < 0.5) };
 * });
 * stage.onStop({ evidence: "reported" }, async () => { await motor.halt(); });
 * ```
 *
 * Hooks: `onStop` (the commissioned stop procedure, BHMS-AUTH-021), `onHold` (`onLeaseLoss: "hold"`, BHMS-LSE-012),
 * `reconcile` (resolve an `unknown` operation from device evidence, BHMS-OPS-005; asked again whenever the device returns,
 * BHMS-OPS-082) and `liveness` (reachability evidence for `status`, optionally probed periodically, BHMS-DEV-012).
 *
 * Thread-safety: declare everything before serving; runtime methods run on the server's event loop.
 */
import { descriptionDigest, canonical } from "../canonical.js";
import type { DeviceDescription, DeviceSummary, Event, Observation } from "../generated/types.js";
import type { ActionContext, Reading, Reconciled } from "./context.js";
import { asObjectSchema, num, type Schema } from "./schemas.js";
import { checkUnits } from "./validation.js";
import { mono } from "./time.js";
import { SchemaValidator } from "../schema.js";
import type { DeviceServer } from "./server.js";

const DEVICE_ID = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/;
const NAME = /^[a-z][a-z0-9_]{0,63}$/;
const CORE_EVENT_TYPES = new Set(["device.online", "device.offline", "device.degraded", "device.replaced", "device.epoch", "device.fault", "operation.state", "operation.resolved", "stop", "lease.revoked", "lease.expired", "policy.changed"]);
const SUMMARY_HARD_LIMIT = 4096;

/** An invalid declaration (raised at start, before anything is served). */
export class DescriptionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DescriptionError";
  }
}

export type Evidence = "measured" | "reported" | "commanded" | "estimated" | "simulated";

export interface PropertyOptions {
  /** UCUM unit; builds a `number` schema when `schema` is not given. */
  unit?: string;
  /** Full JSON Schema of the value (numbers must carry `x-bhms-unit`). */
  schema?: Schema;
  evidence?: Evidence;
  observable?: boolean;
  readEffect?: "none" | "transaction";
  maxRateHz?: number;
  requiresLease?: boolean;
  resources?: string[];
  /** Age in ms after which a retained value is `stale`. */
  validityMs?: number;
  /** Acquisition bound in ms (default 1000). */
  timeoutMs?: number;
  description?: string;
}

export type Getter = () => unknown | Reading | Promise<unknown | Reading>;

export interface PropertySpec {
  name: string;
  getter?: Getter;
  schema: Schema;
  evidence: Evidence;
  observable: boolean;
  readEffect: "none" | "transaction";
  description: string;
  maxRateHz?: number;
  requiresLease: boolean;
  resources: string[];
  validityMs?: number;
  timeoutMs: number;
}

export interface ActionOptions {
  description?: string;
  effect: "none" | "reversible" | "irreversible" | "hazardous";
  idempotency: "idempotent" | "absolute" | "relative" | "toggle";
  /** A full object schema, or a member map (`{ target: range(0, 200, "um") }`). */
  input?: Schema | Record<string, Schema | string>;
  /** Members of the map form that are not required although they have no default. */
  optional?: string[];
  /** A full schema, or a member map (`{ position: "mm" }`). */
  output?: Schema | Record<string, Schema | string>;
  cancel?: "supported" | "unsupported";
  completionEvidence?: "measured" | "reported" | "none";
  verifiedBy?: string[];
  typicalDurationMs?: number;
  /** Required unless `effect` is `none` (default 1000 then). */
  maxDurationMs?: number;
  requiresLease?: boolean;
  /** Default: all the device's resources for effectful actions. */
  resources?: string[];
  onLeaseLoss?: "finish" | "cancel" | "hold";
  /** `{ pressure: 1000 }`: property name to `maxAgeMs` (BHMS-OBS-030). */
  requiresFresh?: Record<string, number>;
  preconditions?: string;
}

export type ActionHandler = (ctx: ActionContext, args: Record<string, unknown>) => Promise<unknown> | unknown;

export interface ActionSpec {
  name: string;
  handler: ActionHandler;
  input: Schema;
  output?: Schema;
  effect: ActionOptions["effect"];
  idempotency: ActionOptions["idempotency"];
  cancel: "supported" | "unsupported";
  completionEvidence: "measured" | "reported" | "none";
  maxDurationMs: number;
  requiresLease: boolean;
  resources: string[];
  description: string;
  verifiedBy: string[];
  typicalDurationMs?: number;
  onLeaseLoss?: "finish" | "cancel" | "hold";
  requiresFresh: Array<{ property: string; maxAgeMs: number }>;
  preconditions?: string;
}

export interface StopSpec {
  handler: () => Promise<void> | void;
  evidence: "measured" | "reported";
  maxDurationMs?: number;
}

export type DeviceStatus = "online" | "offline" | "degraded" | "unknown";

export interface DeviceOptions {
  name?: string;
  description?: string;
  summary?: string;
  capabilities?: string[];
  tags?: string[];
  resources?: string[];
  identity?: Record<string, string>;
  onDisconnect?: "continue" | "hold" | "stop" | "unknown";
  safetySummary?: string;
  /** Seconds after which reachability evidence is stale (default 60, BHMS-DEV-012). */
  livenessS?: number;
  extensions?: Record<string, unknown>;
}

function describeProperty(p: PropertySpec): Record<string, unknown> {
  const out: Record<string, unknown> = { description: p.description, schema: p.schema, evidence: p.evidence, observable: p.observable, readEffect: p.readEffect };
  if (p.maxRateHz !== undefined) out.maxRateHz = p.maxRateHz;
  if (p.requiresLease) out.requiresLease = true;
  if (p.resources.length > 0) out.resources = p.resources;
  return out;
}

function describeAction(a: ActionSpec): Record<string, unknown> {
  const out: Record<string, unknown> = {
    description: a.description, input: a.input, effect: a.effect, idempotency: a.idempotency, cancel: a.cancel,
    completionEvidence: a.completionEvidence, maxDurationMs: a.maxDurationMs, requiresLease: a.requiresLease, resources: a.resources,
  };
  if (a.output !== undefined) out.output = a.output;
  if (a.verifiedBy.length > 0) out.verifiedBy = a.verifiedBy;
  if (a.typicalDurationMs !== undefined) out.typicalDurationMs = a.typicalDurationMs;
  if (a.onLeaseLoss !== undefined) out.onLeaseLoss = a.onLeaseLoss;
  if (a.requiresFresh.length > 0) out.requiresFresh = a.requiresFresh;
  if (a.preconditions !== undefined) out.preconditions = a.preconditions;
  return out;
}

function sorted<T>(o: Record<string, T>): Record<string, T> {
  return Object.fromEntries(Object.entries(o).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
}

function firstSentences(text: string): string {
  const t = text.split(/\s+/).filter(Boolean).join(" ");
  if (t.length <= 280) return t;
  const cut = t.slice(0, 280);
  const stop = cut.lastIndexOf(". ");
  return stop > 40 ? cut.slice(0, stop + 1) : cut.slice(0, 277) + "...";
}

export class Device {
  readonly properties = new Map<string, PropertySpec>();
  readonly actions = new Map<string, ActionSpec>();
  readonly events = new Map<string, { description: string; data?: Schema }>();
  readonly capabilities: string[];
  readonly tags: string[];
  readonly resources: string[];
  /** The display name; reassigning it takes effect with the next {@link invalidate}. */
  name: string;
  /**
   * A last transformation of the description that is served, applied after validation and the digest (so it may produce
   * what validation would refuse). For test devices that serve hostile or inconsistent descriptions on purpose; the hook is
   * responsible for the digest it returns. Call {@link invalidate} when its inputs change.
   */
  describeHook?: (description: DeviceDescription) => DeviceDescription;
  stopSpec?: StopSpec;
  holdHandler?: () => Promise<void> | void;
  reconcileHandler?: (op: Record<string, unknown>) => Promise<Reconciled | undefined> | Reconciled | undefined;
  livenessHandler?: () => Promise<boolean> | boolean;
  /** Seconds between periodic liveness probes (`undefined`: the server's `livenessIntervalS`, off unless set). */
  livenessIntervalS?: number;
  /** How long one liveness probe may take before it counts as failed. */
  livenessTimeoutS = 5;
  private cached?: DeviceDescription;
  private readonly validators = new Map<string, SchemaValidator>();
  private aliveAt?: number;
  private forced?: "offline" | "degraded";
  private probeFailed = false;
  private readonly livenessS: number;

  constructor(readonly server: DeviceServer | undefined, readonly deviceId: string, private readonly o: DeviceOptions = {}) {
    if (!DEVICE_ID.test(deviceId)) throw new DescriptionError(`device id ${JSON.stringify(deviceId)} must match ${DEVICE_ID.source} (BHMS §4.1)`);
    if (o.onDisconnect !== undefined && !["continue", "hold", "stop", "unknown"].includes(o.onDisconnect)) throw new DescriptionError("onDisconnect must be continue, hold, stop or unknown");
    this.name = o.name ?? deviceId;
    this.capabilities = [...(o.capabilities ?? [])];
    this.tags = [...(o.tags ?? [])];
    this.resources = [...(o.resources ?? [])];
    this.livenessS = o.livenessS ?? 60;
  }

  // ------------------------------------------------------------------------------------------------ declarations

  /** Declare a property. With a getter it can be acquired on demand; without one, the device pushes values with `publish`. */
  property(name: string, options: PropertyOptions, getter?: Getter): this {
    if (!NAME.test(name)) throw new DescriptionError(`property name ${JSON.stringify(name)} must be snake_case (${NAME.source})`);
    const unknown = (options.resources ?? []).filter((r) => !this.resources.includes(r));
    if (unknown.length > 0) throw new DescriptionError(`property ${name}: resources ${unknown.join(", ")} are not declared by the device`);
    let schema = options.schema;
    if (!schema) {
      if (options.unit === undefined) throw new DescriptionError(`property ${name}: give a unit or a schema`);
      schema = num(options.unit);
    }
    if (options.requiresLease && (options.resources ?? []).length === 0) throw new DescriptionError(`property ${name}: requiresLease needs resources`);
    this.properties.set(name, {
      name, getter, schema, evidence: options.evidence ?? "reported", observable: options.observable ?? true,
      readEffect: options.readEffect ?? "none", description: options.description ?? "", maxRateHz: options.maxRateHz,
      requiresLease: options.requiresLease ?? false, resources: [...(options.resources ?? [])],
      validityMs: options.validityMs, timeoutMs: options.timeoutMs ?? 1000,
    });
    this.invalidate();
    return this;
  }

  /** Declare an action (see the module docs). */
  action(name: string, options: ActionOptions, handler: ActionHandler): this {
    if (!NAME.test(name)) throw new DescriptionError(`action name ${JSON.stringify(name)} must be snake_case (${NAME.source})`);
    const effectful = options.effect !== "none";
    if (effectful && options.maxDurationMs === undefined) throw new DescriptionError(`action ${name}: maxDurationMs is required for effect ${options.effect} (BHMS-DEV-030)`);
    const resources = options.resources ?? (effectful ? [...this.resources] : []);
    const unknown = resources.filter((r) => !this.resources.includes(r));
    if (unknown.length > 0) throw new DescriptionError(`action ${name}: resources ${unknown.join(", ")} are not declared by the device (BHMS-DEV-032)`);
    if (options.effect === "hazardous" && !options.requiresLease) {
      throw new DescriptionError(`action ${name}: a hazardous action must declare requiresLease: true (BHMS-DEV-033): its caller must hold exclusive control of the resources it acts on`);
    }
    if (options.requiresLease && resources.length === 0) throw new DescriptionError(`action ${name}: requiresLease needs at least one resource (BHMS-DEV-032)`);
    const input = asObjectSchema(options.input, options.optional);
    const output = options.output === undefined ? undefined : asObjectSchema(options.output);
    this.actions.set(name, {
      name, handler, input, output, effect: options.effect, idempotency: options.idempotency, cancel: options.cancel ?? "unsupported",
      completionEvidence: options.completionEvidence ?? "reported", maxDurationMs: options.maxDurationMs ?? 1000,
      requiresLease: options.requiresLease ?? false, resources, description: options.description ?? "",
      verifiedBy: [...(options.verifiedBy ?? [])], typicalDurationMs: options.typicalDurationMs, onLeaseLoss: options.onLeaseLoss,
      requiresFresh: Object.entries(options.requiresFresh ?? {}).map(([property, maxAgeMs]) => ({ property, maxAgeMs })),
      preconditions: options.preconditions,
    });
    this.invalidate();
    return this;
  }

  removeAction(name: string): void {
    if (!this.actions.delete(name)) throw new RangeError(`no action ${name}`);
    this.invalidate();
  }

  /** Declare a device-specific event type (BHMS-EVT-003); it must not reuse a core type. */
  event(type: string, options: { description?: string; data?: Schema | Record<string, Schema | string> } = {}): this {
    if (CORE_EVENT_TYPES.has(type)) throw new DescriptionError(`event type ${JSON.stringify(type)} is a core type; device events must not reuse it`);
    if (!/^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$/.test(type) || type.length > 64) throw new DescriptionError(`event type ${JSON.stringify(type)} must be dotted snake_case of at most 64 characters`);
    const entry: { description: string; data?: Schema } = { description: options.description ?? "" };
    if (options.data !== undefined) entry.data = asObjectSchema(options.data);
    this.events.set(type, entry);
    this.invalidate();
    return this;
  }

  /** Register the commissioned stop procedure (`safety.stop: "supported"`); returning normally means it finished. */
  onStop(options: { evidence?: "measured" | "reported"; maxDurationMs?: number }, handler: () => Promise<void> | void): this {
    const evidence = options.evidence ?? "reported";
    if (evidence !== "measured" && evidence !== "reported") throw new DescriptionError("onStop evidence must be 'measured' or 'reported' (a stop without evidence is never confirmed, BHMS-AUTH-022)");
    this.stopSpec = { handler, evidence, maxDurationMs: options.maxDurationMs };
    this.invalidate();
    return this;
  }

  /** Register the hold command used by `onLeaseLoss: "hold"` (BHMS-LSE-012). */
  onHold(handler: () => Promise<void> | void): this {
    this.holdHandler = handler;
    return this;
  }

  /**
   * Register a hook resolving `unknown` operations from device evidence (BHMS-OPS-005).
   *
   * The server calls it for each of the device's `unknown` operations: after a restart, whenever the device **returns** (its
   * status becomes `online` after `offline`, `degraded` or `unknown`: once per return, BHMS-OPS-082), on `operations/resolve`
   * and on {@link DeviceServer.reconcile}. Each call is bounded by the server's `reconcileTimeoutS`. Return `undefined` (or
   * throw) when the device cannot say what happened: the operation then stays `unknown`; success is never assumed.
   */
  reconcile(handler: NonNullable<Device["reconcileHandler"]>): this {
    this.reconcileHandler = handler;
    return this;
  }

  /**
   * Register the liveness probe `() => boolean` (sync or async).
   *
   * A true result is reachability evidence (BHMS-DEV-012). A false result, an exception or no answer within `timeoutS`
   * (default 5) is evidence that the device is unreachable: its status becomes `offline` until a later probe (or any other
   * evidence of life: a successful acquisition, a completed action, {@link reportAlive}) succeeds.
   *
   * The probe runs once when the server starts. With `intervalS` (or the server's `livenessIntervalS`; both off unless set) it
   * also runs every `intervalS` seconds, so a bridge whose instrument died stops reporting its last status.
   */
  liveness(handler: () => Promise<boolean> | boolean, options: { intervalS?: number; timeoutS?: number } = {}): this {
    if (options.intervalS !== undefined && !(options.intervalS > 0)) throw new RangeError("liveness intervalS must be positive (omit it to leave periodic probing off)");
    if (options.timeoutS !== undefined && !(options.timeoutS > 0)) throw new RangeError("liveness timeoutS must be positive");
    this.livenessHandler = handler;
    this.livenessIntervalS = options.intervalS;
    this.livenessTimeoutS = options.timeoutS ?? 5;
    this.server?.startLiveness(this);
    return this;
  }

  // ------------------------------------------------------------------------------------------------ description

  invalidate(): void {
    const had = this.cached !== undefined;
    this.cached = undefined;
    this.validators.clear();
    if (had) this.server?.deviceChanged(this);
  }

  private safety(): Record<string, unknown> {
    const out: Record<string, unknown> = this.stopSpec
      ? { stop: "supported", stopEvidence: this.stopSpec.evidence, ...(this.stopSpec.maxDurationMs !== undefined ? { stopMaxDurationMs: this.stopSpec.maxDurationMs } : {}) }
      : { stop: "unsupported", stopEvidence: "none" };
    out.onDisconnect = this.o.onDisconnect ?? "unknown";
    out.summary = this.o.safetySummary ?? (this.stopSpec
      ? "stop runs the device's commissioned stop procedure, cancels its operations and revokes its leases"
      : "no commissioned stop procedure; stop only cancels operations and revokes leases");
    return out;
  }

  /** The current `DeviceDescription`; throws {@link DescriptionError} when the declarations are invalid. */
  description(): DeviceDescription {
    if (this.cached) return this.cached;
    const body: Record<string, unknown> = {
      deviceId: this.deviceId, name: this.name, description: this.o.description ?? "", capabilities: this.capabilities, tags: this.tags,
      resources: this.resources,
      properties: sorted(Object.fromEntries([...this.properties].map(([n, p]) => [n, describeProperty(p)]))),
      actions: sorted(Object.fromEntries([...this.actions].map(([n, a]) => [n, describeAction(a)]))),
      safety: this.safety(),
    };
    if (this.o.identity && Object.keys(this.o.identity).length > 0) body.identity = { ...this.o.identity };
    if (this.events.size > 0) body.events = sorted(Object.fromEntries(this.events));
    if (this.o.extensions && Object.keys(this.o.extensions).length > 0) body.extensions = this.o.extensions;
    this.check(body);
    body.digest = descriptionDigest(body);
    const description = body as unknown as DeviceDescription;
    if (canonical(this.summary("unknown", description)).length > SUMMARY_HARD_LIMIT) {
      throw new DescriptionError(`device ${this.deviceId}: summary exceeds ${SUMMARY_HARD_LIMIT} bytes (BHMS-DEV-011); shorten name, summary or tags`);
    }
    const served = this.describeHook ? this.describeHook(description) : description;
    this.cached = served;
    return served;
  }

  private check(body: Record<string, unknown>): void {
    const where = `device ${this.deviceId}`;
    const props = body.properties as Record<string, { schema: unknown }>;
    const actions = body.actions as Record<string, { input: unknown; output?: unknown; verifiedBy?: string[]; requiresFresh?: Array<{ property: string }>; onLeaseLoss?: string }>;
    try {
      for (const [n, p] of Object.entries(props)) checkUnits(p.schema, `${where} property ${n}`);
      for (const [n, a] of Object.entries(actions)) {
        checkUnits(a.input, `${where} action ${n} input`);
        if (a.output !== undefined) checkUnits(a.output, `${where} action ${n} output`);
        for (const p of a.verifiedBy ?? []) if (!(p in props)) throw new RangeError(`${where} action ${n}: verifiedBy names unknown property ${JSON.stringify(p)}`);
        const seen = new Set<string>();
        (a.requiresFresh ?? []).forEach((f, i) => {
          if (!(f.property in props)) throw new RangeError(`${where} action ${n}: requiresFresh[${i}] names unknown property ${JSON.stringify(f.property)} (BHMS-DEV-034)`);
          if (seen.has(f.property)) throw new RangeError(`${where} action ${n}: requiresFresh names ${f.property} twice (BHMS-DEV-034)`);
          seen.add(f.property);
        });
        if (a.onLeaseLoss === "hold" && !this.holdHandler) throw new RangeError(`${where} action ${n}: onLeaseLoss "hold" needs an onHold handler`);
      }
      for (const [t, e] of this.events) if (e.data) checkUnits(e.data, `${where} event ${t} data`);
    } catch (e) {
      if (e instanceof RangeError) throw new DescriptionError(e.message);
      throw e;
    }
  }

  get digest(): string { return this.description().digest; }

  /** The `DeviceSummary` for `devices/list` (BHMS-DEV-011). */
  summary(status: DeviceStatus, desc: DeviceDescription = this.description()): DeviceSummary {
    const text = this.o.summary ?? firstSentences(desc.description);
    return {
      deviceId: this.deviceId, name: this.name, summary: text.slice(0, 280), capabilities: [...this.capabilities], tags: [...this.tags],
      status, digest: desc.digest ?? "sha256:" + "0".repeat(64), actions: Object.keys(desc.actions).sort(), properties: Object.keys(desc.properties).sort(),
    };
  }

  /** Cached validator for an action output or event data schema. */
  validator(key: string, schema: Schema | undefined): SchemaValidator {
    let v = this.validators.get(key);
    if (!v) {
      v = new SchemaValidator(schema ?? true);
      this.validators.set(key, v);
    }
    return v;
  }

  // ------------------------------------------------------------------------------------------------ status

  /**
   * Record reachability evidence now (BHMS-DEV-012); the server also does this on every successful acquisition and every
   * completed action. Evidence of life ends an `offline` that a failed liveness probe caused (a status forced with
   * {@link setStatus} stays until it is cleared).
   */
  reportAlive(): void {
    const previous = this.status;
    this.aliveAt = mono();
    this.probeFailed = false;
    this.changedFrom(previous);
  }

  /** Record evidence that the device does not answer (a failed liveness probe): `offline` until {@link reportAlive}. */
  reportUnreachable(): void {
    const previous = this.status;
    this.probeFailed = true;
    this.changedFrom(previous);
  }

  /** Force `offline` or `degraded`; `undefined` returns to evidence-based `online`/`offline`/`unknown`. */
  setStatus(status: "offline" | "degraded" | undefined): void {
    const previous = this.status;
    this.forced = status;
    this.changedFrom(previous);
  }

  private changedFrom(previous: DeviceStatus): void {
    if (this.status !== previous) this.server?.statusChanged(this, previous);
  }

  /** `offline`/`degraded` when forced; `offline` after a failed liveness probe; `online` with evidence within `livenessS`; else `unknown`. */
  get status(): DeviceStatus {
    if (this.forced) return this.forced;
    if (this.probeFailed) return "offline";
    if (this.aliveAt !== undefined && mono() - this.aliveAt <= this.livenessS * 1000) return "online";
    return "unknown";
  }

  // ------------------------------------------------------------------------------------------------ runtime helpers

  /** Record a value the device pushed (for subscriptions and later reads); returns its `Observation`. */
  publish(property: string, value: unknown, options: { quality?: "valid" | "stale" | "invalid" | "unknown"; uncertainty?: number; source?: string; latencyMs?: number } = {}): Promise<Observation> {
    if (!this.server) throw new Error("the device is not attached to a server");
    return this.server.observations.publish(this, property, value, options);
  }

  /** Append a declared device event (BHMS-EVT-003); `device.fault` is allowed too. */
  emit(type: string, data?: Record<string, unknown>, options: { severity?: Event["severity"]; message?: string; operationId?: string } = {}): Event {
    if (!this.server) throw new Error("the device is not attached to a server");
    if (type !== "device.fault") {
      const decl = this.events.get(type);
      if (!decl) throw new DescriptionError(`event type ${JSON.stringify(type)} is not declared on ${this.deviceId}; declare it with device.event(...) first (BHMS-EVT-003)`);
      const issues = this.validator(`event:${type}`, decl.data).collect(data ?? {});
      if (issues.length > 0) throw new RangeError(`event ${type} data does not match its declared schema: ${issues[0].message}`);
    }
    return this.server.events.append(type, { severity: options.severity, deviceId: this.deviceId, operationId: options.operationId, message: options.message, data });
  }
}
