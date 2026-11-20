import assert from "node:assert/strict";
import { test } from "node:test";
import { Client } from "../src/client.js";
import { BhmsError } from "../src/errors.js";
import { Session } from "../src/jsonrpc/session.js";
import { Principal } from "../src/server/authority.js";
import { memoryPair } from "../src/transport/memory.js";
import { listenTcp } from "../src/transport/socket.js";
import { rig } from "./harness.js";

const grant = "programs:run:sha256:" + "a".repeat(64);
const budget = { id: "pulses", action: "axis-1/pulse", quantity: "/count", unit: "1", total: 2 };

test("v0.2 discovery exposes grants and budget balances, while v0.1 hides them and enforces the same limits", async () => {
  const r = await rig({ policy: (peer) => new Principal(peer.principal, ["read", "invoke:axis-1/pulse", grant], {}, false, [budget]) });
  try {
    assert.equal(r.client.protocolVersion, "2026-11-15");
    const current = r.client.discovered!;
    assert.deepEqual(current.supportedVersions, ["2026-11-15", "2026-11-13"]);
    assert.equal(current.capabilities.programs?.grants, true);
    assert.equal(current.capabilities.authority?.budgets, true);
    assert.equal(current.principal?.budgets?.[0].remaining, 2);
    const meta = { "bhms/protocolVersion": "2026-11-13" };
    const old = await r.client.request("server/discover", { _meta: meta }) as any;
    assert.equal(old.capabilities.programs.grants, undefined);
    assert.equal(old.capabilities.authority?.budgets, undefined);
    assert.equal(old.principal.budgets, undefined);
    assert.ok(!old.principal.scopes.includes(grant));
    await r.client.request("actions/invoke", { _meta: meta, deviceId: "axis-1", action: "pulse", arguments: { count: 2 }, waitMs: 1000 });
    await assert.rejects(r.client.request("actions/invoke", { _meta: meta, deviceId: "axis-1", action: "pulse", arguments: { count: 1 } }),
      (e: unknown) => e instanceof BhmsError && e.bhmsCode === "OUT_OF_RANGE");
    assert.equal((await r.client.discover()).principal?.budgets?.[0].remaining, 0);
  } finally { await r.close(); }
});

test("client falls back to an older server unless the caller pinned a version", async () => {
  async function attempt(pinned: boolean): Promise<void> {
    const [c, s] = memoryPair();
    const versions: unknown[] = [];
    const server = new Session(s, { role: "server", handler: async (ctx) => {
      const version = (ctx.params as any)._meta["bhms/protocolVersion"];
      versions.push(version);
      if (version !== "2026-11-13") throw new BhmsError("UNSUPPORTED_VERSION", "old server", { bound: ["2026-11-13"] });
      return { resultType: "complete", supportedVersions: ["2026-11-13"], serverInfo: { name: "old", version: "1" }, capabilities: {}, epoch: "old" };
    } }).start();
    try {
      if (pinned) {
        await assert.rejects(Client.fromTransport(c, { protocolVersion: "2026-11-15" }), (e: unknown) => e instanceof BhmsError && e.bhmsCode === "UNSUPPORTED_VERSION");
        assert.deepEqual(versions, ["2026-11-15"]);
      } else {
        const client = await Client.fromTransport(c);
        assert.equal(client.protocolVersion, "2026-11-13");
        assert.deepEqual(versions, ["2026-11-15", "2026-11-13"]);
        await client.close();
      }
    } finally { await server.close(); }
  }
  await attempt(false); await attempt(true);
});

test("the v0.2 client uses the standard bearer carrier over loopback TCP and the gate removes it before dispatch", async () => {
  const sessions: Session[] = [];
  const listener = await listenTcp("127.0.0.1", 0, (t) => sessions.push(new Session(t, { role: "server", handler: async (ctx) => {
    assert.ok(!JSON.stringify(ctx.params).includes("secret"));
    return { resultType: "complete", supportedVersions: ["2026-11-15"], serverInfo: { name: "gate", version: "1" }, capabilities: {}, epoch: "one" };
  } }).start()), { token: "secret" });
  try {
    const client = await Client.connect(`tcp://${listener.address}`, { token: "secret" });
    assert.equal(client.protocolVersion, "2026-11-15");
    await client.close();
    await assert.rejects(Client.connect(`tcp://${listener.address}`, { token: "wrong" }), (e: unknown) => e instanceof BhmsError && e.bhmsCode === "UNAUTHORIZED");
  } finally { for (const s of sessions) await s.close(); await listener.close(); }
});
