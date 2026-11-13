# Clock and boot qualification for constrained endpoints

This is a primary-source review and proposed platform contract, not a commissioned
MCU binding. The portable executor still receives boot, clock and commissioning
qualification from trusted platform input. The native compact binding uses an
explicit same-host `CLOCK_MONOTONIC` rate assumption. Neither its process tests
nor the AVR cross-link establishes EEPROM durability, oscillator accuracy, UART
service latency or a physical stop. See the [existing endpoint
contract](../protocol/endpoint/endpoint.h), [host clock
profile](compact-host-binding.md#clock-and-observation-meaning), and [AVR
evidence](../research/constrained/avr/notes/target-build-and-uart-review.md).

The new [finite boot reservation primitive](../protocol/platform/README.md)
is useful executable progress under its stated storage model. It does not yet
supply an ATmega EEPROM driver or an RP2040 flash driver. This review does not
authorize setting `BOOT_QUALIFIED` on a physical installation.

## Sources and exact scope

Checked official sources on 2026-11-06. Local raw documents, source files,
extracted text, selected page images and hashes are under
[clock-boot-platform](../research/constrained/clock-boot-platform/README.md).
The [reading receipt](../research/constrained/clock-boot-platform/reading.json)
distinguishes full files from selected datasheet ranges. Run its original
offline verifier with:

```sh
python3 research/constrained/clock-boot-platform/verify.py
```

The AVR baseline is the non-automotive family manual **DS40002061B,
September 2020**, plus the current family **DS80000855C, April 2024** errata.
The full 19-page errata and full 5-page AVR101 note were read, including the
errata package drawings and all four AVR101 figures. The large family manual
was read only in the recorded EEPROM, reset/watchdog, timer-access, USART,
fuse, electrical and revision ranges. AVR101 is **2526A–AVR–09/02**; its newer
application-note landing-page date is not a new algorithm revision. The
automotive manual, every silicon family variant and packaging qualification
are outside this profile. Sources: [family
manual](https://ww1.microchip.com/downloads/en/DeviceDoc/ATmega48A-PA-88A-PA-168A-PA-328-P-DS-DS40002061B.pdf),
[current family
errata](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/Errata/ATmega48APA88APA168APA328P-SiliConErrataClarif-DS80000855.pdf),
[AVR101](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ApplicationNotes/ApplicationNotes/doc2526.pdf).

The modern baseline is RP2040, not RP2350: official datasheet build
**2025-02-20 / 3184e62-clean** and Pico SDK **2.3.1**, published
2026-09-04, commit `079c6f39023649b154152db30f1d781e884879bc`.
Six original SDK files (`hardware_timer`, `hardware_watchdog`,
`hardware_flash`, each C file and public header) were read fully, including
their RP2350 conditional branches. Their included dependencies, boot ROM
implementation, RTOS integration and the rest of the SDK were not fully read.
The datasheet has selected reset, flash, timer and UART coverage plus the
entire errata appendix; it is not a full 642-page read. No downloaded source
or target binary was executed. Sources: [RP2040
manual](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf),
[SDK release](https://github.com/raspberrypi/pico-sdk/releases/tag/2.3.1),
[pinned source](https://github.com/raspberrypi/pico-sdk/tree/079c6f39023649b154152db30f1d781e884879bc/src/rp2_common).

## What AVR storage actually promises

DS40002061B §§8.4–8.6 specifies byte-addressable EEPROM and at least
100,000 write/erase cycles. §4 gives a *projected failure rate*, not an
absolute no-bit-error guarantee, for retention over temperature and time.
Neither rating proves that a completed boot marker cannot revert or that
an interrupted operation affects only its addressed byte.

The low-voltage warning names two causes: insufficient voltage for a write,
and incorrect CPU execution below its operating voltage. The latter can
invalidate an assumed address or control flow. §8.4.2 recommends holding
RESET active during insufficient supply, using BOD or an appropriate external
supervisor. A reset during a write completes that write **only if supply
voltage remains sufficient**. The EEPROM mode table's combined erase/write
operation is not a promise of power-cut atomicity.

A real callback must wait for EEPE to clear, coordinate any SPM programming,
set the exact address/data/mode, and meet the four-cycle EEMPE-to-EEPE
sequence. Interrupts must not replace EEAR/EEDR or interrupt that sequence.
EEPE clears after the write access completes; reads are unavailable while it
is busy. Readback therefore follows completion, not merely launch. Polling
needs a qualified finite bound and an error result; the typical millisecond
programming time is not a worst-case proof. These obligations come directly
from [§8.6 of the manual](https://ww1.microchip.com/downloads/en/DeviceDoc/ATmega48A-PA-88A-PA-168A-PA-328-P-DS-DS40002061B.pdf).

BOD selection must use the actual supply/clock/temperature envelope and
threshold tolerance. A nominal fuse label does not establish that the CPU
and EEPROM stay valid throughout a falling supply. Tables 29-11/29-12 also
have applicability notes; the former calls its values guidelines. BOD has a
minimum detectable pulse duration. The supervisor, hold-up energy, startup
delay, fuses and brownout waveform remain board-specific evidence. Programmer
erase is another boundary: §28.7.3 erases EEPROM unless EESAVE is programmed.
A firmware update or restored EEPROM image must not silently restore an old
incarnation's reservation bank.

AVR101 spreads parameter writes over cyclic parameter/status buffers and
requires initialized status storage. Its write flow stores a parameter and
then status. That is useful wear-leveling context, but it is not a proof of
never-reused boot identities after arbitrary interruption, corruption or
rollback. HMS should not transplant it as such.

## Finite reservation invariant and failure model

The original byte-bank design can establish unique *published* epochs if all
of these conditions hold for the enrolled incarnation:

1. One owner uses immutable region bounds and exact provisioned header and
   incarnation. No ISR, bootloader, debugger, update, second core or other
   writer changes the bank. Header/configuration and consumed bytes remain
   stable; reads return durable bytes or explicitly fail.
2. A reservation writes only the first erased byte. Interrupted writes may
   leave any value in that byte. Every non-erased byte consumes a position;
   an erased hole before a later consumed byte is refused.
3. No identity is exposed and no ordinary endpoint effect is enabled until
   programming has durably completed and readback equals the committed
   marker. A failed attempt stays inhibited for that boot. Reentry cannot
   allocate a second identity.
4. No cell is erased, reused or recycled; capacity exhaustion is terminal.
   Recommissioning requires a new enrolled incarnation or a separately
   qualified migration protocol, including revocation of the old authority.

These are assumptions of the proof, not consequences of CRC or tests. A
cut before publication can leave an erased byte that is reserved again,
because its earlier identity was never published. A torn non-erased byte
is skipped even if the earlier boot never became usable. A cut after durable
commit but before publication wastes a position. Under the model, a published
position remains consumed forever.

The decisive out-of-model counterexample is a previously published *last*
marker reverting to erased: the bank becomes indistinguishable from a bank
that never used that position. CRC, a second read or detecting interior holes
does not solve that ambiguity. Whole-bank rollback, cloned header/incarnation,
wrong-address writes and arbitrary corruption require additional trusted
platform protection or explicit loss of continuity. Do not repair them by
choosing an apparent maximum, formatting, or retrying a mutation.

With a dedicated 1024-byte ATmega328P EEPROM and 32-byte header, 992 byte
positions are an arithmetic capacity, not a qualified service lifetime.
Repeated reset storms consume this finite resource. No wear-leveling is
needed for cells written only once, but retention and corruption assumptions
remain. Prefer this small, testable model over adding recycling before a
trusted migration protocol exists.

## Clock contract and rollover

`sample_clock` should adapt an independently qualified platform snapshot,
with boot identity, monotonic tick, clock validity and current inhibition
sampled coherently. An original implementation can expose a bounded function
of this shape internally, then adapt it to `hms_ep_config.sample_clock`:

```c
/* Proposed platform seam; not an installed peripheral driver. */
struct platform_snapshot {
    uint64_t boot_epoch;
    uint64_t tick_ms;
    uint32_t clock_generation;
    uint16_t qualification_flags;
};
uint8_t platform_snapshot_read(struct platform_snapshot *out);
```

The installation owns startup, timer registers, interrupt masks and sleep/debug
policy. A changed rate/source, unaccounted sleep, timer reset, missed service
bound, regression, sentinel or overflow removes clock qualification and
inhibits ordinary work. A changed generation is not permission to retime an
existing operation. Snapshot failure must not fabricate a new timestamp;
recovery queries retain uncertainty and claims. The executor's fresh samples
after predicates and driver steps remain necessary, and the driver enforces
the immutable cutoffs at the actual I/O or downstream queue boundary.

On AVR, §16.3 requires low-then-high reads of timer registers; a shared TEMP
register can be corrupted by ISR access to another 16-bit register. Save and
restore interrupt state around the coherent snapshot. A software high word
must be combined with the pending-overflow flag under a documented ordering
and service bound. TOV1 is one pending flag, not a count of arbitrarily many
missed overflows. At a *chosen* 16 MHz and divide-by-64 normal-mode Timer1,
the wrap interval is 262.144 ms. Arduino Timer0 at those settings wraps in
1.024 ms, so masking interrupts for an entire EEPROM busy wait can lose
multiple wraps. These are arithmetic examples, not a selected hardware profile.
Reserve storage before clock qualification where practical, keep critical
sections bounded, and test both sides of every rollover race. A low counter
plus one overflow flag cannot itself detect every violation of the service
bound; an independent monitor or a proven platform scheduling bound is needed.

ATmega328/P rev A/B's 32 kHz oscillator has no workaround for its stated
inaccuracy; rev D is not marked affected. Current errata also changes several
ATmega328P oscillator reset-startup additions from 14 to 19 clock cycles.
Pin silicon revision, oscillator, prescaler and fuses before qualifying time.
[DS80000855C](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/Errata/ATmega48APA88APA168APA328P-SiliConErrataClarif-DS80000855.pdf)

RP2040 provides a hardware 64-bit microsecond counter, but its tick derives
from the watchdog divider and reference clock. Timer pause, debug pause,
clock changes and software writes can invalidate elapsed-time assumptions.
The low-then-high latching read is unsafe across competing cores/interrupts;
the pinned SDK instead reads raw high/low/high and retries on a high-word
change. Low-word alarms wrap at about 72 minutes. HMS needs full-width time
and explicit rate/drift bounds, not a raw 32-bit alarm value as an epoch.
[Manual §4.6](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf),
[pinned timer implementation](https://github.com/raspberrypi/pico-sdk/blob/079c6f39023649b154152db30f1d781e884879bc/src/rp2_common/hardware_timer/timer.c)

A remote MCU oscillator cannot inherit the native host's rate assumption.
Future host mapping needs bounded rate error and interval growth with witness
age, in addition to message-bracketing uncertainty. Use the upper offset bound
for not-before, the lower bound for exclusive cutoffs, and refuse collapsed
windows. An acquisition timestamp must stay attached to its original sample;
repeated queries do not make it younger.

## RP2040 persistence and service boundaries

The RP2040 baseline uses external QSPI flash. SDK programming operates in
256-byte pages, erasure in 4096-byte sectors; XIP is unavailable during the
underlying operation. Interrupt vectors/handlers and another core must not
fetch flash then. Source/data needed in the critical path must remain
accessible. The source also saves/restores XIP configuration and flushes
cache. These mechanisms address execution/coherence, not electrical
transaction durability. [Pinned flash
header](https://github.com/raspberrypi/pico-sdk/blob/079c6f39023649b154152db30f1d781e884879bc/src/rp2_common/hardware_flash/include/hardware/flash.h),
[implementation](https://github.com/raspberrypi/pico-sdk/blob/079c6f39023649b154152db30f1d781e884879bc/src/rp2_common/hardware_flash/flash.c)

Do not emulate the byte-bank callback by repeatedly programming a flash page
without a named flash part's programming, interruption, repeat-program and
retention guarantees. The failure unit may be a page or sector. An original
page-per-reservation profile is a possible later design, still requiring
evidence for failure containment and completed-page stability. No external
flash part or endurance rating is qualified here. RP2040 BOD monitors core
DVDD, with activation/programming delays; it does not by itself establish the
external flash supply's write margin. See [manual §§2.6, 2.8.3.1.3 and
2.12](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf).

Watchdog scratch registers survive soft reset only and are cleared by RUN or
digital-supply reset. They are diagnostic storage, not persistent boot
freshness. Erratum E1 halves watchdog count duration; the SDK compensates by
doubling the load. Timer and watchdog share a reference, so the watchdog is
not evidence of an independent elapsed-time source. Reset reason flags on
either MCU do not prove that an earlier operation had no effect.

## UART, cancellation and independent stop

Expose bounded RX events carrying byte **and** error/overflow state; never
silently omit bad/lost bytes. On AVR, UCSRnA must be read before UDRn to keep
FE/DOR/UPE aligned with the buffered data. DOR denotes one or more lost
frames. On RP2040, preserve UARTDR's FE/PE/BE bits and handle OE as a loss
event; OE is not simply the error of that one character. Software-ring
overflow, DMA loss and link replacement also reset frame assembly. Preserve
the executor's operation, call floor, fences and receipt. A UART idle/receive
timeout is distinct from the protocol's absolute frame deadline; trickle
traffic must not renew the latter. [AVR §20.7.4](https://ww1.microchip.com/downloads/en/DeviceDoc/ATmega48A-PA-88A-PA-168A-PA-328-P-DS-DS40002061B.pdf),
[RP2040 §§4.2.3.2, 4.2.6, UARTDR/UARTRSR](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf)

Set a per-pass RX/TX and callback work budget so flooding cannot starve local
loss handling. Neither a watchdog reset nor clearing a UART FIFO cancels an
accepted physical effect. Watchdog reset targets and output reset states
must be reviewed with the actual driver, actuator and energy sources.
RP2040 DMA erratum E13 additionally means ABORT clearing is not itself proof
all in-flight transfers have finished; follow the documented BUSY/IRQ sequence
if a future driver uses DMA. CANCEL/REVOKE are ordinary protocol paths.
Independent stop needs a separately commissioned path and feedback; no
software acknowledgement or terminal receipt alone establishes physical rest.

## Next implementation and qualification gates

Keep the byte-bank core generic and test the abstract proof first: every torn
byte value, every cut before/after write/completion/readback/publication,
reads failing at each position, malformed header, region overflow, holes,
exhaustion, repeated calls and callback reentry. Include the last-marker
rollback counterexample with an explicit *outside-model* expected result.
Tests must not turn that demonstration into a claimed detected failure.

Then add an original AVR adapter only after its storage and power assumptions
are reviewed: exact chip/revision, board/supervisor, fuses, voltage-frequency
envelope, bounded completion policy, interrupt/SPM exclusion, durable readback,
factory header provisioning and firmware-update continuity. Preserve the
endpoint's `RECONCILE` inhibition after ambiguous reset even when a fresh boot
epoch has been reserved. New identity fences stale commands; it does not
reconstruct prior effects or release old host claims.

Host register models can test clock rollover races, error-event propagation,
bounded service and refusal rules. Cross-linking can establish code size and
compiler stack evidence for the chosen adapter. Actual power cuts across
write phases, brownouts, voltage/temperature corners, oscillator drift,
interrupt load, stack high-water and measured actuator stop remain separate
hardware qualification work. All physical bindings remain uncommissioned.
