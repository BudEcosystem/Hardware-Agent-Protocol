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
| channel | `01` = BHMS-Compact |
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
| 1 | 1 | compact version = `2` (version 1 had no STOP token; a gateway and an endpoint of different versions MUST NOT talk: see BHMS-CMP-050) |
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

### STOP `0x05` (G→E), 3 bytes — `[0x05][reason u8: 0 unspecified, 1 operator, 2 client, 3 gateway][token u8, non-zero]`

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

### STOP_ACK `0x85` (E→G), 5 bytes — `[0x85][outcome: 0 initiated, 1 confirmed, 2 unsupported][evidence: 0 none, 1 reported, 2 measured][canceled count u8][token u8]`

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
anything (normally already caught by the mirrored `multipleOf` and bounds of
BHMS-DEV-071), a value whose `value / scale` is not within 1e-9 (relative) of an
integer, an integer outside the field type's range (`OUT_OF_RANGE`), or an `f32`
value whose binary32 conversion differs from it by more than 1e-6 × max(1, |value|).
It MUST NOT round, clamp or truncate silently.

**BHMS-CMP-011** Action and property indices are those of the layouts; a gateway
MUST NOT derive them from name order.

## 11.5 Sessions and epochs

**BHMS-CMP-020** An endpoint SHOULD derive its non-zero boot epoch from a
persistent boot counter incremented before any effect is possible, and then MUST
set `PERSISTENT_EPOCH`. An endpoint without one MUST clear `PERSISTENT_EPOCH`;
its epoch may repeat after a reboot, so its session check cannot detect a reset.
For such an endpoint the gateway MUST treat every HELLO as a possible reset
(BHMS-CMP-022 applies even when the epoch value is unchanged) and MUST NOT treat
the HELLO as proof that old work was purged (BHMS-OPS-042).

**BHMS-CMP-021** An endpoint MUST refuse every control frame except `HELLO_REQ`
and `STOP` whose session differs from its current epoch with `SESSION_MISMATCH`
and without effect.

**BHMS-CMP-022** When the epoch changes (or, for an endpoint without
`PERSISTENT_EPOCH`, on every HELLO), the gateway MUST mark every operation
dispatched before it and not yet terminal as `unknown` (error per
BHMS-OPS-004, unless a RESULT already settled it), emit `device.epoch`, and MUST
NOT re-send any of them. Only a `PERSISTENT_EPOCH` endpoint whose epoch value
advanced, or an accepted `NEW_SESSION` (BHMS-CMP-023), proves that old work was
purged and lifts the inhibition of BHMS-OPS-042.

A gateway MUST identify an endpoint *incarnation* by more than the epoch value: it
counts incarnations durably, starting a new one at its first HELLO, at every epoch
change and at every HELLO that may follow a reset (that of an endpoint without
`PERSISTENT_EPOCH`, or whose previous HELLO had no persistent epoch, since a
failed epoch store repeats the value at the next boot). Handles are unique only
within one incarnation (an epoch value can recur): `QUERY` (BHMS-CMP-034) and
INVOKE retransmission (BHMS-CMP-033) are only for operations dispatched in the
current incarnation, and retransmission only if the endpoint had
`PERSISTENT_EPOCH` when the INVOKE was first sent. When the bridge proves the
purge it emits `device.epoch` with `purged: true` (see 9.2).

**BHMS-CMP-023** `NEW_SESSION` MUST increment the epoch (persistently when
`PERSISTENT_EPOCH`), clear the ring and reset `lastHandle` to 0; an endpoint with
an active operation MUST ignore the flag and report its current epoch. A HELLO
answering a `NEW_SESSION` request with an epoch different from the one reported
just before is an *accepted new session*: the endpoint asserts it has no active
operation.

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
payload) after a missing reply **only to an endpoint with `PERSISTENT_EPOCH`**
and only while no HELLO has reported a different epoch since the first send. To
an endpoint without `PERSISTENT_EPOCH` it MUST NOT retransmit an INVOKE: after a
silent reboot to the same epoch value, the retransmit would carry a matching
session and a handle above the reset `lastHandle` and would execute again; the
gateway uses QUERY instead. On `HANDLE_UNKNOWN` it MUST leave the operation
`unknown`; it MUST NOT allocate a new handle for the same operation.

**BHMS-CMP-034** After a gateway restart the gateway MUST send `HELLO_REQ`; for
each operation recorded as `dispatching`, `running` or `unknown` that was dispatched
in the *current incarnation* (the epoch is unchanged AND no HELLO that may
follow a reset has been seen since dispatch, see BHMS-CMP-022: for an endpoint
with `PERSISTENT_EPOCH` a HELLO repeating the epoch value is no reset; for one
without it every HELLO may be) it MUST `QUERY` and reconcile from STATUS/RESULT,
keeping `unknown` on `HANDLE_UNKNOWN`. For an endpoint without `PERSISTENT_EPOCH`,
reconciliation after a gateway restart or after a link loss that required a new
HELLO is therefore not possible (the HELLO may follow a reset and handles are
reused): such operations stay `unknown` until a confirmed `stop` (BHMS-OPS-042) or
an operator resolves them; a lost reply on a live link (no HELLO) is still
reconciled by QUERY (BHMS-CMP-033). A gateway that cannot tell which incarnation an operation was dispatched in
(a journal that did not record it) MUST NOT QUERY it. An endpoint MUST answer QUERY for a handle that is not in its
ring (including one above `lastHandle`) with `HANDLE_UNKNOWN`, never by acting.
QUERY reconciles only operations dispatched in the current incarnation: every
STATUS, RESULT and ERROR frame carries the endpoint's current boot epoch in its
frame `session`, a QUERY whose session is not the current epoch is refused with
`SESSION_MISMATCH` (BHMS-CMP-021) in a frame stamped with the current epoch, and
the gateway MUST therefore record the epoch of each operation at dispatch and MUST
NOT QUERY an operation dispatched in an earlier epoch (it is `unknown`,
BHMS-CMP-022). On an endpoint without `PERSISTENT_EPOCH` a QUERY after a silent
reboot to the same epoch value finds an empty ring and is answered
`HANDLE_UNKNOWN`, which keeps the operation `unknown`.

**BHMS-CMP-035** An endpoint MUST send RESULT exactly once per handle unprompted,
and again in answer to QUERY or a retransmitted INVOKE.

**BHMS-CMP-036** A RESULT's `evidence` byte is the endpoint's own claim. A gateway MUST
make the operation's effect `verified` only when the RESULT says `completed` with evidence
`measured`, the action declares `completionEvidence: "measured"`, and the gateway, right
after the RESULT, reads each property the action names in `verifiedBy` with `FRESH` and gets
VALUEs of quality `valid` and evidence `measured`: those observations are the operation's
`evidence` (BHMS-OPS-006). Without them (evidence `reported` or `none`, no `verifiedBy`, a
reading that fails or is not valid and measured) the effect is `unverified`, and an intent
with `require: {effect: "verified"}` ends `failed` with `UNVERIFIED` (BHMS-OPS-007). A RESULT
that arrives after the gateway ended the operation is a late report (BHMS-OPS-072). (Task 14:
`move_joints` and `enable` of the BHMS Arm declare measured completion and always completed
`unverified`, because the byte had no defined mapping.)

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
initiated stop finishes with evidence. Both STOP_ACKs of a STOP MUST echo its
`token`; a STOP_ACK the endpoint causes itself (an endpoint-originated stop, see
below) carries the reserved token `0`. A STOP with token `0` is still carried out (a stop is never
refused for a bad token) and answered with token `0`. The gateway chooses a
non-zero token per stop (all retransmissions of one stop reuse it; no two stops in
progress share one) and MUST count only a STOP_ACK whose token belongs to a stop in
progress as evidence about it: an ack with another token or token `0` never
confirms a gateway stop (a token `0` ack is reported as a `stop` event of the
device instead). A STOP_ACK has no other correlation, so the token is what makes a
late or duplicated ack of an earlier stop harmless.

*Tokens end at a HELLO.* A gateway that restarts says a plain `HELLO_REQ` (the
epoch does not change, nothing is purged), and it may issue a token its predecessor
used for a stop the endpoint is still carrying out. Therefore:

- the endpoint MUST forget the token of the stop in progress whenever it sends a
  HELLO. The stop itself continues, and its confirming STOP_ACK is still sent, with
  token `0`: after a HELLO, a stop received before it is an endpoint-originated
  stop. No STOP_ACK sent after a HELLO carries the token of a STOP received before
  that HELLO. (An `ERROR` answering a refused `HELLO_REQ` is not a HELLO.)
- the gateway MUST start its token sequence at an unpredictable non-zero value
  each time it starts, and MUST ignore a STOP_ACK whose token no STOP it sent
  since the last HELLO it adopted carried. A stop that is in progress when the
  gateway receives a HELLO it adopts can therefore only be confirmed by a STOP
  sent after that HELLO, so the gateway MUST send such a stop again, with a new
  token, once it has adopted the HELLO (a re-HELLO without a reboot, a new
  session or a reconnection alike); the endpoint carries the stop out again and
  confirms it with that token. (A gateway MAY bound how many HELLOs one stop
  outlives; past that bound the stop ends `failed`.)

*Endpoint-originated stops.* Token `0` marks every stop the gateway in session did
not ask for: the hardware stop input, and a stop begun before the last HELLO. When
the hardware stop input asserts while a gateway stop is in progress, the stop
procedure runs again as the endpoint's own and the token becomes `0`: both
remaining STOP_ACKs carry `0` and the gateway stop is **not** confirmed, although
the device stops. This under-claim is deliberate (the safe direction: a gateway
never reports a stop it cannot attribute to its own STOP as confirmed). The
gateway MUST end such a stop `failed`, and its error SHOULD say that the endpoint
reported an endpoint-originated stop and that the device may be stopped, so that
the caller reads the device state; an operator who needs the confirmation sends
stop again. For the same reason a gateway that closes (or restarts) ends its stops
in progress `failed` at once: no acknowledgement can reach them any more, since its
successor's first frame is a `HELLO_REQ`.

**Version.** A `HELLO_REQ` whose compact version differs from the endpoint's is
answered `ERROR UNSUPPORTED` with `detail` = the endpoint's version (never guessed
at); a gateway that receives a HELLO or that ERROR for another version MUST NOT
serve the endpoint and MUST log the versions. Version 2 changed STOP and STOP_ACK
only.

**BHMS-CMP-051** STOP MUST end every active operation on the endpoint (each then
reports RESULT `canceled` or `failed`) and MUST raise the fence floor above every
fence seen, so that a pre-stop lease holder is fenced.

**BHMS-CMP-053** A gateway MUST NOT give a STOP a token that a stop sent since the last
HELLO it adopted carried and that ended without its own confirmation: the endpoint may still
be carrying that stop out, and its late `confirmed` would confirm the new one (the 8-bit token
space wraps after 255 stops in one session). When every token is taken it sends the STOP with
token `0` (carried out, never confirmed) and asks for a HELLO, after which the stop is sent
again with a fresh token. A STOP sent again after a HELLO MUST carry, in its frame `session`,
the epoch of that HELLO (an endpoint accepts STOP in any session, BHMS-CMP-050, but the frame
names the session it belongs to). (Task 9b review, deferred to v0.2.)

## 11.9 Reads and telemetry

**BHMS-CMP-060** VALUE MUST carry quality `invalid` or `unknown` with k = 0 rather
than a substituted value when no measurement exists (BHMS-OBS-001). The gateway
MUST build `Observation.epoch` from the boot epoch and `sequence` from the
VALUE sequence.

**BHMS-CMP-061** An endpoint declares bounded reading latency by reporting the age of each
value: a value it acquires to answer a `FRESH` READ SHOULD carry its real age (0 when acquired
for that READ; the C library: set `meta->age_ms` in the read callback), and `0xFFFFFFFF` is only
for a value whose age it cannot bound. The gateway computes the observation's age as the
reported age plus the time since it sent the READ (an upper bound of the link's share). A
reading of unknown age fails every `maxAgeMs` and every `requiresFresh` (BHMS-OBS-003, BHMS-OBS-030),
so an action with `requiresFresh` on a property whose endpoint reports no age can never be
admitted. (Task 14: every reading of the LedAnalog sketch had unknown age.)

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

A gateway STOP (reason 3, token `0x2a`, session 41, frame sequence 9) and the
endpoint's confirming ack (confirmed, measured, 2 operations canceled, the same
token, sequence 10):

```
7e 48 4d 01 01 00 01 00 00 00 00 00 00 00 29 00 00 00 09 00 03 05 03 2a fb 84 7e
```

```
7e 48 4d 01 02 00 01 00 00 00 00 00 00 00 29 00 00 00 0a 00 05 85 01 02 02 2a 25 ff 7e
```

## 11.11 Endpoint behaviours fixed by the reference library (informative)

`sdk/c` (BHMS-Compact C library, Task 9a) settled the points the layouts leave
open; other endpoints should match them so one gateway handles all of them.

- **Refusals consume nothing, but the fence is judged first.** An INVOKE answered
  with an ERROR other than `HANDLE_UNKNOWN`, `SESSION_MISMATCH` and
  `HANDLE_CONFLICT` neither advances `lastHandle` nor occupies a ring entry; the
  same handle may be retried. Check order for a new handle: ring replay,
  `HANDLE_UNKNOWN`, action index, exact argument length (`MALFORMED`), fence
  (`FENCED`, `LEASE_REQUIRED`), then the floor is raised to the fence and
  the largest fence seen is recorded, then `INHIBITED`, start TTL (`EXPIRED`,
  measured from the first byte of the frame at the endpoint), argument decoding
  and local limits (`OUT_OF_RANGE` or, for a `bool` byte other than 0/1,
  `MALFORMED`; `detail` is the argument index) and `BUSY`. So a refusal after the
  fence check still fences older lease holders (BHMS-CMP-040), while a frame
  refused before it (bad handle, action or length) never touches fence state.
  `UNKNOWN_ACTION` and `UNKNOWN_PROPERTY` put the bad index in `detail`. A
  non-finite `f32` argument is `OUT_OF_RANGE`.
- **Fence saturation.** The floor and the largest fence seen are u32 and saturate
  at `0xFFFFFFFF`. After a STOP that follows fence `0xFFFFFFFF` the floor stays
  there: only that fence value is admitted for the rest of the epoch, so a
  gateway MUST start a new session (BHMS-CMP-041) before its fences approach 2^32.
- **Replies and unsolicited frames.** Replies to a control frame use kind 02. An
  operation that finishes later (after `STATUS running`) sends its RESULT, and
  progress STATUS frames, as kind 03. A `HELLO_REQ` whose compact version is not 2
  is answered `ERROR UNSUPPORTED` with `detail = 2`.
- **Stop.** The first `STOP_ACK` is sent before the RESULT (kind 03, `canceled`)
  of each operation the stop ended; its `canceled` count says how many follow.
  A hardware stop input asserting sends the same sequence with the ack as
  kind 03 and, while it is asserted, INVOKE answers `INHIBITED`.
- **Epoch counter.** An erased cell (`0xFFFFFFFF`) counts as 0; the incremented
  epoch skips 0. `PERSISTENT_EPOCH` is advertised only when the stored counter
  was read successfully and the new value was durably stored; an unreadable
  counter (the epoch may repeat) or a failed store clears it for that boot, and
  it is not regained by a later `NEW_SESSION`.
- **Sequence.** The endpoint frame counter restarts at 0 with each epoch,
  including a `NEW_SESSION` (its HELLO is sequence 0).

## 11.12 Duration bounds over a link

**BHMS-CMP-052** In a compact description an action's `maxDurationMs` is the endpoint's
execution bound: the longest the endpoint may run the operation after it started it, and an
endpoint SHOULD end (RESULT `failed` or `canceled`) an operation that exceeds it. The link adds
latency the endpoint cannot see (the INVOKE's and the RESULT's time on the wire, their
retransmissions, a QUERY for a lost RESULT), so the gateway MUST bound the operation (BHMS-DEV-030,
BHMS-OPS-071) by `maxDurationMs` plus a **link allowance** that it either computes from its link
— the reference bridge: `2 × (retries + 1) × (reply timeout + 2 × the wire time of a largest
frame at the link's baud) + one QUERY period` — or is configured with (`link_allowance_ms` of a
compact upstream), and SHOULD name both in the error of an operation that exceeds them. The
served description is unchanged (it is the endpoint's, digest included); a program's worst-case
duration counts the declared `maxDurationMs`, so a program over compact devices declares its own
`maxDurationMs` with room for the allowance. (Ruling R41 and R53: a fully successful action on a
slow link read as `failed DEADLINE_EXCEEDED`.)
