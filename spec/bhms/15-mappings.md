# 15. Mappings to other ecosystems (informative)

Each table maps BHMS concepts to a neighbouring standard and says what survives
the mapping (**preserved**) and what does not (**lost**). "Lost" means the other
side has no place to carry it; a bridge must then keep it on the BHMS side (for
example in the gateway journal) or refuse.

## 15.1 BHMS ↔ MCP (2026-07-28)

| BHMS | MCP | Preserved | Lost |
|---|---|---|---|
| JSON-RPC 2.0, stateless requests, `_meta` per request | Same model (`io.modelcontextprotocol/*` keys) | Version per request, client info, trace context | — |
| `server/discover` | `server/discover` | Versions, identity, capabilities, instructions | BHMS `epoch`, `limits`, `principal` have no MCP field |
| `subscriptions/listen` + ack | `subscriptions/listen` + ack | Opt-in filters, subscription id tagging, server end by listen result | Observation rate floors, event replay cursor (`after`), `endReason`; BHMS servers never send `notifications/cancelled` |
| `notifications/cancelled` | same | Request abandonment | MCP has no notion that the underlying work continues; BHMS states it (BHMS-LIF-050) |
| Device actions | Tools (via the 8 agent tools, §12) | Input schema, one-line summary, structured result, refusal hint | Per-action `effect`, `idempotency`, lease and evidence metadata appear only in `bhms_describe` content; MCP tool annotations are hints, not enforcement |
| Operation (durable, keyed) | Tool call result (`tasks` extension for long work) | Operation id and state in structured content | Durability, idempotent replay and `unknown` are BHMS-side guarantees; an MCP client that drops the call loses only its view |
| `properties/read`, events | Resources could carry them | Values as structured content | Evidence, quality and age semantics have no MCP field (kept in structured content) |
| Leases, fences, stop | — | Exposed through bridge behaviour and `bhms_stop` | No MCP primitive; MCP cannot fence a stale client |
| Error `data` (`bhmsCode`, `retry`, `mayHaveActed`) | `isError: true` tool result | Carried in structured content | MCP error codes do not encode retry safety |

## 15.2 BHMS ↔ W3C WoT Thing Description 1.1

| BHMS | WoT TD 1.1 | Preserved | Lost |
|---|---|---|---|
| `DeviceDescription` | Thing Description | id, title, description, properties, actions, events | `digest` immutability (TD `version` is informative), `resources`, `safety` |
| Property `schema` + `x-bhms-unit` | `DataSchema` + `unit` | Types, bounds, unit (TD unit is a free string; BHMS requires UCUM) | `evidence`, `readEffect`, `maxRateHz` |
| Action `input`/`output` | `input`/`output` DataSchema | Shapes and bounds | `effect`, `idempotency` (TD has only `safe`/`idempotent` booleans), `cancel`, `completionEvidence`, `maxDurationMs`, `requiresLease` |
| Operation | Action affordance with `queryaction`/`cancelaction` | Status polling, cancel | State machine with `unknown`, idempotency keys, evidence |
| Observation | `readproperty` / `observeproperty` result | Value | Quality, age, sequence, epoch |
| Forms / protocol bindings | `forms` (HTTP, CoAP, MQTT) | — | BHMS is one binding with fixed semantics; TD forms are not emitted |
| Security | `securityDefinitions` | Bearer scheme | Scopes, effective envelopes, stop authority |

A TD can be generated from a description (lossy as above). A TD can be imported
only when a commissioning step supplies the lost members; BHMS-DEV-031 forbids
guessing `measured` evidence.

## 15.3 BHMS ↔ OPC UA (Methods and Programs, Part 10)

| BHMS | OPC UA | Preserved | Lost |
|---|---|---|---|
| Device | Object node | Identity, browse name | Digest-pinned immutable description |
| Property | Variable node | Value, `EngineeringUnits` (UNECE codes; mapped to UCUM), `EURange` | `evidence`; OPC UA `StatusCode` maps to `quality` (Good → valid, Uncertain → stale/unknown, Bad → invalid) |
| Action | Method | Input/output arguments | Method calls are synchronous: no durable operation, idempotency key or `unknown` |
| Operation / program | Program state machine (Part 10: Ready, Running, Suspended, Halted) | Start, halt, state transitions | Evidence-backed `effect`; Halted does not distinguish canceled from failed |
| Leases | — (no standard locking; `LockingServices` in some companion specs) | — | Fencing |
| Events | Events and Alarms & Conditions | Ordered events, severity | Cursor replay with `gap` |
| Stop | Companion-spec methods; safety via PLC | — | BHMS stop scope separation |

## 15.4 BHMS ↔ ROS 2 actions

| BHMS | ROS 2 | Preserved | Lost |
|---|---|---|---|
| Action | Action (goal, feedback, result) | Input, output, cancel | `effect`, `idempotency`, lease metadata |
| `operationId` | Goal UUID (client-chosen) | Unique handle | BHMS ids are server-minted; idempotent replay by key has no ROS equivalent (a resent goal is a new goal) |
| States | `ACCEPTED, EXECUTING, CANCELING, SUCCEEDED, CANCELED, ABORTED` | accepted, running, completed, canceled, failed | `dispatching`, `unknown`, `rejected` (ROS rejects before acceptance), `effect` certainty |
| Cancel | `cancel_goal` | Request semantics | Orthogonal `cancel.state` (ROS folds it into CANCELING) |
| Properties | Topics / parameters | Values | Evidence, quality, age (unless the message type carries them) |
| Observations subscription | Topic subscription with QoS | Rate and depth | Rate floor semantics, quality-change delivery rule |
| Stop | — (robot-specific services, hardware E-stop) | — | Separate stop authority, fence bump |
| Leases | — | — | Exclusive resources and fencing |

## 15.5 BHMS ↔ Home Assistant services

| BHMS | Home Assistant | Preserved | Lost |
|---|---|---|---|
| Device / properties | Device / entities and their state + attributes | Values, unit of measurement | Evidence, quality (only `unavailable`/`unknown` states), sequence |
| Action | Service call (`light.turn_on`, `climate.set_temperature`) | Arguments (service fields with selectors), targets | Durable operation, completion evidence (a service call returns when sent), idempotency classes, `unknown` |
| Capability ids | Entity domains and device classes | Coarse type | Namespaced, versioned capability ids |
| Events | Event bus (`state_changed`) | Ordered events | Cursor replay with `gap` |
| Authority | Long-lived access tokens (all-or-nothing admin) | Bearer identity | Scopes, envelopes, stop authority |
| Stop | — | — | Stop as a separate path |

A Home Assistant adapter must report completion as `reported` (or `none`) unless a
separate sensor verifies it, and must map `unavailable` to `quality: "invalid"`.
