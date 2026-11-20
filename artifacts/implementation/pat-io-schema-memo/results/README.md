# Bounded schema reuse: 45 distinct checks pass, full group still incomplete

The [single-file production change](../schema-reuse.patch) reuses successful
JSON Schema checks for exact bounded bytes and the same private validator.
Every call still parses a detached tree, rejects invalid scalar types and runs
all graph, generation, electrical footprint and lifecycle semantics. Eight LRU
entries bound retained document bytes to 512 KiB plus object overhead. Private
validator replacement invalidates reuse; in-place mutation of those import-time
validators is outside the supported configuration contract. See the
[design](../DESIGN.md) and [source review](../implementation01/source-review.json).

**45 distinct methods pass:** 21 existing topology checks, 11 new schema reuse
regressions, 12 existing group boundary/preflight checks and the actual record
cutoff. The profiler repeats that cutoff and adds no distinct method.
**The complete GPIO group still fails.** PWM remains prepared but unexecuted
pending correction of shared time and storage costs.

| Attempt | Result | Methods | Test seconds | Raw scratch bytes |
|---|---|---:|---:|---:|
| [attempt01-schema44](attempt01-passed44/proof.json) | passed | 44 | 8.313 | 0 |
| [attempt02-record-cutoff](attempt02-passed-cutoff/proof.json) | passed | 1 | 6.338 | 1492414 |
| [attempt03-gpio](attempt03-failed-gpio-deadline/proof.json) | failed | 1 | 60.205 | 16324409 |
| [attempt04-profile-cutoff](attempt04-profiled-cutoff/proof.json) | passed | 1 | 14.417 | 1492414 |

The full GPIO group completes **25 of 30 cases**, versus 12 in the
[preceding source](../../pat-io-group-worker/results/README.md), before the
unchanged 60-second deadline. This is a comparison of retained attempts, not a
controlled benchmark. The active 26th case is `permission_after_completion`;
its runtime state has not been created. All 21 earlier runtime states remain.
The [deadline diagnosis](../DEADLINE-DIAGNOSIS.json) records 2,891 charged records,
7,438,380 charged producer bytes, 8,941,568 observed state bytes, 20 completed-case
child operations and 78 charged scheduler ticks. The reserved terminal receipt
survives; all qualification/attestation/full-coverage flags remain false.
The [read-only state audit](attempt03-failed-gpio-deadline/state-audit.json)
observes 14 activations, 6 completed cycles, 8 cancellations and zero claims/owners.
Those endpoint observations do not validate complete histories or unrun cases.

The actual cutoff still stops at 250 charged records, retains 258 raw files and
two private states, prevents later cases and rejects reuse of the populated
directory. Its 6.338-second uninstrumented test compares with 11.919 seconds in
the prior source; timings are diagnostic, with no performance guarantee.
Both cutoff [state audits](attempt02-passed-cutoff/state-audit.json) preserve the
completed nominal candidate and an unactivated canceled child.

The new [profile](attempt04-profiled-cutoff/attempt/profile.json) takes 14.417
instrumented test seconds versus 26.981 previously. Both perform 285 topology
parses and 494 topology/generation snapshots. Topology cumulative time changes
from 13.672 to 2.014 seconds, snapshot time from 13.953 to 2.088 seconds, and
JSON Schema iter_errors calls from 30,239 to 1,731. Cumulative times overlap and
profiling overhead is material. The [comparison](../PROFILE-ANALYSIS.json)
identifies remaining canonical serialization and repeated complete matrix
reconstruction; it does not justify bypassing runtime authority or semantics.

Retained raw GPIO evidence occupies 16,324,409 bytes, near the unchanged 16 MiB
harness ceiling. The read-only [storage analysis](../STORAGE-ANALYSIS.json)
finds 8,941,568 allocated SQLite bytes, 1,720,199 payload bytes and 7,123,390 unused
bytes within pages. The next storage investigation is a fixed smaller-page
profile for freshly created stores, with recovery/durability validation. No
database was rewritten, vacuumed, compressed or deleted. Complete group storage
cannot be predicted as compliant from this partial attempt; no ceiling is raised.

All four attempts keep 218 project inputs, 221 frozen entries, 6 harness inputs and
159 external pins stable. All actual origin hashes match: 724 records for the
pure selection, 722 for ordinary group attempts and 727 for the profiler;
222/221/223 bytecode reads respectively are refused. No prohibited attempt
occurs. Complete attempt copies and original scratch roots remain, and database
hashes stay unchanged during read-only inspection. Source/compiler/driver
identity is stable within each attempt; prior source evidence is not relabeled
as the new deployment. Primary-agent review was used; helpers remain usage-limited.

Live HMS, the adjacent Harness and physical devices remain unchanged. Independent
current-group outcomes, trusted configuration/run association, actual aggregate
storage enforcement, persistent supervision and public qualification remain
unfinished. Persistent Arduino applications, learning/reuse and physical
device/driver/intelligence-hub control remain part of the full goal. See
[qualification work](../../pat-io-outcome-history/NEXT-QUALIFICATION.md).
