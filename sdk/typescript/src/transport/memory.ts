/**
 * In-process transport pair: two {@link Transport}s wired back to back, for tests and for embedding a client and a
 * server in one process. Messages are delivered asynchronously (never re-entrantly), in order, as JSON text — exactly
 * what a real transport would carry.
 *
 * Thread-safety: single event loop.
 */
import type { Peer, Transport, TransportSink } from "../jsonrpc/session.js";

class MemoryEnd implements Transport {
  peerEnd!: MemoryEnd;
  private sink?: TransportSink;
  private closed = false;
  private readonly backlog: string[] = [];

  constructor(readonly peer: Peer, readonly maxMessageBytes: number) {}

  start(sink: TransportSink): void {
    this.sink = sink;
    for (const m of this.backlog.splice(0)) this.deliver(m);
  }

  deliver(text: string): void {
    if (!this.sink) { this.backlog.push(text); return; }
    queueMicrotask(() => { if (!this.closed) this.sink?.message(text); });
  }

  async send(text: string): Promise<void> {
    if (this.closed || this.peerEnd.closed) throw new Error("transport closed");
    if (Buffer.byteLength(text) > this.peerEnd.maxMessageBytes) {
      queueMicrotask(() => this.peerEnd.sink?.oversize());
      return;
    }
    this.peerEnd.deliver(text);
  }

  async close(): Promise<void> {
    if (this.closed) return;
    this.closed = true;
    const other = this.peerEnd;
    queueMicrotask(() => other.sink?.closed());
  }
}

/** A connected pair `[clientEnd, serverEnd]`; the server end's peer defaults to a trusted (`admin`) principal. */
export function memoryPair(options: { serverPeer?: Partial<Peer>; maxMessageBytes?: number } = {}): [Transport, Transport] {
  const max = options.maxMessageBytes ?? 1_048_576;
  const client = new MemoryEnd({ principal: "memory:server", kind: "memory" }, max);
  const server = new MemoryEnd({ principal: "memory:client", kind: "memory", scopes: ["admin"], ...options.serverPeer }, max);
  client.peerEnd = server;
  server.peerEnd = client;
  return [client, server];
}
