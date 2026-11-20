# Next implementation decision

The two profiles identify repeated serialization and installation/runtime setup,
plus a costly parent tree scan. Cumulative function times overlap and cannot be
added. Instrumentation changes timing; neither profile establishes the precise
cause of the earlier uninstrumented deadline failures or a deployment benchmark.

Start the next implementation from the uninstrumented recovery source index
`d1c5ac0d86c77bd195ffebfcf75dc6e1c95ecf7a0814416073cfba691fb5685c`.
Do not carry the worker diagnostic SIGTERM handler into the candidate.

First investigate a bounded memo for the pure installation-normalization result.
The worker profile observes 71 calls in its partial run, taking 6.054 profiled
seconds; this function contains no authority-database query or device effect.
A proposed memo may reuse only a previously validated exact bounded canonical
input under unchanged validation dependencies and current implementation identity.
It must retain immutable bytes, return detached data, and refuse oversized,
unsupported-type or float-bearing original inputs before a lookup can erase their
distinction. Current source identity must still be recomputed on every call.
Validator/helper changes must invalidate hits and prevent publication if they
change during validation. Invalid inputs must never publish a cached result.
No current permissions, bindings, generations, sessions, database reads, source
identity, effect check or receipt may be cached by this optimization.

This is a design candidate, not approved implementation evidence. Establish exact
error/type/boundary behavior, mutation isolation, dependency invalidation and fixed
entry/byte limits before selecting it. If those invariants cannot be established,
keep the original path. Prefer eliminating duplicate pure work over reducing scan
frequency, raising deadlines, changing page persistence or bypassing validation.
Do not change the general JCS encoder based on this partial profile alone.

Then run the unchanged 171 control selection with focused new cache tests, followed
by uninstrumented PWM and archive-commit cases and the existing worker/owner-loss
cases that the change can affect. Keep all original failures and logical keys.
A new passing diagnostic fixture does not repair an old attempt or prove reliable
nominal performance. Public qualification, hard quotas, trusted service mounting,
PAT learning, persistent applications and real device/driver/hub providers remain.
