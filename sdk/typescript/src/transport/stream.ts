/**
 * Newline-delimited JSON framing over any Node byte stream (spec/bhms/02-transports.md §2.1, §2.2).
 *
 * {@link LineTransport} is the one framing implementation behind stdio, Unix-domain and TCP sockets: a message is one
 * line of UTF-8 JSON terminated by `\n` (BHMS-TRN-010, BHMS-TRN-020). A line longer than `maxMessageBytes` is discarded
 * without buffering the rest of it (BHMS-TRN-004) and reported once through `sink.oversize()`; the connection stays
 * usable. Output honours the stream's back-pressure (`send` resolves after the write drained).
 *
 * Thread-safety: single event loop.
 */
import type { Readable, Writable } from "node:stream";
import type { Peer, Transport, TransportSink } from "../jsonrpc/session.js";

export const DEFAULT_MAX_MESSAGE_BYTES = 1_048_576;

export class LineTransport implements Transport {
  private chunks: Buffer[] = [];
  private size = 0;
  private discarding = false;
  private ended = false;
  private sink?: TransportSink;

  constructor(
    private readonly input: Readable,
    private readonly output: Writable,
    readonly peer: Peer,
    readonly maxMessageBytes: number = DEFAULT_MAX_MESSAGE_BYTES,
    /** Called after the transport closed, e.g. to destroy a socket. */
    private readonly onClose?: () => void,
  ) {}

  start(sink: TransportSink): void {
    this.sink = sink;
    this.input.on("data", (chunk: Buffer | string) => this.onData(typeof chunk === "string" ? Buffer.from(chunk) : chunk));
    const end = (error?: Error): void => {
      if (this.ended) return;
      this.ended = true;
      sink.closed(error);
    };
    this.input.on("end", () => end());
    this.input.on("close", () => end());
    this.input.on("error", (e: Error) => end(e));
    this.output.on("error", (e: Error) => end(e));
  }

  private onData(chunk: Buffer): void {
    let start = 0;
    for (;;) {
      const nl = chunk.indexOf(0x0a, start);
      if (nl < 0) break;
      this.takeLine(chunk.subarray(start, nl));
      start = nl + 1;
    }
    const rest = chunk.subarray(start);
    if (rest.length === 0) return;
    if (this.discarding) return;
    this.size += rest.length;
    if (this.size > this.maxMessageBytes) {
      // Do not buffer an unbounded partial message (BHMS-TRN-004): drop what we have and skip to the next newline.
      this.chunks = [];
      this.size = 0;
      this.discarding = true;
      this.sink?.oversize();
      return;
    }
    this.chunks.push(Buffer.from(rest));
  }

  private takeLine(tail: Buffer): void {
    if (this.discarding) {
      this.discarding = false;
      this.chunks = [];
      this.size = 0;
      return;
    }
    const total = this.size + tail.length;
    const line = this.chunks.length === 0 ? tail : Buffer.concat([...this.chunks, tail]);
    this.chunks = [];
    this.size = 0;
    if (total > this.maxMessageBytes) {
      this.sink?.oversize();
      return;
    }
    let text = line.toString("utf8");
    if (text.endsWith("\r")) text = text.slice(0, -1);
    if (text.length > 0) this.sink?.message(text);
  }

  send(text: string): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      if (this.output.destroyed || this.output.writableEnded) {
        reject(new Error("transport output is closed"));
        return;
      }
      this.output.write(text + "\n", (err) => (err ? reject(err) : resolve()));
    });
  }

  async close(): Promise<void> {
    this.ended = true;
    await new Promise<void>((resolve) => {
      if (this.output.destroyed || this.output.writableEnded) { resolve(); return; }
      this.output.end(() => resolve());
    });
    this.onClose?.();
  }
}
