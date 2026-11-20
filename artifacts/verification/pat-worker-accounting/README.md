# Whole-worker resource diagnostic

The diagnostic records **36.580244 child CPU seconds** and **18.454471 parent CPU
seconds** during the original worker's approximately **60.087-second** interval.
All **15 pure observer controls pass**. The actual original integration remains
**failed at its unchanged 60-second deadline**, with 26 case directories and 25
retained manifests. `permission_after_completion` is incomplete. Import, catalog
activation and a source PAT application were not reached; interrupted worker
effects remain unknown.

The [results](RESULTS.json) and [actual accounting receipt](harness02/attempts/attempt01-accounting/worker-accounting.json)
separate measurement from qualification. All 288 project files, the producer
image and original test are unchanged from the isolated proof-build candidate.
Only the [harness](harness02/README.md) adds accounting around its existing launch
and poll/wait calls. The public runtime is unchanged.

| Observation during launch-to-reap interval | Parent | Waited child aggregate |
|---|---:|---:|
| User CPU seconds | 11.714712 | 34.238430 |
| System CPU seconds | 6.739759 | 2.341814 |
| Filesystem input operations | 0 | 744 |
| Filesystem output operations | 264 | 103,440 |
| Voluntary context switches | 1,935 | 13,231 |
| Involuntary context switches | 4,575 | 5,919 |

These are partial-run measurements. Filesystem operations are not bytes or
waiting durations; switches do not quantify blocked time. Peak child RSS is
retained as 66,996 KiB, without subtraction or summation. All three global
pressure files were available, but they do not attribute pressure to this worker.
Snapshot reads took 0.339–0.752 ms each; that does not measure all observer or
pre-existing harness overhead. No deployment timing guarantee follows.

The separate read-only [audit](audit.py) verifies **3,406 retained files**
totalling **16,669,062 bytes**, all 262 producer-image files, and four unchanged
source databases under **49 original owner/writer locks**. It opens no interrupted
case database. The sole permitted launch is associated with the original attempt,
ledger PID, input and inherited writer-lease identity. Child usage is unchanged
outside the observed launch-to-reap interval. All actual source origins match.
Review was performed by the primary agent, not an independent second reviewer.

The worker attempt is `c00ffb566da8416aa10f99a8be4033c4`; its raw state remains at
`/tmp/hms-worker-accounting-5fz783p1` at audit time. Retained copies survive separately.
The original test ran for 84.382 seconds and the outer scope for 92.742 seconds,
within the original 180-second parent bound. Source authority has one original
handoff, zero import intents/publications and zero source operations/claims; the
installed vault is empty. These source facts do not settle interrupted case effects.

[Design](DESIGN.md), [pure controls](controls.json), [preparation record](PREPARATION.md)
and [primary-source research](../../../research/host-contract/worker-accounting/README.md)
retain the measurement contract and limitations. [Next work](NEXT.md) investigates
parent monitoring cost before another optimization or actual integration scope.
