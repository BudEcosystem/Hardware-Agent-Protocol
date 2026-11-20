# Split supervisor storage — complete simulated integration passed

Stage 90, 2026-11-09. The exact isolated [stage-89 candidate](../../implementation/supervisor-storage-bindings/README.md)
now has passing evidence for **71 distinct controls** and the **complete original
thirty-case worker → vault → catalog → one PAT application**. The source remains
unchanged and is not installed in the public runtime.

The new version-3 ledger binds separate owned control and bulk roots. Its tests
cover cold control/history with bulk unopened, missing/replaced bulk refusal,
marker and owner identity, combined logical retention accounting, pre-SQLite
sidecar refusal, uncertain armed recovery and a real inherited writer lease.
Existing authority, handoff and recovery controls retain their exact methods.

The first revised harness corrected stage 89's unsafe scratch placement by using
fresh private directories below sticky `/tmp`. Four diagnostic scopes passed
28 controls. The next four-test batch received SIGKILL after 41.5 seconds, without
a final child receipt; that batch remains **failed and retained**. Its exact cause
is not conclusively established. No original fixture was reopened or repaired.

A declared diagnostic-profile revision ran the remaining 43 controls separately,
recording direct-child CPU usage. All passed. This increases total diagnostic
budget; it is **not** a pass for the original fourteen-scope packing. Per-process
60-second wall / 40-second CPU, 512 MiB memory, 128 FDs, 16 MiB file and 256 MiB
scratch bounds stayed fixed. All 71 original method identities have complete
passing receipts across 47 passing scopes. The failed scope is additional.
[Control audit](CONTROL_AUDIT.json), [review](REVIEW.md).

The complete actual integration retained its original combined scope and bounds.
It launched **one worker**, captured and semantically checked **30 cases**, made
one vault publication, activated one catalog entry and completed **one simulated
application with one activation and one completion**. Original-key replay,
configuration-drift refusal and cold vault/bridge history passed. Worker time was
**47.915 seconds** under 60; total launcher elapsed time was **125.887 seconds**
under the 180-second parent bound. This single observation does not qualify
deployment timing or establish a performance improvement.

The [actual audit](ACTUAL_RESULTS.json) verifies **4,270 retained files /
35,508,922 bytes**, a **268-file code image**, all **4,011 vault references and
2,798 bodies**, and the source/identity/publication/catalog/effect joins. It holds
**58 original owner/writer files** and reads only four parent databases in immutable
read-only mode; no worker-case database is opened. The stored control/bulk binding
matches the original root, owner and manifest objects. The native scan covers
exactly control, bulk and the selected attempt, preserving the aggregate logical
scan budget. All raw scratch and verified copies remain retained.

All **244 public runtime inputs** remain exact against the existing **866-test**
passing baseline. That public suite was not repeated because no public runtime
code changed. Physical device/driver/hub providers, public qualification mounting,
hard quotas, backed control continuations, hot-journal recovery and the full
filesystem/SQLite profile remain unfinished. The broader HMS goal stays active.

[Plan](PLAN.md) · [actual harness adaptation](harness01/adaptation.patch) ·
[actual audit adaptation](actual-audit-adaptation.patch) · [audit](AUDIT.json) ·
[next work](NEXT.md). Primary-agent review; no independent review claimed.
