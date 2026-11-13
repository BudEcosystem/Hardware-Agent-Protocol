# 5. Observations

An `Observation` is an immutable record of what was known about one property at
one time, and how it was known.

## 5.1 The Observation object

| Member | Type | Required | Meaning |
|---|---|---|---|
| `value` | any \| null | yes | The value, valid against the property schema; `null` when `quality` is `invalid` or `unknown` |
| `unit` | string | no | The UCUM unit of `value` (equal to the schema's `x-bhms-unit`) |
| `evidence` | `measured` \| `reported` \| `commanded` \| `estimated` \| `simulated` | yes | How this value was obtained |
| `quality` | `valid` \| `stale` \| `invalid` \| `unknown` | yes | |
| `acquiredAt` | time \| null | yes | When the device acquired it; `null` when unknown |
| `receivedAt` | time | yes | When the server received it |
| `ageMs` | integer \| null | yes | Conservative age at response time; `null` when unbounded |
| `uncertainty` | number | no | Standard uncertainty, in `unit` |
| `sequence` | integer ≥ 0 | yes | Monotonic per `(deviceId, property, epoch)` |
| `epoch` | string | yes | Producer epoch; changes when the device or its adapter restarts its sequence |
| `source` | string | no | Sensor or channel name; untrusted text |

Quality:

- `valid` — acquired within the device's validity interval, from a working source.
- `stale` — the last good value is older than its validity interval.
- `invalid` — the source reported a fault or produced no value (`value` is `null`).
- `unknown` — the server cannot tell (`value` is `null`).

**BHMS-OBS-001** A missing or failed measurement MUST be reported as
`quality: "invalid"` (or `"unknown"`) with `value: null`. A server MUST NOT
substitute zero, a default, the last commanded value or the previous sample.

**BHMS-OBS-002** `evidence` MUST NOT be stronger than what was actually obtained:
a commanded setpoint echoed by a driver is `commanded`; a value computed from a
model is `estimated`; any value from a simulator is `simulated`.

**BHMS-OBS-003** `ageMs` MUST be computed conservatively from a monotonic clock
(receipt age plus the bounded acquisition latency). When acquisition latency is
unbounded or the device clock is unsynchronised and unbounded, `acquiredAt` and
`ageMs` MUST be `null` and such an observation MUST fail any `maxAgeMs`
requirement. Re-reading a retained observation MUST NOT refresh `acquiredAt`.

**BHMS-OBS-004** `sequence` MUST increase by at least one for every new
acquisition within an `epoch`; a server MUST change `epoch` when the sequence
restarts or wraps.

**BHMS-OBS-005** When `value` is a number, `unit` MUST be present and equal to the
property schema's `x-bhms-unit`.

## 5.2 `properties/read`

`{deviceId, property, maxAgeMs?, fresh?}` → `{observation}`.

- With neither option, the server returns its latest retained observation
  (acquiring one if it has none).
- `maxAgeMs` requires an observation no older than this; the server acquires a
  fresh one when the retained one is too old.
- `fresh: true` requires a new acquisition started after the request arrived.

**BHMS-OBS-010** If a server cannot produce an observation that satisfies
`maxAgeMs` or `fresh`, it MUST answer `STALE` with `field` naming the unmet
parameter and `bound` its value. It MUST NOT return an older observation as if it
satisfied the requirement.

**BHMS-OBS-011** A fresh acquisition of a property with `readEffect:
"transaction"` MUST be authorized as an effect on that property's resources
(BHMS-AUTH-012) and, when `requiresLease` is true, MUST be refused with
`LEASE_REQUIRED` unless the caller holds a current lease on those resources.
Reading the retained observation of such a property needs only read authority.

**BHMS-OBS-012** An unknown property MUST be refused with `INVALID_ARGUMENT`,
`field: "property"`, and a hint listing the device's property names.

## 5.3 Observation subscriptions

A client subscribes with `subscriptions/listen`
`notifications.observations: [{deviceId, property, minIntervalMs?}]` and receives
`notifications/observation {deviceId, property, observation}`.

**BHMS-OBS-020** Only properties with `observable: true` MAY be subscribed; others
MUST appear in the acknowledgement's `refused` list with `UNSUPPORTED`.

**BHMS-OBS-021** A server MUST deliver an observation notification when a new
acquisition occurs and the rate floor permits, and MUST deliver one when
`quality` changes (for example `valid` → `invalid`) even inside the rate floor.

**BHMS-OBS-022** A subscription MUST NOT by itself start device transactions on a
`readEffect: "transaction"` property unless the subscribing principal is
authorized for that effect.

## 5.4 Freshness for decisions

**BHMS-OBS-030** For every entry `{property, maxAgeMs}` of an action's
`requiresFresh` (§4.4), the server MUST, at admission and again immediately
before dispatch (BHMS-OPS-041), hold an observation of that property with
`quality: "valid"` and `ageMs ≤ maxAgeMs`, acquiring a fresh one when needed and
permitted (a `transaction` property is acquired under the action's own
authority and lease). Otherwise it MUST refuse with `STALE`,
`field: "requiresFresh[i]"`, `bound: {"property": …, "maxAgeMs": …}`, and a hint
naming the property and its current quality and age. Free-text
`preconditions` MUST NOT be used for this decision (BHMS-SEC-020).
