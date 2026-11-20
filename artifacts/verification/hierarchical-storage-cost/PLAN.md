# Hierarchical storage cost diagnostic

Stage 92, 2026-11-09. The previous turn is verified progress: the isolated
hierarchy passes nine semantic scopes / 96 checks, and the whole-workflow attempt
establishes a failed 180-second wall gate. Preserve its 212-file seal and original
image. Do not rerun, recover, repair, shrink or extend that experiment.

Use the exact stage-91 source and native binary in two fresh eight-chunk 128 MiB
images. Both runs perform the same deterministic diagnostic workload: twenty
directories, forty named files with sizes cycling through 0, 128, 4,096, 8,193 and
65,536 bytes, synchronous publication, full warm readback and complete cold
readback. These explicitly synthetic small-file shapes investigate cost. They do
not replace the complete 4,270-file / 35,508,922-byte acceptance workload and do
not cover its 15 MiB body or late namespace occupancy. No dataset reduction is
claimed as passing the workload gate.

Run `coarse` once with timing only at logical operation boundaries; run `nested`
once with additional wrappers around the original native call, provider methods,
mount check and selected original OS calls. Call each original implementation
exactly once, retaining all ownership checks, allocated backing, positional I/O,
fsyncs, limits and error behavior. Do not use RAM-backed I/O, a cached mount
inventory, disabled verification, altered filesystem geometry or a new binary.
The same persistent identity and deterministic operations allow comparison of
logical bodies, callback counts and complete final backing bytes.

Each process has 60 seconds wall, 40 seconds CPU, 512 MiB address space, 128 FDs
and 16 MiB per-file limits. The two images total 256 MiB; the entire new stage
stays below 1 GiB. Freeze the source, workload, wrappers, harness and binary before
execution. Stop on failure and preserve state. No unchanged diagnostic retry.

Measure wall and process CPU durations with nested spans. Report inclusive and
exclusive values separately; never add overlapping inclusive values. Timing
overhead is charged partly to callers, so the trace is an intrusive attribution
screen, not a deployment benchmark or a speedup. Retain per-operation callback
deltas and the phase totals. Treat a mismatch in body, callback counts or final
image bytes as an instrumentation failure. Any redesign must follow observed
evidence and preserve the original checks and complete acceptance gate.

Verify receipts, source identities, both original images, all public runtime
inputs and the prior seal without adapter recovery. This stage changes no public
runtime or physical provider. The original prompt/PAT, device/driver/hub, MCU,
microscope, Harness, full-source research and domain goal remains active.
