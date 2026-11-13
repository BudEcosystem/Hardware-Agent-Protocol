/**
 * BHMS client: connect, discover, a typed method for every entry of the schema's `x-bhms-methods`, and subscriptions.
 *
 * `Client.connect("stdio:node server.js")` opens a transport, runs `server/discover` (there is no handshake,
 * BHMS-LIF-022), selects a protocol version (retrying once on `UNSUPPORTED_VERSION`, BHMS-LIF-019) and from then on
 * injects `params._meta` (`bhms/protocolVersion` and `bhms/clientInfo`) into every request.
 *
 * Targets: `stdio:<command and args>`, `unix:<path>`, `tcp://host:port`, `ws://host:port[/path]`.
 *
 * Errors: an error response rejects with {@link BhmsError} (or {@link JsonRpcError} for plain JSON-RPC errors); a request
 * that times out rejects with `BhmsError(DEADLINE_EXCEEDED, mayHaveActed: true)`: the outcome is unknown, so use
 * `operationsGet` or retry with the same `operationKey` (BHMS-LIF-053); a dropped connection rejects with
 * {@link TransportClosed}. A result whose `resultType` is not `"complete"` is a {@link ProtocolViolation}
 * (BHMS-LIF-012). With `strict: true` every result is also validated against its schema definition.
 *
 * Example:
 * ```ts
 * const client = await Client.connect("unix:/tmp/bhms.sock");
 * const listing = await client.devicesList();
 * const { operation } = await client.actionsInvoke("pump-1", "dispense", { volume: { value: 5, unit: "uL" } },
 *   { operationKey: "k-1", waitMs: 2000 });
 * await client.close();
 * ```
 *
 * Thread-safety: requests are multiplexed on one connection and may be awaited concurrently.
 */
import { BhmsError, type BhmsCode } from "./errors.js";
import type {
  ActionsInvokeResult, DevicesDescribeResult, DevicesListFilter, DevicesListResult, DiscoverResult, EventsReadResult,
  LeasesAcquireResult, LeasesReleaseResult, LeasesRenewResult, OperationsCancelResult, OperationsGetResult,
  OperationsListResult, OperationsWaitResult, Program, ProgramsGetResult, ProgramsListResult, ProgramsRegisterResult,
  ProgramsRunResult, PropertiesReadResult, StopResult, SubscriptionFilter,
} from "./generated/types.js";
import { METHODS, PROTOCOL_VERSION } from "./generated/types.js";
import { Session, type ClientStream, type Notification, type Transport } from "./jsonrpc/session.js";
import { loadSchema, validateDef } from "./schema.js";
import { spawnServer } from "./transport/stdio.js";
import { connectSocket } from "./transport/socket.js";
import { connectWebSocket } from "./transport/websocket.js";

export const SUPPORTED_VERSIONS: readonly string[] = [PROTOCOL_VERSION];
export const DEFAULT_CLIENT_INFO = { name: "bhms-typescript", version: "0.1.0" } as const;

/** Protocol method name to the {@link Client} method that exposes it (asserted complete by test/client.test.ts). */
export const METHOD_ATTRS: Readonly<Record<string, string>> = {
  "server/discover": "discover", "devices/list": "devicesList", "devices/describe": "devicesDescribe",
  "properties/read": "propertiesRead", "actions/invoke": "actionsInvoke", "operations/get": "operationsGet",
  "operations/wait": "operationsWait", "operations/list": "operationsList", "operations/cancel": "operationsCancel",
  stop: "stop", "subscriptions/listen": "subscribe", "leases/acquire": "leasesAcquire", "leases/renew": "leasesRenew",
  "leases/release": "leasesRelease", "events/read": "eventsRead", "programs/run": "programsRun",
  "programs/register": "programsRegister", "programs/get": "programsGet", "programs/list": "programsList",
};

/** The peer broke the protocol (for example a result without `resultType: "complete"`). */
export class ProtocolViolation extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProtocolViolation";
  }
}

export interface ClientOptions {
  clientInfo?: Record<string, unknown>;
  /** Validate every result against its schema definition. */
  strict?: boolean;
  /** Default request timeout in ms (default 30 000; 0 disables). */
  timeoutMs?: number;
  /** Bearer token for WebSocket targets. */
  token?: string;
  /** Pin the protocol version instead of negotiating. */
  protocolVersion?: string;
}

export interface CallOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

export interface InvokeOptions extends CallOptions {
  operationKey?: string;
  leaseId?: string;
  deadlineMs?: number;
  waitMs?: number;
  require?: { effect: "verified" };
  descriptionDigest?: string;
}

/** Split a command line into arguments, honouring single and double quotes. */
function splitCommand(line: string): string[] {
  const out: string[] = [];
  const re = /"((?:[^"\\]|\\.)*)"|'([^']*)'|(\S+)/g;
  for (let m = re.exec(line); m; m = re.exec(line)) out.push(m[1] !== undefined ? m[1].replace(/\\(.)/g, "$1") : (m[2] ?? m[3]));
  return out;
}

export interface OpenedTransport {
  transport: Transport;
  /** Terminate the underlying child process (stdio targets). */
  dispose?: () => void;
}

/** Open a transport from `stdio:<command>`, `unix:<path>`, `tcp://host:port` or `ws[s]://...`. */
export async function openTransport(target: string, options: { token?: string; maxMessageBytes?: number } = {}): Promise<OpenedTransport> {
  if (target.startsWith("stdio:")) {
    const [command, ...args] = splitCommand(target.slice("stdio:".length).trim());
    if (!command) throw new RangeError("stdio: target needs a command");
    const { transport, child } = spawnServer(command, args, { maxMessageBytes: options.maxMessageBytes });
    return { transport, dispose: () => { if (child.exitCode === null) child.kill(); } };
  }
  if (target.startsWith("unix:")) {
    let path = target.slice("unix:".length);
    if (path.startsWith("//")) path = path.slice(2);
    return { transport: await connectSocket(path, options.maxMessageBytes) };
  }
  if (target.startsWith("tcp://")) {
    return { transport: await connectSocket(`tcp:${target.slice("tcp://".length).replace(/\/$/, "")}`, options.maxMessageBytes) };
  }
  if (target.startsWith("ws://") || target.startsWith("wss://")) {
    return { transport: await connectWebSocket(target, { token: options.token, maxMessageBytes: options.maxMessageBytes }) };
  }
  throw new RangeError(`unsupported target ${JSON.stringify(target)}; use stdio:<command>, unix:<path>, tcp://host:port or ws://host:port`);
}

export class Subscription implements AsyncIterable<Notification> {
  constructor(private readonly stream: ClientStream, readonly acknowledged: Record<string, unknown>) {}
  get id(): number { return this.stream.id; }
  /** `shutdown`, `overflow` or `unauthorized` once the server ended the subscription (BHMS-LIF-044). */
  get endReason(): string | undefined { return this.stream.result?.endReason as string | undefined; }
  next(): Promise<Notification | undefined> { return this.stream.next(); }
  cancel(reason?: string): void { this.stream.cancel(reason); }
  [Symbol.asyncIterator](): AsyncIterator<Notification> { return this.stream[Symbol.asyncIterator](); }
}

export class Client {
  /** Result of the last `server/discover`. */
  discovered?: DiscoverResult;
  private version: string;
  private readonly clientInfo: Record<string, unknown>;
  private readonly strict: boolean;
  private readonly timeoutMs: number;
  private dispose?: () => void;

  private constructor(readonly session: Session, options: ClientOptions) {
    this.clientInfo = options.clientInfo ?? { ...DEFAULT_CLIENT_INFO };
    this.strict = options.strict ?? false;
    this.timeoutMs = options.timeoutMs ?? 30_000;
    this.version = options.protocolVersion ?? PROTOCOL_VERSION;
  }

  /** Open `target` (see module docs), discover the server and return a ready client. */
  static async connect(target: string, options: ClientOptions = {}): Promise<Client> {
    const opened = await openTransport(target, { token: options.token });
    try {
      const client = await Client.fromTransport(opened.transport, options);
      client.dispose = opened.dispose;
      return client;
    } catch (e) {
      opened.dispose?.();
      await opened.transport.close().catch(() => undefined);
      throw e;
    }
  }

  /** Build a client on an existing transport and run `server/discover`. */
  static async fromTransport(transport: Transport, options: ClientOptions = {}): Promise<Client> {
    const session = new Session(transport, { role: "client", defaultTimeoutMs: options.timeoutMs ?? 30_000 }).start();
    const client = new Client(session, options);
    try {
      await client.discover();
    } catch (e) {
      await session.close();
      throw e;
    }
    return client;
  }

  get protocolVersion(): string { return this.version; }

  async close(): Promise<void> {
    await this.session.close();
    this.dispose?.();
  }

  private meta(): Record<string, unknown> {
    return { "bhms/protocolVersion": this.version, "bhms/clientInfo": this.clientInfo };
  }

  private params(wire: Record<string, unknown>): Record<string, unknown> {
    return { _meta: this.meta(), ...wire };
  }

  private async callOnce(method: string, wire: Record<string, unknown>, options: CallOptions, waitMs: number | undefined): Promise<Record<string, unknown>> {
    const limit = options.timeoutMs ?? (this.timeoutMs === 0 ? 0 : this.timeoutMs + (waitMs ?? 0));
    const result = await this.session.request(method, this.params(wire), { timeoutMs: limit, signal: options.signal });
    if (result.resultType !== "complete") {
      throw new ProtocolViolation(`${method}: result.resultType must be "complete", got ${JSON.stringify(result.resultType)} (BHMS-LIF-012)`);
    }
    if (this.strict) {
      const def = (loadSchema()["x-bhms-methods"] as Record<string, { result: string }>)[method]?.result.replace("#/$defs/", "");
      if (def) validateDef(def, result);
    }
    return result;
  }

  /**
   * Send any request (including extension methods such as `x-conformance/inject`) and return its result object.
   * On `UNSUPPORTED_VERSION` retries once with a mutually supported version (BHMS-LIF-019).
   */
  async request<T = Record<string, unknown>>(method: string, wire: Record<string, unknown> = {}, options: CallOptions & { waitMs?: number } = {}): Promise<T> {
    const { waitMs, ...call } = options;
    try {
      return (await this.callOnce(method, wire, call, waitMs)) as T;
    } catch (e) {
      if (e instanceof BhmsError && e.bhmsCode === "UNSUPPORTED_VERSION" && Array.isArray(e.bound) && method !== "server/discover") {
        const common = (e.bound as string[]).filter((v) => SUPPORTED_VERSIONS.includes(v)).sort().pop();
        if (common && common !== this.version) {
          this.version = common;
          return (await this.callOnce(method, wire, call, waitMs)) as T;
        }
      }
      throw e;
    }
  }

  /** `server/discover`: versions, identity, capabilities, limits and epoch. Selects the protocol version (BHMS-LIF-019). */
  async discover(options: CallOptions = {}): Promise<DiscoverResult> {
    let result: DiscoverResult;
    try {
      result = (await this.callOnce("server/discover", {}, options, undefined)) as DiscoverResult;
    } catch (e) {
      if (!(e instanceof BhmsError) || e.bhmsCode !== "UNSUPPORTED_VERSION" || !Array.isArray(e.bound)) throw e;
      const common = (e.bound as string[]).filter((v) => SUPPORTED_VERSIONS.includes(v)).sort().pop();
      if (!common) throw e;
      this.version = common;
      result = (await this.callOnce("server/discover", {}, options, undefined)) as DiscoverResult;
    }
    if (!result.supportedVersions.includes(this.version)) {
      const common = result.supportedVersions.filter((v) => SUPPORTED_VERSIONS.includes(v)).sort().pop();
      if (!common) {
        throw new BhmsError("UNSUPPORTED_VERSION", `the server supports ${result.supportedVersions.join(", ")}; this client speaks ${SUPPORTED_VERSIONS.join(", ")}`, {
          field: "_meta.bhms/protocolVersion", bound: result.supportedVersions, hint: "upgrade or downgrade the client",
        });
      }
      this.version = common;
    }
    this.discovered = result;
    return result;
  }

  private static strip(o: Record<string, unknown>): Record<string, unknown> {
    return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined));
  }

  devicesList(args: { filter?: DevicesListFilter; cursor?: string; limit?: number } = {}, o: CallOptions = {}): Promise<DevicesListResult> {
    return this.request("devices/list", Client.strip(args), o);
  }

  /** Iterate every device summary across pages. */
  async *iterDevices(args: { filter?: DevicesListFilter; limit?: number } = {}): AsyncGenerator<DevicesListResult["devices"][number]> {
    let cursor: string | undefined;
    do {
      const page = await this.devicesList({ ...args, cursor });
      yield* page.devices;
      cursor = page.nextCursor;
    } while (cursor);
  }

  devicesDescribe(deviceId: string, args: { digest?: string } = {}, o: CallOptions = {}): Promise<DevicesDescribeResult> {
    return this.request("devices/describe", Client.strip({ deviceId, ...args }), o);
  }

  propertiesRead(deviceId: string, property: string, args: { maxAgeMs?: number; fresh?: boolean } = {}, o: CallOptions = {}): Promise<PropertiesReadResult> {
    return this.request("properties/read", Client.strip({ deviceId, property, ...args }), o);
  }

  /** `actions/invoke`. Pass `operationKey` whenever the call may be retried (BHMS-OPS-035). */
  actionsInvoke(deviceId: string, action: string, args: Record<string, unknown>, o: InvokeOptions = {}): Promise<ActionsInvokeResult> {
    const { timeoutMs, signal, ...rest } = o;
    return this.request("actions/invoke", Client.strip({ deviceId, action, arguments: args, ...rest }), { timeoutMs, signal, waitMs: o.waitMs });
  }

  operationsGet(operationId: string, o: CallOptions = {}): Promise<OperationsGetResult> {
    return this.request("operations/get", { operationId }, o);
  }

  operationsWait(operationId: string, timeoutMs: number, o: CallOptions = {}): Promise<OperationsWaitResult> {
    return this.request("operations/wait", { operationId, timeoutMs }, { ...o, waitMs: timeoutMs });
  }

  operationsList(args: { deviceId?: string; state?: string; parentOperationId?: string; cursor?: string; limit?: number } = {}, o: CallOptions = {}): Promise<OperationsListResult> {
    return this.request("operations/list", Client.strip(args), o);
  }

  async *iterOperations(args: { deviceId?: string; state?: string; limit?: number } = {}): AsyncGenerator<OperationsListResult["operations"][number]> {
    let cursor: string | undefined;
    do {
      const page = await this.operationsList({ ...args, cursor });
      yield* page.operations;
      cursor = page.nextCursor;
    } while (cursor);
  }

  operationsCancel(operationId: string, args: { reason?: string } = {}, o: CallOptions = {}): Promise<OperationsCancelResult> {
    return this.request("operations/cancel", Client.strip({ operationId, ...args }), o);
  }

  /** `stop`: name `deviceIds` or pass `scope: "all"`. Stop is not cancel (BHMS-AUTH-020). */
  stop(reason: string, args: { deviceIds?: string[]; scope?: "all"; waitMs?: number } = {}, o: CallOptions = {}): Promise<StopResult> {
    return this.request("stop", Client.strip({ reason, ...args }), { ...o, waitMs: args.waitMs });
  }

  leasesAcquire(resources: string[], ttlMs: number, args: { waitMs?: number } = {}, o: CallOptions = {}): Promise<LeasesAcquireResult> {
    return this.request("leases/acquire", Client.strip({ resources, ttlMs, ...args }), { ...o, waitMs: args.waitMs });
  }

  leasesRenew(leaseId: string, ttlMs: number, o: CallOptions = {}): Promise<LeasesRenewResult> {
    return this.request("leases/renew", { leaseId, ttlMs }, o);
  }

  leasesRelease(leaseId: string, o: CallOptions = {}): Promise<LeasesReleaseResult> {
    return this.request("leases/release", { leaseId }, o);
  }

  eventsRead(args: { after?: string; limit?: number; deviceId?: string; types?: string[] } = {}, o: CallOptions = {}): Promise<EventsReadResult> {
    return this.request("events/read", Client.strip(args), o);
  }

  programsRun(args: { arguments: Record<string, unknown>; program?: Program; digest?: string; operationKey?: string; deadlineMs?: number; waitMs?: number; leaseId?: string }, o: CallOptions = {}): Promise<ProgramsRunResult> {
    return this.request("programs/run", Client.strip(args), { ...o, waitMs: args.waitMs });
  }

  programsRegister(program: Program, o: CallOptions = {}): Promise<ProgramsRegisterResult> {
    return this.request("programs/register", { program }, o);
  }

  programsGet(digest: string, o: CallOptions = {}): Promise<ProgramsGetResult> {
    return this.request("programs/get", { digest }, o);
  }

  programsList(args: { cursor?: string; limit?: number } = {}, o: CallOptions = {}): Promise<ProgramsListResult> {
    return this.request("programs/list", Client.strip(args), o);
  }

  /**
   * `subscriptions/listen`: resolves after `notifications/subscriptions/acknowledged` (BHMS-LIF-040). Iterate the result
   * for notifications; when iteration ends, `endReason` says why the server ended it (BHMS-LIF-044).
   */
  async subscribe(filter: SubscriptionFilter): Promise<Subscription> {
    const stream = this.session.stream("subscriptions/listen", this.params({ notifications: filter }));
    const first = await stream.next();
    if (first === undefined) throw new ProtocolViolation("the subscription ended before it was acknowledged");
    if (first.method !== "notifications/subscriptions/acknowledged") {
      stream.cancel();
      throw new ProtocolViolation(`the first message of a subscription must be an acknowledgement (BHMS-LIF-040), got ${first.method}`);
    }
    return new Subscription(stream, first.params);
  }
}

/** All BHMS method names this client knows (from the schema): used by tests to assert coverage. */
export const KNOWN_METHODS: readonly string[] = Object.keys(METHODS);
export type { BhmsCode };
