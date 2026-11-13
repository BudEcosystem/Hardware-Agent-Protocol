# Original AVR Timer1 clock primitive

Status: original software and host-model verification, with a pinned ATmega328P
cross-build. No MCU execution, oscillator qualification, elapsed-time measurement
or combined endpoint-firmware fit has been demonstrated.

[avr_clock.c](../protocol/platform/avr_clock.c) uses exclusive Timer1 normal mode
at nominal 16 MHz divided by 64, extending the 16-bit counter with a 32-bit wrap
counter. It binds samples to a supplied nonzero, nonreused boot epoch. Startup
does not qualify the clock; a trusted integration must attest source accuracy,
service continuity and bounded interrupt servicing. Faults are sticky for that
boot domain. It has no live rebase or fault-reset API.

The snapshot preserves SREG, reads the overflow flag around a coherent low/high
counter read, and compensates a pending overflow without clearing the flag or
double-counting its later ISR. Integer conversion happens after interrupt-state
restoration. A returned sample describes its capture instant; later invalidation
is still possible before return, so effect-boundary integration and independent
inhibition remain required.

The installation must account for each overflow strictly before 32,768 subsequent
raw ticks, nominally 131.072 ms. The code detects some overdue servicing, but a
single pending flag cannot reveal every missed multiple wrap. Both producer and
independent tests retain explicit alias counterexamples. Timer1 ownership also
excludes conflicting Servo, PWM, input-capture and prescaler users; these conflicts
belong in the future [I/O resource graph](io-driver-hub-control.md).

The [producer receipt](../artifacts/verification/avr-clock/review.json) records
10 groups and 8,655,746 assertions in each plain and sanitizer host run. Selected
linked-disassembly checks cover register order, saved interrupt state and finite
instruction paths; their counts are not CPU-cycle or timing bounds. The isolated
AVR probe links at 1,754 bytes of flash and 47 bytes of static SRAM, including a
22-byte clock state and 24-byte sample. These sizes are not added to a previously
tested endpoint image and called a verified combined build.

The [independent review](../artifacts/verification/avr-clock-review/README.md)
adds 131,920 timestamp-history cases, 8,192,056 conversion cases, 100,000 sequence
steps and boundary/alias probes in each plain and sanitizer build. Twelve compiled
source mutations were rejected. Its offline verifier checks exact snapshots and
receipts; it does not rerun target code or qualify the hardware assumptions.

The next integration must combine boot reservation, clock, RX/TX, endpoint state,
installed primitives and independent inhibition in an actual firmware image,
then establish interrupt/stack/memory/service and electrical behavior on the
specified board. The primitive is one component of that work.
