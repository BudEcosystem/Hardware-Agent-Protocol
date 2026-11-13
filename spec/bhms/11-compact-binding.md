# 11. BHMS-Compact binding

BHMS-Compact carries BHMS semantics to microcontrollers that cannot parse JSON.
It is a fixed-layout binary protocol between a **gateway** and an **endpoint**
(the MCU), carried in the existing HDLC-style `HM` frames
(`protocol/serial/frame.{c,h,py}`). The gateway holds the full device
description, keyed by the digest the endpoint reports, keeps the durable
operation journal, and does all JSON-RPC work. The endpoint keeps its installed
actions, local limits, fence floor, a small replay ring and its stop procedure.

## 11.1 Frame usage

The frame is unchanged (spec/07-constrained-binding.md): flags `7e`, escape
`7d`, a 20-byte header, a payload of at most 192 bytes and a complemented
FCS-16. Header fields are big-endian, as the frame defines.

| Header field | BHMS-Compact use |
|---|---|
| magic, version | `HM`, `01` |
| kind | `01` control (gateway → endpoint), `02` status (endpoint → gateway, replies), `03` telemetry (endpoint → gateway, unsolicited) |
| flags | `00` |
| channel | `01` = BHMS-Compact v1 |
| session (u64) | Endpoint boot epoch, zero-extended u32. `0` only on `HELLO_REQ` before the epoch is known |
| sequence (u32) | Per-direction frame counter from 0 in each epoch; diagnostic only, never a deduplication key |
| length | payload length |

**Payload multi-byte fields are little-endian** (the MCU's native order), unlike
the frame header. Byte 0 of every payload is the message type.

**BHMS-CMP-001** Endpoints and gateways MUST use the `HM` frame of
`protocol/serial/frame.h` unchanged, `channel = 0x01`, and MUST discard frames
with another channel without effect.

**BHMS-CMP-002** A receiver MUST reject (with `ERROR MALFORMED` for control frames,
by discarding for others) any payload whose length differs from the exact length
its type and layout define.

## 11.2 Messages

`G→E` = gateway to endpoint (kind 01); `E→G` = endpoint to gateway (kind 02, or
03 when unsolicited).

### HELLO_REQ `0x01` (G→E), 7 bytes

| Offset | Size | Field |
|---:|---:|---|
| 0 | 1 | `0x01` |
| 1 | 1 | compact version = `1` |
| 2 | 1 | flags: bit 0 `NEW_SESSION` (begin a new epoch; honoured only when no operation is active) |
| 3 | 4 | nonce u32 (echoed) |

### HELLO `0x81` (E→G), 24 bytes

| Offset | Size | Field |
|---:|---:|---|
| 0 | 1 | `0x81` |
| 1 | 1 | compact version |
| 2 | 1 | flags: bit 0 `FENCING` (endpoint enforces fences), bit 1 `PERSISTENT_EPOCH`, bit 2 `STOP_SUPPORTED` |
| 3 | 8 | `digest8`: the first 8 bytes of the description's sha256 |
| 11 | 4 | boot epoch u32 (≠ 0) |
| 15 | 4 | nonce echo u32 |
| 19 | 2 | `lastHandle` u16: highest operation handle accepted in this epoch (0 = none) |
| 21 | 1 | replay ring size (≥ 4) |
| 22 | 1 | maximum concurrently active operations (≥ 1) |
| 23 | 1 | maximum argument bytes per INVOKE |

### INVOKE `0x02` (G→E), 10 + n bytes

| Offset | Size | Field |
|---:|---:|---|
| 0 | 1 | `0x02` |
| 1 | 2 | operation handle u16 (1 … 65535) |
| 3 | 1 | action index u8 (`compact.index`) |
| 4 | 4 | fence u32 (`0` = no lease) |
| 8 | 2 | start TTL u16 ms (`0` = none): refuse if execution cannot start within it |
| 10 | n | arguments, the layout's `args` fields concatenated in order |

### CANCEL `0x03` (G→E), 3 bytes — `[0x03][handle u16]`

### READ `0x04` (G→E), 5 bytes — `[0x04][request u16][property index u8][flags u8: bit 0 FRESH]`

### STOP `0x05` (G→E), 2 bytes — `[0x05][reason u8: 0 unspecified, 1 operator, 2 client, 3 gateway]`

### QUERY `0x06` (G→E), 3 bytes — `[0x06][handle u16]`

### STATUS `0x82` (E→G), 6 bytes

| Offset | Size | Field |
|---:|---:|---|
| 0 | 1 | `0x82` |
| 1 | 2 | handle u16 |
| 3 | 1 | state: 1 accepted, 2 running, 3 completed, 4 failed, 5 canceled, 6 rejected |
| 4 | 1 | cancel: 0 none, 1 requested, 2 acknowledged, 3 refused, 4 confirmed |
| 5 | 1 | progress 0–100, 255 = unknown |

### RESULT `0x83` (E→G), 6 + m bytes

| Offset | Size | Field |
|---:|---:|---|
| 0 | 1 | `0x83` |
| 1 | 2 | handle u16 |
| 3 | 1 | terminal state: 3 completed, 4 failed, 5 canceled, 6 rejected |
| 4 | 1 | evidence: 0 none, 1 reported, 2 measured |
| 5 | 1 | fault u8 (0 = none; device fault number when failed) |
| 6 | m | result fields in the layout's `result` order (only when completed; else m = 0) |

### VALUE `0x84` (E→G), 14 + k bytes

| Offset | Size | Field |
|---:|---:|---|
| 0 | 1 | `0x84` |
| 1 | 2 | request u16 (0 when unsolicited, kind 03) |
| 3 | 1 | property index |
| 4 | 1 | quality: 0 valid, 1 stale, 2 invalid, 3 unknown |
| 5 | 1 | evidence: 0 measured, 1 reported, 2 commanded, 3 estimated, 4 simulated |
| 6 | 4 | sequence u32 |
| 10 | 4 | age ms u32 (`0xFFFFFFFF` = unbounded/unknown) |
| 14 | k | value (property type width; k = 0 when quality is invalid or unknown) |

### STOP_ACK `0x85` (E→G), 4 bytes — `[0x85][outcome: 0 initiated, 1 confirmed, 2 unsupported][evidence: 0 none, 1 reported, 2 measured][canceled count u8]`

### ERROR `0xFF` (E→G), 6 bytes — `[0xFF][request type u8][handle or request u16][code u8][detail u8]`

| Code | Name | Meaning | Gateway mapping |
|---:|---|---|---|
| 1 | MALFORMED | Bad length or type | `INVALID_ARGUMENT` (gateway bug: log) |
| 2 | UNKNOWN_ACTION | No such action index | `UNKNOWN_ACTION` |
| 3 | UNKNOWN_PROPERTY | No such property index | `INVALID_ARGUMENT` |
| 4 | OUT_OF_RANGE | Argument outside local limits; `detail` = argument index | `OUT_OF_RANGE` |
| 5 | FENCED | Fence below the floor | `FENCED` |
| 6 | LEASE_REQUIRED | Fence 0 on an action that needs a lease | `LEASE_REQUIRED` |
| 7 | BUSY | No free operation slot | `BUSY` |
| 8 | HANDLE_UNKNOWN | Handle ≤ `lastHandle` and not in the ring | operation stays `unknown` |
| 9 | SESSION_MISMATCH | Frame session ≠ current epoch | re-HELLO; old-epoch operations `unknown` |
| 10 | EXPIRED | Start TTL elapsed before start | `DEADLINE_EXCEEDED`, no effect |
| 11 | UNSUPPORTED | Feature not installed | `UNSUPPORTED` |
| 12 | PRECONDITION | Local precondition or interlock unmet | `STALE` |
| 13 | INHIBITED | Hardware stop or fault latch active | `DEVICE_UNAVAILABLE` |
| 14 | HANDLE_CONFLICT | Handle in ring with a different payload | `INTERNAL` (gateway bug) |
| 15 | INTERNAL | Endpoint fault | `INTERNAL` |

An ERROR in reply to INVOKE with any code other than 8, 9 and 14 guarantees
that the endpoint did not start the operation.

## 11.3 Size budget

A typical INVOKE carries ≤ 8 argument bytes: a payload of 18 bytes, a decoded
frame of 20 + 18 + 2 = 40 bytes, and **42 bytes on the wire** before
byte-stuffing (each `7e`/`7d` byte in header, payload or FCS adds one). The
largest INVOKE (a 182-byte argument block) fits one frame.

**BHMS-CMP-003** Encoders MUST NOT pad payloads: a frame's wire length MUST be
exactly 24 + payload length + the number of stuffed octets (20-byte header,
2-byte FCS, 2 flags). An INVOKE with ≤ 8 argument bytes is therefore ≤ 64 bytes
on the wire unless more than 22 of its octets need stuffing.

## 11.4 Layouts and value encoding

The description's `compact` layouts (§4.8) define each action's argument and
result fields and each property's value. Types: `u8`, `i8`, `u16`, `i16`, `u32`,
`i32` (little-endian two's complement), `f32` (IEEE 754 binary32 little-endian),
`bool` (one byte, 0 or 1).

A field with `scale` carries the integer `round(value / scale)` on the wire and
denotes `wire × scale` in JSON.

**BHMS-CMP-010** A gateway MUST refuse, with `INVALID_ARGUMENT` before sending
anything, a value whose `value / scale` is not within 1e-9 (relative) of an
integer, an integer outside the field type's range (`OUT_OF_RANGE`), or an `f32`
value whose binary32 conversion differs from it by more than 1e-6 × max(1, |value|).
It MUST NOT round, clamp or truncate silently.

**BHMS-CMP-011** Action and property indices are those of the layouts; a gateway
MUST NOT derive them from name order.

## 11.5 Sessions and epochs

**BHMS-CMP-020** An endpoint MUST choose a non-zero boot epoch that differs from
every earlier epoch: from a persistent boot counter incremented before any
effect is possible (flag `PERSISTENT_EPOCH`), or else the gateway MUST treat every
HELLO as a new epoch.

**BHMS-CMP-021** An endpoint MUST refuse every control frame except `HELLO_REQ`
and `STOP` whose session differs from its current epoch with `SESSION_MISMATCH`
and without effect.

**BHMS-CMP-022** When the epoch changes, the gateway MUST mark every operation
dispatched in the old epoch and not yet terminal as `unknown` (unless a RESULT
already settled it), emit `device.epoch`, and MUST NOT re-send any of them.

**BHMS-CMP-023** `NEW_SESSION` MUST increment the epoch (persistently when
`PERSISTENT_EPOCH`), clear the ring and reset `lastHandle` to 0; an endpoint with
an active operation MUST ignore the flag and report its current epoch.

## 11.6 Operation handles and the replay ring

**BHMS-CMP-030** Within an epoch, the gateway MUST assign operation handles in
strictly increasing order starting at 1, MUST map each durably to its
`operationId` before sending the INVOKE, and MUST start a new session before
handle 65535 is exhausted. Handles never wrap.

**BHMS-CMP-031** An endpoint MUST keep a ring of at least 4 most recently accepted
handles with their complete INVOKE payload and latest STATUS or RESULT.

**BHMS-CMP-032** On INVOKE, an endpoint MUST: if the handle is in the ring and the
payload is identical, re-send the latest STATUS or RESULT without acting again; if
it is in the ring with a different payload, reply `HANDLE_CONFLICT` without
acting; if it is ≤ `lastHandle` and not in the ring, reply `HANDLE_UNKNOWN`
without acting; otherwise treat it as new and set `lastHandle` to it.

**BHMS-CMP-033** A gateway MAY retransmit an INVOKE (same handle, identical
payload) after a missing reply. On `HANDLE_UNKNOWN` it MUST leave the operation
`unknown`; it MUST NOT allocate a new handle for the same operation.

**BHMS-CMP-034** After a gateway restart the gateway MUST send `HELLO_REQ`; if the
epoch is unchanged it MUST `QUERY` each operation recorded as `dispatching`,
`running` or `unknown` and reconcile from STATUS/RESULT, keeping `unknown` on
`HANDLE_UNKNOWN`.

**BHMS-CMP-035** An endpoint MUST send RESULT exactly once per handle unprompted,
and again in answer to QUERY or a retransmitted INVOKE.

## 11.7 Fences

**BHMS-CMP-040** An endpoint advertising `FENCING` MUST keep a fence floor (reset to
0 on each new epoch), MUST refuse an INVOKE whose non-zero fence is below the
floor with `FENCED`, MUST raise the floor to a higher fence, and MUST refuse fence
0 for actions that require a lease with `LEASE_REQUIRED`. Without `FENCING`, the
gateway MUST be the only path to the endpoint and MUST say so
(`capabilities.gateway`).

**BHMS-CMP-041** The gateway MUST map its lease fences to the u32 fence field
monotonically per endpoint epoch.

## 11.8 Stop

**BHMS-CMP-050** An endpoint MUST accept STOP with any session value, MUST process
it before any queued work, MUST reply STOP_ACK immediately (`initiated` or
`confirmed`), and MUST send a second STOP_ACK (kind 03) with `confirmed` when an
initiated stop finishes with evidence.

**BHMS-CMP-051** STOP MUST end every active operation on the endpoint (each then
reports RESULT `canceled` or `failed`) and MUST raise the fence floor above every
fence seen, so that a pre-stop lease holder is fenced.

## 11.9 Reads and telemetry

**BHMS-CMP-060** VALUE MUST carry quality `invalid` or `unknown` with k = 0 rather
than a substituted value when no measurement exists (BHMS-OBS-001). The gateway
MUST build `Observation.epoch` from the boot epoch and `sequence` from the
VALUE sequence.

## 11.10 Worked example (informative)

`pump-1.dispense {volume: 50, rate: 100}` under lease fence 412, as operation
handle 17 in boot epoch 41, frame sequence 7. The layout (§4.8 example in
`examples/devices.describe.response.json`) is action index 0, args
`volume u16 scale 0.1`, `rate u16`, result `dispensed u16 scale 0.1`.

INVOKE payload (14 bytes): `02` type, `11 00` handle 17, `00` action 0,
`9c 01 00 00` fence 412, `00 00` no start TTL, `f4 01` volume 500 × 0.1 = 50 uL,
`64 00` rate 100.

Wire frame (38 bytes, no stuffing needed):

```
7e 48 4d 01 01 00 01 00 00 00 00 00 00 00 29 00 00 00 07 00 0e
02 11 00 00 9c 01 00 00 00 00 f4 01 64 00 e5 f9 7e
```

RESULT payload (8 bytes): `83`, `11 00` handle 17, `03` completed, `02`
measured, `00` no fault, `f5 01` dispensed 501 × 0.1 = 50.1 uL. Wire frame (32
bytes):

```
7e 48 4d 01 02 00 01 00 00 00 00 00 00 00 29 00 00 00 09 00 08
83 11 00 03 02 00 f5 01 33 22 7e
```

These bytes were produced with `protocol/serial/frame.py` and are the first
compact test vectors for Task 9.
