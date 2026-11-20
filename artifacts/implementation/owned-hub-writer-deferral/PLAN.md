# Source-reviewed bounded execution plan

No candidate execution is authorized until root reviews these sources, descriptor inheritance, fixture identity, exact guardian joins and outer cleanup. The existing sealed packets and public files remain unchanged.

Run once after review:

```
python3 -I -S -B run_writer_deferral.py
```

The new `writer-deferral-attempt01` preserves exact source/helper copies, intent, stdout/stderr, control results and per-case checkpoint/ready/recovery records. It must pass all three deterministic writer-lifetime cases: release, EOF and guardian stop. Each case must positively observe the same held lease before and after provider-owner death, defer reconciliation while held, then reap all three family members and observe the free matching lease before final unknown reconciliation. Expected total: nine individually reaped family members plus the outer control process. Root should stop at the first failure and preserve the entire attempt.

There is no timing-only .4-second hold. Predicate waits are bounded observations; the writer remains held by an explicit pipe until the guardian acts. The parent-owned gate writer is closed from every descendant before provider fork/exec. The ready record proves association and calculation, never signal authority or durable completion. Actual kernel-child registration precedes every adopted-writer signal. No stored job PID or process group grants authority.

The exact sealed Guardian is reused in the outer runner. It owns the control and adopts its separate-session descendants if cleanup is needed. The control has 30 observed wall seconds, 30 CPU seconds, 512 MiB address space, 1 MiB per file and 64 FDs. Its fixed owners use the Guardian's existing 5-CPU-second/256-MiB profile; worker limits remain the typed per-process job ceilings. On interruption/timeout, the outer guardian requests TERM cleanup for at most ten seconds, then settles kernel-owned/adopted children within the existing eight-second observed bound. INT/TERM remain guarded through cleanup and final receipt writing. Guardian survival and kernel responsiveness remain assumptions; no aggregate or hard wall guarantee is added.

Before/after the run, verify both complete sealed parent packets, all original baseline copies, candidate change pins, interpreter identity and the 244 public baseline hashes. Do not rerun or reinterpret the previous 866 tests or the previous no-deferral owner-death observations. No service, device, network, GPU or physical-driver changes occur.
