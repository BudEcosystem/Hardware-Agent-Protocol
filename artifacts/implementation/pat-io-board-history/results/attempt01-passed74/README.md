# Actual board-history and reader result: 74 tests pass

The isolated [semantic candidate](../../implementation01/README.md) and
[harness](../../harness01/README.md) pass **74 tests**: 35 new board-history methods
and all 39 unchanged transcript-reader methods. There are zero failures, errors
or skips. Test time is 65.925 seconds; outer time is 74.101164033 seconds, within
the unchanged 180-second deadline. The actual [result](attempt/result.json),
[log](attempt/output.log), [retention proof](proof.json) and [index](index.json)
are retained.

All nineteen historical trial20 data sets are inspected. Eighteen coherent model
histories pass: 29 activations comprise 26 completed cycles and three canceled
activations. The deliberately missing current receipt is rejected while its
original unresolved evidence remains unchanged. The checker preserves provider
completion before authority settlement, including the lost-reply case whose first
completed receipt accompanies an `outcome_unknown` operation and a held claim.
It also accepts an older terminal receipt while a newer valid operation owns the
same pad. These totals and intermediate facts were asserted in-process; this
run does not emit a separate serialized qualification verdict.

The checker derives GPIO/PWM footprints and active/idle model states without
calling provider validators. It checks complete resource/instance inventories,
metadata, scoped proofs, intent digests, dispatch/attempt/event associations,
receipt identities and predecessors, authority receipt copies, and chronological
fencing. Counters are derived from retained history, not accepted because they
balance. Current modeled owners and resource states must agree with pending work.
Start/completion timestamps, strict run/completion/lease limits and four supported
cancellation causes are checked at first capture.

Semantic mutations rebuild canonical pages, row counts, ordering, references and
outer hashes. Inner receipt/dispatch/proof hashes are also recomputed where
relevant. Every semantic mutation first passes the independent structural reader,
then fails its specific history assertion. Covered contradictions include balanced
false counters, forged idle/active state, missing owners/fences/receipts/versions,
reused fences, swapped sessions/attempts/clock epochs, changed immutable receipt
times, mismatched authority copies, premature or deadline-equality completion and
effects appearing before the recorded call. A changed producer parent-status claim
does not turn a canceled activation into a completed cycle. Purity vetoes and
input-nonmutation checks pass.

All 2,802 project/data files, 2,805 frozen preparation entries, six active harness
files and 159 external pins remain stable. The 2,800 inherited files, including
all historical fixture bytes, are unchanged. All 659 actual origins match, with
193 bytecode reads refused and no prohibited attempts. Compiler/provider identities
are stable within this new closure; no historical driver/compiler identity is
qualified as current.

Root rechecked source seals, actual origin-file hashes, exact method/log order and
fixture provenance. All 2,915 trial20 result entries and all 2,837 prior reader39
result entries remain unchanged. The [acquisition](acquisition.log) preserves
2,835 attempt files with equal before/after inventories. The original scratch
directory `/tmp/hms-io-board-history-pure-toqzak9q` remains empty with its original
identity. No simulator was rerun and no database was connected by the test child.

This is a board-history semantic component. `boardHistoryChecked` does not establish
complete authority semantics or physical electrical behavior. Every returned
`authoritySemanticsChecked`, `independentOutcomeChecked` and `qualificationPassed`
flag remains false. Complete operation/event/procedure/replay/floor checks,
independent PAT-to-intent correspondence, no-start guard causes, auxiliary actors,
full configuration attestation, settlement and matrix qualification remain required.
No live HMS runtime, physical device, MCU, model or public service changed. Helper
account limits prevented independent agent review. The historical full748 result
remains separate.
