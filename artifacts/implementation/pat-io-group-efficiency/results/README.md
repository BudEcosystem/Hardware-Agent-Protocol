# Full GPIO capture passes; PWM remains incomplete

The [candidate](../implementation01/README.md) explicitly associates each group
case with the already validated five input documents and uses a fixed compact
layout for fresh synthetic stores. **95 distinct methods pass:** 87 pure checks,
six actual storage checks, the record cutoff and full GPIO group. **PWM fails**
at the original deadline after 28 of 30 cases. A separate diagnostic profile
repeats that failed method; it is not another distinct test or a passing result.

| Attempt | Result | Methods | Test seconds | Raw scratch bytes |
|---|---|---:|---:|---:|
| [attempt01-pure87](attempt01-passed87/proof.json) | passed | 87 | 28.139 | 0 |
| [attempt02-storage6](attempt02-passed-storage6/proof.json) | passed | 6 | 5.417 | 1528832 |
| [attempt03-record-cutoff](attempt03-passed-cutoff/proof.json) | passed | 1 | 4.74 | 977425 |
| [attempt04-gpio](attempt04-passed-gpio/proof.json) | passed | 1 | 58.305 | 14606609 |
| [attempt05-pwm](attempt05-failed-pwm/proof.json) | failed | 1 | 60.295 | 13125092 |
| [attempt06-profile-pwm](attempt06-profiled-pwm-failure/proof.json) | failed | 1 | 61.57 | 6617870 |

The full GPIO test verifies all 30 exact case IDs and all 25 fixed challenges,
rehashes every manifest and both evidence streams, independently sums accounting,
and checks 52 retained SQLite headers. It observes 28 actual child operations,
44 reserved admissions and 99 scheduler ticks. Charged evidence is 3,832 records
and 10,149,988 producer bytes; 4,510,720 closed state bytes bring derived accounting
to 14,660,708 bytes, including the conservative 65,536-byte terminal reservation.
Actual retained scratch is 14,606,609 bytes across 3,936 files. All original
deadlines and byte/record/case/tick ceilings remain. The 58.305-second test leaves
little observed timing margin and is not a performance guarantee.

The [GPIO state audit](attempt04-passed-gpio/state-audit.json) observes 21
activations, 11 completed cycles, 10 cancellations and zero claims/owners across 26
runtime states. The final resource challenge has four completed actors and no
retained owner. The [storage audit](attempt04-passed-gpio/storage-audit.json)
finds 52 intact 1024-byte-page databases, with 2,176,346 payload bytes and 2,195,539
unused page bytes. Endpoint observations and exact capture accounting do not
replace independent complete-history outcome checking. Every group qualification,
attestation, physical-measurement and hard-quota flag remains false.

PWM completes 28 cases before the original 60-second group deadline. The active
`binding_pending` case has created state but no child/effect; the final shared
resource case is unrun. Its 13,125,092 raw bytes and bounded failure receipt remain.
The [state audit](attempt05-failed-pwm/state-audit.json) observes 16 activations,
seven completions, nine cancellations and no claims/owners across 25 states.
No case is skipped and no failing result is converted to success. See the exact
[group accounting and diagnoses](../GROUP-ANALYSIS.json).

The actual cutoff still stops at 250 charged records and preserves 258 raw files,
including two runtime states. The unchanged logical history now occupies 977,425
bytes. The six layout tests verify actual page sizes, DELETE/EXTRA settings,
foreign-key enforcement, integrity, rollback and owner exclusion. They exercise
pending recovery and same-key replay after reopen, reject mismatched expected
layouts without rewriting database bytes, and show the default opener preserves
an existing compact layout. These are settings/rollback/reopen checks, not
physical power-loss durability or filesystem-quota attestation.

The 87 pure methods include the preceding 44 checks, 30 combined-matrix checks,
twelve new validated-input checks and one invalid-storage-profile check. Exact
comparison preserves numeric types, bounded detached documents, all five runner
families and standalone full validation. Current source changes 11 inherited
production modules and one existing test file, adds one production and two test
modules, and leaves 206 inherited files byte-identical. See the
[review](../implementation01/source-review.json) and [delta](../implementation.patch).

The [PWM profile](attempt06-profiled-pwm-failure/attempt/profile.json) reaches 16
cases under the same deadline and fails as expected by the ordinary test's
unchanged assertions. Profiling adds overhead. It records 39,452 canonical
encodings taking 31.440 cumulative instrumented seconds; 184 configuration captures
take 20.095 cumulative seconds. Timings overlap. Source review confirms 6,157
configured writer calls serialize a record again in the base writer, even on
reuse. The [analysis](../PROFILE-ANALYSIS.json) directs the next change toward
removing redundant encoding and bounded reuse of exact unchanged table pages,
while retaining current SQL inspection, type/size checks, locks, fsync, every
evidence record/reference and all source/authority checks. No further optimization
is implemented or verified in this stage.

All six attempts retain stable 221 project inputs, 224 frozen entries, six harness
inputs and 159 external pins. All selected actual import hashes match. Pure,
storage, ordinary group and profile runs respectively record 730/726/724/729
origins and refuse 225/223/222/224 bytecode reads; no prohibited attempt occurs.
Source/compiler/driver identities are stable within each attempt. All complete
attempt copies and original raw scratch roots remain. Read-only audits verify
unchanged database bytes. Primary-agent review was used; helpers remain
usage-limited. Live HMS and the adjacent Harness remain unchanged.

Full PWM capture, independent current-group outcomes, trusted configuration/run
association, enforced aggregate storage, durable supervision and public
qualification remain unfinished. Persistent Arduino applications, synthesis and
learning, physical I/O/driver providers and intelligence-hub lifecycle/compute
control remain part of the complete goal. See [design](../DESIGN.md) and
[remaining qualification work](../../pat-io-outcome-history/NEXT-QUALIFICATION.md).
