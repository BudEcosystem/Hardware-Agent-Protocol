# 7. Leases, stop and authority

## 7.1 Resources

A **resource** is anything that must be used exclusively: an axis, a shared work
zone, a pump head, a bus. Devices declare the resource ids their actions use
(`description.resources`, `action.resources`). Resource ids are server-scoped;
two devices that share a work zone declare the same id (`cell-a/zone-1`).

## 7.2 Leases

`leases/acquire {resources, ttlMs, waitMs?}` → `{lease}`.
`leases/renew {leaseId, ttlMs}` → `{lease}`.
`leases/release {leaseId}` → `{lease}`.

`Lease = {leaseId, resources, fence, state, acquiredAt, expiresAt, ttlMs}`,
`state` ∈ `active`, `released`, `expired`, `revoked`.

**BHMS-LSE-001** `leases/acquire` MUST be all-or-nothing: it either grants a lease
over every requested resource or holds none of them. While waiting (up to
`waitMs`), it MUST NOT hold a subset.

**BHMS-LSE-002** A server MUST NOT grant two `active` leases that share a resource.
A conflicting acquire that cannot be satisfied within `waitMs` MUST fail with
`LEASE_CONFLICT`, naming the conflicting resources in `bound` and when the
blocking lease expires in `hint`, without disclosing the holder's identity.

**BHMS-LSE-003** Every granted lease MUST receive a `fence` strictly greater than
every fence the server has issued before, across restarts (a server-wide
monotonic counter). `leases/renew` MUST NOT change the fence.

**BHMS-LSE-004** `ttlMs` outside `[capabilities.leases.minTtlMs, maxTtlMs]` and
`waitMs` above `maxWaitMs` MUST be refused with `OUT_OF_RANGE`. Unknown resources
MUST be refused with `INVALID_ARGUMENT` naming the index (`resources[2]`).

**BHMS-LSE-005** A lease belongs to the principal that acquired it. Using,
renewing or releasing it as another principal MUST fail with `LEASE_CONFLICT`.

**BHMS-LSE-006** Lease expiry MUST be evaluated on the server's monotonic clock.
Renewing an `expired` or `released` lease MUST fail with `LEASE_EXPIRED`; renewing a `revoked`
lease MUST fail with `FENCED`. Releasing a lease that is not `active` MUST return
it unchanged.

**BHMS-LSE-007** An unknown `leaseId` MUST be answered with `LEASE_EXPIRED`
(servers may forget leases after they end).

## 7.3 Fencing and lease loss

**BHMS-LSE-010** For an action with `requiresLease: true`, the server MUST check at
admission and again immediately before dispatch that `leaseId` is `active`, is
held by the caller, covers every resource of the action, and that its fence is
not lower than the highest fence issued for any of those resources. Failures,
consistent with BHMS-LSE-006 and BHMS-LSE-007:

| Lease condition | Code |
|---|---|
| `leaseId` absent | `LEASE_REQUIRED` (`bound` lists the resources the lease must cover) |
| `expired`, `released` or unknown `leaseId` | `LEASE_EXPIRED` |
| `revoked` (by `stop` or policy) | `FENCED` |
| `active` but its fence is below a resource's highest fence | `FENCED` |
| held by another principal, or not covering every resource | `LEASE_CONFLICT` |

**BHMS-LSE-011** A server that forwards work to another enforcement point (an
upstream server, a BHMS-Compact endpoint) MUST forward the fence so that the
enforcement point can reject a superseded holder, or MUST be the only path to
that device and say so with `capabilities.gateway`.

**BHMS-LSE-012** When a lease expires or is revoked while an operation admitted
under it is running, the server MUST apply the action's `onLeaseLoss`:
`finish` — let it complete and record the result; `cancel` — request cancellation
and end it per §6.6; `hold` — command the device to hold its current state and end
the operation `failed` with `LEASE_EXPIRED`. No new operation and no new program
step MAY start under that lease.

**BHMS-LSE-013** A gateway granting a lease that spans upstream servers MUST
acquire the upstream leases in ascending resource-id order, MUST grant its own
lease only after all of them are held, and MUST renew and release them with its
own lease.

**BHMS-LSE-014** While a lease is `active` on a resource, the server MUST refuse every
action that declares that resource in `resources` unless the request presents that
lease, whether or not the action declares `requiresLease` and whoever the caller is
(the holder too: holding a lease is shown by presenting it, not by identity). The
refusal is `LEASE_CONFLICT` with `field: "leaseId"` and `bound` listing the leased
resources, without disclosing the holder. A `leaseId` supplied with any action,
including one that does not declare `requiresLease`, MUST be validated as in
BHMS-LSE-010 (BHMS-LSE-005 and BHMS-LSE-007 hold for every use of a lease). Both
checks are made at admission and again immediately before dispatch; a program step
is checked like any other action and presents the program's lease when that lease
covers the step's resources. `stop` is never subject to this rule (BHMS-AUTH-020).

A lease is therefore exclusive against everyone, not only against actions that ask
for one: `requiresLease` says that an action cannot run *without* a lease; a held
lease says that nothing else may use the resource *meanwhile*.

## 7.4 Authority

A **principal** is established by the transport (BHMS-SEC-001). A server or
gateway policy grants each principal **scopes**:

| Scope | Grants |
|---|---|
| `read` | `server/discover` details, `devices/*`, retained `properties/read`, `events/read`, subscriptions, own operations |
| `invoke:<pattern>` | `actions/invoke` and fresh `transaction` reads on matching actions/properties |
| `lease` | `leases/*` |
| `stop` or `stop:<deviceGlob>` | `stop` on all or matching devices |
| `programs:run` | `programs/run` (each step also needs its `invoke` scope) |
| `programs:register` | `programs/register` |
| `operations:read` | `operations/get`, `operations/wait`, `operations/list` and operation notifications for other principals' operations (never `operations/cancel`, BHMS-OPS-054) |
| `operations:resolve` | `operations/resolve` on operations the principal can see: asking the device again and recording an operator's resolution of an `unknown` operation (§6.10) |
| `admin` | everything, plus other principals' operations |

`<pattern>` is `<deviceGlob>/<actionGlob>` (split at the last `/`) or
`cap:<capabilityGlob>`; `*` matches any sequence of characters.

**Default agent policy.** The scopes to give an AI agent for the devices it works
with are `read`, `lease`, and per device glob `invoke:<glob>/*` and `stop:<glob>`
(the Python SDK ships them as `bhms.runtime.authority.agent_scopes`). `stop` is
part of the default: when something goes wrong, stopping its own devices is the
one safe action an agent has (§12.7).

**BHMS-AUTH-015** A policy that lets a principal invoke an action with an effect on
a device SHOULD also grant that principal `stop` on the same device
(`stop:<deviceGlob>`). A principal that can start motion but cannot stop it has no
safe action on a fault. Policy tooling SHOULD report such a principal, and a scope
that matches no served device or action (`bhms gateway check-policy`).

**BHMS-AUTH-001** A server MUST derive the principal only from the transport
(BHMS-SEC-001) and MUST NOT accept any request member, argument, `_meta` key or
device-provided text as identity or authorization.

**BHMS-AUTH-002** A server MUST answer a request outside the principal's scopes
with `UNAUTHORIZED` naming the missing scope in `hint`, except that a device the
principal may not `read` MUST be reported as `UNKNOWN_DEVICE` (BHMS-DEV-010).

**BHMS-AUTH-003** An action with `effect: "hazardous"` MUST NOT be granted by an
`invoke` pattern whose action part contains `*` or by a `cap:` pattern; the scope
must name the action literally (for example `invoke:oven-*/heat`), or be `admin`.

**BHMS-AUTH-010** For every numeric or enumerated argument the server MUST enforce
the **effective envelope**: the intersection of the device's schema bounds, the
principal's policy bounds for that action, and — inside a program — the program's
input bounds that produced the value. A value outside it MUST be refused with
`OUT_OF_RANGE` whose `bound` is the effective bound.

**BHMS-AUTH-011** Policy can only narrow: an envelope computed from policy or a
program MUST NOT exceed the device's declared bounds, and an empty intersection
MUST make the action unavailable (`UNAUTHORIZED`).

**BHMS-AUTH-012** A fresh read of a property with `readEffect: "transaction"` MUST
require an `invoke` scope matching `<deviceId>/<property>` in addition to `read`.

**BHMS-AUTH-013** Revoking a scope MUST deny new admissions immediately. Operations
already admitted continue under their recorded authority and lease policy; a
server SHOULD revoke the leases of a principal whose `lease` scope is revoked.

**BHMS-AUTH-014** A gateway forwarding a request MUST enforce its own policy for the client principal before
forwarding, but only *after* its own `(principal, operationKey)` lookup (BHMS-OPS-033): a retry of an admitted request
returns the original operation even when the principal's scope was revoked since. It MUST namespace idempotency keys per
client principal when forwarding, so that two clients' keys cannot collide upstream, and the derivation MUST be
deterministic so that a restarted gateway re-sends the same upstream key and the upstream deduplicates. The pinned
formula is

```
upstreamKey = "g-" + lowercase(base32(sha256(gatewayId "\n" principal "\n" clientKey)))[0:26]
```

(`base32` is RFC 4648 without padding; `gatewayId` is the gateway's configured identity; the result is 28 characters of
`[g\-a-z2-7]`, a valid `operationKey`). A request without a client key gets a gateway-generated one first (BHMS-OPS-035).

## 7.5 Stop

`stop {deviceIds | scope: "all", reason, waitMs?}` → `{stops: DeviceStop[]}`.

`DeviceStop = {deviceId, outcome, evidence, canceledOperations, cancelRequestedOperations?, revokedLeases, detail?, error?}`,
`canceledOperations` lists operations moved to `canceled` (they had not dispatched);
`cancelRequestedOperations` lists `dispatching`, `running` and `unknown` operations on which a
cancellation was requested (their outcome is not yet known),
`outcome` ∈ `confirmed` (the stop procedure finished, with `evidence`),
`initiated` (dispatched, not yet confirmed), `unsupported` (no stop procedure;
operations were still cancelled and leases revoked), `failed` (could not be
dispatched — unreachable, unknown or invisible device).

Stop is not cancel. `operations/cancel` asks one operation to end. `stop` makes
devices execute their commissioned stop procedure, ends all their work, and
revokes their leases. A hardware emergency stop is independent of both.

**BHMS-AUTH-020** `stop` MUST require the `stop` scope (or `admin`) and MUST NOT
require, wait for, or be blocked by any lease, queue, in-flight operation, or
held resource. A server MUST process a `stop` ahead of queued ordinary requests.

**BHMS-AUTH-021** For each target device a server MUST, in this order: dispatch
the device's stop procedure (when `safety.stop` is `supported`); move its
`accepted` operations to `canceled` (`effect: "none"`); record a `stop` history
entry and a cancellation request on its `dispatching`, `running` and `unknown`
operations and on program operations with steps on it; revoke every `active`
lease covering its resources (raising their fences); emit a `stop` event.

**BHMS-AUTH-022** `outcome: "confirmed"` MUST be reported only with `reported` or
`measured` evidence that the stop procedure finished. A server MUST NOT report
`confirmed` because a process was killed, a connection closed or a command was
sent.

**BHMS-AUTH-023** A `stop` with an unknown or invisible device id MUST NOT fail the
request: that device's result is `failed` with error `UNKNOWN_DEVICE`, and the
other devices are stopped.

**BHMS-AUTH-024** `stop` MUST return within `waitMs` (default 0) plus the time to
dispatch, reporting `initiated` for devices not yet confirmed. Later outcomes
appear as `stop` events.

**BHMS-AUTH-025** If a server cannot write its journal, it MAY still execute a
`stop`, MUST mark the result `detail: "degraded-audit"`, and MUST refuse all
ordinary new operations until the journal is writable.

**BHMS-AUTH-026** A stop MUST NOT accept parameters that command motion,
setpoints or any effect other than the device's commissioned stop procedure.

## 7.6 Gateways (notes)

A gateway is a server whose devices are its upstreams' devices. What differs from a device server, normatively covered by
BHMS-DEV-002, BHMS-LSE-011, BHMS-LSE-013, BHMS-AUTH-014 and BHMS-SEC-022/061:

- *Ids.* A device is `<namespace>/<upstreamDeviceId>`; its resources are `<namespace>/<upstreamResourceId>`. Scope patterns
  split at the **last** `/` (§7.4), so `invoke:bench/*/*` means any action of any device of namespace `bench`, while
  `invoke:bench/*` names a device `bench`, which does not exist, and matches nothing. `stop:<glob>` matches the whole
  device id (`stop:bench/*`). A pattern that matches nothing fails closed without a sign; `bhms gateway check-policy
  <config>` lists what every scope of every principal matches among the served devices (BHMS-AUTH-015).
- *Descriptions.* The gateway serves its own description of a device: ids prefixed, the principal's narrowed bounds written
  into the input schemas (an empty envelope removes the action, BHMS-AUTH-011), and the digest recomputed over those bytes
  (BHMS-DEV-021), so the description (and `descriptionDigest` pin) differ per principal that has bounds.
- *Operations.* A refusal by the gateway or by the upstream before it created anything creates no visible operation
  (BHMS-OPS-040). Before it sends, the gateway durably records the intent (BHMS-OPS-003): a pending-forward record keyed
  by `(principal, operationKey)` holding the upstream request, the derived key, the upstream's epoch and the resources. A
  refusal deletes it; the upstream's answer promotes it to the operation; a record found without an answer (a retry with the
  same key, or a restart) becomes an `unknown` operation (BHMS-OPS-004, BHMS-OPS-080) whose resources are inhibited
  (BHMS-OPS-042). The gateway reconciles by re-sending the **same** upstream request only while the upstream's epoch is
  unchanged (BHMS-OPS-081) and never after a cancellation was requested, a stop covered the operation, or its deadline passed.
  The gateway mirrors the upstream along the legal transitions of §6.3: an upstream `accepted` (queued, nothing sent to
  the device) is `accepted` at the gateway until the upstream dispatches it, and an upstream `rejected` is `rejected` at the
  gateway with `effect: "none"` (a refusal before dispatch stays a refusal before dispatch); only an operation the gateway had
  already shown as `dispatching` can end `failed` with `effect: "none"`. A retained observation of a `transaction` property
  that the gateway relayed is served to a principal with read authority only (BHMS-OBS-011), with `ageMs` advanced.
- *Leases.* The gateway lease is arbitrated at the gateway; the upstream leases are held for it, in ascending resource order,
  before it is granted, and the upstream's own lease id and fence are what is forwarded (BHMS-LSE-011, BHMS-LSE-013).
- *Stop.* Fanned out to every upstream at once on a path that bypasses queues and concurrency limits; a device whose upstream
  has not answered within the deadline reports `initiated`, never `confirmed` (BHMS-AUTH-022).
- *Events.* A gateway re-records its upstreams' events in its own log with its own cursors and ids (BHMS-EVT-001).

