# AVR component build and Arduino UART/timer review

The original HMS framing decoder cross-compiles and links for an ATmega328P with the official Arduino AVR GCC toolchain. Its parser object occupies **219 bytes** under that target ABI. The small build-only harness, parser and bundled startup occupy **558 bytes of flash and 221 bytes of static SRAM**. These are component measurements, not the size of an HMS endpoint or a claim of Arduino device support. No target program was executed, no port was opened and no board was flashed.

## Evidence and acquisition

The official [Arduino package index](https://downloads.arduino.cc/packages/package_index.json) retrieved on 2026-11-06 identified Arduino AVR Boards **1.8.8**, its archive and the required compiler **7.3.0-atmel3.6.1-arduino7**. Both archives were fetched over HTTPS from `downloads.arduino.cc` and matched their SHA-256 values in the retained index:

| Retained archive | Bytes | SHA-256 |
|---|---:|---|
| [avr-1.8.8.tar.bz2](../raw/avr-1.8.8.tar.bz2) | 7,162,150 | `a234c2a43dcd01ce54be665806f183b8e6ec4e966d2e3e0c3358b63023d6390c` |
| [avr-gcc-7.3.0-atmel3.6.1-arduino7-x86_64-pc-linux-gnu.tar.bz2](../raw/avr-gcc-7.3.0-atmel3.6.1-arduino7-x86_64-pc-linux-gnu.tar.bz2) | 37,630,618 | `bd8c37f6952a2130ac9ee32c53f6a660feb79bee8353c8e289eb60fdcefed91e` |

[manifest.jsonl](../manifest.jsonl) records acquisition times, URLs, hashes and exact core archive member names. Package content is pinned by archive hash; no Git commit provenance is asserted. [selection.json](../selection.json) retains the selected index entries for convenience. The compiler was extracted with Python's `tarfile` data filter to `/tmp/hms-avr-toolchain-7.3.0-atmel3.6.1-arduino7/avr`. Nothing was installed globally and PATH was not changed. Only compiler/binutils host tools from this official toolchain were run; bundled startup/library objects were linked. Acquired Arduino core source was read without building or executing it.

The [reading receipt](../../reading-avr-full.json) records complete inspection of **15 selected files, 2,653 LF-delimited lines**, plus `boards.txt` lines 1–135. The complete files are `HardwareSerial.cpp`, `HardwareSerial.h`, `HardwareSerial_private.h`, `HardwareSerial0.cpp`, `Stream.cpp`, `Stream.h`, `Print.cpp`, `Print.h`, `wiring.c`, `wiring_private.h`, `main.cpp`, `hooks.c`, `Arduino.h`, `platform.txt`, and `variants/standard/pins_arduino.h`. The package index was parsed for the selected records, not read in full. Neither archive acquisition nor header inclusion implies reading all dependencies. USB bridge firmware, AVR register datasheet details, omitted Arduino dependencies and the compiler implementation remain outside this review.

The existing corpus auditor discovers this manifest and receipt without modification. Its successful run verified all currently registered corpus hashes/coverage chunks; hashes verify retained bytes and coverage metadata, not the truth of a reading or conformance claim.

## Reproducible target build

With the isolated compiler directory present, run from the repository root:

```sh
python3 scripts/check_serial_avr.py --toolchain-bin /tmp/hms-avr-toolchain-7.3.0-atmel3.6.1-arduino7/avr/bin
```

The original [driver](../../../../tests/serial_frame_avr_driver.c) holds one parser and two volatile byte mailboxes. It calls reset and feed to keep the parser in the final link; it supplies no UART, clock, ISR, transport, application operation, executor or device callback. It is never run. Target static assertions check the parser size and 16-bit `int`/32-bit `long` ABI. The [script](../../../../scripts/check_serial_avr.py) uses C11, `-Os`, warnings as errors, function/data sections, section garbage collection and compiler stack reports. LTO is deliberately disabled to retain inspectable function boundaries and `.su` reports; this is not the standard Arduino sketch recipe, which enables LTO.

This compiler's default generic `avr5` linker script has regions larger than an ATmega328P. The script explicitly constrains flash to 32,768 bytes, SRAM to 2,048 bytes starting at `0x800100`, and EEPROM to 1,024 bytes. It additionally checks the UNO profile's 32,256-byte application flash limit. Physical capacities come from the already retained UNO R3 manual; application limit and MCU/clock/variant come from `boards.txt` lines 89–106. These are model/build assumptions, not identification of connected hardware.

The [verification report](../../../../artifacts/verification/serial-avr.json) retains exact command arguments, source hashes, compiler binary hash/version, stdout/stderr, section and symbol measurements, limitations and hashes of the [ELF/map/object/disassembly/stack artifacts](../../../../artifacts/verification/serial-avr-build/).

| Quantity for this build | Bytes | Meaning |
|---|---:|---|
| `hms_avr_parser` | 219 | One fixed parser; 214-byte decoded buffer plus target layout |
| `hms_frame_reset` text | 28 | Linked function symbol |
| `hms_frame_feed` text | 356 | Linked function symbol; validation/FCS helpers are inlined |
| `.text` | 558 | Parser, harness, vectors and toolchain startup/exit |
| `.data` | 0 | Initialized static SRAM, also part of flash load image |
| `.bss` | 221 | Parser and two byte mailboxes |
| `.text + .data` | 558 | Linked harness flash load size |
| `.data + .bss + .noinit` | 221 | Linked harness static SRAM |

The parser functions account for 384 text bytes in this particular link. Their size is not an invariant across compilers, flags or integrations. The ELF file size includes metadata/debug sections and is not flash consumption. The native-host 220-byte parser size is compatible with this target's different 219-byte structure layout.

GCC reports individual static stack usage of 2 bytes for reset, 10 bytes for feed and 2 bytes for the harness main. These reports are not a validated whole-program call-stack bound or a measured high-water mark. No UART ISR stack, library/application stack, nested interrupts, queues, cryptography, procedure storage, bootloader, heap or other runtime component was measured. The remaining chip SRAM is not a demonstrated runtime budget. Successful linking establishes target compile/link compatibility, not execution correctness or timing.

## UART integration findings

The inspected [HardwareSerial header](../source/arduino-avr-1.8.8/cores/arduino/HardwareSerial.h) selects 64-byte RX and TX arrays for an ATmega328P-size SRAM configuration; the circular queues reserve a slot, so each holds at most 63 queued bytes. Those 128 array bytes and the other serial object state are absent from the HMS component measurement. Increasing the buffers is not free, and the header explicitly warns about missing atomicity guards for index widths above 256 bytes.

The receive path in [HardwareSerial_private.h](../source/arduino-avr-1.8.8/cores/arduino/HardwareSerial_private.h), lines 101–121, checks the parity-error bit, reads the data register and stores a byte only if the next queue position differs from the tail. Full-ring bytes and parity-error bytes are dropped without a caller-visible error record. This path does not inspect framing or data-overrun flags. The ordinary `read()` interface returns either one byte or `-1` for an empty queue; it supplies no error event to trigger the HMS parser reset required by the constrained draft. This is a concrete integration gap, not a framing-code defect. A future binding needs an error-aware bounded UART path, queue-loss handling and parser/session reset rules; a CRC failure is not an equivalent UART error notification.

[HardwareSerial.cpp](../source/arduino-avr-1.8.8/cores/arduino/HardwareSerial.cpp) configures a requested baud through integer register arithmetic in `begin()` (lines 117–150); a requested baud is not evidence of actual clock accuracy. `write()` (225–279) waits when the TX queue is full, and `flush()` (205–223) waits for queued and hardware transmission completion. `end()` first flushes and then clears the receive queue. It does not establish that remote, host, USB bridge or already-in-flight bytes are drained. `Print::write(buffer, size)` calls the byte writer repeatedly. Unbounded telemetry/diagnostic writes therefore cannot sit in an assumed bounded supervisory step.

The loop in [main.cpp](../source/arduino-avr-1.8.8/cores/arduino/main.cpp), lines 43–48, invokes `serialEventRun()` only after `loop()` returns. It is not a preemptive control task. [Stream.cpp](../source/arduino-avr-1.8.8/cores/arduino/Stream.cpp), lines 31–52 and 201–228, resets its timeout origin for each timed byte read/peek. A `readBytes` call can wait repeatedly; this timeout does not enforce an absolute frame assembly deadline. HMS should consume available bytes with bounded work per service step and retain an independent absolute receive deadline rather than infer one from `Stream::setTimeout`.

## Timer and runtime boundary

[wiring.c](../source/arduino-avr-1.8.8/cores/arduino/wiring.c) derives the Timer0 overflow increment from a prescale of 64 and 256 ticks; the overflow ISR updates `timer0_millis` and `timer0_overflow_count`. `millis()` reads its counter with interrupts temporarily disabled; `micros()` combines the count with the timer and compensates for one pending overflow. From that source, missed multiple overflows cannot be reconstructed by this single pending-bit correction. A runtime must bound interrupt masking and declare ownership of Timer0 before using these functions for deadlines. No such hardware validation was performed.

`delay()` repeatedly calls `yield()`, but the inspected [hooks.c](../source/arduino-avr-1.8.8/cores/arduino/hooks.c) defines the default yield as empty. `delayMicroseconds()` busy-waits. The `F_CPU=16000000UL` declaration, source cycle comments and absence of blocking inside the HMS parser do not establish response or stop latency. In particular, the parser performs its bounded FCS loop when a closing flag is received; this final-byte path still needs measurement under the intended UART/interrupt workload.

The next runtime gate is a separately specified error-aware UART service and wrap-safe absolute deadline wrapper with explicit queue/work budgets. After that, target execution, interrupt saturation/overflow, reset/brownout, full static/stack memory, and physical action/stop evidence are still required. Session authority, deduplication, procedure admission and physical effects remain outside this decoder and build-only harness.
