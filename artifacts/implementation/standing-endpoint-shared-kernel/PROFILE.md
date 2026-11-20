# Unchanged target and compiler profile

ATmega328P remains16MHz,2KiB SRAM,32KiB physical flash and32,256-byte application allowance. EEPROM remains1,024 bytes. Static growth is at most160 over baseline1,343; standing bytes128 plus glue ceiling32, the existing256-byte arena,64-byte protection reservation and512-byte stack reservation all remain charged. All29 function roots plus main,9 exact storage roots and Timer1/USART vectors are unchanged in the exact copied retention specification and target source.

Native remains C11, `-g -Wall -Wextra -Wconversion -Werror -Wvla -fno-common`, plain `-O2`, sanitized `-O1 -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie`. The original finite/pipe checker keeps its original flags; only its kernel source/header joins change. New controls execute only native synthetic models after review.

AVR remains archive-pinned GCC7.3, `-mmcu=atmega328p -DF_CPU=16000000UL`, identical warnings, `-Os -ffunction-sections -fdata-sections -fno-optimize-sibling-calls -fstack-usage`, compile-only `-MD`, and matching compile/GCC-driver-link LTO flags:

```text
-flto=1 -flto-partition=one -ffat-lto-objects -fuse-linker-plugin
-save-temps=obj -fdump-ipa-cgraph -fdump-ipa-inline
```

The reviewed archive/backend/plugin/alias/header/library/spec pins, ordered first-readable `R_OK` plugin lookup, `/usr/bin/make` and `/bin/sh` pins remain unchanged. Exact parent pin copies are retained. Default AVR bin now names the actually retained `artifacts/implementation/avr-link-integration/toolchains/avr-gcc-7.3.0-cponmrdo/avr/bin`; no restoration/download/tool query occurred. The minimal environment excludes inherited MAKEFLAGS/jobserver state and uses one private compiler TMPDIR.

Pre-LTO records remain labeled pre-LTO; saved backend artifacts remain unqualified inventory even on failed link. Successful linked-image inspection cannot substitute for full callback/helper/ISR stack and UART instruction analysis. No ELF, emulator, serial port or physical device is executed by the proposed checks. Scope includes no physical commissioning or complete host/PAT integration.
