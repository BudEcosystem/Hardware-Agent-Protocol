import assert from "node:assert/strict";
import { mkdtempSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PassThrough } from "node:stream";
import { test } from "node:test";
import { BhmsError, JsonRpcError } from "../src/errors.js";
import { Complete, Session, type Handler, type Notification } from "../src/jsonrpc/session.js";
import { connectSocket, listenTcp, listenUnix } from "../src/transport/socket.js";
import { LineTransport } from "../src/transport/stream.js";
import { memoryPair } from "../src/transport/memory.js";
import { connectWebSocket, listenWebSocket } from "../src/transport/websocket.js";

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

function pair(handler: Handler, serverOptions: { maxMessageBytes?: number } = {}): { client: Session; server: Session } {
  const [c, s] = memoryPair(serverOptions);
  const server = new Session(s, { role: "server", handler, log: () => undefined }).start();
  const client = new Session(c, { role: "client" }).start();
  return { client, server };
}

test("concurrent requests are correlated by id and may finish out of order", async () => {
  const { client } = pair(async (ctx) => {
    const p = ctx.params as { ms: number; v: string };
    await sleep(p.ms);
    return { resultType: "complete", v: p.v };
  });
  const [a, b] = await Promise.all([client.request("t", { ms: 40, v: "slow" }), client.request("t", { ms: 1, v: "fast" })]);
  assert.equal(a.v, "slow");
  assert.equal(b.v, "fast");
  await client.close();
});

test("a BhmsError maps to its JSON-RPC code and back; any other error is INTERNAL without detail", async () => {
  const { client } = pair(async (ctx) => {
    if (ctx.method === "bhms") throw new BhmsError("OUT_OF_RANGE", "too high", { field: "arguments.x", bound: { maximum: 3 }, hint: "send less" });
    if (ctx.method === "rpc") throw new JsonRpcError(-32601, "no such method");
    throw new Error("secret detail");
  });
  await assert.rejects(client.request("bhms", {}), (e: BhmsError) => e.bhmsCode === "OUT_OF_RANGE" && e.field === "arguments.x" && e.mayHaveActed === false);
  await assert.rejects(client.request("rpc", {}), (e: JsonRpcError) => e.code === -32601);
  await assert.rejects(client.request("boom", {}), (e: BhmsError) => e.bhmsCode === "INTERNAL" && e.mayHaveActed && !e.message.includes("secret"));
  await client.close();
});

test("malformed frames, batches and oversize frames are answered with id null and the session keeps going", async () => {
  const up = new PassThrough();
  const down = new PassThrough();
  const server = new Session(new LineTransport(up, down, { principal: "t", kind: "stdio", scopes: ["admin"] }, 2048), {
    role: "server", handler: async () => ({ resultType: "complete" }), log: () => undefined,
  }).start();
  const lines: string[] = [];
  down.on("data", (d: Buffer) => lines.push(...d.toString().split("\n").filter(Boolean)));
  up.write("{not json\n");
  up.write("[{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"x\",\"params\":{}}]\n");
  up.write(JSON.stringify({ jsonrpc: "2.0", id: 5, method: "x", params: { pad: "a".repeat(5000) } }) + "\n");
  up.write(JSON.stringify({ jsonrpc: "2.0", id: 6, method: "x", params: {} }) + "\n");
  await sleep(50);
  const msgs = lines.map((l) => JSON.parse(l));
  assert.deepEqual(msgs.slice(0, 3).map((m) => [m.id, m.error.code]), [[null, -32700], [null, -32600], [null, -32600]]);
  assert.equal(msgs[3].id, 6);
  assert.equal(msgs[3].result.resultType, "complete");
  void server;
});

test("a cancelled request gets no response but its handler keeps running (BHMS-LIF-050/051)", async () => {
  let finished = false;
  let aborted = false;
  const { client, server } = pair(async (ctx) => {
    ctx.signal.addEventListener("abort", () => { aborted = true; });
    await sleep(80);
    finished = true;
    return { resultType: "complete" };
  });
  const ctl = new AbortController();
  const p = client.request("slow", {}, { signal: ctl.signal });
  await sleep(10);
  ctl.abort(new Error("stop waiting"));
  await assert.rejects(p, /stop waiting/);
  await sleep(150);
  assert.ok(aborted, "the handler's signal is aborted");
  assert.ok(finished, "the handler ran to completion");
  assert.equal(server.inflightCount, 0);
  await client.close();
});

test("a request timeout is DEADLINE_EXCEEDED with mayHaveActed and cancels on the wire", async () => {
  const { client } = pair(async () => { await sleep(200); return { resultType: "complete" }; });
  await assert.rejects(client.request("slow", {}, { timeoutMs: 20 }), (e: BhmsError) => e.bhmsCode === "DEADLINE_EXCEEDED" && e.mayHaveActed);
  await client.close();
});

test("streams: notifications are tagged with the request id; the result ends the stream", async () => {
  const { client } = pair(async () => (async function* (): AsyncGenerator<Notification | Complete> {
    yield { method: "notifications/event", params: { n: 1 } };
    yield { method: "notifications/event", params: { n: 2 } };
    yield new Complete({ resultType: "complete", endReason: "shutdown" });
  })());
  const stream = client.stream("subscriptions/listen", {});
  const seen: unknown[] = [];
  for await (const n of stream) seen.push((n.params as { _meta: Record<string, unknown>; n: number })._meta["bhms/subscriptionId"], (n.params as { n: number }).n);
  assert.deepEqual(seen, [stream.id, 1, stream.id, 2]);
  assert.equal(stream.result?.endReason, "shutdown");
  assert.deepEqual((stream.result?._meta as Record<string, unknown>)["bhms/subscriptionId"], stream.id);
  await client.close();
});

test("cancelling a client stream stops the server generator and sends nothing more", async () => {
  let stopped = false;
  const { client } = pair(async () => (async function* (): AsyncGenerator<Notification | Complete> {
    try {
      for (let i = 0; ; i++) { yield { method: "notifications/event", params: { i } }; await sleep(5); }
    } finally { stopped = true; }
  })());
  const stream = client.stream("subscriptions/listen", {});
  await stream.next();
  stream.cancel();
  await sleep(50);
  assert.ok(stopped);
  await client.close();
});


test("Unix-domain sockets: mode 0600, concurrent requests, newline framing", async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-ts-"));
  const path = join(dir, "s.sock");
  const sessions: Session[] = [];
  const listener = await listenUnix(path, (t) => sessions.push(new Session(t, { role: "server", handler: async (ctx) => ({ resultType: "complete", echo: ctx.params }), log: () => undefined }).start()));
  try {
    assert.equal(statSync(path).mode & 0o777, 0o600);
    const client = new Session(await connectSocket(path), { role: "client" }).start();
    const results = await Promise.all([1, 2, 3].map((n) => client.request("echo", { n })));
    assert.deepEqual(results.map((r) => (r.echo as { n: number }).n), [1, 2, 3]);
    await client.close();
  } finally {
    await Promise.all(sessions.map((s) => s.close()));
    await listener.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("TCP listeners bind only loopback (BHMS-TRN-021)", async () => {
  await assert.rejects(listenTcp("0.0.0.0", 0, () => undefined, { token: "t" }), /loopback/);
  const sessions: Session[] = [];
  const listener = await listenTcp("127.0.0.1", 0, (t) => sessions.push(new Session(t, { role: "server", handler: async () => ({ resultType: "complete" }), log: () => undefined }).start()), { token: "tcp-secret" });
  try {
    const client = new Session(await connectSocket(`tcp:${listener.address}`), { role: "client" }).start();
    assert.equal((await client.request("x", { _meta: { "org.bhms.sdk/bearer": "tcp-secret" } })).resultType, "complete");
    await client.close();
  } finally {
    await Promise.all(sessions.map((s) => s.close()));
    await listener.close();
  }
});

test("WebSocket: subprotocol bhms, bearer token required (401 otherwise), one message per frame", async () => {
  const sessions: Session[] = [];
  const listener = await listenWebSocket("127.0.0.1", 0, (t) => sessions.push(new Session(t, { role: "server", handler: async (ctx) => ({ resultType: "complete", principal: ctx.peer.principal }), log: () => undefined }).start()), { token: "s3cret" });
  try {
    await assert.rejects(connectWebSocket(`ws://${listener.address}`), /401/);
    await assert.rejects(connectWebSocket(`ws://${listener.address}`, { token: "wrong" }), /401/);
    const client = new Session(await connectWebSocket(`ws://${listener.address}`, { token: "s3cret" }), { role: "client" }).start();
    assert.equal((await client.request("who", {})).principal, "ws:token");
    await client.close();
  } finally {
    await Promise.all(sessions.map((s) => s.close()));
    await listener.close();
  }
  await assert.rejects(listenWebSocket("0.0.0.0", 0, () => undefined), /bearer token/);
});
