# Batch and admission controls

One owned isolated child executes the [60 frozen methods](../implementation01/test-selection.json):
25 new batch controls, six unchanged single-snapshot/storage controls and all 29
business-commit methods from the previous source. The Journal and prior snapshot
methods have identical ASTs/source to their preceding implementation. This scope
does not repeat the 22 general Journal methods or original worker trial.

The harness derives from the passing business-precommit harness. The source path,
source pin and explicit test selection change; batch and single-snapshot fixture
roots are added and the now-unused temporary-directory override is removed.
Limits remain 45 CPU seconds, 512 MiB address space, 8 MiB per file, 128 descriptors
and a 60-second owned-child wall limit. No subprocess, network, device-file or
outside-attempt database/write action is permitted by the child audit hook.
The exact selected sources/dependencies are verified before and after normal
imports, with project/dependency bytecode refused. Standard-library and installed
interpreter behavior is not a fully attested dynamic-library closure.

Every fresh fixture is retained. Tests use actual SQLite reader locks, read-only
mode, corruption and capacity refusals; time and commit fault seams are installed
test controls. Five joint batch/Journal scenarios are present across the selected
methods, with whole-inventory validity, missing evidence, commit-time expiry and
post-commit cleanup/replay explicitly covered by the new module. The exact method
list governs counts; no catalog mount, qualification worker or physical provider
is exercised. Parent stdout/stderr, pre-verification test log, verified receipts
and all scratch files remain in the attempt.
