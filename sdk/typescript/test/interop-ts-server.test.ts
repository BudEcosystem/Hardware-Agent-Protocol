// Interop both ways for the TypeScript server: the Python client drives it, and the TS client drives it over every
// transport (stdio subprocess, Unix socket, TCP loopback, WebSocket with a bearer token).
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { Client } from "../src/client.js";
import { BhmsError } from "../src/errors.js";
import { PACKAGE_ROOT } from "./paths.js";
import { pythonAvailable, pythonEnv, sleep, tsDevicePath } from "./helpers.js";

const skipPython = pythonAvailable() ? false : "python3 with the bhms reference SDK is not available";
const deviceCmd = `node ${tsDevicePath()} --memory`;

test("a Python client (strict) drives the TypeScript conformance device over stdio", { skip: skipPython, timeout: 60_000 }, async () => {
  const r = await new Promise<{ status: number | null; stdout: string; stderr: string }>((resolve) => {
    const child = spawn("python3", [join(PACKAGE_ROOT, "test/py/drive_ts_server.py"), `stdio:${deviceCmd}`], { env: pythonEnv(), cwd: PACKAGE_ROOT });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d: Buffer) => { stdout += d.toString(); });
    child.stderr.on("data", (d: Buffer) => { stderr += d.toString(); });
    child.on("close", (status) => resolve({ status, stdout, stderr }));
  });
  assert.equal(r.status, 0, `python driver failed:\n${r.stderr}\n${r.stdout}`);
  const result = JSON.parse(r.stdout.trim().split("\n").pop()!) as { ok: boolean; checks: string[] };
  assert.equal(result.ok, true);
  assert.ok(result.checks.length >= 20, `only ${result.checks.length} checks ran`);
});

test("a TS client drives a TS server over stdio (subprocess), including stdin EOF shutdown", { timeout: 30_000 }, async () => {
  const client = await Client.connect(`stdio:${deviceCmd}`, { strict: true });
  try {
    const op = (await client.actionsInvoke("axis-1", "pulse", { count: 4 }, { operationKey: "stdio-1", waitMs: 2000 })).operation;
    assert.deepEqual(op.result, { pulses: 4 });
    assert.equal(client.discovered!.principal?.id, "stdio");
    assert.deepEqual(client.discovered!.principal?.scopes, ["admin"]);
  } finally {
    await client.close();
  }
});

test("TS server: nothing but BHMS messages on stdout, exits on stdin EOF", { timeout: 20_000 }, async () => {
  const child = spawn(process.execPath, [tsDevicePath(), "--memory"], { stdio: ["pipe", "pipe", "pipe"] });
  const out: string[] = [];
  child.stdout.on("data", (d: Buffer) => out.push(...d.toString().split("\n").filter(Boolean)));
  child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: 1, method: "server/discover", params: { _meta: { "bhms/protocolVersion": "2026-11-13" } } }) + "\n");
  child.stdin.write("this is not json\n");
  child.stdin.write(JSON.stringify([{ jsonrpc: "2.0", id: 2, method: "x", params: {} }]) + "\n");
  await sleep(300);
  child.stdin.end();
  const code = await new Promise<number | null>((r) => child.once("exit", r));
  assert.equal(code, 0);
  assert.equal(out.length, 3);
  for (const line of out) assert.equal((JSON.parse(line) as { jsonrpc: string }).jsonrpc, "2.0");
  const errors = out.map((l) => JSON.parse(l) as { error?: { code: number }; id: unknown }).filter((m) => m.error);
  assert.deepEqual(errors.map((m) => m.error!.code).sort(), [-32700, -32600].sort());
  assert.ok(errors.every((m) => m.id === null));
});

test("TS client and TS server over a Unix-domain socket and TCP loopback", { timeout: 30_000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "bhms-ts-sock-"));
  const sock = join(dir, "d.sock");
  const unix = spawn(process.execPath, [tsDevicePath(), `unix:${sock}`, "--memory"], { stdio: ["ignore", "ignore", "pipe"] });
  const tcp = spawn(process.execPath, [tsDevicePath(), "tcp://127.0.0.1:0", "--memory"], { stdio: ["ignore", "ignore", "pipe"] });
  const addr = (c: typeof unix): Promise<string> => new Promise((resolve, reject) => {
    c.stderr!.on("data", (d: Buffer) => { const m = /listening on (\S+)/.exec(d.toString()); if (m) resolve(m[1]); });
    c.once("exit", () => reject(new Error("server exited")));
  });
  try {
    await addr(unix);
    const tcpAddress = await addr(tcp);
    for (const target of [`unix:${sock}`, `tcp://${tcpAddress}`]) {
      const client = await Client.connect(target, { strict: true });
      try {
        const op = (await client.actionsInvoke("axis-1", "move_to", { position: 3 }, { waitMs: 2000 })).operation;
        assert.equal(op.effect, "verified", target);
        const sub = await client.subscribe({ observations: [{ deviceId: "pump-1", property: "pressure" }] });
        const first = await sub.next();
        assert.equal(first?.method, "notifications/observation");
        sub.cancel();
      } finally { await client.close(); }
    }
  } finally {
    unix.kill("SIGTERM");
    tcp.kill("SIGTERM");
    rmSync(dir, { recursive: true, force: true });
  }
});

test("TS client and TS server over WebSocket: bearer token required, the principal is admin only with it", { timeout: 30_000 }, async () => {
  const child = spawn(process.execPath, [tsDevicePath(), "ws://127.0.0.1:0", "--memory"], { stdio: ["ignore", "ignore", "pipe"], env: { ...process.env, BHMS_TOKEN: "s3cret-token" } });
  try {
    const address = await new Promise<string>((resolve, reject) => {
      child.stderr!.on("data", (d: Buffer) => { const m = /listening on (\S+)/.exec(d.toString()); if (m) resolve(m[1]); });
      child.once("exit", () => reject(new Error("server exited")));
    });
    await assert.rejects(Client.connect(`ws://${address}`), /401/);
    await assert.rejects(Client.connect(`ws://${address}`, { token: "nope" }), /401/);
    const client = await Client.connect(`ws://${address}`, { token: "s3cret-token", strict: true });
    try {
      assert.deepEqual(client.discovered!.principal?.scopes, ["admin"]);
      const op = (await client.actionsInvoke("axis-1", "pulse", { count: 1 }, { waitMs: 2000 })).operation;
      assert.equal(op.state, "completed");
      await assert.rejects(client.actionsInvoke("axis-1", "pulse", { count: 1000 }), (e: unknown) => e instanceof BhmsError && e.bhmsCode === "OUT_OF_RANGE");
    } finally { await client.close(); }
  } finally { child.kill("SIGTERM"); }
});
