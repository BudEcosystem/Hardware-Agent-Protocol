# Retained LTO attempts

The reviewed LTO profile still does not fit the unchanged ATmega328P. Attempt 2 compiled all 12 C units and ran the LTO link path, then failed with a physical flash-region overflow of 9124 bytes. No ELF was produced or executed. The C project remains byte-identical to the sealed fit candidate; its native 13-case / 673-assertion results are inherited evidence, not a native rerun with this profile.

| Attempt | Retained result |
| --- | --- |
| [AVR 1](checks-avr.json) | Nine driver queries succeeded; the original file-name query returned a bare plugin name and the runner refused it before compilation. [Independent audit](AUDIT-ATTEMPT-1.json) preserved the distinction between a query-contract failure and a compiler failure. |
| [AVR 2](checks-avr-attempt-2.json) | Ten queries and 12 compilation commands passed; the link command exited 1 with the retained overflow diagnostic. All 23 outer commands were reaped. |

The corrected [search-directory lookup](build/avr-attempt-2/plugin-lookup.json) returned four ordered prefixes. Its first candidate, `avr/bin/../libexec/gcc/avr/7.3.0/liblto_plugin.so`, was readable and resolved to the archive-pinned `liblto_plugin.so.0.0.0`. Lookup, source, private-copy, installed-tool, alias and interpreter checks remained stable. Ownership closed empty, with no cleanup errors, pending interrupts or observed remaining command groups. These are the existing live-owner observations, not a universal process-containment claim.

The [failed-link map](build/avr-attempt-2/runtime.map) and its [data-only arithmetic/root join](MAP-REVIEW.json) report:

| Measurement | Bytes |
| --- | ---: |
| `.text` | 41866 |
| `.data` | 26 |
| Flash total | 41892 |
| Excess over physical 32768 / application 32256 | 9124 / 9636 |
| `.bss` / `.noinit` | 1477 / 0 |
| Static total | 1503 |
| Static plus unchanged 512 stack reservation | 2015 |

This is failed-link map arithmetic, not a valid-ELF resource qualification. Static growth is exactly the 160-byte allowance above the 1343-byte finite baseline; the reservation arithmetic leaves 33 SRAM bytes. All 29 function-root names and nine charged storage names appear in the map, and those storage sections retain their expected sizes totaling 1477 bytes. The successful-link symbol/range checks were not reached.

The 41892-byte total is 1172 bytes below the sealed fit candidate's 43064. The comparison includes both LTO and the stronger explicit root policy: 26 previously present function symbols and nine previously present storage symbols became newly forced. It is not an isolated per-option savings measurement, and no required API or reservation was removed to obtain it.

[The saved inventory](build/avr-attempt-2/lto-artifacts.json) contains 54 assembly/stack/IPA artifacts totaling 8398929 bytes. There are 131 explicitly pre-LTO fat-object frame records and one possible backend `.su` with 105 records, alongside saved backend assembly and WPA/LTRANS dumps. Their presence is not a complete final stack proof. No final ELF disassembly, callback/helper/ISR graph, UART timing qualification or runtime-fit result exists.

[Root's final audit](AUDIT.json) passed the retained byte/receipt joins, all 32 outer command/reap records across both attempts and all 244 public input identities. Its scope explicitly excludes resource arithmetic; [MAP-REVIEW.json](MAP-REVIEW.json) records that separate, limited failed-map calculation. Neither audit success nor root retention means the build passed.

Attempt 2 receipt SHA256 is `a98489ce18e5afe14562fc94379f9c2643691af4b25550e2c35dd238a535a45c`; map SHA256 is `77f813d20f63cb0b274f45bbd40e3c05ee8c76c62f904d821a8cd538257adc30`. Earlier README/PLAN/profile/review metadata are frozen preparation inputs; this results note records their subsequent execution outcome. No retry or frozen-input edit followed the failed link. The packet seal preserves the query refusal, actual LTO flash failure, audits and remaining qualification limits together.
