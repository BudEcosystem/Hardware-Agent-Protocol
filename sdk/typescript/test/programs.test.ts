// programs/*: the shared conformance vectors (spec/bhms/conformance/vectors/programs.json) plus execution semantics.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { BhmsError } from "../src/errors.js";
import { Client } from "../src/client.js";
import { digest } from "../src/canonical.js";
import { DeviceServer } from "../src/server/server.js";
import { memoryPair } from "../src/transport/memory.js";
import type { Operation, Program } from "../src/generated/types.js";
import { counters, inject, key, rig } from "./harness.js";
import { REPO_ROOT } from "./paths.js";
import { sleep, tsDevicePath } from "./helpers.js";

interface Vectors {
  invalid: Array<{ name: string; program: unknown; arguments: Record<string, unknown>; expect: { codes: string[]; field?: string; bound?: unknown } }>;
  valid: Record<string, unknown>;
}
const vectors = JSON.parse(readFileSync(join(REPO_ROOT, "spec/bhms/conformance/vectors/programs.json"), "utf8")) as Vectors;
const prog = (template: unknown): Program => JSON.parse(JSON.stringify(template).replaceAll("{{axis}}", "axis-1")) as Program;
const code = (c: string, extra?: (e: BhmsError) => boolean) => (e: unknown): boolean => e instanceof BhmsError && e.bhmsCode === c && (extra ? extra(e) : true);

async function settle(c: Client, id: string, ms = 10_000): Promise<Operation> {
  return (await c.operationsWait(id, ms)).operation;
}

test("every invalid program vector is refused before any step, with the program path, creating no operation", async () => {
  const r = await rig();
  try {
    const before = (await counters(r.client)).counter;
    for (const v of vectors.invalid) {
      let err: unknown;
      try {
        await r.client.programsRun({ program: prog(v.program), arguments: v.arguments });
      } catch (e) { err = e; }
      assert.ok(err instanceof BhmsError, `${v.name}: expected a refusal`);
      assert.ok(v.expect.codes.includes(err.bhmsCode), `${v.name}: ${err.bhmsCode} not in ${v.expect.codes}`);
      assert.equal(err.mayHaveActed, false, v.name);
      const field = err.field ?? "";
      if (v.expect.field) assert.ok(field === v.expect.field || field.startsWith(v.expect.field) || (v.expect.field.startsWith(field) && field.startsWith("program")), `${v.name}: field ${field}, wanted ${v.expect.field}`);
      if (v.expect.bound !== undefined) assert.deepEqual(err.bound, v.expect.bound, v.name);
    }
    assert.equal((await r.client.operationsList()).operations.length, 0);
    assert.equal((await counters(r.client)).counter, before);
  } finally { await r.close(); }
});

test("ordered program: derived-key children in order, step history, progress, digest and effect", async () => {
  const r = await rig();
  try {
    const program = prog(vectors.valid.ordered);
    const started = (await r.client.programsRun({ program, arguments: {}, waitMs: 5000 })).operation;
    const op = started.state === "completed" ? started : await settle(r.client, started.operationId);
    assert.equal(op.state, "completed");
    assert.equal(op.kind, "program");
    assert.equal(op.programDigest, digest(program));
    assert.equal(op.effect, "unverified");
    const full = (await r.client.operationsGet(op.operationId)).operation;
    assert.deepEqual((full.history ?? []).filter((h) => h.kind === "step").map((h) => h.stepIndex), [0, 1, 2, 3]);
    assert.deepEqual(full.progress, { stepsCompleted: 4, stepsTotal: 4 });
    const kids = (await r.client.operationsList({ parentOperationId: op.operationId })).operations.sort((a, b) => (a.createdAt < b.createdAt ? -1 : 1));
    assert.equal(kids.length, 2);
    kids.forEach((k, i) => {
      assert.equal(k.keyOrigin, "derived");
      assert.equal(k.parentOperationId, op.operationId);
      assert.equal(k.operationKey, "d-" + createHash("sha256").update(`${op.operationId}/${i * 2}`).digest("hex").slice(0, 40));
      assert.equal(k.state, "completed");
    });
    const none = (await r.client.programsRun({ program: prog(vectors.valid.no_effect), arguments: {}, waitMs: 3000 })).operation;
    assert.equal(none.effect, "none");
    assert.deepEqual(none.result, {});
  } finally { await r.close(); }
});

test("repeat, references, saveAs and output: scopes, selectors, literal escape and evaluated result", async () => {
  const r = await rig();
  try {
    const program: Program = {
      bhmsProgram: "2026-11-13", name: "scan", description: "move in steps and read back",
      input: { type: "object", additionalProperties: false, required: ["start", "n"], properties: { start: { type: "number", "x-bhms-unit": "mm", minimum: 0, maximum: 100 }, n: { type: "integer", "x-bhms-unit": "1", minimum: 1, maximum: 3 } } },
      maxDurationMs: 60000,
      steps: [
        { kind: "repeat", times: "${n}", as: "i", steps: [
          { kind: "invoke", deviceId: "axis-1", action: "pulse", arguments: { count: 1 }, saveAs: "p" },
          { kind: "assert", predicate: { op: "ge", left: "${p.pulses}", right: 1 }, message: "pulses must count up" },
        ] },
        { kind: "invoke", deviceId: "axis-1", action: "move_to", arguments: { position: "${start}" }, saveAs: "m" },
        { kind: "read", deviceId: "axis-1", property: "position", fresh: true, saveAs: "obs" },
      ],
      output: { last: "${p.pulses}", at: "${obs.value}", moved: "${m.position}", literal: "$${keep}" },
    } as unknown as Program;
    const info = (await r.client.programsRegister(program)).info;
    assert.equal(info.maxExecutedSteps, 8);
    assert.equal(info.worstCaseDurationMs, 3 * (1000 + 0) + 5000 + 1000);
    assert.deepEqual(info.devices, ["axis-1"]);
    const op = (await r.client.programsRun({ digest: info.digest, arguments: { start: 12.5, n: 3 }, waitMs: 5000 })).operation;
    assert.equal(op.state, "completed", JSON.stringify(op.error));
    assert.deepEqual(op.result, { last: 3, at: 12.5, moved: 12.5, literal: "${keep}" });
    assert.deepEqual(op.progress, { stepsCompleted: 8, stepsTotal: 8 });
    await assert.rejects(r.client.programsRun({ digest: info.digest, arguments: { start: 12.5, n: 4 } }), code("OUT_OF_RANGE", (e) => e.field === "arguments.n"));
  } finally { await r.close(); }
});

test("a failing step stops the program: DEVICE_FAULT with mayHaveActed, earlier effects stay, no later step", async () => {
  const r = await rig();
  try {
    const before = (await counters(r.client)).counter;
    const op = (await r.client.programsRun({ program: prog(vectors.valid.failing), arguments: {}, waitMs: 5000 })).operation;
    assert.equal(op.state, "failed");
    assert.equal(op.error?.bhmsCode, "DEVICE_FAULT");
    assert.equal(op.error?.mayHaveActed, true);
    const full = (await r.client.operationsGet(op.operationId)).operation;
    assert.deepEqual((full.history ?? []).filter((h) => h.kind === "step").map((h) => h.stepIndex), [0, 1]);
    assert.equal(full.progress?.stepsCompleted, 1);
    assert.equal((await counters(r.client)).counter, before + 2);
  } finally { await r.close(); }
});

test("assert false is STALE with the message as hint; waitUntil ignores invalid samples and times out", async () => {
  const r = await rig();
  try {
    const a = (await r.client.programsRun({ program: prog(vectors.valid.assert_false), arguments: {}, waitMs: 3000 })).operation;
    assert.equal(a.state, "failed");
    assert.equal(a.error?.bhmsCode, "STALE");
    assert.match(a.error!.hint, /conformance assert message/);
    await inject(r.client, "sensor_invalid");
    const w = (await r.client.programsRun({ program: prog(vectors.valid.wait_until_invalid), arguments: {}, waitMs: 5000 })).operation;
    assert.equal(w.state, "failed");
    assert.equal(w.error?.bhmsCode, "DEADLINE_EXCEEDED");
    await inject(r.client, "none");
    const ok = (await r.client.programsRun({ program: prog(vectors.valid.wait_until_invalid), arguments: {}, waitMs: 5000 })).operation;
    assert.equal(ok.state, "completed", "with a valid sensor the predicate holds");
  } finally { await r.close(); }
});

test("operations/cancel and stop end a running program and cancel its running child; no later step starts", async () => {
  const r = await rig();
  try {
    const before = (await counters(r.client)).counter;
    const op = (await r.client.programsRun({ program: prog(vectors.valid.long), arguments: {} })).operation;
    let kids: Operation[] = [];
    for (let i = 0; i < 100 && kids.length === 0; i++) { kids = (await r.client.operationsList({ parentOperationId: op.operationId })).operations; await sleep(20); }
    assert.ok(kids.length > 0);
    await r.client.operationsCancel(op.operationId, { reason: "test" });
    assert.equal((await settle(r.client, op.operationId, 8000)).state, "canceled");
    assert.equal((await settle(r.client, kids[0].operationId, 8000)).state, "canceled");
    assert.equal((await counters(r.client)).counter, before + 1);

    const second = (await r.client.programsRun({ program: prog(vectors.valid.long), arguments: {} })).operation;
    for (let i = 0; i < 100; i++) { if ((await r.client.operationsList({ parentOperationId: second.operationId })).operations.length > 0) break; await sleep(20); }
    const stop = await r.client.stop("stop the program", { deviceIds: ["axis-1"] });
    assert.equal(stop.stops[0].outcome, "confirmed");
    const done = await settle(r.client, second.operationId, 8000);
    assert.equal(done.state, "canceled");
    assert.ok((await r.client.operationsGet(second.operationId)).operation.history?.some((h) => h.kind === "stop"));
  } finally { await r.close(); }
});

test("maxDurationMs is enforced at run time: no further step starts and the program fails DEADLINE_EXCEEDED", async () => {
  const r = await rig();
  try {
    const program = { ...prog(vectors.valid.no_effect), name: "slowprog", maxDurationMs: 150, steps: [{ kind: "sleep", durationMs: 100 }, { kind: "sleep", durationMs: 40 }, { kind: "invoke", deviceId: "axis-1", action: "pulse", arguments: { count: 1 } }] } as unknown as Program;
    await assert.rejects(r.client.programsRun({ program, arguments: {} }), code("OUT_OF_RANGE", (e) => e.field === "program.maxDurationMs" && e.bound === 1140));
    const ok = { ...program, maxDurationMs: 1140 } as unknown as Program;
    const op = (await r.client.programsRun({ program: ok, arguments: {}, deadlineMs: 120, waitMs: 3000 })).operation;
    assert.equal(op.state, "failed");
    assert.equal(op.error?.bhmsCode, "DEADLINE_EXCEEDED");
    assert.equal((await counters(r.client)).counter, 0, "the effectful step never started");
  } finally { await r.close(); }
});

test("registry: content-addressed, idempotent, immutable; digest and inline runs share one intent; authority is re-checked", async () => {
  const r = await rig();
  try {
    const program = { ...prog(vectors.valid.no_effect), name: "reg_one" } as Program;
    const info = (await r.client.programsRegister(program)).info;
    assert.equal(info.digest, digest(program));
    assert.deepEqual((await r.client.programsRegister(program)).info, info);
    const got = await r.client.programsGet(info.digest);
    assert.deepEqual(got.program, program);
    assert.ok((await r.client.programsList({ limit: 10 })).programs.some((p) => p.digest === info.digest));
    await assert.rejects(r.client.programsGet("sha256:" + "ab".repeat(32)), code("INVALID_ARGUMENT", (e) => e.field === "digest"));
    await assert.rejects(r.client.programsRun({ digest: "sha256:" + "ab".repeat(32), arguments: {} }), code("INVALID_ARGUMENT", (e) => e.field === "digest"));
    const k = key("prog");
    const inline = await r.client.programsRun({ program, arguments: {}, operationKey: k, waitMs: 2000 });
    const byDigest = await r.client.programsRun({ digest: info.digest, arguments: {}, operationKey: k, waitMs: 2000 });
    assert.equal(byDigest.replayed, true);
    assert.equal(byDigest.operation.operationId, inline.operation.operationId);
    const reader = await r.connect({ principal: "reader", scopes: ["read"] });
    await assert.rejects(reader.programsRun({ digest: info.digest, arguments: {} }), code("UNAUTHORIZED", (e) => e.hint.includes("programs:run")));
    await assert.rejects(reader.programsRegister(program), code("UNAUTHORIZED"));
    const runner = await r.connect({ principal: "runner", scopes: ["read", "programs:run"] });
    const effectful = { ...prog(vectors.valid.ordered), name: "needs_scope" } as Program;
    await assert.rejects(runner.programsRun({ program: effectful, arguments: {} }), code("UNAUTHORIZED", (e) => e.hint.includes("invoke:axis-1/pulse") && (e.field ?? "").startsWith("program.steps[0]")));
  } finally { await r.close(); }
});

test("a program that needs a lease requires one covering its steps (BHMS-PRG-006)", async () => {
  const r = await rig();
  try {
    const program = { ...prog(vectors.valid.no_effect), name: "clamper", steps: [{ kind: "invoke", deviceId: "axis-1", action: "clamp", arguments: { force: 10 } }] } as unknown as Program;
    await assert.rejects(r.client.programsRun({ program, arguments: {} }), code("LEASE_REQUIRED", (e) => JSON.stringify(e.bound) === '["axis-1/clamp"]'));
    const { lease } = await r.client.leasesAcquire(["axis-1/clamp"], 5000);
    const op = (await r.client.programsRun({ program, arguments: {}, leaseId: lease.leaseId, waitMs: 3000 })).operation;
    assert.equal(op.state, "completed");
    assert.equal(op.leaseId, lease.leaseId);
    const child = (await r.client.operationsList({ parentOperationId: op.operationId })).operations[0];
    assert.equal(child.leaseId, lease.leaseId);
  } finally { await r.close(); }
});

test("verified children carry their measured evidence up to the program (BHMS-PRG-016, BHMS-OPS-006)", async () => {
  const r = await rig();
  try {
    const program = { ...prog(vectors.valid.no_effect), name: "movers", steps: [{ kind: "invoke", deviceId: "axis-1", action: "move_to", arguments: { position: 10 } }, { kind: "invoke", deviceId: "axis-1", action: "move_to", arguments: { position: 20 } }] } as unknown as Program;
    const op = (await r.client.programsRun({ program, arguments: {}, waitMs: 5000 })).operation;
    assert.equal(op.state, "completed");
    assert.equal(op.effect, "verified");
    assert.deepEqual(Object.keys(op.evidence!.observations!).sort(), ["s1_position", "s2_position"]);
  } finally { await r.close(); }
});

test("programs are never resumed: kill -9 between steps => failed INTERNAL 'server restarted', no step runs after restart", async () => {
  const stateDir = mkdtempSync(join(tmpdir(), "bhms-ts-prog-"));
  try {
    const child = spawn(process.execPath, [tsDevicePath(), "--state-dir", stateDir], { stdio: ["pipe", "pipe", "inherit"] });
    const lines: string[] = [];
    child.stdout.on("data", (d: Buffer) => lines.push(...d.toString().split("\n").filter(Boolean)));
    const meta = { "bhms/protocolVersion": "2026-11-13" };
    const send = (id: number, method: string, params: object): void => { child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params: { _meta: meta, ...params } }) + "\n"); };
    send(1, "programs/run", { program: prog(vectors.valid.interrupted), arguments: {} });
    for (let i = 0; i < 100 && lines.length < 1; i++) await sleep(20);
    const opId = (JSON.parse(lines[0]) as { result: { operation: { operationId: string } } }).result.operation.operationId;
    let progressed = false;
    for (let i = 0; i < 100 && !progressed; i++) {
      send(100 + i, "operations/get", { operationId: opId });
      await sleep(30);
      progressed = lines.some((l) => (JSON.parse(l) as { result?: { operation?: { progress?: { stepsCompleted: number } } } }).result?.operation?.progress?.stepsCompleted === 1);
    }
    assert.ok(progressed, "the first step completed");
    child.kill("SIGKILL");
    await new Promise((r) => child.once("exit", r));

    const srv = new DeviceServer("conformance-device", { stateDir, log: () => undefined });
    const dev = srv.device("axis-1", { resources: ["axis-1/motion"] });
    dev.action("pulse", { effect: "reversible", idempotency: "relative", maxDurationMs: 1000, input: { count: { type: "integer", "x-bhms-unit": "1" } } }, async () => ({}));
    await srv.start();
    const [c, s] = memoryPair({ serverPeer: { principal: "stdio" } });
    srv.serve(s);
    const client = await Client.fromTransport(c, { strict: true });
    try {
      const op = (await client.operationsGet(opId)).operation;
      assert.equal(op.state, "failed");
      assert.equal(op.error?.bhmsCode, "INTERNAL");
      assert.match(op.error!.message, /server restarted/);
      assert.equal(op.error?.mayHaveActed, true);
      assert.match(op.error!.hint, /stepIndex 0/);
      await sleep(300);
      assert.equal((await client.operationsList({ parentOperationId: opId })).operations.length, 1, "no step ran after the restart");
      assert.equal((await client.operationsGet(opId)).operation.state, "failed");
    } finally { await client.close(); await srv.close(200); }
  } finally { rmSync(stateDir, { recursive: true, force: true }); }
});
