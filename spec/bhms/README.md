# BHMS — Bud HMS Protocol, version 2026-11-13 (v0.1)

BHMS lets AI agents, programs and people **discover, observe and operate physical
devices** through one small protocol. It borrows MCP's shape (JSON-RPC 2.0,
stateless requests, `server/discover`, `subscriptions/listen`) and adds the
semantics physical work needs and chat tools do not:

- **Durable operations.** Every action becomes an `Operation` with a server-minted
  id, an explicit state machine and an evidence-backed `effect`.
- **Idempotent replay.** The same `operationKey` with the same request returns the
  same operation; it never acts twice.
- **Leases with fencing.** Exclusive resources are held with a TTL and a
  monotonic fence, so a stale holder cannot act.
- **Evidence.** Observations say whether a value was measured, reported,
  commanded, estimated or simulated, how old it is, and its quality.
- **Stop.** A separate, always-available path that never waits behind leases or
  queues.
- **Bounded programs.** Validated step sequences with a declared worst-case
  duration; the vehicle for reusable "programs as tools".

The normative chapters are:

| File | Contents |
|---|---|
| [01-overview.md](01-overview.md) | Roles, architecture, design principles, conventions |
| [02-transports.md](02-transports.md) | stdio, Unix/TCP, WebSocket, Streamable HTTP, BHMS-Compact |
| [03-lifecycle.md](03-lifecycle.md) | Messages, `_meta`, versioning, `server/discover`, capabilities, subscriptions, cancellation, pagination |
| [04-devices.md](04-devices.md) | `DeviceSummary`, `DeviceDescription`, actions, properties, units, digests |
| [05-observations.md](05-observations.md) | `properties/read`, `Observation`, freshness and evidence |
| [06-operations.md](06-operations.md) | `actions/invoke`, `operations/*`, state machine, idempotency, crash windows |
| [07-leases-and-authority.md](07-leases-and-authority.md) | `leases/*`, fencing, `stop`, scopes and effective envelopes |
| [08-programs.md](08-programs.md) | Bounded program format, validation, `programs/*` |
| [09-events-and-streams.md](09-events-and-streams.md) | `events/read`, event cursors, notification streams |
| [10-errors.md](10-errors.md) | Error object, BHMS codes, retry classes |
| [11-compact-binding.md](11-compact-binding.md) | BHMS-Compact byte layouts for microcontrollers |
| [12-agent-surface.md](12-agent-surface.md) | The ≤ 8 model-facing tools for MCP and function-calling APIs |
| [13-security.md](13-security.md) | Identity, scopes, untrusted text, stop authority |
| [14-conformance.md](14-conformance.md) | Every requirement ID and how it is tested |
| [15-mappings.md](15-mappings.md) | BHMS ↔ MCP, WoT TD 1.1, OPC UA, ROS 2 actions, Home Assistant |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

Machine-readable sources:

- [`schema/bhms.schema.json`](schema/bhms.schema.json) — JSON Schema 2020-12 for every
  message, with the `x-bhms-methods`, `x-bhms-notifications`, `x-bhms-errors` and
  `x-bhms-agent-tools` maps. **The schema is the contract**: a message that fails it
  is a bug in its sender.
- [`examples/`](examples/) — one valid example per request, result, notification and
  error, plus labelled invalid examples ([convention](examples/README.md)).

## Methods

All methods are client → server requests. "Core" methods MUST be implemented by
every server; the others MUST be implemented exactly when the named capability is
advertised by `server/discover` (BHMS-LIF-020).

| Method | Tier | Params → Result | Chapter |
|---|---|---|---|
| `server/discover` | core | `{}` → `{supportedVersions, serverInfo, capabilities, epoch, limits, instructions?, principal?}` | 03 |
| `devices/list` | core | `{filter?, cursor?, limit?}` → `{devices: DeviceSummary[], nextCursor?}` | 04 |
| `devices/describe` | core | `{deviceId, digest?}` → `{description: DeviceDescription}` | 04 |
| `properties/read` | core | `{deviceId, property, maxAgeMs?, fresh?}` → `{observation}` | 05 |
| `actions/invoke` | core | `{deviceId, action, arguments, operationKey?, leaseId?, deadlineMs?, waitMs?, require?, descriptionDigest?}` → `{operation, replayed}` | 06 |
| `operations/get` | core | `{operationId}` → `{operation}` | 06 |
| `operations/wait` | core | `{operationId, timeoutMs}` → `{operation}` | 06 |
| `operations/list` | core | `{deviceId?, state?, parentOperationId?, cursor?, limit?}` → `{operations, nextCursor?}` | 06 |
| `operations/cancel` | core | `{operationId, reason?}` → `{operation}` | 06 |
| `stop` | core | `{deviceIds \| scope: "all", reason, waitMs?}` → `{stops: DeviceStop[]}` | 07 |
| `subscriptions/listen` | core | `{notifications}` → stream of notifications, then `{endReason}` when the server ends it | 03 |
| `leases/acquire` | `leases` | `{resources, ttlMs, waitMs?}` → `{lease}` | 07 |
| `leases/renew` | `leases` | `{leaseId, ttlMs}` → `{lease}` | 07 |
| `leases/release` | `leases` | `{leaseId}` → `{lease}` | 07 |
| `events/read` | `events` | `{after?, limit?, deviceId?, types?}` → `{events, cursor, gap}` | 09 |
| `programs/run` | `programs` | `{program \| digest, arguments, operationKey?, leaseId?, deadlineMs?, waitMs?}` → `{operation, replayed}` | 08 |
| `programs/register` | `programs.registry` | `{program}` → `{info: ProgramInfo}` | 08 |
| `programs/get` | `programs.registry` | `{digest}` → `{program, info}` | 08 |
| `programs/list` | `programs.registry` | `{cursor?, limit?}` → `{programs: ProgramInfo[], nextCursor?}` | 08 |
| `operations/resolve` | `operations.resolve` | `{operationId, resolution?}` → `{operation}` | 06 |

Every result additionally carries `resultType: "complete"` and MAY carry `_meta`.
Every request's `params` carries `_meta` with `bhms/protocolVersion`.

## Notifications

| Notification | Direction | Delivered on | Chapter |
|---|---|---|---|
| `notifications/subscriptions/acknowledged` | server → client | `subscriptions/listen` stream (first message) | 03 |
| `notifications/devices/listChanged` | server → client | `subscriptions/listen` (`devicesListChanged`) | 04 |
| `notifications/operation` | server → client | `subscriptions/listen` (`operations`) | 06 |
| `notifications/observation` | server → client | `subscriptions/listen` (`observations`) | 05 |
| `notifications/event` | server → client | `subscriptions/listen` (`events`) | 09 |
| `notifications/cancelled` | client → server | Abandon an in-flight request (including a subscription) | 03 |

## Conventions

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
RECOMMENDED, MAY and OPTIONAL are to be interpreted as described in BCP 14
(RFC 2119, RFC 8174) when, and only when, they appear in all capitals.

Every normative statement carries an identifier `BHMS-<AREA>-<NNN>`
(areas: LIF lifecycle, TRN transports, DEV devices, OBS observations, OPS
operations, LSE leases, AUTH authority, PRG programs, EVT events, ERR errors,
CMP compact binding, AGT agent surface, SEC security, CNF conformance).
[14-conformance.md](14-conformance.md) lists every identifier with its test.
Identifiers are never reused; a withdrawn requirement keeps its number with the
note "withdrawn".

The protocol version string for this revision is **`2026-11-13`**.
