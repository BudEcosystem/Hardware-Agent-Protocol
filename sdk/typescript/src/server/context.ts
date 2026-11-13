/**
 * What device code receives and throws: {@link ActionContext}, outcomes and readings.
 *
 * An action handler gets an {@link ActionContext} as its first argument:
 *
 * - `ctx.cancelled` is an `AbortSignal` aborted when `operations/cancel`, a duration bound, a lease loss with
 *   `onLeaseLoss: "cancel"`/`"hold"`, or `stop` asks the action to end. Honour it and throw {@link Canceled} once the device
 *   has observably stopped (`cancel.state: "confirmed"`, BHMS-OPS-052); returning normally means the action completed
 *   (completion may win the race). `await ctx.waitCancelled(ms)` sleeps and returns true when cancelled meanwhile.
 * - `await ctx.running()` records `running` ("the device reported that it is executing", §6.3).
 * - `await ctx.verify("position", (v) => Math.abs(v - target) < 0.1)` takes a fresh measurement of a property and, when it
 *   is `measured`, `valid` and passes the check, attaches it as evidence: only then is the effect `verified`
 *   (BHMS-DEV-031, BHMS-OPS-006). Returns the measured value (`null` when invalid).
 * - `ctx.read(prop)`, `ctx.publish(prop, value)`, `ctx.emit(type, data)`.
 *
 * Outcomes other than a normal return:
 *
 * - `throw new Canceled({ effect })`: terminated after a cancel request (state `canceled`);
 * - `throw new DeviceFault("stalled", { partial: "moved 2 mm" })`: the device reported a fault while acting (`failed` with
 *   `DEVICE_FAULT`, `mayHaveActed: true` unless `proof` names device evidence of no effect, BHMS-ERR-012);
 * - any other exception: the outcome is `unknown` (`DEADLINE_EXCEEDED`, BHMS-OPS-004): a handler bug after dispatch
 *   cannot prove what the device did.
 *
 * A property getter returns a bare value (`valid`, the declared evidence, acquired now) or a {@link Reading}; a getter
 * that throws, times out or returns `undefined`/`null` produces `quality: "invalid"` with `value: null` — never a
 * substitute value (BHMS-OBS-001).
 *
 * Thread-safety: a context belongs to one operation on the server's event loop.
 */
import type { Observation } from "../generated/types.js";

export type EffectCertainty = "none" | "verified" | "unverified" | "unknown";

/** Thrown by a handler that terminated because of a cancellation request. */
export class Canceled extends Error {
  readonly effect: EffectCertainty;
  readonly detail?: string;
  constructor(options: { effect?: EffectCertainty; detail?: string } = {}) {
    super(options.detail ?? "canceled");
    this.name = "Canceled";
    this.effect = options.effect ?? "unknown";
    this.detail = options.detail;
  }
}

/** Thrown by a handler when the device reported a fault while acting. */
export class DeviceFault extends Error {
  readonly partial?: string;
  readonly proof?: string;
  constructor(message: string, options: { partial?: string; proof?: string } = {}) {
    super(message);
    this.name = "DeviceFault";
    this.partial = options.partial;
    this.proof = options.proof;
  }
}

/** One acquisition of a property with its own bounded latency and quality. */
export class Reading {
  constructor(
    readonly value: unknown,
    readonly options: { latencyMs?: number; quality?: "valid" | "stale" | "invalid" | "unknown"; uncertainty?: number; source?: string } = {},
  ) {}
}

/** The answer of a `reconcile` hook (BHMS-OPS-005): what the device's own records say about an `unknown` operation. */
export interface Reconciled {
  state: "completed" | "failed" | "canceled";
  /** Names the evidence (a device query, a command log...): recorded in the `reconciliation` history entry. */
  evidence: string;
  result?: unknown;
  effect?: EffectCertainty;
  message?: string;
  mayHaveActed?: boolean;
}

export interface ActionContext {
  readonly operationId: string;
  readonly deviceId: string;
  readonly action: string;
  /** Aborted on cancel, duration bound, lease loss or stop. */
  readonly cancelled: AbortSignal;
  /** The reason given with the cancellation, when there is one. */
  readonly cancelReason: string | undefined;
  /** Milliseconds until the operation's deadline or `maxDurationMs`, whichever is first. */
  readonly remainingMs: number;
  running(detail?: string): Promise<void>;
  /** Sleep `ms`; resolves `true` if a cancellation arrived first. */
  waitCancelled(ms: number): Promise<boolean>;
  verify(property: string, check: (value: unknown) => boolean): Promise<unknown>;
  read(property: string): Promise<Observation>;
  publish(property: string, value: unknown, options?: { quality?: "valid" | "stale" | "invalid" | "unknown"; latencyMs?: number }): Promise<Observation>;
  emit(type: string, data?: Record<string, unknown>, options?: { severity?: "info" | "warning" | "error" | "critical"; message?: string }): void;
}
