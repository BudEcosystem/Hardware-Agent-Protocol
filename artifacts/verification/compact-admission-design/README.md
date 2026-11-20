# Proposed bounded freshness acquisition for fresh invoke

Status: read-only proposal, not implemented or tested as runtime behavior. The
four preserved mechanism probes are in `../compact-availability-before/`.

The avoidable problem is a fresh request reaching admission after another route
has consumed the target's presence lifetime. The unavoidable limit is that a
new sample can itself expire during publication. Keep the existing 1000 ms TTL,
original acquisition ticks, operation key, namespace and absolute deadlines.

## Entry point and replay order

Use an internal Runtime fresh-submit wrapper for the existing `invoke` method.
Do not add a client-accessible raw refresh API, call `tick`, or put transport I/O
inside a Journal transaction/policy callback. Start with ordinary `Journal.submit`.
That existing path checks the retained namespace/key before sampling current time
or checking live state. Exact retained operations, including accepted, terminal
and outcome-unknown operations, return their existing identity; conflicts and
invalid namespaces retain their existing refusal behavior without route I/O.

Only a narrow internal `PresenceAgeExpired` exception may enter the recovery
path. Preserve its wire code `DEVICE_UNAVAILABLE`. It must mean all of:

- A current row exists for the same installed adapter and endpoint session.
- Current binding generation, description, calibration and control match.
- Existing static policy validation (`validate_bound`, live=False) has checked
  the caller's general invoke, action invoke and read grants, input arguments,
  resource mapping and installed capability support.
- The known expiry is at or before the authoritative admission sample.
- The original submit has exited its transaction without any operation,
  claim, replay-key, command or procedure-child allocation.

Missing presence, mismatched sessions, offline/faulted routes, unknown clocks,
inactive bindings, invalid evidence, false semantic preconditions and authority
errors must not be converted to this signal. In particular the current generic
`DEVICE_UNAVAILABLE` covers more than a known expired row and is insufficient.

## Locking and one observation attempt

After the first failed transaction, acquire the selected route lock, then the
Journal mutex, in that order. Do not acquire a route lock while retaining the
Journal mutex from a caller. Recheck the immutable request by running ordinary
`Journal.submit` again under those locks. This deliberately reuses its exact
replay, current namespace, manager guard, expiry and authority rules instead of
duplicating them in a second admission implementation. A concurrent submit,
revocation or renewal during lock acquisition is then handled normally.

If that recheck again yields the narrowly qualified expired-presence exception,
require the same already installed, catalog-ready compact backend: non-null
stream, installed flag, boot and desired context; no fault; exact same binding
and session. Call one explicit observation-only refresh, with `initialize=False`.
Never initialize/enroll/provision, BIND, ARM, allocate an endpoint command, call
adapter `tick`, or reconcile/resend work as part of this path. A small dedicated
backend method enforcing these preconditions is clearer than an unrestricted
refresh hook. Existing installed compact refresh sends HELLO; its failure may
withdraw authority. It must never grant caller permissions.

After refresh, submit the same canonical request through ordinary Journal
admission while retaining both locks. There is no second refresh or loop. Any
remaining expired presence/observation, semantic refusal, identity change,
namespace expiry or deadline crossing propagates. This is at most one new HELLO
observation attempt, not a guaranteed wall-clock bound on storage or mutex waits.
No new clock sample may restamp the old HELLO or extend the supplied deadlines.

The extra checked submit transaction is a deliberate correctness cost: it avoids
reimplementing replay/freshness classification and proves absence of an allocated
operation before I/O. A later optimization must preserve those same decisions.

## Existing paths that need separate treatment

`prepare` currently calls `describe`, which hides expired presence, before it
constructs a bound request. It is not admission and can be called with a retained
operation key. Do not automatically apply this invoke wrapper there: a distinct
design must preserve its no-allocation result and handle existing-key semantics.
The proven failed-459 request had already been prepared, so fresh invoke is the
narrow first repair target.

`ProcedureStore.tick` in the pinned baseline holds the Journal mutex while
selecting and submitting children. Calling this route-locking wrapper there
would invert the established lock order. Procedure integration requires selecting
an immutable candidate, releasing the mutex, then entering the wrapper with the
managed parent/step token; the existing submission guard must recheck cancellation,
interruption, cursor, dependency and deadline after reacquisition. Do not replace
that guard with the earlier selection. This is a separate coordinated change.

An active endpoint can independently finish previously authorized work as time
passes. The new path promises no new execution authority, no OP/ARM/BIND and no
dispatch of the candidate. It must not claim that a HELLO freezes all preexisting
endpoint activity. For the empty-route native fixture, counters can and should
prove zero dispatch/effects before and after refresh.

## Acceptance evidence required before merging

1. Reproduce the frozen cross-route expiry with unchanged timing. Existing invoke
   succeeds after exactly one target HELLO; unrelated route packet counts do not
   change; no OP/ARM/BIND, dispatch/effect counter or grant/binding mutation occurs
   during refresh. Ordinary later dispatch still sends one OP for the child.
2. Exact retained replay in accepted, terminal and outcome-unknown states performs
   no refresh and returns the original identity even when live presence or wall
   namespace time has expired. Conflicts, pruned/invalid namespaces and managed
   reserved-key conflicts perform no refresh and allocate nothing.
3. Missing/mismatched presence, invalid binding/arguments, absent invoke/read/action
   grant, unavailable or faulted route, and unsupported capability send no HELLO.
   Verify revoked authorization while waiting for the route lock is rechecked.
4. A concurrent same-key admission while waiting returns that retained operation
   without refresh; a concurrent conflict retains conflict behavior. Use bounded
   thread barriers and exact packet/count assertions, not timing sleeps.
5. Deadline or namespace expiry during the refresh refuses the original request
   without allocation. Delayed final publication reproduces the frozen refusal;
   no retry loop, TTL extension or restamped ready observation appears.
6. Restart never refreshes an old retained/unknown handoff on replay. Caller bytes
   are snapshotted once, including aliases, and every attempted submit uses the
   same canonical request. Existing event and managed-child atomic links remain.
7. If prepare or procedure integration is later included, add explicit tests for
   their separate no-allocation/managed-guard behavior and lock-order races.

The proposal improves one demonstrated availability mechanism. It does not
attribute the earlier failed full run to that mechanism and does not guarantee
that finite freshness survives arbitrary storage or scheduling delay.
