# Individually bounded remaining diagnostic controls

The first batch experiment remains failed: four scopes passed 28 controls; the
fifth ended with SIGKILL at 41.5 seconds and has no child CPU receipt. Its cause
is not conclusively attributed. No original database is reopened or repaired.

This explicitly revised diagnostic profile runs the remaining 43 test identities
in separate fresh processes and fixtures, retaining all 28 complete passing
receipts. Source, assertions and child guard remain exact. Each process still has
60 seconds wall, 40 CPU, 512 MiB, 128 FDs, 16 MiB per file and 256 MiB scratch.
The total diagnostic budget increases; this is not a passing result for the
original fourteen-scope packing. Parent-observed child CPU deltas are recorded.
No unchanged batch retry occurs. A failing individual control stops this profile.

The required complete thirty-case worker, reducer, vault, catalog and one PAT
application retain their original joint scope, 60-second worker and 180-second
parent limits. They run only if all 71 diagnostic identities have complete
passing receipts. No production timing or physical qualification is inferred
from control batching. All raw and acquired failed evidence remains retained.
