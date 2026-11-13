# 10. Errors

A request that is refused gets a JSON-RPC error response. Physical outcomes of
admitted work are never JSON-RPC errors: they are operation states carrying an
`OperationError` (§6.2). This chapter defines both shapes and the code table.

## 10.1 Error object

```json
{"jsonrpc":"2.0","id":7,"error":{
  "code":-32602,"message":"position 420 mm is above the maximum 300 mm",
  "data":{"bhmsCode":"OUT_OF_RANGE","field":"arguments.position",
          "bound":{"maximum":300},"mayHaveActed":false,"retry":"never",
          "hint":"send a position between 0 and 300 mm"}}}
```

`data` (`ErrorData`):

| Member | Type | Required | Meaning |
|---|---|---|---|
| `bhmsCode` | string | yes | Code from §10.2 |
| `field` | string | no | Path of the offending member from `params` (`arguments.position`, `resources[2]`, `program.steps[3].timeoutMs`, `_meta.bhms/protocolVersion`) |
| `bound` | any | no | The violated bound (`{"maximum": 300}`), expected value, or supported set |
| `operationId` | string | no | The operation the error concerns (`KEY_CONFLICT`, `STALE` on an unknown operation) |
| `mayHaveActed` | bool | yes | Whether a device may have acted because of this request |
| `retry` | `never` \| `same-key` \| `after-reconcile` \| `backoff` | yes | How to retry |
| `hint` | string | yes | What to do next, for people and models |

`OperationError` (inside an Operation or a DeviceStop) is `ErrorData` plus
`message`.

Retry classes:

- `never` — do not retry this request unchanged; fix the request or the situation.
- `same-key` — retry the identical request with the same `operationKey`.
- `after-reconcile` — read the current state (`operations/get`,
  `properties/read`) and decide; a blind retry may act twice.
- `backoff` — retry later, with the same `operationKey`, with increasing delay.

**BHMS-ERR-001** Every error response for a BHMS method with a code in §10.2 MUST
carry `data` with `bhmsCode`, `mayHaveActed`, `retry` and `hint`, and `code` MUST
equal the number assigned to `bhmsCode`.

**BHMS-ERR-002** Clients MUST dispatch on `data.bhmsCode`, not on `code`: three
codes share `-32602`.

**BHMS-ERR-003** `message` and `hint` MUST name the offending field and its bound
when there is one, and `hint` MUST say what to do next. A server MUST NOT put
secrets, tokens or the identity of another principal in any error member.

**BHMS-ERR-004** `mayHaveActed` MUST be `true` whenever a device may have acted
because of the request (for example a dispatch that timed out), and MUST be
`false` only when the server knows no command reached a device. Admission
refusals (BHMS-OPS-040) are always `false`.

**BHMS-ERR-005** A server MAY override a code's default `retry` only to a more
conservative class (`backoff` → `after-reconcile` → `never`), except that it MAY
use `same-key` for `BUSY` and `DEVICE_UNAVAILABLE` refusals that occurred before
admission.

**BHMS-ERR-006** Error responses for JSON-RPC codes not in §10.2 (`-32700`,
`-32600`, `-32601`, `-32603`) MAY omit `data`; when they carry `data` it MUST NOT
contain `bhmsCode`.

## 10.2 Code table

| BHMS code | JSON-RPC code | Default retry | Meaning |
|---|---|---|---|
| `INVALID_ARGUMENT` | -32602 | never | Malformed params, unknown member, wrong type, unknown property/operation/cursor/digest |
| `OUT_OF_RANGE` | -32602 | never | A value outside the effective envelope or a limit |
| `UNIT_MISMATCH` | -32602 | never | A quantity in a unit other than the declared one; nothing is converted silently |
| `UNKNOWN_DEVICE` | -32001 | never | Device id not registered or not visible |
| `UNKNOWN_ACTION` | -32002 | never | Action not on the device |
| `UNSUPPORTED` | -32003 | never | Capability, method or requirement not available; refuse rather than emulate |
| `LEASE_REQUIRED` | -32004 | never | The action needs a lease; acquire one first |
| `LEASE_CONFLICT` | -32005 | backoff | Another principal holds a needed resource, or the lease is not the caller's |
| `LEASE_EXPIRED` | -32006 | never | The lease expired or is unknown; reacquire |
| `FENCED` | -32007 | never | The lease was superseded or revoked; reacquire |
| `KEY_CONFLICT` | -32008 | never | `operationKey` reused for a different intent |
| `STALE` | -32009 | after-reconcile | A precondition is unmet: stale observation, changed description, unresolved unknown operation, failed assert |
| `DEVICE_UNAVAILABLE` | -32010 | backoff | Device offline or unreachable |
| `UNAUTHORIZED` | -32011 | never | The principal lacks the scope |
| `BUSY` | -32012 | backoff | Device or server saturated |
| `DEADLINE_EXCEEDED` | -32013 | after-reconcile | A deadline or duration bound passed; the outcome may be unknown |
| `INTERNAL` | -32014 | never | Server bug |
| `UNSUPPORTED_VERSION` | -32015 | never | Protocol version not served; `bound` lists supported versions |
| `UNVERIFIED` | -32016 | after-reconcile | Required measured evidence was absent or contradicted the effect |
| `DEVICE_FAULT` | -32017 | after-reconcile | The device reported a fault while acting; partial effects possible |

The numbers lie in JSON-RPC's implementation-defined server range; `-32018`
and `-32019` are reserved for future BHMS codes. The table is implemented by
`bhms.protocol.errors` and mirrored by the schema's `x-bhms-errors` map.

**BHMS-ERR-010** Implementations MUST use exactly these numbers and default retry
classes, and MUST NOT emit a BHMS-range number (`-32001` … `-32019`) with any
other meaning.

**BHMS-ERR-011** `UNSUPPORTED_VERSION` MUST carry `bound` = the server's supported
versions. `KEY_CONFLICT` MUST carry `operationId`. `OUT_OF_RANGE` MUST carry
`field` and `bound`. `UNIT_MISMATCH` MUST carry `field` and `bound` = the declared
unit.

**BHMS-ERR-012** `DEVICE_FAULT` and `UNVERIFIED` MUST appear only as
`OperationError`s of admitted operations (they describe what happened while
acting), with `mayHaveActed: true`.
