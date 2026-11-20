# Whole-domain timing and independent finite I/O outcomes

Status: source-only design against the 19 pinned files in [inputs.json](inputs.json).
No timing evaluator, I/O qualification worker or I/O evidence reducer is implemented
by this document. The isolated compiler's fixed-unit support and the isolated
trusted I/O resolver supply prerequisites; neither is integrated into the live
runtime. Historical source and result references remain unchanged.

## Scope and eligibility

Continue the proposed `hms.pat.eval.sqlite-finite-io-sequence/0.1` policy with
distinct I/O contract, matrix, worker, evidence and trust profiles. Preserve the
fan policy and all its historical identities. One eligible PAT has one role, one
installed action and 1..16 ordered steps. Trusted normalized installation data
must associate that action with exactly one primitive, `gpio_pulse` or `pwm_burst`.
Action names alone do not determine semantics. Require the exact source identity,
installation, resource proof, binding, semantic registration and simulation mode
selected by `IoRegistryPatBindings`.

Only integer literals and direct integer parameter references are eligible.
Validate the complete declared domains, including sparse enums, against both
the type and binding schemas before applying static applicability predicates.
Reject bools and integral floats as integers. At most two declared parameters may
vary; singleton parameters still consume the existing parameter and matrix bounds.
Require exact trusted units: level `1`, duration `ms`, frequency `Hz`, duty
`permille`, resolution `bit`; frames are null. Preserve the installed timer's
frequency envelope and fixed resolution. No inferred units or conversions.

The initial policy covers finite output cycles. Sensor feedback, persistent
controllers, streams, arbitrary expressions, branches, mixed primitives,
driver/service mutations, hub jobs and physical outcomes need their own contracts.
Their absence from this increment does not remove them from the system's required
scope. The [device/driver/hub architecture](../../../docs/io-driver-hub-control.md)
continues to describe those domains.

## Three separate timing claims

1. **Static compatibility:** every advertised duration and argument fits the
   installed primitive and its unchanged bounds.
2. **Constructive simulation schedule:** every declared input fits a particular,
   explicit virtual-clock execution policy, with early admission and lease expiry
   included. This is a sufficient check; conservative rejection is permitted.
3. **Observed trial outcome:** the actual original simulator, authority and
   procedure manager produced consistent retained evidence at recorded times.

Passing the first two does not replace the third. Finite trials do not exhaustively
prove behavior across a parameter range, and virtual-clock success does not
establish a host scheduling bound or electrical behavior.

The existing action permits duration up to 5000 ms, but `begin` requires
`startedMonoMs + durationMs < budgetOriginMonoMs + maxRunMs`. With the current
maximum run budget of 5000 ms, duration 5000 can never start. Do not trim a declared
domain, widen a run budget, or treat applicability as a repair for this mismatch.
Even a smaller duration can fail after dispatch/guard delay consumes its slack.

## Closed virtual-clock policy and whole-domain recurrence

Use a new, identity-bound clock policy, proposed as
`hms.pat.io-clock.zero-latency/0.1`. During ordinary successful trials wall and
monotonic clocks advance together by integer milliseconds; both remain constant
through each synchronous refresh, admission, dispatch, guard, board transaction,
settlement and procedure-progress phase. Admission, dispatch, guard, polling and
settlement lags are explicitly zero in virtual time. This does not assert that
those functions take zero real time. An outer worker deadline remains necessary.
Other lag models require a new reviewed policy, not a caller-supplied override.

At each virtual time, drain bounded durable progress before advancing the clock.
Admission may happen before a child's `notBefore`: the current procedure manager
checks the parent's lower bound, and Journal submission does not wait for the
child's lower bound. Claims and a lease already exist during that wait. Dispatch
does enforce the child's lower bound. The current Registry grants a lease ending
at `min(childCompletion, admission + 60000)`.

Use offsets from the compiler's origin. For step i let `n[i]`, `s[i]`, `c[i]` and
`r[i]` be its not-before, exclusive latest-start, exclusive latest-completion and
run budget. Obtain `dLo[i]` and `dHi[i]` from the literal or the complete declared
duration domain, using the actual enum extrema when present. Never enumerate an
unbounded integer range to compute these values. Let `P` be the parent's exclusive
completion bound and `PS` its exclusive latest-start bound.

```
aLo[0] = aHi[0] = 0
startLo[i] = max(aLo[i], n[i])
startHi[i] = max(aHi[i], n[i])
finishLo[i] = startLo[i] + dLo[i]
finishHi[i] = startHi[i] + dHi[i]
aLo[i+1] = finishLo[i]
aHi[i+1] = finishHi[i]
```

Require all additions and absolute-origin conversions to remain within the exact
integer bounds. Existing PAT syntax, sum-of-run-budget checks and caller deadline
checks still apply. In addition require, for every step:

```
1 <= dLo[i] <= dHi[i] < r[i] <= installedActionMaxRunMs
startHi[i] < s[i]
finishHi[i] < c[i]
finishHi[i] < aLo[i] + 60000
finishHi[i] < P
```

Also require `aHi[0] < PS`; the existing grammar already places the first child's
latest-start at or before `PS`. Duration is positive, so these completion tests
also keep admission and dispatch before the relevant lease/completion bounds.
The range recurrence encloses every declared input. The lease comparison uses
the earliest possible admission with the latest possible finish, deliberately
overapproximating correlations when a parameter is reused. A candidate may be
rejected even if a more precise correlated analysis could accept it. Report that
as unsupported by this sufficient policy; do not call it physically impossible.

This rule is specifically tied to zero virtual lags. A delayed-start challenge
must separately check `start - budgetOrigin + duration < runBudget`; a delayed
finish must occur strictly before run, wall-completion and lease limits. Equality
is refusal/cancellation at those upper bounds. `notBefore` equality is allowed;
reaching `dueMonoMs` equality permits completion if all upper-bound guards pass.

For example, duration 4999 and run budget 5000 can pass the static duration rule
with zero start delay, but one millisecond of start delay excludes activation.
A child admitted at offset 0, starting at 59999 for duration 1, reaches its lease
at 60000 and cannot qualify. Moving its start to 59998 can fit that lease if the
other windows allow it. A domain containing both 4999 and 5000 is rejected before
applicability, even if applicability selects only 4999. These are design examples,
not executed test results.

The actual worker must match the schedule. Compute the next event from retained
accepted-operation timing and pending I/O receipts, including lease, completion
and run boundaries. Never use the fan backend's `_pending` value shape: the I/O
adapter stores dispatch tickets there, not due-time records. Include the parent
deadline and child not-before events. At a fixed time, bound progress by changes
to durable procedure/operation/receipt state, not by fresh observation counters;
refresh traffic alone must not prevent termination. Refuse a stalled or exhausted
scheduler instead of advancing blindly past a required phase.

## Matrix and adversarial schedule coverage

After whole-domain validation, intersect the supported static applicability
predicates using interval arithmetic and bounded enum filtering. Refuse empty
applicability and unsupported predicate combinations. Preserve enum holes. Generate
nominal and low/nominal/high Cartesian boundary cases over the at most two varying
axes, with typed deduplication. Add explicit invalid type, below/above domain,
enum-hole, missing/extra argument and wrong-context cases. Do not fill holes or
silently truncate a matrix to meet a quota.

Separate policy-refusal vectors from runnable qualification trials. Invalid
artifact domains, the duration/run equality and an impossible sequential window
must fail before the worker receives an executable qualification request. Runtime
fault trials use an otherwise eligible program and a named trusted interruption
or clock schedule. A fault trial passes only by establishing its specified refusal,
cancellation or historical-reconciliation outcome; it does not make that failed
execution a successful PAT completion.

Plan these schedule boundaries explicitly:

| Boundary | Required check |
| --- | --- |
| Just before / at not-before | No early handoff; equality can start |
| Just before / at latest-start | Exclusive upper bound; no activation at equality |
| Due before / at run limit | Exact run equality excludes a start; late completion cancels |
| Due before / at wall-completion | Completion guard runs before due-time success |
| Long wait after early admission | Lease can expire while the child still holds accepted claims |
| Sequential next step | Admission follows successful predecessor settlement at the same virtual time |
| Reused duration parameter / sparse enum | Whole-domain bound is preserved without range enumeration |
| Deadline after provider completion | Historical completion remains true even if parent reporting is late |
| Clock regression or epoch mismatch | No continuation under an invalid clock mapping |

Ordinary qualifying trials require final parent reporting before `P` under the
defined scheduler. The procedure manager currently reconciles a fully successful
prefix to parent completion before checking the parent deadline. Therefore a
later read of an already completed cycle is not evidence that the physical/simulated
cycle ran late. Keep a delayed-reporting fault separate from successful on-time
qualification and preserve the original child completion truth.

## Raw evidence for an independent reducer

Use a separate pure reducer for I/O; shared parsing and compilation are acceptable,
but do not delegate outcome checks to `SyntheticIoBoard._validate_state`,
`_active_state`, adapter projections or the fan outcome reducer. Import no worker
into the reducer. A worker `passed` flag is a claim to verify, not the oracle.

Each trial starts from a new private installation and full board, not copied user
state. Retain canonical raw rows in closed, typed records and acquire logical
database backups at terminal/failure boundaries. Bind pages to exact trial,
checkpoint, table, row count, canonical ordering and content digest. Every table
has an explicit expected inventory; bounded pagination must reject gaps, overlaps,
duplicates, missing tables and extra rows. Preserve scalar types and original
canonical document bytes with their stored hashes. Do not manufacture missing
evidence from summaries.

Required evidence includes:

- Full trusted installation, topology, routes, handler map, generation snapshot,
  scoped proof, type/binding and explicit semantic registration; actual authority,
  session, owner epoch and clock mapping. Preserve both the source environment
  and the worker's fresh session binding, with an explicit checked correspondence.
- Board `io_meta`, `io_resources`, `io_owners`, `io_fences`, `io_effects`, latest
  `io_receipts` and every `io_receipt_versions` row.
- Authority operations, admission records, `claims`, `resource_floors`, namespaces,
  `replay_keys`, `io_dispatch_links`, `io_authority_receipts`, procedure rows,
  reserved keys and step links, plus complete bounded operation/procedure events.
- Exact requests and returned success/error values for initial submission,
  same-key replay, conflicting-key refusal and cancellation. Preserve unresolved
  calls as such; do not infer a response from the eventual database state.
- Before/after phase records with wall and monotonic time, clock epoch and the
  identities of calls and snapshots. Pending-to-terminal board receipts have no
  completion timestamp field; these phase records are needed to place the actual
  board transaction in the controlled virtual schedule. An authority completion
  event alone may be later than the board effect.

Checkpoint labels must identify baseline, admitted/unstarted, pending, provider
terminal before authority settlement where injected, settled, replay and reopen
boundaries as applicable. Retain the exact operation/receipt identities across
each cut. A quiescent worker owns both databases during capture; preserve evidence
if capture or close fails, and do not claim an atomic cross-database snapshot from
uncoordinated copies.

The reducer derives GPIO and PWM footprints directly from the typed access,
pin/timer/channel and atom relations in the trusted topology; checks alias
expansions against those footprints; and compares claims with the retained proof.
Dependency identity and exclusive ownership are separate: containment or a driver
dependency does not automatically add an ordinary output claim. Keep the complete
inventory, including unaffected instances and atoms, in the comparison.

Independently derive idle states: pins high impedance with null level; timers
disabled with zero frequency/resolution; channels disabled with zero duty.
Derive active states from the primitive and exact arguments: GPIO pin in push-pull
mode with requested level; PWM pin in PWM mode with null level, enabled timer with
requested frequency/resolution and enabled channel with requested duty. No claim
about voltage, pulse shape or measured frequency follows from these model states.

## Independent transition and ownership rules

| Durable provider result | Activation | Completed cycle | Established idle | Versions |
| --- | --- | --- | --- | --- |
| No handoff; accepted operation canceled | 0 | 0 | Baseline unchanged | None |
| Guarded start excluded | 0 | 0 | True | Sequence 1 only; all receipt times null |
| Pending | 1 | 0 | False | Sequence 1 |
| Completed | 1 | 1 | True | Sequence 1 then sequence 2 |
| Canceled after activation | 1 | 0 | True | Sequence 1 then sequence 2 |

Join every receipt to exact operation intent/digest, claims/fences, dispatch link,
attempt, adapter, authority, installation, endpoint session and owner/clock epoch.
Sequence 2 must preserve all immutable sequence-1 fields and change only sequence,
state and result. Reject replacement of a no-start receipt by a started receipt,
missing predecessors, extra versions, mismatching latest rows, wrong hashes and
authority snapshots that differ from the corresponding board version.

For started work, require `budgetOrigin <= started`, `due = started + duration`,
and the strict start budget inequality. Use the recorded controlled-clock phase
to establish that a completed cycle reached due while its completion/run/lease
guards still permitted completion. Canceled work may stop before due or after an
upper bound; the reason and injection must agree with the transcript. Never count
an activation followed by cancellation as zero effects.

At each checkpoint derive activation/completion/cancellation counts from retained
receipt histories for every instance, not from observation `value`. Require
`activations = completed + canceled + pending`, exact baseline deltas, and no
unexplained increment. Current board owners are exactly the claims of pending
receipts; no overlaps. Active resources match those owners' derived states and
all other resources are idle. Fences persist after owners are removed and may
refer to a later operation on the same atom; historical receipts do not require
permanent current ownership.

Compute Journal floor increments from distinct admitted operations and each
operation's exact claim set, not from step ordinal or effect count. Admission can
advance a floor even when no output starts. Board floors advance only for started
work, and replay advances neither floor. Check replay and reserved procedure key
rows against exact request identities and steps. Same-key exact replay must return
the same IDs/history with unchanged business state; read/observation refresh is
tracked separately. A conflicting request must retain the original rows and
produce the expected conflict without another effect.

At a provider-commit/authority-settlement cut the board may already be idle while
Journal claims remain held. That is an expected intermediate state. Normal final
completion/cancellation requires exact retained idle evidence and released claims.
Missing or contradictory evidence stays unknown/unresolved, preserving claims
where required. Do not convert an uncertain operation to success, assume restart
stopped a physical device, or retry a mutation with a new key.

## Challenges, limits and integration order

Retain before/after records for cancellation while accepted and while pending,
reopen while accepted and while pending, and loss of the provider-completion reply
before authority settlement. A pending receipt on reopen is stopped/canceled once;
a completed receipt is reconciled without another activation. Session/epoch changes
are recorded as actual values. Historical idle is not fresh admission authority.

Use explicit trusted fixture operations to challenge shared-pad GPIO/PWM exclusion
across routes and progress on an independent pad. Their identities, requests,
effects and budgets must be included, distinct from the PAT's ordered children.
The one-role PAT restriction does not authorize hidden background test effects.
Actual driver/service lifecycle operations remain in their separately staged lane.

Keep initial hard ceilings at or below 32 total trial cases, 512 total child and
challenge operations, 2048 scheduler ticks, 16 MiB producer evidence, 64 KiB per
evidence document, 4096 evidence records and 20 MiB full derived evidence closure.
The worker's wall deadline is at most 60000 ms. These are proposed I/O policy
ceilings, not changes to existing fan constants. Count mandatory fault/challenge
trials in preflight totals. If full evidence cannot fit, refuse or fail the attempt
and retain its partial evidence; never omit a required checkpoint or relabel a
partial run as qualified. These bounds do not imply an enforced filesystem quota;
supervision, aggregate storage and public service installation remain separate.

Freeze source/dependency and policy/configuration identities before any execution.
Compiler identity still has its separately documented optional-dependency gap;
pin all actual imported dependencies for a worker and do not claim that this plan
repairs the compiler identity. Fresh execution environments must be reconstructed
exactly; current-source changes invalidate old worker/configuration compatibility.

Implementation order and acceptance are:

1. Add a pure isolated I/O timing/contract/matrix module and arithmetic boundary
   tests. Include duration 4999/5000, sparse extrema, applicability cannot narrow
   invalid declared domains, empty start windows, sequential deadlines, lease
   waiting, integer overflow and whole-range computation without range expansion.
2. Add a bounded worker using the actual original `IoRuntime` and procedure manager.
   Prove its virtual scheduler matches the static policy, and emit raw evidence
   before interpreting trial success. Retain every failed attempt and its sources.
3. Add the independent reducer with actual original worker outputs and mutation
   tests: activation/completion confusion, balanced but false counters, forged idle,
   omitted owner/fence/version/table, swapped identities, mismatched replay rows,
   skipped floor increments, impossible phase time, omitted/extra events and
   truncated inventories. Recompute outer hashes in semantic mutation tests so a
   hash mismatch is not the only reason for refusal.
4. Review the combined library and run relevant legacy/fixed-unit/resolver/I/O
   checks on one frozen source closure before considering live integration. The
   separate 34 pure passes and 28-plus-focused-one resolver evidence do not prove
   this composition. The full748 milestone excludes these staged changes.
5. Connect explicit trusted service configuration, current worker reconstruction,
   retained evidence import/memo, durable supervision and storage admission before
   exposing qualification or allowing automatic PAT promotion.

The reducer provides independent computation over a trusted producer transcript,
not independent sensing or execution attestation. A consistently fabricated
transcript is outside that claim. Prompt learning must consume these scoped facts
and preserve uncertainty; repeated apparent success alone is insufficient to
promote a procedure for new wiring, a new driver generation or a new hub context.
