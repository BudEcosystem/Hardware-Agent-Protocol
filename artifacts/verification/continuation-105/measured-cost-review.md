# What the diagnostic changes

The actual diagnostic attempt completed once with unchanged production and the
original native image/evaluator. Its observed control interval is 9.642591362s;
final launcher bookkeeping/cleanup completes at 10.730299100s. The loop itself
is 8.186641095s. The original 128-record capacity profile remains failed at its
thirty-second limit; this separate 32-record diagnostic does not replace it.

The source count model is confirmed: iteration n performs 4n+6 mutation
validations, comprising 2n during preparation, n+5 during abandonment and n+1
during the old post-assertion. The total is 2,176. The 4,352 read-SELECT figure
remains a source prediction, not an independently observed SQL count.

The audit separates setup/final/cleanup from loop-only timings. The largest
measured exclusive loop spans are catalog._selected (64 calls, 1.928830858s),
policy.hold_image.enter (32, 0.827209297s), policy.fresh (128, 0.809445257s),
store.abandon_prepared_mutation (32, 0.452657952s), deployment-row reads (416,
0.384699585s), mutation-row reads (2,176, 0.304479336s) and remaining mutation
validation (2,176, 0.106740081s). These are measured method wall spans including
unknown probe overhead. They are not CPU attribution. Inclusive spans and held
context lifetimes overlap and must not be added to those exclusive quantities.
The non-held exclusive total is 5.284797397s, leaving 2.901843698s of loop wall
time outside those spans. This remainder has not been assigned to a cause.

Focused source reads of InstalledPolicy and StandingCatalog show repeated pure
installation/artifact parsing and compilation within selection, in addition to
the current source, database and authority checks. The aggregate _selected
measurement does not identify one inner parser as the bottleneck. A next source
proposal can assess reuse of a detached, already validated installation inside
one pure call chain, with independent equivalence and freshness controls. It
must not omit current policy, DB inventory, evidence-lease, source-image or
commit checks, or reuse authority across callbacks. O(n²) mutation history also
remains a concrete cost, even though it is smaller in this bounded run.

The raw trace contains four DESCRIBE, one BIND, one OPEN and 64 STATUS requests,
with all 70 corresponding replies. No reserved START is sent. All 28 native
selectors agree before/after except the response counter (6 to 70). The retained
249,856-byte database contains 32 canonical never-handed-off records, three
shared claims, zero mutation sequence and no activations/episodes. Its independent
logical charge is 81,471 bytes, not a full-capacity result.

Root read the complete 422-line data auditor before executing it once. The
receipt retains 61,794 evidence assertions; the terminal summary reports 61,795
because the final receipt-size assertion follows the output count snapshot.
Both numbers describe that same successful execution. No source/receipt was
rewritten and no candidate or auditor retry occurred. The audit verifies 309
attempt files, the original 299 frozen inputs, 5,067 parent files, 244 public
inputs and the absence of both reaped process identities. It does not establish
full capacity, protected storage, target fit, physical I/O or learned PAT domains.
