# Compact endpoint wire profile — proposed v0.1

Status: experimental application profile with an original [portable C executor and link wrapper](../protocol/endpoint/README.md), a [Python packet/receipt codec](../hms/endpoint_wire.py) and synthetic byte/state fixtures. The implementation and its verification receipts remain separate from a commissioned physical adapter or physical conformance. The [serial codec](../protocol/serial/README.md) only frames bytes. All supplied fixtures are synthetic and physically uncommissioned. It is an independent HMS design, not official Anthropic MHS, Firmata or PPP compatibility. The earlier [design-only source/review snapshot](../artifacts/verification/endpoint-design-snapshot/index.json) is retained.

The [execution core](02-execution.md), [host profile](08-host-contract.md), [constrained requirements](07-constrained-binding.md) and [embedded source findings](../docs/embedded-evidence.md) remain applicable. A gateway retains the durable host operation, descriptions, authentication and policy. A small endpoint enforces an installed primitive table, local limits, one finite execution slot, boot/control domains, resource fences and local timing. The protocol does not upload arbitrary code, register addresses, native structs, pointers, JSON or unbounded procedures.

## Selected baseline and trust

The baseline has one slot shared by queued/running work and its retained receipt, eight local resource positions, at most 72 argument bytes and at most 32 result bytes. A position names an installed resource, not a pin. A primitive ID selects an installed function and exact argument/result layouts. An AVR or an RTOS target may implement this same baseline. More concurrent slots, uploads, procedure bytecode, large objects and telemetry require separately versioned extensions; unused capacity is not permission to invent another layout.

The route is the commissioned, physically protected, exclusively owned full-duplex binary serial route of chapter 07. The trusted gateway must prevent model/ordinary-client access to raw frames. FCS and digests do not authenticate senders. An untrusted bus, serial server, shared host process or wireless route requires an independently specified authenticated transport and replay/freshness argument before physical commissioning. Neither a host challenge echo nor a random-looking boot banner supplies that argument.

No wire request commissions a physical machine or clears an unknown physical history. A platform starts with ordinary actuation inhibited. Its installed boot/loss/stop policy and a qualified local commissioning/reconciliation input determine whether effects can ever be enabled. A simulator can implement explicitly synthetic eligibility; this is not a physical commissioning shortcut.

## Independent identities and retained host mapping

| Identity | Scope and rule |
|---|---|
| Enrolled incarnation, 16 bytes | Stable installation-assigned endpoint identity; not an address or a generated-at-boot random value. A replacement/rollback recovery gets a new enrolled incarnation. It is identity data, not authentication. |
| Boot epoch, `u64` | Nonzero, qualified, never reused within the enrolled incarnation; also the serial frame session. Changes when volatile execution history is lost. |
| Control generation, `u32` | Endpoint-owned monotonic counter within the boot; begins at 1. Successful BIND and REVOKE increment it without wrap. Manual intervention/lost continuity inhibits ordinary work and advances or faults this domain. |
| Context handle, `u16` | Host-assigned, positive and strictly increasing for successful BINDs within the boot. It selects a full immutable host mapping, not a capability inferred from a number. No handle reuse after revocation. |
| Call number, `u32` | Positive, host-assigned and never reused for another operation within this endpoint boot. The endpoint retains a boot-wide accepted high-water mark, across control/context changes. Gaps are allowed. |
| Resource fence, `u32` | Positive, monotonic per installed resource position within this endpoint boot; cannot preempt an unresolved holder. No narrowing of a larger host token is allowed. |
| Frame sequence, `u32` | Directional diagnostic/request-correlation number. It is not an operation key or an execution proof. Duplicated/reordered frames can reach the application. |

The durable host replay key remains `(principal, deployment, replay namespace, caller operationKey)`. It is not shortened to a call number. Before handing bytes to a driver, the host durably records the existing admitted operation and its dispatch ownership, enrolled incarnation, boot/control/context tuple, call number, complete binary OP payload, full intent digest, local fence mapping and clock translation. A repeated host key resolves that same host operation; it cannot allocate another endpoint call.

The host context digest pins a retained mapping containing the full type/firmware/installed-manifest/binding/calibration revisions, primitive IDs and encodings, units/frames/scales, local-to-global resources, evidence/stop policies and timing qualification. Full artifacts remain on the host. The endpoint compares the supplied installed-manifest digest to its installed constant and stores the host context digest as an opaque binding tag. It does not reconstruct or verify a WoT document or host JSON intent. Only a trusted admitted gateway can perform that mapping.

On host restart, restore this mapping and query the existing call. A missing/rolled-back mapping is a reconciliation fault, not authority to renumber or resend. Reopening UART/USB or changing its stream epoch does not restart the endpoint: boot, control, fences, accepted high-water mark, lease and slot remain. Parser state is reset on a transport fault, but operation state is not.

## Boot and nonvolatile platform obligations

This baseline selects a qualified persistent boot counter, rather than assuming a CSPRNG or specifying an unproved challenge protocol. Before any output path can perform ordinary effects, the platform must establish the next boot epoch durably and verify it. Loss/reset of any volatile execution/replay state must pass this gate, including watchdog resets and relevant brownouts. Software reset that retains the old advertised epoch while clearing the slot is forbidden.

The platform must document atomic/torn-write recovery, brownout behavior, endurance/wear leveling, exhaustion, erased/uninitialized NVM, rollback/backup protection, and every reset cause. A CRC or two EEPROM copies alone is not a proof of monotonicity. Firmware restore or replacement NVM cannot silently restore an older epoch under the same incarnation. An exhausted or ambiguous counter enters fault/inhibit; recovery requires a separately authorized new incarnation or a qualified repair process. No wrapping counter or entropy estimate is substituted.

The generic protocol does not choose an EEPROM journal algorithm or certify an AVR EEPROM. A platform unable to meet these requirements may answer diagnostic HELLO with frame session zero and `boot_qualified=0`; BIND, ARM and OP must be denied. An authenticated, ordered reset/drain barrier could be a future alternative profile, but is not implemented or assumed here.

Boot-counter durability only prevents old-session frames from becoming new commands. It does not atomically commit a physical effect and receipt. The baseline slot, receipt and fence floors are volatile. A reset after a possible physical prefix loses its outcome; the host preserves `outcome_unknown` and claims. The new endpoint reports reconciliation required and ordinary inhibition until the installed local recovery procedure establishes an acceptable state. New boot identity is not evidence of rest, homing, absence of dispensing or an empty native-controller queue.

## Envelope, integers and exact lengths

Use the chapter 07 serial frame, version 1, channel 0. Host requests use kind 1; endpoint responses use kind 2. Kinds 3/4 and other channels have no executable meaning in this baseline. Payload version is byte `01`; byte 1 is the opcode. All multi-byte application integers are unsigned big-endian unless the installed primitive explicitly declares a signed argument/result. No native struct layout, implicit padding, float or endian inference is permitted.

HELLO request alone uses frame session zero. Its response uses the current qualified boot epoch or zero when unqualified. Every other request/response must use the exact current nonzero boot epoch. A mismatched boot is rejected before any slot/fence change. Unknown versions/opcodes, wrong kind/channel, reserved bits or non-exact lengths reject the entire request without effects. Length checks precede every field access.

Frame sequence zero is reserved for a HELLO request made without an established boot domain. Otherwise senders use positive non-wrapping sequences within `(incarnation, boot, direction, channel)` and retain their next value across host reconnect/restart. Duplicates retain their original sequence; sequence ordering alone never admits or repeats an action. A sender that cannot recover its counter must not invent continuity or issue ordinary work. Exhaustion requires inhibited, reconciled establishment of a qualified new boot domain. This restriction does not prevent the independent local stop/loss mechanism from operating. A HELLO response to a zero-sequence probe is diagnostic; it alone cannot qualify freshness for physical admission.

Each response begins with `version:u8, response_opcode:u8, echoed_request_sequence:u32, status:u8` (7 bytes). Response opcode is request opcode OR `80`. Its frame sequence is the endpoint's own sequence. The host correlates boot, expected opcode and echoed request sequence; it retains possible dispatch on mismatch/loss. Nonzero-status responses are exactly these 7 bytes, contain no receipt, and do not establish the outcome of a previous possibly delivered request. A successfully processed request returns the exact success layout below. Rate-limit diagnostics and keep at most one pending transmit response; no unbounded error queue is allowed.

| Request opcode | Name | Exact request payload bytes | Successful response bytes |
|---:|---|---:|---:|
| `01` | HELLO | 2 | 186 |
| `10` | BIND | 72 | 69 |
| `11` | ARM | 48 | 69 |
| `12` | REVOKE | 10 | 69 |
| `20` | OP | `88 + 4*popcount(resource_mask) + argument_length`, at most 192 | `86 + result_length`, at most 118 |
| `21` | QUERY | 44 | `86 + result_length`, at most 118 |
| `22` | CANCEL | 44 | `86 + result_length`, at most 118 |
| `23` | RETIRE | 44 | 7 |

All unspecified/reserved values are refused. An implementation may close/reset framing after malformed input; it must not execute a valid prefix.

## HELLO and installed primitives

The success HELLO response is the 7-byte prefix followed, in order, by: incarnation `[16]`, firmware SHA-256 `[32]`, installed-manifest SHA-256 `[32]`, current control generation `u32`, last bound context handle `u16`, current/last host context digest `[32]`, endpoint state `u8`, flags `u16`, resource count `u8`, maximum argument bytes `u8`, maximum result bytes `u8`, active capacity `u8`, receipt capacity `u8`, current boot-local tick `u64`, armed-until tick `u64`, accepted call high-water mark `u32`, held-resource mask `u8`, and eight resource fence floors `8*u32`. Total: 186. Unused resource positions/floors are zero. Before the first binding, handle and context digest are zero. Revocation retains the last handle/digest for diagnosis but does not make that context executable.

Flags: bit 0 boot qualified; bit 1 physical/history reconciliation required; bit 2 physical commissioning valid; bit 3 simulator only; bit 4 local monotonic clock qualified; bit 5 ordinary actuation inhibited; bit 6 independent stop commissioned. Bits 7–15 are zero. Simulator-only and physical-commissioning flags cannot both be set. Independent-stop commissioning cannot be inferred from another flag. Current fixtures set simulator-only and never physical commissioning/independent-stop commissioning.

Endpoint states: 0 RESET_INHIBITED, 1 BOUND_DISARMED, 2 ARMED, 3 DRAINING, 4 FAULT_LOCKED. Slot execution is a separate state, so ARMED can have a queued/running call. HELLO is a bounded snapshot, not an authenticated discovery catalogue or fresh physical observation.

The installed manifest defines each nonzero `u16` primitive ID: exact argument/result layouts; checked integer ranges/scales/units/frames; required resource positions; local predicates/interlocks and freshness; maximum run and cleanup bounds; step/yield behavior; cancellation/loss response; and required completion, verification and quiescence evidence. IDs are not reserved for the three host simulator examples. A primitive can implement bounded motion, timed I/O, sample acquisition or an already installed finite procedure if its local implementation and metadata qualify. Unknown primitives, missing resources, invalid arguments and unsupported evidence requirements are refused. Updating firmware, calibration, resource layout or primitive semantics invalidates the manifest/context and requires the maintenance/commissioning path, not an OP payload.

## Binding, arming and revocation

BIND after the 2-byte request prefix contains `expected_control_generation:u32, new_context_handle:u16, installed_manifest_digest:[32], host_context_digest:[32]`. It is allowed only in RESET_INHIBITED or BOUND_DISARMED with qualified boot/clock, no occupied slot or unresolved claims, ordinary inhibition and cleared platform reconciliation requirements. The expected generation must equal the current one. The handle must exceed the previous handle; both digests must be nonzero, and installed manifest must match. Validate everything before storing the new context and incrementing control generation once. Result is BOUND_DISARMED with a valid bound context, never automatic ARM. A repeated BIND with an old expected generation cannot increment again; query HELLO to resolve a lost reply. Handle/generation exhaustion faults ordinary admission before wrap.

ARM contains `control_generation:u32, context_handle:u16, host_context_digest:[32], lease_until_tick:u64` after its prefix. It requires BOUND_DISARMED or ARMED state, the exact current valid bound context, local eligibility, no reconciliation/fault and a qualified clock. The last handle/digest retained for diagnosis after REVOKE is not a valid bound context. `now < lease_until_tick <= now + min(installed_max_lease_ms, 60000)`, checked without overflow. It permits ordinary admission under that context; it is not a primitive invocation or a claim of safe motion. A successful renewal can increase the context lease to the supplied absolute tick, but never alters an existing OP's immutable lease/deadlines. Replaying an older ARM cannot extend beyond its original absolute tick or shorten the current lease. After expiry, only a fresh valid ARM in the still-qualified context can restore eligibility; pending/running work has already followed its loss policy.

REVOKE contains `expected_control_generation:u32, context_handle:u16, reason:u16` after the prefix. It requires the exact current generation and nonzero current context handle, endpoint state BOUND_DISARMED or ARMED, and reason exactly 6 (control revocation) in this version; other reason values are reserved. Validate these fields before changing state. Processing it inhibits ordinary work and increments control generation before acknowledging. It must be serviced within the installed control-service bound and cannot enter the ordinary-operation queue; qualifying that bound requires bounded primitive callbacks. A queued call becomes REJECTED_BEFORE_START with no possible effect. Running work enters the installed bounded loss response; claims remain until its documented quiescence condition. If the generation cannot advance, fault/inhibit instead of wrapping. A stale duplicate cannot revoke a later generation. REVOKE does not clear a slot, reset the call/fence floors or authorize a replacement binding. A new BIND is required after revocation.

The 69-byte BIND/ARM/REVOKE success response is the response prefix followed by `current_control_generation:u32, last_context_handle:u16, host_context_digest:[32], endpoint_state:u8, flags:u16, now_tick:u64, armed_until_tick:u64, accepted_call_high_water:u32, held_resource_mask:u8`. An inactive arm deadline is zero. A response records controller state only; revocation acknowledgement is not termination or physical rest.

REVOKE clears bound-context validity and the arm deadline. It leaves RESET_INHIBITED when no possible execution needs draining, otherwise DRAINING until the installed loss/quiescence condition is established, then RESET_INHIBITED. Context ARM lease expiry alone preserves context validity: it leaves BOUND_DISARMED after unstarted exclusion or finished quiescence, with DRAINING while a running loss response remains unresolved. ARM is forbidden during DRAINING and cannot resume expired work. A per-operation cutoff applies its loss policy to that call without changing the independently bounded context lease; the occupied slot still excludes new work, and no ARM renewal can resume the expired call. Neither transition evicts the retained receipt; BIND still waits for RETIRE. A clock/continuity fault overrides these states with FAULT_LOCKED.

## OP bytes and local admission

| Payload offset | Bytes | Field |
|---:|---:|---|
| 0 | 1 | Payload version `01` |
| 1 | 1 | Opcode `20` |
| 2 | 4 | Control generation |
| 6 | 2 | Context handle |
| 8 | 4 | Call number |
| 12 | 32 | Complete host intent SHA-256 value, without textual `sha256:` prefix |
| 44 | 2 | Installed primitive ID |
| 46 | 1 | Resource mask; bits 0–7 refer to installed positions |
| 47 | 1 | Argument length, 0–72 |
| 48 | 1 | Required effect: 0 capability completion, 1 physical verified |
| 49 | 1 | Flags, exactly zero |
| 50 | 2 | Reserved, exactly zero |
| 52 | 8 | Not-before boot-local tick |
| 60 | 8 | Exclusive latest-start tick |
| 68 | 8 | Exclusive latest-completion tick |
| 76 | 4 | Positive maximum run milliseconds |
| 80 | 8 | Exclusive operation lease-until tick |
| 88 | `4*n` | Positive fences, in ascending set-bit order of the resource mask |
| `88+4*n` | 0–72 | Installed primitive's exact argument bytes |

With all eight resources and 72 arguments, `88+32+72=192`; decoded serial frame is 214 bytes and conservative escaped wire bound is 430 bytes. A smaller mask does not raise the 72-byte argument ceiling. Resource mask must be nonzero and exactly the installed primitive's admitted requirement in this baseline; an action requiring no external resource reserves an installed executor resource. There is no separate bulk upload or fragmentation of OP.

After envelope/length/boot validation, a retained same call compares the entire immutable OP payload, including digest, timing and fences. Exact equality returns its current receipt with no further admission or effect. Different bytes return CONFLICT even when the supplied digest is identical. This comparison occurs before current-lease/context eligibility so a revoked/expired operation can still be identified. An absent call at or below the accepted high-water mark is OLD_OR_FORGOTTEN and cannot execute.

For a new call above the high-water mark, require a free slot, ARMED current context, installed argument/evidence validity, current local predicates, time/lease validity, and all requested resources locally quiescent/unowned. Every proposed fence must exceed its resource floor. A higher token does not displace an active/unknown holder. Validate all fields/fences before changing any state. Commit the complete bounded payload to the volatile slot, advance the call high-water mark and all involved fence floors, and acquire all resource bits before returning QUEUED or calling a driver. No partial resource admission is permitted. Refusal before this transition changes no call/fence/slot state and performs no effect.

This volatile QUEUED receipt is endpoint acceptance within the boot, not the host core's durable `accepted` event. Immediately before the first possible output/native-driver dispatch, recheck context, resource ownership/fences, all local predicates and time; mark RUNNING and `may_have_acted=1` before calling the primitive. Subsequent ordinary steps retain these checks at the installed, bounded service points. An unbounded callback cannot qualify. The endpoint need not compute SHA-256: it retains the full host digest and exact compact payload, while the gateway verifies their admitted mapping. A malicious gateway can lie about that mapping; this physically protected profile does not solve that threat.

## Clock and deadline interpretation

The clock is a qualified monotonically advancing `u64` count of milliseconds since this boot. Hardware may use a smaller timer only if a platform-owned extension detects every wrap, snapshots atomically and cannot lose time during interrupt masking/sleep. AVR multi-byte reads need an audited bounded critical section. The value must not wrap or reach the all-ones absent-time sentinel; loss of clock continuity faults/inhibits ordinary work. A plain wrapping `millis()` value is not this clock.

All operation deadlines are absolute in this boot domain. This avoids granting a new budget each time a delayed frame arrives or interpreting a stale timestamp as current after a 32-bit wrap. Host UTC deadlines are converted using a measured clock mapping, epoch and conservative transit/drift/uncertainty bounds; without those bounds the gateway must not claim the corresponding physical timing contract. No UTC synchronization protocol is supplied here.

Require `not_before < latest_start <= latest_completion`, `now < latest_start`, and `latest_completion <= operation_lease_until <= armed_until` at new admission. Every future boundary must be within the installed horizon, at most `0x7fffffff` ms from now; maximum run is 1 through the smaller of that horizon and the primitive's installed bound. If not-before is already past, it is satisfied, not rewritten. At start require `not_before <= now < latest_start`; after start ordinary steps require `now < start+max_run`, `now < latest_completion`, and `now < operation_lease_until`. All additions are checked `u64` operations. Equality to a cutoff is expired.

Expiry before start produces REJECTED_BEFORE_START with `may_have_acted=0` and releases the unstarted local claims. Expiry/clock failure after possible output invokes the installed loss response, retains possible effects and does not assert completion or rest. A controlled deceleration may need further pulses after the ordinary-work cutoff; only its separately bounded installed cleanup policy authorizes those pulses. A trusted clock/qualification snapshot is required after potentially time-consuming predicates and driver callbacks: a completion received after a cutoff cannot be backdated to callback entry. Installed drivers must enforce the immutable cutoff at actual I/O service points and declare their worst-case service bounds. Successful checks do not themselves prove physical completion before a wall-clock deadline.

## Receipt, cancellation and exact eviction

QUERY, CANCEL and RETIRE have the same 44-byte request shape: the 2-byte prefix, recorded `control_generation:u32, context_handle:u16, call_number:u32, intent_digest:[32]`. They target the existing boot-local record, including an older control generation after revocation. They do not reacquire its resource lease. Wrong digest/context for a retained call returns CONFLICT. They remain serviceable when ordinary admission/clock/lease is degraded, subject to the independently qualified CPU/driver service bound.

Successful OP/QUERY/CANCEL replies contain this layout after the 7-byte prefix:

| Offset | Bytes | Field |
|---:|---:|---|
| 7 | 4 | Recorded control generation |
| 11 | 2 | Recorded context handle |
| 13 | 4 | Call number |
| 17 | 32 | Host intent digest |
| 49 | 1 | Execution state |
| 50 | 1 | Cancellation state |
| 51 | 1 | Result evidence kind |
| 52 | 1 | Effect verification |
| 53 | 1 | Held-resource mask |
| 54 | 1 | `may_have_acted`, exactly 0 or 1 |
| 55 | 2 | Reason code |
| 57 | 4 | Receipt revision, positive and non-wrapping |
| 61 | 8 | Queued-at tick |
| 69 | 8 | Started-at tick or `ffffffffffffffff` |
| 77 | 8 | Terminal-at tick or `ffffffffffffffff` |
| 85 | 1 | Result length, 0–32 |
| 86 | 0–32 | Installed primitive result encoding |

Execution states are 1 QUEUED, 2 RUNNING, 3 COMPLETED, 4 FAILED, 5 CANCELED, 6 REJECTED_BEFORE_START, 7 OUTCOME_UNKNOWN. Cancellation states are 0 NOT_REQUESTED, 1 REQUESTED, 2 ACKNOWLEDGED, 3 REJECTED, 4 CONFIRMED. Evidence kinds are 0 NONE, 1 COMMAND_ECHO, 2 ESTIMATE, 3 CONTROLLER_MEASUREMENT, 4 PHYSICAL_SENSOR, 5 SIMULATION. Verification is 0 UNVERIFIED, 1 VERIFIED, 2 FAILED, 3 DISPUTED. Reason codes: 0 none, 1 start expiry, 2 runtime expiry, 3 completion expiry, 4 lease expiry, 5 client cancellation, 6 control revocation, 7 clock fault, 8 driver fault, 9 ambiguous execution, 10 interlock, 11 reconciliation required, 12 counter exhaustion.

QUEUED and REJECTED_BEFORE_START have no possible output, absent start tick and no result; rejected work holds no resources. RUNNING sets possible output before dispatch. COMPLETED requires the installed completion evidence; an operation requiring physical verification additionally requires qualified physical evidence in that completion. Simulation and command echo never yield VERIFIED. NONE has zero result bytes; any returned value is interpreted only using its pinned result schema and evidence policy. Completed/failed/canceled terminal execution cannot be silently rewritten; later disagreement is a disputed receipt/host audit event. Receipt revision orders updates within the one record and never acts as a durable event cursor.

Held-resource bits must be a subset of the admitted mask; queued/running/unknown work cannot lose its unresolved claims. Known timestamps preserve queued-before-start-before-terminal ordering. If a clock fault makes a later time unknown, use the absent sentinel and an explicit clock-fault reason, not a fabricated timestamp. Receipt timestamps describe execution bookkeeping, not sensor acquisition. A measurement primitive must define acquisition time, freshness, uncertainty and quality in its bounded result layout/context or decline the corresponding observation guarantee.

CANCEL of QUEUED proves local start exclusion, produces CANCELED/CONFIRMED with no possible effect, and releases its claims. CANCEL after possible output records REQUESTED and services the installed cancellation path. An acknowledgement cannot release claims or become CANCELED until the documented termination condition is established. Cancellation may be rejected by an installed primitive. Completion can win the race and coexist with a requested/acknowledged/rejected cancellation; CONFIRMED requires CANCELED. CANCEL of a terminal record returns that record without restarting cleanup or rewriting execution. Cancellation is not independent stop.

Terminal state does not alone release resources. The installed quiescence predicate clears the held mask and advances receipt revision; an unknown or disputed outcome, or unverified required quiescence, retains the remaining held bits. A later ordinary callback cannot resolve a disputed receipt. Native controller queues, energy and shared workspace must be included in that predicate. Never infer it from the host disconnecting or the function returning.

There is **no timeout or LRU receipt eviction**. The single slot blocks new OPs even when terminal and quiescent until explicit RETIRE. The host may send RETIRE only after durably storing the complete terminal receipt and its mapping, and resolving required host evidence. The endpoint accepts RETIRE only for its exact retained terminal record with held mask zero and no unresolved/disputed outcome. It frees payload/result storage but leaves the boot-wide call high-water mark and every fence floor unchanged. Success is a 7-byte response. A lost RETIRE response is resolved by QUERY; a repeated RETIRE after freeing returns OLD_OR_FORGOTTEN and performs no action.

An absent call `<= high_water` always returns OLD_OR_FORGOTTEN, not “completed” or “never executed”; gaps mean the endpoint cannot even assert that every lower number was accepted. An absent call `> high_water` returns NOT_SEEN, which is only the current snapshot: an already queued transport copy may still arrive. CANCEL of NOT_SEEN does not install a future tombstone. Before treating an uncertain absent command as excluded, the host must revoke its control domain and reconcile/drain the route; it must not simply assign the same intent a new number. When a reply is lost, use QUERY, never automatic OP retry or a new physical operation key. Endpoint duplicate suppression handles actual copies; it is not a retry policy.

## Local state transitions and independent stop

| Trigger | Required transition |
|---|---|
| Reset/history loss | Platform output/loss gate first; qualify next persistent boot epoch; RESET_INHIBITED with reconciliation requirement as applicable. Never resume an old slot automatically. |
| Valid BIND while slot-free and reconciled | Advance control, install opaque context, BOUND_DISARMED. |
| Valid ARM | ARMED with absolute context lease; no primitive effect. |
| Valid new OP | One volatile QUEUED slot and all resource fences/claims committed before reply. |
| Eligible start | RUNNING/possible-output recorded before primitive dispatch. |
| Local completion/failure/cancellation evidence | Update receipt; keep claims until installed quiescence evidence. |
| Link loss | Reset partial frame; preserve slot/epochs/fences. Continue or interrupt only under installed loss policy and existing immutable budgets; no reconnect lease renewal. |
| REVOKE/manual intervention/lease failure | Inhibit ordinary starts; invalidate control as specified; drain using installed loss policy; no arbitrary replacement work. |
| RETIRE after terminal quiescence | Free receipt bytes; preserve call and fence floors. |
| Unknown continuity/counter exhaustion | Fault/inhibit; preserve known claims/evidence until separate qualified recovery. |

The parser, a normal CANCEL frame and REVOKE share serial bandwidth; none is an emergency-stop channel. A 430-byte frame can occupy the wire for the arithmetic interval in chapter 07 before another frame is transmitted. UART flood, a stalled callback, full transmit ring or journal failure cannot be assumed to leave that path bounded. A commissioned independent stop/loss path uses an appropriate independent interlock/timer/controller/output mechanism and a bounded installed stop procedure; it cannot carry arbitrary new motion. Its degraded audit behavior must be explicit. It must remain operative when the host cannot log, but this draft implements no such path and claims no stop latency.

A watchdog reset is not universally a safe stop: gravity, stored energy, heaters and native controllers require assessed behavior. Stop/deceleration code must continue being serviced if that is its termination mechanism. Reporting a step count or requested target is command/controller state, not automatically a measured position or rest condition.

## AVR memory allocation plan and RTOS mapping

The following is a proposed **allocation ceiling**, not measured endpoint firmware. The existing pinned ATmega328P build measured a 219-byte parser and a 558-byte flash/221-byte static-RAM minimal framing harness; it did not contain this executor. The board's 2,048 SRAM bytes do not make the following plan pass without a complete link map and measured worst-case stack/ISR load.

| SRAM allocation | Planned bytes |
|---|---:|
| Existing AVR framing parser, including 214 decoded bytes | 219 |
| Custom UART RX ring and indices/error flags | 70 |
| One raw TX frame scratch buffer; no 430-byte escaped copy | 214 |
| Incremental escape/FCS/transmit state | 10 |
| UART TX ring and indices | 67 |
| Immutable OP slot, 192 bytes plus length | 193 |
| Receipt metadata and maximum 32-byte result | 69 |
| Eight local resource fence floors | 32 |
| Boot/control/context/digest/call/clock/arm/diagnostic state allowance | 96 |
| Timer, driver-service and NVM-update scratch allowance | 64 |
| Installed primitive/board persistent working state allowance | 256 |
| Main/interrupt/primitive stack reservation | 512 |
| Total allocated/reserved | **1,802** |
| Remaining for other globals/alignment/margin within 2,048 | **246** |

Store manifest/firmware digests, primitive tables, constant layouts and strings in flash/qualified NVM, not implicit AVR RAM copies. Use explicit byte accessors; do not rely on packed unaligned structs. TX streams escaping from the raw frame and never blocks while draining a full ring. No heap, recursive parser, VLA, printf buffer, extra full OP copy or stock-library hidden UART/Wire/Servo allocation is included. Every selected driver must fit the 256-byte allowance or the target profile fails. A compiler/linker map and stack high-water/canary plus adverse interrupt testing must account for every byte; the 246-byte remainder is not a measured safety margin.

A provisional 32-KiB flash allocation is 2 KiB framing/UART, 8 KiB endpoint state/validation, 4 KiB platform clock/NVM/interlocks, 8 KiB installed primitives, 2 KiB manifest/tables, 2 KiB bootloader reservation and 6 KiB unallocated. These are design ceilings only. Exact bootloader reservation depends on the board. No on-device JSON or generic SHA implementation is needed for this protected-link profile; adding authenticated transport requires a new measured code/RAM budget.

The boot journal, stable incarnation and calibration state require separately budgeted qualified NVM with platform-specific wear/endurance and recovery evidence. No minimum two-slot layout is declared sufficient; slot count, commit mechanism and storage bytes depend on the required write lifetime and brownout guarantees. Volatile receipts do not become durable merely because the boot epoch is durable.

An RTOS implementation may use these same wire limits but must serialize state transitions, bound ISR/queue work, assign the local supervision path sufficient scheduling service, and avoid sharing the parser's mutable READY buffer across tasks. Copy into the one admitted slot only after validation; no queue of borrowed parser pointers. Target-specific task stacks and middleware buffers are additional to the AVR allocation. Larger capacities require an explicit profile revision and separate exhaustion tests, not merely a larger heap.

## Status codes, fixtures and acceptance gates

Status codes: 0 OK, 1 UNSUPPORTED, 2 BAD_LENGTH, 3 RESERVED_FIELD, 4 BAD_STATE, 5 BOOT_MISMATCH, 6 CONTEXT_MISMATCH, 7 BUSY, 8 OLD_OR_FORGOTTEN, 9 CONFLICT, 10 UNKNOWN_PRIMITIVE, 11 BAD_ARGUMENT, 12 RESOURCE_MISMATCH, 13 STALE_FENCE, 14 BAD_TIME, 15 START_EXPIRED, 16 LEASE_INVALID, 17 UNCOMMISSIONED_OR_EVIDENCE_UNSUPPORTED, 18 BOOT_UNQUALIFIED, 19 COUNTER_EXHAUSTED, 20 NOT_SEEN, 21 CLOCK_UNQUALIFIED, 22 RECONCILIATION_REQUIRED. Reserved values fail closed. Validate syntactic lengths/reserved fields/positive identity fields before replay lookup; an all-zero call number is BAD_ARGUMENT. Where multiple independent admission guards fail, any applicable refusal code is permitted; vectors list alternatives where needed, while nonmutation remains mandatory. A malformed request that cannot identify a valid opcode gets only a bounded local diagnostic, not a fabricated correlated response.

[Vectors](../protocol/endpoint/vectors.json) pin byte layouts and proposed state outcomes. Their serial frames are encoded with the existing original framing codec. The JSON's original layout checks are distinct from the later [executor and integration verification](../protocol/endpoint/README.md); a vector declaration alone is not an executed assertion. Synthetic manifest/context values are fixture identities, not commissioned firmware hashes. The abstract fixture primitives are independent of the host demo's three scenarios.

Before platform support/conformance claims, require independent review of these layouts/state rules; exact-length/overflow/fence/duplicate/eviction vectors; reset at each acceptance/first-effect/result boundary; counter exhaustion and NVM torn-write/rollback/brownout tests; clock wrap-extension/stall tests; UART error/overflow/trickle/saturation integration; queue/receipt exhaustion; revocation and cancellation races; and pinned AVR/RTOS build/stack results. Physical commissioning additionally needs measured local bounds, feedback, native-queue fencing and independent stop/loss behavior. A successful encoder, native state-machine simulation or AVR cross-build cannot substitute for those physical gates.
