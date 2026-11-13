# 3. Messages, lifecycle and discovery

BHMS has no handshake. Every request is self-describing: it carries its protocol
version (and optionally client identity and capabilities) in `params._meta`, and
the server processes it independently of any earlier request on the same
connection.

## 3.1 Messages

BHMS uses JSON-RPC 2.0 requests, result responses, error responses and
notifications.

**BHMS-LIF-010** A request MUST carry an `id` that is a string or an integer
(never `null`) and that is unique among the sender's requests still awaiting a
response.

**BHMS-LIF-011** A request MUST carry a `params` object. `params._meta` MUST be
present and MUST contain `bhms/protocolVersion`. A server MUST reject a request
without it with `INVALID_ARGUMENT` (`-32602`), `field: "_meta.bhms/protocolVersion"`.

**BHMS-LIF-012** Every result MUST carry `resultType`. In this version the only
value is `"complete"`. A client MUST treat any other value as an invalid result.

**BHMS-LIF-013** A server MUST answer an unknown method with `-32601` (Method not
found). It MUST answer a BHMS method whose capability it does not advertise with
`UNSUPPORTED` (`-32003`) and a hint naming the capability.

**BHMS-LIF-014** A receiver MUST NOT respond to a notification. Notifications
MUST NOT carry an `id`.

**BHMS-LIF-015** Message objects defined by this specification are closed: a
receiver MUST reject a request whose `params` contain a member the schema does
not define (`INVALID_ARGUMENT` naming the member), except inside `_meta`,
`extensions`, `arguments`, `result`, `data` and embedded JSON Schemas.

## 3.2 `_meta`

`_meta` keys have an optional prefix (dot-separated labels followed by `/`) and
a name. The prefix `bhms/` is reserved for this specification. Extensions use a
reverse-DNS prefix (`com.example/…`).

| Key | Where | Type | Meaning |
|---|---|---|---|
| `bhms/protocolVersion` | request (required) | string | Protocol version of this request |
| `bhms/clientInfo` | request | `Implementation` | Client name and version (display/logging only) |
| `bhms/clientCapabilities` | request | `ClientCapabilities` | Client capabilities relevant to this request |
| `bhms/serverInfo` | result | `Implementation` | Server name and version |
| `bhms/subscriptionId` | notification, listen result | string \| integer | The `subscriptions/listen` request this message belongs to |
| `traceparent`, `tracestate` | request | string | W3C trace context, propagated by gateways |

**BHMS-LIF-016** Implementations MUST NOT define keys under the `bhms/` prefix
other than those in this table, and MUST ignore unknown `_meta` keys that use
another prefix.

**BHMS-LIF-017** Clients SHOULD send `bhms/clientInfo` on every request. Servers
MUST NOT use `clientInfo` or `serverInfo` for any authorization decision.

**BHMS-LIF-018** A gateway forwarding a request MUST propagate `traceparent` and
`tracestate` unchanged when present.

## 3.3 Versioning

The version string is a date. This revision is `2026-11-13`.

**BHMS-LIF-019** If a server does not serve the requested version it MUST answer
`UNSUPPORTED_VERSION` (`-32015`) with `field: "_meta.bhms/protocolVersion"` and
`bound` set to the array of versions it supports. A client SHOULD retry with a
mutually supported version or report the incompatibility.

## 3.4 `server/discover`

`server/discover` returns everything a client needs to talk to a server: the
versions it supports, its identity, capabilities, limits, storage epoch,
optional guidance for models, and (when authenticated) the effective authority
of the caller.

```json
{"jsonrpc":"2.0","id":1,"method":"server/discover",
 "params":{"_meta":{"bhms/protocolVersion":"2026-11-13",
                    "bhms/clientInfo":{"name":"bhms-cli","version":"0.1.0"}}}}
```

Result members:

| Member | Type | Meaning |
|---|---|---|
| `supportedVersions` | string[] | Versions this server serves (non-empty) |
| `serverInfo` | `Implementation` | Name, version, optional title |
| `capabilities` | `ServerCapabilities` | §3.5 |
| `epoch` | string | Identity of the server's durable state; changes only when that state is lost (BHMS-OPS-034) |
| `limits` | `{maxMessageBytes, maxPageSize, maxWaitMs}` | Hard limits applied to every request |
| `instructions` | string? | Guidance for models; untrusted text (BHMS-SEC-020) |
| `principal` | `{id, scopes}`? | The authenticated principal of this request and its effective scopes |

**BHMS-LIF-020** Every server MUST implement `server/discover` and every core
method (README "Methods"). A server MUST implement each optional method exactly
when it advertises that method's capability.

**BHMS-LIF-021** `server/discover` MUST succeed for any principal that can reach
the server, and its result MUST NOT disclose devices, operations or leases.

**BHMS-LIF-022** A client SHOULD call `server/discover` before other requests
when it needs capabilities; it MAY instead send requests directly and handle
`UNSUPPORTED_VERSION`.

## 3.5 Capabilities

Capabilities are objects; absence means unsupported. An empty object means
supported with defaults.

| Capability | Members | Enables |
|---|---|---|
| `devices` | `listChanged: bool` | `devicesListChanged` subscription |
| `observations` | `subscribe: bool`, `minIntervalMs` | `observations` subscription and its rate floor |
| `operations` | `durable: bool`, `cancel: bool`, `keyRetentionS` | always present; declares durability and key window |
| `stop` | `{}` | always present (stop is core) |
| `subscriptions` | `maxObservations`, `maxOperationIds` | always present; bounds per `subscriptions/listen` |
| `leases` | `minTtlMs`, `maxTtlMs`, `maxWaitMs` | `leases/*` |
| `events` | `retentionS`, `maxPageSize` | `events/read` and `events` subscription |
| `programs` | `registry: bool`, `limits` | `programs/run`; `programs/register`, `programs/get`, `programs/list` when `registry` |
| `compact` | `links` | the server bridges BHMS-Compact endpoints |
| `gateway` | `crossDeviceLeases: bool`, `upstreams` | the server aggregates other servers |
| `extensions` | `{"<prefix>/<name>": object}` | negotiated extensions |

**BHMS-LIF-023** A server MUST advertise `operations`, `stop` and `subscriptions`.
If any action it exposes has `requiresLease: true`, it MUST advertise `leases`.

**BHMS-LIF-024** Capabilities MUST NOT vary between requests of the same
principal within one `epoch`, except `extensions` added or removed by a
configuration change that also emits `notifications/devices/listChanged`.

Client capabilities (`bhms/clientCapabilities`) are an object with optional
`extensions`; v0.1 defines no other client capability.

**BHMS-LIF-025** A server MUST NOT require a client capability that the request
did not declare in `bhms/clientCapabilities`; it MUST refuse with `UNSUPPORTED`
naming the missing capability instead.

## 3.6 Statelessness

**BHMS-LIF-030** A server MUST NOT rely on an earlier request on the same
connection to establish version, identity, capabilities or context. State that
spans requests MUST be referenced by a server-minted identifier passed
explicitly: `operationId`, `leaseId`, event `cursor`, list `cursor`, program
`digest`.

**BHMS-LIF-031** A server MUST mint every durable identifier itself. It MUST NOT
accept a client-chosen `operationId`, `leaseId` or cursor. (A client-chosen
`operationKey` is an idempotency key, not an identifier; §6.4.)

## 3.7 Subscriptions: `subscriptions/listen`

Server-to-client notifications are opted into with one long-lived request. Its
response stream carries only the notifications the client asked for, each
tagged with the request's id.

```json
{"jsonrpc":"2.0","id":"sub-1","method":"subscriptions/listen",
 "params":{"_meta":{"bhms/protocolVersion":"2026-11-13"},
  "notifications":{
    "devicesListChanged": true,
    "operations": {"deviceIds": ["pump-1"]},
    "observations": [{"deviceId":"pump-1","property":"pressure","minIntervalMs":500}],
    "events": {"after":"ev-000120","types":["device.fault"]}}}}
```

Filter members (all optional; omitting one means "not wanted"):

| Member | Type | Delivers |
|---|---|---|
| `devicesListChanged` | bool | `notifications/devices/listChanged` |
| `operations` | `{operationIds?, deviceIds?, all?}` | `notifications/operation` for matching operations |
| `observations` | `[{deviceId, property, minIntervalMs?}]` | `notifications/observation` |
| `events` | `{deviceIds?, types?, after?}` | `notifications/event`, replaying from `after` first |

**BHMS-LIF-040** A server MUST send `notifications/subscriptions/acknowledged` as
the first message of a subscription, carrying `_meta["bhms/subscriptionId"]`
equal to the listen request's id, the honoured subset of the filter in
`notifications`, and a `refused` entry (`path`, `bhmsCode`, `hint`) for every
part it will not honour.

**BHMS-LIF-041** A server MUST NOT send a notification type the client did not
request, and MUST tag every notification on the subscription with
`_meta["bhms/subscriptionId"]`.

**BHMS-LIF-042** A server MUST apply authorization to every notification at
delivery time; revoking a principal's read scope ends delivery of what it no
longer may see.

**BHMS-LIF-043** A server MUST NOT deliver observations for one
`(deviceId, property)` more often than `max(minIntervalMs, capabilities.observations.minIntervalMs)`.
It MUST bound its per-subscription queue; when a slow client overflows it, the
server MUST drop the oldest observation notifications first, MUST NOT drop
operation notifications for terminal states, and MUST end the subscription
with `endReason: "overflow"` (BHMS-LIF-044) rather than block device work.

**BHMS-LIF-044** A subscription ends in exactly one of three ways: the client
sends `notifications/cancelled` for its id or closes its stream (the server then
sends nothing more, BHMS-LIF-051); the transport closes; or the server ends it.
A server MUST end a subscription only by sending the listen result
`{resultType: "complete", endReason, _meta: {"bhms/subscriptionId": id}}` and MUST
send nothing further on it. `endReason` is one of:

| `endReason` | Meaning | Client action |
|---|---|---|
| `shutdown` | The server is stopping or restarting | Reconnect later and listen again with `events.after` |
| `overflow` | The client did not keep up (BHMS-LIF-043) | Read state with `operations/get`/`events/read`, then listen again |
| `unauthorized` | The principal's credentials or `read` scope were revoked | Do not listen again without new authority |

A transport close without a listen result is an abrupt end; the client MAY
reconnect.

**BHMS-LIF-045** Subscription state MUST NOT outlive the listen request. After a
reconnect the client MUST send a new `subscriptions/listen`; it SHOULD pass the
last event cursor it processed as `events.after` to resume without loss.

**BHMS-LIF-046** Notifications are hints about change, not a replacement for the
durable record: a client that needs an operation's outcome MUST be able to
obtain it with `operations/get`, even if it missed every notification.

## 3.8 Request cancellation

`notifications/cancelled {requestId, reason?}` abandons an in-flight request.

**BHMS-LIF-050** Request cancellation MUST NOT cancel the physical work a request
started. Cancelling an `actions/invoke` request after admission leaves the
operation running and durable; cancelling `operations/wait` only stops waiting.
To cancel physical work a client calls `operations/cancel`; to halt a device it
calls `stop`.

**BHMS-LIF-051** A server receiving `notifications/cancelled` for an unknown or
finished request MUST ignore it. After honouring a cancellation it SHOULD NOT
send a response for that request; a client MUST ignore a response that arrives
after it cancelled.

**BHMS-LIF-052** A server MUST NOT send `notifications/cancelled`; it is a
client-to-server notification only. (Unlike MCP, a server ends a subscription
solely with the listen result, BHMS-LIF-044.)

**BHMS-LIF-053** Clients SHOULD apply a timeout to every request and cancel it
when the timeout passes. A timeout on `actions/invoke` means "outcome not yet
known"; the client MUST then use `operations/get`, or retry with the same
`operationKey`, never re-issue with a new key (BHMS-OPS-031).

## 3.9 Pagination

List methods (`devices/list`, `operations/list`, `events/read`, `programs/list`)
return pages with an opaque cursor.

**BHMS-LIF-060** Cursors MUST be opaque strings minted by the server. A client
MUST NOT parse or construct them. A server MUST answer a malformed or foreign
cursor with `INVALID_ARGUMENT`, `field: "cursor"`.

**BHMS-LIF-061** `nextCursor` MUST be absent exactly when no further items exist
at the time of the request. A server MAY return fewer items than `limit`
(including zero with a `nextCursor`), and MUST NOT return more than
`min(limit, limits.maxPageSize)`.

**BHMS-LIF-062** List order MUST be deterministic: devices by `deviceId`
ascending (Unicode code point), operations by `createdAt` descending then
`operationId` ascending, programs by `digest` ascending, events by cursor order.

## 3.10 Extensions

**BHMS-LIF-070** An extension MUST be identified by a `_meta`-style key with a
non-`bhms/` prefix, MUST be advertised under `capabilities.extensions`, and MUST
name its methods `<prefix>/<name>/<method>` or `x-<name>/<method>`. A server
MUST NOT require a client to use an extension.

**BHMS-LIF-071** An extension MUST NOT weaken a core guarantee: it cannot make a
lost reply into success, make `stop` wait on a lease, or grant authority from an
argument.
