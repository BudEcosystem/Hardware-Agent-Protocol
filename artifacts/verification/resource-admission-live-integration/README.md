# Live resource-admission integration proof

The final focused run passed **32 tests**, with no failures, errors or skips:
87.904 seconds in unittest and 88.594 seconds in the retaining harness.
Its 140 captured inputs (139 shared project inputs plus this lane's runner)
and compiler identity stayed unchanged. All tested HMS imports came from the
copied current source tree. No Runtime, endpoint or simulation-worker module
was imported by these tests.

The implementation ports the reviewed resource catalog and Registry seam,
then fixes two independently retained problems. New resource-table reads and
the catalog's historical-binding reads check SQL storage type and byte size
before fetching values into Python. Point reads have finite cardinality, and
route/instance inventories must exactly match their immutable configuration.
The binding validator also preserves supplied scalar types, so an invalid
`maxLength: 1.0` remains invalid after the transaction-body extraction.

The proof retains three distinct executions:

| Execution | Actual result | Scope |
| --- | --- | --- |
| `attempts/20261107T000451.320019Z-before-6fb5090ce25e` | 5 methods, 48 subtest failures, 0 errors | Staged-equivalent code fetched damaged values into Python, accepted a noninteger token revision and ignored extra inventory rows. |
| `legacy-scalar-before` | 1 test, 1 failure, 0 errors | Exact original Registry refused an integral-float bound that the staged extraction accepted. |
| `attempts/20261107T001032.614975Z-after-c86700179e92` | 32 tests passed | Original 26 admission tests plus five bounded-storage tests and the scalar-compatibility regression. |

Before/after source copies, compiler manifests, actual test logs, SQL traces,
row-factory observations and per-test authority backups remain intact. The
failed runs remain failures. The earlier compiler manifests predate the
separate extensionless-schema-resource identity fix; the final run includes
that corrected current identity. Stability is scoped to each retained run.

Normal tests import live `hms` modules and the existing normal topology-test
helpers. The only historical implementation import is the exact pinned original
Registry fixture at `tests/fixtures/registry-before-resource-roots/hms/registry.py`.
Its TD schema occupies its real relative path. The test bounds and checks both
files before executing the original source; it does not rewrite `__file__`,
import a staged implementation or claim a complete old Runtime binary.

The [independent root review](../resource-admission-live-review/review.json)
found no blocker against the final pins. It was read-only and recorded the
focused run as pending at its own review time; this proof records the later
terminal result without altering that review.

This is admission and quiescent configuration publication, not provider or
lifecycle execution. The tests use a controllable clock. Host-fetch bounds do
not establish SQLite internal memory/time bounds, native-clock availability,
authority-lock latency or a global history-retention quota. Unrelated legacy
Registry/Journal reads were not redesigned. No Runtime/public provider mounting,
physical qualification or full-suite pass is claimed here; the parent-owned
696-test run was pending when this focused proof was sealed.

`index.json` hashes every retained file except `__pycache__` files and the index
itself, using workspace-relative paths. It verifies both snapshots of each
focused run, the scalar-before tree, compiler pairs, runner pins and final-source
equality at sealing. No attempt payload was rewritten while sealing.
