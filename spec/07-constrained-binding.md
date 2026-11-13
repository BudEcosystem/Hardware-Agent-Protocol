# Constrained endpoint binding — research draft

This chapter defines an experimental bounded serial frame and the requirements for an MCU execution binding above it. The frame encoder/decoders and fault fixtures exist; enrollment, authority, operation payloads, procedure bytecode, firmware and device execution do not yet exist. Passing these tests does not establish P1/P2 support. The independent HMS design does not claim PPP or official Anthropic MHS wire compatibility.

## Keep semantics while changing representation

The gateway owns full WoT descriptions, scientific metadata, the durable operation journal, user authentication and higher-level planning. The endpoint owns its installed primitives, local timers, physical limits, finite queues, current execution session and commissioned loss/stop behavior. A gateway cannot compensate for absent local observability or a blocking motor routine merely by attaching richer metadata.

A compact binding must preserve the [execution contract](02-execution.md), including binding/control generations, immutable intent, evidence and uncertain outcomes. Small numeric handles can reference a previously installed immutable context; they cannot silently replace it. Context installation acknowledges the exact firmware/capability digest, local resource map, physical limits, coordinate/scale conventions and lifetime. The gateway retains the full mapping durably. Endpoint reset or relevant reconfiguration invalidates those handles.

Use installed primitives and a validated bounded procedure representation for dynamic Arduino work. Do not stream arbitrary host memory structures, C pointers or unbounded Firmata message loops. Primitive identifiers name installed functions with declared resource ownership and bounds; pin numbers alone do not identify a microscope or its permissible motion. The [embedded code review](../docs/embedded-evidence.md) records why the inspected scheduler and motion wrappers cannot simply be relabeled as an HMS executor.

## Experimental serial frame v0.1

The first framing candidate targets a commissioned, exclusively owned, full-duplex binary-transparent serial link. Configure the entire UART/USB/host route for eight data bits, no parity, one stop bit, no software XON/XOFF processing and no newline conversion. Electrical levels, baud accuracy, USB bridge behavior and physical trust are installation facts. A network serial server is not automatically within this trusted boundary.

Use octet flags/escaping and the 16-bit FCS arithmetic described in RFC 1662, but with an independent HMS header and no PPP/LCP negotiation. The [source review](../research/constrained/serial/notes/framing-review.md) records the exact reused mechanism and differences. No bit-stuffed, half-duplex bus, shared-medium or seven-bit binding is implied.

| Offset in decoded frame | Bytes | Meaning |
|---:|---:|---|
| 0 | 2 | Magic bytes `48 4d` (`HM`) |
| 2 | 1 | Frame version `01` |
| 3 | 1 | Kind: `01` control, `02` status, `03` telemetry, `04` bounded data chunk |
| 4 | 1 | Reserved flags, exactly zero |
| 5 | 1 | Channel identifier, interpreted only by a negotiated application binding |
| 6 | 8 | Session reference, unsigned big-endian |
| 14 | 4 | Frame sequence, unsigned big-endian |
| 18 | 2 | Payload length, unsigned big-endian, 0–192 |
| 20 | 0–192 | Opaque application payload |
| 20 + payload length | 2 | Complemented FCS, least-significant octet first |

The FCS register starts at `ffff`, uses reflected polynomial `8408`, and is complemented before transmission. Checking the complete decoded frame including FCS yields `f0b8`. It covers every header and payload byte. The frame is enclosed in `7e` flags. Within flags, encode `7e` as `7d 5e` and `7d` as `7d 5d`. No other control octets are removed. A transmitter emits both flags; receivers also accept a shared boundary flag and ignore empty frames.

The maximum decoded frame is 214 bytes; the conservative encoded bound is 430 bytes including flags. There is no allocation from the length field. Receivers reject unknown versions/kinds, nonzero reserved flags, bad lengths, bad FCS, overflow and an escape immediately followed by a flag. Overflow discards until the next flag, producing one bounded error event. Noise before the first flag is ignored. A UART framing/parity/overrun error, transport replacement or absolute receive-frame deadline resets the partial parser and requires a new flag. Error events must not create an unbounded diagnostic queue.

`protocol/serial/frame.py` supplies a host encoder and incremental decoder. `frame.c`/`frame.h` supply an original portable C decoder with a fixed buffer and no allocator, I/O, clock or device callbacks. Each feed consumes one byte and returns at most one event. A C `READY` result exposes the validated raw bytes until the next feed/reset; the receiver derives the complete length from the validated two-byte payload length. Consume/copy within bounded caller storage; do not retain a mutable pointer across feeds or share one parser concurrently. A timer supplied by the endpoint must enforce an absolute assembly duration as well as any idle timeout, so a trickle of bytes cannot retain a partial command indefinitely.

The framing layer accepts zero session/sequence fields because handshake semantics are not implemented. An eventual application binding must restrict session zero to specified non-effectful negotiation, establish a nonzero session before effects, enforce sequence rules and authenticate/authorize the command. A decoded control-kind frame grants no authority. The codec intentionally demonstrates that duplicate frames can decode twice; deduplication belongs to the operation layer. CRC protects against accidental corruption, not forgery, replay or hostile peers.

## Session, call identity and recovery requirements

Keep frame sequence, endpoint session, authority generation and operation identity separate. Frame sequences are diagnostic/ordering values within their declared directional channel domain, not durable deduplication keys. No counter used for authority or identity may wrap silently. Drain/quiesce and create a qualified new domain before exhaustion; resetting a number does not reset physical obligations.

A proposed compact call reference is `(endpoint_session, call_number)`, mapped durably to the complete HMS operation key and intent. The endpoint advertises its ordering, active-call and result-retention capacities. One tiny implementation may require strictly increasing call numbers, retain an accepted high-water mark and refuse older calls after their result slots are evicted. It must not interpret a forgotten result as permission to repeat an irreversible action. Conflicting duplicates still need exact bounded-request comparison or the agreed full intent digest; a truncated checksum is insufficient. This call protocol has not been encoded or implemented yet.

On reset, enter the installed reset/loss response and inhibit new ordinary effects. A boot/session identity requires evidence of freshness: for example, a qualified persistent boot counter, a suitable authenticated fresh challenge mechanism, or a proved ordered-link reset/drain barrier while an independent actuation gate remains inhibited. Merely echoing a random host value over a replayable path is not enough. Persistent counters require torn-write, rollback and endurance analysis. A gateway restart is not proof that its MCU restarted. If a device cannot establish continuity or a fresh session, expose that limitation and require reconciliation/recommissioning before effects.

Old work in gateway queues, USB/UART buffers, native controller queues and DMA must be addressed by the chosen reset barrier. A newly printed boot banner does not establish that those paths were purged. When source/destination state after a reset is uncertain, preserve the prior operation as uncertain and inhibit conflicting follow-on work. The host journal cannot reconstruct an unobserved physical prefix merely from the program counter it last received.

## Bounded dynamic procedures

The proposed executor accepts an immutable admitted procedure with fixed instruction/data budgets. Candidate instructions are installed primitive invocation, bounded wait, timestamped sample, typed condition, finite repeat and external-evidence barrier. No arbitrary memory access, native pointer serialization, recursion, dynamic allocation or unrestricted backward jump is part of the tiny profile. More capable targets may expose separately admitted native programs.

Static verification must calculate instruction visits, maximum program/storage size, per-resource claims, maximum duration and physical totals such as travel/exposure/dispense. Integer arithmetic is checked before conversion to target widths. Units and scaled-integer conventions are declared; no implicit float-to-int truncation or AVR/host `long` reinterpretation. A symbolic loop count must have an enforced finite bound. A condition depending on external evidence cannot proceed offline with a placeholder.

The local scheduler services control/watchdog work independently of parsing and bulk data. Each primitive has a measured nonblocking step or a separately justified bounded execution time. A cooperative callback that never returns defeats a supervisory polling watchdog; use an independent mechanism appropriate to the installation. Cancellation and normal motion completion must retain their native physical meanings. A stop procedure may need to continue a deceleration trajectory, not simply stop calling the motion library.

One admitted procedure can execute many control pulses without a host round trip or durable host write per pulse. Progress records identify accepted versus actually executed prefixes and their persistence. A lost progress message produces uncertainty, not automatic replay. Parameter changes and new primitive/firmware installation have different authority and binding-generation effects.

## Resource and timing budgets

This 192-byte payload candidate is not a mandatory footprint for every chip. Smaller devices may need a separately specified reduced-capacity binding, installed peripheral bridge or P0 gateway representation. No smaller buffer configuration is implemented in the current C decoder. Every supported capacity must be explicit in negotiation and tested; a universal semantic interface does not imply identical endpoint memory requirements.

The archived UNO R3 manual identifies an ATmega328P with 2 kB SRAM and 32 kB flash. This motivates explicit budgets; it does not establish that an HMS runtime fits. The native C decoder's measured host `sizeof` is 220 bytes. A pinned AVR cross-build measures 219 bytes for the parser and 558 bytes flash/221 bytes static RAM for a minimal build-only harness plus startup; [target artifact](../artifacts/verification/serial-avr.json). Its decoded buffer is exactly 214 bytes independent of ABI, but stack, UART buffers, driver state, queues, program storage and cryptography are additional. No target execution or total endpoint firmware memory measurement has run. A bitwise FCS avoids a 512-byte RAM table; target cycle costs still need measurement, and a flash-resident lookup is another implementation option.

The [pinned Arduino AVR core review](../research/constrained/avr/notes/target-build-and-uart-review.md) finds silent receive-ring/parity drops and no propagation of framing/overrun errors through stock Serial. That interface cannot alone implement this draft's UART-error reset rule. Its blocking write/flush/read paths and Timer0 assumptions also require an explicit bounded integration; successful component linking does not qualify them. The original [AVR receive boundary](../protocol/platform/README.md) now retains status-before-data, latches continuity loss and resets frame assembly before reopening its queue. Host register tests and an isolated cross-link do not qualify baud, ISR load or hardware behavior.

At an illustrative 115200 baud with 8N1, 430 serialized bytes consume at most about 37.33 ms of wire time; at 9600 baud the same bound is about 447.92 ms. These are arithmetic bounds for this frame size and assumed baud, excluding queueing, driver scheduling, inter-byte gaps, clock error and device response. They are not measured command or stop latency. A shared serial stream cannot preempt a frame already being sent; bound normal frames/queues and retain an independent local loss/stop mechanism. Bulk camera data should use another suitable route.

Before support claims, require a complete RAM/flash/stack budget and target build; UART saturation/overflow tests; parser/driver timing under interrupt load; counter wrap and brownout tests; exact session reset barriers; fixed queue exhaustion; stop under journal/transport failure; bounded program rejection; physical feedback and measured action/stop outcomes. The [conformance plan](../docs/conformance-plan.md) remains applicable.

The present tests establish cross-language framing behavior and bounded decoded storage under malformed input. They do not test UART hardware, compiler output for an MCU, session authority, procedure execution or a motor.
