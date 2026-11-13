# 1. Overview

## 1.1 Roles

- **Client** — an agent, a program or a human tool. It sends requests and opts in
  to notifications.
- **Server** — exposes one or more devices. A *device server* is usually a small
  process next to the hardware, built with a BHMS SDK.
- **Gateway** — a server that is also a client of many servers. It aggregates
  devices, adds authority, policy and cross-device leases, keeps its own durable
  journal, and bridges BHMS-Compact links to microcontrollers.

Every server speaks the same protocol. A client cannot tell a gateway from a
direct server except through declared capabilities (`capabilities.gateway`).

```
 agent / program / human tool
            │  JSON-RPC 2.0 (stdio, Unix/TCP, WebSocket, Streamable HTTP)
            ▼
 ┌──────────────────────┐
 │ gateway (optional)   │  authority, policy, cross-device leases, journal
 └──────────────────────┘
      │ JSON-RPC            │ BHMS-Compact (HM frames over UART/USB)
      ▼                     ▼
 device server          microcontroller endpoint
```

## 1.2 Design principles

1. **Small core, explicit options.** Eleven core methods every server
   implements; leases, events and programs are advertised capabilities.
   Extensions are namespaced (§3.9).
2. **Stateless requests, server-minted state.** No handshake and no
   per-connection session. Everything that must outlive a request — operations,
   leases, cursors, subscriptions' scope — is named by an explicit id that the
   server mints and the client passes back.
3. **Honest physical semantics never weaken for convenience.**
   A transport acknowledgement is not completion. A lost reply after dispatch
   becomes `unknown`, never success or failure. A missing measurement is
   `invalid`, never zero. Unsupported means refuse. Cancellation is a request, not
   a guarantee. Stopping is not cancelling.
4. **Authority comes from the channel, never from arguments.** A model-supplied
   field cannot grant permission, raise a bound, or bypass a lease.
5. **Compact for models, precise for programs.** Device summaries fit in 400
   tokens; descriptions carry full JSON Schema 2020-12 with UCUM units.
6. **Every refusal teaches.** Errors name the field, the bound, whether the
   device may have acted, how to retry, and a hint.

## 1.3 Object model

| Object | Identity | Mutability | Chapter |
|---|---|---|---|
| Device | `deviceId` | summary status changes; description immutable per `digest` | 04 |
| Observation | `(deviceId, property, epoch, sequence)` | immutable | 05 |
| Operation | `operationId` (server-minted), `operationKey` (idempotency) | append-only history | 06 |
| Lease | `leaseId` (server-minted), `fence` | renewed, released, expired or revoked | 07 |
| Event | `cursor` (server-minted) | immutable | 09 |
| Program | `digest` (sha256 over canonical JSON) | immutable | 08 |
| Subscription | JSON-RPC id of its `subscriptions/listen` request | lives as long as that request | 03 |

## 1.4 Semantic foundations

BHMS carries forward the HMS execution semantics (operation states and evidence,
idempotency and crash windows, cancellation versus stop) from the HMS research
drafts (`spec/02-execution.md`, `spec/12-io-driver-boundary.md`) and the HMS
conformance matrix (`docs/conformance-plan.md`). Where BHMS simplifies HMS — for
example one server-wide fence counter instead of per-resource authority
generations — the simplification is stated where it occurs and never weakens a
guarantee that a conforming server claims.

## 1.5 Conventions

- JSON member names are `camelCase`. Enumerated string values are lowercase.
- Times are RFC 3339 UTC strings with a `Z` suffix (for example
  `2026-11-13T09:30:00.125Z`). Durations are integer milliseconds in fields ending
  in `Ms`, seconds in fields ending in `S`.
- Physical quantities are bare JSON numbers in the unit declared by the schema's
  `x-bhms-unit` (UCUM, §4.5). No field ever implies a unit.
- Digests are `"sha256:"` followed by 64 lowercase hex digits computed over the
  RFC 8785 (JCS) canonical JSON of the object.
- Identifiers (`deviceId`, `operationId`, …) are opaque, case-sensitive strings.

**BHMS-LIF-001** Implementations MUST encode every JSON-RPC message as UTF-8 JSON
(RFC 8259) and MUST reject numbers that are NaN or infinite.

**BHMS-LIF-002** Implementations MUST compute every BHMS digest as
`"sha256:" + hex(sha256(JCS(object)))` with RFC 8785 canonicalisation.

**BHMS-LIF-003** Timestamps MUST be RFC 3339 UTC strings ending in `Z`; servers
SHOULD emit millisecond precision.

## 1.6 Where BHMS sits

BHMS is not a robot middleware, a field bus or a safety system. It does not
replace a hardware emergency stop, a PLC safety function or a real-time control
loop; it carries intent, authority and evidence to and from the devices that run
those. Mappings to MCP, WoT TD, OPC UA, ROS 2 and Home Assistant, with what each
preserves and loses, are in [15-mappings.md](15-mappings.md).
