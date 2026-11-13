# Fixed-storage endpoint executor

This directory contains an original portable C executor and serial adapter for the [compact endpoint profile](../../spec/11-endpoint-wire.md). HELLO, BIND, ARM, REVOKE, OP, QUERY, CANCEL and RETIRE are implemented with one retained operation/receipt slot, eight local resource positions and fixed buffers. The native synthetic driver exercises these paths; no physical endpoint, qualified NVM/clock implementation or independent stop is commissioned.

The maximum OP is `88 + 8*4 + 72 = 192` payload bytes. Host replay identity, endpoint boot/control/context/call identity, resource fences and serial correlation remain separate. Exact retained OP bytes identify a duplicate; changed bytes conflict even with the same supplied digest. RETIRE requires terminal, undisputed local quiescence and preserves call/fence floors. Those floors and receipts are volatile: qualified new boot identity and reconciliation are mandatory after history loss.

## C integration

[`endpoint.h`](endpoint.h) exposes caller-owned storage and immutable configuration. `hms_endpoint_init` receives an already qualified boot epoch, clock tick and platform flags. The library generates no entropy and implements no EEPROM journal. An untrusted caller's qualification bit is not evidence. Reinitializing with the same epoch while clearing history violates the platform contract.

`hms_endpoint_handle` consumes one complete, FCS-validated request and writes at most 192 response bytes. It validates all fields, predicates, timing and fences before taking the slot and all local claims; it performs no ordinary primitive step. `hms_endpoint_poll` services at most one bounded installed callback. One owner serializes every API call; there is no internal interrupt/thread lock or allocator.

The five configuration callbacks read immutable identity/digest bytes, describe/validate a primitive's exact argument/result layout, check current predicates, sample qualified clock/platform state, and perform an installed step. Nonzero primitive IDs are extensible. The original core test fixture remains separate; the new `scenario_fixture.c` implements the three installed synthetic host scenarios. Callbacks must be bounded, nonblocking and nonreentrant. Ordinary API reentry from callbacks is refused, but arbitrary native callback code is not sandboxed. Configuration/user storage outlives the executor; callbacks must not reset or mutate it concurrently.

The clock callback is mandatory. It is sampled after admission predicates before QUEUED commit, after predicates before dispatch, and after every driver step. Steps receive immutable exclusive latest-start and ordinary-work cutoffs and must enforce them at actual I/O/native-controller queue boundaries. A callback crossing a cutoff cannot return a backdated completion: it produces UNKNOWN with the sampled cause and retains claims, ignoring same-report release bits. Clock failure latches inhibition; an unknown terminal timestamp carries reason 7. These checks do not measure physical timing or callback latency.

Installation-mode changes invalidate the live context before ordinary dispatch. Evidence mode is pinned to each admitted call. Simulator work cannot report controller/sensor evidence or VERIFIED; physical-mode work cannot report SIMULATION. Malformed reports fail closed. A terminal dispute preserves the terminal state, faults/inhibits the context and retains remaining claims; later ordinary quiescence cannot resolve or retire it. Earlier established partial quiescence is not retracted.

[`link.h`](link.h) uses the original [serial C parser](../serial/frame.h) and streams escaping from one 214-byte raw TX buffer. There is one pending response. While it is transmitting, ordinary requests are dropped before admission; valid CANCEL/REVOKE still run, with potentially dropped replies. A partial outgoing frame is never overwritten. Host recovery is query/reconciliation, not automatic mutation retry.

The default **synthetic** receive-assembly budget is 1,000 ms. Configure an installation budget with `hms_endpoint_link_set_receive_budget`; call `hms_endpoint_link_check_deadline` even without incoming bytes. Trickle traffic does not renew it. UART errors/overrun/link replacement call `hms_endpoint_link_reset_receive`, which clears framing only, preserving operations and fences. A qualified timer or explicit platform error/reset path remains necessary when the ordinary clock fails. No UART registers, peripheral driver, ISR, RTOS policy or measured stop path is supplied.

## Reproducible checks

From the repository root:

```sh
python3 -I -B scripts/check_endpoint_vectors.py
python3 scripts/check_endpoint_native.py
python3 scripts/check_endpoint_integration.py
python3 scripts/check_endpoint_avr.py --toolchain-bin /path/to/trusted/avr/bin
```

The independent vector checker uses the standard library rather than importing the framing implementation. It checks 41 frame/FCS fixtures, response layouts, two host intent mappings, manifest/context hashes, references and arithmetic. The 18 negative cases and 14 state scenarios are fixture declarations; the vector checker does not execute them. Actual implemented coverage is recorded in the native and integration receipts. The [design review](../../artifacts/verification/endpoint-independent-review.json) and archived snapshot distinguish those checks from later implementation tests.

The [native receipt](../../artifacts/verification/endpoint-native.json) pins compiled source/binary hashes, compiler flags, sanitizer output and actual test counts. Its C suite covers replay/conflict, atomic fences, retention, future cancellation, cancellation/completion races, cutoffs, slow predicates/callbacks, clock faults, mode changes, reset ambiguity, malformed evidence, disputes, exhaustion, maximum payload, 64-bit time, backpressure and receive reset/deadline behavior, plus 20,000 deterministic malformed payloads. The original [fixture driver](../../tests/endpoint_fixture.c) supplies installed callbacks. ASan/UBSan success is bounded evidence, not exhaustive proof.

The [AVR receipt](../../artifacts/verification/endpoint-avr.json) records the complete original executor/link and synthetic callback harness cross-link: sections, symbols, map, compiler stack reports and explicit budget analysis. The retained ATmega328P build uses 15,780 bytes of flash and 1,335 bytes of static SRAM, including explicit UART/platform/primitive storage reservations. Its exact synthetic call graph yields a conservative 231-byte foreground stack bound. A separate 512-byte planning reservation leaves 201 SRAM bytes; its interrupt and future-callback allowances are assumptions. The AVR binary and an MCU emulator are not executed. UART/platform storage reservations are placeholders, not working drivers; qualification remains synthetic. The earlier 1,802-byte SRAM table is a design plan, not a measured stack or target fit result. Native `sizeof`, cross-linking and compiler estimates do not measure interrupt load, timing, stack high-water, NVM persistence or physical conformance.

The independent [Python packet codec](../../hms/endpoint_wire.py) constructs immutable requests and validates correlated replies without automatic I/O/retry; its 18 packet tests cover malformed/cross-field cases. The [framed process checker](../../scripts/check_endpoint_integration.py) drives the retained C executable with that codec and an acknowledged synthetic control socket. Its [integration receipt](../../artifacts/verification/endpoint-integration.json) pins the matching native build and records 13 actual process scenarios, including lost replies, replay, cancellation races, reset ambiguity, malformed driver evidence and callback-time cutoff crossing.

The executor/link source uses no heap, VLA or recursive executor path. Future callbacks/platforms must preserve those constraints. Independent C review and host-process integration have separate receipts; the native build receipt alone does not claim their results.

## Native pipe harness

`artifacts/verification/endpoint-native-build/endpoint-pipe` uses binary stdin/stdout for normal serial frames. Defaults match the retained fixture identity/digests and boot 42. Optional `--incarnation HEX`, `--firmware HEX`, `--manifest HEX` and `--boot DECIMAL` set explicit synthetic identities. Normal mode uses process monotonic time anchored at tick 1000. OS pipe writes may block: this is a test process, not an embedded service-bound test.

Pass an inherited duplex socketpair via `--test-control-fd N` for deterministic integration. Time starts frozen at 1000. Each command is one byte followed by big-endian `u64`; its nine-byte ACK follows processing. Success echoes command/argument except counter queries. Failure is `ff` plus integer 1. No test opcode enters the production wire.

| Command | Meaning |
|---:|---|
| 1 | Set absolute tick and perform one poll; ACK echoes requested tick. A slow callback can advance sampled time further. |
| 2 | Assert a strictly higher qualified synthetic boot; reset endpoint/driver activity and time to 1000, require reconciliation, preserve external synthetic dispatch/effect counters. This is not NVM proof. |
| 3 | Replace platform flags and poll. Physical/independent-stop commissioning flags are refused. |
| 4 | Argument 0: return dispatch count. |
| 5 | Argument 0: return committed synthetic effect count. |
| 6 | Select fixture mode 0–8. |

Default behavior queues, dispatches once on an eligible poll, completes after at least 100 synthetic milliseconds, then reports quiescence on a later poll. Cancellation terminates on a poll and releases claims on a later poll. Modes: 0 normal; 1 completion wins cancellation; 2 reject cancellation; 3 withhold quiescence; 4 invalid physical evidence; 5 oversized result length; 6 never complete normally; 7 premature quiescence; 8 advance a completing callback by 20 ms. Mode 8 requires deterministic mode: start at 1150, poll at 1340, sample completion at 1360 beyond cutoff 1350; the executor reports UNKNOWN and retains claims despite the fixture's observed effect count.

The fixture primitives (`0x1234` scaled pair and `0x4242` opaque 72 bytes) exercise extension interfaces, not a motor/sensor. External counters survive the simulated reset only to expose ambiguous windows in tests; that is not durable physical execution. Deployment still needs qualified NVM/clock, measured driver/interrupt/queue bounds, local interlocks/feedback, downstream fencing, brownout/rollback testing and an independently commissioned stop/loss path. CANCEL/REVOKE acknowledgement or terminal software state does not establish physical rest.

The [durable host binding](../../docs/compact-host-binding.md) connects the separate three-scenario fixture to Runtime/CLI authority, exact command reservations, receipt recovery and acquisition-time-preserving observations. Its native and Python/CLI tests do not extend the AVR target-build claim to this new fixture.
