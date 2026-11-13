# 14. Conformance

This chapter lists every normative requirement of BHMS v0.1 with how it is
tested. The conformance suite (`bhms conformance`, Task 7) implements the
`wire`, `fault`, `transport`, `compact` and `agent` checks against a server,
gateway, endpoint or bridge under test; `schema` checks run against the schema
and example corpus; `inspection` rows need review evidence and cannot be passed
by a test run alone.

## 14.1 Profiles

A conformance claim names the protocol version and the profiles it covers.

| Profile | Applies to | Requirements |
|---|---|---|
| `core` | every server | rows marked `core` |
| `leases` | servers advertising `leases` | `core` + `leases` |
| `events` | servers advertising `events` | `core` + `events` |
| `programs` | servers advertising `programs` | `core` + `programs` |
| `registry` | servers advertising `programs.registry` | `programs` + `registry` |
| `gateway` | servers advertising `gateway` | `core` + `gateway` |
| `compact` | BHMS-Compact gateways and endpoints | `compact` |
| `ws`, `http` | WebSocket and Streamable HTTP bindings | `ws` / `http` |
| `agent` | MCP bridges and function-tool adapters | `agent` |

## 14.2 Test methods

| Method | Meaning |
|---|---|
| `schema` | Static check of messages against `bhms.schema.json` and the example corpus |
| `wire` | Black-box requests to the implementation under test, checking responses and device-side counters of the conformance device |
| `fault` | Fault injection: process kill and restart, dropped or delayed replies, link loss, clock steps, stalled devices |
| `transport` | Binding-level checks (framing, headers, cancellation by stream close) |
| `compact` | Byte-level vectors and a simulated endpoint or gateway on a BHMS-Compact link |
| `agent` | Tool listing and tool-call checks against a bridge, including model-free scripted calls |
| `inspection` | Review of code, configuration or documentation; recorded as evidence, never as an automated pass |

The `wire` and `fault` methods rely on the **conformance device**: a device
server fixture (Task 7) that counts every physical command it receives, so a
test can prove "no effect" and "exactly one effect" instead of inferring them
from responses. HMS matrix ids (`docs/conformance-plan.md`) are cited where a
row covers one.

## 14.3 Claims and reports

**BHMS-CNF-001** A conformance claim MUST state the protocol version, the profiles
claimed, the transports tested and the implementation's name and version.

**BHMS-CNF-002** A conformance report MUST list every requirement of the claimed
profiles with one status: `passed`, `failed`, `skipped`, or `not-applicable`
with a reason. A skipped row is not a pass.

**BHMS-CNF-003** Each result MUST record the requirement ID, the schema digest,
the implementation commit, the transport, the random seed and the exact command
that reproduces it.

**BHMS-CNF-004** A profile MAY be claimed only when every row of that profile has
passed or is `not-applicable` with a reason.

**BHMS-CNF-005** A report MUST state whether devices were physical or simulated.
Passing against simulated devices is not evidence of physical behaviour
(stopping time, measured evidence quality).

**BHMS-CNF-006** An implementation's message validator MUST accept every valid
example in `spec/bhms/examples/` and reject every `invalid-*` example.

## 14.4 Requirement index

Level is the strongest keyword in the requirement. The summary is the first
sentence of the requirement; the chapter text is normative.

### LIF

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-LIF-001 | MUST | core | Implementations MUST encode every JSON-RPC message as UTF-8 JSON (RFC 8259) and MUST reject numbers that are NaN or infinite. (01) | wire | Send a request containing NaN/Infinity tokens and invalid UTF-8; expect -32700 or INVALID_ARGUMENT, never acceptance. |
| BHMS-LIF-002 | MUST | core | Implementations MUST compute every BHMS digest as `"sha256:" + hex(sha256(JCS(object)))` with RFC 8785 canonicalisation. (01) | schema | Recompute every digest in example and live describe/program results with JCS; must match byte-for-byte. |
| BHMS-LIF-003 | MUST | core | Timestamps MUST be RFC 3339 UTC strings ending in `Z`; servers SHOULD emit millisecond precision. (01) | schema | Every time field in live results matches the RFC 3339 Z pattern. |
| BHMS-LIF-010 | MUST | core | A request MUST carry an `id` that is a string or an integer (never `null`) and that is unique among the sender's requests still awaiting a response. (03) | wire | Send id null and an object id; expect -32600; duplicate in-flight ids are not required to be detected but must not crash. |
| BHMS-LIF-011 | MUST | core | A request MUST carry a `params` object. (03) | wire | Omit params, omit _meta, omit bhms/protocolVersion; each gets INVALID_ARGUMENT naming _meta.bhms/protocolVersion. |
| BHMS-LIF-012 | MUST | core | Every result MUST carry `resultType`. (03) | wire | Every result of every method carries resultType complete (schema-validate all responses). |
| BHMS-LIF-013 | MUST | core | A server MUST answer an unknown method with `-32601` (Method not found). (03) | wire | Unknown method gets -32601; an un-advertised optional method gets UNSUPPORTED naming the capability. |
| BHMS-LIF-014 | MUST | core | A receiver MUST NOT respond to a notification. (03) | wire | Send a notification with an id-less unknown method; no response arrives. |
| BHMS-LIF-015 | MUST | core | Message objects defined by this specification are closed: a receiver MUST reject a request whose `params` contain a member the schema does not define (`INVALID_ARGUMEN… (03) | wire | Add an undeclared member to params of each method; expect INVALID_ARGUMENT naming it. |
| BHMS-LIF-016 | MUST | core | Implementations MUST NOT define keys under the `bhms/` prefix other than those in this table, and MUST ignore unknown `_meta` keys that use another prefix. (03) | wire | Send _meta with bhms/admin and com.example/x; the first is refused, the second ignored. |
| BHMS-LIF-017 | MUST | core | Clients SHOULD send `bhms/clientInfo` on every request. (03) | wire | Change bhms/clientInfo name to an admin-sounding value; authorization result unchanged. |
| BHMS-LIF-018 | MUST | gateway | A gateway forwarding a request MUST propagate `traceparent` and `tracestate` unchanged when present. (03) | wire | Send traceparent through a gateway; upstream sees the same value. |
| BHMS-LIF-019 | MUST | core | If a server does not serve the requested version it MUST answer `UNSUPPORTED_VERSION` (`-32015`) with `field: "_meta.bhms/protocolVersion"` and `bound` set to the arra… (03) | wire | Request with protocolVersion 1999-01-01; expect UNSUPPORTED_VERSION with bound listing supported versions. |
| BHMS-LIF-020 | MUST | core | Every server MUST implement `server/discover` and every core method (README "Methods"). (03) | wire | Call every core method and every method of each advertised capability; none returns -32601. |
| BHMS-LIF-021 | MUST | core | `server/discover` MUST succeed for any principal that can reach the server, and its result MUST NOT disclose devices, operations or leases. (03) | wire | server/discover as an unauthorised principal succeeds and lists no devices, operations or leases. |
| BHMS-LIF-022 | SHOULD | core | A client SHOULD call `server/discover` before other requests when it needs capabilities; it MAY instead send requests directly and handle `UNSUPPORTED_VERSION`. (03) | inspection | Client SDK documentation and behaviour: discover optional, UNSUPPORTED_VERSION handled. |
| BHMS-LIF-023 | MUST | core | A server MUST advertise `operations`, `stop` and `subscriptions`. (03) | wire | discover advertises operations, stop and subscriptions; leases present when any action requiresLease. |
| BHMS-LIF-024 | MUST | core | Capabilities MUST NOT vary between requests of the same principal within one `epoch`, except `extensions` added or removed by a configuration change that also emits `n… (03) | wire | Repeated discover calls in one epoch return identical capabilities. |
| BHMS-LIF-025 | MUST | core | A server MUST NOT require a client capability that the request did not declare in `bhms/clientCapabilities`; it MUST refuse with `UNSUPPORTED` naming the missing capab… (03) | wire | No v0.1 method may require a client capability; requests with empty clientCapabilities succeed. |
| BHMS-LIF-030 | MUST | core | A server MUST NOT rely on an earlier request on the same connection to establish version, identity, capabilities or context. (03) | wire | Send requests on fresh connections with no prior traffic; each succeeds with only its own _meta. |
| BHMS-LIF-031 | MUST | core | A server MUST mint every durable identifier itself. (03) | wire | Try to supply operationId/leaseId/cursor values the server never minted; expect INVALID_ARGUMENT or LEASE_EXPIRED. |
| BHMS-LIF-040 | MUST | core | A server MUST send `notifications/subscriptions/acknowledged` as the first message of a subscription, carrying `_meta["bhms/subscriptionId"]` equal to the listen reque… (03) | wire | Open a listen; first message is the acknowledgement with the subscription id and refused entries for bad filters. |
| BHMS-LIF-041 | MUST | core | A server MUST NOT send a notification type the client did not request, and MUST tag every notification on the subscription with `_meta["bhms/subscriptionId"]`. (03) | wire | Subscribe to operations only; trigger list changes and events; only operation notifications arrive, all tagged. |
| BHMS-LIF-042 | MUST | core | A server MUST apply authorization to every notification at delivery time; revoking a principal's read scope ends delivery of what it no longer may see. (03) | wire | Revoke read scope mid-subscription; notifications for the device stop. |
| BHMS-LIF-043 | MUST | core | A server MUST NOT deliver observations for one `(deviceId, property)` more often than `max(minIntervalMs, capabilities.observations.minIntervalMs)`. (03) | fault | Subscribe at minIntervalMs 100 to a 50 Hz property and stop reading; rate floor holds, memory bounded, terminal operation notifications retained, and the subscription ends with a listen result endReason overflow rather than blocking the device. |
| BHMS-LIF-044 | MUST | core | A subscription ends in exactly one of three ways: the client sends `notifications/cancelled` for its id or closes its stream (the server then sends nothing more, BHMS-… (03) | wire | Server shutdown and overflow each end the subscription with exactly one listen result carrying endReason (shutdown/overflow; unauthorized after credential revocation) and nothing after it; after a client cancel nothing is sent. |
| BHMS-LIF-045 | MUST | core | Subscription state MUST NOT outlive the listen request. (03) | fault | Reconnect after transport loss; no notifications until a new listen; events.after resumes without loss. |
| BHMS-LIF-046 | MUST | core | Notifications are hints about change, not a replacement for the durable record: a client that needs an operation's outcome MUST be able to obtain it with `operations/g… (03) | wire | Complete an operation with no subscription open; operations/get returns the outcome. |
| BHMS-LIF-050 | MUST | core | Request cancellation MUST NOT cancel the physical work a request started. (03) | wire | Cancel an actions/invoke request after admission; operation keeps running; cancel operations/wait; operation unaffected. |
| BHMS-LIF-051 | MUST | core | A server receiving `notifications/cancelled` for an unknown or finished request MUST ignore it. (03) | wire | Cancel an unknown request id and a finished one; server ignores both. |
| BHMS-LIF-052 | MUST | core | A server MUST NOT send `notifications/cancelled`; it is a client-to-server notification only. (03) | transport | Over the whole suite the server never emits notifications/cancelled. |
| BHMS-LIF-053 | MUST | core | Clients SHOULD apply a timeout to every request and cancel it when the timeout passes. (03) | inspection | Client SDK retries a timed-out invoke only via operations/get or the same key (code review + SDK test). |
| BHMS-LIF-060 | MUST | core | Cursors MUST be opaque strings minted by the server. (03) | wire | Send a fabricated cursor to each list method; expect INVALID_ARGUMENT field cursor. |
| BHMS-LIF-061 | MUST | core | `nextCursor` MUST be absent exactly when no further items exist at the time of the request. (03) | wire | Page through 10,000 devices with limit 100: no item lost or duplicated, nextCursor absent at the end, never more than limit. |
| BHMS-LIF-062 | MUST | core | List order MUST be deterministic: devices by `deviceId` ascending (Unicode code point), operations by `createdAt` descending then `operationId` ascending, programs by… (03) | wire | List twice; order identical and as specified. |
| BHMS-LIF-070 | MUST | core | An extension MUST be identified by a `_meta`-style key with a non-`bhms/` prefix, MUST be advertised under `capabilities.extensions`, and MUST name its methods `<prefi… (03) | wire | Advertised extension ids match the pattern; core suite passes with no extension use. |
| BHMS-LIF-071 | MUST | core | An extension MUST NOT weaken a core guarantee: it cannot make a lost reply into success, make `stop` wait on a lease, or grant authority from an argument. (03) | inspection | Review each extension against the core guarantees. |

### TRN

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-TRN-001 | MUST | core | A binding MUST deliver client requests and notifications to the server, and server responses and notifications to the client. (02) | transport | Observe that the server never emits a JSON-RPC request; clients never emit responses. |
| BHMS-TRN-002 | MUST | core | Senders MUST NOT send JSON-RPC batch arrays. (02) | wire | Send a JSON array batch; expect one -32600 error with id null. |
| BHMS-TRN-003 | MUST | core | A binding MUST allow several requests in flight at once on one connection; responses MAY arrive in any order and are correlated by `id`. (02) | wire | Issue 16 concurrent requests incl. a long operations/wait; responses correlate by id and are not serialised behind the wait. |
| BHMS-TRN-004 | MUST | core | A server MUST reject a message larger than its advertised `limits.maxMessageBytes` (at least 1 048 576 bytes) with `-32600` and MUST NOT buffer an unbounded partial me… (02) | wire | Send a message 1 byte over maxMessageBytes; expect -32600 and bounded memory. |
| BHMS-TRN-005 | MUST | core | Closing a connection MUST NOT cancel, roll back or forget any operation, lease or durable record. (02) | fault | Invoke with waitMs, drop the connection; reconnect and operations/get shows the operation continuing; lease still active. |
| BHMS-TRN-010 | MUST | core | Messages on stdio MUST be delimited by `\n` and MUST NOT contain embedded newlines. (02) | transport | Scan server stdout: one valid JSON message per line, nothing else. |
| BHMS-TRN-011 | SHOULD | core | The server SHOULD exit when stdin reaches end-of-file. (02) | transport | Close stdin; server exits within a timeout. |
| BHMS-TRN-012 | MUST | core | On stdio a client MUST cancel an in-flight request with `notifications/cancelled`; there is no per-request stream to close. (02) | transport | Cancel an operations/wait on stdio with notifications/cancelled; no response follows. |
| BHMS-TRN-020 | MUST | core | Socket bindings MUST use the stdio framing (BHMS-TRN-010). (02) | transport | Run the stdio checks over a Unix socket and TCP loopback. |
| BHMS-TRN-021 | MUST | core | A TCP listener MUST bind only to a loopback address unless the connection is protected by TLS and every request is authenticated with a bearer token (BHMS-SEC-004). (02) | inspection | Start the TCP listener without TLS on a non-loopback address; implementation must refuse to start. |
| BHMS-TRN-022 | MUST | core | A Unix-domain socket server SHOULD derive the principal from the peer credential (`SO_PEERCRED` or equivalent) and MUST create the socket with permissions no wider tha… (02) | transport | Connect from two uids; principals differ per policy; socket file mode no wider than configured. |
| BHMS-TRN-030 | MUST | ws | A WebSocket binding MUST carry exactly one JSON-RPC message per text frame and MUST negotiate the subprotocol `bhms`. (02) | transport | Upgrade without subprotocol bhms is refused; two messages in one frame are rejected. |
| BHMS-TRN-031 | MUST | ws | A WebSocket server reachable from anything but loopback MUST require `Authorization: Bearer <token>` on the upgrade request and MUST reject the upgrade with HTTP 401 w… (02) | transport | Non-loopback upgrade without/with wrong bearer token gets HTTP 401. |
| BHMS-TRN-032 | MUST | ws | On WebSocket a client MUST cancel an in-flight request with `notifications/cancelled`. (02) | transport | Cancel an in-flight wait with notifications/cancelled over WebSocket. |
| BHMS-TRN-040 | MUST | http | Each client message MUST be an HTTP POST with `Content-Type: application/json` and headers `BHMS-Protocol-Version` and `BHMS-Method` mirroring `params._meta["bhms/prot… (02) | transport | POST with mismatched BHMS-Method header gets HTTP 400 + INVALID_ARGUMENT. |
| BHMS-TRN-041 | MUST | http | The response to an ordinary request MUST be either `application/json` (one response) or `text/event-stream` whose events each carry one JSON-RPC message, ending with t… (02) | transport | subscriptions/listen answers text/event-stream; ordinary request answers application/json or SSE ending in the response. |
| BHMS-TRN-042 | MUST | http | On Streamable HTTP, closing the response stream is the cancellation signal for that request; the server MUST treat a disconnect exactly as `notifications/cancelled` (a… (02) | fault | Close the SSE stream of an actions/invoke with waitMs; the operation continues (operations/get). |
| BHMS-TRN-043 | MUST | http | Notifications sent by the client (only `notifications/cancelled`) MUST be POSTed and answered with HTTP 202 and no body. (02) | transport | POST notifications/cancelled; expect 202 with empty body. |
| BHMS-TRN-050 | MUST | core | A custom transport MUST preserve the JSON-RPC message format, the per-request `_meta` model and the cancellation semantics of this chapter, and SHOULD reuse the stdio… (02) | inspection | Custom transport documentation states framing, metadata and cancellation; runner suite passes over it. |

### DEV

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-DEV-001 | MUST | core | A `deviceId` MUST be unique within a server and MUST survive address, transport and process changes of the device. (04) | fault | Restart the device server and change its address; deviceId unchanged. Swap hardware; new digest and device.replaced event. |
| BHMS-DEV-002 | MUST | gateway | A gateway that aggregates servers MUST keep `deviceId`s unique across upstreams; it SHOULD prefix upstream ids (`<upstream>/<deviceId>`) on collision and MUST keep the… (04) | wire | Aggregate two upstreams exposing the same id; gateway ids unique and stable across gateway restart. |
| BHMS-DEV-010 | MUST | core | `devices/list` MUST return only devices the principal may read, and MUST NOT reveal through counts, cursors or errors that hidden devices exist. (04) | wire | A principal without read on a device: absent from list, UNKNOWN_DEVICE on describe, page counts unchanged. |
| BHMS-DEV-011 | MUST | core | A `DeviceSummary` SHOULD be at most 1 600 bytes of canonical JSON (about 400 tokens), and MUST be at most 4 096 bytes. (04) | wire | Measure canonical size of every DeviceSummary (<= 4096; report > 1600). |
| BHMS-DEV-012 | MUST | core | `status: "online"` MUST mean the server has had evidence of the device's reachability within its declared liveness interval. (04) | fault | Disconnect a device; status leaves online within its liveness interval. |
| BHMS-DEV-020 | MUST | core | A `DeviceDescription` MUST be immutable for a given `digest`: two describe results with the same digest MUST be byte-identical in canonical JSON. (04) | wire | Describe twice and after restart; canonical bytes identical for the same digest. |
| BHMS-DEV-021 | MUST | core | `digest` MUST equal `"sha256:" + hex(sha256(JCS(description without its digest member)))`. (04) | wire | Recompute the digest of every live description. |
| BHMS-DEV-022 | MUST | core | When `params.digest` is given and differs from the current description, the server MUST answer `STALE` with `field: "digest"` and `bound` set to the current digest (it… (04) | wire | Describe with a stale digest; expect STALE with bound = current digest (or the historical description). |
| BHMS-DEV-023 | MUST | core | A change to anything in a description (an action bound, a unit, firmware that changes behaviour, calibration that changes a schema bound) MUST produce a new digest and… (04) | wire | Change a bound in the device configuration; digest changes and devicesListChanged fires. |
| BHMS-DEV-030 | MUST | core | An action whose `effect` is not `none` MUST declare `maxDurationMs`, and the server MUST enforce it: an operation still running after `maxDurationMs` MUST be cancelled… (04) | fault | Make the device hang past maxDurationMs; operation ends failed DEADLINE_EXCEEDED or unknown, never completed. |
| BHMS-DEV-031 | MUST | core | `completionEvidence: "measured"` MUST be declared only when the server obtains an independent measurement (for example an encoder, a scale, a flow meter) that confirms… (04) | inspection | Review each measured action's evidence path; conformance device asserts verification uses the verifiedBy property. |
| BHMS-DEV-032 | MUST | core | An action's `resources` MUST be a subset of the device's `resources`. (04) | wire | Static check of every description: action resources subset of device resources; lease actions declare resources. |
| BHMS-DEV-033 | SHOULD | core | Actions with `effect: "hazardous"` SHOULD declare `requiresLease: true`. (04) | wire | Report hazardous actions without requiresLease (SHOULD). |
| BHMS-DEV-034 | MUST | core | Every `requiresFresh[i].property` MUST name a property of the same device, and the list MUST NOT name a property twice. (04) | wire | Static check: requiresFresh names existing properties of the device, each once. |
| BHMS-DEV-040 | MUST | core | An action `input` MUST be `{"type": "object", …}` with `additionalProperties: false`. (04) | wire | Static check: inputs closed; no remote $ref; server never fetches (network sandbox). |
| BHMS-DEV-041 | MUST | core | Every `number` or `integer` schema in an action `input` or `output`, a property `schema`, an event `data` schema and a program `input` MUST carry `x-bhms-unit` with a… (04) | schema | Every numeric schema in inputs, outputs, property schemas, event data and program inputs has x-bhms-unit (schema NumericUnitRule for top-level members and property schemas; deep scan for nested ones). |
| BHMS-DEV-042 | MUST | core | Units SHOULD come from the BHMS unit registry below. (04) | wire | Static check units against the registry; SDK convert refuses unknown units. |
| BHMS-DEV-043 | MUST | core | A server MUST accept a quantity object only when its `unit` equals the declared unit exactly, and MUST then treat it as the bare `value`. (04) | wire | Send {value, unit} in the declared unit (accepted), a convertible unit and an incompatible one (UNIT_MISMATCH with bound and converted hint). |
| BHMS-DEV-044 | MUST | core | A server MUST validate `arguments` against `input` before admission and MUST NOT coerce, round, clamp or default a value the client sent: a wrong type or unknown membe… (04) | wire | Send "5" for a number, 5.5 for an integer, a value 1 ulp over maximum, an unknown enum; each refused with the right code and no operation created. |
| BHMS-DEV-050 | MUST | core | A property MUST declare `readEffect: "transaction"` when a fresh acquisition changes shared device state (selects a multiplexer, consumes a FIFO, clears a latch, start… (04) | inspection | Review driver acquisition effects; conformance device exposes a transaction property and its fresh read is authorised as an effect. |
| BHMS-DEV-051 | MUST | core | `evidence` MUST describe the weakest evidence the property can deliver. (04) | inspection | Review property evidence declarations against driver behaviour. |
| BHMS-DEV-060 | MUST | core | A device with any action whose `effect` is `irreversible` or `hazardous` SHOULD declare `stop: "supported"`. (04) | wire | Report irreversible/hazardous devices without stop support; onDisconnect claims verified on a compact endpoint by cutting the link. |
| BHMS-DEV-070 | MUST | compact | The `args` of a compact layout MUST map every member of the action's `input` exactly once (a fixed-width frame cannot omit a member), and every mapped member MUST be e… (04) | schema | Static check of compact layouts: args map every input member once, each mapped member required or with a default, result fields name output members, unique indices. |
| BHMS-DEV-071 | MUST | compact | A compact field with `scale` MUST be mirrored in the description: the corresponding `input` member (and, for result fields, the `output` member; for properties, the pr… (04) | compact | Static check that every scaled field is mirrored by multipleOf and in-range bounds; send 50.05 uL to a scale-0.1 field: refused by the description validator (tolerant multipleOf) before the gateway, and 50.1 accepted. |

### OBS

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-OBS-001 | MUST | core | A missing or failed measurement MUST be reported as `quality: "invalid"` (or `"unknown"`) with `value: null`. (05) | fault | Disconnect the sensor; read returns quality invalid and value null, never 0 or the last commanded value (HMS OBS-02). |
| BHMS-OBS-002 | MUST | core | `evidence` MUST NOT be stronger than what was actually obtained: a commanded setpoint echoed by a driver is `commanded`; a value computed from a model is `estimated`;… (05) | fault | Encoder unplugged while commanding position; observation evidence is commanded or invalid, never measured. |
| BHMS-OBS-003 | MUST | core | `ageMs` MUST be computed conservatively from a monotonic clock (receipt age plus the bounded acquisition latency). (05) | fault | Delay acquisition beyond maxAgeMs and step the wall clock back; ageMs stays conservative and maxAgeMs fails (HMS OBS-01, OBS-03). |
| BHMS-OBS-004 | MUST | core | `sequence` MUST increase by at least one for every new acquisition within an `epoch`; a server MUST change `epoch` when the sequence restarts or wraps. (05) | fault | Restart the device; epoch changes and sequence restarts only with a new epoch. |
| BHMS-OBS-005 | MUST | core | When `value` is a number, `unit` MUST be present and equal to the property schema's `x-bhms-unit`. (05) | schema | Every numeric observation carries unit equal to the schema unit. |
| BHMS-OBS-006 | MUST | core | When an operation whose action's `effect` is not `none` settles on a device, the server MUST NOT afterwards return, as the retained observation of one of that device's properties that it can acquire on demand, a sample acquired before the operation settled; the next read without `maxAgeMs` or `fresh` acquires a new one. (05) | wire | Read position, move, read position again with no options: the second value is the post-move reading with a new sequence; a push-only property keeps its sample. |
| BHMS-OBS-010 | MUST | core | If a server cannot produce an observation that satisfies `maxAgeMs` or `fresh`, it MUST answer `STALE` with `field` naming the unmet parameter and `bound` its value. (05) | fault | Request maxAgeMs below achievable and fresh on a stalled sensor; expect STALE naming the field. |
| BHMS-OBS-011 | MUST | core | A fresh acquisition of a property with `readEffect: "transaction"` MUST be authorized as an effect on that property's resources (BHMS-AUTH-012) and, when `requiresLeas… (05) | wire | Fresh read of a transaction property without invoke scope (UNAUTHORIZED) and without lease (LEASE_REQUIRED); retained read succeeds. |
| BHMS-OBS-012 | MUST | core | An unknown property MUST be refused with `INVALID_ARGUMENT`, `field: "property"`, and a hint listing the device's property names. (05) | wire | Read an unknown property; INVALID_ARGUMENT with the property list in hint. |
| BHMS-OBS-020 | MUST | core | Only properties with `observable: true` MAY be subscribed; others MUST appear in the acknowledgement's `refused` list with `UNSUPPORTED`. (05) | wire | Subscribe to a non-observable property; refused entry with UNSUPPORTED. |
| BHMS-OBS-021 | MUST | core | A server MUST deliver an observation notification when a new acquisition occurs and the rate floor permits, and MUST deliver one when `quality` changes (for example `v… (05) | fault | Within the rate floor, flip sensor validity; a quality-change notification is delivered immediately. |
| BHMS-OBS-022 | MUST | core | A subscription MUST NOT by itself start device transactions on a `readEffect: "transaction"` property unless the subscribing principal is authorized for that effect. (05) | wire | Subscribe to a transaction property without invoke scope; no device transactions occur (device counter). |
| BHMS-OBS-030 | MUST | core | For every entry `{property, maxAgeMs}` of an action's `requiresFresh` (§4.4), the server MUST, at admission and again immediately before dispatch (BHMS-OPS-041), hold… (05) | fault | Make pressure stale/invalid for pump-1.dispense (requiresFresh pressure 1000 ms): invoke refused with STALE field requiresFresh[0]; stale it between acceptance and dispatch: operation rejected, no device command. |

### OPS

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-OPS-001 | MUST | core | A server MUST change `state` only along the transitions in the table, and MUST append a history entry for every change of `state`, `cancel.state` or `effect`. (06) | wire | Drive operations through every path; check each history against the transition table. |
| BHMS-OPS-002 | MUST | core | A terminal state MUST NOT change. (06) | fault | Inject contradicting evidence after completion; state unchanged, correction entry appended. |
| BHMS-OPS-003 | MUST | core | A server MUST record `dispatching` durably *before* the command can reach the device. (06) | fault | Make the journal read-only before dispatch; device counter shows no dispatch and the operation is rejected or accepted. |
| BHMS-OPS-004 | MUST | core | Once an operation has reached `dispatching`, a transport error, timeout, lost reply or process crash MUST result in `unknown` (or a state proven by device evidence), n… (06) | fault | Drop the device reply after dispatch; operation becomes unknown with error DEADLINE_EXCEEDED, mayHaveActed true, retry after-reconcile (HMS OP-03, OP-04); same code after a server restart and an endpoint epoch change. |
| BHMS-OPS-005 | MUST | core | An operation may leave `unknown` only through a `reconciliation` history entry that names its evidence (a device query, a compact replay-ring answer, a measurement). (06) | fault | Reconcile an unknown operation via device query; history retains the unknown entry and a reconciliation entry names evidence. |
| BHMS-OPS-006 | MUST | core | `rejected` and `canceled`-from-`accepted` operations MUST have `effect: "none"`. (06) | wire | Check effect for rejected, canceled-before-dispatch, completed (measured/reported) and none-class actions. |
| BHMS-OPS-007 | MUST | core | When `require.effect` is `"verified"`, the server MUST refuse at admission with `UNSUPPORTED` if the action's `completionEvidence` is not `measured`, and MUST NOT mark… (06) | wire | require verified on a reported action (UNSUPPORTED); on a measured action with a failing sensor (failed UNVERIFIED). |
| BHMS-OPS-008 | MUST | core | `result` MUST be present exactly when `state` is `completed` and MUST validate against the action's `output` schema. (06) | wire | Validate result against output schema; result absent in every non-completed state. |
| BHMS-OPS-009 | MUST | core | `failed`, `rejected` and `unknown` operations MUST carry `error`. (06) | wire | Every failed/rejected/unknown operation carries error; dispatched ones have mayHaveActed true. |
| BHMS-OPS-030 | MUST | core | For each principal, a server MUST map an `operationKey` to at most one operation. (06) | wire | Repeat an invoke with the same key and intent 3 times; same operationId, replayed true, one device effect (HMS OP-01). |
| BHMS-OPS-031 | MUST | core | A request whose key exists with a different `requestDigest` MUST be refused with `KEY_CONFLICT`, carrying `operationId` of the existing operation, and MUST NOT create… (06) | wire | Reuse a key with different arguments; KEY_CONFLICT with operationId, no new operation, no effect (HMS OP-02). |
| BHMS-OPS-032 | MUST | core | Concurrent requests with the same principal and key MUST produce exactly one operation; all of them return it. (06) | wire | Fire 20 concurrent identical keyed invokes; exactly one operation and one device effect. |
| BHMS-OPS-033 | MUST | core | A server MUST look up `(principal, operationKey)` immediately after validating the params shape and authenticating the principal, before resolving the device or action… (06) | fault | Lose the reply of a keyed invoke, then revoke the invoke scope / let the lease expire / publish a description without the action; a same-key retry returns the original operation with replayed true (no UNAUTHORIZED/UNKNOWN_ACTION/LEASE_EXPIRED). |
| BHMS-OPS-034 | MUST | core | A server with `capabilities.operations.durable: true` MUST retain key mappings and operation records for at least `keyRetentionS` seconds (≥ 86 400) across restarts, a… (06) | fault | Restart a durable server; keys and operations survive and epoch is unchanged; wipe its store; epoch changes (HMS OP-05). |
| BHMS-OPS-035 | MUST | core | When `operationKey` is absent, the server MUST generate a unique key, set `keyOrigin: "server"`, and treat a re-sent request as a new operation. (06) | wire | Invoke twice without key; two operations with keyOrigin server. |
| BHMS-OPS-036 | MUST | core | A client MUST NOT reuse an `operationKey` for a different intent, and MUST NOT reuse any key after `keyRetentionS` has passed since its first use. (06) | inspection | Client SDK generates fresh keys per intent and documents the retention window; spec lists this as a weakening relative to HMS (01 §1.4). |
| BHMS-OPS-037 | MUST | core | Keys starting with `d-` are reserved for derived program-step keys and keys starting with `g-` for gateways forwarding on behalf of their clients (BHMS-AUTH-014). (06) | wire | Send operationKey d-123 (INVALID_ARGUMENT field operationKey); derived child keys use d-; a non-gateway principal sending g- keys is refused when configured. |
| BHMS-OPS-040 | MUST | core | Steps 1–9 MUST complete before an operation is created. (06) | wire | Each admission refusal of a new key returns a JSON-RPC error with mayHaveActed false and creates no operation; KEY_CONFLICT on a dispatched operation carries its operationId and mayHaveActed true. |
| BHMS-OPS-041 | MUST | core | Checks that depend on time (lease validity and fence, deadline, device reachability, preconditions) MUST be repeated immediately before dispatch. (06) | fault | Expire the lease or the deadline between acceptance and dispatch; operation rejected, effect none, no device command. |
| BHMS-OPS-042 | MUST | core | While an operation whose action has `effect` other than `none` is `unknown`, the server MUST refuse new operations that use any of its resources with `STALE` naming th… (06) | fault | Leave an operation unknown; new invokes on its resources get STALE naming it; a reconnect, gateway restart or HELLO from a non-persistent endpoint does not lift it; a confirmed stop, a persistent epoch advance or an accepted NEW_SESSION does. |
| BHMS-OPS-050 | MUST | core | Cancelling an `accepted` operation MUST prevent dispatch and make it `canceled` with `cancel.state: "confirmed"` and `effect: "none"`. (06) | wire | Cancel an accepted (queued) operation; canceled, confirmed, effect none, device counter unchanged. |
| BHMS-OPS-051 | MUST | core | Cancelling an operation whose action declares `cancel: "unsupported"` MUST set `cancel.state: "refused"` (not an error) and MUST NOT change `state`. (06) | wire | Cancel an action with cancel unsupported; cancel.state refused, state unchanged. |
| BHMS-OPS-052 | MUST | core | `acknowledged` MUST mean only that the device or adapter received the request. (06) | fault | Drop the termination evidence after acknowledgement; state not canceled; completion racing cancel wins cleanly (HMS CANCEL-01). |
| BHMS-OPS-053 | MUST | core | Cancelling a settled-terminal operation MUST return it unchanged. (06) | wire | Cancel a completed operation (unchanged) and an unknown operation (request recorded). |
| BHMS-OPS-054 | MUST | core | Only the principal that created an operation, or one with the `admin` scope, MAY cancel it; others MUST receive `UNAUTHORIZED`. (06) | wire | Cancel another principal's operation; UNAUTHORIZED. Cancel without holding the lease succeeds. |
| BHMS-OPS-055 | MUST | agent | `canceled` MUST NOT be presented as "safe" or "at rest". (06) | agent | Bridge summaries for canceled operations never say stopped or safe. |
| BHMS-OPS-060 | MUST | core | `operations/wait` MUST return as soon as the operation is settled, or when `timeoutMs` elapses, whichever is first. (06) | wire | wait on a running operation with a short timeout returns it non-settled without error; timeout above maxWaitMs is OUT_OF_RANGE. |
| BHMS-OPS-061 | MUST | core | `waitMs` on `actions/invoke` and `programs/run` MUST behave like `operations/wait` after admission; a server MUST NOT fail an admitted operation because the response w… (06) | wire | invoke with waitMs shorter than the action returns accepted/running without failing it. |
| BHMS-OPS-062 | MUST | core | An unknown or invisible `operationId` MUST be answered with `INVALID_ARGUMENT`, `field: "operationId"`. (06) | wire | get another principal's operation id and a fabricated id; both INVALID_ARGUMENT field operationId. |
| BHMS-OPS-063 | MUST | core | An operation that a client has seen MUST remain retrievable with `operations/get` for at least `keyRetentionS` seconds after it settled. (06) | wire | Read a settled operation after a server restart within retention. |
| BHMS-OPS-070 | MUST | core | If `deadlineAt` passes before dispatch, the operation MUST become `rejected` with `DEADLINE_EXCEEDED` and `mayHaveActed: false`. (06) | fault | Queue behind a busy device with a short deadline; rejected DEADLINE_EXCEEDED mayHaveActed false, no device command. |
| BHMS-OPS-071 | MUST | core | If `deadlineAt` or the action's `maxDurationMs` passes while the operation is `dispatching` or `running`, the server MUST request cancellation when the action supports… (06) | fault | Run past deadline; cancel requested; ends failed DEADLINE_EXCEEDED mayHaveActed true or unknown. |
| BHMS-OPS-080 | MUST | core | On restart a server MUST move every action operation found in `dispatching` or `running` to `unknown` (error per BHMS-OPS-004), and settle program operations per BHMS-… (06) | fault | SIGKILL the server in dispatching/running (test_crash_after_dispatch_becomes_unknown); after restart the operation is unknown before any conflicting request is admitted (HMS OP-03). |
| BHMS-OPS-081 | MUST | core | A server MUST NOT re-send to a device a command whose operation was `dispatching` or later, unless the device's own replay protection guarantees it will not act twice… (06) | fault | After the crash above, the device command counter shows no resend. |
| BHMS-OPS-090 | MUST | core | A server MUST deliver `notifications/operation` to matching subscriptions for every change of `state`, `cancel.state` or `effect`, with the operation (without `history… (06) | wire | Subscribe to operations; every state/cancel/effect change produces one notification, in order. |

### LSE

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-LSE-001 | MUST | leases | `leases/acquire` MUST be all-or-nothing: it either grants a lease over every requested resource or holds none of them. (07) | wire | Acquire [A,B] while B is held; nothing held during the wait; A free for others meanwhile. |
| BHMS-LSE-002 | MUST | leases | A server MUST NOT grant two `active` leases that share a resource. (07) | wire | Two principals acquire overlapping resources; one gets LEASE_CONFLICT naming resources and expiry, no holder id (HMS LEASE-01). |
| BHMS-LSE-003 | MUST | leases | Every granted lease MUST receive a `fence` strictly greater than every fence the server has issued before, across restarts (a server-wide monotonic counter). (07) | fault | Fences strictly increase across acquires and across a server restart; renew keeps the fence. |
| BHMS-LSE-004 | MUST | leases | `ttlMs` outside `[capabilities.leases.minTtlMs, maxTtlMs]` and `waitMs` above `maxWaitMs` MUST be refused with `OUT_OF_RANGE`. (07) | wire | ttlMs below min/above max and waitMs above max are OUT_OF_RANGE; unknown resource names its index. |
| BHMS-LSE-005 | MUST | leases | A lease belongs to the principal that acquired it. (07) | wire | Use, renew and release another principal's lease; LEASE_CONFLICT each time. |
| BHMS-LSE-006 | MUST | leases | Lease expiry MUST be evaluated on the server's monotonic clock. (07) | fault | Step the wall clock; expiry follows the monotonic clock. Renew expired (LEASE_EXPIRED) and revoked (FENCED) leases. |
| BHMS-LSE-007 | MUST | leases | An unknown `leaseId` MUST be answered with `LEASE_EXPIRED` (servers may forget leases after they end). (07) | wire | Use a fabricated leaseId; LEASE_EXPIRED. |
| BHMS-LSE-010 | MUST | leases | For an action with `requiresLease: true`, the server MUST check at admission and again immediately before dispatch that `leaseId` is `active`, is held by the caller, c… (07) | wire | Invoke with no lease (LEASE_REQUIRED), expired/released/unknown (LEASE_EXPIRED), revoked by stop and superseded (FENCED), foreign and non-covering (LEASE_CONFLICT); no dispatch in any case. |
| BHMS-LSE-011 | MUST | gateway | A server that forwards work to another enforcement point (an upstream server, a BHMS-Compact endpoint) MUST forward the fence so that the enforcement point can reject… (07) | fault | Partition a gateway, acquire a newer lease via another path, replay the old holder's command; endpoint rejects it (HMS LEASE-02). |
| BHMS-LSE-012 | MUST | leases | When a lease expires or is revoked while an operation admitted under it is running, the server MUST apply the action's `onLeaseLoss`: `finish` — let it complete and re… (07) | fault | Expire the lease mid-operation for each onLeaseLoss value (finish, cancel, hold); behaviour as declared, no new program step starts. |
| BHMS-LSE-013 | MUST | gateway | A gateway granting a lease that spans upstream servers MUST acquire the upstream leases in ascending resource-id order, MUST grant its own lease only after all of them… (07) | wire | Cross-device lease on two upstreams; upstream leases acquired in resource order, released together. |

### AUTH

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-AUTH-001 | MUST | core | A server MUST derive the principal only from the transport (BHMS-SEC-001) and MUST NOT accept any request member, argument, `_meta` key or device-provided text as iden… (07) | wire | Put identity claims in arguments, _meta and clientInfo; authorization decisions unchanged (HMS AUTH-01). |
| BHMS-AUTH-002 | MUST | core | A server MUST answer a request outside the principal's scopes with `UNAUTHORIZED` naming the missing scope in `hint`, except that a device the principal may not `read`… (07) | wire | Invoke outside scope: UNAUTHORIZED naming scope; unreadable device: UNKNOWN_DEVICE. |
| BHMS-AUTH-003 | MUST | core | An action with `effect: "hazardous"` MUST NOT be granted by an `invoke` pattern whose action part contains `*` or by a `cap:` pattern; the scope must name the action l… (07) | wire | Grant invoke:oven-*/*; invoking a hazardous action is UNAUTHORIZED; invoke:oven-1/heat grants it. |
| BHMS-AUTH-010 | MUST | core | For every numeric or enumerated argument the server MUST enforce the **effective envelope**: the intersection of the device's schema bounds, the principal's policy bou… (07) | wire | Policy narrows volume to 200 uL; 250 is OUT_OF_RANGE with bound maximum 200; inside a program the program bound applies. |
| BHMS-AUTH-011 | MUST | core | Policy can only narrow: an envelope computed from policy or a program MUST NOT exceed the device's declared bounds, and an empty intersection MUST make the action unav… (07) | wire | Load a policy that widens a device bound; rejected. Disjoint bounds make the action UNAUTHORIZED. |
| BHMS-AUTH-012 | MUST | core | A fresh read of a property with `readEffect: "transaction"` MUST require an `invoke` scope matching `<deviceId>/<property>` in addition to `read`. (07) | wire | Fresh transaction read with read-only scope; UNAUTHORIZED. |
| BHMS-AUTH-013 | MUST | core | Revoking a scope MUST deny new admissions immediately. (07) | fault | Revoke a scope while an operation runs and a request queues; queued admission denied, running one continues (HMS AUTH-03). |
| BHMS-AUTH-014 | MUST | gateway | A gateway forwarding a request MUST enforce its own policy for the client principal before forwarding, but only after its own key lookup, and MUST namespace idempotency keys per client principal with the pinned deterministic formula (g- + base32(sha256(gatewayId, principal, clientKey))[:26]). (07) | wire | Two clients use the same operationKey through a gateway; upstream sees the two pinned keys and two operations; revoke the scope and replay: the original operation is returned. |
| BHMS-AUTH-020 | MUST | core | `stop` MUST require the `stop` scope (or `admin`) and MUST NOT require, wait for, or be blocked by any lease, queue, in-flight operation, or held resource. (07) | fault | Hold every resource with long leases from another principal and saturate the queue; stop still dispatches within its budget. |
| BHMS-AUTH-021 | MUST | core | For each target device a server MUST, in this order: dispatch the device's stop procedure (when `safety.stop` is `supported`); move its `accepted` operations to `cance… (07) | wire | Stop a device with accepted, running and unknown operations and active leases; check order effects, history entries, revocations and event. |
| BHMS-AUTH-022 | MUST | core | `outcome: "confirmed"` MUST be reported only with `reported` or `measured` evidence that the stop procedure finished. (07) | fault | Kill the device process during stop; outcome is not confirmed. |
| BHMS-AUTH-023 | MUST | core | A `stop` with an unknown or invisible device id MUST NOT fail the request: that device's result is `failed` with error `UNKNOWN_DEVICE`, and the other devices are stop… (07) | wire | Stop [known, unknown] devices; known stopped, unknown failed UNKNOWN_DEVICE, request succeeds. |
| BHMS-AUTH-024 | MUST | core | `stop` MUST return within `waitMs` (default 0) plus the time to dispatch, reporting `initiated` for devices not yet confirmed. (07) | wire | stop with waitMs 0 returns initiated promptly; a later stop event carries the confirmation. |
| BHMS-AUTH-025 | MUST | core | If a server cannot write its journal, it MAY still execute a `stop`, MUST mark the result `detail: "degraded-audit"`, and MUST refuse all ordinary new operations until… (07) | fault | Make the journal unwritable; stop executes with degraded-audit; ordinary invokes refused until restored. |
| BHMS-AUTH-026 | MUST | core | A stop MUST NOT accept parameters that command motion, setpoints or any effect other than the device's commissioned stop procedure. (07) | schema | StopParams is closed: motion parameters are rejected by the schema. |

### PRG

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-PRG-001 | MUST | programs | A server MUST validate the whole program and its arguments before starting any step, and MUST refuse an invalid program with a JSON-RPC error (`INVALID_ARGUMENT` or `O… (08) | wire | Submit programs with each class of defect; JSON-RPC error with program path, no operation, no device effect (HMS MCU-01). |
| BHMS-PRG-002 | MUST | programs | Validation MUST reject: unknown step kinds or members; unknown devices, actions or properties; references to undefined variables or variables defined later; a variable… (08) | wire | Undefined variable, forward reference, shadowed input, depth-5 predicate and each limit exceeded; all refused. |
| BHMS-PRG-003 | MUST | programs | A `repeat.times` reference MUST name a required integer input whose schema `minimum` is at least 1 and `maximum` at most `maxRepeat`; validation MUST use that maximum… (08) | wire | repeat.times referencing an input with maximum 2000, minimum 0, a non-integer or an optional input is refused. |
| BHMS-PRG-004 | MUST | programs | The server MUST compute the worst-case duration as the sum, over the flattened steps with repeats multiplied out, of the per-kind durations in §8.2, and MUST refuse th… (08) | wire | Declared maxDurationMs one ms below the computed worst case is OUT_OF_RANGE with bound = computed value. |
| BHMS-PRG-005 | MUST | programs | For every literal argument the server MUST check the action `input` and the caller's effective envelope at validation time. (08) | wire | Literal out of range and an input whose bounds exceed the action envelope are refused before any step. |
| BHMS-PRG-006 | MUST | programs | Before the first step, the server MUST verify that the caller has `programs:run` and an `invoke` scope for every `invoke` step and every fresh `transaction` read, and… (08) | wire | Run without programs:run, without a step's invoke scope, without a covering lease; refused before step 1. |
| BHMS-PRG-007 | MUST | programs | The program `digest` MUST be the BHMS digest of the program object. (08) | schema | Program digests in results equal the JCS digest of the program. |
| BHMS-PRG-010 | MUST | programs | Steps MUST execute strictly in order, one at a time. (08) | wire | Child operations appear in order with parentOperationId and derived keys matching the formula. |
| BHMS-PRG-011 | MUST | programs | When a step fails, the program MUST start no further step. (08) | fault | Fail step 3 of 5 after an irreversible step 2; steps 4-5 never start; effects of 1-2 recorded (HMS PLAN-01). |
| BHMS-PRG-012 | MUST | programs | A server MUST enforce the declared `maxDurationMs` at run time: when it elapses, no further step starts, a running step is cancelled where supported, and the program e… (08) | fault | Slow a device so the run exceeds maxDurationMs; no further step, failed DEADLINE_EXCEEDED. |
| BHMS-PRG-013 | MUST | programs | A `waitUntil` step MUST evaluate its predicate only on observations with `quality: "valid"`, and MUST fail the program with `DEADLINE_EXCEEDED` (`mayHaveActed` per ear… (08) | fault | waitUntil with an invalid sensor times out (invalid samples never satisfy); a false assert fails with STALE and its message. |
| BHMS-PRG-014 | MUST | programs | `operations/cancel` on a program operation MUST stop further steps and forward the cancellation to the running child. (08) | wire | Cancel a program mid-step and stop its device; no further steps; child cancelled. |
| BHMS-PRG-015 | MUST | programs | The program operation's `history` MUST contain a `step` entry for every started step (with `stepIndex` and, for `invoke`, `childOperationId`), and `progress` MUST repo… (08) | wire | History has one step entry per started step; progress counts match. |
| BHMS-PRG-016 | MUST | programs | The program operation's `effect` MUST be `none` if no effectful child was dispatched, `unknown` if any child is `unknown`, `verified` if every effectful child is `veri… (08) | wire | Aggregate effect for programs with no effects, all verified, mixed and one unknown child. |
| BHMS-PRG-017 | MUST | programs | A server MUST NOT resume a program after a restart. (08) | fault | SIGKILL between steps (program ends failed INTERNAL with the last completed step), before any step (rejected), and during a step whose child becomes unknown (program unknown; settles failed once the child is reconciled); never resumes. |
| BHMS-PRG-020 | MUST | registry | A `digest` that is not registered MUST be refused with `INVALID_ARGUMENT`, `field: "digest"`. (08) | wire | programs/get and run with an unregistered digest; INVALID_ARGUMENT field digest. |
| BHMS-PRG-021 | MUST | registry | Registration MUST NOT grant authority: running a registered program re-checks the runner's scopes, envelope and lease (BHMS-PRG-005, BHMS-PRG-006) at each run. (08) | wire | Register as an admin, run as a principal lacking a step scope; UNAUTHORIZED. |
| BHMS-PRG-022 | MAY | programs | Idempotency for `programs/run` follows §6.4 with the intent `{method, digest, arguments, deadlineMs?}`; an inline program and its registered digest with the same argum… (08) | wire | Run inline then by digest with the same key and arguments; replayed true. |

### EVT

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-EVT-001 | MUST | events | Cursors MUST be opaque, server-minted and totally ordered per server; an event read twice MUST have the same cursor and content. (09) | wire | Read the same range twice; identical cursors and contents. |
| BHMS-EVT-002 | MUST | events | A server MUST record `stop`, `device.fault`, `device.epoch`, `device.replaced`, `lease.revoked` and `operation.state` transitions into `unknown` as events whenever it… (09) | wire | Trigger stop, fault, epoch change, replacement, revocation and an unknown operation; each produces an event. |
| BHMS-EVT-003 | MUST | events | Device-specific event types MUST be declared in the device description, and their `data` MUST validate against the declared schema. (09) | wire | Device-specific events are declared and their data validates. |
| BHMS-EVT-010 | MUST | events | A server MUST return events in cursor order, starting strictly after `after`. (09) | wire | events/read after a cursor returns strictly later events in order. |
| BHMS-EVT-011 | MUST | events | When `after` is older than the oldest retained event, or the log was reset (new `epoch`), the server MUST set `gap: true`. (09) | fault | Read from a cursor older than retention and across a server epoch reset; gap true (HMS STREAM-01). |
| BHMS-EVT-012 | MUST | events | A server MUST retain events for at least `capabilities.events.retentionS` seconds. (09) | wire | Events older than retentionS minus margin are still returned. |
| BHMS-EVT-013 | MUST | events | Event visibility MUST follow device read authority: an event about a device the principal cannot read MUST be skipped, without affecting cursor continuity (`gap` stays… (09) | wire | Events of unreadable devices are skipped without gap. |
| BHMS-EVT-020 | MUST | events | With `subscriptions/listen` `events.after`, the server MUST first deliver retained events after that cursor, then live events, with no duplicate and no omission betwee… (09) | fault | Listen with events.after while events are produced concurrently; no duplicate or missing cursor across the replay/live seam. |
| BHMS-EVT-030 | MUST | core | Observation notifications MUST NOT carry values larger than 64 KiB of canonical JSON; larger data MUST be returned by reference. (09) | wire | Observation notifications above 64 KiB never occur (size check on the stream). |

### ERR

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-ERR-001 | MUST | core | Every error response for a BHMS method with a code in §10.2 MUST carry `data` with `bhmsCode`, `mayHaveActed`, `retry` and `hint`, and `code` MUST equal the number ass… (10) | schema | Validate every error response against ErrorObject (number/bhmsCode agreement, required data). |
| BHMS-ERR-002 | MUST | core | Clients MUST dispatch on `data.bhmsCode`, not on `code`: three codes share `-32602`. (10) | inspection | Client SDKs dispatch on bhmsCode (code review + SDK unit test). |
| BHMS-ERR-003 | MUST | core | `message` and `hint` MUST name the offending field and its bound when there is one, and `hint` MUST say what to do next. (10) | wire | Every error names field and bound where applicable and has a non-empty hint; scan for tokens and other principals' ids. |
| BHMS-ERR-004 | MUST | core | `mayHaveActed` MUST be `true` whenever a device may have acted because of the request (for example a dispatch that timed out), and MUST be `false` only when the server… (10) | fault | Errors after dispatch carry mayHaveActed true; admission refusals false. |
| BHMS-ERR-005 | MAY | core | A server MAY override a code's default `retry` only to a more conservative class (`backoff` → `after-reconcile` → `never`), except that it MAY use `same-key` for `BUSY… (10) | wire | retry classes in errors are the default or more conservative (same-key only for pre-admission BUSY/DEVICE_UNAVAILABLE). |
| BHMS-ERR-006 | MUST | core | Error responses for JSON-RPC codes not in §10.2 (`-32700`, `-32600`, `-32601`, `-32603`) MAY omit `data`; when they carry `data` it MUST NOT contain `bhmsCode`. (10) | schema | -32601/-32600/-32700/-32603 responses carry no bhmsCode. |
| BHMS-ERR-010 | MUST | core | Implementations MUST use exactly these numbers and default retry classes, and MUST NOT emit a BHMS-range number (`-32001` … `-32019`) with any other meaning. (10) | schema | x-bhms-errors, 10-errors.md and bhms.protocol.errors agree (tests/test_schema_examples.py::test_error_tables_agree). |
| BHMS-ERR-011 | MUST | core | `UNSUPPORTED_VERSION` MUST carry `bound` = the server's supported versions. (10) | wire | Provoke UNSUPPORTED_VERSION, KEY_CONFLICT, OUT_OF_RANGE and UNIT_MISMATCH; required members present. |
| BHMS-ERR-012 | MUST | core | `DEVICE_FAULT` and `UNVERIFIED` MUST appear only as `OperationError`s of admitted operations (they describe what happened while acting), with `mayHaveActed: true`. (10) | wire | DEVICE_FAULT and UNVERIFIED appear only inside operations, with mayHaveActed true. |

### CMP

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-CMP-001 | MUST | compact | Endpoints and gateways MUST use the `HM` frame of `protocol/serial/frame.h` unchanged, `channel = 0x01`, and MUST discard frames with another channel without effect. (11) | compact | Feed frames on channel 0 and 2; endpoint ignores them without effect. |
| BHMS-CMP-002 | MUST | compact | A receiver MUST reject (with `ERROR MALFORMED` for control frames, by discarding for others) any payload whose length differs from the exact length its type and layout… (11) | compact | Every message type with length +/- 1; control frames get ERROR MALFORMED, others are discarded. |
| BHMS-CMP-003 | MUST | compact | Encoders MUST NOT pad payloads: a frame's wire length MUST be exactly 24 + payload length + the number of stuffed octets (20-byte header, 2-byte FCS, 2 flags). (11) | compact | Encode reference INVOKE vectors; wire length equals 24 + payload + stuffed octets; typical invoke <= 64 bytes. |
| BHMS-CMP-010 | MUST | compact | A gateway MUST refuse, with `INVALID_ARGUMENT` before sending anything (normally already caught by the mirrored `multipleOf` and bounds of BHMS-DEV-071), a value whose… (11) | compact | Gateway refuses non-integral scaled values, out-of-type integers and lossy f32 values before sending. |
| BHMS-CMP-011 | MUST | compact | Action and property indices are those of the layouts; a gateway MUST NOT derive them from name order. (11) | compact | Reorder action names in a description; gateway still uses layout indices. |
| BHMS-CMP-020 | MUST | compact | An endpoint SHOULD derive its non-zero boot epoch from a persistent boot counter incremented before any effect is possible, and then MUST set `PERSISTENT_EPOCH`. (11) | fault | Reboot a persistent endpoint 100 times: epochs strictly increase. Reboot a non-persistent endpoint to the same epoch: gateway still treats it as a reset (operations unknown). |
| BHMS-CMP-021 | MUST | compact | An endpoint MUST refuse every control frame except `HELLO_REQ` and `STOP` whose session differs from its current epoch with `SESSION_MISMATCH` and without effect. (11) | compact | Send INVOKE/READ/CANCEL with a wrong session; SESSION_MISMATCH, no effect; STOP with a wrong session still stops. |
| BHMS-CMP-022 | MUST | compact | When the epoch changes (or, for an endpoint without `PERSISTENT_EPOCH`, on every HELLO), the gateway MUST mark every operation dispatched before it and not yet termina… (11) | fault | Reset the endpoint mid-operation (persistent: new epoch; non-persistent: same epoch); gateway marks the operation unknown, emits device.epoch, never resends. |
| BHMS-CMP-023 | MUST | compact | `NEW_SESSION` MUST increment the epoch (persistently when `PERSISTENT_EPOCH`), clear the ring and reset `lastHandle` to 0; an endpoint with an active operation MUST ig… (11) | compact | NEW_SESSION while idle increments the epoch and clears the ring (accepted new session); while active it is ignored and the epoch is unchanged. |
| BHMS-CMP-030 | MUST | compact | Within an epoch, the gateway MUST assign operation handles in strictly increasing order starting at 1, MUST map each durably to its `operationId` before sending the IN… (11) | compact | Gateway handle sequence is strictly increasing per epoch and journaled before send; new session before 65535. |
| BHMS-CMP-031 | MUST | compact | An endpoint MUST keep a ring of at least 4 most recently accepted handles with their complete INVOKE payload and latest STATUS or RESULT. (11) | compact | Endpoint retains at least 4 handles: replay the last 4 INVOKEs; all answered from the ring. |
| BHMS-CMP-032 | MUST | compact | On INVOKE, an endpoint MUST: if the handle is in the ring and the payload is identical, re-send the latest STATUS or RESULT without acting again; if it is in the ring… (11) | compact | Retransmit identical (no re-execution), conflicting (HANDLE_CONFLICT) and evicted (HANDLE_UNKNOWN) INVOKEs; actuator counter checks. |
| BHMS-CMP-033 | MUST | compact | A gateway MAY retransmit an INVOKE (same handle, identical payload) after a missing reply **only to an endpoint with `PERSISTENT_EPOCH`** and only while no HELLO has r… (11) | fault | Drop the RESULT: to a persistent endpoint the gateway retransmits the same handle and payload; to a non-persistent endpoint it never retransmits (QUERY only); reboot the non-persistent endpoint before the retransmit window: actuator counter shows one execution. |
| BHMS-CMP-034 | MUST | compact | After a gateway restart the gateway MUST send `HELLO_REQ`; if the epoch is unchanged it MUST `QUERY` each operation recorded as `dispatching`, `running` or `unknown` a… (11) | fault | Restart the gateway mid-operation; it re-HELLOs and QUERYs, reconciling from RESULT; QUERY of a handle above lastHandle answers HANDLE_UNKNOWN without acting. |
| BHMS-CMP-035 | MUST | compact | An endpoint MUST send RESULT exactly once per handle unprompted, and again in answer to QUERY or a retransmitted INVOKE. (11) | compact | RESULT sent once unprompted, again on QUERY and on retransmit. |
| BHMS-CMP-040 | MUST | compact | An endpoint advertising `FENCING` MUST keep a fence floor (reset to 0 on each new epoch), MUST refuse an INVOKE whose non-zero fence is below the floor with `FENCED`,… (11) | compact | INVOKE with fence below floor (FENCED), fence 0 on a lease action (LEASE_REQUIRED), higher fence raises the floor. |
| BHMS-CMP-041 | MUST | compact | The gateway MUST map its lease fences to the u32 fence field monotonically per endpoint epoch. (11) | compact | Gateway fence mapping is monotonic per epoch. |
| BHMS-CMP-050 | MUST | compact | An endpoint MUST accept STOP with any session value, MUST process it before any queued work, MUST reply STOP_ACK immediately (`initiated` or `confirmed`), and MUST sen… (11) | compact | STOP with any session is answered before queued work; STOP_ACK initiated then confirmed. |
| BHMS-CMP-051 | MUST | compact | STOP MUST end every active operation on the endpoint (each then reports RESULT `canceled` or `failed`) and MUST raise the fence floor above every fence seen, so that a… (11) | compact | After STOP, active operations report canceled/failed and a pre-stop fence is FENCED. |
| BHMS-CMP-060 | MUST | compact | VALUE MUST carry quality `invalid` or `unknown` with k = 0 rather than a substituted value when no measurement exists (BHMS-OBS-001). (11) | compact | Disconnect the endpoint sensor; VALUE has quality invalid and no value bytes; gateway Observation epoch/sequence derived correctly. |

### AGT

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-AGT-001 | MUST | agent | A bridge MUST expose at most these eight tools, with exactly these names and the input schemas of `x-bhms-agent-tools`. (12) | agent | List bridge tools: at most the 8 names with schema-identical inputs; run_program/programs absent without the capabilities. |
| BHMS-AGT-002 | MUST | agent | A bridge MUST pass every tool call to BHMS methods with the bridge's own principal and MUST NOT accept identity, scopes, leases or bounds from tool arguments. (12) | agent | Tool calls carrying identity/scope/lease fields are refused by the input schema; server sees only the bridge principal (HMS AUTH-02). |
| BHMS-AGT-010 | MUST | agent | Every tool result MUST begin with a one-line summary of at most 200 characters and MUST carry the BHMS result as structured content (MCP `structuredContent`; for funct… (12) | agent | Every tool result begins with a one-line summary <= 200 chars and carries structured content. |
| BHMS-AGT-011 | MUST | agent | A summary MUST state units for every quantity, the operation's `state` and `effect` for operation results, and `quality`, `evidence` and age for observations. (12) | agent | Summaries include units, state/effect or quality/evidence/age, say replayed for replayed results, and never say done for non-completed operations. |
| BHMS-AGT-012 | MUST | agent | Device-provided text (names, descriptions, messages) MUST appear in summaries only quoted and truncated to 60 characters, and MUST NOT be presented as instructions (BH… (12) | agent | Inject an instruction-like device description; summaries quote and truncate it. |
| BHMS-AGT-013 | MUST | agent | `bhms_describe`'s signature block MUST list every action with its argument names, types, units, bounds, `effect`, `idempotency`, `requiresLease`, `cancel`, `completion… (12) | agent | bhms_describe block lists every action/property with required metadata within 400 tokens; elision is announced. |
| BHMS-AGT-014 | SHOULD | agent | `bhms_read` without `max_age_ms` and `fresh` SHOULD NOT hand a model a retained observation older than 1000 ms as if it were the current state: for a property with `readEffect: "none"` the bridge asks for `maxAgeMs: 1000`… (12) | agent | Move then read through the bridge: the value is the post-move reading; a push-only property falls back to the retained observation with its age in the summary; transaction properties are not acquired by a default read. |
| BHMS-AGT-020 | MUST | agent | Every BHMS error MUST be turned into a refusal carrying `bhmsCode`, `message`, `field`, `bound`, `mayHaveActed`, `retry` and `hint` unchanged, and the summary MUST inc… (12) | agent | Map every BHMS error to a refusal; unknown and mayHaveActed errors say 'outcome unknown — check before retrying' (HMS AGENT-02). |
| BHMS-AGT-021 | MUST | agent | Arguments that fail the tool's input schema or the action's `input` MUST be refused before any BHMS request that could act, with the field, the bound and a corrected e… (12) | agent | Out-of-schema arguments are refused before any BHMS request that could act (violations_reaching_device == 0). |
| BHMS-AGT-030 | MUST | agent | `operation_key` is optional. (12) | agent | Invoke without operation_key; summary says not retry-safe; bridge sent no key. |
| BHMS-AGT-031 | MUST | agent | Tool descriptions MUST tell the model how to retry safely: after a timeout or a lost result, call `bhms_operation` with the `operation_id` if known; otherwise call `bh… (12) | agent | Tool descriptions contain the safe-retry instructions; retry with the same key yields replayed true. |
| BHMS-AGT-032 | MUST | agent | `wait_ms` defaults to 5000 and MUST be capped at 60000 and at the server's `limits.maxWaitMs`. (12) | agent | wait_ms default 5000, capped at 60000 and maxWaitMs; unsettled results say how to keep waiting. |
| BHMS-AGT-040 | MUST | agent | For an action or program that requires a lease, the bridge MUST acquire a lease on exactly the needed resources (waitMs 0), renew it while the operation is not settled… (12) | agent | Lease-requiring invoke via the bridge acquires, renews and releases exactly the needed resources; conflicts become refusals with expiry. |
| BHMS-AGT-041 | MUST | agent | When the model supplies `operation_key`, the bridge MUST first send `actions/invoke` (or `programs/run`) **without** `leaseId`. (12) | agent | With operation_key: the bridge sends invoke without leaseId first; a retry while the original still runs and holds the bridge lease returns replayed true (no LEASE_CONFLICT); on LEASE_REQUIRED it acquires and resends with the same key. |
| BHMS-AGT-050 | MUST | agent | A function-tool adapter MUST emit the same names, descriptions and input schemas as the MCP bridge. (12) | agent | Function-tool definitions equal the MCP tool definitions and are not declared strict. |
| BHMS-AGT-051 | MUST | agent | The published input schema of a tool is the `x-bhms-agent-tools` schema made self-contained: `$ref`s are inlined (a definition used more than once or a recursive one stays once under `$defs`) and a top-le… (12) | agent | Tool schemas have no top-level oneOf and no dangling $ref; bhms_stop and bhms_run_program refuse none-or-both selectors before any request; MCP and function schemas are identical. |

### SEC

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-SEC-001 | MUST | core | A server MUST establish the principal from the transport as in the table and MUST reject requests on network transports that carry no valid credential, except `server/… (13) | wire | Network request without credential is refused (except discover without principal). |
| BHMS-SEC-002 | MUST | core | A server MUST compare bearer tokens in constant time, MUST store only their hashes, and MUST NOT log, echo or return a token. (13) | inspection | Code review: constant-time compare, hashed storage; log scan for tokens during the suite. |
| BHMS-SEC-003 | MUST | core | A stdio server MUST treat its parent as the only principal and MUST NOT open additional listeners unless configured to. (13) | transport | stdio server opens no listening sockets (inspect /proc/net). |
| BHMS-SEC-004 | MUST | core | A server on a non-loopback network address MUST use TLS (or an equivalent authenticated, encrypted channel) and bearer or mutual-TLS authentication. (13) | inspection | Non-loopback deployment configuration requires TLS and authentication. |
| BHMS-SEC-010 | MUST | core | Policy MUST default to deny: a principal with no matching scope has no access beyond `server/discover`. (13) | wire | A principal with no scopes can only call server/discover. |
| BHMS-SEC-011 | MUST | gateway | Policy bounds MUST only narrow (BHMS-AUTH-011); a policy that widens a device bound MUST be rejected when loaded. (13) | wire | Policy widening a device bound fails to load. |
| BHMS-SEC-012 | MUST | gateway | A policy change MUST take effect for new admissions without a restart and MUST be recorded as a `policy.changed` event. (13) | wire | Change the policy at runtime; new admissions follow it; policy.changed event emitted. |
| BHMS-SEC-020 | MUST | agent | No implementation may derive authority, bounds, scopes, lease decisions or stop decisions from untrusted text. (13) | agent | Device text containing instructions never alters authorization or bridge behaviour (prompt-injection fixture). |
| BHMS-SEC-021 | MUST | core | Schemas embedded in descriptions MUST be validated with bounded resources (depth ≤ 32, ≤ 10 000 subschemas, time budget) and MUST NOT trigger network fetches (BHMS-DEV… (13) | wire | Describe a device whose schema is deeply nested or remote-referencing; validation bounded, no network fetch. |
| BHMS-SEC-022 | MUST | gateway | A gateway MUST verify that an upstream's description digest is correct (BHMS-DEV-021) before serving it, and MUST NOT let an upstream description widen a bound set by… (13) | wire | Upstream serving a wrong digest or a widened bound is refused/not served. |
| BHMS-SEC-030 | MUST | core | A server MUST NOT treat any argument as an authority claim. (13) | wire | Send authorized/override/force arguments; INVALID_ARGUMENT, no effect. |
| BHMS-SEC-031 | MUST | agent | Every refusal MUST be decided by the server; a bridge MUST NOT retry a refused request with different authority. (13) | agent | Bridge never retries a refused request with other credentials (bridge log). |
| BHMS-SEC-040 | MUST | core | The `stop` scope MUST be grantable independently of every other scope; a principal with only `stop` can stop devices but not invoke actions, and a principal with `invo… (13) | wire | Principal with only stop can stop but not invoke; principal with invoke but no stop cannot stop. |
| BHMS-SEC-041 | MUST | core | Stop MUST remain available when the operation journal, the policy store or an upstream is degraded (BHMS-AUTH-025), but MUST still be authenticated and authorized. (13) | fault | Degrade journal, policy store and an upstream; authenticated stop still works. |
| BHMS-SEC-042 | MUST | core | Software stop is not a safety function. (13) | inspection | Documentation and tool descriptions never call stop an emergency stop. |
| BHMS-SEC-050 | MUST | compact | The FCS-16 detects corruption, not forgery. (13) | inspection | Deployment review: compact links are exclusive physical links. |
| BHMS-SEC-060 | MUST | core | A server MUST bound message size (BHMS-TRN-004), page size, waits (`limits.maxWaitMs`), subscriptions per principal, observation subscriptions per subscription (`maxOb… (13) | wire | Exceed each bound (message, page, wait, subscriptions, observations, program size/duration, schema cost); refused, memory bounded. |
| BHMS-SEC-061 | MUST | gateway | One slow or dead upstream or device MUST NOT stall requests to others: a gateway MUST apply per-upstream timeouts and concurrency limits and answer `DEVICE_UNAVAILABLE… (13) | fault | Stall one upstream; requests to other upstreams keep their latency (test_stalled_server_isolated). |

### CNF

| ID | Level | Profile | Requirement | Method | Test |
|---|---|---|---|---|---|
| BHMS-CNF-001 | MUST | core | A conformance claim MUST state the protocol version, the profiles claimed, the transports tested and the implementation's name and version. (14) | inspection | Conformance report lists version, profiles, transports and implementation identity. |
| BHMS-CNF-002 | MUST | core | A conformance report MUST list every requirement of the claimed profiles with one status: `passed`, `failed`, `skipped`, or `not-applicable` with a reason. (14) | inspection | Report contains one row per applicable ID with an allowed status. |
| BHMS-CNF-003 | MUST | core | Each result MUST record the requirement ID, the schema digest, the implementation commit, the transport, the random seed and the exact command that reproduces it. (14) | inspection | Report records the evidence fields. |
| BHMS-CNF-004 | MAY | core | A profile MAY be claimed only when every row of that profile has passed or is `not-applicable` with a reason. (14) | inspection | Profile claims are backed by passing rows for all of the profile's IDs. |
| BHMS-CNF-005 | MUST | core | A report MUST state whether devices were physical or simulated. (14) | inspection | Reports with simulated devices say so. |
| BHMS-CNF-006 | MUST | core | An implementation's message validator MUST accept every valid example in `spec/bhms/examples/` and reject every `invalid-*` example. (14) | schema | Run the example corpus through the implementation's validator: valid accepted, invalid rejected. |

Total: 247 requirements — agent 17, compact 17, fault 48, inspection 19, schema 11, transport 14, wire 121.
