import assert from "node:assert/strict";
import { test } from "node:test";
import { Client } from "../src/client.js";
import { BhmsError } from "../src/errors.js";
import { Session, type Peer } from "../src/jsonrpc/session.js";
import { DeviceServer } from "../src/server/server.js";
import { tokenDigest } from "../src/server/authority.js";
import { memoryPair } from "../src/transport/memory.js";
import { connectWebSocket } from "../src/transport/websocket.js";

const unauthorized = (e: unknown): boolean => e instanceof BhmsError && e.bhmsCode === "UNAUTHORIZED";
const metadata = (credential?: unknown): Record<string, unknown> => ({
  "bhms/protocolVersion": "2026-11-13",
  ...(credential === undefined ? {} : { "bhms/authorization": credential }),
});

test("standard request credentials replace the stdio parent for one request only, without invalid-token fallback", async () => {
  const srv = new DeviceServer("auth", { store: "memory", policyDocument: {
    principals: { reader: { tokens: [tokenDigest("reader-secret")], scopes: ["read"] } },
  } });
  srv.extension("test/auth", {}, { "x-test/identity": async (params, ctx) => ({
    principal: srv.authenticate(ctx).wire(), params, contextParams: ctx.params,
  }) });
  await srv.start();
  const [c, s] = memoryPair({ serverPeer: { kind: "stdio", principal: "parent", scopes: ["admin"] } });
  srv.serve(s);
  const client = new Session(c, { role: "client" }).start();
  const discover = (credential?: unknown) => client.request("server/discover", { _meta: metadata(credential) });
  try {
    assert.deepEqual((await discover("Bearer reader-secret")).principal, { id: "reader", scopes: ["read"] });
    const extension = await client.request("x-test/identity", { _meta: metadata("Bearer reader-secret") });
    assert.deepEqual(extension.principal, { id: "reader", scopes: ["read"] });
    assert.ok(!JSON.stringify(extension).includes("reader-secret"));
    for (const invalid of ["Bearer wrong", "reader-secret", 123, null, "Bearer "]) {
      await assert.rejects(discover(invalid), (error: unknown) => {
        assert.ok(unauthorized(error));
        assert.ok(!JSON.stringify((error as BhmsError).toJsonRpc()).includes("reader-secret"));
        return true;
      });
    }
    assert.deepEqual((await discover()).principal, { id: "parent", scopes: ["admin"] });
    srv.setPolicy({ principals: {} });
    await assert.rejects(discover("Bearer reader-secret"), unauthorized);
  } finally { await client.close(); await srv.close(); }
});

for (const peer of [
  { kind: "unix", principal: "owner", scopes: ["admin"] },
  { kind: "ws", principal: "header", token: "header-secret", scopes: ["admin"] },
] satisfies Peer[]) {
  test(`a request credential conflicts with the ${peer.kind} transport identity`, async () => {
    const srv = new DeviceServer("auth", { store: "memory", token: "reader-secret" });
    await srv.start();
    const [c, s] = memoryPair({ serverPeer: peer });
    srv.serve(s);
    const client = new Session(c, { role: "client" }).start();
    try {
      await assert.rejects(client.request("server/discover", { _meta: metadata("Bearer reader-secret") }), unauthorized);
    } finally { await client.close(); await srv.close(); }
  });
}

test("a headerless loopback WebSocket authenticates each request separately", async () => {
  const srv = new DeviceServer("auth", { store: "memory", token: "reader-secret" });
  const address = await srv.run("ws://127.0.0.1:0");
  const client = new Session(await connectWebSocket(`ws://${address}`), { role: "client" }).start();
  try {
    await assert.rejects(client.request("server/discover", { _meta: metadata() }), unauthorized);
    assert.deepEqual((await client.request("server/discover", { _meta: metadata("Bearer reader-secret") })).principal,
      { id: "token", scopes: ["admin"] });
    await assert.rejects(client.request("server/discover", { _meta: metadata() }), unauthorized);
  } finally { await client.close(); await srv.close(); }
});

test("TLS listener promises and outbound credential transport checks fail before opening a connection", async () => {
  for (const scheme of ["wss", "https", "tcps"]) {
    const srv = new DeviceServer("tls", { store: "memory" });
    await assert.rejects(srv.run(`${scheme}://127.0.0.1:0`), /BHMS-SEC-007/);
  }
  for (const scheme of ["ws", "tcp"]) {
    await assert.rejects(Client.connect(`${scheme}://192.0.2.1:1`, { token: "secret" }), /BHMS-SEC-007/);
  }
  await assert.rejects(connectWebSocket("ws://192.0.2.1:1", { token: "secret" }), /BHMS-SEC-007/);
});
