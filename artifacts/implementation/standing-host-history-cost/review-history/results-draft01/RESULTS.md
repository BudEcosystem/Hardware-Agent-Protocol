# Observed history-cost diagnostic

Draft retained observations; the independent auditor is source-reviewed but has
not yet been executed. The root actually ran the fixed attempt01 and observed
terminal0. Frozen execution inputs and the attempt remain unchanged.

[Attempt01](history-cost-attempt01/RESULTS.json) passed one fixed32-loop case with
143 checks:142 case checks plus one invocation check. The observed control wall
time was9.642591362 seconds; final elapsed, including cleanup and rehashing, was
10.730299100 seconds. The outer control's retained CPU observation was6.658848
seconds. One native peer and one outer control were cleanly reaped; both owner
receipts report empty/closed state, no pending interrupts, no cleanup errors and
no unexpected children. The control stayed within the original30-second limit.

The retained249,856-byte DB contains32 original never-handed-off START records,
all original keys and exactly three occupied shared claims. The accepted OPEN
remains, mutation sequence and activation/ACK prefixes stay zero, and no STOP,
REVOKE or RETIRE was sent. The retained logical charge is81,471 bytes under the
unchanged16MiB ceiling. This small prefix is not a full reachable-capacity test.

The recorded validation count is exactly2,176, matching4n+6 for each n=0..31.
There are981 bounded metric rows. The following values include only the32 loop
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

Loop wall time was8.186641095 seconds. Summing only non-held exclusive method
spans gives5.284797397 seconds;2.901843698 seconds falls outside those measured
spans. The method spans contain unknown instrumentation overhead and unmeasured
nested work. Context held lifetimes overlap them and are not added. These are
intrusive wall observations, not CPU attribution, a speedup comparison or a
duration prediction for128 records. Initial candidate imports took0.217065481
seconds, fixture setup0.619897804, initial prepare/OPEN/cycle/snapshot0.493775252;
the true module-to-loop-start interval was1.345672641 seconds.

All28 native selectors were retained before and after the loops. Only response
sequence changed, from6 to70; dispatch, loss, output, clock, boot, source counters,
generation and standing state were unchanged. The140 retained raw packets are70
request/reply pairs: four DESCRIBE, one BIND, one OPEN and64 read-only STATUS
requests, plus replies. Reserved START transport numbers were never handed off.

The new [auditor source](audit_retained.py) and [audit plan](AUDIT-PLAN.md) join the
309 retained attempt files, original299 frozen inputs,261 exact reused files,
25 provenance copies, both sealed parents, public244, original image/evaluation
association, durable records, traces and timing aggregates. Execution of that
independent audit remains pending; this paragraph does not claim an audit pass.

The sealed boundary capacity timeout remains failed. This run changed no
production code and reran no qualifier. Original20-case/173-check host validation,
13 owner-death cases and18 passing boundary cases remain their separate evidence;
this packet does not extend their scope. Full128-record and simultaneous capacity,
the remaining boundary profiles, physical qualification, protected storage and
public deployment eligibility remain open.
