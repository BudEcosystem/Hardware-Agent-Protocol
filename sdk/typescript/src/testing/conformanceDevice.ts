#!/usr/bin/env node
/**
 * `conformance-device`: the deterministic simulated device server every BHMS SDK ships; this one mirrors the Python
 * reference (`python -m bhms.testing.conformance_device`) device for device, action for action and number for number.
 *
 * Run it with `node dist/src/testing/conformanceDevice.js [unix:/path | ws://127.0.0.1:port] [--state-dir DIR] [--memory]`
 * (stdio by default), or build it in-process with {@link build}.
 *
 * Behavioural contract (the conformance runner relies on every line of it):
 *
 * Server
 *   `serverInfo.name` is `conformance-device`. Capabilities: devices, observations (`minIntervalMs` 20), operations
 *   (durable unless `--memory`), stop, subscriptions, leases (`minTtlMs` 50, `maxTtlMs` 600000, `maxWaitMs` 30000), events,
 *   and the extension `org.bhms/conformance` with the methods below. (This SDK does not implement `programs/*`.)
 *   Every number is exact and every delay is fixed, so outcomes are reproducible.
 *
 * Device `axis-1`, a simulated linear axis (resources `axis-1/motion`, `axis-1/clamp`)
 *   - `position` (mm, `measured`, observable, `maxRateHz` 50): the simulated encoder. It reads the true position unless the
 *     fault `encoder_disagrees` is set (then it reports position + 1 mm) or `sensor_invalid` (acquisition fails:
 *     `quality: invalid`, `value: null`).
 *   - `counter` (`1`, `reported`): the number of physical commands the device has executed (every action handler that reached
 *     the device increments it exactly once): the device-side counter that proves "no effect" and "exactly one effect".
 *   - `temperature` (Cel, `measured`, `validityMs` 1000, constant 21.5): can be made stale on command: after the fault
 *     `sensor_stale` every acquisition carries 10 000 ms of latency, so observations are `stale`.
 *   - `fifo` (`1`, `readEffect: transaction`, `requiresLease`, resources `axis-1/motion`): each fresh acquisition pops one
 *     value and increments `fifo_reads`.
 *   - `move_to(position: 0-200 mm, multipleOf 0.1)`: absolute, reversible, `completionEvidence: measured`
 *     (`verifiedBy: position`), `cancel: supported`, `maxDurationMs` 5000; takes 20 ms; verified when the encoder agrees
 *     within 0.05 mm.
 *   - `pulse(count: 1-100)`: relative, reversible, reported; adds `count` to `pulses`; takes 1 ms.
 *   - `slow_move(duration_ms: 1-60000 ms, default 1000)`: relative, `cancel: supported`, `maxDurationMs` 61000; honours
 *     cancellation and then ends `canceled` (`effect: unverified`).
 *   - `clamp(force: 0-100 %)`: `requiresLease: true` on `axis-1/clamp`, `onLeaseLoss: cancel`, `cancel: supported`,
 *     `maxDurationMs` 10000; holds for 50 ms.
 *   - `fault()`: irreversible; always ends `failed` with `DEVICE_FAULT` (`mayHaveActed: true`) after incrementing `counter`.
 *   - Stop procedure: halts motion, ends a pending `hang`, and returns (`stopEvidence: reported`).
 *   - Reconcile hook: answers from the device-side command log: `completed` (with the recorded result) when the command
 *     finished, `failed` (`mayHaveActed: true`) when it started but did not finish, `failed` (`mayHaveActed: false`,
 *     `effect: none`) when it never reached the device.
 *
 * Device `pump-1`, a syringe pump (resource `pump-1/plunger`)
 *   - `pressure` (kPa, `measured`, observable, 101.3; `sensor_invalid` applies), `dispensed_volume` (uL, `measured`).
 *   - `dispense(volume: 1-1000 uL, multipleOf 0.1)`: irreversible, relative, `requiresLease: true`,
 *     `requiresFresh: [{pressure, 1000}]`, `completionEvidence: measured` (`verifiedBy: dispensed_volume`), `cancel:
 *     supported`, `maxDurationMs` 60000; takes 10 ms.
 *   - No stop procedure (`stop: unsupported`).
 *
 * Faults: `x-conformance/inject {"fault": <name>}` (not an operation; works even when the journal is read-only)
 *   `none` (clear all), `sensor_invalid`, `sensor_valid`, `sensor_stale`, `encoder_disagrees`, `fail_next` (the next physical
 *   command raises a device fault), `crash_next` (the next handler throws an unexpected error after acting: `unknown`),
 *   `hang_next` (the next command never finishes until stopped or cancelled), `journal_readonly` / `journal_writable`,
 *   `offline` / `online` (device status of `axis-1`). `x-conformance/counters` returns `{counter, pulses, fifo_reads, stops,
 *   log}` where `log` lists `[operationId, "start"|"done"]` entries of the device-side command log.
 *
 * Thread-safety: one event loop.
 */
import { BhmsError } from "../errors.js";
import { Canceled, DeviceFault, Reading, type ActionContext, type Reconciled } from "../server/context.js";
import { DeviceServer, type DeviceServerOptions } from "../server/server.js";
import { int, range } from "../server/schemas.js";
import type { Device } from "../server/device.js";
import { sleep } from "../server/time.js";

export const FAULTS = ["none", "sensor_invalid", "sensor_valid", "sensor_stale", "encoder_disagrees", "fail_next", "crash_next", "hang_next", "journal_readonly", "journal_writable", "offline", "online"] as const;

/** A latch that can be set, waited for and cleared (the simulator's "halt" signal). */
class Latch {
  private waiters: Array<() => void> = [];
  private isSet = false;
  set(): void { this.isSet = true; for (const w of this.waiters.splice(0)) w(); }
  clear(): void { this.isSet = false; }
  wait(): Promise<void> { return this.isSet ? Promise.resolve() : new Promise((resolve) => { this.waiters.push(resolve); }); }
}

/** The device side of the link: true state, counters, the command log and armed faults. */
export class Simulator {
  position = 0;
  pulses = 0;
  counter = 0;
  fifoReads = 0;
  stops = 0;
  volume = 0;
  sensor: "valid" | "invalid" | "stale" = "valid";
  encoderOffset = 0;
  readonly armed = new Set<string>();
  readonly log: Array<[string, string]> = [];
  readonly results = new Map<string, unknown>();
  readonly halt = new Latch();

  /** A command reached the device: count it, log it, then apply armed faults. */
  begin(operationId: string): void {
    this.counter += 1;
    this.log.push([operationId, "start"]);
    if (this.armed.delete("fail_next")) throw new DeviceFault("injected device fault", { partial: "the command started" });
  }

  /** The command finished: log it (after an armed hang or crash). */
  async end(operationId: string, result: unknown, cancelled: AbortSignal): Promise<unknown> {
    if (this.armed.delete("hang_next")) {
      this.halt.clear();
      await Promise.race([
        this.halt.wait(),
        new Promise<void>((resolve) => { if (cancelled.aborted) resolve(); else cancelled.addEventListener("abort", () => resolve(), { once: true }); }),
      ]);
      throw new Canceled({ effect: "unverified", detail: "a hung command was released by stop or cancel" });
    }
    if (this.armed.delete("crash_next")) throw new Error("injected adapter crash after the device acted");
    this.log.push([operationId, "done"]);
    this.results.set(operationId, result);
    return result;
  }
}

function sensorReading(sim: Simulator, value: unknown): unknown {
  if (sim.sensor === "invalid") throw new Error("injected sensor failure");
  if (sim.sensor === "stale") return new Reading(value, { latencyMs: 10_000 });
  return value;
}

/** The conformance device server and its simulator (see the module docs). */
export function build(options: DeviceServerOptions & { memory?: boolean } = {}): { server: DeviceServer; sim: Simulator } {
  const { memory, ...rest } = options;
  const sim = new Simulator();
  const server = new DeviceServer("conformance-device", {
    title: "BHMS conformance device", observationMinIntervalMs: 20, leaseMinTtlMs: 50,
    instructions: "Deterministic simulated devices for conformance testing; nothing is physical.",
    ...(memory ? { store: "memory" as const } : {}), ...rest,
  });
  axis(server, sim);
  pump(server, sim);

  server.extension("org.bhms/conformance", { version: "1", faults: [...FAULTS] }, {
    "x-conformance/inject": async (params, ctx) => {
      const fault = params.fault;
      if (typeof fault !== "string" || !(FAULTS as readonly string[]).includes(fault)) {
        throw new BhmsError("INVALID_ARGUMENT", `unknown fault ${JSON.stringify(fault)}`, { field: "fault", bound: [...FAULTS], hint: `use one of ${FAULTS.join(", ")}` });
      }
      server.authenticate(ctx);
      const axisDevice = server.devices.get("axis-1")!;
      if (fault === "none") {
        sim.armed.clear();
        sim.sensor = "valid";
        sim.encoderOffset = 0;
        axisDevice.setStatus(undefined);
      } else if (fault === "sensor_invalid" || fault === "sensor_valid" || fault === "sensor_stale") {
        sim.sensor = fault.slice("sensor_".length) as Simulator["sensor"];
      } else if (fault === "encoder_disagrees") {
        sim.encoderOffset = 1;
      } else if (fault === "fail_next" || fault === "crash_next" || fault === "hang_next") {
        sim.armed.add(fault);
      } else if (fault === "journal_readonly" || fault === "journal_writable") {
        server.store.setWritable(fault === "journal_writable");
      } else {
        axisDevice.setStatus(fault === "offline" ? "offline" : undefined);
        if (fault === "online") axisDevice.reportAlive();
      }
      return { fault };
    },
    "x-conformance/counters": async (_params, ctx) => {
      server.authenticate(ctx);
      return { counter: sim.counter, pulses: sim.pulses, fifo_reads: sim.fifoReads, stops: sim.stops, log: sim.log.map((e) => [...e]) };
    },
  });
  return { server, sim };
}

const COUNT_MAX = 2_000_000_000;

function axis(srv: DeviceServer, sim: Simulator): Device {
  const dev = srv.device("axis-1", {
    name: "Conformance axis", capabilities: ["bhms.axis.linear"], tags: ["conformance"], resources: ["axis-1/motion", "axis-1/clamp"],
    description: "Deterministic simulated linear axis with device-side command counters.",
    identity: { manufacturer: "BHMS", model: "conformance-axis", firmwareVersion: "1" },
  });
  dev.reportAlive();
  dev.liveness(() => true);

  dev.property("position", { unit: "mm", evidence: "measured", maxRateHz: 50, description: "Encoder position." },
    () => sensorReading(sim, Math.round((sim.position + sim.encoderOffset) * 1e6) / 1e6));
  dev.property("counter", { schema: int("1", { minimum: 0, maximum: COUNT_MAX }), evidence: "reported", description: "Physical commands executed by the device." }, () => sim.counter);
  dev.property("temperature", { unit: "Cel", evidence: "measured", validityMs: 1000, description: "Housing temperature; can be made stale with the sensor_stale fault." }, () => sensorReading(sim, 21.5));
  dev.property("fifo", {
    schema: int("1", { minimum: 0, maximum: COUNT_MAX }), evidence: "reported", readEffect: "transaction", requiresLease: true, resources: ["axis-1/motion"],
    description: "Pops one value from the device FIFO (a device transaction).",
  }, () => { sim.fifoReads += 1; return sim.fifoReads; });

  dev.action("move_to", {
    description: "Move to an absolute position (20 ms).", effect: "reversible", idempotency: "absolute", completionEvidence: "measured", verifiedBy: ["position"],
    cancel: "supported", maxDurationMs: 5000, typicalDurationMs: 20, resources: ["axis-1/motion"],
    input: { position: range(0, 200, "mm", { step: 0.1 }) }, output: { position: "mm" },
  }, async (ctx: ActionContext, args) => {
    const position = args.position as number;
    sim.begin(ctx.operationId);
    if (await ctx.waitCancelled(20)) throw new Canceled({ effect: "unverified", detail: "stopped before reaching the target" });
    sim.position = position;
    const measured = await ctx.verify("position", (v) => Math.abs((v as number) - position) <= 0.05);
    return sim.end(ctx.operationId, { position: measured ?? position }, ctx.cancelled);
  });

  dev.action("pulse", {
    description: "Add count pulses (1 ms).", effect: "reversible", idempotency: "relative", maxDurationMs: 1000, resources: ["axis-1/motion"],
    input: { count: range(1, 100, "1", { integer: true }) }, output: { pulses: int("1", { minimum: 0, maximum: COUNT_MAX }) },
  }, async (ctx, args) => {
    sim.begin(ctx.operationId);
    await sleep(1);
    sim.pulses += args.count as number;
    return sim.end(ctx.operationId, { pulses: sim.pulses }, ctx.cancelled);
  });

  dev.action("slow_move", {
    description: "Move slowly for duration_ms; honours cancellation within 5 ms.", effect: "reversible", idempotency: "relative", cancel: "supported", maxDurationMs: 61_000,
    resources: ["axis-1/motion"], input: { duration_ms: range(1, 60_000, "ms", { integer: true, default: 1000 }) },
  }, async (ctx, args) => {
    sim.begin(ctx.operationId);
    if (await ctx.waitCancelled(args.duration_ms as number)) throw new Canceled({ effect: "unverified", detail: `canceled (${ctx.cancelReason})` });
    await sim.end(ctx.operationId, {}, ctx.cancelled);
    return undefined;
  });

  dev.action("clamp", {
    description: "Clamp with a force for 50 ms (needs a lease on axis-1/clamp).", effect: "reversible", idempotency: "absolute", requiresLease: true, onLeaseLoss: "cancel",
    cancel: "supported", maxDurationMs: 10_000, resources: ["axis-1/clamp"], input: { force: range(0, 100, "%") },
  }, async (ctx) => {
    sim.begin(ctx.operationId);
    if (await ctx.waitCancelled(50)) throw new Canceled({ effect: "unverified", detail: `released (${ctx.cancelReason})` });
    await sim.end(ctx.operationId, {}, ctx.cancelled);
    return undefined;
  });

  dev.action("fault", {
    description: "Always fails with a device fault after acting.", effect: "irreversible", idempotency: "relative", maxDurationMs: 1000, resources: ["axis-1/motion"],
  }, async (ctx) => {
    sim.begin(ctx.operationId);
    throw new DeviceFault("the conformance device reports a fault", { partial: "counter incremented" });
  });

  dev.onStop({ evidence: "reported", maxDurationMs: 100 }, async () => {
    sim.stops += 1;
    sim.halt.set();
  });

  dev.reconcile(async (op): Promise<Reconciled> => {
    const id = op.operationId as string;
    const entries = new Set(sim.log.filter(([i]) => i === id).map(([, s]) => s));
    if (entries.has("done")) return { state: "completed", evidence: "device command log: done", result: sim.results.get(id) ?? {} };
    if (entries.has("start")) {
      return { state: "failed", evidence: "device command log: started, not finished", message: "interrupted; partial effect possible", mayHaveActed: true };
    }
    return { state: "failed", evidence: "device command log has no record", effect: "none", message: "the command never reached the device", mayHaveActed: false };
  });
  return dev;
}

function pump(srv: DeviceServer, sim: Simulator): Device {
  const dev = srv.device("pump-1", {
    name: "Conformance pump", capabilities: ["bhms.liquid.dispense"], tags: ["conformance"], resources: ["pump-1/plunger"],
    description: "Simulated syringe pump with a pressure precondition.",
  });
  dev.reportAlive();
  dev.property("pressure", { unit: "kPa", evidence: "measured", maxRateHz: 50, description: "Line pressure." }, () => sensorReading(sim, 101.3));
  dev.property("dispensed_volume", { unit: "uL", evidence: "measured", description: "Volume dispensed by the last dispense." }, () => sim.volume);
  dev.action("dispense", {
    description: "Dispense a volume (10 ms).", effect: "irreversible", idempotency: "relative", requiresLease: true, requiresFresh: { pressure: 1000 },
    completionEvidence: "measured", verifiedBy: ["dispensed_volume"], cancel: "supported", maxDurationMs: 60_000,
    input: { volume: range(1, 1000, "uL", { step: 0.1 }) }, output: { dispensed: "uL" },
  }, async (ctx, args) => {
    const volume = args.volume as number;
    sim.begin(ctx.operationId);
    if (await ctx.waitCancelled(10)) throw new Canceled({ effect: "unverified", detail: "stopped early" });
    sim.volume = volume;
    const measured = await ctx.verify("dispensed_volume", (v) => Math.abs((v as number) - volume) <= 0.05);
    return sim.end(ctx.operationId, { dispensed: measured ?? volume }, ctx.cancelled);
  });
  return dev;
}

/** Command-line entry point. */
export async function main(argv: string[]): Promise<void> {
  let url: string | undefined;
  let stateDir: string | undefined;
  let memory = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--memory") memory = true;
    else if (a === "--state-dir") stateDir = argv[++i];
    else if (a.startsWith("--state-dir=")) stateDir = a.slice("--state-dir=".length);
    else if (a === "-h" || a === "--help") {
      process.stderr.write("usage: conformanceDevice.js [unix:<path> | ws://127.0.0.1:<port>] [--state-dir DIR] [--memory]\n");
      return;
    } else if (!a.startsWith("-") && url === undefined) url = a;
    else throw new RangeError(`unexpected argument ${a}`);
  }
  const { server } = build({ stateDir, memory });
  const address = await server.run(url);
  if (address !== undefined) {
    process.stderr.write(`conformance-device listening on ${address}\n`);
    const stop = (): void => { void server.close().then(() => process.exit(0)); };
    process.on("SIGINT", stop);
    process.on("SIGTERM", stop);
  } else {
    process.exit(0);
  }
}

import { fileURLToPath } from "node:url";
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main(process.argv.slice(2)).catch((e: unknown) => {
    process.stderr.write(`${e instanceof Error ? e.stack ?? e.message : String(e)}\n`);
    process.exit(1);
  });
}
