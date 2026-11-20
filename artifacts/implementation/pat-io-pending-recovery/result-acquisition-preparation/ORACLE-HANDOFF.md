# Required independent recovery-history extension

This is a source-review handoff, not implemented recovery semantics or an
execution result. The current authorized-history candidate deliberately refuses
an unknown authority outcome with a pending board receipt. Actual recovery46
results must be acquired before new fixtures or positive claims are created.

## Trust and input boundary

Keep trusted installation/PAT setup, the authority/grant plan and the fault plan
separate from untrusted captured streams. The fault plan uses
`hms.pat.io-trusted-fault-plan/0.1`, a closed `faults` list with at most sixteen
entries, unique increasing integer phases within the existing 2,048-tick ceiling,
the exact `drive:adapters` label, one occurrence per entry, and the named point,
exception and code combinations below. Do not infer the expected fault plan from
captured exception messages, `injectedFaults`, board reason strings or outcomes.
Retained injection summaries are producer claims to compare, not authority.

| Point | Expected code | Required phase result |
| --- | --- | --- |
| `board.begin.after_commit` | `injected:io_begin_reply_loss` | Engine call returns; accepted child becomes unknown; board has pending sequence 1 and active ownership; authority has no receipt |
| `board.finish.before_commit` | `injected:io_finish_before_commit` | Engine call fails; board tables and authority claims remain unchanged; running child becomes unknown, or already unknown child stays unchanged |
| `journal.reconcile.before_commit` | `injected:io_recovery_authority_reply_loss` | Engine call fails; authority operation/events/claims remain unchanged; a pending board receipt has already stopped, or an existing terminal receipt stays unchanged |

All named failures are `JournalError`. Every scheduled fault must be consumed by
one matching phase and one independently identified eligible operation. Reject
unknown points/codes, missing or duplicate phases, unused schedules, changed
occurrence counts and unplanned call failures. A missing reply and a failed stop
must not become interchangeable allowances.

## State obligations

Join configurations and exact call/checkpoint pairs before evaluating faults.
Continue to validate immutable bindings, current sessions and fresh after-phase
observations. Preserve explicit read permission during invocation withdrawal;
full read withdrawal remains unsupported by the current report profile.

For every newly observed `outcome_unknown` event, independently identify its first
checkpoint, prior operation and scheduled fault. Begin reply loss permits only
`io_acceptance_unknown`; a failed finish of a running child permits only
`io_completion_unknown`. A failed finish/reconciliation of an already unknown
child must not append a second unknown event. The operation-history fold still
checks complete event ordering, identities, claims and evidence; this extension
must not replace it with checks of final summaries.

A begin-reply-loss case requires an accepted pre-phase child with no board
receipt, then one pending receipt linked to the same dispatch/attempt, original
intent, claims, session and installation. The authority has no receipt for that
operation yet. The existing independent board and operation reducers must verify
the activation, active states, floors, owner and event transitions.

A before-finish failure requires a pending pre-phase receipt and a running or
unknown authority operation. Compare all seven board tables across the phase:
none may change. The exact authority claim set must remain. An already unknown
operation and its events must also remain unchanged. Refresh observations may
change; that does not establish device progress.

On a later adapter phase, an unknown operation with a pending receipt must stop
with `reconciliation_stop` before any ordinary completion/permission guard. This
precedence holds at due time, after invocation withdrawal and after a client
cancel request. It does not confirm that client cancellation caused the stop.
A specifically scheduled before-finish failure may leave the board pending for
that failed phase only; the next unfailed recovery phase must establish the stop.

A reconciliation-before-commit failure permits terminal board evidence while
the authority remains unknown and holds its original claims. It cannot justify
a still-pending board receipt after a successful recovery stop. A subsequent
unfailed phase must settle the existing terminal receipt and release claims;
it cannot reactivate the output or rewrite the receipt's historical cause.

Derive the expected settled authority state from that receipt: completed stays
completed; client/owner cancellation stays canceled; a recovery stop settles as
failed. Parent cancellation and child cancellation remain distinct. Require
authority settlement/release on an unfailed recovery phase, rather than merely
allowing arbitrary lack of progress that an event-validity check would tolerate.

## Composition boundary and tests

Prefer a private validated interruption map keyed by checkpoint record and
operation. The existing guard checker may consume it for a failed before-finish
phase or a pending-unknown recovery phase; ordinary public inspection must retain
its existing refusal without the new trusted-fault validation. Every private map
entry must be consumed exactly once. The board reducer can accept
`reconciliation_stop` only through this joined cause proof, and its public API
must still refuse an unjoined cause. Do not rewrite evidence to make a legacy
checker accept it.

Compose independent PAT correspondence, configuration, guard/cause, board,
operation and parent reductions over the same unchanged records. Add attacks
that rehash inner receipts and outer pages: omitted/reordered/untrusted fault
plans; wrong return/error; fabricated unknown cause; lost activation; hidden or
early-released claims; changed state during a failed stop; completion instead of
recovery stop; relabeled client-cancel cause; repeated activation; unchanged
unknown state after an unfailed recovery; missing authority receipt; wrong parent
projection. Include input immutability, I/O veto and import-closure checks.

Use actual acquired recovery46 fixtures and retain their provenance. Existing
authorized103 and board regressions remain required for changed readers; select
bounded isolated runs without widening the original execution or evidence bounds.
No physical-stop, current-source attestation, complete fault-matrix, aggregate
storage, public qualification or automatic-promotion claim follows from this
extension. Reopen/clock-loss and auxiliary actors still require their own trusted
profiles and complete evidence.
