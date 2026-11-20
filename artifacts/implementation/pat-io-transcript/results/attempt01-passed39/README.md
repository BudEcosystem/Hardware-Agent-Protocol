# Actual transcript-reader result: 39 tests pass

The isolated [reader candidate](../../implementation01/README.md) and
[harness](../../harness01/README.md) pass **39 tests**, with zero failures, errors
or skips, in 11.478 test seconds and 15.955765874 outer seconds. The actual
[result](attempt/result.json), [test log](attempt/output.log),
[acquisition proof](proof.json) and [index](index.json) are retained.

The all-trials method checks every one of the nineteen original trial20 outputs:
2,619 records, 352 checkpoints and 153 calls. This is inspection of retained data,
not another execution of the simulator. The data includes cancellation, restart,
lost replies, a missing receipt, typed negative input, lowered budgets and the
sixteen-step multi-page case.

The new reader independently checks the closed serialization and phase grammar:
all 29 tables and exact columns/types, bounded ordered pages, unique primary keys,
canonical embedded documents, complete backward references, call brackets,
controlled clocks, reopen epochs/sessions and exact compiler-return/plan equality.
It checks every recorded byte and does not resolve a path supplied by a transcript.
Trusted setup must be supplied separately from the untrusted records.

Mutation tests recompute record hashes, changed page references and observation
accounting. They still reject missing/duplicate/forward pages, omitted/duplicate
tables, duplicate keys, unsorted rows, incorrect scalar tags, altered blob bytes,
missing call boundaries, contradictory clocks, stale sessions, skipped epochs,
changed plans, truncation and inserted success claims. Separate tests cover
envelope integrity and bounds. A purity test vetoes files, clocks and SQLite
during inspection; source inspection confirms no producer/provider imports.
These are actual in-process assertions, not a separate semantic-outcome verdict.

Structural acceptance is deliberately weaker than a successful outcome. The
missing-receipt transcript remains structurally complete and reports one
unresolved operation. Every inspection result keeps
`independentOutcomeChecked: false` and `qualificationPassed: false`.

All 2,800 copied project/data files, 2,803 preparation entries, six active harness
files and 159 external pins are unchanged. Of the project closure, 159 inputs are
inherited unchanged; the additions are the reader/tests and exact historical data.
All 655 recorded origins match, with 191 bytecode reads refused and no prohibited
attempts. Compiler/provider identities are stable within this run. The historical
fixtures retain their older identities; no current-source reconstruction or
qualification of those identities is claimed.

Root rehashed the actual source/origin files, verified the exact 39-method log
order and checked all historical fixture bytes against the original retained
trial20 package. All 2,915 entries in that earlier result seal remain unchanged.
The successful [acquisition](acquisition.log) copied 2,833 attempt files, with
before/after inventories equal. The original private scratch directory
`/tmp/hms-io-transcript-pure-zmxl9md0` remains empty with its original identity.

This completes the reader component. Independent GPIO/PWM state/footprint
derivation, receipt/intent/proof joins, counter histories, event/replay semantics,
complete configuration attestation, settlement and matrix-level qualification
remain unfinished. Helper usage limits prevented independent agent review. No
live HMS module, physical device, MCU, live model or public service changed; no
SQLite connection or Runtime construction occurred in this test child. The
historical full748 verification remains separate.
