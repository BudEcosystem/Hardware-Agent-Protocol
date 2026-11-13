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
import net from "node:net";
import { LineTransport } from "./stream.js";
import type { Transport } from "../jsonrpc/session.js";

export interface Listener {
  close(): Promise<void>;
  /** The bound address: socket path or `host:port`. */
  address: string;
  server: net.Server;
}

const LOOPBACK = new Set(["127.0.0.1", "::1", "localhost"]);

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

/** Listen on a loopback TCP port (0 = ephemeral). Non-loopback hosts are refused (BHMS-TRN-021). */
export function listenTcp(
  host: string,
  port: number,
  onTransport: (t: Transport) => void,
  options: { principal?: string; scopes?: string[]; maxMessageBytes?: number } = {},
): Promise<Listener> {
  if (!LOOPBACK.has(host)) {
    return Promise.reject(new RangeError(`refusing to listen on ${host}: a TCP listener must bind a loopback address (BHMS-TRN-021)`));
  }
  return new Promise((resolve, reject) => {
    const server: net.Server = net.createServer((socket) => {
      track(server, socket);
      onTransport(new LineTransport(socket, socket, { principal: options.principal ?? "tcp:loopback", kind: "tcp", scopes: options.scopes ?? ["admin"] }, options.maxMessageBytes, () => socket.destroy()));
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
