# Read-only retention scan evaluation

The prior original-worker diagnostic measured 18.454471 parent CPU seconds during
the approximately 60-second worker interval. This evaluation measures the exact
`tree_usage` function on that original, now-quiescent output tree. It does not
launch a worker, modify production, change scan frequency or relax any limit.

Extract the function, its exact exception/require helpers and the original harness
audit callback as AST from pinned source. Do not import project packages. Hold all
49 original owner/writer locks and verify raw root, attempt-directory and lease
identities before scanning. No case database is opened, read or recovered; only
directory metadata and zero-length lock descriptors are inspected. Control JSON
and copied source are read separately during preparation.

A common audit dispatcher permits only directory opens during measurements and
refuses process, network, database and filesystem mutation events. One comparison
mode additionally invokes the exact original Python audit callback; the other
omits that callback. Both include the same dispatcher overhead. This isolates
the callback's incremental cost here, not all interpreter or harness overhead.
The cooperative audit is not an OS security sandbox.

Run one fixed warm scan per mode and seven fixed alternating pairs of five scans.
Every scan must reproduce the original archive's 3,227 entries and 11,889,866
logical file bytes under its original 8,192-entry/64-MiB reservation limits. Record
CPU and monotonic elapsed times, observed audit event counts and original callback
violations. Before/after metadata must match, excluding access times which reads
can change. The original integration's failure and unknown effects remain intact.

The evaluation has a 60-second wall timer, 30 CPU-second limit and 16-MiB file
limit. It has no adaptive repetition. Results on the completed partial tree do
not reproduce a growing concurrent tree or identify the previous timeout's cause.
Use the observations to decide whether a scan implementation or harness callback
correction merits a separately verified candidate.
