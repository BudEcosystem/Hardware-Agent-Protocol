# Durable bounded procedures

Status: experimental `hms.bound-sequence/0.1`, implemented for the installed
simulation adapters. Focused engine tests pass; the current full-suite receipt
must be checked in [PROGRESS](../PROGRESS.md) before relying on an integration
claim. No physical device, full PAT learning loop or MCU procedure interpreter
is established by this profile.

## Contract

`procedure_submit` takes `{request: envelope}`. The envelope is:

```json
{
  "protocol": "hms.procedure/0.1",
  "replayNamespace": "<issued namespace>",
  "procedureKey": "<new parent key>",
  "procedure": {
    "profile": "hms.bound-sequence/0.1",
    "timing": {
      "notBeforeUnixMs": 1000,
      "latestStartUnixMs": 5000,
      "latestCompletionUnixMs": 5500
    },
    "steps": [
      {"stepId": "first", "request": "<complete retained hms.invoke/0.1 object>"}
    ]
  }
}
```

This is a structural illustration: the child request is an actual object, and
times and namespace must be valid for the running authority. There are 1–16
ordered steps. All fields are closed; all child invocations retain their full
binding, session, arguments, effect requirement and timing. Step IDs and parent/
child keys must be distinct, and every child uses the parent's replay namespace.
The host JSON byte, depth, numeric and node bounds also apply. API/transport
wrappers consume part of the 65,536-byte message limit.

Every child's interval lies inside the parent interval. The first child's latest
start is no later than the parent's latest start; this bounds first handoff, not
only parent acceptance. The namespace must last at least through the parent's
completion deadline. Parent identity hashes the entire canonical envelope with
the domain prefix `HMS-PROCEDURE-JCS-SHA256-v0.1` followed by a NUL byte. The
separate child digest remains its existing HMS intent digest.

Parent admission validates all static bindings, argument schemas, permissions
and installed handler support. It does not assert future live readiness or
reserve all future physical resources. Each child is admitted only at its turn,
with current presence, session, preconditions, authority and resource checks.
Other operations can execute between procedure steps. This is ordered execution,
not an atomic physical transaction.

## Atomicity and continuation

The parent and all key reservations commit together. A caller cannot bypass the
order by invoking an unstarted child's reserved key directly. The selected child
operation, replay key, resource fences/claims, accepted event and procedure link
commit in one Journal transaction. No handoff occurs before this commit.

The next child is eligible only when every predecessor has completed, released
its resource claims and has no failed/disputed verification. Rechecks before
handoff prevent a stale scheduler decision from bypassing a new cancel, pause or
dispute. The current profile fails on substantive admission refusal; resource
contention and clock unavailability pause selection without minting new keys.
It does not silently retry an accepted or unknown child as a new operation.

An authority restart changes active parent controls to `interrupted`. Adapter
receipt queries and reconciliation continue, but new handoffs and continuation
require `procedure_resume`. Resume checks current static authority and bindings,
the existing prefix and deadlines. An unknown child must be reconciled first.
Existing linked child IDs are retained. An accepted paused child still undergoes
normal start/lease expiry cleanup; pausing does not extend its lease.

Selection processes at most 64 parents per pass with round-robin pagination,
and at most one new child per selected parent. This is a work bound, not a
qualified latency guarantee: the authority mutex and durable storage are shared.
Idle selection does not sample or write the authority clock.

## Cancellation, timeout and evidence

The owner can latch `procedure_cancel` even after future-step permissions or
read access are revoked. This prevents further steps. Delivery of cancellation
to a current nonterminal child still requires that child's current cancellation
permission. A denied delivery does not roll back the parent latch, and does not
pretend the running child stopped. An accepted child that is authorized for
cancellation can be canceled atomically before any handoff.

The cancellation reply is a minimal owner-safe acknowledgement with a delivery
status: `no_active_child`, `recorded`, `denied` or `already_terminal`. It can be
rendered after read revocation. It does not contain child arguments or results.
Full status and events require current read access to every target in the plan.

Parent states are `accepted`, `running`, `interrupted`, `completed`, `failed`,
`canceled` and `expired`. These describe procedure control. A canceled or expired
parent may still have an active/unknown child or held claims. Parent timeout
never releases those claims or fabricates child termination. Child deadlines and
adapter evidence remain authoritative.

Status reports compact per-step execution, cancellation, verification and held
resource counts plus operation IDs. Use `operation` and `events` for detailed
child results. The aggregate verification summary is `unverified`, `failed` or
`disputed`; the profile does not assert that completing all steps verifies an
arbitrary physical or scientific goal. A late dispute remains visible even after
the historical parent control state became completed. `unresolvedOperations`
includes active work, held claims and failed/disputed evidence.

Exact parent replay returns the same procedure and current compact state while
the namespace is retained. Like ordinary operation replay, an expired but
unpruned namespace permits lookup; pruning invalidates replay. Status by ID and
the immutable parent/child/event records remain. Reservations preserve audit
ownership after pruning, not fresh admission authority.

## CLI, client and MCP

| Local method | `hctl` subcommand | Result |
|---|---|---|
| `procedure_submit` | `procedure-submit --request-file plan.json` | Compact procedure status |
| `procedure_status` | `procedure-status PROCEDURE_ID` | Compact procedure status |
| `procedure_cancel` | `procedure-cancel PROCEDURE_ID` | Owner-safe delivery acknowledgement |
| `procedure_resume` | `procedure-resume PROCEDURE_ID` | Current status after explicit continuation |
| `procedure_events` | `procedure-events PROCEDURE_ID --after N --limit L` | Ordered page, head and next cursor |

Use `python3 -m hms --socket PATH` before a subcommand. The Python checked client
uses the local method names. MCP exposes the corresponding
`hardware_procedure_*` tools with the same checked schemas. MCP request
cancellation, a lost reply and client exit do not cancel the procedure; retain
the exact submitted envelope and use explicit domain queries/cancellation.

Procedure event pages are limited to 100 records with contiguous sequence
checks. Events record acceptance, child admission, cursor advance, control
transitions, cancellation intent and delivery. Child evidence is independently
recorded in its operation journal. All stored execution truth survives loss of
the agent's conversation.

## Verification and remaining scope

[Engine tests](../tests/test_procedures.py) exercise reserved-key exclusion,
atomic rollback and abrupt process exits, concurrent replay, permission changes,
first-handoff/deadline constraints, interruption, quiescence, disputes, pagination,
16-step status bounds and an ordered five-step sequence across a SQLite route
and two original native C endpoints. These tests execute original simulations;
they do not execute an MCU or acquired controller.

Reusable parameterized [PATs](prompt-to-pat.md), branches and bounded loops,
material/data references, observation guards and streams, hierarchical
[I/O/driver/hub resources](io-driver-hub-control.md), distributed scheduling,
retention quotas and physical deployments remain separate required work. Existing
historical Harness receipts cover their pinned primitive flows; they do not
validate this new procedure surface without a new integration run.
