Archived-data diagnosis of all four public I/O transport errors from the failed
focused37 attempt `20261107T005504.237197Z-360d486cb278`. The original attempt and
failure captures are unchanged. `inputs/` is its exact 151-file before snapshot;
`cases/` contains hash-checked copies of the four retained JSON database dumps,
capture records and reports. No daemon, Runtime or database was opened by this
probe, and no live project module was imported.

`diagnose.py` reconstructs the Runtime.operation/IoRouteAdapter.result projection
from each later retained terminal snapshot and calls the actual archived API
validator. These are reconstructed terminal projections, not a claim to have
captured the exact rejected wire body. Three completed operations and one
canceled operation all pass the JSON Schema shape. All four fail the precise
cross-field check requiring `type(output.get("effectCommitted")) is bool`.
`result.json` retains the exact envelopes, schema-error lists and validator
traceback source line. `output.log` records 4 schema-valid / 4 cross-field failures.

The I/O receipt intentionally separates `activationCommitted`, `cycleCompleted`
and `safeIdle`; cancellation can follow activation. Mapping activation to the
legacy field conflicts with its canceled/failed=false rule, while mapping cycle
completion would obscure the meaning of an already-started effect. The proposed
fix is an explicit `hms.synthetic-io-result/1` output profile with closed typed
activation/cycle/idle state checks. Existing unprofiled simulation behavior must
remain unchanged. Unknown explicit profiles must refuse. This diagnostic does
not implement or test that correction, change any timing, or claim physical
verification.
