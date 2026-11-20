# Isolated standing endpoint controller candidate

Status: source prepared for parent review; **not built or executed**. This packet changes no public source and does not modify either sealed input packet. No device, port, target ELF or emulator was accessed. The local controller, synthetic driver and controls are original candidate source; host durable deployment/PAT/learning integration remains required.

The candidate extends the actual common C endpoint handle/poll, rather than replaying finite OP/ARM. It keeps one standing deployment or one finite record, exact immutable OPEN identity, shared context/fence floors, two locally acquired inputs, bounded hysteresis/dwell/feedback, an explicit renewable lease, two retained activation records, durable-host ACK semantics, suspended evidence collection before renewed preparation, terminal stop/retirement and a dedicated loss witness. Direct finite APIs and the serial link share the same exclusion gate.

| Review input | Purpose |
| --- | --- |
| [PLAN.md](PLAN.md) | Scope, retained target budgets and required controlled checks |
| [WIRE.md](WIRE.md) | Complete version2 requests, response pages, controller configuration, records and lifecycle |
| [wire-vectors.json](wire-vectors.json) | Independently authored literal OPEN/START/190-byte reply and page vectors |
| [standing.h](project/protocol/endpoint/standing.h) and [standing.c](project/protocol/endpoint/standing.c) | Exact128-byte state,256-byte arena, lifecycle/codec/kernel implementation |
| [endpoint.c](project/protocol/endpoint/endpoint.c) and [link.c](project/protocol/endpoint/link.c) | Common finite/standing authority, sibling poll services and bounded stop lane |
| [standing_fixture.c](project/tests/standing_fixture.c) | Concrete64-byte synthetic finite/standing driver with actual-boundary gates |
| [standing_controls.c](project/tests/standing_controls.c) | Twelve native scenarios, including independent vectors, full ledger/resume, finite interoperation, fault ordering, acquisition boundaries and interrupted-feedback ACK gates |
| [standing_target.c](project/tests/standing_target.c) | Complete original ATmega328P clock/boot/EEPROM/RX/TX/ISR composition plus controller, compile/link only |
| [source-pins.json](source-pins.json) and `originals/` | Exact required original source copies and retained runner input |
| [REVIEW.md](REVIEW.md) | Contract refinements, source review gates and limits |
| [run_checks.py](run_checks.py) | Bounded attempted-check orchestration; separate parent review required before invocation |

No standing compiler/layout/stack/flash result exists yet. The target retains the original16MHz ATmega328P,2048 SRAM bytes,32256-byte application flash ceiling,256-byte primitive allowance,64-byte protection reservation and512-byte stack reservation with64 ISR and128 future-callback allowances. Candidate standing state/glue must fit128+32 additional static bytes. A source assertion or native `sizeof` is not target fit. Any actual resource failure is an unsupported-target result, not permission to increase the MCU or remove reservations.

The supplied driver reports only SIMULATION and has no output queue. The endpoint can express a physical evidence mode only for separately installed and qualified drivers; this fixture cannot satisfy it. In particular there is no physical independent stop, acquired vendor implementation, Arduino sketch wrapper or qualified ADC/GPIO/PWM path. Input acquisition itself is treated as potentially effectful: authority, shared resources, source epochs, clock and cutoff are rechecked before the synthetic acquisition sequence advances.

The native scenarios are proposed controls, not passing evidence. The original finite and AVR register controls are retained to run with the new extension linked. The runner must preserve a failed first build as carefully as a passing attempt. Future result receipts will identify exact frozen inputs; this source packet should not be described as an implemented end-to-end prompted application until durable host, PAT selection/qualification and provider integration also exist.
