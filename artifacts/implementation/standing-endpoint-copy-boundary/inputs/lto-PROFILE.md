# Exact proposed profile

Every eligible C unit keeps the original target/ABI and warning options, `-Os`, function/data sections, `-fno-common`, `-fno-optimize-sibling-calls`, `-fstack-usage` and `-g`. It additionally receives:

```text
-flto=1 -flto-partition=one -ffat-lto-objects -fuse-linker-plugin
-save-temps=obj -fdump-ipa-cgraph -fdump-ipa-inline
```

The final link uses the GCC driver with the same options, excluding only the compile-stage `-MD` dependency option. `-ffat-lto-objects` is effective at compilation and ignored at linking. The original linker section limits and `--gc-sections` remain. There is no `-Ofast`, `-fwhole-program`, relaxed arithmetic, different MCU, larger region or reduced reservation. GCC 7.3 documents LTO with `-g` as experimental; debug information is not accepted as a stack/timing proof.

All generated LTO work is requested as one job and one partition. `/usr/bin/make` is hash-pinned and supplied through absolute `MAKE`; the environment is constructed explicitly and contains no inherited `MAKEFLAGS`, `MFLAGS`, `GNUMAKEFLAGS` or jobserver state. A private per-attempt `compiler-tmp` directory is supplied as `TMPDIR`. `/bin/sh` and its resolved executable are pinned as a possible make recipe shell. This does not assert that the wrapper necessarily executes a shell. All descendants remain within the existing live-owner command lifecycle and limits; RSS observation is not universal containment.

The actual archive-derived `lto1`, `lto-wrapper`, `liblto_plugin.so.0.0.0` and both plugin aliases are recorded in [toolchain-pins.json](toolchain-pins.json). The runner checks archive bytes, selected compiler/backend/plugin paths, alias targets, AVR headers/libraries/specs and host make/shell before use and after commands. It retains GCC-selected backend program queries, the same-profile program search-prefix query and ordered `R_OK` plugin selection, and built-in specs output. The plugin must be the first readable candidate and satisfy the existing archive/path/alias pins; [PLUGIN-LOOKUP-REVIEW.md](PLUGIN-LOOKUP-REVIEW.md) explains the corrected lookup after the preserved first-attempt refusal. No compiler was invoked to prepare the original pins: ELF dependency names were read as data. Host dynamic loader/libraries retain the prior trusted-unpinned scope; this is not a complete host runtime dependency qualification.

[retention.json](retention.json) gives the exact roots and reasons. Function groups are endpoint API 3, link/transport API 8, standing/common-core API 10, runtime API 4, prior frame-step/wire-drained capabilities 2, and Timer1/USART RX vectors 2. All 29 names appeared in the parent failed map. Three were already forced; 26 become newly forced. `main` must also remain. No previously-unlinked public helper is introduced.

| Charged object | Exact bytes |
| --- | ---: |
| `hms_target_runtime` | 964 |
| `hms_target_standing` | 134 |
| `hms_target_arena` | 256 |
| `hms_target_primitive` | 17 |
| `hms_target_controller` | 15 |
| `hms_target_installation` | 17 |
| `hms_target_initialized` | 1 |
| `hms_target_glue_reserve` | 9 |
| `hms_target_protection_reserve` | 64 |

These nine roots already existed and sum to 1477 bytes. Their final symbol sizes and nonoverlapping ranges must match; other `.data`, `.bss` and `.noinit` remain part of complete static accounting. The standing/glue charge stays 160 and total static growth must stay within 160 above the finite baseline 1343. The source target is unchanged, including zero commissioning assurances.

Before linking, `pre-lto-stack-records.json` labels every conventional fat-object frame as pre-LTO. After owner settlement, including failures, `lto-artifacts.json` inventories saved assembly, IPA and possible backend stack artifacts. Names alone do not establish their phase or final coverage. A successful link additionally retains the actual final map/symbol/disassembly outputs. Final foreground/callback/helper/ISR graph analysis and exact UART register/interrupt review remain separate; the runner always leaves runtime fit false and final stack coverage incomplete until that work exists.
