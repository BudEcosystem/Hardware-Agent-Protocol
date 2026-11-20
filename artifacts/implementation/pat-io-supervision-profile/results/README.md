# Supervised I/O profiling evidence

The parent-instrumented original PWM test passes: all30cases complete, independent
inspection succeeds, and exact replay before/after reopen and same-key conflict
checks pass. Source and request semantics are unchanged. It takes157.708test seconds
(163.036s including harness collection), within the original180s outer bound.
The supervisor/group still use60s. Parent timing includes61.963s in collection,
which includes archival after producer settlement, and64.801s in independent
history inspection. These cumulative values overlap with their callees.

| Diagnostic | Test result | Raw files / bytes | Parent SQL opens |
|---|---|---:|---:|
| [Parent profile](attempt01-profiled-pwm/README.md) | 1 pass |4269 /19551533|2|
| [Worker profile](attempt02-profiled-worker-failed/README.md) | 1 failure, original deadline |1198 /8004907|1|

The [parent profile](attempt01-profiled-pwm/attempt/profile.json) records1767tree
scans (24.396 cumulative profiled seconds), about2.89million DirEntry.stat calls,
and86089canonical encodings (61.842 cumulative profiled seconds across the whole
test). Parent CPU is121.061s; reaped child CPU is35.150s. The profile is not a
controlled benchmark or proof of the cause of earlier deadline failures.
Read-only audits verify the exact256-file image,3936output files/14,821,081bytes,
26states/53databases,21activations,11completions,10cancellations and zero observed
claims/owners. The original uninstrumented PWM failure remains authoritative
negative evidence for its own attempt; this pass does not repair or replace it.

The separate [worker profile](attempt02-profiled-worker-failed/attempt/scratch/test_complete_owned_pwm_group_retains_inputs_before_launch_and_replays/supervisor/d7da5918c79744269b2c6273b79e9580/worker-profile.json)
changes only the worker entry to profile run_io_group. The parent is uninstrumented.
A bounded receipt is attempted on SIGTERM, then the worker raises SIGTERM to itself
with default disposition; the original parent stop/kill grace remains. The actual
archive recordsexit-15, SUPERVISOR_DEADLINE, no group return, false transport/semantic
qualification and unknown unresolved effects. The11,841-byte profile is associated
with the exact private image, source identity, retained input and physical attempt.
All238other source files and the original test remain unchanged.

That worker profile records53.451s wall/42.847s CPU over907functions before
interruption. It observes12739canonical encodings (26.975 cumulative seconds),
71installation normalizations (6.054s),10runtime openings (21.028s), and452binding
proof calculations (7.574s). These are overlapping instrumented times, not sums.
It retains11case directories,10manifests, six complete state pairs and an incomplete
authority-only state for case10. Observed complete pairs have4activations,
2completions and2cancellations; no aggregate effect-resolution claim follows.
All14databases retain their original bytes. No old mutation is retried or repaired.

Both runs keep the original selected239project/242frozen inputs,6active harness
files and159external pins stable. Their837/831 actual origin inventories are
recorded precisely in the proofs; system libraries are not a complete attested
runtime closure. The original60s/180s deadlines,32-case,20MiBderived-output,
64MiBattempt,256MiBroot and collection limits remain. No physical device, MCU,
inference, acquired controller or live service executes.

[Next decision](../NEXT.md): investigate bounded reuse of pure installation
normalization with exact original-type/byte checks, current source revalidation,
dependency invalidation and detached results. No authority state or validation
boundary may be skipped. The memo is not implemented here; scanning is not slowed
and the general JCS encoder is not changed. The original PWM/archive-commit
nominal failures remain unresolved, and the full end-to-end goal remains active.
