# Observed history-cost diagnostic

The root actually ran the fixed attempt01 and its independently reviewed
retained-data auditor; both completed with terminal exit0. Frozen execution
inputs, the attempt and original audit bytes remain unchanged.

[Attempt01](history-cost-attempt01/RESULTS.json) passed one fixed 32-loop case with
143 checks: 142 case checks plus one invocation check. The observed control wall
time was 9.642591362 seconds; final elapsed, including cleanup and rehashing, was
10.730299100 seconds. The outer control's retained CPU observation was 6.658848
seconds. One native peer and one outer control were cleanly reaped; both owner
receipts report empty/closed state, no pending interrupts, no cleanup errors and
no unexpected children. The control stayed within the original 30-second limit.

The retained 249,856-byte DB contains 32 original never-handed-off START records,
all original keys and exactly three occupied shared claims. The accepted OPEN
remains, mutation sequence and activation/ACK prefixes stay zero, and no STOP,
REVOKE or RETIRE was sent. The retained logical charge is 81,471 bytes under the
unchanged 16MiB ceiling. This small prefix is not a full reachable-capacity test.

The recorded validation count is exactly 2,176, matching 4n+6 for each n=0..31.
There are 981 bounded metric rows. The following values include only the 32 loop
phases; setup, final verification and cleanup are excluded from this table.

| Measured method | Loop calls | Exclusive wall seconds |
| --- | ---: | ---: |
| catalog current selection | 64 | 1.928830858 |
| host image context entry | 32 | 0.827209297 |
| current policy/installation check | 128 | 0.809445257 |
| explicit prepared settlement | 32 | 0.452657952 |
| deployment record read | 416 | 0.384699585 |
| mutation record read | 2,176 | 0.304479336 |
| mutation validation outside nested read | 2,176 | 0.106740081 |

Loop wall time was 8.186641095 seconds. Summing only non-held exclusive method
spans gives 5.284797397 seconds; 2.901843698 seconds falls outside those measured
spans. The method spans contain unknown instrumentation overhead and unmeasured
nested work. Context held lifetimes overlap them and are not added. These are
intrusive wall observations, not CPU attribution, a speedup comparison or a
duration prediction for 128 records. Initial candidate imports took 0.217065481
seconds, fixture setup 0.619897804, initial prepare/OPEN/cycle/snapshot 0.493775252;
the true module-to-loop-start interval was 1.345672641 seconds.

All 28 native selectors were retained before and after the loops. Only response
sequence changed, from 6 to 70; dispatch, loss, output, clock, boot, source counters,
generation and standing state were unchanged. The 140 retained raw packets are 70
request/reply pairs: four DESCRIBE, one BIND, one OPEN and 64 read-only STATUS
requests, plus replies. Reserved START transport numbers were never handed off.

The [independent audit](AUDIT.json) passed. Its retained receipt records 61,794
evidence checks; the terminal summary reports 61,795, including the final receipt
size assertion performed after the receipt's check count was captured. The
[auditor source](audit_retained.py) and [audit plan](AUDIT-PLAN.md) join all 309
attempt files, original 299 frozen inputs, 261 exact reused files, 25 provenance
copies, both sealed parents (5,067 indexed files), public244, the original image
and evaluation association, durable records, traces and timing aggregates. Both
observed owned identities were absent at audit time. The audit receipt SHA256 is
`ad43b0a46898e13a0c8d59bb92ed48a31beeb16c07f816d44ad7e1a6fe64ef0e`.

The sealed boundary capacity timeout remains failed. This run changed no
production code and reran no qualifier. Original 20-case/173-check host validation,
13 owner-death cases and 18 passing boundary cases remain their separate evidence;
this packet does not extend their scope. Full 128-record and simultaneous capacity,
the remaining boundary profiles, physical qualification, protected storage and
public deployment eligibility remain open.
