# Shared current-group capture: bounded failures retained

The coordinator now attempts one exact current-candidate matrix, with evidence,
configuration, manifests, admissions, scheduler ticks and deadline checks sharing
one ledger. **The complete group has not passed.** The current corrected source
has 13 distinct passing methods: 12 pure/preflight methods and one actual
record-cutoff method. Profiling repeats that cutoff method; it is not an additional
distinct passing case. The full GPIO method fails at the original group deadline.
PWM remains unexecuted pending correction of the shared performance cost.

| Attempt | Result | Methods | Test seconds | Raw scratch bytes |
|---|---|---:|---:|---:|
| [attempt01-group11](attempt01-passed11/proof.json) | passed | 11 | 12.308 | 0 |
| [attempt02-gpio](attempt02-failed-gpio-acquired/proof.json) | failed | 1 | 8.071 | 845640 |
| [attempt03-group12](attempt03-passed12/proof.json) | passed | 12 | 9.818 | 0 |
| [attempt04-gpio](attempt04-failed-gpio-deadline/proof.json) | failed | 1 | 62.808 | 6879179 |
| [attempt05-record-cutoff](attempt05-passed-cutoff/proof.json) | passed | 1 | 11.919 | 1492414 |
| [attempt06-profile-cutoff](attempt06-profiled-cutoff/proof.json) | passed | 1 | 26.981 | 1492414 |

The [first full-group failure](attempt02-failed-gpio-acquired/proof.json) completed
the candidate and extra-parameter refusal, then found a real coordinator error:
the planner represents nonapplicability with no error code, while compilation
returns `PAT_NOT_APPLICABLE`. [Source02](../implementation02/README.md) maps that
exact distinction, retains actual compiler codes separately from static outcomes,
and adds a pure check of all four negative cases. The planner, compiler, runtime,
fault schedules and budget rules remain unchanged. The [diagnosis](../DIAGNOSIS.json)
and exact [two-file correction](../negative-result-correction.patch) are retained.

The corrected full GPIO attempt completes **12 of 30 cases** before the original
60-second group boundary refuses further capture. Its active case is
`latest_start_before`, index 12. The [deadline diagnosis](../DEADLINE-DIAGNOSIS.json)
retains 1,160 charged records, 3,108,990 charged producer bytes, eight completed-case
operations and 29 charged scheduler ticks. Actual scratch is 6,879,179 bytes,
including the unfinished case's state. The ledger's after-close state accounting
does not include that unfinished case; it is not a hard filesystem quota.
The final bounded failure receipt survives. No remaining case is run and no
qualified result is returned. The 62.808-second test includes setup outside the
group and terminal work; checked group boundaries are not hard preemption.

The actual reduced-record test stops at **250 charged records**, retaining 258
scratch files including two private runtime states. Later cases do not start and
the populated group directory cannot be reused. The reserved terminal document
is included in the record ceiling and charged conservatively at 65,536 bytes.
Read-only [deadline-state inspection](attempt04-failed-gpio-deadline/state-audit.json)
finds six activations, three completed cycles, three cancellations and no retained
claims/board owners across nine created states; the unfinished case has no child
or effect. The [cutoff-state inspection](attempt05-passed-cutoff/state-audit.json)
finds the completed candidate and a canceled unactivated child. These endpoint
observations do not replace complete-history validation or prove the remaining
matrix cases.

The [diagnostic profile](attempt06-profiled-cutoff/attempt/profile.json) covers the
same cutoff test after imports. Its 26.981 seconds include profiler overhead;
the ordinary test took 11.919 seconds. Repeated topology parsing accounts for
285 calls and 13.672 cumulative seconds in this sampled path. JSON Schema and
canonical serialization also appear prominently; cumulative timings overlap.
The [analysis](../PROFILE-ANALYSIS.json) directs the next change toward bounded
reuse of exactly validated topology/schema bytes and current matrix setup, while
preserving strict input types, detached outputs, validation and identity checks.
No optimization has yet been implemented or verified.

Every executed attempt preserves 217 project files, 220 frozen entries, six active
harness inputs and 159 selected external pins. Ordinary attempts have 722 matched
origin records and 221 refused bytecode reads; the profiler has 727/223. No
prohibited attempt occurs. Complete attempt copies and original raw scratch roots
are retained. Source/compiler/driver identities are stable within every attempt;
source02's worker/driver identity changes from source01 and is never presented as
the old deployment. Read-only state inspection verifies database hashes unchanged.

The first acquisition of the single-test failure encountered a plural-only log
regex. Its [failed acquisition record](attempt02-failed-gpio/acquisition-error.json)
remains. The one-line [acquirer correction](../acquire02.patch) accepts `test` or
`tests` for the exact observed count and acquires into a fresh destination.
No test or producer is restarted for acquisition. Prepared source01 PWM/cutoff
and source02 PWM harnesses remain unexecuted.

All original group and harness ceilings remain. Live HMS, physical devices,
drivers, hub providers and the adjacent Harness are untouched. Primary-agent
review was used because existing helpers remain usage-limited. Complete group
execution, independent outcome composition, current configuration/run association,
actual aggregate filesystem quotas, persistent service and public qualification
remain unfinished. See [design](../DESIGN.md) and
[qualification work](../../pat-io-outcome-history/NEXT-QUALIFICATION.md).
