# Independent supervisor review

[design-01.json](design-01.json) pins the existing interfaces and records the
owner's proposed ledger and process-ownership protocol before implementation
review. This was read-only work during the parent's full643 run. No tests,
worker or Runtime were executed, and no live or staged implementation was
edited.

The pre-spawn inherited writer lease closes the launch/recovery race. A free
lease proves only that the trusted writer has stopped; completed-result replay
still needs exact archived bytes and evidence validation. Process ownership,
archive import and catalog commit must remain separate recoverable phases.

The current catalog callback lacks a run ID and retains callback exceptions as
inconclusive evaluations. The current evidence reducer accepts only passed,
zero-unresolved worker results, and its import owns a potentially expensive
write transaction. These interfaces require an explicit later service adapter;
they must not be bridged by inventing zero unresolved effects or rerunning a
completed archive after a missing catalog commit.

Root approved deferring service mounting. Logical retention reservations,
bounded collection and watchdog termination are useful components, but
`totalDiskQuotaEnforced` must remain false. A hard aggregate filesystem quota
and its storage-admission protocol remain outstanding.

The implementation review is pending. This record does not approve an
implementation, attest a physical outcome or establish a sandbox.
