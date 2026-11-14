# 9. Events and streams

Events are an ordered, cursor-addressed log of things that happened: devices
going online or offline, faults, stops, lease revocations, operation state
changes and device-specific occurrences. They are available by polling
(`events/read`) and live (`subscriptions/listen` with `events`).

## 9.1 The Event object

| Member | Type | Required | Meaning |
|---|---|---|---|
| `cursor` | string | yes | Server-minted position of this event |
| `time` | time | yes | When the server recorded it |
| `type` | string | yes | §9.2 |
| `severity` | `info` \| `warning` \| `error` \| `critical` | yes | |
| `deviceId` | string | no | |
| `operationId` | string | no | |
| `message` | string ≤ 1000 | no | Untrusted text |
| `data` | object | no | Valid against the type's `data` schema when the device declares one |

## 9.2 Event types

Core types (`data` members in parentheses):

| Type | Meaning |
|---|---|
| `device.online`, `device.offline`, `device.degraded` | Reachability changed |
| `device.replaced` | A device id was bound to different hardware (`previousDigest`) |
| `device.epoch` | The device restarted its sequence or session (`epoch`) |
| `device.fault` | The device reported a fault (`code?`) |
| `operation.state` | An operation changed state (`state`, `previousState`) |
| `operation.resolved` | An `unknown` operation was resolved (`state`, `source`: `device` or `operator`, `principal?`; §6.10) |
| `stop` | A stop was requested or its outcome became known (`outcome`, `reason`) |
| `lease.revoked`, `lease.expired` | A lease ended other than by release (`leaseId`) |
| `policy.changed` | The server's authorization policy changed |

Device-specific types are declared in the description's `events` map and MUST
NOT equal a core type.

**BHMS-EVT-001** Cursors MUST be opaque, server-minted and totally ordered per
server; an event read twice MUST have the same cursor and content.

**BHMS-EVT-002** A server MUST record `stop`, `device.fault`, `device.epoch`,
`device.replaced`, `lease.revoked` and `operation.state` transitions into
`unknown` as events whenever it advertises `events`.

**BHMS-EVT-003** Device-specific event types MUST be declared in the device
description, and their `data` MUST validate against the declared schema.

## 9.3 `events/read`

`{after?, limit?, deviceId?, types?}` → `{events, cursor, gap}`.

- Without `after`, reading starts at the oldest retained event.
- `cursor` in the result is the position to pass as `after` next time; when no
  events are returned it equals the given `after` (or the current head).
- `gap: true` means events between `after` and the first returned event were
  lost (retention expired or the log was reset).

**BHMS-EVT-010** A server MUST return events in cursor order, starting strictly
after `after`.

**BHMS-EVT-011** When `after` is older than the oldest retained event, or the log
was reset (new `epoch`), the server MUST set `gap: true`. It MUST NOT invent
events or present a discontinuous history as continuous.

**BHMS-EVT-012** A server MUST retain events for at least
`capabilities.events.retentionS` seconds.

**BHMS-EVT-013** Event visibility MUST follow device read authority: an event
about a device the principal cannot read MUST be skipped, without affecting
cursor continuity (`gap` stays false).

## 9.4 Live events

**BHMS-EVT-020** With `subscriptions/listen` `events.after`, the server MUST first
deliver retained events after that cursor, then live events, with no duplicate
and no omission between the two; if the cursor is too old, the acknowledgement
MUST carry `eventsGap: true`.

## 9.5 Streams

v0.1 defines no bulk-data streaming (camera frames, waveforms). Actions that
produce bulk data return a reference in their `result` (for example a URI and a
digest) defined by the device's `output` schema. A streaming extension is
expected in a later version.

**BHMS-EVT-030** Observation notifications MUST NOT carry values larger than
64 KiB of canonical JSON; larger data MUST be returned by reference.
