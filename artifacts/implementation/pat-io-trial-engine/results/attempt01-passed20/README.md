# Actual I/O phase-engine result: 20 tests pass

The isolated [candidate](../../implementation01/README.md) and
[harness](../../harness01/README.md) ran all twenty selected integration methods:
**20 pass, zero failures, errors or skips**, in 114.915 test seconds and
121.191994721 outer seconds. The actual [result](attempt/result.json),
[test log](attempt/output.log), [retention proof](proof.json) and
[capture comparisons](observations.json) are retained here. This is an original
host simulation result for a worker component, not an I/O qualification decision.

The engine uses the actual private `IoRuntime`, trusted I/O binding resolver,
compiler, procedure manager and GPIO/PWM board. Tests cover sequential completion,
same-time progress, early admission while waiting, exact replay, cancellation
before and after activation, restart, lost replies/receipts, strict execution
deadlines, typed negative inputs, sixteen steps and lowered evidence/tick limits.
The sixteen-step case retains sixteen completed cycles and 32 receipt versions.

I/O recovery preserves the compiled request's original session. Owner reopen
rotates the board session: an accepted command or unstarted suffix refuses resume
with `IO_SESSION_CHANGED`; pending work is canceled once by board reopen. A
completed single-step history can reconcile after a lost reply and finish without
another activation. A completed prefix remains completed when its unfinished
suffix is refused. These cases do not reuse the fan worker's recovery assumptions.

All 159 copied project inputs, 162 frozen preparation entries, six active harness
inputs and 159 selected external files remain stable. All 691 recorded origins
match; 209 bytecode reads are refused, with no prohibited network/subprocess
attempts. Compiler and driver identities are unchanged. Root rechecked the exact
method order, source seals and actual origin-file hashes after execution.

All twenty workspaces are retained, including nineteen engine states, 38 closed
databases and 2,619 records. The original private root
`/tmp/hms-io-trial-engine-w72g_7vf` remains in place with its original identity;
2,715 raw files totaling 17,183,506 bytes match both retained copies. Nothing was
deleted or reset. The copied attempt contains 2,908 files including source,
harness, execution receipts and fixtures.

A separate standard-library acquisition script checked all record hashes,
352 checkpoints, 10,208 table references, typed cells and clock/call ordering.
It opened only copied databases using SQLite `mode=ro&immutable=1`, checked their
integrity and compared 551 final captured tables byte-for-byte at cell level
with the 38 closed databases. This validates capture consistency, not independent
effect semantics. No project module was imported by that script.

The deliberately missing current receipt remains absent, with one historical
pending version, one board owner and one authority claim. Its operation is still
unresolved. The two lowered-budget fixtures retain accepted parents without
child operations. Closing a runtime is not evidence of settlement. Every engine
report and the root proof keep `qualificationPassed: false` and
`independentOutcomeChecked: false`.

The first [acquisition script](acquire.py) stopped before copying anything: it
mistakenly treated the harness index's relative paths as repository-root paths.
Its [failure log](acquisition.log) is preserved. The one-location correction in
[acquire02.py](acquire02.py) uses the harness directory for that index; its
[successful log](acquisition02.log) records the actual acquisition/comparison
counts. This correction did not rerun or change the tested source, test inputs,
attempt, raw state or harness.

Independent agent review was unavailable because the helper agents reached their
account usage limit. Matrix/fault orchestration, complete configuration attestation,
an independent outcome reducer, enforced aggregate storage, public qualification
and actual-device evidence remain unfinished. The live HMS runtime, adjacent
Harness checkout and historical full748 verification are unchanged. No physical
device, MCU program, live inference or external service ran.

The [index](index.json) seals this result package; source and harness seals remain
separate and unchanged.
