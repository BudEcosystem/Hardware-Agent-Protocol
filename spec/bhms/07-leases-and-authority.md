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
Renewing an `expired` lease MUST fail with `LEASE_EXPIRED`; renewing a `revoked`
lease MUST fail with `FENCED`. Releasing a lease that is not `active` MUST return
it unchanged.

**BHMS-LSE-007** An unknown `leaseId` MUST be answered with `LEASE_EXPIRED`
(servers may forget leases after they end).

## 7.3 Fencing and lease loss

**BHMS-LSE-010** For an action with `requiresLease: true`, the server MUST check at
admission and again immediately before dispatch that `leaseId` is `active`, is
held by the caller, covers every resource of the action, and that its fence is
not lower than the highest fence issued for any of those resources. Failures are
`LEASE_REQUIRED` (missing), `LEASE_EXPIRED`, `LEASE_CONFLICT` (not the caller's
or not covering) or `FENCED` (superseded).

**BHMS-LSE-011** A server that forwards work to another enforcement point (an
upstream server, a BHMS-Compact endpoint) MUST forward the fence so that the
enforcement point can reject a superseded holder, or MUST be the only path to
that device and say so with `capabilities.gateway`.

**BHMS-LSE-012** When a lease expires or is revoked while an operation admitted
under it is running, the server MUST apply the action's `onLeaseLoss`:
`finish` — let it complete and record the result; `stop` — request cancellation
and end it per §6.6; `hold` — command the device to hold its current state and end
the operation `failed` with `LEASE_EXPIRED`. No new operation and no new program
step MAY start under that lease.

**BHMS-LSE-013** A gateway granting a lease that spans upstream servers MUST
acquire the upstream leases in ascending resource-id order, MUST grant its own
lease only after all of them are held, and MUST renew and release them with its
own lease.

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
| `admin` | everything, plus other principals' operations |

`<pattern>` is `<deviceGlob>/<actionGlob>` (split at the last `/`) or
`cap:<capabilityGlob>`; `*` matches any sequence of characters.

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

**BHMS-AUTH-014** A gateway forwarding a request MUST enforce its own policy for
the client principal before forwarding, and MUST namespace idempotency keys per
client principal when forwarding (for example
`upstreamKey = "g-" + first 32 hex digits of sha256(principal + "\n" + operationKey)`), so
that two clients' keys cannot collide upstream.

## 7.5 Stop

`stop {deviceIds | scope: "all", reason, waitMs?}` → `{stops: DeviceStop[]}`.

`DeviceStop = {deviceId, outcome, evidence, canceledOperations, revokedLeases, detail?, error?}`,
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
