"""Update current status with the completed isolated integration evidence."""
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
def replace_between(name,start,end,body):
    p=ROOT/name;s=p.read_text();left=s.index(start);right=s.index(end,left)
    p.write_text(s[:left]+body+s[right:])

replace_between('README.md','The [supervisor storage-binding candidate]','The [PAT foundation]',
'''The [split supervisor integration](artifacts/verification/supervisor-storage-integration/README.md)
now passes **71 distinct controls and the complete thirty-case simulated worker →
vault → catalog → one PAT application** against separate owned control/bulk roots.
The worker completes in 47.9 seconds under 60; the parent in 125.9 seconds under
180. One failed diagnostic batch remains retained; its remaining controls passed
in explicitly revised individual scopes with a larger total diagnostic budget.
The complete actual scope and bounds stayed fixed. All 244 public runtime inputs
remain exact; this candidate is still isolated. Full storage capacity/recovery
qualification and physical providers remain unfinished. Device I/O, drivers and
the intelligence hub remain one [managed resource graph](docs/io-driver-hub-control.md).

''')
replace_between('PROGRESS.md','Status: **active, incomplete','## Earlier continuation: qualification libraries installed',
'''Status: **active, incomplete — split supervisor control/bulk bindings pass
71 distinct controls and the complete original simulated integration**. The
previous turn authored and froze the candidate and identified unsafe harness
scratch ancestry before SQLite opened. That 655-file seal remains exact.

The [new verification](artifacts/verification/supervisor-storage-integration/README.md)
keeps all 309 candidate project files and 312 frozen source inputs unchanged.
Fresh private scratch under sticky `/tmp` fixes placement. Thirteen authority,
eleven recovery, thirty-two handoff and fifteen split-binding controls have
complete passing receipts. Missing/replaced bulk, control-only cold history,
marker/owner changes, inherited writer leases and uncertain recovery are covered.

The original fourteen-scope diagnostic packing remains **failed**: four scopes
passed 28 methods, then a four-test batch received SIGKILL after 41.5 seconds with
no final child receipt. Its cause is not conclusively established. The exact raw
state, acquired copy, original leases, source and log remain retained. A declared
profile revision ran the remaining 43 methods individually and recorded child CPU.
All passed, giving 71 distinct methods in 47 complete passing scopes. This changes
batching and increases aggregate diagnostic budget; each process retains its
60-second wall / 40-second CPU, memory, FD, file and scratch bounds.

The full actual integration retains its **original combined scope and limits**:
one worker, all **30 cases**, the real semantic reducer, one vault publication,
catalog activation and one simulated PAT application. Exactly one activation and
completion occur. Original-key replay, configuration-drift refusal and cold
vault/bridge history pass. Worker time is **47.915 seconds** under 60; launcher
elapsed time is **125.887 seconds** under the 180-second parent bound. One local
observation does not qualify deployment timing or establish a speedup.

The [actual audit](artifacts/verification/supervisor-storage-integration/ACTUAL_RESULTS.json)
verifies **4,270 files / 35,508,922 bytes**, the **268-file producer image**, all
**4,011 vault references / 2,798 bodies**, and the complete source, publication,
catalog and single-effect joins. It holds **58 original owner/writer files** and
opens only four parent databases in immutable read-only mode. No worker-case
database is opened. The version-3 binding matches original control/bulk root,
owner and manifest identities. Raw scratch and verified copies remain retained.

All **244 public runtime inputs** remain exact against the existing **866-test**
passing receipt; those tests were not repeated. The candidate remains isolated.
It establishes directory ownership/separation, not hard aggregate quotas, backed
control continuations, hot-journal recovery or complete filesystem/SQLite service
support. [Next work](artifacts/verification/supervisor-storage-integration/NEXT.md)
addresses the actual hierarchical namespace and remaining storage gates before
public mounting.

Unified device I/O, driver and hub control, prompt learning into deterministic
PATs, persistent MCU execution, concrete physical providers, microscope
commissioning, native Harness installation, remaining full-source research and
home/laboratory/manufacturing qualification remain required. Primary-agent review;
the original complete goal stays active.

''')
replace_between('docs/control-storage.md','The [explicit supervisor-binding candidate]','The [qualification-library installation]',
'''The [split supervisor integration](../artifacts/verification/supervisor-storage-integration/README.md)
passes 71 distinct controls and the complete original thirty-case simulated
qualification-to-PAT application against separate owned control and bulk roots.
Cold history works without opening bulk; fresh work and byte-dependent recovery
check its identity. The binding matches original root/owner/manifest objects.
One failed diagnostic batch is retained; remaining methods passed in separately
declared individual scopes. The complete actual scope kept its original limits.

This candidate remains isolated. The [source contract](../artifacts/verification/service-storage-contract/CONTRACT.md)
still requires a complete hierarchical namespace, SQLite temporary-file
confinement, capacity checks before recovery mutations, every-writer aggregate
enforcement and backed continuations. Sidecar refusal is not hot-journal recovery;
logical retention scans do not reserve capacity. The existing block-read profile's
54 semantic checks and 22 interruption cases remain separate evidence. All 244
public runtime inputs remain exact; physical providers and power loss are unqualified.

''')
replace_between('docs/io-driver-hub-control.md','The [supervisor storage-binding candidate]','The [qualification libraries]',
'''The [split supervisor integration](../artifacts/verification/supervisor-storage-integration/README.md)
now passes 71 distinct controls and the full thirty-case simulated qualification,
vault publication, catalog activation and one PAT application. The isolated
candidate separates control history from worker bulk storage and verifies its
owned binding. Original-key replay and configuration-drift refusal pass. Actual
I/O, driver/hub lifecycle providers, local outage behavior and physical stopping
still require implementation and qualification. Capacity/recovery gates remain;
all public runtime inputs are unchanged.

''')
