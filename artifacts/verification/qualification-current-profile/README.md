# Current qualification worker profile

**The diagnostic is audited; actual qualification remains incomplete.** The
complete thirty-case matrix was requested under the original 60-second worker
and 180-second parent bounds. The worker stopped at its deadline with 21 case
manifests and case 21 incomplete. No complete return, evidence publication,
catalog promotion or PAT application exists. Interrupted worker effects remain
unresolved.

All 83 core HMS modules are byte-identical to the namespace candidate. Only the
fixed worker entry adds the previously reviewed bounded profiler; the function's
AST is unchanged. The [source review](implementation01/source-review.json) also
records the expected test-identity literal updates. The diagnostic handler cannot
enter production. The public runtime remains at its previously verified 861-test
source, and the [ASCII encoder experiment](../pat-ascii-canonical-evaluation/README.md)
is not adopted.

The profile covers 57.355184 seconds of instrumented wall time and 41.799391
seconds of process CPU time, with 951 function entries. The parent completes in
81.177 seconds. These are observations of a partial diagnostic, not qualified
execution times or proof of the earlier timeout's cause.

| Observed function | Calls | Cumulative elapsed seconds | Self elapsed seconds |
|---|---:|---:|---:|
| SQLite `execute` | 95,038 | 11.184359 | 11.184359 |
| Explicit `fsync` | 2,398 | 7.794022 | 7.794022 |
| `check_tree` | 28,695 | 10.635110 | 6.976787 |
| `canonical` | 24,065 | 17.801332 | 0.132873 |
| Legacy table capture | 7,663 | 6.818527 | 0.267112 |
| Configuration table capture | 3,960 | 4.784702 | 0.225282 |
| Fresh driver implementation digest | 167 | 5.746167 | 0.116660 |

Cumulative times overlap and must not be added. Function timings include profiler
overhead and, for blocking calls, waiting. They are not per-function CPU counters.
The records support inspecting repeated metadata reads and validation work; they
do not justify dropping durability, fresh authority checks or qualification cases.

The read-only [audit](RESULTS.json) verifies **2,793 retained files / 14,534,626
bytes**, 267 producer-image files and four unchanged parent databases under
**41 original owner/writer locks**. It opens zero worker case databases and joins
the sole launch, writer lease and supervisor record to the original request.
Source authority retains one reservation/handoff and zero imported evidence or
application operations; its board counters remain zero. These parent facts do
not settle interrupted case effects.

Two preparation failures remain retained. The first acquired an old stage path
and was rejected by the source pin. The corrected harness was initially invoked
with launcher isolation that hid its approved dependency directory. Both stopped
before any child. The corrected normal launcher acquired the exact reviewed
dependency metadata and launched the one diagnostic worker; child and worker
isolation flags remained unchanged. The [invocation correction](invocation-correction.json)
and [release](release02.json) preserve that distinction.

[Original failed diagnostic](harness02/attempts/attempt02-profile/result.json),
[scope](harness02/SCOPE.md), [plan](PLAN.md), [next work](NEXT.md).
No physical endpoint, MCU, inference, network or live service ran. The full HMS
goal remains active and incomplete.
