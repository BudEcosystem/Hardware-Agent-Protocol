# Isolated pending-recovery46 runtime harness

Run the original 38 capture tests plus eight new pending-output recovery cases.
See [scope](SCOPE.md), [selection](targets.json) and [index](index.json). The
46 workspaces contain 45 engines/90 databases; 26 methods retain configuration.
Trusted fault/authority plans and actual injection identities/counts are compared
against the reviewed selection. Original 600-second/64 MiB scratch bounds and
exact per-test SQLite scope remain unchanged. Preparation and source review
precede execution; actual results are separate. Helper review is unavailable.
