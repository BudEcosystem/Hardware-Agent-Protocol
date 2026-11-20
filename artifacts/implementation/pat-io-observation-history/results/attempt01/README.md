# Independent sample history: 27 passing pure tests

All 27 new methods pass in 60.606 test seconds and 68.902 elapsed seconds, within
the original 180-second deadline. They check twelve configuration, six active
withdrawal and eight pending-recovery fixtures. All 7,056 inherited source/data
files remain unchanged; the prior 136-method result remains historical and is
not represented as a new full regression.

The checker validates 434 snapshots, 1,288 produced samples and 1,736 retained
value readings. There are 26 initial sample batches, one reopen batch, 134 driven
refreshes and 273 checkpoints retaining cached samples. Seventy-two snapshots
correctly contain a value behind the current board counter: each driven phase
samples before it acts. A committed activation cannot retroactively appear in
that phase's input. Reopening creates new sequence-one streams while preserving
the historical activation count.

Values are synthetic activation counters plus an installed-ready flag. They do
not measure electrical output, prove completed cycles or establish task success.
The sample component validates trusted configuration/grants, PAT correspondence,
guarded stop/recovery causes and independently derived board counts before
checking observation values. It never accepts a supplied validation verdict.

Several rehashed adversaries first pass the previous history checker, then fail
the sample component: monotone undercounts, a same-phase future activation,
skipped sequences, mismatched ready/value refreshes, invented samples during
lowering/admission/cancellation/capture, a suppressed zero-time refresh, a missing
pre-fault sample, a sample predating baseline and an undercount after reopening.
Forged board counts still fail board validation before they can justify a sample.
The full composition also rejects sample lies; both new APIs pass I/O vetoes and
input-immutability assertions.

`inspect_observation_history` checks observations across all 26 fixtures and
leaves full operation/parent flags false. `inspect_observed_execution_history`
additionally runs the original authority/parent composition. Ordinary reopen,
completed-before-withdrawal and lost-reconciliation cases pass that composition.
The two pre-effect permission-refusal fixtures retain their existing full-history
refusals: `PAT_IO_PROCEDURE_SUBMIT_FAILURE_UNIMPLEMENTED` and
`PAT_IO_OPERATION_PREDISPATCH_CAUSE`. There is no fallback to a sample-only verdict.
The next cause extension must derive those refusals from trusted authorization
and prior state before passing a private validated handoff to the respective
event/parent folds. A captured error string alone cannot authorize either cause.

All 7,058 project/data inputs, 7,061 preparation entries, six active harness files
and 159 external pins remain stable. All 681 origins match, 204 bytecode reads
are refused and no prohibited attempts occur. Compiler and driver identities
remain stable within the run. Acquisition compares inherited bytes, original
fixture records and all actual import hashes; 4,235 fixture/manifest files are
rechecked against the sealed original captures. The complete attempt and original
empty private scratch root are retained.

See the [test log](attempt/output.log), [actual result](attempt/result.json),
[acquisition proof](proof.json), [source scope](../../implementation01/README.md),
and [harness scope](../../harness01/SCOPE.md). The original evidence/document/tick
and harness resource limits remain unchanged.

This is a tested observation component and scoped composition, not a complete
qualification verdict. Current compiler identity, the two refusal cause extensions,
broader fault/timing and auxiliary-actor coverage, aggregate enforcement and public
qualification remain unfinished. Full attestation, physical-measurement,
independent-outcome and qualification flags stay false. No Runtime, SQL connection,
physical device, MCU/emulator, live inference, public service or acquired controller
ran. No live HMS or adjacent Harness source changed. Primary-agent review and
acquisition only; helper usage limits prevented independent agent review.
