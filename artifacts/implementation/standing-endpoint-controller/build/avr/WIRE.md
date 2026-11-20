# Candidate standing-single wire version2

This is the exact source-candidate profile, not deployed hardware support. Existing frame version1/FCS, channel0, request kind1 and response kind2 remain unchanged. Multibyte fields are big-endian; signed values are two's-complement32. Unknown opcode is silent. Known malformed requests return a bounded error. All reserved/unused fields must be zero. No operation accepts more than192 bytes.

Responses use their own existing boot-local monotonic frame sequence. The application prefix now explicitly echoes the request sequence. This corrects the sealed design's missing correlation field:66+124=190 instead of62+128=190. No extra retained buffer is introduced.

## Requests and opcodes

| Opcode | Name | Length | Body |
| --- | --- | ---: | --- |
| 01 | DESCRIBE | 3 | byte2 descriptor page0 identity or1 capabilities; session0, request sequence may0 |
| 10 | BIND | 72 | Same context generation/handle, installed manifest and context digest fields as finite BIND; version byte2; occupied record refuses |
| 12 | REVOKE | 10 | Same current generation/handle and reason6 as finite REVOKE; inhibits common authority before response |
| 40 | OPEN | 134 | Fixed layout below |
| 41 | START | 66 | Fixed mutation; expected revision only |
| 42 | RENEW | 66 | Fixed mutation; expected revision and new lease |
| 43 | STATUS | 49 | Identity bytes0..43; page byte44 (0 state,1 observations,2 activation); activation cursor45..48, zero except page2 |
| 44 | ACK | 66 | Fixed mutation; expected revision and acknowledged prefix |
| 45 | SUSPEND | 66 | Fixed mutation; expected revision and reason2 |
| 46 | RESUME | 66 | Fixed mutation; expected revision and new lease; trusted host attests durable suspended summary/ledger collection |
| 47 | STOP | 66 | Fixed mutation; expected revision and reason1 |
| 48 | RETIRE | 66 | Fixed mutation; expected revision and final ACK watermark |

All requests except DESCRIBE require the exact qualified boot session and nonzero request sequence. BIND/REVOKE use current common authority. Record identity includes original bound authority and stays queryable after invalidation. During a standing record every version1 request, including HELLO/QUERY/RETIRE/ARM, gets explicit UNSUPPORTED; version2 REVOKE remains available. Without standing occupancy the original version1 behavior remains. Under TX backpressure only version1 CANCEL/REVOKE and version2 STOP/SUSPEND/REVOKE may be processed with discarded replies; a partial response is never replaced.

OPEN offsets:0 version2,1 opcode40,2 control generation:u32,6 context handle:u16,8 standing number:u32,12 digest32,44 kernel:u16=1,46 config length:u8=32,47 config32,79 resource mask:u8,80 eight fixed fence:u32 entries,112 initial lease:u64,120 outage policy:u8=0 (bounded local continuation),121 evidence mode:u8 (0 simulation,1 physical),122 activation cap:u32>0,126 expected demand epoch:u32>0,130 expected feedback epoch:u32>0. Unused fence entries are zero. Mask must equal the installed transitive footprint. Digest is nonzero, immutable identity rather than authentication.

Configuration offsets relative to47:0 lower demand:i32,4 upper demand:i32,8 required cooling improvement:i32>=0 (0 disables this predicate),12 minimum on-feedback:i32>0,16 sample period:u16,18 demand max age:u16,20 feedback max age:u16,22 minimum on dwell:u16,24 minimum off dwell:u16,26 feedback window:u16,28 off code0,29 on code1,30 installed loss code0,31 policy0. Durations are1..60000 except dwell may0; sample period must be strictly below both max ages and feedback window. Lower<upper; temperature demand uses installed millidegree units in[-100000,200000], feedback uses installed nonnegative RPM in[0,100000]. This kernel always requests binary0/1 and its first installed aggregate loss contract is0; it makes no claim that this is a safe physical default for another installation.

Mutation offsets:0 version2,1 opcode,2 generation4,6 handle2,8 standing number4,12 digest32,44 positive mutation sequence4,48 expected lifecycle revision4,52 lease8,60 ACK watermark4,64 reason2. Only listed fields may be nonzero for that opcode. Identity comparison covers bytes2..43. Last accepted comparison retains bytes0..1 plus48..65, with sequence separate. Exact accepted duplicates win before current revision checking and do not reapply. Next accepted sequence is previous+1 without wrap. Rejected requests consume nothing. Older requests are OLD_OR_FORGOTTEN; changed retained bytes are CONFLICT. RETIRE discards the record so a retry is OLD_OR_FORGOTTEN. OPEN exact replay compares all134 immutable bytes even after lease/revision changes.

## Response prefix and pages

Every known version2 response has this66-byte prefix:0 version2;1 request opcode|80;2 echoed request sequence:u32;6 status:u8;7 page:u8 (ff means no body);8 original record generation:u32;12 handle:u16;14 current standing number:u32;18 digest32;50 lifecycle revision:u32;54 last accepted mutation sequence:u32;58 activation high-water:u32;62 ACK watermark:u32. When no record exists, record identity/counters are zero, except a syntactically complete record request's identity may be echoed to identify a refusal. Current common authority is supplied by DESCRIBE capabilities. Error responses have no body. Successful RETIRE has no body. OPEN/mutations normally return state page0. DESCRIBE/BIND return the requested/capabilities page; REVOKE returns state page if standing remains, otherwise capabilities.

State page0 is124 bytes with the following page-relative offsets, explicitly serialized in canonical byte form; this is not a native C struct dump. Current standing number/high-water is omitted because the prefix already carries it. Other duplicate counters are retained in the fixed page to keep the exact source-state map simple and independently checkable.

| Offset | Field | Bytes |
| ---: | --- | ---: |
| 0 | slot kind | 1 |
| 1 | lifecycle revision | 4 |
| 5 | last accepted mutation sequence | 4 |
| 9 | last comparison (version/opcode + typed body) | 20 |
| 29 | current prepared/active lease | 8 |
| 37 | activation high-water | 4 |
| 41 | ACK watermark | 4 |
| 45 | next service tick | 8 |
| 53 | first loss tick | 8 |
| 61 | cleanup deadline | 8 |
| 69 | quiescence acceptance tick | 8 |
| 77 | two pinned input epochs | 8 |
| 85 | completed conservative commanded-on milliseconds | 4 |
| 89 | lifecycle state | 1 |
| 90 | drain target | 1 |
| 91 | service phase | 1 |
| 92 | owned mask | 1 |
| 93 | aggregate quiescent mask | 1 |
| 94 | first loss reason | 2 |
| 96 | standing flags | 2 |
| 98 | ledger head | 1 |
| 99 | ledger count | 1 |
| 100 | pending feedback slot (ff absent) | 1 |
| 101 | loss command state | 1 |
| 102 | aggregate witness | 22 |

Observation page1 has two24-byte records: value:i32@0, acquired:u64@4, sequence:u32@12, source epoch:u32@16, quality:u8@20 (0 absent,1 good), continuity:u8@21 (1 exact declared sequence continuity), pending evaluation:u8@22, reserved0@23. Invalid candidates latch faults without replacing last accepted values/identities. Duplicate publication does not set pending evaluation.

Activation page2 returns exactly one44-byte record matching the positive cursor: ID:u32@0, dispatch tick:u64@4, demand sequence:u32@12, demand value:i32@16, demand age:u16@20, feedback sequence:u32@22, feedback acquisition:u64@26, feedback value:i32@34, previous output:u8@38, requested output:u8@39, state flags:u8@40, evidence/quality:u8@41, reason:u16@42. State flags:bits0..2 pending1/succeeded2/failed3/FEEDBACK_INTERRUPTED4/unknown5, bit3 possibly acted, bits4..5 verification (existing enum), bits6..7 zero. Evidence byte bits0..2 existing evidence enum, bit3 good quality, bits4..7 zero. Before the first post-dispatch observation, feedback tick is UINT64_MAX and its sequence is the pre-dispatch source floor, not feedback evidence. A valid response requires a strictly later acquisition tick and advancing sequence. Cursor<=ACK is OLD_OR_FORGOTTEN; cursor>high-water is NOT_SEEN; retained-ID mismatch is an internal fault, never fabricated data.

FEEDBACK_INTERRUPTED means evaluation ended after a known synchronous command handoff without establishing its goal predicate. It retains possibly-acted and UNVERIFIED; it is neither physical cancellation nor successful completion. Its ACK is refused until the separate loss service has a valid aggregate witness, full owned-mask quiescence and no unresolved/disputed loss. The trusted host must still durably retain the interrupted/unverified outcome and its loss summary; ACK cannot convert it into goal-success evidence. An unknown ordinary handoff remains state5 and is never downgraded to state4. A later unknown loss handoff blocks ACK of state4 even when the simulator internally knows its output became zero. State3 denotes the declared feedback criterion not being established within its window, not a universal diagnosis of mechanical failure.

Witness22: source index:u8@0 (feedback1), quality:u8@1, evidence:u8@2, verification:u8@3, source sequence:u32@4, acquisition:u64@8, value:i32@16, settled output:u8@20, reserved0@21. Its epoch is the pinned source epoch. It qualifies only the installed whole-mask aggregate predicate. A full ordinary ledger cannot consume this witness slot.

The aggregate witness must be acquired strictly after the confirmed actual loss-command handoff; first-loss time alone is insufficient, and acquisition at the same coarse tick is refused. Internally, while loss state3 and WITNESS_VALID is clear, the8 bytes otherwise reserved for quiescence acceptance temporarily retain that precise handoff tick. Wire state pages serialize quiescence time as ABSENT until a witness is valid. A valid witness replaces the temporary tick with quiescence acceptance time. First-loss time and cleanup deadline are never repurposed. Timeout/unknown dispatch cannot populate this handoff value; no additional timestamp buffer or full loss-command trace is claimed.

DESCRIBE identity page0 is80 bytes: incarnation16, firmware32, manifest32. Capabilities page1 is116 bytes: current generation:u32@0, handle:u16@4, context digest32@6, now:u64@38, platform flags:u16@46, common state:u8@48, resource count:u8@49, slot kind:u8@50, installed mask:u8@51, kernel:u16@52, input count2@54, ledger capacity2@55, config size32@56, feature bits1@57 (single standing/finite exclusion), maximum lease:u32@58, installed maximum commanded-on milliseconds:u32@62, cleanup budget:u16@66, demand epoch:u32@68, feedback epoch:u32@72, historical standing high-water:u32@76, finite high-water:u32@80, eight fence floors:u32@84. Maximum response is190 bytes. Request cursors are not retained. Pages are independently sampled, not an atomic multi-page export.

Status values0..22 preserve the finite status enum. New values:23 BAD_REVISION,24 ACK_PENDING,25 BAD_PAGE,26 SOURCE_INVALID. Lifecycle0 none,1 PREPARED,2 ACTIVE,3 DRAINING,4 SUSPENDED_QUIESCENT,5 STOPPED_QUIESCENT,6 FAULT_UNKNOWN. Slot0 empty,1 finite,2 standing. Flags bits0..12: ever-possible, unresolved, disputed, initial-start, prepared-after-resume, demand-ready, feedback-ready, witness-valid, first-loss, loss-command-possible, exhausted, demand-fault, feedback-fault; bits13..15 zero. Loss states0 none,1 requested,2 possible,3 driver-finished,4 unknown. Drain target4 suspend,5 terminal stop,6 fault. Reasons0 none,1 STOP,2 SUSPEND,3 LEASE,4 LEDGER,5 STALE,6 QUALITY,7 EPOCH,8 GAP,9 FEEDBACK,10 GUARD,11 AUTHORITY,12 CLOCK,13 DRIVER,14 COUNTER,15 ACCOUNT,16 TIMING.

## Lifecycle and driver boundaries

OPEN validates configuration, source bindings, common authority/platform, exact footprint and all fences before atomically retaining bytes and ownership. It does not require finite ARM. Common BIND authorizes the context; OPEN's explicit lease authorizes the standing interval. A pure installed guard must establish the declared initial baseline without unowned acquisition. PREPARED acquires under its reservation and START requires fresh exact inputs and matching baseline; initial/resumed preparation both retain claims through expiry until eligible RETIRE.

ACTIVE rotates bounded demand acquisition, feedback acquisition and evaluation phases. One poll performs at most one I/O driver step. No missed-period catch-up loop exists. A fresh demand evaluation enforces hysteresis/dwell; at most one transition awaits feedback. On feedback verifies RPM>=configured minimum and optional demand improvement by the response deadline; off feedback requires RPM0. Simulation evidence never becomes physical verification. Actual output handoff must enforce the passed exclusive cutoff; unknown/late handoff becomes unresolved and cannot be ACKed.

The installed step receives a read-only authority view carrying the exact immutable deployment, current ordinary activation, common context, owned footprint and admitted fences. It rechecks those bindings at the actual handoff together with the supplied cutoff, which includes lease/response-window, input-age and cumulative-accounting limits. The supplied synthetic driver performs a synchronous bounded handoff and has no native output queue. A queued provider must retain and enforce the same exact identity/limits within its separately accounted driver storage; that capability is not demonstrated here. Disputed callback evidence is latched separately and cannot be ACKed or cleared by a later ordinary callback.

The ordinary activation identity is `(incarnation, qualified boot, standing number, activation number)`, bound to the immutable digest/configuration and exact fences. The current core invokes its synchronous ordinary handoff at most once for that identity, including when the result is unknown. A future queued provider must deduplicate exact repeated admission to the same retained activation without another effect, refuse changed content under the identity, enforce current cutoffs/fences at dequeue, and retain uncertainty instead of retrying a possible effect. Its queue/replay storage and crash semantics must fit a separately reviewed allocation; this component supplies no durable driver queue or exactly-once physical-effect claim.

Acquisition crosses the same authority boundary: PREPARED/ACTIVE context, exact installed input epochs, owned footprint, current qualified clock and exclusive acquisition lease are checked before a bus operation or source-sequence advance. Loss observation instead uses retained ownership, exact source bindings and cleanup cutoff even after context revoke. A post-callback epoch check latches drift before any further ordinary work. Clock/cutoff failure cannot be disguised by advancing an acquisition sequence; independent physical protection under unavailable clock remains unimplemented.

Renew before the existing cutoff only; neither renewal nor resume resets accounting or activations. Capacity is two unacknowledged records. ACK frees only a contiguous eligible terminal/known/undisputed prefix committed by the trusted host and never releases ownership; interrupted feedback has the additional aggregate-settlement gate above. On loss ordinary observations/work freeze, pending known feedback becomes FEEDBACK_INTERRUPTED with the cause, and the separate installed loss path obtains a dedicated aggregate witness. Unknown output/clock/driver evidence stays unresolved. A known quiescent loss stops conservative on-time accounting at the witness/settlement time; this may overcount until confirmed quiescence and is not a physical-energy measurement.

Only explicit SUSPEND, lease expiry and ledger exhaustion are resumable in this initial profile, with valid unchanged context/epochs and no unresolved/disputed evidence. After durable loss summary and complete ordinary prefix collection, RESUME prepares a fresh lease and observations; START is separate. Before clearing the exported witness, its accepted feedback identity/value/time advances the retained feedback observation watermark; fresh sample sequences then advance from that actual predecessor. Freshness-ready flags remain clear until a new acquisition, so this does not reuse the witness as a fresh trigger. RETIRE requires terminal quiescence, no unresolved/disputed effects and complete ACK. It alone releases the reservation. Source changes, clock faults, revoke and unknown outcomes require external qualified recovery/new boot as appropriate; this profile has no wire command that clears those facts.
