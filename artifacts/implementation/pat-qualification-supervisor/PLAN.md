# Durable qualification attempt and process slice

Staging only. The main 643-test suite completed successfully before execution of
this stage is allowed. No old evidence stage or live source is changed.

The first implementation supplies a durable, single-flight attempt ledger and
an original isolated worker launcher. Catalog/evidence-store mounting remains
deferred: the worker can return failed/inconclusive with unknown unresolved
effects, the current evidence store accepts only complete passes, and the
catalog callback carrier has no direct unknown-effect result mapping. No zero
or successful result will be fabricated to bridge that gap.

## API and phases

Trusted setup chooses one protected root and immutable limits. The caller does
not supply a command, URL, import name, endpoint, authority object or physical
provider. `prepare_request(trust, limits)` validates the exact trusted worker
capsule and pins current supervisor/worker identities. An outer service must
lookup the run key before preparing a fresh capsule, so retries do not invent a
new attempt/session/input identity.

`AttemptLedger.admit(request)` persists a detached canonical request before any
spawn. Its immutable key is `(deployment, evaluatorId, runId)`; changed bytes
conflict. Exact existing keys return the retained attempt without launching.
One active attempt and bounded retained archive/reservation counts are enforced
per configured root. A future trusted Runtime configuration must fix this root;
this internal library cannot claim global single-flight across arbitrary roots.

`QualificationSupervisor.execute(request)` launches only a newly admitted row.
`status` and exact-key replay expose retained control facts. `recover(id)` is
explicit and cannot launch a replacement. The states are:

| State | Meaning |
|---|---|
| admitted | Immutable input committed; spawn not yet armed. |
| launching | Input/directories/lease identity durable; parent owns writer lease; launch intent committed. |
| running | Live parent owns a process handle and pidfd; child owns inherited writer lease. |
| stopping | A deadline/output/retention/stop veto is latched; termination requested, not confirmed. |
| interrupted | Ownership was lost or settlement is unconfirmed; active slot remains held. |
| archived | Writer quiescence established and bounded control/result records committed; success is not implied. |

The parent acquires the per-attempt writer lease before spawn and passes that
already-held FD to a fixed isolated Python entry. The child retains it until
exit. Its inode/device identity is stored with launch intent. The supervisor's
root owner lock and Journal/SQLite descriptors are never inherited. A private
code image contains exact original HMS sources plus the fixed entry/support
code; it is not selected by capsule data. The worker sees only the capsule,
attempt/output paths and deliberate control/lease FDs, with a minimal environment.

Live signaling uses the parent's pidfd, never a persisted bare PID. A reopened
supervisor does not reconstruct a kill target from a PID. A held or replaced/
missing armed lease is unresolved ownership and blocks recovery/import/new
attempts. Lease-free proves only that the trusted writer stopped. Recovery
preserves an unknown exit status; it never invents normal exit or zero effects.
A completed return found after owner loss may be archived for review, but it is
not automatically accepted for qualification when normal process completion
cannot be established. There is no same-run rerun in this first slice.

The worker receives an initially empty `attempt/output/` directory. Input,
lease, logs and `worker-return.json` live beside it. The fixed entry writes the
exact bounded canonical return to its own exclusive file and fsyncs it and the
directory. Parent collection reads stdout/stderr incrementally with strict byte
caps. Archive commit stores the exact bounded return bytes and digest in the
ledger as well as preserving files; path replacement cannot change a committed
replay. Referenced producer records are checked after writing has settled.
Missing/malformed/failed output and partial files remain retained.

## Deadlines and storage

Logical admission reserves a configured attempt budget before launch and keeps
reservations for unresolved writers. A bounded file-count/depth/byte scan and
bounded streams can trigger the watchdog. A child per-file resource limit may
bound individual files. These are not an aggregate filesystem quota or a hard
process termination guarantee. Signals may remain pending during kernel I/O;
writer settlement, not the signal call, releases the active slot. All results
retain `totalDiskQuotaEnforced=false`. Free-space observations are not storage
reservations. No quota configuration or privileged action is part of this stage.
No unresolved archive is deleted to recover capacity.

## Deferred service adapter

The future outer `qualify` must authorize and capture Registry/config snapshots
in a short Journal transaction, build/hash the capsule outside the transaction,
then reauthorize/recheck revisions and dependencies before attempt admission.
Source/config drift refuses; it must not relabel archived evidence.

After a normal complete archive, full reduction/import is a separate durable
phase. Existing EvidenceStore construction/import must occur under
`Journal._mutex` with no existing Journal transaction: those methods own BEGIN.
They still perform expensive full reduction; memo warming alone does not make
import cheap. Do not use the shared connection from an unguarded worker thread.
The memo's smaller capacity needs explicit admission/prewarming and final
eligibility rechecks; cold is unavailable, never novelty or an alternate match.

Only then should an outer serialized qualification call bind a one-use opaque
context-local token containing the exact deployment/evaluator/run/artifact/
environment/request/result association and invoke Catalog.evaluate. Its callback
must return only the immutable archived evaluator result, refuse absent or
reentrant tokens, and clear the token in finally. Do not invoke the catalog while
an attempt is pending/busy: callback exceptions currently consume a run key as
an inconclusive receipt. Direct generic catalog management for this evaluator
must remain unmounted until that boundary is reviewed.

A crash after committed evidence/archive import but before catalog commit must
reuse the same retained bytes, not rerun trials or normalize random IDs. Existing
catalog receipt hash/row association checks remain required. Failed/inconclusive
worker archives stay distinct and need an explicitly reviewed negative-result
mapping before catalog publication. Current qualification, persistent service
reconstruction, aggregate storage enforcement and public mounting are not
claimed by this process slice.
