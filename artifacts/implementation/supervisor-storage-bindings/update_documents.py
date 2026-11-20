"""Replace current status paragraphs; preserve earlier stage records."""
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
def replace_between(name,start,end,body):
    p=ROOT/name;s=p.read_text();left=s.index(start);right=s.index(end,left)
    p.write_text(s[:left]+body+s[right:])

replace_between('README.md','The [actual service storage contract]','The [PAT foundation]',
'''The [supervisor storage-binding candidate](artifacts/implementation/supervisor-storage-bindings/README.md)
adds separate owned control and bulk roots, including image, launch, retention and
archive consumers. Its read-only import inspection passes, but validation remains
incomplete: the first control test rejected the harness's scratch ancestry before
opening SQLite. The failure is retained; no worker or PAT application ran and no
shared permissions changed. All 244 public runtime inputs remain exact. Complete
storage qualification and physical providers remain unfinished. Device I/O,
drivers and the intelligence hub remain one
[managed resource graph](docs/io-driver-hub-control.md).

''')
replace_between('PROGRESS.md','Status: **active, incomplete','## Earlier continuation: qualification libraries installed',
'''Status: **active, incomplete — explicit supervisor storage bindings authored;
validation stopped at a harness placement error**. The preceding source assessment
identified shared control/bulk consumers and remains sealed with all 146 files
verified. The new candidate is isolated from the public runtime.

The [candidate](artifacts/implementation/supervisor-storage-bindings/README.md)
adds a version-3 control ledger bound to distinct owned control and bulk roots.
Control-only startup/history are designed to leave bulk unopened. Fresh admission,
code images, launch, archive reading and recovery requiring producer bytes check
the bound bulk objects. Legacy ledger profiles, attempt keys, durable handoff and
inherited writer leases retain their contracts. Sidecars requiring unqualified
automatic SQLite recovery are refused before opening the new-profile database.
Hard quotas, backed control capacity and hot-journal recovery are not implemented.

The 309-file project is frozen in a 312-file source index. Five existing production
files change and one module is added; two original tests change only computed
identity literals. A read-only import inspection passes and verifies a 268-file
producer image. Its initial missing dependency-path failure and the preparation
script's incorrect expected test filename are both retained explicitly.

**One of 71 selected controls started and errored; zero passed.** The runner placed
scratch below non-sticky group-writable workspace ancestors. The unchanged
`private_state_directory` guard rejected it with `UNSAFE_STATE_ANCESTOR` before
SQLite opened. Seventy controls remain unrun. No split ledger, diagnostic child,
qualification worker, evidence import or PAT application ran. No experimental
retry, widened limit or shared-ancestor chmod followed.

The [audit](artifacts/implementation/supervisor-storage-bindings/AUDIT.json)
verifies the exact failed project, retained result, empty scratch file inventory,
ancestor metadata, terminated parent and all **244 unchanged public runtime
inputs**. The existing **866-test** public passing receipt remains the baseline;
those tests were not repeated and do not validate this candidate.

[Next work](artifacts/implementation/supervisor-storage-bindings/NEXT.md) prepares
a separately identified harness with fresh private scratch below the reviewed
sticky `/tmp` ancestor, preserving all original limits and failed evidence. All
71 controls and then the complete original thirty-case workflow still require
execution. Full filesystem/SQLite qualification and backed continuations remain.

Device I/O, driver and hub control, natural-language learning into deterministic
PATs, persistent MCU execution, physical providers, microscope commissioning,
Harness installation, remaining research and home/laboratory/manufacturing
qualification remain in scope. Primary-agent review only; the complete goal is
active and incomplete.

''')
replace_between('docs/control-storage.md','The [actual service contract]','The [qualification-library installation]',
'''The [explicit supervisor-binding candidate](../artifacts/implementation/supervisor-storage-bindings/README.md)
separates control records from code images and worker output through a versioned
owned-root binding. Control startup/history are designed to avoid bulk access;
new work and byte-dependent recovery verify its identity. New-profile sidecars
are refused before SQLite opens. The candidate remains unvalidated: the first
control test rejected the harness's scratch ancestry before database creation.
The failure is retained, with no retry, worker launch or shared-directory chmod.

The [source contract](../artifacts/verification/service-storage-contract/CONTRACT.md)
still requires a complete filesystem namespace, SQLite temporary-file confinement,
pre-recovery capacity checks, every-writer enforcement and backed continuations.
The [block-read profile](../artifacts/verification/chunk-block-read-regressions/README.md)
retains its 54 semantic checks and 22 passing interruption cases. These do not
validate the new supervisor profile or reserve capacity. All 244 public runtime
inputs remain unchanged; physical power loss and actual providers are untested.

''')
replace_between('docs/io-driver-hub-control.md','The [service storage contract]','The [qualification libraries]',
'''The [supervisor storage-binding candidate](../artifacts/implementation/supervisor-storage-bindings/README.md)
addresses one dependency in this graph: control history must remain accessible
when code-image and worker-output storage is unavailable. It adds explicit owned
roots but remains unvalidated. The first control check rejected the harness's
scratch ancestry before SQLite opened; no worker ran. Actual I/O, driver/hub
lifecycle providers, local outage behavior and physical stopping still require
implementation and qualification. All public runtime inputs remain unchanged.

''')
