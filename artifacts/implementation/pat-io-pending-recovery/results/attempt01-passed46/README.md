# Pending-output recovery: 46 passing original host tests

All 46 tests passed in 334.815 test seconds and 355.192 elapsed seconds, within
the original 600-second harness deadline. The selection contains the prior 38
capture methods and eight new recovery cases. All 5,903 inherited project/data
inputs are unchanged; the candidate adds one test file. Production runtime,
provider, compiler and independent-reader behavior remain unchanged.

The new cases demonstrate that an unknown authority outcome can coexist with an
active output, pending receipt, board ownership and held authority claims. A lost
activation reply does not imply that activation failed. A failed stop attempt
before commitment leaves those states intact. Recovery stops the existing output,
retains the original activation and reconciles the same operation without another
activation. The eight final receipts are canceled with `reconciliation_stop`:
eight activations, zero completed cycles and eight canceled activations.

GPIO recovery prevents the remaining PAT step from running. PWM recovery restores
all three claimed resources. Recovery at due time stops rather than claiming
completion, and invocation withdrawal does not prevent that recovery. A prior
client cancellation leaves the parent canceled, but the child settles as failed
with a recovery-stop receipt and its cancellation request still recorded. That
parent state is not evidence of a confirmed client-cancel stop cause.

The authority-reconciliation reply-loss case retains a committed board stop and
modeled idle while the authority remains unknown and holds its claims. A later
phase reconciles the existing terminal receipt and releases claims. The failed
recovery-stop case instead retains a pending active output until the later stop
succeeds. All cases repeat an adapter phase after settlement and assert no new
activation or receipt version.

Trusted fault schedules declare ten injections at exact phases and named points:
seven lost post-commit activation replies, two failed pre-commit finishes and one
failed authority reconciliation after the board stop. Each manifest retains a
separate authority plan and the actual injection identities/counts. The harness
compares those declarations to its reviewed schedule; captured outcomes do not
define their own expected fault plan.

The 45 engine states retain 90 closed databases, 5,771 execution records and
1,057 configuration records, including 434 paired configuration snapshots.
All 5,904 project/data inputs, 5,907 preparation entries, six active harness files
and 159 external pins stay stable. All 709 origins match; 218 bytecode reads were
refused, with no prohibited attempts. The original per-trial limits are unchanged.
Original scratch `/tmp/hms-io-pending-recovery-wo86732j` remains retained and
unchanged, totaling 42,800,037 bytes. The inherited missing-receipt fixture still
retains its unresolved operation, authority claim and board owner.

Acquisition verifies 7,054 raw/copy scratch files, all 786 execution checkpoints,
22,794 execution-table references and 6,510 configuration-table references. It
compares 1,695 final table snapshots against the 90 copied closed databases and
retains all 12,992 attempt files. Original scratch and historical artifacts remain
unchanged. In the acquisition proof, the inherited `newActiveTrials`, `newEffects`
and `replyLossCases` field names describe the six active38 regression cases;
`newPendingTrials`, `pendingEffects` and `injectedFaultsChecked` describe the eight
cases added by this stage. Their counts are distinct.

See [proof](proof.json), [pending states](pending-states.json),
[all observations](observations.json), the actual [log](attempt/output.log),
[result](attempt/result.json), [source](../../implementation01/README.md), and
[harness scope](../../harness01/SCOPE.md). Primary-agent acquisition checks raw
and copied bytes, paired snapshots and final tables against read-only immutable
copies of the closed databases. It compares fault schedules to the retained
unknown/pending/terminal/claim states; these are association checks, not a new
independent derivation of the fault cause.

The [oracle handoff](ORACLE-HANDOFF.md) specifies the next independent trusted-fault
and recovery-cause checks. The existing composed reader still refuses pending
unknown recovery. Broader fault/auxiliary-actor coverage, current compiler identity,
intermediate sampling, aggregate storage enforcement and public qualification
remain unfinished. Full-outcome and qualification flags stay false. No physical
device, MCU/emulator, live inference or public service ran. No live HMS or adjacent
Harness source changed; the historical full748 regression is not extended.
Helper account limits prevented independent agent review.
