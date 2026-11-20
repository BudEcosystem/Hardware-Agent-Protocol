# Actual service writers and storage contract

Stage 88, 2026-11-09. Source assessment changes the next implementation step:
**split supervisor control from bulk explicitly before exposing the storage
adapter to the complete service**. [Required contract](CONTRACT.md).

The assessment freezes 124 current Python/C sources and parses all 123 Python
modules without importing HMS. It classifies every one of 156 selected syntactic
I/O candidates and identifies the five SQLite connection constructors. Fourteen
current source files / 2,329 LF lines were read in full, with selected ranges from
other files recorded separately. The complete official SQLite temporary-file
article adds 489 rendered LF lines. [Reading coverage](reading.json).

The current supervisor ledger and worker/code trees share one root. Launch,
admission scanning, recovery and archive import all rely on that binding. Several
database constructors mutate recovery state before a later service could enforce
capacity. SQLite also has implicit temporary-file paths that a Python call census
cannot prove confined.

The successful retained workflow used 267 code-image files and 3,936 output files;
its supervisor tree had 4,248 regular files and 164 inferred non-root directories.
Current generated components reach 94 bytes including a rollback-journal suffix.
The private 16-inode / 63-byte-name adapter cannot host this namespace. These are
exact source/index observations, not capacity reservations or a new worker run.
[Results](RESULTS.json), [call inventory](call-inventory.json),
[classification](site-review.json), [historical inputs](observation-inputs.json).

All 244 runtime inputs remain exact against the existing 866-test passing receipt.
No database is opened, no worker is rerun, and no runtime, mount or physical provider
changes. The preceding [block-read regressions](../chunk-block-read-regressions/README.md)
remain sealed and valid for their declared scope. [Audit](AUDIT.json),
[exact index](index.json), [next implementation](NEXT.md). The full goal stays active.
