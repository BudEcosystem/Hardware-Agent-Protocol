# Snapshot 08: exact refusal expectation correction

This is source preparation only. It copies snapshot 07 and changes one assertion block in `test_bad_typed_revision_and_ordinary_grants_do_not_authorize_management`. The bool revision must raise `JournalError` with exact code `ARGUMENT_SCHEMA_MISMATCH`; immediate zero-operation and zero-claim checks separate that refusal from the unchanged ordinary-grant authorization half.

The preserved 44-method attempt ran 43 clean methods and one error: the first assertion expected `ContractError`, so the grant half did not execute. Its log and copied immutable DB inspection show the existing Registry refusal before any operation, claim or effect. No production fix is inferred. The original failed attempt and all prior snapshots remain unchanged.

All 48 HMS modules, the other 155 project inputs, runner, child, selected package inventory, source-origin checks, scratch policy and timeout are byte-identical to snapshot 07. All other lifecycle methods and their ASTs are unchanged. The inherited README, acceptance plan and source-preparation.json are historical snapshot-07 material; this revision note and source-preparation-08.json describe the new snapshot.

No test, project import, Runtime, SQLite effect or child execution has occurred for snapshot 08. `commands.json` records proposed focused-one and 44-method commands; each requires a separate parent release. New boundary cases, the wider regression suite, public lifecycle output/mounting and physical execution are outside this correction.
