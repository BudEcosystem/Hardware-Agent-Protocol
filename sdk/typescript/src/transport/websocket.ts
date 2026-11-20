/**
 * WebSocket transport (spec/bhms/02-transports.md §2.3), built on the `ws` package (an optional dependency).
 *
 * One JSON-RPC message per text frame and the subprotocol `bhms` (BHMS-TRN-030). A server reachable from anything but
 * loopback must require `Authorization: Bearer <token>` on the upgrade and reject it with HTTP 401 otherwise
 * (BHMS-TRN-031): {@link listenWebSocket} refuses a non-loopback host unless a `token` is configured (and TLS is then the
 * operator's responsibility, BHMS-SEC-004 — terminate it in front of this listener). With a `token`, a missing or wrong
 * bearer is rejected on loopback too unless `allowAnonymousLoopback` is enabled. That option passes headerless peers
 * with no scopes to a server that authenticates each request; it never grants a transport principal privileges.
 *
 * `ws` is loaded lazily so that stdio-only users need not install it.
 *
 * Thread-safety: single event loop.
 */
import { createServer, type IncomingMessage, type Server } from "node:http";
import { timingSafeEqual } from "node:crypto";
import type { Duplex } from "node:stream";
import type { Peer, Transport, TransportSink } from "../jsonrpc/session.js";
import { DEFAULT_MAX_MESSAGE_BYTES, UTF8 } from "./stream.js";
import { LOOPBACK } from "./socket.js";

type WsModule = typeof import("ws");
let wsModule: WsModule | undefined;
async function loadWs(): Promise<WsModule> {
  wsModule ??= (await import("ws")) as WsModule;
  return wsModule;
}

export const SUBPROTOCOL = "bhms";

type WebSocketLike = import("ws").WebSocket;

class WsTransport implements Transport {
  private sink?: TransportSink;
  constructor(private readonly socket: WebSocketLike, readonly peer: Peer, readonly maxMessageBytes: number) {}

  start(sink: TransportSink): void {
    this.sink = sink;
    this.socket.on("message", (data, isBinary) => {
      if (isBinary) return; // BHMS-TRN-030: text frames only
      const bytes = Array.isArray(data) ? Buffer.concat(data) : Buffer.from(data as Buffer);
      if (bytes.length > this.maxMessageBytes) { sink.oversize(); return; }
      let text: string;
      try { text = UTF8.decode(bytes); } catch { sink.invalidUtf8(); return; }
      sink.message(text);
    });
    this.socket.on("close", () => sink.closed());
    this.socket.on("error", (e) => sink.closed(e));
  }

  send(text: string): Promise<void> {
    return new Promise((resolve, reject) => {
      this.socket.send(text, (err) => (err ? reject(err) : resolve()));
    });
  }

  close(): Promise<void> {
    return new Promise((resolve) => {
      if (this.socket.readyState === this.socket.CLOSED) { resolve(); return; }
      this.socket.once("close", () => resolve());
      this.socket.close();
      setTimeout(() => { this.socket.terminate(); }, 1000).unref();
    });
  }
}

/** Connect to `ws://host:port/path` as a client, negotiating the `bhms` subprotocol. */
export async function connectWebSocket(url: string, options: { token?: string; maxMessageBytes?: number } = {}): Promise<Transport> {
  if (options.token && url.startsWith("ws:") && !LOOPBACK.has(new URL(url).hostname.replace(/^\[|\]$/g, ""))) {
    throw new RangeError("credentials require TLS or a local transport (BHMS-SEC-007)");
  }
  const { WebSocket } = await loadWs();
  const max = options.maxMessageBytes ?? DEFAULT_MAX_MESSAGE_BYTES;
  const socket = new WebSocket(url, SUBPROTOCOL, {
    maxPayload: max,
    headers: options.token ? { Authorization: `Bearer ${options.token}` } : undefined,
  });
  await new Promise<void>((resolve, reject) => {
    socket.once("open", () => resolve());
    socket.once("error", reject);
    socket.once("unexpected-response", (_req, res) => reject(new Error(`WebSocket upgrade rejected: HTTP ${res.statusCode}`)));
  });
  if (socket.protocol !== SUBPROTOCOL) {
    socket.terminate();
    throw new Error(`server did not negotiate the "${SUBPROTOCOL}" subprotocol`);
  }
  return new WsTransport(socket, { principal: `ws:${url}`, kind: "ws" }, max);
}

export interface WsListener {
  close(): Promise<void>;
  address: string;
  server: Server;
}

function bearerOk(req: IncomingMessage, token: string): boolean {
  const header = req.headers.authorization ?? "";
  const m = /^Bearer (.+)$/.exec(header);
  if (!m) return false;
  const a = Buffer.from(m[1]);
  const b = Buffer.from(token);
  return a.length === b.length && timingSafeEqual(a, b);
}

/**
 * Listen for WebSocket clients. `token` makes the bearer check mandatory (required off loopback, BHMS-TRN-031); the peer is
 * then `ws:token` with `scopes` (default `admin`). `allowAnonymousLoopback` permits a headerless loopback upgrade only;
 * its requests still need authentication by the session handler. `verifyToken` replaces the single-token check with the caller's own
 * (e.g. a policy table): the peer carries the presented token so the server can resolve its principal per request.
 */
export async function listenWebSocket(
  host: string,
  port: number,
  onTransport: (t: Transport) => void,
  options: { allowAnonymousLoopback?: boolean; token?: string; verifyToken?: (token: string) => boolean; scopes?: string[]; maxMessageBytes?: number; path?: string } = {},
): Promise<WsListener> {
  if (!LOOPBACK.has(host) && !options.token && !options.verifyToken) {
    throw new RangeError(`refusing to listen on ${host} without a bearer token (BHMS-TRN-031)`);
  }
  const { WebSocketServer } = await loadWs();
  const max = options.maxMessageBytes ?? DEFAULT_MAX_MESSAGE_BYTES;
  const http = createServer((_req, res) => { res.writeHead(426, { "Content-Type": "text/plain" }); res.end("BHMS WebSocket endpoint"); });
  const wss = new WebSocketServer({
    noServer: true,
    maxPayload: max,
    handleProtocols: (protocols) => (protocols.has(SUBPROTOCOL) ? SUBPROTOCOL : false),
  });
  http.on("upgrade", (req: IncomingMessage, socket: Duplex, head: Buffer) => {
    if (options.path && req.url !== options.path) { socket.write("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n"); socket.destroy(); return; }
    const bearer = /^Bearer (.+)$/.exec(req.headers.authorization ?? "")?.[1];
    const anonymous = options.allowAnonymousLoopback && LOOPBACK.has(host) && req.headers.authorization === undefined;
    if (!anonymous && (options.verifyToken ? !(bearer !== undefined && options.verifyToken(bearer)) : options.token && !bearerOk(req, options.token))) {
      socket.write("HTTP/1.1 401 Unauthorized\r\nWWW-Authenticate: Bearer\r\nConnection: close\r\n\r\n");
      socket.destroy();
      return;
    }
    // BHMS-TRN-030: the bhms subprotocol is required; an upgrade that does not offer it is refused at the handshake
    const offered = String(req.headers["sec-websocket-protocol"] ?? "").split(",").map((p) => p.trim());
    if (!offered.includes(SUBPROTOCOL)) {
      socket.write("HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n");
      socket.destroy();
      return;
    }
    wss.handleUpgrade(req, socket, head, (ws) => {
      if (ws.protocol !== SUBPROTOCOL) { ws.close(1002, "subprotocol bhms required"); return; }
      // with `verifyToken` the server's policy maps the bearer token to a principal on every request, so the peer carries it
      const peer: Peer = anonymous ? { principal: "ws:anonymous", kind: "ws", scopes: [] } : options.verifyToken
        ? { principal: "ws:token", kind: "ws", token: bearer }
        : { principal: options.token ? "ws:token" : "ws:loopback", kind: "ws", token: bearer, scopes: options.scopes ?? ["admin"] };
      onTransport(new WsTransport(ws, peer, max));
    });
  });
  await new Promise<void>((resolve, reject) => {
    http.once("error", reject);
    http.listen(port, host, () => { http.off("error", reject); resolve(); });
  });
  const a = http.address() as import("node:net").AddressInfo;
  return {
    address: `${host}:${a.port}`,
    server: http,
    close: () => new Promise<void>((resolve) => {
      for (const c of wss.clients) c.terminate();
      http.close(() => resolve());
      http.closeAllConnections?.();
    }),
  };
}
