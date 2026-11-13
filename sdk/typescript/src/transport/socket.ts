/**
 * Unix-domain and TCP socket transports (spec/bhms/02-transports.md §2.2): the stdio framing over a byte stream.
 *
 * - A Unix-domain listener creates its socket with mode 0600 (BHMS-TRN-022) and treats every peer as the owning user:
 *   Node exposes no `SO_PEERCRED`, so the file mode is the access control and the principal is `unix:socket` (`admin`).
 * - A TCP listener binds only to a loopback address (BHMS-TRN-021); a non-loopback host is refused with an error because
 *   this SDK has no TLS + bearer-token path for raw TCP (use WebSocket with `wss`-terminating proxy or a Unix socket).
 *   Every TCP peer is a single configured principal (`principal`, default `tcp:loopback`) with the given `scopes`
 *   (default `["admin"]`: loopback TCP is reachable by any local user, so pass narrower scopes when that matters).
 *
 * Thread-safety: single event loop.
 */
import { chmodSync, existsSync, unlinkSync } from "node:fs";
import { timingSafeEqual } from "node:crypto";
import net from "node:net";
import { BhmsError } from "../errors.js";
import { LineTransport } from "./stream.js";
import type { Peer, Transport, TransportSink } from "../jsonrpc/session.js";

export interface Listener {
  close(): Promise<void>;
  /** The bound address: socket path or `host:port`. */
  address: string;
  server: net.Server;
}

export const LOOPBACK = new Set(["127.0.0.1", "::1", "localhost"]);

/** Connect to a `unix:<path>` / `<path>` socket (or `tcp:host:port`) and return the client transport. */
export function connectSocket(target: string, maxMessageBytes?: number): Promise<Transport> {
  return new Promise((resolve, reject) => {
    let socket: net.Socket;
    if (target.startsWith("tcp:")) {
      const [host, port] = splitHostPort(target.slice(4));
      socket = net.connect({ host, port });
    } else {
      socket = net.connect({ path: target.startsWith("unix:") ? target.slice(5) : target });
    }
    socket.once("error", reject);
    socket.once("connect", () => {
      socket.off("error", reject);
      resolve(new LineTransport(socket, socket, { principal: `socket:${target}`, kind: target.startsWith("tcp:") ? "tcp" : "unix" }, maxMessageBytes, () => socket.destroy()));
    });
  });
}

function splitHostPort(s: string): [string, number] {
  const i = s.lastIndexOf(":");
  if (i < 0) throw new RangeError(`expected host:port, got ${s}`);
  return [s.slice(0, i).replace(/^\[|\]$/g, ""), Number(s.slice(i + 1))];
}

/** Listen on a Unix-domain socket (mode 0600). `onTransport` receives each accepted connection. */
export function listenUnix(path: string, onTransport: (t: Transport) => void, maxMessageBytes?: number): Promise<Listener> {
  return new Promise((resolve, reject) => {
    if (existsSync(path)) unlinkSync(path);
    const server: net.Server = net.createServer((socket) => {
      track(server, socket);
      onTransport(new LineTransport(socket, socket, { principal: "unix:socket", kind: "unix", scopes: ["admin"] }, maxMessageBytes, () => socket.destroy()));
    });
    server.once("error", reject);
    server.listen(path, () => {
      chmodSync(path, 0o600);
      server.off("error", reject);
      resolve({ address: path, server, close: () => closeServer(server) });
    });
  });
}

/** The `_meta` key a client uses to present the bearer token on every request over raw TCP (an extension key, BHMS-LIF-016). */
export const BEARER_KEY = "org.bhms.sdk/bearer";

/**
 * Wraps a transport so that every request except `server/discover` must carry the bearer token in
 * `params._meta["org.bhms.sdk/bearer"]` (BHMS-SEC-001: a network transport without a valid credential is rejected). A request
 * without it is answered `UNAUTHORIZED` here and never reaches the session.
 */
class BearerGate implements Transport {
  readonly peer: Peer;
  readonly maxMessageBytes: number;
  constructor(private readonly inner: Transport, private readonly token: string, peer: Peer) {
    this.peer = peer;
    this.maxMessageBytes = inner.maxMessageBytes;
  }

  start(sink: TransportSink): void {
    this.inner.start({
      ...sink,
      message: (text) => { if (this.admit(text)) sink.message(text); },
      oversize: () => sink.oversize(),
      invalidUtf8: () => sink.invalidUtf8(),
      closed: (e) => sink.closed(e),
    });
  }

  private admit(text: string): boolean {
    let msg: { id?: unknown; method?: unknown; params?: { _meta?: Record<string, unknown> } };
    try { msg = JSON.parse(text); } catch { return true; } // the session answers a parse error
    if (typeof msg !== "object" || msg === null || Array.isArray(msg) || typeof msg.method !== "string" || !("id" in msg)) return true;
    if (msg.method === "server/discover") return true;
    const presented = msg.params?._meta?.[BEARER_KEY];
    const a = Buffer.from(typeof presented === "string" ? presented : "");
    const b = Buffer.from(this.token);
    if (a.length === b.length && timingSafeEqual(a, b)) return true;
    const id = typeof msg.id === "string" || typeof msg.id === "number" ? msg.id : null;
    const error = new BhmsError("UNAUTHORIZED", "this transport needs a bearer token", { hint: `send params._meta["${BEARER_KEY}"] with the server's token` }).toJsonRpc();
    void this.inner.send(JSON.stringify({ jsonrpc: "2.0", id, error })).catch(() => undefined);
    return false;
  }

  send(text: string): Promise<void> { return this.inner.send(text); }
  close(): Promise<void> { return this.inner.close(); }
}

/**
 * Listen on a loopback TCP port (0 = ephemeral). Non-loopback hosts are refused (BHMS-TRN-021), and so is a listener without
 * a `token`: raw TCP carries no credential of its own, so every request except `server/discover` must present the token
 * (see {@link BearerGate}); the peer then has `scopes` (default `["admin"]`, like a WebSocket bearer).
 */
export function listenTcp(
  host: string,
  port: number,
  onTransport: (t: Transport) => void,
  options: { token: string; principal?: string; scopes?: string[]; maxMessageBytes?: number },
): Promise<Listener> {
  if (!LOOPBACK.has(host)) {
    return Promise.reject(new RangeError(`refusing to listen on ${host}: a TCP listener must bind a loopback address (BHMS-TRN-021)`));
  }
  if (!options || typeof options.token !== "string" || options.token.length === 0) {
    return Promise.reject(new RangeError("refusing to listen on TCP without a bearer token: raw TCP carries no credential (BHMS-SEC-001)"));
  }
  return new Promise((resolve, reject) => {
    const server: net.Server = net.createServer((socket) => {
      track(server, socket);
      const peer: Peer = { principal: options.principal ?? "tcp:token", kind: "tcp", scopes: options.scopes ?? ["admin"] };
      const inner = new LineTransport(socket, socket, peer, options.maxMessageBytes, () => socket.destroy());
      onTransport(new BearerGate(inner, options.token, peer));
    });
    server.once("error", reject);
    server.listen(port, host, () => {
      server.off("error", reject);
      const a = server.address() as net.AddressInfo;
      resolve({ address: `${host}:${a.port}`, server, close: () => closeServer(server) });
    });
  });
}

const open = new WeakMap<net.Server, Set<net.Socket>>();
function track(server: net.Server, socket: net.Socket): void {
  let set = open.get(server);
  if (!set) { set = new Set(); open.set(server, set); }
  set.add(socket);
  socket.once("close", () => set!.delete(socket));
}

function closeServer(server: net.Server): Promise<void> {
  return new Promise((resolve) => {
    server.close(() => resolve());
    for (const s of open.get(server) ?? []) s.destroy();
  });
}
