/**
 * Bounded programs: validation before the first step, and execution over the operation machinery (spec/bhms/08).
 *
 * Validation ({@link Validator}, BHMS-PRG-001..007) checks the whole program before anything runs and refuses with a JSON-RPC
 * error whose `field` is a path into the program (`program.steps[1].steps[0].arguments.distance`): size and
 * step/depth/repeat/variable/executed-step limits (§8.1), devices, actions and properties, references (undefined, defined
 * later, defined twice or shadowing an input), predicate depth <= 4, `repeat.times` references (a required integer input with
 * `minimum >= 1` and `maximum <= maxRepeat`), literal arguments against the action `input`, input references whose bounds
 * must lie inside the action's envelope, worst-case duration against the declared `maxDurationMs`, and authority
 * (`programs:run`, every `invoke` scope, fresh `transaction` reads) plus a lease covering every lease-requiring step.
 *
 * Execution ({@link ProgramRunner}, BHMS-PRG-010..016): one async loop per run executes steps strictly in order. Each `invoke`
 * step creates a child operation through {@link Executor.admit} (so every admission check applies again, including arguments
 * built from saved results) with `keyOrigin: derived` and the key `d-` + sha256(parentId + "/" + executionPath)[:40]. A failing
 * step stops the program (`failed` with the step's error, `mayHaveActed` true if an effectful child was dispatched; `unknown`
 * if the child is unknown); completed effects are never rolled back. `maxDurationMs` (and `deadlineMs`) is enforced at run
 * time; `operations/cancel` and `stop` end the run after cancelling the running child. The program's `effect` follows its
 * children (BHMS-PRG-016); when every effectful child is `verified` their measured observations are carried up under
 * `s<n>_<property>` so that the program itself has measured evidence (BHMS-OPS-006).
 *
 * Programs are never resumed after a restart (BHMS-PRG-017): {@link ProgramRunner.recoverAfterRestart} settles each from its
 * step history, and {@link ProgramRunner.settleAfterReconcile} settles an `unknown` program once its `unknown` children are
 * reconciled.
 *
 * The registry (`programs/register|get|list`) stores validated programs by digest in the {@link Store}; registration grants
 * no authority (BHMS-PRG-021).
 *
 * Thread-safety: single event loop.
 */
import { createHash } from "node:crypto";
import { BhmsError } from "../errors.js";
import { canonicalString, digest } from "../canonical.js";
import type { ActionsInvokeParams, Observation, Operation } from "../generated/types.js";
import { validateDef, type JsonSchema } from "../schema.js";
import { PROTOCOL_VERSION } from "../generated/types.js";
import type { Principal } from "./authority.js";
import type { Device, ActionSpec, PropertySpec } from "./device.js";
import { intentDigest } from "./executor.js";
import type { Lease } from "./leases.js";
import { OperationRecord, unknownError, type Effect, type TransitionOptions } from "./operations.js";
import type { DeviceServer } from "./server.js";
import { StoreError, type StoredOperation, type StoredProgram } from "./store.js";
import { iso, mono, newId } from "./time.js";
import { admitArguments, checkUnits } from "./validation.js";

type Obj = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export interface ProgramLimits {
  maxSteps: number;
  maxRepeat: number;
  maxDepth: number;
  maxExecutedSteps: number;
  maxVariables: number;
  maxProgramBytes: number;
  maxDurationMs: number;
}

export const DEFAULT_PROGRAM_LIMITS: ProgramLimits = {
  maxSteps: 256, maxRepeat: 1000, maxDepth: 4, maxExecutedSteps: 4096, maxVariables: 64, maxProgramBytes: 65536, maxDurationMs: 3_600_000,
};

const REFERENCE = /^\$\{([A-Za-z_][A-Za-z0-9_]*)((?:\.[A-Za-z0-9_]+|\[[0-9]+\])*)\}$/;
const SELECTOR = /\.([A-Za-z0-9_]+)|\[([0-9]+)\]/g;
const MAX_PREDICATE_DEPTH = 4;
const EFFECT_RANK: Record<string, number> = { none: 0, reversible: 1, irreversible: 2, hazardous: 3 };

// ------------------------------------------------------------------------------------------------ values and predicates

/** `[variable, selectors]` when `value` is exactly a `${path}` reference (§8.2). */
export function reference(value: unknown): [string, string] | undefined {
  if (typeof value === "string") {
    const m = REFERENCE.exec(value);
    if (m) return [m[1], m[2]];
  }
  return undefined;
}

function references(value: unknown): string[] {
  const found = reference(value);
  if (found) return [found[0]];
  if (Array.isArray(value)) return value.flatMap(references);
  if (typeof value === "object" && value !== null) return Object.values(value).flatMap(references);
  return [];
}

/** Replace every reference by the referenced value (type preserved); `"$${x}"` is the literal `"${x}"`. */
export function resolve(value: unknown, variables: Record<string, unknown>): unknown {
  const found = reference(value);
  if (found) {
    if (!(found[0] in variables)) throw new RangeError(`variable ${found[0]} is not defined`);
    let cur: any = variables[found[0]]; // eslint-disable-line @typescript-eslint/no-explicit-any
    for (const m of found[1].matchAll(SELECTOR)) {
      if (cur === null || cur === undefined) throw new RangeError("a selector walks through a missing value");
      cur = m[2] !== undefined ? cur[Number(m[2])] : cur[m[1]];
      if (cur === undefined) throw new RangeError(`no member ${m[1] ?? m[2]}`);
    }
    return cur;
  }
  if (typeof value === "string" && value.startsWith("$${")) return value.slice(1);
  if (Array.isArray(value)) return value.map((v) => resolve(v, variables));
  if (typeof value === "object" && value !== null) return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, resolve(v, variables)]));
  return value;
}

const isNumber = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Evaluate a predicate (§8.2); ordering and `within` on non-numbers are false. */
export function evaluate(p: Obj, variables: Record<string, unknown>): boolean {
  if ("all" in p) return (p.all as Obj[]).every((q) => evaluate(q, variables));
  if ("any" in p) return (p.any as Obj[]).some((q) => evaluate(q, variables));
  if ("not" in p) return !evaluate(p.not, variables);
  const left = resolve(p.left, variables);
  const right = resolve(p.right, variables);
  if (p.op === "eq" || p.op === "ne") {
    const same = canonicalString(left) === canonicalString(right);
    return p.op === "eq" ? same : !same;
  }
  if (!isNumber(left) || !isNumber(right)) return false;
  if (p.op === "within") {
    const tol = resolve(p.tolerance, variables);
    return isNumber(tol) && Math.abs(left - right) <= tol;
  }
  return { lt: left < right, le: left <= right, gt: left > right, ge: left >= right }[p.op as "lt"];
}

// ------------------------------------------------------------------------------------------------ validation

interface PlanStep {
  raw: Obj;
  index: number;
  path: string;
  device?: Device;
  action?: ActionSpec;
  property?: PropertySpec;
  body: PlanStep[];
  timesInput?: string;
}

export interface Plan {
  program: Obj;
  digest: string;
  steps: PlanStep[];
  info: Obj;
  leaseResources: string[];
  /**
   * Every invoke step that uses resources without requiring a lease: such a step presents the program's lease when that
   * lease holds any of its resources (BHMS-LSE-014), which must then cover all of them (BHMS-PRG-006).
   */
  sharedSteps: Array<{ path: string; action: string; resources: string[] }>;
}

class Validator {
  private readonly limits: ProgramLimits;
  private count = 0;
  private executed = 0;
  private readonly ids = new Set<string>();
  private names = new Set<string>();
  private readonly effects: string[] = [];
  private readonly devices = new Set<string>();
  private readonly resources = new Set<string>();
  private readonly leaseResources = new Set<string>();
  private readonly sharedSteps: Plan["sharedSteps"] = [];
  private inputs: Record<string, Obj> = {};
  private required = new Set<string>();

  constructor(private readonly srv: DeviceServer, private readonly principal: Principal, private readonly program: Obj) {
    this.limits = srv.programLimits;
  }

  private fail(code: ConstructorParameters<typeof BhmsError>[0], field: string, message: string, hint: string, bound?: unknown): BhmsError {
    return new BhmsError(code, message, { field, bound, hint });
  }

  run(): Plan {
    const program = this.program;
    const limits = this.limits;
    const size = Buffer.byteLength(canonicalString(program));
    if (size > limits.maxProgramBytes) {
      throw this.fail("OUT_OF_RANGE", "program", `the program is ${size} bytes of canonical JSON`, `keep programs under ${limits.maxProgramBytes} bytes`, { maximum: limits.maxProgramBytes });
    }
    try {
      validateDef("Program", program);
    } catch (e) {
      if (e instanceof BhmsError) throw this.fail("INVALID_ARGUMENT", e.field ? `program.${e.field}` : "program", e.message, e.hint);
      throw e;
    }
    if (program.bhmsProgram !== PROTOCOL_VERSION) {
      throw this.fail("INVALID_ARGUMENT", "program.bhmsProgram", `programs for ${program.bhmsProgram} are not served`, "write the program for a supported protocol version", [PROTOCOL_VERSION]);
    }
    try {
      checkUnits(program.input, "program.input");
    } catch (e) {
      if (e instanceof RangeError) throw this.fail("INVALID_ARGUMENT", "program.input", e.message, "give every numeric input x-bhms-unit");
      throw e;
    }
    if (program.maxDurationMs > limits.maxDurationMs) {
      throw this.fail("OUT_OF_RANGE", "program.maxDurationMs", `maxDurationMs ${program.maxDurationMs} is above this server's limit ${limits.maxDurationMs}`, `declare at most ${limits.maxDurationMs} ms`, { maximum: limits.maxDurationMs });
    }
    this.inputs = program.input.properties ?? {};
    this.required = new Set(program.input.required ?? []);
    this.names = new Set(Object.keys(this.inputs));
    const defined = new Set(Object.keys(this.inputs));
    const [steps, worst] = this.walkSteps(program.steps, "program.steps", 0, 1, defined, new Set());
    if (this.count > limits.maxSteps) {
      throw this.fail("OUT_OF_RANGE", "program.steps", `the program has ${this.count} steps`, `use at most ${limits.maxSteps} step objects`, { maximum: limits.maxSteps });
    }
    if (this.executed > limits.maxExecutedSteps) {
      throw this.fail("OUT_OF_RANGE", "program.steps", `the program can execute ${this.executed} steps`, `keep worst-case executions at or below ${limits.maxExecutedSteps}`, { maximum: limits.maxExecutedSteps });
    }
    if (this.names.size > limits.maxVariables) {
      throw this.fail("OUT_OF_RANGE", "program", `the program uses ${this.names.size} variables`, `use at most ${limits.maxVariables} inputs, saveAs names and repeat indices`, { maximum: limits.maxVariables });
    }
    for (const [name, value] of Object.entries(program.output ?? {})) this.refs(value, `program.output.${name}`, defined, new Set());
    if (worst > program.maxDurationMs) {
      throw this.fail("OUT_OF_RANGE", "program.maxDurationMs", `the worst-case duration is ${worst} ms, above the declared ${program.maxDurationMs} ms`, `declare maxDurationMs of at least ${worst} or shorten the program`, worst);
    }
    const progDigest = digest(program);
    const effect = this.effects.reduce((a, b) => (EFFECT_RANK[b] > EFFECT_RANK[a] ? b : a), "none");
    const info = {
      digest: progDigest, name: program.name, description: program.description, input: program.input, effect, worstCaseDurationMs: worst,
      maxDurationMs: program.maxDurationMs, stepCount: this.count, maxExecutedSteps: this.executed, devices: [...this.devices].sort(),
      resources: [...this.resources].sort(), requiresLease: this.leaseResources.size > 0,
    };
    return { program, digest: progDigest, steps, info, leaseResources: [...this.leaseResources].sort(), sharedSteps: this.sharedSteps };
  }

  private define(name: string, path: string): void {
    if (this.names.has(name)) throw this.fail("INVALID_ARGUMENT", path, `variable ${JSON.stringify(name)} is defined twice`, "give every input, saveAs and repeat index a distinct name (BHMS-PRG-002)");
    this.names.add(name);
  }

  private refs(value: unknown, path: string, defined: Set<string>, local: Set<string>): void {
    for (const name of references(value)) {
      if (!defined.has(name) && !local.has(name)) {
        throw this.fail("INVALID_ARGUMENT", path, `\${${name}} is undefined here or defined later`, "reference only inputs, earlier saveAs names and enclosing repeat indices");
      }
    }
  }

  private predicate(p: Obj, path: string, defined: Set<string>, local: Set<string>, depth = 1): void {
    if (depth > MAX_PREDICATE_DEPTH) throw this.fail("INVALID_ARGUMENT", path, "predicates nest deeper than 4", "flatten the predicate (all/any/not at most 4 levels, BHMS-PRG-002)");
    for (const key of ["all", "any"]) {
      if (key in p) {
        (p[key] as Obj[]).forEach((child, i) => this.predicate(child, `${path}.${key}[${i}]`, defined, local, depth + 1));
        return;
      }
    }
    if ("not" in p) { this.predicate(p.not, `${path}.not`, defined, local, depth + 1); return; }
    for (const member of ["left", "right", "tolerance"]) if (member in p) this.refs(p[member], `${path}.${member}`, defined, local);
  }

  private walkSteps(raw: Obj[], base: string, depth: number, multiplier: number, defined: Set<string>, local: Set<string>): [PlanStep[], number] {
    const out: PlanStep[] = [];
    let worst = 0;
    raw.forEach((r, position) => {
      const path = `${base}[${position}]`;
      const step: PlanStep = { raw: r, index: this.count, path, body: [] };
      this.count += 1;
      if ("id" in r) {
        if (this.ids.has(r.id)) throw this.fail("INVALID_ARGUMENT", `${path}.id`, `step id ${JSON.stringify(r.id)} is used twice`, "step ids must be unique");
        this.ids.add(r.id);
      }
      worst += this.step(step, depth, multiplier, defined, local);
      out.push(step);
    });
    return [out, worst];
  }

  private step(step: PlanStep, depth: number, multiplier: number, defined: Set<string>, local: Set<string>): number {
    const { raw, path } = step;
    const kind = raw.kind as string;
    if (kind === "repeat") return this.repeat(step, depth, multiplier, defined, local);
    this.executed += multiplier;
    if (kind === "invoke") {
      const device = this.srv.visibleDevice(this.principal, raw.deviceId, `${path}.deviceId`);
      const action = device.actions.get(raw.action);
      if (!action) {
        throw new BhmsError("UNKNOWN_ACTION", `${raw.deviceId} has no action ${JSON.stringify(raw.action)}`, { field: `${path}.action`, bound: [...device.actions.keys()].sort(), hint: `the actions are: ${[...device.actions.keys()].sort().join(", ") || "(none)"}` });
      }
      if (!this.principal.canInvoke(device.deviceId, action.name, device.capabilities, action.effect)) {
        throw new BhmsError("UNAUTHORIZED", `the principal may not invoke ${raw.deviceId}/${raw.action}`, { field: `${path}.action`, hint: `missing scope invoke:${raw.deviceId}/${raw.action} (BHMS-PRG-006)` });
      }
      step.device = device;
      step.action = action;
      this.arguments(action, raw.arguments, `${path}.arguments`, defined, local);
      this.effects.push(action.effect);
      this.devices.add(device.deviceId);
      for (const r of action.resources) this.resources.add(r);
      if (action.requiresLease) for (const r of action.resources) this.leaseResources.add(r);
      else if (action.resources.length > 0) this.sharedSteps.push({ path, action: action.name, resources: [...action.resources] });
      if (raw.saveAs) { this.define(raw.saveAs, `${path}.saveAs`); defined.add(raw.saveAs); }
      return action.maxDurationMs;
    }
    if (kind === "read" || kind === "waitUntil") {
      const device = this.srv.visibleDevice(this.principal, raw.deviceId, `${path}.deviceId`);
      const property = this.srv.observations.spec(device, raw.property, `${path}.property`);
      step.device = device;
      step.property = property;
      this.devices.add(device.deviceId);
      const acquires = kind === "waitUntil" || raw.fresh || raw.maxAgeMs !== undefined;
      if (property.readEffect === "transaction" && acquires) {
        if (!this.principal.canInvoke(device.deviceId, property.name, device.capabilities)) {
          throw this.fail("UNAUTHORIZED", `${path}.property`, `a fresh read of ${device.deviceId}.${property.name} starts a device transaction`, `missing scope invoke:${device.deviceId}/${property.name} (BHMS-PRG-006)`);
        }
        if (property.requiresLease) for (const r of property.resources.length > 0 ? property.resources : device.resources) this.leaseResources.add(r);
      }
      if (kind === "waitUntil") this.predicate(raw.predicate, `${path}.predicate`, defined, new Set([...local, "observed"]));
      if (raw.saveAs) { this.define(raw.saveAs, `${path}.saveAs`); defined.add(raw.saveAs); }
      return kind === "waitUntil" ? raw.timeoutMs : (raw.timeoutMs ?? 1000);
    }
    if (kind === "assert") { this.predicate(raw.predicate, `${path}.predicate`, defined, local); return 0; }
    return raw.durationMs; // sleep
  }

  private repeat(step: PlanStep, depth: number, multiplier: number, defined: Set<string>, local: Set<string>): number {
    const { raw, path } = step;
    if (depth + 1 > this.limits.maxDepth) throw this.fail("OUT_OF_RANGE", path, `repeat nesting exceeds ${this.limits.maxDepth}`, "flatten nested repeats", { maxDepth: this.limits.maxDepth });
    const times = raw.times;
    const maxRepeat = this.limits.maxRepeat;
    let count: number;
    if (typeof times === "string") {
      const found = reference(times);
      const name = found && !found[1] ? found[0] : undefined;
      const spec = name ? this.inputs[name] : undefined;
      if (!spec || !this.required.has(name!) || spec.type !== "integer" || (spec.minimum ?? 0) < 1 || (spec.maximum ?? maxRepeat + 1) > maxRepeat) {
        throw this.fail(!spec || spec.type !== "integer" ? "INVALID_ARGUMENT" : "OUT_OF_RANGE", `${path}.times`,
          `repeat.times ${times} must name a required integer input with minimum >= 1 and maximum <= ${maxRepeat}`,
          `declare the input as {"type": "integer", "minimum": 1, "maximum": ${maxRepeat}, "x-bhms-unit": "1"} and list it in required (BHMS-PRG-003)`, { minimum: 1, maximum: maxRepeat });
      }
      step.timesInput = name;
      count = spec.maximum;
    } else {
      if (times > maxRepeat) throw this.fail("OUT_OF_RANGE", `${path}.times`, `repeat.times ${times} is above ${maxRepeat}`, `repeat at most ${maxRepeat} times`, { maximum: maxRepeat });
      count = times;
    }
    const inner = new Set(local);
    if (raw.as) { this.define(raw.as, `${path}.as`); inner.add(raw.as); }
    const [body, bodyWorst] = this.walkSteps(raw.steps, `${path}.steps`, depth + 1, multiplier * count, defined, inner);
    step.body = body;
    return count * bodyWorst;
  }

  private arguments(action: ActionSpec, args: Obj, path: string, defined: Set<string>, local: Set<string>): void {
    const members = (action.input.properties ?? {}) as Record<string, Obj>;
    for (const name of Object.keys(args)) {
      if (!(name in members)) {
        throw this.fail("INVALID_ARGUMENT", `${path}.${name}`, `${name} is not an argument of ${action.name}`, `${action.name} accepts only: ${Object.keys(members).sort().join(", ") || "no members"}`);
      }
    }
    for (const name of (action.input.required ?? []) as string[]) {
      if (!(name in args)) throw this.fail("INVALID_ARGUMENT", `${path}.${name}`, `${path}.${name} is required`, `add ${name} to the step arguments`);
    }
    for (const [name, value] of Object.entries(args)) {
      this.refs(value, `${path}.${name}`, defined, local);
      const found = reference(value);
      if (found) {
        if (found[0] in this.inputs && !found[1]) this.inputEnvelope(members[name], this.inputs[found[0]], `${path}.${name}`);
        continue; // saved results are checked when the step is admitted
      }
      if (references(value).length > 0) continue;
      const single = { type: "object", additionalProperties: false, properties: { [name]: members[name] } };
      admitArguments(single as JsonSchema, { [name]: value }, path);
    }
  }

  /** An argument that is exactly an input reference: the input's bounds must lie inside the action's envelope (BHMS-PRG-005). */
  private inputEnvelope(node: Obj, source: Obj, path: string): void {
    const unit = node["x-bhms-unit"];
    if (unit !== undefined && source["x-bhms-unit"] !== unit) {
      throw this.fail("UNIT_MISMATCH", path, `the input feeding ${path} is in ${JSON.stringify(source["x-bhms-unit"])}, the action takes ${unit}`, `declare the input in ${unit}`, unit);
    }
    const problems: string[] = [];
    if ("minimum" in node && !("minimum" in source && source.minimum >= node.minimum)) problems.push("minimum");
    if ("maximum" in node && !("maximum" in source && source.maximum <= node.maximum)) problems.push("maximum");
    if ("enum" in node && !("enum" in source && (source.enum as unknown[]).every((v) => (node.enum as unknown[]).some((e) => canonicalString(e) === canonicalString(v))))) problems.push("enum");
    if (problems.length > 0) {
      const bound = Object.fromEntries(problems.map((k) => [k, node[k]]));
      throw this.fail("OUT_OF_RANGE", path, `the input feeding ${path} allows values outside the action's envelope (${problems.join(", ")})`,
        `narrow the input's bounds to ${Object.entries(bound).map(([k, v]) => `${k} ${JSON.stringify(v)}`).join(", ")} (BHMS-PRG-005)`, bound);
    }
  }
}

// ------------------------------------------------------------------------------------------------ execution

class StepFailed extends Error {
  constructor(readonly error: ReturnType<BhmsError["toOperationError"]>) { super(error.message); }
}
class StepUnknown extends Error {}
class Halted extends Error {}
/** The server is closing: the program stays in flight and is settled at restart (BHMS-PRG-017). */
class Shutdown extends Error {}

/** A latch with a timed wait: `set()` wakes a waiter early. */
class Wake {
  private flag = false;
  private wake?: () => void;
  set(): void { this.flag = true; this.wake?.(); }
  clear(): void { this.flag = false; }
  wait(ms: number): Promise<void> {
    if (this.flag) return Promise.resolve();
    return new Promise((resolve) => {
      const t = setTimeout(done, Math.max(0, ms));
      const self = this;
      function done(): void { clearTimeout(t); self.wake = undefined; resolve(); }
      this.wake = done;
    });
  }
}

interface Run {
  rec: OperationRecord;
  plan: Plan;
  principal: Principal;
  leaseId?: string;
  variables: Record<string, unknown>;
  deadlineMono: number;
  wake: Wake;
  halted: boolean;
  shutdown: boolean;
  child?: OperationRecord;
  done: number;
  task?: Promise<void>;
}

const derivedKey = (parentId: string, path: string): string => "d-" + createHash("sha256").update(`${parentId}/${path}`).digest("hex").slice(0, 40);

/**
 * BHMS-PRG-006 with BHMS-LSE-014: a step that does not require a lease but uses a resource the program's own lease holds runs
 * under that lease, so the lease must cover all of that step's resources. Refused at `programs/run`, before anything is
 * recorded, naming the step: at run time the step would be refused by the program's own lease, which reads as a conflict
 * with nobody.
 */
function checkSharedSteps(plan: Plan, lease: Lease): void {
  const held = new Set(lease.resources);
  for (const { path, action, resources } of plan.sharedSteps) {
    const covered = [...new Set(resources)].filter((r) => held.has(r)).sort();
    const missing = [...new Set(resources)].filter((r) => !held.has(r)).sort();
    if (covered.length === 0 || missing.length === 0) continue;
    throw new BhmsError("LEASE_CONFLICT", `${path} (${action}) uses ${resources.join(", ")}; the lease you run the program under holds ${covered.join(", ")} but not ${missing.join(", ")}`, {
      field: "leaseId", bound: missing,
      hint: `acquire one lease that also covers ${missing.join(", ")} and run the program under it: a step that uses a leased resource must present a lease covering all of its resources (BHMS-PRG-006, BHMS-LSE-014)`,
    });
  }
}

/** `effect` (and, when `verified`, the carried-up `evidence`) of a program from its children (BHMS-PRG-016). */
function programOutcome(children: OperationRecord[]): { effect: Effect; evidence?: Operation["evidence"] } {
  const effectful = children.filter((c) => c.data.effectClass !== "none" && c.dispatched);
  if (effectful.length === 0) return { effect: "none" };
  if (effectful.some((c) => c.state === "unknown" || c.op.effect === "unknown")) return { effect: "unknown" };
  if (!effectful.every((c) => c.op.effect === "verified")) return { effect: "unverified" };
  const observations: Record<string, Observation> = {};
  effectful.forEach((child, i) => {
    for (const [prop, obs] of Object.entries(child.op.evidence?.observations ?? {})) observations[`s${i + 1}_${prop}`] = obs;
  });
  return { effect: "verified", evidence: { kind: "measured", observations } };
}

export class ProgramRunner {
  private readonly runs = new Map<string, Run>();
  private readonly programs = new Map<string, StoredProgram>();

  constructor(private readonly server: DeviceServer, loaded: StoredProgram[]) {
    for (const p of loaded) this.programs.set(p.digest, p);
  }

  // ------------------------------------------------------------------------------------------------ validation and registry

  validate(principal: Principal, program: Obj): Plan {
    return new Validator(this.server, principal, program).run();
  }

  register(principal: Principal, program: Obj): Obj {
    if (!principal.has("programs:register")) throw new BhmsError("UNAUTHORIZED", "programs/register needs the programs:register scope", { hint: "missing scope programs:register" });
    const plan = this.validate(principal, program);
    const existing = this.programs.get(plan.digest);
    if (existing) return existing.info;
    const stored: StoredProgram = { digest: plan.digest, program, info: plan.info };
    try {
      this.server.store.writeProgram(stored);
    } catch (e) {
      if (e instanceof StoreError) { this.server.journalFailed(e); throw this.server.journalBusy(); }
      throw e;
    }
    this.programs.set(plan.digest, stored);
    return stored.info;
  }

  get(principal: Principal, programDigest: string): StoredProgram {
    if (!principal.canRead) throw new BhmsError("UNAUTHORIZED", "programs/get needs the read scope", { hint: "missing scope read" });
    const stored = this.programs.get(programDigest);
    if (!stored) throw new BhmsError("INVALID_ARGUMENT", `no registered program ${programDigest}`, { field: "digest", hint: "register it with programs/register, or run it inline (BHMS-PRG-020)" });
    return stored;
  }

  list(principal: Principal, after: string | undefined, limit: number): { infos: Obj[]; next?: string } {
    if (!principal.canRead) throw new BhmsError("UNAUTHORIZED", "programs/list needs the read scope", { hint: "missing scope read" });
    const rows = [...this.programs.values()].sort((a, b) => (a.digest < b.digest ? -1 : 1)).filter((p) => after === undefined || p.digest > after);
    const page = rows.slice(0, limit);
    return { infos: page.map((p) => p.info), next: rows.length > limit ? page[page.length - 1].digest : undefined };
  }

  // ------------------------------------------------------------------------------------------------ run

  /** `programs/run` from key lookup to the start of execution (BHMS-PRG-022). */
  async run(principal: Principal, params: Obj): Promise<{ rec: OperationRecord; replayed: boolean }> {
    const programDigest: string = params.digest ?? digest(params.program);
    const intent: Obj = { method: "programs/run", digest: programDigest, arguments: params.arguments };
    if (params.deadlineMs !== undefined) intent.deadlineMs = params.deadlineMs;
    const requestDigest = digest(intent);
    return this.server.executor.keyed(principal, params.operationKey, requestDigest, params.waitMs, (key, origin) => this.admit(principal, params, programDigest, key, origin, requestDigest));
  }

  private async admit(principal: Principal, params: Obj, programDigest: string, key: string, origin: "client" | "server", requestDigest: string): Promise<OperationRecord> {
    const srv = this.server;
    let program: Obj | undefined = params.program;
    if (program === undefined) {
      const stored = this.programs.get(programDigest);
      if (!stored) throw new BhmsError("INVALID_ARGUMENT", `no registered program ${programDigest}`, { field: "digest", hint: "register it with programs/register, or send it inline (BHMS-PRG-020)" });
      program = stored.program;
    }
    if (!principal.has("programs:run")) throw new BhmsError("UNAUTHORIZED", "programs/run needs the programs:run scope", { hint: "missing scope programs:run" });
    const plan = this.validate(principal, program);
    const { admitted, differs } = admitArguments(plan.program.input, params.arguments);
    let lease: Lease | undefined;
    if (plan.leaseResources.length > 0 || params.leaseId !== undefined) lease = srv.leases.check(principal.id, params.leaseId, plan.leaseResources);
    if (lease) checkSharedSteps(plan, lease);
    srv.requireJournal();
    const now = Date.now();
    const op: Operation = {
      operationId: newId("op"), operationKey: key, keyOrigin: origin, kind: "program", programDigest, arguments: params.arguments, requestDigest,
      state: "accepted", cancel: { state: "none" }, effect: "none", progress: { stepsCompleted: 0, stepsTotal: plan.info.maxExecutedSteps },
      createdAt: iso(now), updatedAt: iso(now),
    };
    if (differs) op.admittedArguments = admitted;
    if (lease) { op.leaseId = lease.leaseId; op.fence = lease.fence; }
    const data: StoredOperation = {
      id: op.operationId, principal: principal.id, op, history: [], resources: plan.info.resources, effectClass: plan.info.effect, cancelSupported: true,
      onLeaseLoss: "finish", completionEvidence: "none", maxDurationMs: plan.program.maxDurationMs, admitted,
    };
    let bound = plan.program.maxDurationMs as number;
    if (params.deadlineMs !== undefined) {
      data.deadlineMs = now + params.deadlineMs;
      op.deadlineAt = iso(now + params.deadlineMs);
      bound = Math.min(bound, params.deadlineMs);
    }
    let rec: OperationRecord;
    try {
      rec = srv.journal.create(data);
    } catch (e) {
      if (e instanceof StoreError) { srv.journalFailed(e); throw srv.journalBusy(); }
      throw e;
    }
    const run: Run = { rec, plan, principal, leaseId: lease?.leaseId, variables: { ...admitted }, deadlineMono: mono() + bound, wake: new Wake(), halted: false, shutdown: false, done: 0 };
    this.runs.set(rec.id, run);
    run.task = this.execute(run);
    return rec;
  }

  // ------------------------------------------------------------------------------------------------ execution

  private async execute(run: Run): Promise<void> {
    const j = this.server.journal;
    try {
      try {
        await this.steps(run, run.plan.steps, "");
        const output = resolve(run.plan.program.output ?? {}, run.variables);
        const o = this.outcome(run);
        j.transition(run.rec, "completed", { result: output, hasResult: true, effect: o.effect, evidence: o.evidence });
      } catch (e) {
        if (e instanceof Shutdown) return;
        if (e instanceof Halted) this.halt(run);
        else if (e instanceof StepUnknown) {
          j.transition(run.rec, "unknown", { error: unknownError(`step outcome unknown (child ${run.child?.id ?? "?"}); the program stopped`) });
        } else if (e instanceof StepFailed) this.failRun(run, e.error);
        else throw e;
      }
    } catch (e) {
      if (e instanceof StoreError) {
        this.server.journalFailed(e);
        this.server.log(`could not record the outcome of program ${run.rec.id}; it is settled at restart`);
      } else {
        this.server.log(`program ${run.rec.id} failed unexpectedly: ${e instanceof Error ? e.stack : String(e)}`);
        try {
          if (run.rec.state === "accepted") j.transition(run.rec, "rejected", { error: new BhmsError("INTERNAL", "the program could not start", { hint: "this is a server bug" }).toOperationError() });
          else if (!run.rec.settled) j.transition(run.rec, "unknown", { error: unknownError("the program coordinator failed") });
        } catch { /* nothing more can be recorded */ }
      }
    } finally {
      this.runs.delete(run.rec.id);
    }
  }

  private children(run: Run): OperationRecord[] { return this.server.journal.children(run.rec.id); }
  private outcome(run: Run): { effect: Effect; evidence?: Operation["evidence"] } { return programOutcome(this.children(run)); }
  private acted(children: OperationRecord[]): boolean { return children.some((c) => c.dispatched && c.data.effectClass !== "none"); }

  private failRun(run: Run, error: ReturnType<BhmsError["toOperationError"]>): void {
    const j = this.server.journal;
    const kids = this.children(run);
    const acted = this.acted(kids);
    const payload = { ...error, mayHaveActed: acted };
    if ((payload.bhmsCode === "DEVICE_FAULT" || payload.bhmsCode === "UNVERIFIED") && !acted) payload.bhmsCode = "INTERNAL";
    if (run.rec.state === "accepted") {
      j.transition(run.rec, "rejected", { error: { ...payload, mayHaveActed: false } });
      return;
    }
    const o = programOutcome(kids);
    j.transition(run.rec, "failed", { error: payload, effect: o.effect, evidence: o.evidence, proof: acted ? undefined : "no effectful step was dispatched" });
  }

  private halt(run: Run): void {
    const j = this.server.journal;
    if (run.rec.settled) return;
    if (run.rec.state === "accepted") { j.transition(run.rec, "canceled", { detail: "canceled before the first step" }); return; }
    const o = this.outcome(run);
    j.transition(run.rec, "canceled", { effect: o.effect, evidence: o.evidence, detail: `no further steps after ${run.done} completed step(s)` });
  }

  private checkBoundary(run: Run): void {
    if (run.shutdown) throw new Shutdown();
    if (run.halted) throw new Halted();
    if (mono() >= run.deadlineMono) {
      throw new StepFailed(new BhmsError("DEADLINE_EXCEEDED", "the program exceeded its maxDurationMs or deadline; no further step started", {
        mayHaveActed: true, hint: "inspect the child operations before running a compensating program",
      }).toOperationError());
    }
    if (run.leaseId !== undefined) {
      try {
        this.server.leases.check(run.principal.id, run.leaseId, run.plan.leaseResources);
      } catch (e) {
        if (e instanceof BhmsError) throw new StepFailed(e.toOperationError());
        throw e;
      }
    }
  }

  /** Move the program to `running` (a barrier commit via `dispatching`) before its first step can act. */
  private begin(run: Run): void {
    if (run.rec.state === "accepted") {
      this.server.journal.transition(run.rec, "dispatching");
      this.server.journal.transition(run.rec, "running", { detail: "first step started" });
    }
  }

  private startStep(run: Run, step: PlanStep, path: string, child?: OperationRecord): void {
    this.begin(run);
    this.server.journal.annotate(run.rec, "step", `${step.raw.kind} ${path}`, { stepIndex: step.index, childOperationId: child?.id });
  }

  private finishStep(run: Run): void {
    run.done += 1;
    this.server.journal.setProgress(run.rec, { stepsCompleted: run.done, stepsTotal: run.plan.info.maxExecutedSteps });
  }

  private async steps(run: Run, steps: PlanStep[], prefix: string): Promise<void> {
    for (const [position, step] of steps.entries()) {
      const path = `${prefix}${position}`;
      const kind = step.raw.kind as string;
      if (kind === "repeat") {
        const times = step.timesInput ? (run.variables[step.timesInput] as number) : (step.raw.times as number);
        const name = step.raw.as as string | undefined;
        for (let i = 0; i < times; i++) {
          if (name) run.variables[name] = i;
          await this.steps(run, step.body, `${path}/${i}/`);
        }
        if (name) delete run.variables[name];
        continue;
      }
      this.checkBoundary(run);
      if (kind === "invoke") {
        await this.invoke(run, step, path);
      } else {
        this.startStep(run, step, path);
        if (kind === "read") await this.read(run, step);
        else if (kind === "waitUntil") await this.waitUntil(run, step);
        else if (kind === "assert") {
          if (!evaluate(step.raw.predicate, run.variables)) {
            throw new StepFailed(new BhmsError("STALE", `assert failed: ${step.raw.message}`, { hint: step.raw.message }).toOperationError());
          }
        } else await this.sleep(run, step.raw.durationMs / 1000);
      }
      this.finishStep(run);
    }
  }

  /** Sleep the full duration (bounded by the program deadline); cancellation or stop ends it early. */
  private async sleep(run: Run, seconds: number): Promise<void> {
    const truncated = mono() + seconds * 1000 > run.deadlineMono;
    const end = Math.min(mono() + seconds * 1000, run.deadlineMono);
    for (let remaining = end - mono(); remaining > 0; remaining = end - mono()) {
      run.wake.clear();
      await run.wake.wait(remaining);
      if (run.shutdown) throw new Shutdown();
      if (run.halted) throw new Halted();
    }
    if (truncated) this.checkBoundary(run);
  }

  /**
   * The lease an invoke step presents: the program's lease when the step requires one or when that lease holds any resource
   * the step uses (a held lease refuses a request that does not present it, BHMS-LSE-014; admission made sure it then covers
   * all of them, BHMS-PRG-006). The step's admission checks it like any other request's ({@link LeaseManager.admit}).
   */
  private stepLease(run: Run, action: ActionSpec): string | undefined {
    if (run.leaseId === undefined) return undefined;
    if (action.requiresLease) return run.leaseId;
    const lease = this.server.leases.get(run.leaseId);
    return lease && action.resources.some((r) => lease.resources.includes(r)) ? run.leaseId : undefined;
  }

  private async invoke(run: Run, step: PlanStep, path: string): Promise<void> {
    const srv = this.server;
    const action = step.action!;
    let args: Obj;
    try {
      args = resolve(step.raw.arguments, run.variables) as Obj;
    } catch (e) {
      throw new StepFailed(new BhmsError("INVALID_ARGUMENT", `step ${path}: a reference could not be resolved (${(e as Error).message})`, {
        field: `program.steps[${path}].arguments`, hint: "check the saved value the step refers to",
      }).toOperationError());
    }
    const leaseId = this.stepLease(run, action);
    const params = { deviceId: step.device!.deviceId, action: action.name, arguments: args, ...(leaseId !== undefined ? { leaseId } : {}) } as unknown as ActionsInvokeParams;
    const key = derivedKey(run.rec.id, path);
    const requestDigest = intentDigest({ deviceId: params.deviceId, action: params.action, arguments: args });
    const deadlineAtMs = Date.now() + Math.max(0, run.deadlineMono - mono());
    // The program is durably dispatching before its first child exists, so a crash never leaves a dispatched child under a
    // program that still reads accepted (BHMS-PRG-017, BHMS-OPS-080).
    this.begin(run);
    let child: OperationRecord;
    try {
      child = await srv.executor.admit(run.principal, params, key, "derived", requestDigest, { parentId: run.rec.id, deadlineAtMs });
    } catch (e) {
      if (e instanceof BhmsError) throw new StepFailed(e.toOperationError());
      throw e;
    }
    run.child = child;
    this.startStep(run, step, path, child);
    while (!child.settled) {
      let remaining = run.deadlineMono - mono();
      if (remaining <= 0 && child.op.cancel.state === "none") {
        srv.executor.cancel(child, "program maxDurationMs exceeded");
        remaining = srv.opts.cancelGraceMs;
      }
      await srv.journal.wait(child, Math.max(10, remaining));
      if (run.shutdown) throw new Shutdown();
      if (!child.settled && run.deadlineMono + srv.opts.cancelGraceMs < mono()) break;
    }
    if (child.state === "completed") {
      if (step.raw.saveAs) run.variables[step.raw.saveAs] = child.op.result;
      return;
    }
    if (child.state === "unknown" || !child.settled) throw new StepUnknown();
    if (run.halted && child.state === "canceled") throw new Halted();
    if (mono() >= run.deadlineMono) this.checkBoundary(run);
    const error = child.op.error ?? new BhmsError("INTERNAL", `step ${path} ended ${child.state}`, { mayHaveActed: child.dispatched, hint: "inspect the child operation" }).toOperationError();
    throw new StepFailed({ ...error, message: `step ${path} (${action.name}): ${error.message}`.slice(0, 2000) });
  }

  private async read(run: Run, step: PlanStep): Promise<void> {
    const raw = step.raw;
    const timeout = Math.min(raw.timeoutMs ?? 1000, Math.max(0, run.deadlineMono - mono()));
    let timer: NodeJS.Timeout | undefined;
    try {
      const timedOut = new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new StepFailed(new BhmsError("DEADLINE_EXCEEDED", `read of ${step.device!.deviceId}.${step.property!.name} timed out`, { mayHaveActed: true, hint: "check the sensor" }).toOperationError())), timeout);
      });
      const observation = await Promise.race([
        this.server.observations.read(step.device!, step.property!.name, { maxAgeMs: raw.maxAgeMs, fresh: raw.fresh, principal: run.principal }),
        timedOut,
      ]);
      run.variables[raw.saveAs] = observation;
    } catch (e) {
      if (e instanceof BhmsError) throw new StepFailed(e.toOperationError());
      throw e;
    } finally {
      clearTimeout(timer);
    }
  }

  private async waitUntil(run: Run, step: PlanStep): Promise<void> {
    const raw = step.raw;
    const poll = Math.max(10, raw.pollMs ?? 100);
    const until = Math.min(mono() + raw.timeoutMs, run.deadlineMono);
    const fresh = step.property!.getter !== undefined;
    for (;;) {
      let observation: Observation | undefined;
      try {
        observation = await this.server.observations.read(step.device!, step.property!.name, { fresh: fresh || undefined, principal: run.principal });
      } catch (e) {
        if (!(e instanceof BhmsError)) throw e;
      }
      if (observation && observation.quality === "valid" && evaluate(raw.predicate, { ...run.variables, observed: observation })) {
        if (raw.saveAs) run.variables[raw.saveAs] = observation;
        return;
      }
      if (mono() + poll > until) {
        throw new StepFailed(new BhmsError("DEADLINE_EXCEEDED", `waitUntil on ${step.device!.deviceId}.${step.property!.name} timed out after ${raw.timeoutMs} ms`, {
          mayHaveActed: true, hint: "the condition never held on a valid observation (BHMS-PRG-013)",
        }).toOperationError());
      }
      run.wake.clear();
      await run.wake.wait(poll);
      if (run.shutdown) throw new Shutdown();
      if (run.halted) throw new Halted();
    }
  }

  // ------------------------------------------------------------------------------------------------ cancel, stop, lease loss

  /** `operations/cancel` on a program: no further steps; the running child is cancelled (BHMS-PRG-014). */
  cancel(rec: OperationRecord, reason: string | undefined): void {
    if (rec.terminal) return;
    const j = this.server.journal;
    if (rec.op.cancel.state === "none" || rec.op.cancel.state === "refused") j.setCancel(rec, "requested", { reason });
    const run = this.runs.get(rec.id);
    if (!run) return;
    run.halted = true;
    run.wake.set();
    if (run.child && !run.child.settled) this.server.executor.cancel(run.child, reason ?? "program canceled");
  }

  /** Stop every running program with steps on `deviceId` (BHMS-PRG-014, BHMS-AUTH-021). */
  stopDevice(deviceId: string, reason: string): void {
    for (const run of [...this.runs.values()]) {
      if (!(run.plan.info.devices as string[]).includes(deviceId) || run.rec.settled) continue;
      try {
        this.server.journal.annotate(run.rec, "stop", `stop of ${deviceId}: ${reason}`);
        if (run.rec.op.cancel.state === "none" || run.rec.op.cancel.state === "refused") this.server.journal.setCancel(run.rec, "requested", { reason: `stop: ${reason}` });
      } catch (e) {
        if (!(e instanceof StoreError)) throw e;
        this.server.journalFailed(e);
      }
      run.halted = true;
      run.wake.set();
      if (run.child && !run.child.settled) this.server.executor.cancel(run.child, `stop: ${reason}`);
    }
  }

  /** No new step starts under an ended lease (BHMS-LSE-012): wake runs so their boundary check fails. */
  onLeaseEnd(lease: Lease): void {
    for (const run of this.runs.values()) if (run.leaseId === lease.leaseId) run.wake.set();
  }

  /** Leave running programs in flight (they are settled at restart) and stop their loops. */
  async close(timeoutMs = 1000): Promise<void> {
    const tasks = [...this.runs.values()].map((r) => { r.shutdown = true; r.wake.set(); return r.task; }).filter((t): t is Promise<void> => t !== undefined);
    await Promise.race([Promise.allSettled(tasks), new Promise((r) => setTimeout(r, timeoutMs))]);
  }

  // ------------------------------------------------------------------------------------------------ restart (BHMS-PRG-017)

  recoverAfterRestart(): void {
    const j = this.server.journal;
    for (const rec of [...j.records.values()]) {
      if (rec.op.kind === "program" && (rec.state === "accepted" || rec.state === "dispatching" || rec.state === "running")) this.settleAfterRestart(rec);
    }
    for (const rec of [...j.records.values()]) {
      if (rec.op.kind === "program" && rec.state === "unknown") this.settleAfterReconcile(rec.id);
    }
  }

  private stepSummary(rec: OperationRecord): { last?: number; children: OperationRecord[] } {
    const steps = rec.data.history.filter((h) => h.kind === "step");
    const children = this.server.journal.children(rec.id);
    const byId = new Map(children.map((c) => [c.id, c]));
    let last: number | undefined;
    steps.forEach((entry, i) => {
      const child = entry.childOperationId ? byId.get(entry.childOperationId) : undefined;
      if (i + 1 < steps.length || child?.state === "completed") last = entry.stepIndex;
    });
    return { last, children };
  }

  private settleAfterRestart(rec: OperationRecord): void {
    const j = this.server.journal;
    const kids = j.children(rec.id);
    if (rec.state === "accepted") {
      if (kids.length === 0) {
        j.transition(rec, "rejected", { error: new BhmsError("INTERNAL", "the server restarted before the program's first step", { mayHaveActed: false, hint: "no step ran; run the program again" }).toOperationError() });
        return;
      }
      j.transition(rec, "dispatching"); // a child exists although the program never recorded dispatching
    }
    const { last, children } = this.stepSummary(rec);
    if (children.some((c) => c.state === "unknown")) {
      j.transition(rec, "unknown", { error: unknownError("the server restarted during the program while a step's outcome is unknown") });
      return;
    }
    this.failInternal(rec, last, children, "state", undefined);
  }

  private failInternal(rec: OperationRecord, last: number | undefined, children: OperationRecord[], kind: "state" | "reconciliation", detail: string | undefined): void {
    const acted = this.acted(children);
    const where = last !== undefined ? `the last completed step is stepIndex ${last}` : "no step completed";
    const error = new BhmsError("INTERNAL", "server restarted during the program", {
      mayHaveActed: acted,
      hint: `${where}; inspect the child operations (operations/list parentOperationId) before running a compensating program; programs are never resumed`,
    }).toOperationError();
    const o = programOutcome(children);
    this.server.journal.transition(rec, "failed", { error, kind, detail, effect: o.effect, evidence: o.evidence, proof: acted ? undefined : "no effectful step was dispatched" });
  }

  /** When the `unknown` children of an `unknown` program are all reconciled, settle the program the same way (BHMS-PRG-017). */
  settleAfterReconcile(parentId: string): void {
    const parent = this.server.journal.get(parentId);
    if (!parent || parent.state !== "unknown" || parent.op.kind !== "program") return;
    const { last, children } = this.stepSummary(parent);
    if (children.some((c) => c.state === "unknown")) return;
    this.failInternal(parent, last, children, "reconciliation", "all unknown children were reconciled; the program is settled from its step history");
  }
}

export type { TransitionOptions };
