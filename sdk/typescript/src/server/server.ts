/**
 * `DeviceServer`: a complete, honest BHMS server for devices declared with plain method calls.
 *
 * A working server in about fifteen lines:
 *
 * ```ts
 * import { DeviceServer, range } from "@bhms/sdk";
 *
 * const srv = new DeviceServer("bench-stage");
 * const stage = srv.device("stage-z", { capabilities: ["bhms.axis.linear"], resources: ["stage-z"] });
 * stage.property("position", { unit: "um", evidence: "measured" }, () => encoder.read());
 * stage.action("move_to", {
 *   effect: "reversible", idempotency: "absolute", maxDurationMs: 5000, cancel: "supported",
 *   input: { target: range(0, 200, "um") }, output: { position: "um" },
 * }, async (ctx, { target }) => {
 *   await motor.move(target as number, ctx.cancelled);
 *   return { position: await ctx.verify("position", (v) => Math.abs((v as number) - (target as number)) < 0.5) };
 * });
 * await srv.run();   // stdio by default; srv.run("unix:/run/stage.sock"), srv.run("ws://127.0.0.1:8765")
 * ```
 *
 * It implements every method of the schema's `x-bhms-methods` except `programs/*`: `server/discover`, `devices/*`,
 * `properties/read`, `actions/invoke`, `operations/*`, `stop`, `subscriptions/listen`, `leases/*` and `events/read`, over
 * the durable runtime in this directory (an append-only JSON-lines journal under `stateDir`, recovered before the first
 * request is answered, BHMS-OPS-080). The `programs` capability is not advertised, so `programs/*` answers `UNSUPPORTED`
 * naming it (BHMS-LIF-013).
 *
 * Authentication comes from the transport (BHMS-SEC-001, {@link Policy}): the stdio parent and same-user Unix peers are
 * `admin`; WebSocket clients present a bearer token. TCP listens on loopback only.
 *
 * Thread-safety: one event loop; declare devices before `start()` (later declarations are announced with
 * `notifications/devices/listChanged`).
 */
import { randomBytes } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { BhmsError, JsonRpcError } from "../errors.js";
import type { ActionsInvokeParams, DeviceStop, DevicesListFilter, Event } from "../generated/types.js";
import { METHODS, PROTOCOL_VERSION } from "../generated/types.js";
import { Session, type RequestContext, type Transport, type HandlerResult, METHOD_NOT_FOUND } from "../jsonrpc/session.js";
import { loadSchema, validateDef } from "../schema.js";
import { listenUnix, type Listener } from "../transport/socket.js";
import { stdioServerTransport } from "../transport/stdio.js";
import { listenWebSocket, type WsListener } from "../transport/websocket.js";
import { Principal, defaultPolicy, type Policy } from "./authority.js";
import { Device, DescriptionError, type DeviceOptions } from "./device.js";
import { EventLog } from "./events.js";
import { Executor } from "./executor.js";
import { LeaseManager, leaseWire, type Lease } from "./leases.js";
import { listen } from "./listen.js";
import { ObservationHub } from "./observations.js";
import { DEFAULT_PROGRAM_LIMITS, ProgramRunner, type ProgramLimits } from "./programs.js";
import { Journal } from "./operations.js";
import { JournalStore, MemoryStore, StoreError, type Store } from "./store.js";
import { sleep } from "./time.js";

export type ExtensionHandler = (params: Record<string, unknown>, ctx: RequestContext) => Promise<Record<string, unknown>>;

export interface DeviceServerOptions {
  version?: string;
  title?: string;
  /** Guidance for models; untrusted text (BHMS-SEC-020). */
  instructions?: string;
  /** Directory of the journal (default `$BHMS_STATE_DIR`, else `$XDG_STATE_HOME/bhms`, else `~/.local/state/bhms`). */
  stateDir?: string;
  /** `"memory"` for a non-durable store (new epoch every start), or a custom {@link Store}. Default: durable journal. */
  store?: "memory" | Store;
  policy?: Policy;
  /** Bearer token granting `admin` over WebSocket (default `$BHMS_TOKEN`). */
  token?: string;
  /** How long keys and settled operations are kept (>= 86 400, BHMS-OPS-034). */
  keyRetentionS?: number;
  eventRetentionS?: number;
  maxWaitMs?: number;
  maxPageSize?: number;
  leaseMinTtlMs?: number;
  leaseMaxTtlMs?: number;
  leaseMaxWaitMs?: number;
  /** Queued operations per device before `BUSY`. */
  queueLimit?: number;
  observationMinIntervalMs?: number;
  /** How long a cancelled handler may take to terminate after a duration bound. */
  cancelGraceMs?: number;
  maxMessageBytes?: number;
  /** Serve `programs/*` with a durable registry (default true). */
  programs?: boolean;
  /** Program limits (§8.1); servers may advertise lower values than the defaults, never higher. */
  programLimits?: Partial<ProgramLimits>;
  /** Validate every result against the schema before sending (conformance mode). */
  strict?: boolean;
  log?: (message: string) => void;
}

function defaultStateDir(): string {
  if (process.env.BHMS_STATE_DIR) return process.env.BHMS_STATE_DIR;
  return join(process.env.XDG_STATE_HOME || join(homedir(), ".local", "state"), "bhms");
}

const EXTENSION_NAME = /^(x-[a-z0-9-]+\/[a-z0-9_-]+|[a-z0-9.-]+\/[a-z0-9-]+\/[a-z0-9_-]+)$/;

function limit(requested: number | undefined, max: number, def = 100): number {
  return Math.min(requested ?? Math.min(def, max), max);
}

function encodeCursor(kind: string, value: string): string {
  return Buffer.from(`${kind}:${value}`).toString("base64url");
}

function decodeCursor(kind: string, cursor: string): string {
  const text = Buffer.from(cursor, "base64url").toString("utf8");
  if (!text.startsWith(`${kind}:`) || encodeCursor(kind, text.slice(kind.length + 1)) !== cursor) {
    throw new BhmsError("INVALID_ARGUMENT", "malformed or foreign cursor", { field: "cursor", hint: "pass the nextCursor of the previous call unchanged" });
  }
  return text.slice(kind.length + 1);
}

function capabilityMatches(pattern: string, caps: readonly string[]): boolean {
  return pattern.endsWith(".*") ? caps.some((c) => c.startsWith(pattern.slice(0, -1))) : caps.includes(pattern);
}

/** Whether a `DeviceSummary` satisfies a `devices/list` filter (BHMS §4.2). */
export function summaryMatches(f: DevicesListFilter | undefined, s: { capabilities: string[]; tags: string[]; name: string; summary: string }, status: string): boolean {
  if (!f) return true;
  if (f.capability !== undefined && !capabilityMatches(f.capability, s.capabilities)) return false;
  if (f.tag !== undefined && !s.tags.includes(f.tag)) return false;
  if (f.status !== undefined && f.status !== status) return false;
  if (f.text !== undefined) {
    const needle = f.text.toLowerCase();
    if (![s.name, s.summary, ...s.tags].some((h) => h.toLowerCase().includes(needle))) return false;
  }
  return true;
}

function waitError(field: string, value: number, max: number): BhmsError {
  return new BhmsError("OUT_OF_RANGE", `${field} ${value} is above the maximum ${max}`, { field, bound: { maximum: max }, hint: `use ${field} of at most ${max}` });
}

export class DeviceServer {
  readonly devices = new Map<string, Device>();
  readonly policy: Policy;
  readonly sessions = new Set<Session>();
  readonly deviceListeners = new Set<() => void>();
  readonly closingController = new AbortController();
  private readonly extensionInfo: Record<string, Record<string, unknown>> = {};
  private readonly extensionMethods = new Map<string, ExtensionHandler>();
  private listeners: Array<Listener | WsListener> = [];
  private readonly lifecycleTimers = new Set<NodeJS.Timeout>();
  private started = false;
  private closed = false;
  private journalOk = true;
  readonly opts: Required<Pick<DeviceServerOptions, "version" | "keyRetentionS" | "eventRetentionS" | "maxWaitMs" | "maxPageSize" | "leaseMinTtlMs" | "leaseMaxTtlMs" | "leaseMaxWaitMs" | "queueLimit" | "observationMinIntervalMs" | "cancelGraceMs" | "maxMessageBytes" | "strict">> & DeviceServerOptions;

  // set by start()
  store!: Store;
  journal!: Journal;
  events!: EventLog;
  observations!: ObservationHub;
  leases!: LeaseManager;
  executor!: Executor;
  programs?: ProgramRunner;
  readonly programLimits: ProgramLimits;

  constructor(readonly name: string, options: DeviceServerOptions = {}) {
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(name)) throw new RangeError(`server name ${JSON.stringify(name)} must be 1-128 characters of [A-Za-z0-9._-]`);
    if ((options.keyRetentionS ?? 7 * 86400) < 86_400) throw new RangeError("keyRetentionS must be at least 86400 (BHMS-OPS-034)");
    this.opts = {
      version: "0.1.0", keyRetentionS: 7 * 86400, eventRetentionS: 7 * 86400, maxWaitMs: 60_000, maxPageSize: 500, leaseMinTtlMs: 1000,
      leaseMaxTtlMs: 600_000, leaseMaxWaitMs: 30_000, queueLimit: 64, observationMinIntervalMs: 50, cancelGraceMs: 1000,
      maxMessageBytes: 4_194_304, strict: false, ...options,
    };
    this.programLimits = { ...DEFAULT_PROGRAM_LIMITS, ...options.programLimits };
    const token = options.token ?? process.env.BHMS_TOKEN;
    this.opts.token = token;
    const base = options.policy ?? defaultPolicy;
    this.policy = base;
  }

  // ------------------------------------------------------------------------------------------------ declaration

  /** Declare a device (see {@link Device}). */
  device(deviceId: string, options: DeviceOptions = {}): Device {
    if (this.devices.has(deviceId)) throw new RangeError(`device ${JSON.stringify(deviceId)} is already declared (BHMS-DEV-001)`);
    const dev = new Device(this, deviceId, options);
    this.devices.set(deviceId, dev);
    if (this.started) {
      dev.description();
      this.deviceChanged(dev);
    }
    return dev;
  }

  /**
   * Advertise extension `key` (`"<prefix>/<name>"`, BHMS-LIF-070) under `capabilities.extensions` and register its methods
   * (`x-<name>/<method>` or `<prefix>/<name>/<method>`; handlers get the raw params). Declare before `start()`. Extensions
   * cannot weaken core guarantees (BHMS-LIF-071).
   */
  extension(key: string, info: Record<string, unknown>, methods: Record<string, ExtensionHandler>): void {
    if (this.started) throw new Error("declare extensions before start()");
    this.extensionInfo[key] = info;
    for (const [m, h] of Object.entries(methods)) {
      if (!EXTENSION_NAME.test(m)) throw new RangeError(`${JSON.stringify(m)} is not a valid extension method name (<prefix>/<name>/<method> or x-<name>/<method>, BHMS-LIF-070)`);
      this.extensionMethods.set(m, h);
    }
  }

  resources(): ReadonlySet<string> {
    return new Set([...this.devices.values()].flatMap((d) => d.resources));
  }

  log(message: string): void {
    (this.opts.log ?? ((m: string) => { process.stderr.write(`[bhms ${this.name}] ${m}\n`); }))(message);
  }

  get closing(): boolean { return this.closed; }
  get closingSignal(): AbortSignal { return this.closingController.signal; }
  get epoch(): string { return this.store.epoch; }

  // ------------------------------------------------------------------------------------------------ lifecycle

  private openStore(): Store {
    const s = this.opts.store;
    if (s === "memory") return new MemoryStore();
    if (s !== undefined) return s;
    return new JournalStore(join(this.opts.stateDir ?? defaultStateDir(), `${this.name}.journal.jsonl`));
  }

  /** Open the store, recover, validate descriptions (idempotent). */
  async start(): Promise<void> {
    if (this.started) return;
    for (const dev of this.devices.values()) dev.description(); // fail fast on invalid declarations
    this.store = this.openStore();
    const loaded = this.store.load();
    this.journal = new Journal(this.store);
    this.journal.onWriteFailure = (e) => this.journalFailed(e);
    this.journal.adopt(loaded.ops);
    this.events = new EventLog(this.store, this.opts.eventRetentionS, loaded.events);
    this.observations = new ObservationHub(this, this.opts.observationMinIntervalMs);
    this.leases = new LeaseManager(this.store, { minTtlMs: this.opts.leaseMinTtlMs, maxTtlMs: this.opts.leaseMaxTtlMs, maxWaitMs: this.opts.leaseMaxWaitMs }, () => this.resources(), loaded.fence, (l, reason) => this.leaseEnded(l, reason));
    this.executor = new Executor(this, this.opts.queueLimit, this.opts.cancelGraceMs);
    if (this.opts.programs !== false) this.programs = new ProgramRunner(this, loaded.programs);
    this.started = true;
    // BHMS-OPS-080: before any request is answered
    await this.executor.recover();
    const cutoff = Date.now() - this.opts.keyRetentionS * 1000;
    this.journal.forget(this.store.prune(cutoff));
    this.events.prune(Date.now());
    for (const dev of this.devices.values()) {
      this.events.append("device.epoch", { deviceId: dev.deviceId, data: { epoch: this.observations.epoch }, message: "observation sequences restarted with the server" });
    }
    for (const dev of this.devices.values()) if (dev.livenessHandler) this.probeLiveness(dev);
    this.executor.resume();
  }

  private probeLiveness(dev: Device): void {
    const probe = async (): Promise<void> => {
      try { if (await dev.livenessHandler!()) dev.reportAlive(); } catch { /* unreachable: no evidence */ }
    };
    void probe();
    const t = setInterval(() => { void probe(); }, 15_000);
    t.unref();
    this.lifecycleTimers.add(t);
  }

  /** Connect a transport to this server; returns its session. */
  serve(transport: Transport): Session {
    if (!this.started) throw new Error("call start() before serve()");
    const session = new Session(transport, { role: "server", handler: (ctx) => this.dispatch(ctx), log: (m) => this.log(m) });
    this.sessions.add(session);
    session.onClose = () => { this.sessions.delete(session); };
    return session.start();
  }

  /**
   * Run the server: `undefined` or `"stdio"` serves this process's stdin/stdout until the parent closes it
   * (BHMS-TRN-011); `unix:<path>` and `ws://127.0.0.1:<port>` listen (TCP has no credential and is refused). Resolves when stdio ends;
   * for listeners resolves with the address once listening (call `close()` to stop).
   */
  async run(url?: string): Promise<string | undefined> {
    await this.start();
    if (url === undefined || url === "stdio") {
      const session = this.serve(stdioServerTransport(this.opts.maxMessageBytes));
      await session.waitClosed();
      await this.close();
      return undefined;
    }
    let listener: Listener | WsListener;
    if (url.startsWith("unix:")) {
      listener = await listenUnix(url.slice(5), (t) => { this.serve(t); }, this.opts.maxMessageBytes);
    } else if (url.startsWith("tcp://")) {
      throw new RangeError("TCP carries no credential, so a server will not serve it (BHMS-SEC-001); use unix:<path> or ws://127.0.0.1:<port> with a bearer token");
    } else if (url.startsWith("ws://")) {
      const u = new URL(url);
      this.ensureToken();
      listener = await listenWebSocket(u.hostname.replace(/^\[|\]$/g, ""), Number(u.port || 80), (t) => { this.serve(t); }, { token: this.opts.token, maxMessageBytes: this.opts.maxMessageBytes });
    } else {
      throw new RangeError(`unsupported url ${JSON.stringify(url)}; use stdio, unix:<path> or ws://127.0.0.1:<port>`);
    }
    this.listeners.push(listener);
    return listener.address;
  }

  /**
   * A WebSocket listener always requires a bearer token (BHMS-TRN-031, BHMS-SEC-001): one passed as `token`, taken from
   * `$BHMS_TOKEN`, or else generated and written to `<stateDir>/<name>.token` with mode 0600. Tokens are never logged
   * (BHMS-SEC-002); only the file's path is.
   */
  private ensureToken(): void {
    if (this.opts.token) return;
    const dir = this.opts.stateDir ?? defaultStateDir();
    mkdirSync(dir, { recursive: true, mode: 0o700 });
    const path = join(dir, `${this.name}.token`);
    this.opts.token = randomBytes(24).toString("base64url");
    writeFileSync(path, this.opts.token + "\n", { mode: 0o600 });
    this.log(`bearer token written to ${path} (mode 0600); clients pass it as Authorization: Bearer`);
  }

  /** Stop listening and close every connection. Physical work in flight is never cancelled (BHMS-TRN-005); it is awaited
   * for up to `drainMs` and recorded in the journal. */
  async close(drainMs = 2000): Promise<void> {
    if (this.closed) return;
    this.closed = true;
    this.closingController.abort(); // ends subscriptions with endReason "shutdown"
    await Promise.all(this.listeners.map((l) => l.close()));
    await sleep(0); // let subscription generators deliver their endReason
    await Promise.all([...this.sessions].map((s) => s.close()));
    if (this.started) {
      await this.programs?.close();
      await this.executor.idle(drainMs);
      this.leases.close();
      this.observations.close();
      this.store.close();
    }
    for (const t of this.lifecycleTimers) clearInterval(t);
  }

  // ------------------------------------------------------------------------------------------------ hooks used by the runtime

  authenticate(ctx: RequestContext): Principal {
    return this.policy(ctx.peer);
  }

  visibleDevice(principal: Principal, deviceId: string, field = "deviceId"): Device {
    const dev = this.devices.get(deviceId);
    if (!dev || !principal.canRead) {
      throw new BhmsError("UNKNOWN_DEVICE", `no device ${JSON.stringify(deviceId)}`, { field, hint: "devices/list shows the devices you can use" });
    }
    return dev;
  }

  deviceChanged(_dev: Device): void {
    for (const l of [...this.deviceListeners]) l();
  }

  statusChanged(dev: Device, _previous: string): void {
    const s = dev.status;
    if (s === "online" || s === "offline" || s === "degraded") {
      this.events.append(`device.${s}`, { deviceId: dev.deviceId, severity: s === "online" ? "info" : "warning" });
    }
  }

  private leaseEnded(lease: Lease, reason: "expired" | "revoked"): void {
    this.events.append(reason === "expired" ? "lease.expired" : "lease.revoked", { severity: "warning", data: { leaseId: lease.leaseId } });
    this.executor.onLeaseEnded(lease, reason);
    this.programs?.onLeaseEnd(lease);
  }

  /** The journal could not be written: refuse ordinary new operations until it can (BHMS-AUTH-025). */
  journalFailed(e: Error): void {
    if (this.journalOk) this.log(`the journal cannot be written (${e.message}); ordinary operations are refused until it can`);
    this.journalOk = false;
  }

  journalBusy(): BhmsError {
    return new BhmsError("BUSY", "the operation journal cannot be written; new operations are refused until it can", { retry: "same-key", hint: "retry later with the same operationKey; stop remains available" });
  }

  requireJournal(): void {
    if (this.journalOk && this.store.writable) return;
    if (this.store.probeWritable() && this.journal.flushDirty()) {
      this.journalOk = true;
      return;
    }
    throw this.journalBusy();
  }

  get journalHealthy(): boolean {
    return this.journalOk && this.store.writable;
  }

  /** Ask every device's `reconcile` hook about `unknown` operations (BHMS-OPS-005). */
  async reconcile(): Promise<void> {
    await this.executor.reconcileAll();
  }

  // ------------------------------------------------------------------------------------------------ discovery

  private capabilities(): Record<string, unknown> {
    const o = this.opts;
    return {
      devices: { listChanged: true },
      observations: { subscribe: true, minIntervalMs: o.observationMinIntervalMs },
      operations: { durable: this.store.durable, cancel: true, keyRetentionS: this.store.durable ? o.keyRetentionS : 0 },
      stop: {},
      subscriptions: { maxObservations: 256, maxOperationIds: 256 },
      leases: { minTtlMs: o.leaseMinTtlMs, maxTtlMs: o.leaseMaxTtlMs, maxWaitMs: o.leaseMaxWaitMs },
      events: { retentionS: o.eventRetentionS, maxPageSize: o.maxPageSize },
      ...(this.programs ? { programs: { registry: true, limits: this.programLimits } } : {}),
      ...(Object.keys(this.extensionInfo).length > 0 ? { extensions: this.extensionInfo } : {}),
    };
  }

  private advertises(capability: string): boolean {
    const [head, member] = capability.split(".", 2);
    const value = (this.capabilities() as Record<string, Record<string, unknown> | undefined>)[head];
    if (value === undefined) return false;
    return member === undefined ? true : Boolean(value[member]);
  }

  // ------------------------------------------------------------------------------------------------ dispatch

  /** The session handler: method lookup, `_meta` and version checks, capability gate, shape validation, then the method. */
  async dispatch(ctx: RequestContext): Promise<HandlerResult> {
    const method = ctx.method;
    const spec = (METHODS as Record<string, { tier: string; capability?: string }>)[method];
    const ext = this.extensionMethods.get(method);
    if (method !== "server/discover" && spec === undefined && ext === undefined) throw new JsonRpcError(METHOD_NOT_FOUND, `Method not found: ${method}`);
    const params = ctx.params;
    const metaError = (field: string, message: string): BhmsError => new BhmsError("INVALID_ARGUMENT", message, { field, hint: `send params._meta with "bhms/protocolVersion": "${PROTOCOL_VERSION}" (BHMS-LIF-011)` });
    if (typeof params !== "object" || params === null || Array.isArray(params)) throw metaError("_meta.bhms/protocolVersion", "params must be an object carrying _meta.bhms/protocolVersion");
    const meta = (params as Record<string, unknown>)._meta;
    if (typeof meta !== "object" || meta === null || !("bhms/protocolVersion" in meta)) throw metaError("_meta.bhms/protocolVersion", "missing _meta.bhms/protocolVersion");
    const version = (meta as Record<string, unknown>)["bhms/protocolVersion"];
    if (version !== PROTOCOL_VERSION) {
      throw new BhmsError("UNSUPPORTED_VERSION", `protocol version ${JSON.stringify(version)} is not served`, {
        field: "_meta.bhms/protocolVersion", bound: [PROTOCOL_VERSION], hint: `retry with a supported version: ${PROTOCOL_VERSION}`,
      });
    }
    if (spec?.capability !== undefined && !this.advertises(spec.capability)) {
      throw new BhmsError("UNSUPPORTED", `${method} needs the ${JSON.stringify(spec.capability)} capability, which this server does not advertise`, {
        hint: `check server/discover capabilities.${spec.capability} before calling ${method}`,
      });
    }
    if (ext) {
      const out = await ext(params as Record<string, unknown>, ctx);
      return { resultType: "complete", ...out };
    }
    const defs = loadSchema()["x-bhms-methods"] as Record<string, { params: string; result: string }>;
    validateDef(defs[method].params.replace("#/$defs/", ""), params);
    const result = await this.handle(method, params as never, ctx);
    if (!(Symbol.asyncIterator in Object(result)) && this.opts.strict) {
      validateDef(defs[method].result.replace("#/$defs/", ""), result);
    }
    return result;
  }

  private async handle(method: string, p: Record<string, unknown> & { _meta: unknown }, ctx: RequestContext): Promise<HandlerResult> {
    const principal = this.authenticate(ctx);
    const complete = (r: Record<string, unknown>): Record<string, unknown> => ({ resultType: "complete", ...r });
    const max = this.opts.maxPageSize;
    switch (method) {
      case "server/discover": {
        const result: Record<string, unknown> = {
          resultType: "complete", supportedVersions: [PROTOCOL_VERSION],
          serverInfo: { name: this.name, version: this.opts.version, ...(this.opts.title ? { title: this.opts.title } : {}) },
          capabilities: this.capabilities(), epoch: this.epoch,
          limits: { maxMessageBytes: ctx.session.maxMessageBytes, maxPageSize: max, maxWaitMs: this.opts.maxWaitMs },
          principal: principal.wire(),
        };
        if (this.opts.instructions) result.instructions = this.opts.instructions;
        return result;
      }
      case "devices/list": {
        if (!principal.canRead) return complete({ devices: [] }); // BHMS-DEV-010: nothing reveals hidden devices
        const lim = limit(p.limit as number | undefined, max);
        const after = p.cursor !== undefined ? decodeCursor("d", p.cursor as string) : undefined;
        const matches = [];
        for (const dev of [...this.devices.values()].sort((a, b) => (a.deviceId < b.deviceId ? -1 : 1))) {
          if (after !== undefined && dev.deviceId <= after) continue;
          const status = dev.status;
          const summary = dev.summary(status);
          if (!summaryMatches(p.filter as DevicesListFilter | undefined, summary, status)) continue;
          matches.push(summary);
          if (matches.length > lim) break;
        }
        const out: Record<string, unknown> = { devices: matches.slice(0, lim) };
        if (matches.length > lim) out.nextCursor = encodeCursor("d", matches[lim - 1].deviceId);
        return complete(out);
      }
      case "devices/describe": {
        const dev = this.visibleDevice(principal, p.deviceId as string);
        const description = dev.description();
        if (p.digest !== undefined && p.digest !== description.digest) {
          throw new BhmsError("STALE", `${dev.deviceId}'s description changed`, { field: "digest", bound: description.digest, hint: "describe again without digest and update your cached copy (BHMS-DEV-022)" });
        }
        return complete({ description });
      }
      case "properties/read": {
        const dev = this.visibleDevice(principal, p.deviceId as string);
        const observation = await this.observations.read(dev, p.property as string, { maxAgeMs: p.maxAgeMs as number | undefined, fresh: p.fresh as boolean | undefined, principal });
        return complete({ observation });
      }
      case "actions/invoke": {
        const params = p as unknown as ActionsInvokeParams;
        const { rec, replayed } = await this.executor.invoke(principal, params); // key lookup first (BHMS-OPS-033)
        if (params.waitMs) await this.journal.wait(rec, Math.min(params.waitMs, this.opts.maxWaitMs), ctx.signal);
        return complete({ operation: rec.wire(), replayed });
      }
      case "operations/get":
        return complete({ operation: this.operationFor(principal, p.operationId as string).wire(true) });
      case "operations/wait": {
        const timeoutMs = p.timeoutMs as number;
        if (timeoutMs > this.opts.maxWaitMs) throw waitError("timeoutMs", timeoutMs, this.opts.maxWaitMs);
        const rec = this.operationFor(principal, p.operationId as string);
        await this.journal.wait(rec, timeoutMs, ctx.signal);
        return complete({ operation: rec.wire(true) });
      }
      case "operations/list": {
        const { page, cursor } = this.journal.list({
          principal: principal.operationsAll ? undefined : principal.id, limit: limit(p.limit as number | undefined, max),
          after: p.cursor as string | undefined, deviceId: p.deviceId as string | undefined, state: p.state as string | undefined, parentId: p.parentOperationId as string | undefined,
        });
        return complete({ operations: page, ...(cursor !== undefined ? { nextCursor: cursor } : {}) });
      }
      case "operations/cancel": {
        const rec = this.journal.get(p.operationId as string);
        if (!rec || (rec.principal !== principal.id && !principal.operationsAll && !principal.admin)) {
          throw new BhmsError("INVALID_ARGUMENT", `no operation ${JSON.stringify(p.operationId)}`, { field: "operationId", hint: "use an operationId returned to you" });
        }
        if (rec.principal !== principal.id && !principal.admin) {
          throw new BhmsError("UNAUTHORIZED", "only the principal that created an operation (or admin) may cancel it", { field: "operationId", hint: "ask its owner, or use stop if the device must halt (BHMS-OPS-054)" });
        }
        if (rec.op.kind === "program") this.programs!.cancel(rec, p.reason as string | undefined);
        else this.executor.cancel(rec, p.reason as string | undefined);
        return complete({ operation: rec.wire() });
      }
      case "stop":
        return complete({ stops: await this.stop(principal, p as unknown as { deviceIds?: string[]; scope?: "all"; reason: string; waitMs?: number }) });
      case "subscriptions/listen":
        return listen(this, principal, ctx.peer, p.notifications as never, ctx.signal);
      case "leases/acquire":
      case "leases/renew":
      case "leases/release": {
        if (!principal.has("lease")) throw new BhmsError("UNAUTHORIZED", "leases need the lease scope", { hint: "missing scope lease" });
        if (method === "leases/acquire") {
          const lease = await this.leases.acquire(principal.id, p.resources as string[], p.ttlMs as number, p.waitMs as number | undefined, ctx.signal);
          return complete({ lease: leaseWire(lease) });
        }
        const lease = method === "leases/renew" ? this.leases.renew(principal.id, p.leaseId as string, p.ttlMs as number) : this.leases.release(principal.id, p.leaseId as string);
        return complete({ lease: leaseWire(lease) });
      }
      case "programs/run": {
        const { rec, replayed } = await this.programs!.run(principal, p);
        if (p.waitMs) await this.journal.wait(rec, Math.min(p.waitMs as number, this.opts.maxWaitMs), ctx.signal);
        return complete({ operation: rec.wire(), replayed });
      }
      case "programs/register":
        return complete({ info: this.programs!.register(principal, p.program as never) });
      case "programs/get": {
        const stored = this.programs!.get(principal, p.digest as string);
        return complete({ program: stored.program, info: stored.info });
      }
      case "programs/list": {
        const after = p.cursor !== undefined ? decodeCursor("p", p.cursor as string) : undefined;
        const { infos, next } = this.programs!.list(principal, after, limit(p.limit as number | undefined, max));
        return complete({ programs: infos, ...(next !== undefined ? { nextCursor: encodeCursor("p", next) } : {}) });
      }
      case "events/read": {
        if (!principal.canRead) throw new BhmsError("UNAUTHORIZED", "events/read needs the read scope", { hint: "missing scope read" });
        const r = this.events.read({ after: p.after as string | undefined, limit: limit(p.limit as number | undefined, max), deviceId: p.deviceId as string | undefined, types: p.types as string[] | undefined });
        return complete({ events: r.events, cursor: r.cursor, gap: r.gap });
      }
      default:
        throw new JsonRpcError(METHOD_NOT_FOUND, `Method not found: ${method}`);
    }
  }

  /** The operation if the principal may see it; otherwise `INVALID_ARGUMENT` (BHMS-OPS-062). */
  operationFor(principal: Principal, operationId: string) {
    const rec = this.journal.get(operationId);
    if (!rec || (rec.principal !== principal.id && !principal.operationsAll)) {
      throw new BhmsError("INVALID_ARGUMENT", `no operation ${JSON.stringify(operationId)}`, { field: "operationId", hint: "use an operationId returned to you" });
    }
    return rec;
  }

  // ------------------------------------------------------------------------------------------------ stop (BHMS-AUTH-020..026)

  /**
   * The `stop` fast path: takes no lock, waits for no lease, queue or operation, dispatches each device's commissioned
   * stop procedure first (a synchronous handler has run before anything is written), and only then does the bookkeeping of
   * BHMS-AUTH-021 in order: cancel `accepted` operations, request cancellation of running ones, revoke leases, record a
   * `stop` event.
   */
  async stop(principal: Principal, p: { deviceIds?: string[]; scope?: "all"; reason: string; waitMs?: number }): Promise<DeviceStop[]> {
    if (!principal.hasAnyStop) throw new BhmsError("UNAUTHORIZED", "stop needs the stop scope", { hint: "missing scope stop (or stop:<deviceGlob>)" });
    const ids = p.scope === "all" ? [...this.devices.keys()].sort() : [...(p.deviceIds ?? [])];
    if (p.scope === "all" && !principal.has("stop")) throw new BhmsError("UNAUTHORIZED", "scope all needs the unrestricted stop scope", { hint: "missing scope stop" });
    for (const id of ids) {
      if (this.devices.has(id) && principal.canRead && !principal.canStop(id)) {
        throw new BhmsError("UNAUTHORIZED", `the principal may not stop ${id}`, { field: "deviceIds", hint: `missing scope stop or stop:${id}` });
      }
    }
    const degraded = !this.journalHealthy;
    type Pending = { id: string; dev?: Device; done?: Promise<"done" | "failed">; stop: DeviceStop; failure?: unknown };
    const pending: Pending[] = [];
    for (const id of ids) {
      const dev = this.devices.get(id);
      if (!dev || !principal.canRead) {
        pending.push({
          id, stop: {
            deviceId: id, outcome: "failed", evidence: "none", canceledOperations: [], revokedLeases: [],
            error: new BhmsError("UNKNOWN_DEVICE", `no device ${JSON.stringify(id)}`, { hint: "devices/list shows the devices you can stop" }).toOperationError(),
          },
        });
        continue;
      }
      // 1. dispatch the stop procedure (its first step runs now, before any bookkeeping)
      let done: Promise<"done" | "failed"> | undefined;
      const entry: Pending = { id, dev, stop: { deviceId: id, outcome: "unsupported", evidence: "none", canceledOperations: [], revokedLeases: [] } };
      if (dev.stopSpec) {
        try {
          done = Promise.resolve(dev.stopSpec.handler()).then(() => "done" as const, (e: unknown) => { entry.failure = e; return "failed" as const; });
        } catch (e) {
          entry.failure = e;
          done = Promise.resolve("failed" as const);
        }
        entry.stop.outcome = "initiated";
      }
      // 2-5. bookkeeping
      entry.stop.canceledOperations = this.executor.cancelAccepted(id, p.reason);
      const requested = this.executor.requestCancelOn(id, p.reason);
      if (requested.length > 0) entry.stop.cancelRequestedOperations = requested;
      this.programs?.stopDevice(id, p.reason);
      entry.stop.revokedLeases = this.leases.revokeCovering(dev.resources).map((l) => l.leaseId);
      this.events.append("stop", { deviceId: id, severity: "critical", message: p.reason, data: { outcome: dev.stopSpec ? "initiated" : "unsupported", reason: p.reason } });
      entry.done = done;
      pending.push(entry);
    }
    // 6. wait up to waitMs for the procedures (stop returns within waitMs plus the time to dispatch, BHMS-AUTH-024)
    const waitMs = Math.min(p.waitMs ?? 0, this.opts.maxWaitMs);
    await Promise.all(pending.map(async (e) => {
      if (!e.done || !e.dev?.stopSpec) return;
      const timer = new Promise<"timeout">((resolve) => { const t = setTimeout(() => resolve("timeout"), waitMs); t.unref(); });
      const r = await Promise.race([e.done, timer]);
      const spec = e.dev.stopSpec;
      if (r === "done") {
        e.stop.outcome = "confirmed";
        e.stop.evidence = spec.evidence;
        this.executor.confirmStop(e.id);
        this.events.append("stop", { deviceId: e.id, severity: "info", data: { outcome: "confirmed", reason: p.reason } });
      } else if (r === "failed") {
        e.stop.outcome = "failed";
        e.stop.error = new BhmsError("INTERNAL", `the stop procedure of ${e.id} failed`, { mayHaveActed: true, hint: "treat the device as not stopped; use its hardware emergency stop" }).toOperationError();
        this.log(`stop procedure of ${e.id} failed: ${String(e.failure)}`);
        this.events.append("stop", { deviceId: e.id, severity: "error", data: { outcome: "failed", reason: p.reason } });
      } else {
        // not finished within waitMs: report initiated now, and record the outcome when it becomes known (BHMS-AUTH-024)
        void e.done.then((v) => {
          if (v === "done") { this.executor.confirmStop(e.id); this.events.append("stop", { deviceId: e.id, severity: "info", data: { outcome: "confirmed", reason: p.reason } }); }
          else this.events.append("stop", { deviceId: e.id, severity: "error", data: { outcome: "failed", reason: p.reason } });
        });
      }
    }));
    return pending.map((e) => {
      if (degraded || !this.journalHealthy) e.stop.detail = "degraded-audit";
      return e.stop;
    });
  }
}

export { DescriptionError, StoreError };
export type { Event };
