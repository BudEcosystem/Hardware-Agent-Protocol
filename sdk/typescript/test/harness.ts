import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Client } from "../src/client.js";
import { memoryPair } from "../src/transport/memory.js";
import { build, type Simulator } from "../src/testing/conformanceDevice.js";
import type { DeviceServer, DeviceServerOptions } from "../src/server/server.js";
import type { Peer } from "../src/jsonrpc/session.js";

export interface Rig {
  server: DeviceServer;
  sim: Simulator;
  client: Client;
  stateDir?: string;
  /** Connect another client (with its own principal). */
  connect(peer?: Partial<Peer>): Promise<Client>;
  close(): Promise<void>;
}

/** A conformance device and a strict in-process client. `durable` journals under a temporary directory. */
export async function rig(options: DeviceServerOptions & { durable?: boolean; stateDir?: string; peer?: Partial<Peer>; keepState?: boolean } = {}): Promise<Rig> {
  const { durable, peer, keepState, ...serverOptions } = options;
  const stateDir = durable ? (options.stateDir ?? mkdtempSync(join(tmpdir(), "bhms-ts-state-"))) : undefined;
  const { server, sim } = build({ memory: !durable, stateDir, log: () => undefined, cancelGraceMs: 200, ...serverOptions });
  await server.start();
  const clients: Client[] = [];
  const connect = async (p?: Partial<Peer>): Promise<Client> => {
    const [c, s] = memoryPair({ serverPeer: { ...peer, ...p } });
    server.serve(s);
    const client = await Client.fromTransport(c, { strict: true });
    clients.push(client);
    return client;
  };
  const keepAlive = setInterval(() => undefined, 1000); // in-memory transports hold no handle; real ones keep the loop alive
  const client = await connect();
  return {
    server, sim, client, stateDir, connect,
    async close() {
      clearInterval(keepAlive);
      for (const c of clients) await c.close().catch(() => undefined);
      await server.close(500);
      if (durable && !options.stateDir && !keepState && stateDir) rmSync(stateDir, { recursive: true, force: true });
    },
  };
}

export const inject = (c: Client, fault: string): Promise<unknown> => c.request("x-conformance/inject", { fault });
export const counters = (c: Client): Promise<{ counter: number; pulses: number; fifo_reads: number; stops: number; holds: number; trace: Record<string, string>; log: string[][] }> => c.request("x-conformance/counters");
let n = 0;
export const key = (prefix = "k"): string => `${prefix}-${Date.now().toString(36)}-${++n}`;
