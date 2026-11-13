# Embedded execution evidence

The [next aggregate source proposal](../artifacts/design/standing-endpoint-aggregate-size/README.md)
targets ordered field checks and serialization across both controller paths.
Its catalogue adds 1,090 descriptor/constant bytes before helper and caller code;
the existing serializers alone cannot close the 6,930-byte application gap.
It preserves callbacks, full-width time, alias/store order and all charged services.
This is a source proposal with no new compiler result, savings forecast or fit proof.

The latest [phase-kernel candidate](../artifacts/implementation/standing-endpoint-phase-kernels/RESULTS.md)
preserves the finite/runtime and fourteen standing cases. Parent, byte-backend
and scalar-fallback controller traces match in plain and sanitizer modes:
twenty groups / 1,617 assertions / 1,177 records in each of six traces. Numeric
controls pass six groups / 86,889 assertions per backend/mode. The AVR link
fails at 39,186 flash bytes, 716 fewer than the shared-kernel parent but still
6,418 above physical flash and 6,930 above the application allowance. Static
SRAM remains 1,503 bytes. The audit verifies 58 commands/reaps and 139 frozen
inputs. Failed-map arithmetic and backend frames do not establish a valid ELF,
complete combined stack, timing or physical I/O qualification.

The preceding [shared-kernel candidate](../artifacts/implementation/standing-endpoint-shared-kernel/RESULTS.md)
preserves original finite/runtime checks and fourteen standing cases / 766
assertions. Four complete differential traces match across normal and sanitizer
builds: sixteen groups, 1,241 assertions including 475 new checks, and 829 trace
records each. Three numeric-kernel groups pass 13,014 assertions in each mode.
The AVR link still fails: 39,902 flash-load bytes, 1,908 fewer than the parent,
but 7,134 above physical flash and 7,646 above the application allowance. Static
SRAM remains 1,503 bytes. All fifty commands/reaps and 119 frozen inputs are
independently audited. No valid target ELF, complete stack bound or physical
execution is claimed.

The [phase-size source proposal](../artifacts/design/standing-endpoint-phase-size/README.md)
uses the same failed-link evidence: 151 allocated text sections, 131 generated
bodies and 676 direct call sites. Its coordinated byte-arithmetic and phase
proposal requires preservation of full uint64 values, capture/callback order,
public ABI, roots, services and reserves. No compiler or target ran in that proposal. The measured
28,076-byte finite/standing/kernel group is an ownership total, not a savings
forecast. Its then-current application gap was 7,646 bytes; the later candidate
above measures the combined refactor's result.

The preceding [copy/boundary candidate](../artifacts/implementation/standing-endpoint-copy-boundary/RESULTS-REVIEW.md)
passes fourteen standing cases / 766 assertions in normal and ASan/UBSan builds,
including high-bit, carry and near-maximum timestamp timelines. Original finite
and runtime regressions also pass. Its AVR link still fails by 9,042 bytes:
41,810 flash-load bytes, 82 fewer than the LTO parent, and 1,503 static SRAM bytes.
The generated endpoint-poll wrapper has no local frame and six saved bytes;
the finite service's frame is now separate from the standing branch. This local
observation does not prove a complete foreground/helper/callback/ISR stack bound.
No target or physical I/O ran. The [attribution packet](../artifacts/verification/standing-lto-attribution/README.md)
retains the preceding source/instruction measurements and their reading scope.

The [source proposal for the shared kernel](../artifacts/design/standing-endpoint-size-reduction/README.md)
joins complete instruction inventories for the standing poll and both handlers:
8,604 instructions / 17,982 bytes, with sixty-nine wide-arithmetic call sites.
It proposes shared private time/serialization operations and measured phase
boundaries while preserving the full time domain, callbacks, ABI and target.
Savings were unknown at that source/data review; the later build above measures
the combined change. The proposal itself contains no compiler execution result.

The [Arduino AVR I/O boundary review](../research/embedded/avr-io-boundaries/README.md)
adds six completely read source files / 1,443 LF lines from the retained official
1.8.8 archive. It traces PWM disconnection during digital reads, shared ADC/reference
effects, an unbounded conversion wait, pin-table bounds and startup conflicts with
the existing Timer1/UART owners. No acquired source is built or executed. These
findings inform the [I/O and driver boundary](../spec/12-io-driver-boundary.md);
they do not qualify a physical adapter.

The [standing endpoint proposal](../artifacts/design/standing-endpoint-programs/README.md)
now maps a narrow renewable two-input controller onto the sealed finite AVR
composition. Its field reconciliation accounts for 128 bytes of standing state,
32 bytes of additional glue/padding and the existing 256-byte primitive allowance.
The resulting 2,015-byte SRAM target includes the unchanged 512-byte stack
reservation. The [first C implementation](../artifacts/implementation/standing-endpoint-controller/RESULTS-REVIEW.md)
exceeded flash and the proposed static increment. Subsequent bounded
[object inspection](../artifacts/verification/standing-size-analysis/RESULTS-REVIEW.md)
confirmed an eight-byte descriptor copy in SRAM. The [fit candidate](../artifacts/implementation/standing-endpoint-fit/RESULTS-REVIEW.md)
removes that excess and reduces combined flash load by 582 bytes. Thirteen
standing cases / 673 assertions pass normally and under ASan/UBSan, alongside
the original finite and runtime checks. The complete AVR link still fails by
10,296 bytes: its failed map totals 43,064 flash-load and 1,503 static SRAM bytes.
The exact 160-byte static increment plus 512 reserved stack bytes gives 2,015
SRAM bytes arithmetically. There is no valid ELF or combined stack proof.
Acquisition authority, strictly post-handoff loss evidence
and interrupted-feedback retention have native controls; physical service timing
and I/O qualification remain open.

The [GCC 7.3.0 option review](../research/constrained/avr/compiler-options-review/NOTES.md)
retains two fully read manual chapters / 3,438 extracted body lines. It establishes
requirements and evidence gaps for a possible LTO profile. No LTO build or final
stack evidence is claimed from that research.

The subsequent [LTO build](../artifacts/implementation/standing-endpoint-lto/RESULTS-REVIEW.md)
compiles all twelve exact unchanged units and fails linking by 9,124 physical
flash bytes. Its failed map records 41,892 flash-load and 1,503 static SRAM bytes,
with all 29 required function roots and nine charged objects present. Compared
with the fit profile, 1,172 fewer bytes reflect LTO plus stronger explicit
retention of already-present symbols. Two attempts and 32 command reaps are
independently audited. The first attempt's plugin-query failure is preserved;
the [source-grounded lookup correction](../research/constrained/avr/plugin-lookup-review/NOTES.md)
retains its precise partial-file research scope. Fifty-four saved compiler
artifacts include 105 possible backend stack records, but there is no valid ELF,
complete final graph bound, timing qualification or target execution.

The [I/O feature follow-up](../research/embedded/io-feature-review/README.md)
adds ten completely read digital, analog/PWM and servo feature files at the same
pinned ConfigurableFirmata revision. It traces mode changes, input pull-ups,
immediate reporting, reset behavior and servo allocation. Its source findings
require validation before pin-state lookup, explicit configuration effects and
separate driver/resource lifecycle contracts. No third-party firmware is built
or adopted. The original 35-file ledger below retains its earlier scope; the
follow-up has its own exact reading and dependency coverage.

The inspected implementations support HMS's split between a host authority and a small local executor. Runtime selection of installed I/O and motion primitives is practical; that does not make an arbitrary incoming program bounded, a callback deadline enforceable, or a reported motor position a measurement. Firmata supplies useful patterns for compact commands and pin discovery. The inspected scheduler and motion wrapper require substantial validation and lifecycle work before they could implement the HMS execution contract. rclc supplies ordered callback execution and configurable input-taking semantics, with application and middleware limits still needing explicit treatment.

This is a source review at exact revisions, not a hardware validation, firmware build, security audit, or claim about all current releases. No acquired third-party code was executed or modified. Full-file reading means every LF-delimited line in the named file was displayed and read, including dependencies listed in the reading log; it does not mean that every file in a checkout was read. The machine-readable [reading log](../research/embedded/reading-log.json) gives root-relative paths, hashes, byte counts, LF coverage and exclusions. [Repository pins](../research/embedded/repositories.json) distinguish the newly acquired checkout from earlier retained checkouts.

| Source | Exact commit | Scope used here |
| --- | --- | --- |
| [Firmata protocol](https://github.com/firmata/protocol/tree/7908873e8faae33111143aa6cc236148b12118f2) | `7908873e8faae33111143aa6cc236148b12118f2` | Core protocol, scheduler and AccelStepper protocol documents, all read in full |
| [Firmata Arduino](https://github.com/firmata/arduino/tree/ebd19be71b3673ba16f884c00b0a2e940ef86157) | `ebd19be71b3673ba16f884c00b0a2e940ef86157` | StandardFirmata sketch, parser, core class and associated headers, listed in log |
| [ConfigurableFirmata](https://github.com/firmata/ConfigurableFirmata/tree/3734757348263e890d276f7e4fbc1f7e2bf5f2b9) | `3734757348263e890d276f7e4fbc1f7e2bf5f2b9` | Scheduler, motion wrapper, vendored AccelStepper/MultiStepper, dispatcher, parser and example loop, listed in log |
| [rclc](https://github.com/ros2/rclc/tree/c34f5d9121e1190e2cb188a8f19e57eead1448c1) | `c34f5d9121e1190e2cb188a8f19e57eead1448c1` | Complete executor implementation/header, handle implementation/header and sleep implementation/header |

## Compact I/O is possible, but a fixed array is not a complete bound

[StandardFirmata](../research/protocols/repos/firmata-arduino/examples/StandardFirmata/StandardFirmata.ino) has fixed pin/port arrays, eight continuous I2C query slots and a 64-byte I2C receive array. [Firmata.h](../research/protocols/repos/firmata-arduino/Firmata.h) adds a fixed parser array; [FirmataConstants.h](../research/protocols/repos/firmata-arduino/FirmataConstants.h) sets its capacity to 64 bytes. These are examples of finite MCU storage. They are not an SRAM budget: core UART/Wire buffers, Servo objects, stack, object overhead and platform ABI must also be accounted for. The core class also allocates a firmware-name vector with `malloc` during setup (`Firmata.cpp`, lines 200–234), so this sketch is not evidence of a wholly heap-free system.

The StandardFirmata loop drains available input before periodic analog/I2C work (lines 786–824). I2C handling calls Wire synchronously and can use an explicitly configured microsecond delay (lines 185–220). There is no per-turn byte/callback budget or independent command-expiry/watchdog check in this sketch. Startup can wait for Serial indefinitely (lines 775–778). Actual Wire/UART blocking bounds depend on the selected Arduino core, which this review did not inspect. A nominal 19 ms sampling interval does not establish a worst-case sample age under input flood, bus failure or output backpressure.

Argument validation is uneven. The I2C callback reads fields before consistently checking `argc`, and its I2C write loop assumes paired bytes. `readAndReportData` does not locally cap returned bytes to the 62 payload slots remaining after address/register; whether a particular Wire core prevents the larger transfer is a separate dependency. Pin getters in `Firmata.cpp` directly index arrays, and the mode callback calls a getter before establishing a pin bound. HMS must validate each opcode's exact length, indices and numeric domain before accessing arguments or changing pins, even if a trusted host normally sends valid requests.

The protocol's [pin-state query](../research/protocols/repos/firmata-protocol/protocol.md) explicitly distinguishes stored output state from pin value. StandardFirmata returns the stored state for PWM/servo outputs. An HMS adapter must classify that result as command state/echo, and obtain physical feedback separately when required.

## Parser recovery must reject the whole malformed frame

In [FirmataParser.cpp](../research/protocols/repos/firmata-arduino/FirmataParser.cpp), lines 85–95 and 380–455, individual writes are capacity checked, but `parse` ignores the overflow result and continues increasing `sysexBytesRead`. On the closing marker it still invokes message processing using that logical length. Oversized string decoding can therefore read beyond the stored payload, and generic callbacks receive a length that is not bounded by the stored bytes. The Arduino wrapper then narrows the callback count to `uint8_t`. An empty SysEx frame has no separate guard before reading the command byte and subtracting one from the count. Bounds on writes alone do not produce a fail-closed parser.

While parsing SysEx, this parser treats every byte other than the end marker as data, including a reset or another start marker. There is no inter-byte/frame timeout in the inspected parser. A truncated frame can consume later commands until an end marker arrives; a software reset byte is not an independent stop channel in that state.

The separately pinned [ConfigurableFirmata parser](../research/embedded/repos/configurable-firmata/src/ConfigurableFirmata.cpp) makes different choices: it rejects empty messages, handles reset before the parser-state branch, and discards an overfull message in the byte-at-a-time path (lines 214–343). These improvements cannot be attributed to the other Arduino pin. Its conditional `LARGE_MEM_DEVICE` receive optimization (lines 261–278) copies four-byte words directly into the destination without checking remaining destination capacity. The corresponding header declares a 4,096-byte input cache and a 252-byte message buffer for that build path. This is a source-level capacity defect in the conditional path, not a claim that it is enabled on every board.

HMS therefore needs an independently specified parser state machine: length checked before buffering, bounded decoded length, exact opcode payload validation, frame timeout, explicit discard/resynchronization, and no dispatch from a partially received or rejected frame. CRC, session validation, sequence/replay checks and authority are additional layers; Firmata's delimiters and 7-bit encoding do not supply them.

## The Firmata scheduler is message replay, not bounded procedure execution

The [scheduler protocol](../research/protocols/repos/firmata-protocol/scheduler.md) intentionally stores message streams and permits a final delay command to restart a task. The complete [implementation](../research/embedded/repos/configurable-firmata/src/FirmataScheduler.cpp) exposes several relevant limitations:

| Source location | Static finding | Consequence for HMS |
| --- | --- | --- |
| `createTask`, lines 115–130 | Allocates the caller-selected task length and dereferences the result without a null check; no aggregate task-byte quota | Bound slots and bytes before installation; allocation failure must leave prior state intact |
| `addToTask` / `schedule`, lines 154–179 | Upload and execution share `pos`; scheduling resets it without requiring the declared buffer to have been fully filled | Keep upload completeness separate from execution position; validate an immutable program before arming |
| `schedule` / `delayTask` / `report`, lines 169–190 and 233–263 | Uses signed `long` times, zero as unscheduled sentinel and direct comparisons; the due test explicitly carries an overflow TODO | Declare timer width and maximum horizon; use an audited rollover rule; test the sign boundary and wrap |
| `execute`, lines 275–291 | Replays arbitrary stored Firmata bytes until a time change or end; final delay permits repeated execution | Enforce total instruction/iteration/runtime budgets and yield points locally; a finite buffer does not bound total effects |
| `reportTask`, lines 211–230 | Serializes native struct bytes, skips a hard-coded three-byte prefix, and comments that it depends on AVR layout | Encode fixed-width fields explicitly; pointer size, padding and `int` width cannot be wire semantics |

Two further source traces need resolution before reuse. In `report`, a non-due task advances `current` without advancing `previous`; if a later task completes, the unlink logic can discard an earlier pending list segment. Also, task bytes can invoke deletion/reset of the currently executing task through the same parser; `execute` then reads the freed task's fields. These are static control-flow findings, not reproduced hardware incidents. A bounded executor should prohibit mutation of active program storage and use explicit cancellation/cleanup state.

The scheduler has no observed lease, session, expiry-at-effect or independent watchdog mechanism. Its reset frees task storage; that alone does not stop a motion primitive already started by a task. The [example loop](../research/embedded/repos/configurable-firmata/examples/ConfigurableFirmata/ConfigurableFirmata.ino) registers optional features and the [dispatcher](../research/embedded/repos/configurable-firmata/src/FirmataExt.cpp) calls their reports sequentially. Feature selection is a useful firmware customization pattern, but arbitrary feature callbacks must not bypass the HMS resource and effect envelope.

## Motion completion and stopping need separate evidence

The [motion protocol](../research/protocols/repos/firmata-protocol/accelStepperFirmata.md) advertises ten steppers and five groups, asynchronous completion messages, absolute/relative steps, and a zero command that changes the coordinate estimate without moving. The limit-switch command is explicitly unimplemented. A protocol feature ID does not establish that its implementation or feedback exists.

The vendored [AccelStepper implementation](../research/embedded/repos/configurable-firmata/src/utility/AccelStepper.cpp) increments `_currentPos` when it emits a step, and `currentPosition()` returns that variable. Its [header](../research/embedded/repos/configurable-firmata/src/utility/AccelStepper.h) explicitly identifies open-loop operation and loss of position knowledge after stall/overspeed. The [Firmata wrapper](../research/embedded/repos/configurable-firmata/src/AccelStepperFirmata.cpp) reports that count. Thus a normal completion is a controller-generated pulse-count result, not an encoder measurement or proof of physical arrival. Reset/zero/manual movement changes the meaning of inferred position and requires the HMS generation/reconciliation rules.

A concrete stop mismatch occurs at wrapper lines 216–221: it calls `stop()`, immediately clears `isRunning`, and emits move-complete. The underlying `stop()` (AccelStepper lines 636–647) only sets a new deceleration target; subsequent `run()` calls are needed to execute it. The wrapper's single-axis report loop calls `run()` only while `isRunning` is true. For an axis serviced only by this path, clearing that flag prevents the planned deceleration from being stepped. The completion is emitted immediately, before observing physical rest. The group stop similarly clears the group-running flag and reports completion; there is no feedback confirmation. Concurrent group/individual control is not excluded by this wrapper. None of these messages alone can satisfy a commissioned stop condition that requires controlled deceleration, zero measured velocity or holding force.

Additional bounds require attention: the common device guard allows indices below ten even for five-entry group arrays; several commands read operands without checking their byte counts; group member indices are unchecked; the wrapper increments membership count without observing `MultiStepper::addStepper` failure; repeated configuration can allocate replacements without releasing prior objects; group move uses a variable-length stack array. Its 32-bit step decoder masks the high portion after shifting it into high bits (`decode32BitSignedInteger`, line 352), losing those bits. A source-derived example is magnitude `2^28`, whose low four chunks are zero and fifth chunk is one: this expression decodes it as zero. No compilation or device run was used for that arithmetic trace.

Timing is cooperative: `run()` emits at most one due step per call, `runSpeed()` measures elapsed `micros()`, and pulse generation includes a short busy delay. The example services features in sequence, so communication and other callbacks affect step jitter. MultiStepper coordinates nominal constant-speed targets, without acceleration/deceleration or evidence of measured simultaneous arrival. Hard pulse deadlines should be implemented in a timer/drive path with a measured service bound, not inferred from asynchronous API shape.

## What rclc LET actually guarantees here

The complete [rclc executor](../research/protocols/repos/rclc/rclc/src/rclc/executor.c) and [header](../research/protocols/repos/rclc/rclc/include/rclc/executor.h) were read. The default scheduler checks readiness, then takes each handle's input immediately before invoking its callback. The LET variant (lines 1724–1767) checks readiness, evaluates the trigger, takes input for all handles, then invokes callbacks in registration order. The code explicitly states that output writes are not held until the end of the callback round. This prevents later callbacks in that round from taking newly published DDS input; it is not a globally simultaneous sensor snapshot, fixed physical output-release time, or cross-device clock guarantee.

Callbacks run inline in `_rclc_execute` (lines 1395–1683). A slow/blocking subscription, service or action callback delays later work. `spin_some(timeout_ns)` passes that timeout to `rcl_wait`; it is not a callback execution budget or preemption deadline. An `ALWAYS` subscription callback receives null when no data is available, subject to the executor's trigger allowing that round. A trigger requiring all handles to be ready is a readiness barrier, not a freshness or timestamp-alignment check.

Memory is bounded by configured counts but not wholly static: initialization allocates the handle array; action registration allocates goal storage; `prepare` initializes a dynamically allocated RCL wait set. Adding/removing handles invalidates the wait set and can cause later allocation. Prepare after final registration, freeze the configuration during critical execution, use bounded message storage, and audit the selected RCL/RMW transport and allocator separately. The header's action-registration tables say no allocation, while the implementation visibly calls the allocator; the pinned implementation is the stronger evidence for budgeting.

The periodic helper (lines 2007–2032) reads `rcutils_system_time_now`, calls `spin_some`, computes remaining time and sleeps in whole milliseconds through [rclc_sleep_ms](../research/protocols/repos/rclc/rclc/src/rclc/sleep.c). When late it skips sleeping and advances the nominal invocation time; there is no application deadline-fault policy in that helper. This review did not follow rcutils's platform clock implementation. Do not convert the helper's period parameter into a monotonic, hard real-time guarantee without that dependency and platform evidence.

## Implications for the HMS implementation

These findings reinforce [execution semantics](../spec/02-execution.md), particularly the separation of completion, effect verification, cancellation and stop. For the tiny profile, the firmware should expose a commissioned table of primitives, a finite command/program store, explicit session and control generation, local start/runtime expiry, fixed argument formats, and a dedicated loss-of-authority path. Upload/install/arm/run must be distinct states. Each effectful step checks the local envelope; no host round-trip is required per pulse.

The full description and durable idempotency journal can remain on the gateway. The MCU must still refuse stale-session frames, reject malformed commands without side effects, account for queued/running work, and report uncertain partial outcomes after reset. Stop/hold policy must be local and remain serviceable despite a stuck parser, ordinary callback or host. A hardware watchdog reset also needs a commissioned boot/output policy; reset is not intrinsically equivalent to stopping the attached machine.

Required next evidence is specific: compile/link size and stack margins on named targets; parser fault-injection and framing fixtures; allocation/exhaustion handling; timer boundary tests; saturated-link stop latency; stuck-bus/blocked-callback behavior; reset during upload and execution; duplicate and stale-session rejection; and a physical motion bench that compares pulse-count completion with measured position/rest. This review supplies the source rationale for those checks, not their passing results.
