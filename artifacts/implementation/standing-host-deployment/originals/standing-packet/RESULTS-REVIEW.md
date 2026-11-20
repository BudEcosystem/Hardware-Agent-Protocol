# Standing controller results

The current candidate passes the native controls but **does not fit the original ATmega328P target**. All twelve AVR translation units compile; the complete link fails because the physical 32768-byte flash region is exceeded by 10878 bytes. The failed-link map also exceeds the proposed 160-byte additional static-storage allowance by 8 bytes. No valid standing target ELF or combined stack qualification was produced.

This document records the completed attempts. The unchanged README, PLAN, REVIEW, runner review and source-review metadata are historical preparation inputs, preserved exactly in the attempt snapshots; their prospective or source-only status statements are superseded by these results. Public source and both sealed design/AVR input packets remain unchanged.

| Attempt | Retained result | Subsequent change |
| --- | --- | --- |
| [Native 1](checks-native.json) | Original finite suite and plain AVR register integration pass; standing compilation refuses an unsigned-to-byte quality ternary under `-Wconversion -Werror`. | One explicit bounded `uint8_t` cast; [review](ATTEMPT01-REVIEW.md). |
| [Native 2](checks-native-attempt-2.json) | All native suites pass, including 12 standing cases and 638 assertions in each plain and ASan/UBSan run. | No semantic change. |
| [AVR 1](checks-avr.json) | Standing compilation refuses three byte-addition/signed-promotion expressions under `-Wsign-conversion -Werror`. | Explicit unsigned head conversion at exactly three ring-index sites; [review](AVR-ATTEMPT01-REVIEW.md). |
| [Native 3](checks-native-attempt-3.json) | Final source passes all native suites. | None. |
| [AVR 2](checks-avr-attempt-2.json) | All 12 units compile; complete target link fails with physical flash overflow. | None; target, warnings and reservations remain unchanged. |

Final native evidence includes 12 standing cases / 638 assertions in each plain and ASan/UBSan run; the original finite suite's 26 cases / 2548 assertions / 20000 malformed inputs and pipe smoke; and the AVR register integration's 11 cases / 143471 assertions / 20000 wire-oracle steps / 256 interrupt snapshots in each plain and ASan/UBSan run. These are synthetic host checks. They exercise shared finite/standing authority, exact wire/replay behavior, local feedback, acquisition and output cutoff gates, full-ledger loss/resume, interrupted-feedback ACK restrictions, witness ordering and stop under TX backpressure. They do not qualify physical I/O or an end-to-end prompted application.

[AUDIT.json](AUDIT.json) verifies all five retained attempts, their frozen inputs and command evidence: 65 outer commands and reaps, observed owned identities absent, current source native pass and AVR failure, and 244 public inputs exact. The receipts preserve logs, intent/start/result records and failure snapshots. This is the runner's stated ownership/observation scope, not a claim of protection against runner SIGKILL, host death or every possible descendant escape. That audit expressly excludes AVR resource arithmetic; [MAP-REVIEW.json](MAP-REVIEW.json) separately checks the following failed-link map arithmetic against the linker diagnostic.

| Failed-link map quantity | Bytes | Interpretation |
| --- | ---: | --- |
| `.text` + `.data` load | 43612 + 34 = 43646 | 10878 above physical 32768; 11390 above the retained 32256-byte application ceiling. |
| `.data` + `.bss` + `.noinit` | 34 + 1477 + 0 = 1511 | 168 above the sealed 1343-byte static baseline; proposed delta 160 is exceeded by 8. |
| Static + reserved stack | 1511 + 512 = 2023 | Arithmetic leaves 25 of 2048 SRAM bytes; this does not establish a sufficient stack or target fit. |

The [failed map](build/avr-attempt-2/runtime.map) places 8 bytes of `standing-fixture.o` read-only data in SRAM-backed `.data`. The constant `hms_ep_primitive` initializer in [finite_describe](project/tests/standing_fixture.c) is a source/layout explanation consistent with those 8 bytes: one 32-bit field and four byte fields. Its exact relocation attribution has not been inspected, so this remains an inference. Explicit standing state/pointers/configuration/core glue and its reservation account for the intended 160 bytes; the compiler-generated data must also count against the complete-image budget.

The same failed map attributes 5866 bytes to `hms_standing_handle` and 8002 to `hms_standing_poll`, identifying concrete size-review targets. Compiler `.su` records include a 143-byte bounded dynamic local frame for standing poll, 47 for handle and 49 for the synthetic standing driver. These are local function reports, not a combined foreground/callback/ISR bound. The sealed finite image's stack assessment cannot be inherited by this controller.

No target ELF was executed, no emulator or physical port was used, and no physical driver, independent stop or clock/boot commissioning follows from these results. The actual local lifecycle/kernel implementation is present and natively checked; durable host deployment, PAT qualification/selection and learning integration remain required. [NEXT.md](NEXT.md) records the bounded continuation from this unsupported-fit result.
