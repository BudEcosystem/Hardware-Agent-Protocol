# Current result

The native checks pass. The original ATmega328P target still does not fit: the AVR link failed with a 9,042-byte physical flash overflow. The combined source changes reduce failed-map flash by 82 bytes and establish the intended finite/standing frame separation in the saved backend assembly. They do not establish a valid linked image, combined stack bound or runtime fit.

| Retained attempt | Observed result |
| --- | --- |
| [Native](checks-native.json) | 14 standing cases / 766 assertions in both plain and ASan/UBSan; reports agree. Original finite 26 / 2,548 / 20,000 malformed inputs and pipe smoke pass. Runtime 11 / 143,471 / 20,000 wire steps / 256 interrupt snapshots passes in both modes. |
| [AVR](checks-avr.json) | Ten queries and all 12 C units pass; the link fails with physical flash overflow 9,042. No final ELF exists. No AVR image, emulator or device ran. |
| [Data audit](AUDIT.json) | Pass: both terminal receipts, 37 outer commands/reaps and 37 observed owned identities absent; all 65 inputs per attempt, tools/runtime/aliases/plugin lookup, 36 current/original project files, 93 history files, 13 original control bodies and public244 remain exact. |

[MAP-REVIEW.json](MAP-REVIEW.json) records failed-link text arithmetic: `.text` 41,784 + `.data` 26 = 41,810 flash bytes, versus parent LTO 41,892. The application ceiling is also exceeded, by 9,554 bytes. All 29 function roots plus `main` and all nine exact charged storage objects are represented in the failed map. `.bss` 1,477 + `.data` 26 = 1,503 static bytes, exactly the 1,343 baseline plus the allowed 160. Adding the unchanged 512-byte stack reservation gives 2,015 bytes, with 33 bytes remaining arithmetically; this is not proof that the actual stack fits that reservation.

The failed map shows standing poll 7,410 bytes and standing handle 5,692 bytes. The separated finite callee plus wrapper total 2,892 bytes, 18 bytes larger than the prior combined wrapper; newly linked `memmove` and `memset` bodies cost 36 and 14 bytes. These are section observations, not isolated savings assigned to individual substitutions. The measured net change for the complete candidate is 82 bytes.

[GENERATED-BOUNDARY-REVIEW.md](GENERATED-BOUNDARY-REVIEW.md) and [boundary-coverage.json](boundary-coverage.json) retain complete current wrapper/callee text coverage. The standing call now carries six saved caller bytes and no finite local frame, versus the parent's 83 local + 18 saved = 101. That is 95 fewer caller-owned live bytes at this call only. The separate finite callee has 82 local + 18 saved bytes and its own outgoing arguments. Backend `.su` values of wrapper 8/static and finite 106/dynamic-bounded are local evidence; subtracting them does not prove an application stack reduction.

The attempt preserves 54 saved compiler artifacts totaling 8,457,521 bytes, 131 explicitly pre-LTO stack records and 106 possible backend `.su` entries. No complete final linked foreground/callback/helper/ISR stack graph or new final UART instruction qualification exists.

README, PLAN, REVIEW, project-source-review and the other 65 pinned inputs intentionally remain frozen preparation records, including their pre-execution status fields. This result note, audit, map and boundary reports describe the subsequent outcomes. Both first attempts and the exact tested source/runner bytes are preserved. No budget, target, root, protocol, dispatch-report ABI or qualification scope was relaxed to obtain these results.
