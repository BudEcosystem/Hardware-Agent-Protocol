# Original ATmega328P Timer1 clock verification

This lane implements and checks an original, bounded platform component. It is
not installed firmware or a qualified physical clock. No MCU, emulator, serial
device, uploader, bootloader, acquired controller, or SDK target code executes.
`python3 scripts/check_avr_clock.py` runs the original native register probe
with plain GCC and ASan/UBSan, then cross compiles/links and inspects a separate
AVR image using the previously acquired official pinned compiler archive.

## Installation contract

The only profile is ATmega328P, nominal CPU/IO clock 16 MHz with CLKPR=0, Timer1
normal mode and /64 prescaling. One tick is nominally 4 microseconds; 250 raw
ticks are one nominal millisecond. `F_CPU=16000000UL` is a build assertion,
not oscillator evidence. The installer must establish the actual oscillator,
fuses, silicon revision, voltage/temperature/error budget and continuity.
Timer1 and its shared 16-bit TEMP latch are exclusively owned. Servo libraries,
Timer1 PWM/capture, competing vectors and other Timer1 register users conflict.
Timer0 is not used, but Timer0/1 share a prescaler: another component resetting
PSRSYNC or holding TSM violates this clock contract. The layer never writes
CLKPR, PRR, GTCCR, DDR or GPIO registers and never enables global interrupts.

Software init and the one-shot Timer1 start occur only inside a **fresh endpoint
boot and inhibition boundary**, before any work can use that clock domain.
The nonzero, nonsentinel 64-bit boot epoch must already be durable and nonreused;
this module does not allocate, persist, increment or prove the epoch. An active
endpoint cannot call init again or replace the object to clear a fault. A second
start latches a fault without register writes. Qualify never clears a fault.
No reset, rebase, rate-change or generation-recovery API exists.

Start disables Timer1 interrupts, stops Timer1, selects disconnected compare
outputs/normal mode, writes counter high then low, clears only TOV1 with W1C,
enables only overflow interrupt, and starts /64 counting. It does not reset the
shared free-running prescaler. Datasheet first-count phase is 1 through N+1 CPU
clocks, not an exact timestamp at the start call. Existing compare/capture
flags are retained and their interrupts stay disabled.

The caller installs exactly one ordinary, non-nesting TIMER1_OVF vector which
calls `hms_avr_clock_overflow` once. Hardware vector entry has already cleared
TOV1; the helper must not be used as a foreground manual clear/service routine.
All other Timer1 vectors are disabled. One foreground owner reads the clock.
State and output objects must be valid, disjoint and not mutated by callers.
No API is a general defense against malicious trusted code or RAM corruption.

## Qualification and the finite service bound

Init/start leave the clock unqualified. `hms_avr_clock_qualify` accepts only the
identical boot epoch and all three explicit **trusted caller attestations**:
source assurance, service-bound assurance, and uninterrupted-clock assurance.
These assertions have to be established outside this register layer. They are
not measurements or test results. The inspection image deliberately passes
zero assurance bits and therefore cannot qualify a clock if executed.

Every overflow must be accounted by its vector **strictly before 32768 raw ticks
after that overflow**, nominally 131.072 ms. This bound applies continuously
from start, including all interrupt masking, other ISRs, foreground work,
sleep/wakeup and debugger pauses. It is stronger than the 65536-tick wrap period
(nominally 262.144 ms). Merely bounding one CLI region is insufficient: all
delays to actual overflow accounting count. The installer must prove or monitor
this scheduling/continuity obligation; this lane supplies no such measurement.

A pending flag with counter >=32768, or the same late counter at vector-helper
entry, latches loss. A new TOV1 seen inside the helper is also loss. These are
partial observations. **Two or more unobserved wraps can alias a timely value**:
the retained counterexample advances two full periods plus17 ticks; one TOV1
and counter17 lead to one period plus17, undetectably one period short. The
test explicitly accepts that outcome outside the contract and then invalidates.
Likewise a temporary clock/prescaler change followed by restoration is not
detectable by reading current registers. Before any possible bound violation,
unaccounted sleep, debug halt, clock change or competing timer access, the
trusted platform must inhibit effects and invalidate. Qualification loss is
sticky for that boot domain.

## Snapshot and conversion

Within a saved-SREG window the reader checks configuration, reads TOV1, reads
TCNT1 low/high coherently, and reads TOV1 again. If the flag changes from0 to1,
it rereads low/high once. A pending flag adds one to a local 32-bit overflow
word; it does not consume the flag or update the ISR's overflow count. Later
vector service accounts that overflow exactly once. Under the service bound,
there cannot be a second unaccounted wrap. An impossible flag disappearance,
configuration mismatch, observed regression or counter exhaustion latches loss.

The extended counter has48 bits and never wraps successfully; at the next wrap
after raw `0xffffffffffff`, snapshot or ISR faults. Its nominal horizon is about
35.7 years, not an availability promise. Equal consecutive integer ticks are
valid. A prior unqualified read can update monotonic observation state but
cannot expose a sample. Output remains byte-for-byte unchanged on non-OK.

After restoring SREG, the reader creates the absolute raw tick and nominal
millisecond floor. For `high = 125*q+r`,

```
floor((high*65536 + low)/250)
  = q*32768 + floor((r*65536 + low)/250)
```

The residual is at most8191999, so two bounded 32-bit divisions suffice and no
64-bit divide is linked. The exact host 64-bit expression remains the independent
arithmetic oracle. Floor error is less than one nominal millisecond; initial
prescaler phase, oscillator error/drift, sample latency and any external mapping
uncertainty belong in the platform's error budget. Division is never in the ISR
or the snapshot's masked interval. AVR compiler-generated stack-pointer changes
add two small saved-SREG windows around the reader's stack frame.

Qualification linearizes with the captured counter, not with function return.
An interrupt after SREG restoration can invalidate the live clock before the
already-captured sample is copied out. A retained race test demonstrates this.
The endpoint must sample freshly at admission/dispatch/step and the driver must
enforce its clock/inhibit guard at actual I/O or native queue boundaries. This
module neither performs I/O nor proves independent stop. The full saved SREG
value is restored at each window; ordinary C ABI arithmetic flags after return
are not promised unchanged.

An integration wrapper may implement the endpoint `sample_clock` callback by
reading a local `hms_avr_clock_sample`, returning0 on non-OK, and returning its
`tick_ms` on OK after checking the endpoint boot epoch matches `boot_epoch`.
Only the externally attested clock status can contribute `HMS_EP_CLOCK_QUALIFIED`.
`BOOT_QUALIFIED`, `INHIBITED`, power/stop/driver capabilities and any other flags
must come from the actual platform's independent coherent snapshot. This lane
does not provide an integration wrapper that invents those flags or claim that
separately read flags are coherent with this sample.

## What the checks establish

The original host shim models TCNT1 low-byte latching of the shared TEMP high
byte, sticky TOV1, vector clear, and saved interrupt status. It exhausts all
65536 low-counter values both with and without pending overflow, injects one
rollover at every before/after register-read boundary, tests the transition
reread, ISR before CLI/after restore, post-restore invalidation, all256 SREG
patterns, threshold/exhaustion/regression/configuration/epoch/grant failures,
100 conversion boundary pairs, and50000 deterministic bounded random steps.
It is not an instruction-level MCU emulator, and it does not assert cycle or
interrupt latency measurements. Saved-SREG unit calls with I=1 directly into
the overflow helper test restoration only; normal vector entry has I=0.

The checker verifies the compiler archive hash, installed tools, linked support
objects/libraries, device specification and complete expected header closure
before AVR compilation. It retains source snapshots, commands, dependencies,
objects, ELF, map, disassembly, section/symbol counts and compiler stack files.
Selected instruction checks follow all local CFG branches, enforce saved-SREG
balance, low-before-high reads, flag/counter order, startup-only timer writes,
W1C setup constants, ISR late guards, and arithmetic calls after restoration.
All masked paths are acyclic including their reviewed helpers. Nine mutated
disassembly text fixtures check rejection sensitivity; none is executed.

For the selected pinned build, the masked instruction-count upper bounds,
including CLI/restore and acyclic helper instructions, are startup43,
qualification76, invalidation6, overflow helper63, snapshot122, plus reader
prologue/epilogue3 each. These are **instruction counts, not CPU cycles or time**.
The separate inspection ISR wrapper has37 instructions plus its helper call.
The 32-bit divide helper initializes a33-step shift/divide loop; the two
64-bit shift calls have constant16 and15 counts. These post-restore arithmetic
loops have no I/O, polling, CLI or allocation. Full pointer/register-value
dataflow and whole-application WCET remain outside these selected checks.

The separate linked image is1754 flash bytes and47 static SRAM bytes:22-byte
clock state,24-byte sample,1-byte result. Driver function text is1224 bytes.
Compiler `.su` records are static: source/running-config2 each, init6, start6,
qualify13, invalidate2, overflow5, read36, inspection ISR wrapper17 and main5.
These are per-function compiler records, not an integrated worst-case stack
proof: callees, return addresses per compiler convention, an interrupted
foreground, installed wrapper changes, interrupt nesting and other application
state require a complete linked application analysis. There is **no combined
endpoint/UART/EEPROM/clock firmware fit claim**.

Primary-source review is restricted to exact retained datasheet/errata LF
excerpts and hashes in `primary-source-review.json`. The web open of the manual
failed because the source exceeded the web response size; the existing pinned
official document was used. This is neither a fresh-document acquisition nor
whole-manual/latest-silicon qualification. Existing receipts outside this new
lane are preserved.
