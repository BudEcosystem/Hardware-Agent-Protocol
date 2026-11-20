# Independent pending-output recovery: 136 passing pure tests

Two disjoint selections pass against the same frozen source: 83 configuration
and board regressions in 77.009 test seconds (84.888 elapsed), followed by 20
authorization regressions and 33 new recovery methods in 112.575 test seconds
(123.602 elapsed). Both retain the original 180-second deadline. Together they
cover all 103 previous methods and 33 new methods, with zero failures, errors,
skips or expected failures. These are separate attempts, not one combined
qualification-worker run or a replacement for the historical full748 regression.

The new checker joins separately trusted fault and permission schedules with
independently checked PAT requests, board state/receipts, authority events/claims
and parent history. It distinguishes post-commit activation reply loss,
pre-commit finish failure and pre-commit reconciliation failure. It derives each
fault's target from the prior state and requires every scheduled fault to appear
at its exact phase. Producer injection summaries do not authorize a fault cause.

All eight acquired recovery histories pass. They contain eight activations,
zero completed cycles and eight recovery cancellations; seven parents fail and
the previously canceled parent remains canceled. Ten fault observations, ten
guard phases, eight recovery stops and eight settlements are checked. Each final
board is modeled idle, with no unresolved operation or held authority claim.
Failed stops retain active output and claims. A committed stop with a lost
reconciliation reply retains terminal board proof while authority stays unknown.
Later unfailed recovery must settle that same receipt and release its claims.

One adversarial test first proves that the existing operation-event checker can
accept a consistent but stalled unknown history. The new composition rejects it
because an observed successful recovery did not settle the operation. Other
rehashed adversaries cover invented/omitted faults, unexpected errors, altered
unknown causes, lost proof, early claim release, false completion, rewritten
cancellation, hidden activation, active PWM output after stopping and false
parent success. Due time, invocation withdrawal and client cancellation cannot
relabel a pending-unknown recovery stop. Both standalone APIs retain their
original refusal unless the recovery cause is independently joined.

The source preserves 5,902 inherited project/data files, changes only two pure
reader modules and adds the recovery module, 33-method test file and 1,150
fixture/index files. The eight manifests and 1,141 record files are exact copies
of the retained recovery46 captures: 823 execution records, 318 configuration
records and 136 paired snapshots. Trusted schedules are separately checked
against the reviewed capture-harness selection. Runtime, provider, compiler and
inherited tests are unchanged.

Each attempt preserves all 7,056 project/data inputs, 7,061 preparation entries,
six active harness inputs and 159 external pins. The runs record 665 and 677
matching origins respectively, refuse 196 and 202 bytecode reads, and contain no
prohibited attempts. Compiler and driver identities remain stable within each
run. Inspection also passes file/clock/SQL vetoes and input-immutability checks.
The complete attempts retain 7,089 files each, alongside their original empty
private scratch roots.
Acquisition rehashes all 12,999 entries in the original recovery46 result, exact
fixture provenance, actual import files and the source/harness inventories.

See the [83-test log](attempt01-regression83/output.log),
[83-test result](attempt01-regression83/result.json),
[53-test log](attempt02-recovery53/output.log),
[53-test result](attempt02-recovery53/result.json),
[acquisition proof](proof.json), [selection plan](selection-plan.json),
[source scope](../../implementation01/README.md),
[regression harness](../../harness01-regression83/SCOPE.md), and
[recovery harness](../../harness02-recovery53/SCOPE.md).

This closes the tested pending-output recovery cause/settlement gap for one
immutable synthetic installation. Full read withdrawal, recovery across reopen
or clock loss, auxiliary actors, intermediate sample semantics, current compiler
identity, the complete timing/fault matrix, aggregate storage enforcement and
public qualification remain unfinished. Full attestation, independent-outcome
and qualification flags stay false. No Runtime, SQLite connection, physical
device, MCU/emulator, live inference or public service ran in these pure tests.
No live HMS or adjacent Harness source changed. Helper usage limits prevented
independent agent review; the source review and acquisition were by the primary
agent.
