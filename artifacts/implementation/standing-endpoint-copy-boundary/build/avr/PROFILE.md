# Unchanged build profile

This successor retains the corrected sealed LTO runner's native and AVR build commands, except for native coverage gates and source/metadata paths. [inputs/lto-PROFILE.md](inputs/lto-PROFILE.md) is the exact earlier detailed profile; its discussion of newly forced roots refers to the historical fit-to-LTO transition. This candidate adds no forced root.

Native compilation remains C11, `-g -Wall -Wextra -Wconversion -Werror -Wvla -fno-common`, plain `-O2`, and sanitized `-O1 -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie`. The existing original finite/pipe checker retains its own unchanged flags. Runtime register models and standing driver remain synthetic; only native binaries may later execute.

AVR remains pinned GCC 7.3, `-mmcu=atmega328p -DF_CPU=16000000UL`, the same common warnings, `-Os -ffunction-sections -fdata-sections -fno-optimize-sibling-calls -fstack-usage`, compile-only `-MD`, and matching compile/GCC-driver-link LTO flags:

```text
-flto=1 -flto-partition=one -ffat-lto-objects -fuse-linker-plugin
-save-temps=obj -fdump-ipa-cgraph -fdump-ipa-inline
```

The selected archive-derived driver/backend/plugin paths, plugin aliases and ordered first-readable `R_OK` lookup, headers/libraries/specs, pinned `/usr/bin/make` and possible `/bin/sh` remain unchanged. [toolchain-pins.json](toolchain-pins.json), [plugin-lookup-source-pins.json](plugin-lookup-source-pins.json) and [PLUGIN-LOOKUP-REVIEW.md](PLUGIN-LOOKUP-REVIEW.md) are exact parent copies. No new tool query or import was used to prepare them. The explicit environment still excludes inherited make/jobserver flags, and private `TMPDIR` confines saved LTO artifacts to the attempt.

Keep all 29 function roots plus `main`, nine exact/nonoverlapping charged storage objects, Timer1/USART vectors and the unmodified target. Physical/application flash limits remain 32,768/32,256; SRAM 2,048; EEPROM 1,024; stack reservation 512; total static growth at most 160 over baseline 1,343. The 128-byte standing state, 32-byte glue ceiling, 256-byte arena and 64-byte protection reservation are unchanged. Do not trade away reserves or required paths for a passing map.

Pre-LTO `.su` records remain explicitly pre-LTO. Saved backend artifacts are inventory only. The added noinline source boundary requires generated-code inspection, and complete final foreground/helper/callback/ISR stack accounting remains separate. Neither the runner nor a successful size check reports runtime fit. No AVR image, emulator, serial port or physical device may execute in these checks.
