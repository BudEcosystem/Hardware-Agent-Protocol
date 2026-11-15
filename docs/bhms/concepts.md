# Concepts

This page explains the ideas BHMS is built on, in the order you meet them: devices, actions and properties, effects
and evidence, durable operations and unknown outcomes, leases and fencing, stop, programs, gateways, the compact binding
for microcontrollers, and conformance profiles. Read it once before you build anything that moves.

Each section names the normative chapter of the [specification](../../spec/bhms/README.md) it summarises. Where this page
and the specification differ, the specification wins.

## The shape of the protocol

BHMS is JSON-RPC 2.0 with MCP's shape: requests carry no session state, `server/discover` tells a client what the server
offers, and `subscriptions/listen` is a long-running request that streams notifications. What it adds is what physical
work needs and chat tools do not ([spec 1](../../spec/bhms/01-overview.md)):

```text no-run
 agent / program / person
            |  JSON-RPC 2.0 over stdio, Unix socket, WebSocket or Streamable HTTP
            v
 +----------------------+
 | gateway (optional)   |  principals and scopes, narrowed bounds, cross-device leases, its own journal
 +----------------------+
      | JSON-RPC            | BHMS-Compact (binary HM frames over UART / USB CDC)
      v                     v
 device server          microcontroller endpoint
```

Authority comes from the connection, never from arguments: a stdio parent is the only principal of its child, a Unix
socket peer is known by its uid, a WebSocket or HTTP client by its bearer token. Nothing a model writes into a request
can grant a permission, raise a bound or skip a lease ([spec 13](../../spec/bhms/13-security.md)).

## Devices

A server exposes devices. Each has a short **summary** for listings (`devices/list`, about 400 tokens at most: id, name,
status, capabilities, action and property names) and a full **description** (`devices/describe`): every action and
property with its JSON Schema, units, bounds and safety declarations, plus a `digest`, a sha256 over the canonical JSON
of the description. The digest changes whenever anything in the description changes, so a client can pin it
(`descriptionDigest` on an invoke) and be refused if the device changed underneath it
([spec 4](../../spec/bhms/04-devices.md)).

A device's **status** is `online`, `offline`, `degraded` or `unknown`, and it is evidence-based: `online` means the
server has recent evidence that the device answers (a successful liveness probe, acquisition or action, or a driver's
`report_alive()`); with no evidence the status is `unknown`, after a failed probe `offline`. New work on an `offline`
device is refused with `DEVICE_UNAVAILABLE`.

**Resources** are what must be used exclusively: an axis, a pump head, a shared work zone. A device declares them, and
each action names the subset it uses. Leases and the unknown-outcome inhibition below work on resources, not devices.

## Actions and properties

A **property** is something you read: `properties/read` returns an **observation**, an immutable record of a value and
how it is known ([spec 5](../../spec/bhms/05-observations.md)):

| Member | Meaning |
|---|---|
| `value`, `unit` | The value, in the UCUM unit the schema declares. `null` when the reading is invalid or unknown, never a substitute such as zero or the last good value. |
| `evidence` | How it was obtained: `measured` (an independent sensor), `reported` (the device or driver says so), `commanded` (a setpoint echoed back), `estimated` (a model), `simulated` (a simulator). Never stronger than what was obtained. |
| `quality` | `valid`, `stale` (older than its validity interval), `invalid` (the source failed), `unknown`. |
| `acquiredAt`, `ageMs` | When the device acquired it, and a conservative age. `ageMs` is `null` when the latency is unbounded; such a reading fails every freshness requirement. |

`maxAgeMs` or `fresh: true` on a read asks for a recent acquisition. An action can require fresh observations before it
runs (`requiresFresh`), which the server checks at admission and again before dispatch.

An **action** is something you ask the device to do. Its declaration is the contract a client reasons with:

| Declaration | Values | Why it matters |
|---|---|---|
| `effect` | `none`, `reversible`, `irreversible`, `hazardous` | What it does to the world. `hazardous` (heat, force, lasers) requires a lease, and a scope that names the action literally. |
| `idempotency` | `idempotent`, `absolute`, `relative`, `toggle` | What a duplicate execution would do. A `relative` move or a dispense doubles; that is why operation keys exist. |
| `completionEvidence` | `measured`, `reported`, `none` | What the server can know about completion. `measured` only with an independent sensor named in `verifiedBy`. |
| `maxDurationMs` | integer | Enforced: an operation still running after it is cancelled (when the action supports it) and never completes. |
| `cancel` | `supported`, `unsupported` | Whether `operations/cancel` can end it. |
| `requiresLease`, `resources`, `onLeaseLoss` | | See leases below. |
| `input`, `output` | JSON Schema | Arguments and result, every number with an `x-bhms-unit`. Arguments outside the schema are refused before anything acts. |

Arguments are bare numbers in the declared unit. A quantity object (`{"value": 10, "unit": "uL/min"}`) is accepted only
in that same unit; a different unit is refused with `UNIT_MISMATCH`, never converted silently.

## Operations: durable, idempotent, honest

`actions/invoke` does not return "ok". It creates an **operation**: a durable record with a server-minted id, a state
machine and an evidence-backed `effect` ([spec 6](../../spec/bhms/06-operations.md)).

```text no-run
 accepted ──> dispatching ──> running ──> completed | failed | canceled
    │              │             │
    │              └─────────────┴──> unknown ──(reconciliation evidence)──> running | completed | failed | canceled
    └──> rejected | canceled          (before dispatch: no effect)
```

- `dispatching` is written to the journal before the command can reach the device. If that write fails, nothing is sent.
- After dispatch, a lost reply, a timeout, a dropped link or a server crash makes the operation **`unknown`**, never
  `failed` and never `completed`. Every transition into `unknown` carries `DEADLINE_EXCEEDED` with `mayHaveActed: true`
  and `retry: "after-reconcile"`, so a client treats every unknown outcome the same way.
- `completed`, `failed`, `canceled` and `rejected` are terminal; terminal states and `unknown` together are *settled*.
  A later contradiction is appended to the history as a correction; a terminal state never changes.

The operation's **`effect`** says what is known about the physical effect: `none` (nothing happened, with proof),
`verified` (an independent measurement confirmed it), `unverified` (it was reported, not measured) or `unknown`. A
completed move with `reported` completion evidence is `unverified`. Ask for `require: {effect: "verified"}` and the server
refuses at admission unless the action can measure its completion, and fails the operation with `UNVERIFIED` if the
measurement disagrees.

**Operation keys.** A client that may retry sends an `operationKey`. For each principal a key names at most one
operation: the same key with the same request returns the same operation (`replayed: true`) and dispatches nothing,
whatever its state; the same key with a different request is refused with `KEY_CONFLICT`. Without a key the server makes
one up (`keyOrigin: "server"`), and a re-sent request is a new operation. Keys are kept at least 24 hours
(`keyRetentionS`); do not reuse one after that.

**Unknown outcomes block their resources.** While an effectful operation is `unknown`, new work on any of its resources
is refused with `STALE` naming it. The inhibition ends when the operation is reconciled from device evidence (the
server asks the device after a restart, whenever the device comes back online, and on request), when a `stop` of the
device is confirmed, when a microcontroller proves that a reboot purged its work (a persistent boot epoch that
advanced), or when an operator resolves it. An operator's resolution (`operations/resolve`, `bhms resolve`) is
recorded as what it is, an operator's report: it can never make an effect `verified`.

## Leases and fencing

A **lease** is exclusive, time-limited control of a set of resources ([spec 7](../../spec/bhms/07-leases-and-authority.md)):
`leases/acquire {resources, ttlMs}` grants all of them or none, `leases/renew` extends it, `leases/release` ends it.

- **Exclusive against everyone.** While a lease is active on a resource, every action that uses that resource is refused
  unless the request presents that lease (`leaseId`), whether or not the action declares `requiresLease`, and also for
  the holder that forgot to present it (`LEASE_CONFLICT`, `field: "leaseId"`). Ordinary reads are never blocked.
- **`requiresLease: true`** additionally means the action cannot run without one (`LEASE_REQUIRED`, with the resources
  in `bound`). Hazardous actions always require one.
- **Fencing.** Every lease gets a `fence`, a number higher than every fence the server issued before, across restarts. A
  holder whose lease expired, was revoked by `stop`, or was superseded presents an old fence and is refused (`FENCED`,
  `LEASE_EXPIRED`), at admission and again immediately before dispatch. A gateway forwards the upstream fence, and a
  microcontroller checks it too, so a stale holder is stopped at every enforcement point.
- **Lease loss while running** follows the action's `onLeaseLoss`: `finish`, `cancel` or `hold`.

The agent bridge acquires, renews and releases leases for a model by itself; programs and people use them directly
([leases and safety guide](guides/leases-and-safety.md)).

## Stop

`stop {deviceIds | scope: "all", reason}` makes devices run their commissioned stop procedure, cancels their queued
work, asks running work to end, and revokes their leases. It needs only the `stop` scope, and it never waits for a
lease, a queue or an in-flight operation: a server processes it ahead of everything else. Each device reports
`confirmed` (the stop procedure finished, with evidence), `initiated` (dispatched, not yet confirmed), `unsupported` (no
stop procedure: work was still cancelled and leases revoked) or `failed`.

Stop is not cancel (`operations/cancel` asks one operation to end), and neither is an emergency stop. A hardware
E-stop that cuts power must exist independently of any software. The default agent policy includes `stop` on the agent's
own devices, because stopping is the one safe action an agent has when something goes wrong.

## Programs

A **program** is a bounded, validated sequence of steps (`invoke`, `read`, `waitUntil`, `assert`, `sleep`, `repeat`
with a fixed bound) over the actions and properties of one server ([spec 8](../../spec/bhms/08-programs.md)). It is plain
JSON with no unbounded loops and no code. The server validates all of it before the first step: structure, references,
the caller's scopes and bounds, leases and the worst-case duration, which must fit the declared `maxDurationMs`. One
operation represents the run; each `invoke` step is a child operation with a derived key. A failed step stops the
program, and completed effects are never rolled back.

A program is content-addressed by its digest. Registered once (`programs/register`), it is run by digest with new
arguments, and its `name`, `description` and `input` schema are what a model needs to use it as a tool
([writing programs](guides/programs.md)).

## Gateways

A gateway is a server whose devices are its upstreams' devices, namespaced (`bench/stage-z`). It adds what one device
server cannot ([spec 7.6](../../spec/bhms/07-leases-and-authority.md#76-gateways-notes)):

- **Principals and scopes** per token or uid, with narrowed bounds per action (`bounds` in the policy). A principal sees
  the narrowed schema in its descriptions, and is held to it.
- **Its own durable journal.** Before forwarding an invoke it records the intent, and it derives a deterministic upstream
  key, so a restarted gateway re-sends the same key and the upstream deduplicates.
- **Cross-device leases**, acquired upstream in a fixed order, and a **stop fan-out** that bypasses every queue.
- **Compact bridges** that serve microcontrollers as ordinary devices.

Scope patterns are `invoke:<deviceGlob>/<actionGlob>`, split at the last `/`. Behind a gateway `invoke:bench/*` names a
device called `bench` and matches nothing; you want `invoke:bench/*/*`. `bhms gateway check-policy` shows what every scope
matches ([deploying a gateway](guides/gateway.md)).

## The compact binding (microcontrollers)

A microcontroller cannot parse JSON. **BHMS-Compact** is a fixed-layout binary protocol between a gateway and the board,
carried in HDLC-style `HM` frames over UART or USB CDC ([spec 11](../../spec/bhms/11-compact-binding.md)). The
specification's typical INVOKE (at most 8 argument bytes) is 42 bytes on the wire before byte-stuffing and stays within
64 bytes ([spec 11.3](../../spec/bhms/11-compact-binding.md#113-size-budget)); the measured requests of the reference
endpoint were 35 to 37 bytes ([performance](performance.md), budget B5).

- The board reports, in its `HELLO`, the first 8 bytes of its description's digest. The gateway holds the full
  description as a **sidecar** JSON file and serves the board only when the digests match.
- The board keeps a **boot epoch** (ideally a persistent counter incremented before any effect is possible) and a small
  **replay ring** of recent operation handles, so a retransmitted command is answered, not executed twice. Without a
  persistent epoch the gateway never retransmits a command; it asks instead.
- The gateway keeps the durable journal and does all JSON-RPC work; the board keeps its local limits, fence floor and
  stop procedure. `STOP` frames bypass everything else on the link.

The C library (`sdk/c`, no heap, ATmega328P class and up) and its Arduino wrapper implement the endpoint
([Arduino guide](guides/arduino.md), [BHMS Arm](guides/bhms-arm.md)).

## Agents

Models do not see the protocol. They get eight tools (`bhms_find`, `bhms_describe`, `bhms_read`, `bhms_invoke`,
`bhms_operation`, `bhms_cancel`, `bhms_stop`, `bhms_run_program`) through the MCP bridge or the OpenAI adapter
([spec 12](../../spec/bhms/12-agent-surface.md), [connecting agents](guides/connecting-agents.md)). Every result starts with a
one-line summary; every refusal says what to change. The bridge checks arguments before anything could act, uses
operation keys, holds leases for exactly the resources an action needs, and treats text that comes from devices as
data, never as instructions.

## Conformance profiles

A conformance claim names the protocol version and the profiles it covers
([spec 14](../../spec/bhms/14-conformance.md)): `core` (every server), `leases`, `events`, `programs`, `registry`,
`authority` (more than one principal, or a scope policy), `gateway`, `compact`, `ws`, `http` and `agent` (MCP bridges and
function-tool adapters). `bhms conformance` runs the checks. A claim is supported only when every row of the profile
passed or is not applicable with a reason; a skipped row is not a pass, and a claim against arbitrary devices (rather
than the conformance device, which counts every physical command) is a generic report that supports no claim
([running conformance](guides/conformance.md)).
