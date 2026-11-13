/**
 * Observations: acquisition, retention, freshness and rate-limited subscriptions (spec/bhms/05-observations.md).
 *
 * {@link ObservationHub} owns one retained sample per `(deviceId, property)` and turns samples into `Observation`
 * objects at response time:
 *
 * - a getter that throws, times out or returns `undefined`/`null` (or a value that fails the property schema) yields
 *   `quality: "invalid"` and `value: null`: never zero, a default or the previous sample (BHMS-OBS-001);
 * - `ageMs` is computed on the monotonic clock from the *start* of the acquisition plus the declared bounded latency, so
 *   it never under-states the age and wall-clock steps cannot shrink it; re-reading never refreshes it (BHMS-OBS-003);
 * - `sequence` increases by one per acquisition; `epoch` is minted per process because sequences restart with it
 *   (BHMS-OBS-004); numeric values carry `unit` (BHMS-OBS-005);
 * - `properties/read` honours `maxAgeMs` and `fresh` or answers `STALE` naming the parameter (BHMS-OBS-010); a fresh
 *   acquisition of a `transaction` property needs an `invoke` scope on `<deviceId>/<property>` and, when the property
 *   requires one, a lease (BHMS-OBS-011, BHMS-AUTH-012); an unknown property is `INVALID_ARGUMENT` listing the property
 *   names (BHMS-OBS-012);
 * - {@link ObservationHub.requireFresh} enforces an action's `requiresFresh` (BHMS-OBS-030);
 * - when an effectful operation settles on a device, retained samples of its on-demand properties are dropped so the next
 *   read acquires a new one (BHMS-OBS-006);
 * - subscriptions deliver at most once per `max(minIntervalMs, capabilities.observations.minIntervalMs)` per subscriber,
 *   with the latest sample sent when the floor ends, except that a change of `quality` is delivered at once
 *   (BHMS-OBS-021, BHMS-LIF-043). While a property with a getter and `readEffect: "none"` has subscribers it is polled
 *   at that rate; `transaction` properties are never polled (BHMS-OBS-022). Values over 64 KiB are never sent
 *   (BHMS-EVT-030).
 *
 * Thread-safety: single event loop.
 */
import { randomBytes } from "node:crypto";
import { BhmsError } from "../errors.js";
import type { Observation } from "../generated/types.js";
import { SchemaValidator } from "../schema.js";
import { canonical } from "../canonical.js";
import { Reading } from "./context.js";
import type { Device, PropertySpec } from "./device.js";
import type { Principal } from "./authority.js";
import type { DeviceServer } from "./server.js";
import { iso, mono } from "./time.js";

interface Sample {
  value: unknown;
  quality: "valid" | "stale" | "invalid" | "unknown";
  startedMono: number;
  latencyMs: number;
  receivedMs: number;
  sequence: number;
  uncertainty?: number;
  source?: string;
}

interface Subscriber {
  deliver: (n: { deviceId: string; property: string; observation: Observation }) => void;
  floorMs: number;
  lastSentMono: number;
  lastQuality?: string;
  timer?: NodeJS.Timeout;
}

interface Slot {
  sample?: Sample;
  sequence: number;
  subs: Set<Subscriber>;
  poller?: NodeJS.Timeout;
  pollMs?: number;
}

export const MAX_NOTIFICATION_BYTES = 64 * 1024;

export class ObservationHub {
  readonly epoch = `boot-${randomBytes(4).toString("hex")}`;
  private readonly slots = new Map<string, Slot>();
  private readonly validators = new WeakMap<PropertySpec, SchemaValidator>();

  constructor(private readonly server: DeviceServer, readonly minIntervalMs: number) {}

  private slot(deviceId: string, prop: string): Slot {
    const key = `${deviceId}\0${prop}`;
    let s = this.slots.get(key);
    if (!s) {
      s = { sequence: 0, subs: new Set() };
      this.slots.set(key, s);
    }
    return s;
  }

  spec(device: Device, prop: string): PropertySpec {
    const spec = device.properties.get(prop);
    if (!spec) {
      throw new BhmsError("INVALID_ARGUMENT", `${device.deviceId} has no property ${JSON.stringify(prop)}`, {
        field: "property", bound: [...device.properties.keys()].sort(), hint: `the properties are: ${[...device.properties.keys()].sort().join(", ") || "(none)"}`,
      });
    }
    return spec;
  }

  // ------------------------------------------------------------------------------------------------ acquisition

  private validator(spec: PropertySpec): SchemaValidator {
    let v = this.validators.get(spec);
    if (!v) {
      v = new SchemaValidator(spec.schema);
      this.validators.set(spec, v);
    }
    return v;
  }

  private newSample(spec: PropertySpec, slot: Slot, started: number, value: unknown, o: { quality?: Sample["quality"]; latencyMs?: number; uncertainty?: number; source?: string }): Sample {
    let quality = o.quality ?? "valid";
    let v = value;
    if (v === undefined || v === null) {
      quality = quality === "unknown" ? "unknown" : "invalid";
      v = null;
    } else if (quality !== "invalid" && quality !== "unknown" && !this.validator(spec).isValid(v)) {
      quality = "invalid"; // a value outside the declared schema is a failed measurement, not a value (BHMS-OBS-001)
      v = null;
    }
    if (quality === "invalid" || quality === "unknown") v = null;
    const s: Sample = { value: v, quality, startedMono: started, latencyMs: Math.max(0, o.latencyMs ?? 0), receivedMs: Date.now(), sequence: ++slot.sequence };
    if (o.uncertainty !== undefined) s.uncertainty = o.uncertainty;
    if (o.source !== undefined) s.source = o.source;
    return s;
  }

  /** Acquire one sample from the getter (bounded by the property's timeout) and retain it. */
  async acquire(device: Device, spec: PropertySpec): Promise<Sample> {
    const slot = this.slot(device.deviceId, spec.name);
    const started = mono();
    let sample: Sample;
    try {
      const got = await Promise.race([
        Promise.resolve().then(() => spec.getter!()),
        new Promise<never>((_, reject) => { setTimeout(() => reject(new Error("acquisition timed out")), spec.timeoutMs).unref(); }),
      ]);
      sample = got instanceof Reading
        ? this.newSample(spec, slot, started, got.value, got.options)
        : this.newSample(spec, slot, started, got, {});
      if (sample.quality !== "invalid") device.reportAlive();
    } catch {
      sample = this.newSample(spec, slot, started, null, { quality: "invalid" });
    }
    slot.sample = sample;
    this.emit(device, spec, slot);
    return sample;
  }

  /** Retain a value the device pushed and return its observation. */
  async publish(device: Device, prop: string, value: unknown, o: { quality?: Sample["quality"]; uncertainty?: number; source?: string; latencyMs?: number } = {}): Promise<Observation> {
    const spec = this.spec(device, prop);
    const slot = this.slot(device.deviceId, prop);
    const sample = this.newSample(spec, slot, mono(), value, o);
    slot.sample = sample;
    device.reportAlive();
    this.emit(device, spec, slot);
    return this.present(spec, sample);
  }

  /** The `Observation` of a sample as of now. */
  present(spec: PropertySpec, s: Sample): Observation {
    const ageMs = Math.ceil(mono() - s.startedMono + s.latencyMs);
    let quality = s.quality;
    if (quality === "valid" && spec.validityMs !== undefined && ageMs > spec.validityMs) quality = "stale";
    const unit = typeof spec.schema["x-bhms-unit"] === "string" ? (spec.schema["x-bhms-unit"] as string) : undefined;
    const obs: Observation = {
      value: quality === "invalid" || quality === "unknown" ? null : s.value,
      ...(unit !== undefined ? { unit } : {}),
      evidence: spec.evidence, quality,
      acquiredAt: iso(s.receivedMs - s.latencyMs), receivedAt: iso(s.receivedMs), ageMs, sequence: s.sequence, epoch: this.epoch,
    };
    if (s.uncertainty !== undefined) obs.uncertainty = s.uncertainty;
    if (s.source !== undefined) obs.source = s.source;
    return obs;
  }

  private unknown(spec: PropertySpec): Observation {
    const unit = typeof spec.schema["x-bhms-unit"] === "string" ? (spec.schema["x-bhms-unit"] as string) : undefined;
    return { value: null, ...(unit !== undefined ? { unit } : {}), evidence: spec.evidence, quality: "unknown", acquiredAt: null, receivedAt: iso(Date.now()), ageMs: null, sequence: 0, epoch: this.epoch };
  }

  /** `properties/read` semantics (§5.2); `internal` reads run under an operation's own authority. */
  async read(device: Device, prop: string, o: { maxAgeMs?: number; fresh?: boolean; principal?: Principal; internal?: boolean } = {}): Promise<Observation> {
    const spec = this.spec(device, prop);
    const slot = this.slot(device.deviceId, prop);
    const requested = mono();
    let sample = slot.sample;
    if (!o.fresh && sample) {
      const current = this.present(spec, sample);
      if (o.maxAgeMs === undefined || (current.ageMs !== null && current.ageMs <= o.maxAgeMs)) return current;
    }
    if (!spec.getter) {
      if (!sample) return this.unknown(spec);
      const [what, bound] = o.fresh ? ["fresh", true] : ["maxAgeMs", o.maxAgeMs];
      throw new BhmsError("STALE", `${device.deviceId}.${prop} cannot be acquired on demand and its latest value does not satisfy ${what}`, {
        field: what as string, bound, hint: "this property is published by the device; read it without fresh/maxAgeMs, or subscribe to it",
      });
    }
    if (!o.internal) this.authorizeAcquisition(device, spec, o.principal);
    sample = await this.acquire(device, spec);
    const observation = this.present(spec, sample);
    if (o.fresh && sample.startedMono < requested) {
      throw new BhmsError("STALE", `${device.deviceId}.${prop}: no acquisition started after the request`, { field: "fresh", bound: true, hint: "retry; the device did not acquire a new value" });
    }
    if (o.maxAgeMs !== undefined && (observation.ageMs === null || observation.ageMs > o.maxAgeMs)) {
      throw new BhmsError("STALE", `${device.deviceId}.${prop}: the newest observation is ${observation.ageMs} ms old, above maxAgeMs ${o.maxAgeMs}`, {
        field: "maxAgeMs", bound: o.maxAgeMs, hint: "ask for a larger maxAgeMs or check the device's acquisition latency",
      });
    }
    return observation;
  }

  /** BHMS-OBS-011 / BHMS-AUTH-012: a transaction acquisition is an effect and needs an invoke scope and the lease. */
  private authorizeAcquisition(device: Device, spec: PropertySpec, principal: Principal | undefined): void {
    if (spec.readEffect !== "transaction" || !principal) return;
    if (!principal.canInvoke(device.deviceId, spec.name, device.capabilities)) {
      throw new BhmsError("UNAUTHORIZED", `a fresh read of ${device.deviceId}.${spec.name} is a device transaction and needs an invoke scope`, {
        field: "property", hint: `missing scope invoke:${device.deviceId}/${spec.name}`,
      });
    }
    if (spec.requiresLease && !this.server.leases.holds(principal.id, spec.resources)) {
      throw new BhmsError("LEASE_REQUIRED", `${device.deviceId}.${spec.name} needs a lease on ${spec.resources.join(", ")}`, {
        field: "property", bound: [...spec.resources], hint: `acquire a lease covering ${spec.resources.join(", ")} with leases/acquire first`,
      });
    }
  }

  /** Hold a valid observation no older than `maxAgeMs` for each requirement, or refuse with `STALE` (BHMS-OBS-030). */
  async requireFresh(device: Device, requirements: ReadonlyArray<{ property: string; maxAgeMs: number }>, principal: Principal | undefined): Promise<Record<string, Observation>> {
    const held: Record<string, Observation> = {};
    for (const [index, req] of requirements.entries()) {
      const spec = this.spec(device, req.property);
      const slot = this.slot(device.deviceId, req.property);
      let obs = slot.sample ? this.present(spec, slot.sample) : undefined;
      const ok = (o?: Observation): boolean => o !== undefined && o.quality === "valid" && o.ageMs !== null && o.ageMs <= req.maxAgeMs;
      if (!ok(obs) && spec.getter && (spec.readEffect !== "transaction" || !principal || principal.canInvoke(device.deviceId, spec.name, device.capabilities))) {
        obs = this.present(spec, await this.acquire(device, spec));
      }
      if (!ok(obs)) {
        throw new BhmsError("STALE", `${device.deviceId}.${req.property} has no valid observation within ${req.maxAgeMs} ms`, {
          field: `requiresFresh[${index}]`, bound: { property: req.property, maxAgeMs: req.maxAgeMs },
          hint: `${req.property} is ${obs?.quality ?? "unknown"} (age ${obs?.ageMs ?? null} ms); restore the sensor or wait for a valid reading before retrying`,
        });
      }
      held[req.property] = obs!;
    }
    return held;
  }

  /** BHMS-OBS-006: after an effectful operation settles, on-demand properties must be acquired anew. */
  afterSettled(device: Device): void {
    for (const spec of device.properties.values()) {
      if (spec.getter) {
        const slot = this.slots.get(`${device.deviceId}\0${spec.name}`);
        if (slot) slot.sample = undefined;
      }
    }
  }

  // ------------------------------------------------------------------------------------------------ subscriptions

  /** Deliver `{deviceId, property, observation}` on new acquisitions; returns the unsubscribe function. */
  subscribe(device: Device, prop: string, minIntervalMs: number | undefined, deliver: Subscriber["deliver"]): () => void {
    const spec = this.spec(device, prop);
    const slot = this.slot(device.deviceId, prop);
    const rate = spec.maxRateHz ? 1000 / spec.maxRateHz : 0;
    const sub: Subscriber = { deliver, floorMs: Math.max(minIntervalMs ?? 0, this.minIntervalMs, rate), lastSentMono: Number.NEGATIVE_INFINITY };
    slot.subs.add(sub);
    this.retune(device, spec, slot);
    if (slot.sample) this.sendTo(device, spec, slot, sub);
    return () => {
      slot.subs.delete(sub);
      if (sub.timer) clearTimeout(sub.timer);
      this.retune(device, spec, slot);
    };
  }

  private sendTo(device: Device, spec: PropertySpec, slot: Slot, sub: Subscriber): void {
    if (!slot.sample) return;
    const obs = this.present(spec, slot.sample);
    const qualityChanged = sub.lastQuality !== undefined && sub.lastQuality !== obs.quality;
    const wait = sub.lastSentMono + sub.floorMs - mono();
    if (!qualityChanged && wait > 0) {
      if (!sub.timer) {
        sub.timer = setTimeout(() => { sub.timer = undefined; this.sendTo(device, spec, slot, sub); }, Math.ceil(wait));
        sub.timer.unref();
      }
      return;
    }
    if (sub.timer) { clearTimeout(sub.timer); sub.timer = undefined; }
    if (canonical(obs).length > MAX_NOTIFICATION_BYTES) return; // BHMS-EVT-030: values this large go by reference
    sub.lastSentMono = mono();
    sub.lastQuality = obs.quality;
    sub.deliver({ deviceId: device.deviceId, property: spec.name, observation: obs });
  }

  private emit(device: Device, spec: PropertySpec, slot: Slot): void {
    for (const sub of [...slot.subs]) this.sendTo(device, spec, slot, sub);
  }

  /** Poll while there are subscribers (never a transaction property, BHMS-OBS-022). */
  private retune(device: Device, spec: PropertySpec, slot: Slot): void {
    const pollable = spec.getter !== undefined && spec.readEffect === "none" && slot.subs.size > 0;
    const interval = pollable ? Math.min(...[...slot.subs].map((s) => s.floorMs)) : undefined;
    if (slot.poller && slot.pollMs !== interval) { clearInterval(slot.poller); slot.poller = undefined; }
    if (interval !== undefined && !slot.poller) {
      slot.pollMs = interval;
      slot.poller = setInterval(() => { void this.acquire(device, spec); }, Math.max(1, interval));
      slot.poller.unref();
    }
  }

  close(): void {
    for (const slot of this.slots.values()) {
      if (slot.poller) clearInterval(slot.poller);
      for (const s of slot.subs) if (s.timer) clearTimeout(s.timer);
      slot.subs.clear();
    }
  }
}
