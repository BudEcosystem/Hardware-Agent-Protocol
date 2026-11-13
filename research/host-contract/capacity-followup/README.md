# SQLite capacity and control-history follow-up

Eight official SQLite pages are retained as raw HTML, extracted text and hashed
metadata. The [reading receipt](reading.json) records **2,449 LF lines**: seven
complete extracted texts and selected sections of the PRAGMA reference. Inline
syntax-diagram text was read for Transaction and ATTACH; diagram geometry and the
remaining PRAGMA sections are still unreviewed. This is not a full-media reading
claim. No acquired script or repository code was executed.

The metadata files retain their original acquisition-time status. The separate
reading receipt records subsequent coverage without rewriting those records.
The [launcher note](launcher-note.json) retains one unsuccessful `python` command
before using the available `python3` interpreter; no acquisition started in the
failed launch. The three acquisition utilities use fixed official URLs and a
2 MiB per-response bound. Source HTML scripts/styles are never executed.

## Source notes

| Source | Coverage | Consequence for HMS |
|---|---|---|
| [SQLite limits](https://sqlite.org/limits.html) / [local text](text/limits.txt) | 362/362 LF lines | Limits need explicit, tested bounds. Maximum page count bounds one database file; growth beyond it returns SQLITE_FULL. Row, SQL, column and schema limits are separate concerns. Published defaults vary by SQLite version. |
| [Transactions](https://sqlite.org/lang_transaction.html) / [local text](text/transactions.txt) | 235/235 LF lines; diagram geometry pending | BEGIN IMMEDIATE acquires write authority early. FULL/IOERR/INTERRUPT/NOMEM may roll back a statement or the whole transaction. Check transaction state and settle rollback explicitly; never assume a failed statement preserved the surrounding work. |
| [Temporary files](https://sqlite.org/tempfiles.html) / [local text](text/tempfiles.txt) | 618/618 LF lines | A main-file cap does not cover rollback journals, super-journals, WAL, statement journals, temporary databases, materializations, transient indexes or VACUUM work. Some temporary-file behavior is explicitly implementation-dependent. Memory temporary storage does not remove durable journal obligations. |
| [DBSTAT](https://sqlite.org/dbstat.html) / [local text](text/dbstat.txt) | 194/194 LF lines | Read-only built-in DBSTAT can report btree allocation without creating a virtual table when compiled in. Freelist, pointer-map and lock pages are omitted; audit them separately before treating sums as complete. |
| [PRAGMA reference](https://sqlite.org/pragma.html) / [local text](text/pragmas.txt) | 251/2,688 LF lines in four recorded ranges | max_page_count returns its actual cap and cannot go below existing pages. journal_size_limit bounds files left after transactions/checkpoints, not their peak active size. Page-size changes are deferred; synchronous EXTRA adds directory synchronization for DELETE-journal commits. |
| [ATTACH](https://sqlite.org/lang_attach.html) / [local text](text/attach.txt) | 517/517 LF lines; diagram geometry pending | Schema qualification avoids ambiguous table lookup. Multi-file atomicity depends on configuration; WAL and in-memory main databases have different crash behavior. Attaching a file does not isolate its failures from control operations. |
| [Authorizer callbacks](https://sqlite.org/c3ref/set_authorizer.html) / [local text](text/authorizer.txt) | 188/188 LF lines | Authorization occurs during SQL preparation and may recur during re-preparation. Arguments can be NULL. Keep the correct callback active; do not change the connection inside it. Callback authorization is not a substitute for current runtime permissions. |
| [Authorizer action codes](https://sqlite.org/c3ref/c_alter_table.html) / [local text](text/authorizer-codes.txt) | 84/84 LF lines | Actions identify different objects and may supply NULL fields. ATTACH identifies a filename; READ includes schema context. A profile must reject unknown attachment/read contexts rather than broadening a default allowlist. |

These pages were acquired on 2026-11-08. Current web documentation includes
features newer than the locally observed SQLite **3.45.1**. In particular, schema
limit documentation for 3.54.0 must not be treated as available in the local build.
The cited documents state conditions for SQLite behavior; they do not qualify
this host's filesystem, power-loss behavior or device control.

## Findings and original experiments

The [bounded host experiments](../../../artifacts/verification/pat-storage-capacity/README.md)
separate three requirements: a per-file ceiling, aggregate storage enforcement,
and capacity still owed to admitted control work. The passing scope observes
cap reset after reopen, evidence reuse of free pages, a live journal larger than
its zero retention setting, and control progress after a separate bulk file fills.
The initial attachment-guard failure remains retained separately.

These observations reject a page-limit-only reservation design. They support
separating bulk evidence from authority history, but do not prove a particular
filesystem allocation is reserved or an active operation can always settle.
The [implementation design](../../../artifacts/verification/pat-storage-capacity/DESIGN.md)
requires separate connection/failure handling, immutable evidence publication,
current-body checks, pre-recovery cap verification, and a real capacity provider.
The existing current-body, original-key and unknown-outcome rules remain required.

No retained runtime database was changed. No production profile, public tool or
physical provider was enabled. The broader full-source reading backlog remains.
