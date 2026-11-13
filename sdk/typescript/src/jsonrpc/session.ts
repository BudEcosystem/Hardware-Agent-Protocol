/**
 * JSON-RPC 2.0 session over a {@link Transport}: one class serves both roles of spec/bhms/02-transports.md.
 *
 * - `role: "client"`: {@link Session.request} (concurrent, per-request timeout, abort), {@link Session.stream} (a request
 *   whose handler yields notifications until it completes or is cancelled, e.g. `subscriptions/listen`) and
 *   {@link Session.notify}. Servers never send requests and clients never send responses (BHMS-TRN-001).
 * - `role: "server"`: every incoming request runs its handler concurrently. Cancellation contract (BHMS-LIF-050,
 *   BHMS-TRN-005): `notifications/cancelled`, a disconnect and `close()` never cancel physical work. The handler's
 *   `AbortSignal` (`ctx.signal`) is aborted and its response is dropped (BHMS-LIF-051), but the handler promise keeps
 *   running, tracked by the session, so a physical operation is never silently abandoned. Handlers that only *wait*
 *   (`operations/wait`, `leases/acquire`, `subscriptions/listen`) observe the signal and return early.
 *   A handler returns a result object, or an async iterable yielding {@link Notification} items and finally a
 *   {@link Complete}: the form `subscriptions/listen` uses; the session tags each with `_meta["bhms/subscriptionId"]`
 *   (BHMS-LIF-041, BHMS-LIF-044).
 *
 * Framing errors keep the session alive: a malformed frame is answered `-32700`, an oversize frame or a batch `-32600`,
 * both with `id: null` (BHMS-TRN-002/004). A non-BHMS handler exception is logged locally and sent as `INTERNAL` with
 * `mayHaveActed: true` and no detail.
 *
 * Thread-safety: a session belongs to one event loop (Node is single-threaded); all methods may be called
 * concurrently from async code.
 */
import { BhmsError, JsonRpcError, fromJsonRpc, type JsonRpcErrorObject } from "../errors.js";

export const PARSE_ERROR = -32700;
export const INVALID_REQUEST = -32600;
export const METHOD_NOT_FOUND = -32601;
export const SUBSCRIPTION_KEY = "bhms/subscriptionId";
export const CANCELLED = "notifications/cancelled";

/** Who is on the other end, established by the transport (BHMS-SEC-001). */
export interface Peer {
  /** Stable principal id, e.g. `stdio`, `unix:uid=1000`, `ws:token`. */
  principal: string;
  kind: "stdio" | "unix" | "tcp" | "ws" | "memory";
  /** Scopes the transport grants outright (`stdio` and same-user Unix peers are `admin`); undefined = ask the policy. */
  scopes?: string[];
  /** Bearer token presented on a WebSocket upgrade, if any (never logged). */
  token?: string;
}

export interface TransportSink {
  message(text: string): void;
  /** A frame exceeded the transport's maximum size and was discarded (BHMS-TRN-004). */
  oversize(): void;
  /** A frame was not valid UTF-8 (BHMS-LIF-001): answered -32700. */
  invalidUtf8(): void;
  /** The connection ended (error when abnormal). */
  closed(error?: Error): void;
}

/** A framed, bidirectional message channel. See transport/*.ts. */
export interface Transport {
  readonly peer: Peer;
  readonly maxMessageBytes: number;
  /** Begin delivering inbound frames to `sink`. Called once. */
  start(sink: TransportSink): void;
  /** Send one message (the transport adds framing). Resolves when it was accepted by the OS / socket. */
  send(text: string): Promise<void>;
  close(): Promise<void>;
}

export class TransportClosed extends Error {
  constructor(message = "transport closed") {
    super(message);
    this.name = "TransportClosed";
  }
}

export interface Notification {
  method: string;
  params: Record<string, unknown>;
}
export class Complete {
  constructor(readonly result: Record<string, unknown>) {}
}

export interface RequestContext {
  id: string | number;
  method: string;
  params: unknown;
  peer: Peer;
  session: Session;
  /** Aborted when the client cancelled this request or the connection closed. */
  signal: AbortSignal;
}

export type HandlerResult = Record<string, unknown> | AsyncIterable<Notification | Complete>;
export type Handler = (ctx: RequestContext) => Promise<HandlerResult>;

export interface SessionOptions {
  role: "client" | "server";
  handler?: Handler;
  /** Default client request timeout in ms (undefined: 30 s; 0 disables). */
  defaultTimeoutMs?: number;
  /** Maximum outgoing message size in bytes (default: the transport's). */
  maxMessageBytes?: number;
  /** Cap on bytes queued for a peer that does not read; beyond it the session closes (default 64 MiB). */
  maxQueuedBytes?: number;
  /** Server: maximum concurrently handled requests; beyond it BUSY (default 16384). */
  maxInflight?: number;
  /** Logger for diagnostics (default: stderr). */
  log?: (message: string) => void;
}

const defaultLog = (m: string): void => { process.stderr.write(`[bhms] ${m}\n`); };

function validId(v: unknown): v is string | number {
  return typeof v === "string" || (typeof v === "number" && Number.isFinite(v));
}

function internalError(): BhmsError {
  return new BhmsError("INTERNAL", "internal server error", {
    mayHaveActed: true,
    hint: "This is a server bug and not a problem with your request; whether work started is unknown, so reconcile with operations/get before retrying. Details are in the server log.",
  });
}

/** The client end of a streaming request: an async iterator of notifications; `result` is set when it completes. */
export class ClientStream implements AsyncIterable<Notification> {
  result?: Record<string, unknown>;
  private readonly buffer: Notification[] = [];
  private wake?: () => void;
  private terminal?: { error?: unknown; done: boolean };
  constructor(readonly id: number, private readonly session: Session, private readonly maxBuffer: number) {}

  /** @internal */
  push(n: Notification): void {
    if (this.terminal) return;
    if (this.buffer.length >= this.maxBuffer) {
      this.session.dropStream(this.id);
      this.finish(new Error(`subscription ${this.id} fell more than ${this.maxBuffer} messages behind; read current state and call subscriptions/listen again (BHMS-LIF-044)`));
      this.session.sendCancel(this.id, "client buffer overflow");
      return;
    }
    this.buffer.push(n);
    this.wake?.();
  }

  /** @internal */
  finish(error?: unknown, result?: Record<string, unknown>): void {
    if (this.terminal) return;
    this.result = result;
    this.terminal = { error, done: true };
    this.wake?.();
  }

  async next(): Promise<Notification | undefined> {
    for (;;) {
      const item = this.buffer.shift();
      if (item) return item;
      if (this.terminal) {
        if (this.terminal.error) throw this.terminal.error;
        return undefined;
      }
      await new Promise<void>((resolve) => { this.wake = resolve; });
      this.wake = undefined;
    }
  }

  async *[Symbol.asyncIterator](): AsyncIterator<Notification> {
    for (;;) {
      const n = await this.next();
      if (n === undefined) return;
      yield n;
    }
  }

  /** Abandon the stream: tell the server and drop anything buffered (idempotent; BHMS-LIF-044). */
  cancel(reason?: string): void {
    if (this.terminal) return;
    this.buffer.length = 0;
    this.finish();
    if (this.session.dropStream(this.id)) this.session.sendCancel(this.id, reason);
  }
}

interface Inflight {
  ctx: RequestContext;
  abort: AbortController;
  abandoned: boolean;
}

export class Session {
  readonly role: "client" | "server";
  readonly maxMessageBytes: number;
  private readonly handler?: Handler;
  private readonly defaultTimeoutMs: number;
  private readonly maxQueuedBytes: number;
  private readonly maxInflight: number;
  private readonly log: (m: string) => void;
  private nextId = 0;
  private readonly pending = new Map<number, { resolve: (r: Record<string, unknown>) => void; reject: (e: unknown) => void }>();
  private readonly streams = new Map<number, ClientStream>();
  private readonly inflight = new Map<string | number, Inflight>();
  private readonly detached = new Set<Promise<unknown>>();
  private sendChain: Promise<void> = Promise.resolve();
  private queuedBytes = 0;
  private closedFlag = false;
  private readonly closedWaiters: Array<() => void> = [];
  private started = false;
  /** Called once when the session ends (peer closed, I/O error or close()). */
  onClose?: (error?: Error) => void;

  constructor(readonly transport: Transport, options: SessionOptions) {
    this.role = options.role;
    this.handler = options.handler;
    this.defaultTimeoutMs = options.defaultTimeoutMs ?? 30_000;
    this.maxMessageBytes = options.maxMessageBytes ?? transport.maxMessageBytes;
    this.maxQueuedBytes = options.maxQueuedBytes ?? 64 * 1024 * 1024;
    this.maxInflight = options.maxInflight ?? 16384;
    this.log = options.log ?? defaultLog;
  }

  get peer(): Peer { return this.transport.peer; }
  get closed(): boolean { return this.closedFlag; }
  /** Server: requests currently handled (including detached ones). */
  get inflightCount(): number { return this.inflight.size + this.detached.size; }

  start(): this {
    if (this.started) throw new Error("session already started");
    this.started = true;
    this.transport.start({
      message: (text) => this.onText(text),
      invalidUtf8: () => this.sendError(null, { code: PARSE_ERROR, message: "parse error: the frame is not valid UTF-8 (BHMS-LIF-001)" }),
      oversize: () => this.sendError(null, { code: INVALID_REQUEST, message: `message exceeds the ${this.transport.maxMessageBytes} byte limit (BHMS-TRN-004)` }),
      closed: (err) => this.teardown(err),
    });
    return this;
  }

  /** Resolves once the session has shut down. */
  waitClosed(): Promise<void> {
    return this.closedFlag ? Promise.resolve() : new Promise((resolve) => { this.closedWaiters.push(resolve); });
  }

  /**
   * Graceful shutdown: abandon in-flight requests (their handlers keep running, BHMS-TRN-005), flush queued output and
   * close the transport. Idempotent.
   */
  async close(): Promise<void> {
    if (!this.closedFlag) {
      try { await this.sendChain; } catch { /* the peer is gone */ }
      await this.teardown();
    }
    await this.waitClosed();
  }

  /** Wait up to `timeoutMs` for detached handlers; survivors are logged, never cancelled (BHMS-TRN-005). */
  async drain(timeoutMs: number): Promise<void> {
    if (this.detached.size === 0) return;
    let timer: NodeJS.Timeout | undefined;
    const timeout = new Promise<"timeout">((resolve) => { timer = setTimeout(() => resolve("timeout"), timeoutMs); });
    const all = Promise.allSettled([...this.detached]).then(() => "done" as const);
    const r = await Promise.race([all, timeout]);
    clearTimeout(timer);
    if (r === "timeout") this.log(`${this.detached.size} handler(s) still running ${timeoutMs} ms after their requests were abandoned; left running because they may be physical work`);
  }

  // ---------------------------------------------------------------------------------------------------- outbound

  private enqueue(text: string): Promise<void> {
    if (this.closedFlag) return Promise.reject(new TransportClosed("session is closed"));
    const bytes = Buffer.byteLength(text);
    if (bytes > this.maxMessageBytes) return Promise.reject(new RangeError(`message of ${bytes} bytes exceeds the ${this.maxMessageBytes} byte limit`));
    this.queuedBytes += bytes;
    if (this.queuedBytes > this.maxQueuedBytes) {
      this.log("peer is not reading and the outbound queue is full; closing the session");
      void this.teardown(new Error("outbound queue overflow"));
      return Promise.reject(new TransportClosed("outbound queue overflow"));
    }
    const p = this.sendChain.then(async () => {
      try {
        await this.transport.send(text);
      } finally {
        this.queuedBytes -= bytes;
      }
    });
    this.sendChain = p.catch((e: unknown) => { void this.teardown(e instanceof Error ? e : new Error(String(e))); });
    return p;
  }

  private sendRaw(message: unknown): void {
    this.enqueue(JSON.stringify(message)).catch(() => { /* closed */ });
  }

  /** @internal */
  sendCancel(requestId: number, reason?: string): void {
    const params: Record<string, unknown> = { requestId };
    if (reason) params.reason = reason.slice(0, 500);
    this.sendRaw({ jsonrpc: "2.0", method: CANCELLED, params });
  }

  private sendError(id: string | number | null, error: JsonRpcErrorObject): void {
    this.sendRaw({ jsonrpc: "2.0", id, error });
  }

  // ---------------------------------------------------------------------------------------------------- client API

  private requireClient(what: string): void {
    if (this.role !== "client") throw new Error(`a server session cannot ${what} (BHMS-TRN-001)`);
  }

  /**
   * Send a request and return its result object. Rejects with BhmsError / JsonRpcError for an error response,
   * `BhmsError(DEADLINE_EXCEEDED, mayHaveActed)` after the timeout (the request is cancelled on the wire and the outcome
   * is unknown, BHMS-LIF-053), TransportClosed if the connection drops, and with the abort reason after `signal`.
   */
  async request(method: string, params: unknown, options: { timeoutMs?: number; signal?: AbortSignal } = {}): Promise<Record<string, unknown>> {
    this.requireClient("send requests");
    const id = ++this.nextId;
    const text = JSON.stringify({ jsonrpc: "2.0", id, method, params });
    if (Buffer.byteLength(text) > this.maxMessageBytes) {
      throw new BhmsError("INVALID_ARGUMENT", `request of ${Buffer.byteLength(text)} bytes exceeds the ${this.maxMessageBytes} byte message limit`, {
        field: "", bound: this.maxMessageBytes, hint: "send less data per request; the server's limits.maxMessageBytes is the bound",
      });
    }
    const limit = options.timeoutMs ?? this.defaultTimeoutMs;
    return new Promise<Record<string, unknown>>((resolve, reject) => {
      let timer: NodeJS.Timeout | undefined;
      const cleanup = (): void => {
        if (timer) clearTimeout(timer);
        options.signal?.removeEventListener("abort", onAbort);
        this.pending.delete(id);
      };
      const onAbort = (): void => {
        cleanup();
        this.sendCancel(id, "aborted by caller");
        reject(options.signal?.reason ?? new Error("aborted"));
      };
      this.pending.set(id, {
        resolve: (r) => { cleanup(); resolve(r); },
        reject: (e) => { cleanup(); reject(e); },
      });
      if (limit > 0) {
        timer = setTimeout(() => {
          cleanup();
          this.sendCancel(id, "timeout");
          reject(new BhmsError("DEADLINE_EXCEEDED", `no response to ${method} within ${limit} ms`, {
            mayHaveActed: true,
            hint: "The outcome is unknown. Check with operations/get, or retry with the same operationKey; never re-issue with a new key (BHMS-LIF-053).",
          }));
        }, limit);
      }
      if (options.signal) {
        if (options.signal.aborted) { onAbort(); return; }
        options.signal.addEventListener("abort", onAbort, { once: true });
      }
      this.enqueue(text).catch((e: unknown) => { cleanup(); reject(e); });
    });
  }

  /** Start a streaming request (`subscriptions/listen`); notifications arrive on the returned stream. */
  stream(method: string, params: unknown, options: { maxBuffer?: number } = {}): ClientStream {
    this.requireClient("send requests");
    const id = ++this.nextId;
    const stream = new ClientStream(id, this, options.maxBuffer ?? 1024);
    this.streams.set(id, stream);
    this.enqueue(JSON.stringify({ jsonrpc: "2.0", id, method, params })).catch((e: unknown) => {
      this.streams.delete(id);
      stream.finish(e);
    });
    return stream;
  }

  /** Send a notification (only `notifications/cancelled` exists client to server). */
  notify(method: string, params: Record<string, unknown>): void {
    this.requireClient("send notifications");
    this.sendRaw({ jsonrpc: "2.0", method, params });
  }

  /** @internal */
  dropStream(id: number): boolean {
    return this.streams.delete(id);
  }

  // ---------------------------------------------------------------------------------------------------- inbound

  private onText(text: string): void {
    let msg: unknown;
    try {
      msg = JSON.parse(text);
    } catch {
      this.sendError(null, { code: PARSE_ERROR, message: "parse error: the frame is not valid JSON" });
      return;
    }
    if (Array.isArray(msg)) {
      this.sendError(null, { code: INVALID_REQUEST, message: "batch arrays are not allowed (BHMS-TRN-002)" });
      return;
    }
    if (typeof msg !== "object" || msg === null || (msg as { jsonrpc?: unknown }).jsonrpc !== "2.0") {
      this.sendError(null, { code: INVALID_REQUEST, message: "not a JSON-RPC 2.0 message" });
      return;
    }
    const m = msg as Record<string, unknown>;
    if (typeof m.method === "string") {
      if (!("id" in m)) this.onNotification(m.method, m.params);
      else if (this.role === "server") this.onRequest(m);
      // a client never receives requests (BHMS-TRN-001): ignore
      else this.log(`ignored a request from the server: ${m.method}`);
    } else if ("result" in m || "error" in m) {
      if (this.role === "client") this.onResponse(m);
      // servers never receive responses (BHMS-TRN-001): ignore
    } else {
      this.sendError(validId(m.id) ? m.id : null, { code: INVALID_REQUEST, message: "neither a request, a notification nor a response" });
    }
  }

  private onNotification(method: string, params: unknown): void {
    if (this.role === "server") {
      if (method !== CANCELLED) return; // unknown notifications are ignored (BHMS-LIF-014)
      const requestId = (params as { requestId?: unknown } | null)?.requestId;
      if (validId(requestId)) this.abandon(requestId);
      return;
    }
    // client: stream notifications
    const meta = (params as { _meta?: Record<string, unknown> } | null)?._meta;
    const sub = meta?.[SUBSCRIPTION_KEY];
    if (typeof sub === "number") this.streams.get(sub)?.push({ method, params: params as Record<string, unknown> });
  }

  private onResponse(m: Record<string, unknown>): void {
    const id = m.id;
    if (typeof id !== "number") return;
    const stream = this.streams.get(id);
    let outcome: { ok: true; result: Record<string, unknown> } | { ok: false; error: unknown };
    if ("error" in m) {
      const e = m.error as JsonRpcErrorObject;
      outcome = { ok: false, error: fromJsonRpc(e) ?? new JsonRpcError(e.code, e.message, e.data) };
    } else {
      outcome = { ok: true, result: m.result as Record<string, unknown> };
    }
    if (stream) {
      this.streams.delete(id);
      if (outcome.ok) stream.finish(undefined, outcome.result);
      else stream.finish(outcome.error);
      return;
    }
    const p = this.pending.get(id);
    if (!p) return; // a response after cancel/timeout is ignored (BHMS-LIF-051)
    if (outcome.ok) p.resolve(outcome.result);
    else p.reject(outcome.error);
  }

  private onRequest(m: Record<string, unknown>): void {
    const id = m.id;
    if (!validId(id)) {
      this.sendError(null, { code: INVALID_REQUEST, message: "request id must be a string or an integer (BHMS-LIF-010)" });
      return;
    }
    if (this.inflight.has(id)) {
      this.sendError(id, { code: INVALID_REQUEST, message: `request id ${JSON.stringify(id)} is already in flight (BHMS-LIF-010)` });
      return;
    }
    if (!this.handler) {
      this.sendError(id, { code: METHOD_NOT_FOUND, message: `method not found: ${String(m.method)}` });
      return;
    }
    if (this.inflight.size + this.detached.size >= this.maxInflight) {
      this.sendRaw({ jsonrpc: "2.0", id, error: new BhmsError("BUSY", "too many requests in flight", { hint: "retry later with the same operationKey" }).toJsonRpc() });
      return;
    }
    const abort = new AbortController();
    const ctx: RequestContext = { id, method: m.method as string, params: m.params, peer: this.peer, session: this, signal: abort.signal };
    const entry: Inflight = { ctx, abort, abandoned: false };
    this.inflight.set(id, entry);
    const run = this.run(entry);
    // The promise is tracked so close() can wait for work that outlives its request.
    this.detached.add(run);
    void run.finally(() => this.detached.delete(run));
  }

  private abandon(id: string | number): void {
    const entry = this.inflight.get(id);
    if (!entry) return; // unknown or finished: ignored (BHMS-LIF-051)
    entry.abandoned = true;
    entry.abort.abort(new Error("request cancelled"));
    this.inflight.delete(id);
  }

  private errorObject(e: unknown): JsonRpcErrorObject {
    if (e instanceof JsonRpcError) return e.toError();
    if (e instanceof BhmsError) {
      try {
        return e.toJsonRpc();
      } catch {
        this.log(`handler raised operation-only error ${e.bhmsCode} as a JSON-RPC error`);
        return internalError().toJsonRpc();
      }
    }
    this.log(`request handler failed: ${e instanceof Error ? e.stack ?? e.message : String(e)}`);
    return internalError().toJsonRpc();
  }

  private async run(entry: Inflight): Promise<void> {
    const { ctx } = entry;
    try {
      const out = await this.handler!(ctx);
      if (isAsyncIterable(out)) {
        await this.runStream(entry, out);
        return;
      }
      if (!entry.abandoned) this.sendRaw({ jsonrpc: "2.0", id: ctx.id, result: out });
    } catch (e) {
      if (!entry.abandoned) this.sendRaw({ jsonrpc: "2.0", id: ctx.id, error: this.errorObject(e) });
    } finally {
      if (this.inflight.get(ctx.id) === entry) this.inflight.delete(ctx.id);
    }
  }

  private async runStream(entry: Inflight, source: AsyncIterable<Notification | Complete>): Promise<void> {
    const { ctx } = entry;
    const iterator = source[Symbol.asyncIterator]();
    const tag = { [SUBSCRIPTION_KEY]: ctx.id };
    const stop = (): void => { void iterator.return?.(undefined)?.catch?.(() => undefined); };
    entry.abort.signal.addEventListener("abort", stop, { once: true });
    try {
      for (;;) {
        const step = await iterator.next();
        if (step.done || entry.abandoned) break;
        const item = step.value;
        if (item instanceof Complete) {
          const result = { ...item.result, _meta: { ...((item.result._meta as object | undefined) ?? {}), ...tag } };
          this.sendRaw({ jsonrpc: "2.0", id: ctx.id, result });
          return;
        }
        const params = { ...item.params, _meta: { ...((item.params._meta as object | undefined) ?? {}), ...tag } };
        await this.enqueue(JSON.stringify({ jsonrpc: "2.0", method: item.method, params })).catch(() => undefined);
      }
    } catch (e) {
      if (!entry.abandoned) this.sendRaw({ jsonrpc: "2.0", id: ctx.id, error: this.errorObject(e) });
    } finally {
      entry.abort.signal.removeEventListener("abort", stop);
    }
  }

  // ---------------------------------------------------------------------------------------------------- teardown

  private async teardown(error?: Error): Promise<void> {
    if (this.closedFlag) return;
    this.closedFlag = true;
    for (const id of [...this.inflight.keys()]) this.abandon(id);
    const reason = new TransportClosed(error?.message ?? "session closed");
    for (const p of [...this.pending.values()]) p.reject(reason);
    this.pending.clear();
    for (const s of [...this.streams.values()]) s.finish(reason);
    this.streams.clear();
    try { await this.transport.close(); } catch { /* already closed */ }
    for (const w of this.closedWaiters.splice(0)) w();
    this.onClose?.(error);
  }
}

function isAsyncIterable(v: unknown): v is AsyncIterable<Notification | Complete> {
  return typeof v === "object" && v !== null && Symbol.asyncIterator in v;
}
