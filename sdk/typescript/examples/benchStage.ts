// A complete device server in about fifteen lines: the TypeScript twin of sdk/python/examples/bench_stage.py.
import { DeviceServer, range } from "../src/index.js";

const srv = new DeviceServer("bench-stage");
const stage = srv.device("stage-z", { capabilities: ["bhms.axis.linear"], resources: ["stage-z"] });
const z = { um: 0 }; // a simulated stage: replace with your driver, and use evidence "measured" with a real encoder

stage.property("position", { unit: "um", evidence: "simulated" }, () => z.um);

stage.action("move_to", {
  effect: "reversible", idempotency: "absolute", requiresLease: false, completionEvidence: "reported", maxDurationMs: 5000,
  input: { target: range(0, 200, "um") }, output: { position: "um" },
}, async (ctx, { target }) => {
  z.um = target as number;
  await ctx.running();
  return { position: z.um };
});

await srv.run(process.argv[2]); // stdio by default; "unix:/tmp/stage.sock", "ws://127.0.0.1:8765"
