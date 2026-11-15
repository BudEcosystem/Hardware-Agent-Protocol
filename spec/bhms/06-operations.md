# 6. Operations

An **Operation** is the durable record of one physical intent: an action
invocation or a program run. It is created at admission, never deleted within
its retention window, and changes only by appending history.

## 6.1 `actions/invoke`

Params:

| Member | Type | Required | Meaning |
|---|---|---|---|
| `deviceId` | string | yes | |
| `action` | string | yes | Action name |
| `arguments` | object | yes | Valid against the action's `input` (`{}` when it takes none) |
| `operationKey` | string, 1–128 chars of `[A-Za-z0-9._:~-]`, not starting with `d-` | no | Idempotency key (§6.4) |
| `leaseId` | string | when `requiresLease` | A current lease covering the action's `resources` |
| `deadlineMs` | integer ≥ 1 | no | Latest completion, relative to acceptance |
| `waitMs` | integer ≥ 0 | no (default 0) | Hold the response until the operation settles or this elapses |
| `require` | `{effect: "verified"}` | no | Demand measured verification of the effect |
| `descriptionDigest` | string | no | The description the client planned against |

Result: `{operation, replayed}` — `replayed` is `true` when an existing operation
was returned for the same key.

## 6.2 The Operation object

| Member | Type | Required | Meaning |
|---|---|---|---|
| `operationId` | string | yes | Server-minted |
| `operationKey` | string | yes | The client's key, or a server-generated one |
| `keyOrigin` | `client` \| `server` \| `derived` | yes | `server`: generated because none was sent — **not retry-safe**; `derived`: a program step's key |
| `kind` | `action` \| `program` | yes | |
| `deviceId`, `action` | string | for `action` | |
| `programDigest` | string | for `program` | |
| `parentOperationId` | string | no | The program operation that created this step operation |
| `arguments` | object | yes | Arguments exactly as sent (the input of `requestDigest`, §6.4) |
| `admittedArguments` | object | no | Arguments as admitted (defaults applied, quantity objects replaced by their values); present only when they differ from `arguments` |
| `requestDigest` | string | yes | Digest of the intent (§6.4) |
| `state` | `OperationState` | yes | §6.3 |
| `cancel` | `{state, reason?, requestedAt?}` | yes | §6.6 |
| `effect` | `none` \| `verified` \| `unverified` \| `unknown` | yes | What is known about the physical effect |
| `evidence` | `{kind, observations?}` | no | Evidence behind `effect` (`kind`: `measured` \| `reported` \| `none`) |
| `require` | `{effect}` | no | As requested |
| `leaseId`, `fence` | string, integer | no | Lease and fence the operation was admitted under |
| `deadlineAt` | time | no | Absolute deadline |
| `result` | any | no | Present only when `completed`; valid against the action's `output` |
| `error` | `OperationError` | no | Present when `failed`, `rejected` or `unknown` |
| `progress` | `{stepsCompleted, stepsTotal}` | no | Programs |
| `createdAt`, `updatedAt` | time | yes | |
| `upstream` | `{server, operationId}` | no | Gateways only, and only for `admin` principals: the upstream server (its namespace) and the operation id there (BHMS-OPS-064) |
| `history` | `HistoryEntry[]` | no | Returned by `operations/get` and `operations/wait`; omitted in lists and notifications |

`OperationError` is the error data of §10 plus `message`.
`HistoryEntry = {seq, at, kind, state?, cancel?, effect?, detail?, stepIndex?, childOperationId?, operator?}`
(`operator: {principal, basis}` only on a `reconciliation` entry written from an operator's resolution, §6.10),
`kind` ∈ `state`, `cancel`, `effect`, `evidence`, `reconciliation`, `correction`,
`step`, `stop`, `lease`.

**Results are I-JSON.** An operation's `result` (and every JSON value a server records) MUST be
I-JSON (RFC 7493): numbers are IEEE 754 doubles, so an integer outside ±2^53 (9007199254740991) or a
non-finite number cannot be recorded. A server that is handed such a result MUST NOT complete the
operation: it ends `failed` with `INTERNAL`, `mayHaveActed: true` and a message naming the member and
the rule (return the value as a string, or as a float when rounding is acceptable).

## 6.3 States

`state` ∈ `accepted`, `dispatching`, `running`, `completed`, `failed`,
`canceled`, `rejected`, `unknown`.

| State | Means | Allowed successors | Evidence required for the transition |
|---|---|---|---|
| `accepted` | Durably admitted; nothing sent to the device | `dispatching`, `rejected`, `canceled` | `dispatching`: durable dispatch record. `rejected`/`canceled`: proof no dispatch occurred |
| `dispatching` | The command may have reached the device | `running`, `completed`, `failed`, `canceled`, `unknown` | Device or adapter evidence; a missing reply means `unknown` |
| `running` | The device reported that it is executing | `completed`, `failed`, `canceled`, `unknown` | Completion evidence, a reported fault, an observed termination, or insufficient evidence |
| `unknown` | The device may or may not have acted | `running`, `completed`, `failed`, `canceled` | Only a `reconciliation` history entry carrying new evidence |
| `completed` | The action finished; `result` is set | none | |
| `failed` | Known failure; partial effects recorded | none | |
| `canceled` | A termination condition was observed after cancellation or before dispatch | none | |
| `rejected` | Refused after admission and before dispatch; no effect | none | |

`completed`, `failed`, `canceled` and `rejected` are **terminal**. Terminal
states and `unknown` together are **settled**: a client waiting for an outcome
stops waiting when an operation is settled.

**BHMS-OPS-001** A server MUST change `state` only along the transitions in the
table, and MUST append a history entry for every change of `state`,
`cancel.state` or `effect`.

**BHMS-OPS-002** A terminal state MUST NOT change. A later correction (for example
evidence that contradicts a `completed` result) MUST be appended as a
`correction` history entry without altering `state`, `result` or `effect`.

**BHMS-OPS-003** A server MUST record `dispatching` durably *before* the command
can reach the device. If it cannot write the record, it MUST NOT dispatch, and
the operation becomes `rejected` (error `INTERNAL`, `mayHaveActed: false`) or
remains `accepted`. A record that was written but could not be made durable (the
sync of the journal failed) counts as not written: nothing is dispatched, and
because the record already reads `dispatching` the operation ends `failed`
(`mayHaveActed: false`, `effect: "none"`: the server can prove nothing was sent).
Concurrent intents may share one sync (group commit) as long as none is
dispatched, and none is reported to anyone (the invoker's answer, operation
notifications, `operations/get`, `operations/list`, a gateway mirroring it),
before the sync covering its own record has completed.

**BHMS-OPS-004** Once an operation has reached `dispatching`, a transport error,
timeout, lost reply or process crash MUST result in `unknown` (or a state proven
by device evidence), never `failed` with `mayHaveActed: false` and never
`completed` without completion evidence. Every transition into `unknown` MUST
carry `error.bhmsCode: "DEADLINE_EXCEEDED"` with `mayHaveActed: true` and
`retry: "after-reconcile"`, whatever the cause (lost reply, link loss, server
restart, endpoint epoch change); `error.message` states the cause. One code lets
clients treat every unknown outcome the same way.

**BHMS-OPS-005** An operation may leave `unknown` only through a `reconciliation`
history entry that names its evidence (a device query, a compact replay-ring
answer, a measurement). The prior `unknown` entry MUST remain in history.

**BHMS-OPS-006** `rejected` and `canceled`-from-`accepted` operations MUST have
`effect: "none"`. A `completed` operation MUST have `effect` `verified` only with
`measured` evidence; with `reported` evidence it is `unverified`; for an action
whose `effect` class is `none` it is `none`.

**BHMS-OPS-007** When `require.effect` is `"verified"`, the server MUST refuse at
admission with `UNSUPPORTED` if the action's `completionEvidence` is not
`measured`, and MUST NOT mark the operation `completed` unless the effect is
verified; otherwise it ends `failed` with error `UNVERIFIED` and
`mayHaveActed: true`.

**BHMS-OPS-008** `result` MUST be present exactly when `state` is `completed` and
MUST validate against the action's `output` schema. When a returned result is
well-formed except that a number lies outside the range its `output` schema
declares (`minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`), the server
MUST NOT complete the operation and MUST NOT lose the value: the operation ends
`failed` with `OUT_OF_RANGE`, `field` naming the member (`result.volume`), `bound`
the violated bound, `mayHaveActed: true` and `retry: "after-reconcile"`; `effect`
and `evidence` are what the completion evidence supports (for an action with an
effect never `none`: the device acted); `error.message` states the returned value
and an `evidence` history entry records the result as returned. This is a
measurement outside its declared range, which a client must be able to tell from
a server fault; every other invalid result ends `failed` with `INTERNAL` (§6.2).

**BHMS-OPS-009** `failed`, `rejected` and `unknown` operations MUST carry `error`.
`error.mayHaveActed` MUST be `true` whenever the operation reached
`dispatching`, unless device evidence proves no effect.

## 6.4 Idempotency

The **intent** of a request is the object
`{method, deviceId, action, arguments, deadlineMs?, require?, descriptionDigest?}`
for `actions/invoke` and `{method, digest, arguments, deadlineMs?}` for
`programs/run` (where `digest` is the program digest, also for inline programs),
and where `arguments` are exactly as sent (quantity objects are kept as sent, so a
retry must repeat the arguments verbatim) and absent members are omitted.
`requestDigest` is the BHMS digest of the intent. `leaseId`, `waitMs`,
`operationKey` and `_meta` are not part of it. The intent is computed from the
request alone, without the device description, so the key lookup needs no
resolution or authorization step (BHMS-OPS-033).

**BHMS-OPS-030** For each principal, a server MUST map an `operationKey` to at most
one operation. A request whose key exists with the same `requestDigest` MUST
return the existing operation with `replayed: true` and MUST NOT dispatch
anything, whatever the operation's state.

**BHMS-OPS-031** A request whose key exists with a different `requestDigest` MUST
be refused with `KEY_CONFLICT`, carrying `operationId` of the existing operation,
and MUST NOT create or modify any operation.

**BHMS-OPS-032** Concurrent requests with the same principal and key MUST produce
exactly one operation; all of them return it.

**BHMS-OPS-033** A server MUST look up `(principal, operationKey)` immediately
after validating the params shape and authenticating the principal, before
resolving the device or action, authorizing, checking the description pin,
arguments, leases or device state. The lookup is gated only by the principal's
visibility of its own operations (BHMS-OPS-062), which scope revocation does not
remove. A retry of an admitted request therefore returns the existing operation
even after its lease expired, a scope was revoked, or the description changed
or dropped the action.

**BHMS-OPS-034** A server with `capabilities.operations.durable: true` MUST retain
key mappings and operation records for at least `keyRetentionS` seconds
(≥ 86 400) across restarts, and MUST keep the same `epoch` while it does. A
server that loses that state MUST present a new `epoch`. A server with
`durable: false` MUST present a new `epoch` on every start, and clients MUST
treat its earlier operations as `unknown`.

**BHMS-OPS-035** When `operationKey` is absent, the server MUST generate a unique
key, set `keyOrigin: "server"`, and treat a re-sent request as a new operation.
Clients that may retry MUST send their own key.

**BHMS-OPS-036** A client MUST NOT reuse an `operationKey` for a different intent,
and MUST NOT reuse any key after `keyRetentionS` has passed since its first use.
*This is a documented weakening of HMS* (§1.4): HMS keeps a server-side
replay-namespace floor so that a forgotten key can never become a new
operation; BHMS v0.1 replaces that floor with this client obligation plus a
minimum retention of 24 h. A client that violates it after the window may cause
a second effect. Servers SHOULD retain keys longer than `keyRetentionS` when
storage allows.

**BHMS-OPS-037** Keys starting with `d-` are reserved for derived program-step
keys and keys starting with `g-` for gateways forwarding on behalf of their
clients (BHMS-AUTH-014). A server MUST refuse a client key starting with `d-`
with `INVALID_ARGUMENT`, `field: "operationKey"`; it MAY refuse `g-` keys from
principals not configured as gateways. Clients other than gateways MUST NOT use
either prefix.

## 6.5 Admission

Admission order for `actions/invoke` (and, per step, for programs):

1. Validate `_meta` and the params shape (`INVALID_ARGUMENT`); the principal is
   already authenticated by the transport (BHMS-SEC-001).
2. Key lookup (§6.4): an existing key returns its operation (`replayed: true`) or
   `KEY_CONFLICT`, and admission ends here.
3. Resolve the device: unknown or unreadable → `UNKNOWN_DEVICE`; unknown action →
   `UNKNOWN_ACTION`.
4. Authorize (`UNAUTHORIZED`) — §7.4.
5. Pin check: `descriptionDigest` differs from current → `STALE`.
6. Validate arguments against `input` and the principal's effective envelope
   (`INVALID_ARGUMENT`, `OUT_OF_RANGE`, `UNIT_MISMATCH`).
7. `require` check (`UNSUPPORTED`).
8. Lease check: `LEASE_REQUIRED`, `LEASE_EXPIRED`, `LEASE_CONFLICT`, `FENCED`.
9. State check: device reachable (`DEVICE_UNAVAILABLE`), `requiresFresh`
   observations (`STALE`, BHMS-OBS-030), unresolved `unknown` operations on the same resources
   (`STALE`), capacity (`BUSY`).
10. Durably record `accepted`; return or wait.

**BHMS-OPS-040** Steps 1–9 MUST complete before an operation is created. A refusal
in steps 1 and 3–9 concerns a request with no existing operation for its key
(step 2 would have answered otherwise), so it MUST be a JSON-RPC error with
`mayHaveActed: false` and MUST NOT create an operation. `KEY_CONFLICT` (step 2)
MUST carry the existing `operationId` and `mayHaveActed` equal to that
operation's `error.mayHaveActed`, or `true` if it reached `dispatching` and has no
error.

**BHMS-OPS-041** Checks that depend on time (lease validity and fence, deadline,
device reachability, preconditions) MUST be repeated immediately before dispatch.
A failure at that point makes the operation `rejected` with the corresponding
error and `effect: "none"`.

**BHMS-OPS-042** While an operation whose action has `effect` other than `none`
is `unknown`, the server MUST refuse new operations that use any of its resources
with `STALE` naming that `operationId`, until the operation is reconciled, a
`stop` of the device returns `outcome: "confirmed"`, or the device *proves* an
epoch change that purged its work: a persistent epoch counter that advanced
(BHMS-CMP-020) or an accepted new session, which requires no active operation
(BHMS-CMP-023). A re-established connection, a gateway restart or an endpoint
that cannot prove its epoch (no `PERSISTENT_EPOCH`) MUST NOT lift the inhibition.

## 6.6 Cancellation

`operations/cancel {operationId, reason?}` → `{operation}`.
`cancel.state` ∈ `none`, `requested`, `acknowledged`, `refused`, `confirmed`.

**BHMS-OPS-050** Cancelling an `accepted` operation MUST prevent dispatch and make
it `canceled` with `cancel.state: "confirmed"` and `effect: "none"`.

**BHMS-OPS-051** Cancelling an operation whose action declares
`cancel: "unsupported"` MUST set `cancel.state: "refused"` (not an error) and
MUST NOT change `state`.

**BHMS-OPS-052** `acknowledged` MUST mean only that the device or adapter received
the request. `state: "canceled"` with `cancel.state: "confirmed"` MUST be set
only when a termination condition was observed. Completion or failure MAY win the
race; a late acknowledgement MUST NOT overwrite a terminal state.

**BHMS-OPS-053** Cancelling a settled-terminal operation MUST return it unchanged.
Cancelling an `unknown` operation MUST record the request and forward it to the
device when possible.

**BHMS-OPS-054** Only the principal that created an operation, or one with the
`admin` scope, MAY cancel it; others MUST receive `UNAUTHORIZED`. Cancellation
MUST NOT require a lease.

**BHMS-OPS-055** `canceled` MUST NOT be presented as "safe" or "at rest". A client
that needs the device halted MUST use `stop`.

## 6.7 Reading and waiting

`operations/get {operationId}` and `operations/wait {operationId, timeoutMs}`
return `{operation}` with `history`. `operations/list {deviceId?, state?,
parentOperationId?, cursor?, limit?}` returns `{operations, nextCursor?}` without
history.

**BHMS-OPS-060** `operations/wait` MUST return as soon as the operation is
settled, or when `timeoutMs` elapses, whichever is first. It MUST NOT return an
error because the timeout elapsed. `timeoutMs` above `limits.maxWaitMs` MUST be
refused with `OUT_OF_RANGE`.

**BHMS-OPS-061** `waitMs` on `actions/invoke` and `programs/run` MUST behave like
`operations/wait` after admission; a server MUST NOT fail an admitted operation
because the response wait elapsed.

**BHMS-OPS-062** An unknown or invisible `operationId` MUST be answered with
`INVALID_ARGUMENT`, `field: "operationId"`. Operations are visible to the
principal that created them and to principals with `admin`.

**BHMS-OPS-064** A gateway MUST NOT include the member `upstream` in an operation
it gives to a principal without `admin` (the operation's owner and
`operations:read` included), nor in any notification: what lies behind a gateway
is not a client's business. To a principal with `admin` it SHOULD give, in
`operations/get`, `operations/wait` and `operations/list`,
`upstream: {server, operationId}`: the namespace of the upstream server the
operation was forwarded to and the operation's id there (a gateway mints its own
operation ids), so that a gateway record can be joined to the device server's own
journal after an incident. A device server never sends `upstream`.

**BHMS-OPS-063** An operation that a client has seen MUST remain retrievable with
`operations/get` for at least `keyRetentionS` seconds after it settled.

## 6.8 Deadlines and duration bounds

**BHMS-OPS-070** If `deadlineAt` passes before dispatch, the operation MUST become
`rejected` with `DEADLINE_EXCEEDED` and `mayHaveActed: false`.

**BHMS-OPS-071** If `deadlineAt` or the action's `maxDurationMs` passes while the
operation is `dispatching` or `running`, the server MUST request cancellation when
the action supports it and MUST end the operation `failed` with
`DEADLINE_EXCEEDED` and `mayHaveActed: true`, or `unknown` when termination is not
observed.

## 6.9 Crash windows

| Crash point | Outcome after restart |
|---|---|
| Before `accepted` is durable | No operation; a retry with the key creates it |
| After `accepted`, before `dispatching` | Rechecked per BHMS-OPS-041, then dispatched or `rejected` |
| After `dispatching`, before any device reply | `unknown`, then reconciled when the device can be queried |
| After the device finished, before the result is durable | `unknown`, then reconciled |
| After the result is durable, before the reply | The stored operation is returned to a retry with the key |

**BHMS-OPS-080** On restart a server MUST move every action operation found in
`dispatching` or `running` to `unknown` (error per BHMS-OPS-004), and settle
program operations per BHMS-PRG-017, before
answering any request that could touch the same resources, and SHOULD then
attempt reconciliation.

**BHMS-OPS-081** A server MUST NOT re-send to a device a command whose operation
was `dispatching` or later, unless the device's own replay protection guarantees
it will not act twice (for example the BHMS-Compact replay ring, §11.6).

**BHMS-OPS-082** A server that can ask a device what happened (a reconciliation
path: a device query, a replay ring, a device-side log) MUST attempt reconciliation
of that device's `unknown` operations whenever the device **returns**: its status
becomes `online` after `offline`, `degraded` or `unknown`. It asks once per return,
bounds each attempt in time, and MUST NOT take a missing or failed answer for
success: the operation then stays `unknown`. (BHMS-OPS-080 covers the server's own
restart; this covers the device's.)

## 6.10 Resolving an unknown operation

`operations/resolve {operationId, resolution?}` → `{operation}` (with `history`),
offered when `capabilities.operations.resolve` is `true`.

`resolution = {state, basis, effect?, mayHaveActed?, result?}`: `state` is
`completed` or `failed`; `basis` (1–2000 characters) is free text saying what was
inspected, by whom and what was found (readings the operator took belong here, as
text); `result` belongs to `completed`; `mayHaveActed` belongs to `failed`;
`effect` is `none` or `unverified`.

An `unknown` operation inhibits its resources (BHMS-OPS-042) until evidence
resolves it. When the device can never give that evidence (a dead bridge, a
controller that kept no record), an **operator** — a person with authority over
the device, not the client that started the operation and never a model — states
what happened, and the server records it as what it is: an operator's statement.

**BHMS-OPS-100** A server MUST answer `operations/resolve` only for a principal
with `admin` or `operations:resolve`, on an operation that principal can see
(BHMS-OPS-062); any other caller gets `UNAUTHORIZED` naming `operations:resolve`,
also for an operation it owns. A program operation is refused with
`INVALID_ARGUMENT` (it settles through its step operations, BHMS-PRG-017). An
agent bridge MUST NOT expose this method (§12).

**BHMS-OPS-101** The server MUST first attempt reconciliation of the operation
(BHMS-OPS-005); device evidence, when there is any, is what is recorded, and the
`resolution` is then not used. Without `resolution` the call does nothing else: it
is the way to ask the device again. An operation that is not `unknown` MUST be
returned unchanged, with nothing recorded.

**BHMS-OPS-102** If the operation is still `unknown` and `resolution` is given, the
server MUST record it as a `reconciliation` history entry carrying
`operator: {principal, basis}` (the caller's principal id and the stated basis),
after the earlier entries, which are never changed or removed. An operator's
statement is a report, never a measurement: the recorded `effect` MUST NOT be
`verified` and the operation's `evidence` MUST be `{"kind": "reported"}`, whatever
the request says; `verified` and `measured` arise only from evidence the device
itself supplies, which is the reconciliation of BHMS-OPS-101. Consequently an
operation that required a verified effect (BHMS-OPS-007) cannot be resolved as
`completed`. A `completed` resolution needs a `result` valid against the action's
`output` and records `unverified` (`none` for an action without effect). A `failed`
resolution records `unknown` (default) or `unverified`; `mayHaveActed: false` and
`effect: "none"` are one claim, proof that nothing happened, and are stated
together or not at all. A resolution that breaks a rule is refused
(`INVALID_ARGUMENT`, or `OUT_OF_RANGE` for a result outside the declared output
range) and nothing is recorded. Every resolution of an `unknown` operation,
whatever its source, MUST be recorded as an `operation.resolved` event (§9.1) with
`data.source` `"device"` or `"operator"`, and `data.principal` for an operator.

A gateway forwards `operations/resolve` to the upstream server that holds the
device's record, adding to `basis` who asked through which gateway, and mirrors
the answer (its own entry carries `operator` with the caller's principal). When
that upstream is not reachable, has no record of the request or does not offer
the method, and a `resolution` is given, the gateway records the resolution on its
own operation under the same rules (BHMS-OPS-102): it is an enforcement point of its own, and its record is what
inhibits the resources at the gateway. The upstream keeps its own inhibition
until the operation is resolved there.

## 6.11 Operation notifications

**BHMS-OPS-090** A server MUST deliver `notifications/operation` to matching
subscriptions for every change of `state`, `cancel.state` or `effect`, with the
operation (without `history`) as of that change, in change order per operation.
