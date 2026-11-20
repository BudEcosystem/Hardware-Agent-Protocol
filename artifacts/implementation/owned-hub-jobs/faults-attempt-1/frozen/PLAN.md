# Reviewed execution slice

Candidate source is prepared; no host-job control has been executed. The root must review final source and this runner before execution. `helper-check01` is the separately completed, preserved original signal-query binding control.

Run each fixed group in a new attempt only, stopping after any failure. The runner preserves frozen sources, hashes, stdout/stderr, process observations and result receipts. It verifies the exact prior 244-file receipt/hash set before and after each group and records interpreter path/running-byte identity stability. Those observations do not rerun the prior866tests. SIGTERM raises into owned cleanup; SIGINT/SIGTERM remain blocked during cleanup and receipt finalization, then restore only after retained ownership has been handled and recorded. A retry uses a new attempt name; prior attempts are never overwritten.

```
python3 -I -S -B run_controls.py structural structural-attempt-1
python3 -I -S -B run_controls.py live live-attempt-1
python3 -I -S -B run_controls.py faults faults-attempt-1
```

`structural` checks exact request/result types, sealed memfd mutation refusal, immutable original keys/terminal receipts, strict receipt counters/reasons and cross-slot successor refusal. `live` checks real fixed CPU work, exact result validation, replay/conflict, active capacity, simulated source-read drift, owner-thread refusal, cancellation before/after release, a delayed durable release-intent boundary whose expired budget withholds the gate byte, seven malformed/wrong outputs, output overflow and a retained descendant writer while its leader waits. `faults` injects exceptions at ten durable/ownership boundaries, then deliberately settles original handles before reopening; it also checks failed pidfd acquisition, explicit SIGCHLD-ignore refusal and pending SIGINT at owned-child registration and post-reap publication.

These checkpoint exceptions are orderly failure controls, not killed-owner crash qualification. The current run slice does not execute the installed early-leader-exit or bootstrap-failure modes, force post-release wall/CPU exhaustion, exhaust sixteen keys, qualify real storage loss/power failure, or prove complete descendant enumeration. The delayed-gate control covers only pre-release wall-budget expiration, preserving conservative `mayHaveActed=true` after committed release intent. Sealing has direct negative mutation controls; the normal worker also verifies both inherited sealed images. No test mode is caller-selectable.

The outer runner admits one control process with per-process CPU30s, address512MiB, file1MiB, open-FD128 and no-core limits. Group wall limits are15/30/40s, followed on interruption/timeout by TERM with8s for the control's exception/finally cleanup, then KILL if needed and3s for owned exit observation. The fixed control handles TERM once and settles its retained provider handles through finally blocks. The provider jobs have their own stricter typed per-process limits. These are not aggregate reservations. Polling and host scheduling can delay observations; kernel signals can also fail to make a process promptly waitable.

The control process launches jobs in separate sessions. Killing the outer control group cannot establish their containment. Normal controls retain and settle each real provider handle; on abnormal controller death/timeout the runner reports bounded observed descendants and any remaining live observations, refuses a passing result, and stops. It never signals job PIDs recovered from files or observation alone. Root must treat such a failure as unresolved ownership, not permission to continue new runs. Actual owner-death containment and crash recovery need a later explicitly owned harness/profile.

Public sources, simulation mount, schemas, public tests and previous sealed packets remain unchanged. A successful candidate run would demonstrate this installed CPU process component only; it would not qualify public resource admission, storage durability, GPU/inference readiness, device I/O/drivers or learned PAT deployment.
