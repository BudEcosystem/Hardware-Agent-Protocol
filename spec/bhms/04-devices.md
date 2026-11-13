# 4. Devices

A device is described twice: a **`DeviceSummary`** small enough to put dozens in
a model's context (returned by `devices/list`), and an immutable
**`DeviceDescription`** precise enough to generate code from (returned by
`devices/describe`).

## 4.1 Identifiers and names

| Item | Pattern | Example |
|---|---|---|
| `deviceId` | `^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$` | `pump-1`, `lab-a/arm-2` |
| action / property / event names | `^[a-z][a-z0-9_]{0,63}$` (event types may contain `.`) | `move_to`, `pressure`, `limit.hit` |
| capability ids | `^[a-z][a-z0-9-]*(\.[a-z0-9-]+)+$` | `bhms.axis.linear`, `com.acme.spectrometer` |
| resource ids | `^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$` | `arm-1/motion`, `cell-a/zone-1` |

Action and property names are snake_case so they can be used directly as parts
of model tool names. Capability ids are namespaced; `bhms.` is reserved for
capabilities defined by BHMS documents.

**BHMS-DEV-001** A `deviceId` MUST be unique within a server and MUST survive
address, transport and process changes of the device. A server MUST NOT bind an
existing `deviceId` to a replacement physical device without a change of
`digest` and an event `device.replaced`.

**BHMS-DEV-002** A gateway that aggregates servers MUST keep `deviceId`s unique
across upstreams; it SHOULD prefix upstream ids (`<upstream>/<deviceId>`) on
collision and MUST keep the mapping stable across restarts.

## 4.2 `devices/list`

`{filter?: {capability?, tag?, text?, status?}, cursor?, limit?}` →
`{devices: DeviceSummary[], nextCursor?}`.

- `capability` matches an id exactly, or a prefix when it ends in `.*`
  (`bhms.axis.*`).
- `tag` matches one tag exactly. `text` is a case-insensitive substring match over
  `name`, `summary` and tags. `status` matches the summary status.
- Filters combine with AND.

`DeviceSummary`:

| Member | Type | Meaning |
|---|---|---|
| `deviceId` | string | |
| `name` | string ≤ 80 | Human name |
| `summary` | string ≤ 280 | One or two sentences; untrusted text |
| `capabilities` | string[] | Capability ids |
| `tags` | string[] | Free-form labels |
| `status` | `online` \| `offline` \| `degraded` \| `unknown` | Current reachability |
| `digest` | string | Digest of the current description |
| `actions` | string[] | Action names, sorted |
| `properties` | string[] | Property names, sorted |

**BHMS-DEV-010** `devices/list` MUST return only devices the principal may read,
and MUST NOT reveal through counts, cursors or errors that hidden devices exist.

**BHMS-DEV-011** A `DeviceSummary` SHOULD be at most 1 600 bytes of canonical
JSON (about 400 tokens), and MUST be at most 4 096 bytes.

**BHMS-DEV-012** `status: "online"` MUST mean the server has had evidence of the
device's reachability within its declared liveness interval. A device whose
reachability cannot be established MUST be `unknown`, not `online`.

## 4.3 `devices/describe`

`{deviceId, digest?}` → `{description: DeviceDescription}`.

**BHMS-DEV-020** A `DeviceDescription` MUST be immutable for a given `digest`:
two describe results with the same digest MUST be byte-identical in canonical
JSON.

**BHMS-DEV-021** `digest` MUST equal `"sha256:" + hex(sha256(JCS(description
without its digest member)))`. A client SHOULD verify it.

**BHMS-DEV-022** When `params.digest` is given and differs from the current
description, the server MUST answer `STALE` with `field: "digest"` and `bound`
set to the current digest (it MAY instead return the requested historical
description if it retains it). Clients cache descriptions by digest.

**BHMS-DEV-023** A change to anything in a description (an action bound, a unit,
firmware that changes behaviour, calibration that changes a schema bound) MUST
produce a new digest and SHOULD emit `notifications/devices/listChanged`.

Description members:

| Member | Type | Required | Meaning |
|---|---|---|---|
| `deviceId` | string | yes | |
| `name` | string ≤ 80 | yes | |
| `description` | string ≤ 4000 | yes | Untrusted text for people and models |
| `capabilities` | string[] | yes | |
| `tags` | string[] | yes | |
| `resources` | string[] | yes | Exclusive resources this device's actions may use (§7.1) |
| `identity` | `{manufacturer?, model?, serialNumber?, hardwareRevision?, firmwareVersion?}` | no | |
| `properties` | `{name: PropertyDescription}` | yes | May be empty |
| `actions` | `{name: ActionDescription}` | yes | May be empty |
| `events` | `{type: {description, data?}}` | no | Device-specific event types (§9.2) |
| `safety` | `SafetyDescription` | yes | Stop and disconnect behaviour |
| `extensions` | object | no | Keys are extension identifiers |
| `digest` | string | yes | §4.3 |

## 4.4 Actions

| Member | Type | Required | Meaning |
|---|---|---|---|
| `description` | string ≤ 1000 | yes | Untrusted text |
| `input` | JSON Schema | yes | Schema of `arguments` (§4.5) |
| `output` | JSON Schema | no | Schema of `operation.result` |
| `effect` | `none` \| `reversible` \| `irreversible` \| `hazardous` | yes | Physical effect class |
| `idempotency` | `idempotent` \| `absolute` \| `relative` \| `toggle` | yes | What repeating it does |
| `cancel` | `supported` \| `unsupported` | yes | Whether `operations/cancel` can terminate it |
| `completionEvidence` | `measured` \| `reported` \| `none` | yes | Evidence available for completion |
| `verifiedBy` | string[] | no | Properties whose measurement verifies the effect |
| `typicalDurationMs` | integer | no | |
| `maxDurationMs` | integer ≥ 1 | yes | Enforced upper bound on execution |
| `requiresLease` | bool | yes | Whether `leaseId` is required |
| `resources` | string[] | yes | Resources the action uses (subset of device `resources`) |
| `onLeaseLoss` | `finish` \| `cancel` \| `hold` | no (default `finish`) | Behaviour of a running operation whose lease expires or is revoked |
| `requiresFresh` | `[{property, maxAgeMs}]` | no | Machine-checked freshness preconditions: each named property of this device must have a `valid` observation no older than `maxAgeMs` at admission and dispatch (BHMS-OBS-030) |
| `preconditions` | string ≤ 500 | no | Untrusted text describing required state; never machine-checked |
| `compact` | `CompactActionLayout` | no | Byte layout on a BHMS-Compact endpoint (§11) |

Effect classes:

- `none` — no physical effect (configuration readback, computation).
- `reversible` — a physical effect another action can undo (a move, a setpoint).
- `irreversible` — an effect that cannot be undone (dispensing, cutting, a photo
  exposure of a sample).
- `hazardous` — an effect that can injure people or damage property if misused
  (heating above ambient, lasers, high force).

Idempotency classes say what a *duplicate execution* would do — the reason
server-side deduplication exists:

- `idempotent` — repeating has no further effect.
- `absolute` — drives to an absolute target; repeating returns to the target
  (it may move again or extend exposure).
- `relative` — each execution adds an increment (move-by, dispense); a duplicate
  doubles the effect.
- `toggle` — each execution flips a state; a duplicate undoes the first.

**BHMS-DEV-030** An action whose `effect` is not `none` MUST declare
`maxDurationMs`, and the server MUST enforce it: an operation still running after
`maxDurationMs` MUST be cancelled if the action supports cancellation and MUST
end `failed` (error `DEADLINE_EXCEEDED`) or `unknown`, never `completed`.

**BHMS-DEV-031** `completionEvidence: "measured"` MUST be declared only when the
server obtains an independent measurement (for example an encoder, a scale, a
flow meter) that confirms the effect, and `verifiedBy` SHOULD name it.
A command echo or the driver's return value is `reported`, not `measured`.

**BHMS-DEV-032** An action's `resources` MUST be a subset of the device's
`resources`. An action with `requiresLease: true` MUST declare at least one
resource.

**BHMS-DEV-033** Actions with `effect: "hazardous"` SHOULD declare
`requiresLease: true`.

**BHMS-DEV-034** Every `requiresFresh[i].property` MUST name a property of the same
device, and the list MUST NOT name a property twice.

## 4.5 Schemas, units and arguments

`input`, `output` and property `schema` are JSON Schema 2020-12 documents with
these BHMS rules:

**BHMS-DEV-040** An action `input` MUST be `{"type": "object", …}` with
`additionalProperties: false`. Embedded schemas MUST NOT contain `$ref` to any
URI outside the schema itself, and servers MUST NOT dereference remote
references.

**BHMS-DEV-041** Every `number` or `integer` schema in an action `input` or
`output`, a property `schema`, an event `data` schema and a program `input` MUST
carry `x-bhms-unit` with a case-sensitive UCUM code — counts, indices and other
dimensionless numbers use `"1"`, percentages `"%"` — so that every numeric
observation and argument has a unit (BHMS-OBS-005). Physical quantities SHOULD
also carry `minimum` and `maximum`. A coordinate value MAY carry `x-bhms-frame`
naming its frame.

**BHMS-DEV-042** Units SHOULD come from the BHMS unit registry below. A client
MUST NOT convert a unit that is not in the registry.

| Dimension | Codes |
|---|---|
| length | `m`, `cm`, `mm`, `um`, `nm` |
| angle | `rad`, `deg`, `mrad` (angles are not dimensionless) |
| time | `s`, `ms`, `us`, `min`, `h` |
| temperature | `K`, `Cel`, `[degF]` |
| volume | `L`, `mL`, `uL`, `nL` |
| mass | `kg`, `g`, `mg`, `ug` |
| pressure | `Pa`, `kPa`, `bar`, `mbar`, `[psi]` |
| flow | `L/min`, `mL/min`, `uL/min` |
| current / voltage | `A`, `mA` / `V`, `mV` |
| frequency | `Hz`, `kHz` |
| dimensionless | `1`, `%` (`50 %` = `0.5` of `1`) |

The registry is implemented by `bhms.protocol.units` (exact rational
conversion).

**Quantity arguments.** Wherever a schema declares `x-bhms-unit`, a client MAY
send a quantity object `{"value": <number>, "unit": "<ucum>"}` instead of a bare
number. This lets a model state the unit it believes it is using.

**BHMS-DEV-043** A server MUST accept a quantity object only when its `unit`
equals the declared unit exactly, and MUST then treat it as the bare `value`.
For any other unit it MUST answer `UNIT_MISMATCH` with `field` naming the
argument and `bound` set to the declared unit; when the units are convertible
the `hint` SHOULD state the converted value. A server MUST NOT convert silently.

**BHMS-DEV-044** A server MUST validate `arguments` against `input` before
admission and MUST NOT coerce, round, clamp or default a value the client sent:
a wrong type or unknown member is `INVALID_ARGUMENT`; a violated `minimum`,
`maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `minLength`, `maxLength`,
`minItems`, `maxItems` or `enum` is `OUT_OF_RANGE` with `bound` set to the
violated keyword(s) and value(s). A `multipleOf` violation is `INVALID_ARGUMENT`
with `bound: {"multipleOf": …}` (as BHMS-CMP-010). Defaults declared in the schema MAY
be applied to *absent* members and MUST then be recorded in the operation's
`admittedArguments` (§6.2); `arguments` keeps the request exactly as sent.

## 4.6 Properties

| Member | Type | Required | Meaning |
|---|---|---|---|
| `description` | string ≤ 1000 | yes | Untrusted text |
| `schema` | JSON Schema | yes | Schema of the value (`x-bhms-unit` on numbers) |
| `evidence` | `measured` \| `reported` \| `commanded` \| `estimated` \| `simulated` | yes | What a value of this property is |
| `observable` | bool | yes | Whether it may be subscribed to |
| `maxRateHz` | number | no | Highest rate the device can produce new values |
| `readEffect` | `none` \| `transaction` | yes | Whether a fresh read starts a device transaction with side effects |
| `requiresLease` | bool | no (default false) | Fresh reads require a lease (only with `transaction`) |
| `resources` | string[] | no | Resources a fresh read uses |
| `compact` | `CompactValue` | no | Encoding on a BHMS-Compact endpoint |

**BHMS-DEV-050** A property MUST declare `readEffect: "transaction"` when a fresh
acquisition changes shared device state (selects a multiplexer, consumes a FIFO,
clears a latch, starts a bus transaction another owner could observe). Such a
fresh read is subject to the same authority and lease checks as an action that
uses the same resources (BHMS-AUTH-012).

**BHMS-DEV-051** `evidence` MUST describe the weakest evidence the property can
deliver. A property that reports a commanded setpoint MUST be `commanded`, even
when the device usually reaches it.

## 4.7 Safety description

| Member | Type | Required | Meaning |
|---|---|---|---|
| `stop` | `supported` \| `unsupported` | yes | Whether the device has a commissioned stop procedure |
| `stopEvidence` | `measured` \| `reported` \| `none` | yes | Evidence a stop result can carry |
| `stopMaxDurationMs` | integer | no | Upper bound on the stop procedure |
| `onDisconnect` | `continue` \| `hold` \| `stop` \| `unknown` | yes | What the device does when it loses its server or gateway |
| `summary` | string ≤ 1000 | yes | Untrusted text describing stop behaviour |

**BHMS-DEV-060** A device with any action whose `effect` is `irreversible` or
`hazardous` SHOULD declare `stop: "supported"`. A device MUST NOT declare
`onDisconnect` other than `unknown` unless that behaviour is implemented on the
device side of the link (not only in the server).

## 4.8 Compact layouts

A description served on behalf of a BHMS-Compact endpoint carries the byte
layout of each action and property, so the gateway can translate. The layout is
part of the description and therefore of its digest.

`CompactActionLayout = {index, args: CompactField[], result: CompactField[]}`;
`CompactField = {name, type, scale?}`; `CompactValue = {index, type, scale?}`;
`type` ∈ `u8, i8, u16, i16, u32, i32, f32, bool`. Semantics are in §11.4.

**BHMS-DEV-070** The `args` of a compact layout MUST map every member of the
action's `input` exactly once (a fixed-width frame cannot omit a member), and
every mapped member MUST be either `required` or declare a `default`, which the
gateway applies and records (BHMS-DEV-044). Every `result` field MUST name a
member of `output`. `index` values MUST be unique per device among actions and
among properties.

**BHMS-DEV-071** A compact field with `scale` MUST be mirrored in the
description: the corresponding `input` member (and, for result fields, the
`output` member; for properties, the property `schema`) MUST declare
`multipleOf` equal to `scale`, and its `minimum`/`maximum` MUST lie inside the
field type's range times `scale`. This makes every gateway refusal under
BHMS-CMP-010 predictable from the description. Because decimal steps such as 0.1
are not exact in binary floating point, BHMS validators MUST evaluate
`multipleOf` with a relative tolerance of 1e-9 (or exact decimal arithmetic),
the same tolerance as BHMS-CMP-010.
