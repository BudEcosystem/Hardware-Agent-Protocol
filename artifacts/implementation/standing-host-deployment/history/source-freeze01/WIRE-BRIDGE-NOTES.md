# Standing host wire/bridge source review

Status: **source only, not imported, compiled, linked or executed**. Only new
`project/hms/standing_wire.py`, `project/tests/standing_host_pipe.c`, and this
note were added by the wire/bridge author. Original/public/sealed sources were
read, not changed. Root review must precede any validation execution.

## Python interface

The codec imports the existing `protocol.serial.frame.Frame`, not an alternate
transport. `Request(Frame)` validates request syntax; `.opcode` is an Opcode and
`.reference` is a Reference or None. `describe(page)`, `bind(generation, handle,
manifest_digest, context_digest)`, `revoke(generation, handle)`,
`reference(generation, handle, standing_number, intent_digest)`,
`status(ref, page=0, cursor=0)` return the documented payload/identity types.

`Reference(generation, handle, standing_number, intent_digest).payload(opcode)`
returns the 44-byte record prefix. `Configuration(lower_demand, upper_demand,
required_improvement, minimum_on_feedback, sample_period, demand_max_age,
feedback_max_age, minimum_on_dwell, minimum_off_dwell, feedback_window)` has fixed
0/1/0/0 output-policy defaults. `.payload()` returns exactly 32 bytes and
`Configuration.parse(bytes32)` decodes and validates the canonical form.

`Open(reference, configuration, resource_mask, fences, lease_until,
activation_cap, demand_epoch, feedback_epoch, evidence_mode=0, kernel_id=1,
outage_policy=0).payload()` returns 134 bytes; `Open.parse` validates it.
`fences` is always a tuple of eight entries including zero unused entries.
`open_payload` accepts the same constructor arguments.

`mutation(ref, opcode, mutation_sequence, expected_revision, *, lease_until=0,
ack_watermark=0, reason=0)` returns 66 bytes. STOP requires `reason=1`, SUSPEND
requires `reason=2`. Only RENEW/RESUME permit lease and ACK/RETIRE permit ACK.
`describe` uses frame session0; all other `Request`s require nonzero session and
request sequence. The codec itself never supplies authority or a clock.

`decode_response(frame, request)` returns integer enum values consistently in a
mapping with `opcode/status/page/prefix/raw_prefix/raw_body/raw/session/
response_sequence` and the appropriate `identity`, `capabilities`, `state`,
`observations`, or `activation`. State also exports `witness`, repeated at the
response level. Prefix names are `generation/handle/standing_number/
intent_digest/revision/mutation_sequence/activation_high_water/ack_watermark`.
State names include `lifecycle/owned_mask/quiescent_mask/flags/lease_until/
epochs/loss_reason/loss_command/accounted_on_ms/last_comparison`. All body
records preserve `raw` bytes, all clocks/counters are Python integers, and the
absent-time sentinel remains `ABSENT_TIME`, never converted to a host clock.

The decoder checks exact 66/124/190 bounds, request echo, boot session, page
selection/length, canonical reserved fields and enums, record identity on
success, prefix/state duplicated counters, ledger capacity, typed last mutation
comparison, feedback/witness layout and prohibition on verified simulation.
Refusals may carry a different currently occupied record identity. A witness
without WITNESS_VALID is exposed as unapproved candidate bytes; source overflow
can leave such bytes in the exact endpoint. The host remains responsible for
continuity across independently sampled pages, installed evidence policy,
durable collection, ACK eligibility, request ordering and recovery.

## Native bridge and private control protocol

The only startup form is `standing-host-pipe --test-control-fd N`, where N>=3 is
an inherited private duplex test descriptor. stdin/stdout carry the original
serial frame stream through unchanged `hms_endpoint_link_feed/next`, attached
`hms_standing`, and original `hms_st_fixture` callbacks. No executable, path,
device or network arguments are accepted; the bridge opens none and forks none.
Start is exact fixture boot1, tick0, flags25, demand25000, automatic feedback,
source epochs1, fixed incarnation a0..af, firmware b0..cf, manifest c0..df.

Private commands and acknowledgments are 9 bytes: opcode then big-endian u64.
Success echoes opcode and argument, except snapshot returns the selected value;
rejection is opcode255/value1. Effects complete before acknowledgment. Commands
are serialized, each service command performs at most three endpoint polls and
each poll retains the endpoint's one-driver-step bound. No sleep/time-based
ordering or automatic clock advancement occurs. Poll waits and output waits
have 1000ms bounds. EOF on either input exits; malformed descriptors/I/O errors
fail closed. Runner supplies overall CPU, file, process and time limits.

| Op | Action / argument |
|---:|---|
| 1 | Set fixture clock to argument and perform one endpoint poll (regression/ABSENT can inject clock faults). |
| 2 | Poll at argument, argument+1, argument+2; argument <= UINT64_MAX-3. |
| 3 | Set demand to low signed32 bits; argument must fit u32. |
| 4 | Set existing fixture injection bitmask, u8. |
| 5 | Read one snapshot selector below; no poll. |
| 6 | Set source epoch, `(channel << 32) | positive_epoch`, channel0/1. |
| 7 | Set platform flags <=127; physical and stop commissioning forbidden. |
| 8 | Set feedback u32; UINT32_MAX means original automatic output-derived feedback. |
| 9 | Set guard denial, 0/1. |
| 10 | Set existing step-advance u32. |
| 11 | Set existing guard-advance u32. |
| 12 | Set existing boundary drift, 0..3. |
| 13 | Set existing witness-time fault, 0..2. |
| 14 | Set source sequence, `(channel << 32) | sequence`, channel0/1. |
| 15 | Fresh synthetic reset to strictly greater boot, with RECONCILE set; refuses pending partial RX/TX. This is a test oracle, not qualified persistent boot/recovery. |

Snapshot selectors: 0 dispatches, 1 loss commands, 2 output, 3 demand sequence,
4 feedback sequence, 5 lifecycle, 6 standing flags, 7 fixture clock, 8 common
generation, 9 standing high-water, 10 activation high-water, 11 ACK watermark,
12 revision, 13 mutation sequence, 14 owned mask, 15 quiescent mask, 16 fixture
platform flags, 17 step advance, 18 guard advance, 19 demand epoch, 20 feedback
epoch, 21 boot, 22 response sequence, 23 loss-command state, 24 conservative
accounted-on milliseconds, 25 ledger count, 26 demand bits, 27 feedback bits.

Setters except tick/cycle do not poll. Read-only snapshots do not change endpoint
state. If both descriptors are ready, available wire bytes are handled first;
this alone cannot order an incomplete frame against a private command. Runner
must await a full wire response before a subsequent control command, and await
the control acknowledgment before the next wire request. Snapshot selectors
are individual samples, so freeze clock/service and collect sequentially when a
multi-value association is needed. The control descriptor is never exposed as
ordinary Runtime wire authority.

## Remaining review and validation

No execution evidence is claimed. Root must review both new sources and runner
permissions/limits, then separately authorize imports, compiler invocation and
native controls. Required later checks include exact golden OPEN/START vectors,
strict malformed decoder cases, framed stream correlation, pristine descriptor
identity, mutation replay/conflict, bounded lifecycle/ledger/loss cases, clock
and source faults, EOF behavior and no automatic service. No mock endpoint,
physical qualification, durable driver queue, production control side channel,
or native resource-ownership table was added.
