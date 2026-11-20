# Fit candidate results

The scoped candidate passes native controls and reduces total flash load by **582 bytes**, but still **does not fit the original ATmega328P**. The complete AVR link exceeds physical flash by 10296 bytes. Its failed-link map now reaches the exact proposed static-growth allowance of 160 bytes; this is resource arithmetic, not a valid ELF or combined stack qualification.

The unchanged README, PLAN and source/runner reviews are frozen preparation inputs. Their prospective status statements are superseded by these completed attempts; their exact bytes remain in the build snapshots.

| Attempt | Result |
| --- | --- |
| [Native 1](checks-native.json) | Pass: 13 standing cases / 673 assertions in each plain and ASan/UBSan run; original finite 26 cases / 2548 assertions / 20000 malformed inputs plus pipe smoke; AVR register integration 11 cases / 143471 assertions / 20000 wire-oracle steps / 256 interrupt snapshots in each mode. |
| [AVR 1](checks-avr.json) | All 12 units compile; the complete target link fails with physical flash overflow. No valid standing ELF is produced. |

The two receipts retain 14 and 19 outer commands respectively, all 33 reaped. They report unchanged original/frozen sources, installed pins and runtime; empty/closed ownership; no cleanup errors or pending interrupts; and observed groups absent. These are the runner's stated orderly-cleanup and observation claims, not universal process containment or host-failure recovery.

The independent [retained-data audit](AUDIT.json) verifies both attempts, current
source correspondence, all 33 observed owned identities absent and all 244 public
inputs exact, without rerunning the controls. It explicitly retains native success
and AVR failure as different outcomes. [MAP-REVIEW.json](MAP-REVIEW.json) separately
joins the failed-link section arithmetic to the diagnostic and sealed parent.

The [failed-link map](build/avr/runtime.map) and [linker diagnostic](build/avr/avr-link.stderr) give:

| Quantity | Sealed parent | This candidate |
| --- | ---: | ---: |
| `.text` | 43612 | 43038 |
| `.data` | 34 | 26 |
| Flash load, `.text` + `.data` | 43646 | 43064 |
| Excess over physical 32768 | 10878 | 10296 |
| Excess over application ceiling 32256 | 11390 | 10808 |
| Static SRAM, `.data` + `.bss` + `.noinit` | 1511 | 1503 |
| Static growth over sealed finite baseline 1343 | 168 | 160 |

The combined changes reduce `.text` by 574 bytes and `.data` by 8 bytes. No separate per-change flash saving is inferred: descriptor field stores, bounded signed feedback arithmetic and four encoded timestamp comparisons were built together. The failed map no longer contains the fixture's eight-byte SRAM-backed constant. `.bss` remains 1477 and `.noinit` zero. Static 1503 plus the unchanged 512-byte stack reservation equals 2015, leaving 33 arithmetic SRAM bytes; complete foreground/callback/helper/ISR stack usage remains unproved.

The MCU, clock declaration, wire/lifecycle behavior, compiler flags and every reservation remain unchanged. No LTO profile was built in this packet. No target ELF, emulator or physical port was executed or accessed. The synthetic controls establish neither physical I/O qualification nor completed durable-host/PAT integration. The unchanged target remains unsupported by this implementation; [NEXT.md](NEXT.md) records the continuation.
