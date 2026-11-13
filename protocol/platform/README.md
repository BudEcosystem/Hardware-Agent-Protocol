# Original platform primitives — experimental

The portable endpoint still needs qualified boot storage, clocks, transport
drivers and independent protection on a real device. The code here implements
bounded software building blocks. It neither commissions a platform nor grants
physical verification. The [platform source review](../../docs/clock-boot-platform.md)
separates hardware/SDK findings from implementation assumptions.

## Finite boot-epoch reservations

[boot_epoch.c](boot_epoch.c) and [its interface](boot_epoch.h) reserve a new
positive epoch before a firmware boot can advertise ordinary execution
eligibility. The bank belongs to the same immutable enrolled incarnation as
the endpoint. One cell is consumed for each successful or partially written
reservation. It is never rewritten, erased, recycled or wrapped by this module.

The factory-provisioned header is exactly 32 bytes: ASCII `HMSBOOT1`, the 16
incarnation bytes, a big-endian 16-bit cell count, then six zero reserved bytes.
An erased, mismatched or malformed header is refused. `hms_boot_header_byte`
describes this layout; it does not write or provision storage.

Every byte other than `0xff` is consumed. A full scan requires one consumed
prefix followed by an erased suffix. An erased hole before another consumed
cell is refused. The allocator programs the first erased cell to zero, awaits
the installed callback's durable-completion result and reads back zero before
publishing `cell_index + 1`. No positive epoch escapes a failed attempt.

| Reset/failure interval | Retained bank under the stated model | Next boot |
|---|---|---|
| Before the reservation byte changes | Same erased candidate | May reserve that never-published epoch |
| Interrupted write leaves any non-`0xff` value | Candidate consumed | Skips that epoch |
| Completion/readback succeeded, before publication | Candidate consumed | Skips that epoch |
| After a positive epoch was published | Completed candidate remains consumed | Reserves a strictly greater epoch |
| No erased cells remain | Full bank | Refuses; never wraps or erases |

A one-shot RAM latch records the attempt before calling storage functions.
Calling again in the same boot returns the same success or failure; it cannot
consume a fresh epoch to disguise an unresolved error. `hms_boot_init` is only
for the serialized startup boundary, before ordinary endpoint activity. It is
not a public model command, recovery shortcut or live identity reset.

## What the storage contract assumes

The proof requires exclusive access and immutable configuration. A successful
read must return the durable stored byte. A successful
`program_zero_and_sync` must mean durable completion, including the controller,
bus and any cache. Interrupted programming may leave any of the 256 byte
values in its selected previously erased cell. The header and all previously
completed cells must remain stable. Callbacks must be bounded and must not
reenter or allow concurrent storage writers.

Those are platform obligations. The module does not establish sufficient
voltage, reset supervision, correct CPU execution during brownout, persistence
after removal of power, or containment of a torn write to one byte. In
particular, the ATmega datasheet's combined erase/write mode does not establish
power-fail atomicity. A page-programmed flash device cannot be treated as this
byte-store callback without qualifying its actual page and power-failure model.

If the highest completed byte is erased or an old bank image is restored, the
allocator can reuse a previously issued epoch. That state is indistinguishable
from a reservation that never occurred. The tests deliberately reproduce this
counterexample. CRCs and readback would not prove immunity to arbitrary rollback,
cloning or corruption. The incarnation/header must not be copied to another
device or reused after erasing the bank.

Capacity is finite: a 1,024-byte region with this header has 992 reservations.
This is an allocation calculation, not a qualified lifetime or endurance result.
Exhaustion requires an explicit enrollment transition to a new incarnation or a
different qualified boot-storage profile. Automatic in-place recycling is not
implemented. Other persistent counters, trusted gateway reset barriers and
larger stores need separately reviewed profiles.

The allocator does not clear reset reconciliation or establish that a previous
physical effect stopped. Platform startup must still keep ordinary outputs
inhibited, qualify its clock/transport, and reconcile residual motion or other
uncertain state before granting execution eligibility.

## Boundaries and measured build scope

There is no heap, recursion or variable-length array. A successful call makes
at most `capacity + 33` byte reads, one program-and-sync call, and 32 immutable
incarnation-byte reads. This is a call-count bound; the platform must supply
actual callback timing and startup/watchdog behavior. A blocking write wait
must not invalidate the timer assumptions used later for endpoint deadlines.

The native tests use an original in-memory byte store, with exact interruption
points and independently injected torn byte values. They do not run EEPROM,
an MCU emulator or acquired SDK/controller code:

```sh
python3 scripts/check_boot_epoch.py
```

The [retained receipt](../../artifacts/verification/boot-epoch.json) records 11
cases in both plain and ASan/UBSan builds, 311,973 assertions per build, 1,792
torn-byte cases, 84 read/write interruption boundaries, all 256 eight-cell
prefix patterns, read failures, maximum capacity and explicit rollback limits.
The endpoint reset test uses matching bank/endpoint incarnation bytes and
demonstrates refusal of the old boot domain.

[Independent probes](../../artifacts/verification/boot-epoch-review/review.json)
add a literal header-layout oracle, null configurations, every non-success byte
return value, reentry latching, 256 last-cell tears and exact maximum addresses.
They exercise the same explicit fault model, not electrical power failure.

The original module also cross-compiles for ATmega328P with archive-verified
compiler tools and headers. Its object contains 910 bytes of function text and
eight bytes of read-only constants. The AVR reservation struct is 12 bytes;
storage configuration is 14 bytes. Compiler-reported per-function stack usage
is at most 19 bytes, excluding called functions, storage callbacks, interrupts
and the application's complete call graph. These are object/ABI observations,
not a linked firmware footprint or target execution result. The earlier
endpoint AVR receipt remains a distinct build; its SRAM arithmetic has not
silently absorbed this module or a real EEPROM driver.

## ATmega328P EEPROM register adapter

[avr_eeprom.c](avr_eeprom.c) and [its interface](avr_eeprom.h) implement original
register callbacks for the finite bank. The driver accepts addresses 0–1023,
waits for EEPROM/self-programming readiness with a finite poll budget, and
rejects an enabled EEPROM-ready interrupt. Each access saves the interrupt
state, disables interrupts, rechecks readiness, accesses the address/data
registers, then restores the saved state. Busy waiting occurs outside these
short critical sections; entering with interrupts disabled keeps them disabled.

Programming requires an erased byte. It selects write-only mode, places zero
in the data register, launches the EEMPE/EEPE sequence, waits for completion,
and reads back zero. The driver owns the mode bits and leaves write-only mode
selected. It never erases or provisions a bank. Reentry refuses without
overwriting the active call's diagnostic status. A failure after launch may
still consume the candidate; the allocator's one-shot latch prevents another
reservation attempt in the same boot.

The budget counts register-readiness checks, including masked rechecks; it is
not a microsecond deadline. An idle read requires two checks and an idle write
four. The driver does not feed a watchdog. A platform context must wrap the
driver together with the immutable incarnation provider because the allocator
passes one shared user pointer to all callbacks; the original probe shows this
composition.

```sh
python3 scripts/check_avr_eeprom.py
```

The [retained register-model/build receipt](../../artifacts/verification/avr-eeprom/review.json)
records 12 cases and 25,948 assertions in each of plain and ASan/UBSan builds,
including all 1,024 addresses, all 255 non-erased values, readiness races,
interrupt restoration, reentry, bounded polls and allocator integration.
The actual AVR disassembly contains adjacent `sbi 0x1f,2` and `sbi 0x1f,1`
instructions under the saved interrupt mask. Three deliberately altered
instruction sequences are rejected by the bounded sequence checker. That checker
does not prove all register dataflow: the actual write-only mode value and saved
SREG restoration also require the retained manual disassembly review.

The [independent review](../../artifacts/verification/avr-eeprom-review/review.json)
passes five additional sanitizer probe groups with 20,033 assertions, covering
all 256 simulated SREG snapshots, 360 write-budget scenarios, every nonzero
readback value, post-launch ownership conflicts and the allocator's failure
latch. Manual review confirms the current compiled mode/data and saved-register
sequence. Disassembly-text mutations demonstrate the automated checker's
dataflow limits; they do not change the retained ELF or establish a source bug.

The driver object has 604 bytes of function text and a four-byte state object.
The separate boot-plus-driver probe links to 1,902 flash bytes and 53 static
SRAM bytes. Its per-function stack records are retained; they are not a whole
call-chain/interrupt bound. This image is separate from the endpoint build and
has never run on an MCU or emulator. Completion polling and readback do not
qualify supply/reset behavior, retention, completed-cell stability or
target-byte failure containment. Those physical obligations still control
whether the allocator may be used to grant a qualified boot domain.

## Error-aware AVR receive boundary

[avr_uart.c](avr_uart.c) and [avr_uart.h](avr_uart.h) implement an original,
receive-only USART0 boundary for ATmega328P. The caller owns exclusive peripheral
configuration, its RX interrupt vector and a qualified service budget. The
module reads status before data so FE/DOR/UPE remain associated with the byte.
A hardware error, full 16-cell ring or reported discontinuity closes a sticky
loss gate, discards queued data and drains subsequent incoming bytes. Foreground
acknowledgment resets frame assembly before atomically reopening the gate.

Each foreground step consumes at most one byte. Parser/CRC work runs with the
caller's prior interrupt state restored; a second masked loss check suppresses
a frame completed while continuity was lost. A clean frame is linearized at
that check. A later loss does not revoke the already-complete frame. Every
critical section restores saved SREG. Transport reset never resets endpoint
identity, context, counters, receipts or uncertain effects.

The [producer receipt](../../artifacts/verification/avr-uart/review.json) retains
12 host cases and 435,502 assertions in each plain/sanitized build, including
fault/byte combinations, ring layouts and injected interleavings. The separate
[review](../../artifacts/verification/avr-uart-review/README.md) passes 13,418
checks per build, inspects saved-status and instruction flow, and rejects five
deliberate regressions. These are original host register models and static AVR
inspection; neither runs silicon or an emulator.

The isolated AVR probe uses 1,142 bytes flash and 267 bytes static SRAM (including
the 41-byte queue, 219-byte parser and four-byte event). Driver function text is
548 bytes. Selected instruction-count bounds exclude callees and the ISR wrapper;
they are not cycle or interrupt-latency measurements. This probe is separate from
the earlier endpoint and EEPROM builds. Their totals must not be added and called
a linked, qualified firmware image. TX, baud/configuration setup, overflow-aware
clock integration, actual ISR nesting, electrical behavior and physical stop
remain unimplemented or unqualified platform work.
