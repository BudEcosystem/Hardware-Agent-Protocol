# Bounded multi-manifest evidence snapshots

The isolated vault candidate passes **60 controls: 25 new batch methods, six
existing vault methods and all 29 business-commit methods**.
[Source](implementation01/README.md), [design](DESIGN.md),
[test receipt](harness01/attempts/attempt01/child-result.json) and
[read-only audit](RESULTS.json) are retained. The [harness prose correction](HARNESS-NOTE.md)
clarifies that four new methods join a batch view to Journal admission.

`snapshot_many` holds the exact requested manifest set in one read transaction.
It checks all associations and aggregate limits before fetching selected body
blobs, validates every selected body, and refuses the whole view if any member is
missing, conflicting or corrupt. It supports the full 32-manifest bound. Shared
immutable bodies reuse memory, while each reference still counts against the
logical budget. Detached access checks owner, thread, lease identity and expiry.

Real Journal controls verify complete-batch checks after admission writes, no
admission for a missing member, rollback when the batch expires at commit, and
original-key replay when lease cleanup fails after a successful commit. These
are storage/admission fixtures; no PAT catalog selection or qualification worker
executes. The existing single-snapshot methods and Journal source are unchanged.

The child runs all 60 methods in 19.962 seconds; its parent completes in 21.439
seconds within the 60-second bound. The read-only audit verifies 194 retained
files (2,976,200 bytes), 70 unchanged databases and 54 observation files under 70
original owner locks. Two intentionally corrupted bodies and one forged manifest
scope remain intact. All frozen source/dependency inputs are unchanged.

The public runtime is unchanged. Logical budgets are not heap measurements or
backed storage reservations. The new catalog must still bind this complete view
to exact publication references, current applicability and its commit check.
Actual complete-worker/catalog/application integration, learning and physical
providers remain unfinished. [Next work](NEXT.md).
