# PAT control-storage capacity review

Five original bounded SQLite experiments pass on SQLite 3.45.1. A separate
read-only allocation audit passes against the preceding complete catalog scope.
This stage changes no production runtime and establishes no physical capacity
reservation. The [design](DESIGN.md) selects separate evidence/control stores and
connections, with an explicit new publication and admission contract to implement.

| Experiment | Retained observation |
|---|---|
| Database-full rollback | SQLITE_FULL rolled back the active transaction; original control state survived and a subsequent small control write succeeded |
| Freelist reuse | Requesting a 33-page cap on a 34-page file returned 34; evidence reused two free pages without growing the file |
| Reopening | A 16-page cap reopened at 4,294,967,294 until explicitly reapplied before data mutation |
| Live journal | A zero journal retention limit still allowed a 17,024-byte active rollback journal |
| Separate files | A 16-page bulk database filled after seven committed rows; a failed cross-database transaction left no control marker, then an independent control write succeeded |

[Attempt 01](attempts/attempt01/result.json) remains failed: the exact-path
authorizer refused a parameterized ATTACH during SQL preparation. Its six files
and traceback are retained; no five-case passing receipt is claimed for it.
[Source 02](source02/origin.json) changes only the internally generated ATTACH
statement to a safely quoted literal and selects a fresh attempt directory. The
authorizer and all limits remain unchanged. [Attempt 02](attempts/attempt02/result.json)
passes all five cases in 0.316 seconds, retaining 76,800 bytes across six files.
The [complete child observations](attempts/attempt02/stdout.log) and
[scope](SCOPE.md) specify the tested limits and exclusions.

The [allocation audit](allocation.json), executed once from source 01, holds 56
owner/writer locks and checks original/copy hashes against the previous sealed
index. Both remain unchanged. Of the 16,199,680-byte authority file, 15,440,896
bytes belong to compact evidence and 758,784 bytes to other btrees. There are no
freelist pages. The 577,536-byte gap below the file ceiling is not a reservation.
The copied source-02 audit script was not executed.

The [primary-source overlay](../../../research/host-contract/capacity-followup/README.md)
retains eight official SQLite pages and exact reading coverage. The evidence
supports keeping database ceilings, aggregate filesystem quotas and capacity owed
to admitted work as separate requirements. Attached-file atomicity is documented
under specific SQLite configurations; this experiment does not test power loss
or prove isolation from a missing/failed attachment.

The new profile remains design work. No evidence history was removed, no existing
run was retried, no old bound was raised, and no device, driver or hub service was
operated. The full HMS goal remains active.
