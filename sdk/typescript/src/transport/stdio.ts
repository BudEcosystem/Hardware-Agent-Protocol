/**
 * stdio transports (spec/bhms/02-transports.md §2.1).
 *
 * - {@link stdioServerTransport}: this process is the server; the parent that launched it is the principal and is
 *   `admin` (BHMS-TRN-011, BHMS-SEC-003). Nothing but BHMS messages may be written to stdout (BHMS-TRN-010), so
 *   `console.log` must not be used in a stdio server: log to stderr.
 * - {@link spawnServer}: this process launches a server as a subprocess and talks to it over its stdin/stdout.
 *
 * Thread-safety: single event loop.
 */
import { spawn, type ChildProcess, type SpawnOptions } from "node:child_process";
import { LineTransport } from "./stream.js";
import type { Transport } from "../jsonrpc/session.js";

/** The server end on this process's stdin/stdout. The parent process is `admin`. */
export function stdioServerTransport(maxMessageBytes?: number): Transport {
  return new LineTransport(process.stdin, process.stdout, { principal: "stdio", kind: "stdio", scopes: ["admin"] }, maxMessageBytes);
}

export interface SpawnedServer {
  transport: Transport;
  child: ChildProcess;
}

/**
 * Launch `command args...` as a BHMS stdio server and return the client end of its pipes. The server's stderr is
 * inherited (or piped to `stderr` when given). Killing the child on close is left to the caller (`child.kill()`).
 */
export function spawnServer(command: string, args: string[] = [], options: SpawnOptions & { maxMessageBytes?: number } = {}): SpawnedServer {
  const { maxMessageBytes, ...spawnOptions } = options;
  const child = spawn(command, args, { stdio: ["pipe", "pipe", "inherit"], ...spawnOptions });
  if (!child.stdout || !child.stdin) throw new Error("child process has no stdio pipes");
  const transport = new LineTransport(child.stdout, child.stdin, { principal: `stdio:${command}`, kind: "stdio" }, maxMessageBytes);
  return { transport, child };
}
