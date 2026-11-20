# Actual original-run import attempt

Status: **verified progress; actual scope failed before evidence import**.
The [read-only audit](RESULTS.json) preserves all three failed scopes and confirms
that production remains unchanged. A fresh owned worker requested the complete
30-case matrix and reached its original 60-second supervisor deadline. It retained
30 case directories and 29 manifests; the final shared-resource GPIO/PWM challenge
is incomplete. A case manifest alone is not independent qualification evidence.

The original attempt is `bc1ae56b94664e38961ea82bb7aa9de6`. Its archive records
`SUPERVISOR_DEADLINE`, exit `-15`, incomplete transport, no complete return or
evidence-integrity closure, and **unknown unresolved effects**. It must not be
relabelled as a passed run or replaced under another key. The source authority
retains one original reservation/handoff, zero import intents and publications;
the installed vault contains zero manifests, references and bodies. No source
PAT application was invoked.

The [actual harness](harness03/README.md) keeps the original 180-second child wait,
60-second worker, six parent SQLite opens, 16 MiB single-file limit, 256 MiB scratch
bound, 15 MiB vault cap and five-second snapshot. All 262 producer-image files
match the acquired project/dependencies. The audit independently recomputes the
legacy consumer, vault and authority-importer identities.

The audit holds **57 original owner/writer locks**, including the original writer
lease identity, and checks **four source databases** without changing their hashes.
It verifies all original and retained scratch bytes. It does not open or recover
the interrupted worker's per-case databases. Quiescence permits inspection; it does
not establish that the partial worker completed or settled every simulated effect.

The final test took 77.887 seconds; the enclosing attempt took 83.094 seconds.
Observed test-body phases place spawn at 12.257 seconds and producer settlement
at 72.319 seconds. Installation completed before launch, and no import phase was
reached. These observations establish a deadline failure, not its underlying
performance cause or a deployment latency guarantee.

## Retained preparation failures

- [Scope01](harness01/README.md) failed during loading because the new test imported
  evidence before the inherited fixture configured the supervisor module path.
  It opened no SQLite connection and launched no worker. The
  [fresh source correction](implementation02/correction.json) moves only that import;
  the complete test class AST and all production files are identical.
- [Scope02](harness02/README.md) rejected the vault's exact `file:` URI after three
  setup connections. Its declared path was correct, but the harness treated the
  URI as a filesystem path. No worker was launched. Scope03 recognizes only that
  exact declared URI with `mode=rw`, retaining the same path set and six-open limit.
- The first independent audit compared Python path-component order with the
  runner's relative-path string order. All path/size/hash mappings were identical.
  Its [failure record](audit01-failure.json) remains; the corrected audit passes.

All 285 inherited files remain exact in source01; source02 changes only the newly
added test's import order. The earlier [25 authority controls](../../verification/pat-vault-authority-controls/README.md)
remain passing historical evidence on identical production. They do not supply
the missing complete actual-run qualification.

[Catalog source review](CATALOG-NOTES.md) identifies the distinct snapshot and
precommit integration required next. [Next work](NEXT.md) retains performance,
actual import, catalog, public tooling, prompt learning and physical providers.
The full HMS goal remains active.
