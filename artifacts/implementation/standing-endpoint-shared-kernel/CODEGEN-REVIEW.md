# Shared-kernel generated-code review

The failed AVR link allocates **39,902 flash bytes**, a **1,908-byte combined reduction** from the sealed copy-boundary parent. It still exceeds physical flash by **7,134 bytes** and the application allowance by **7,646 bytes**. There is no linked ELF, runtime-fit result, complete stack proof or physical qualification.

The retained [map](build/avr/runtime.map) has `.text=39,876`, `.data=26`, `.bss=1,477` and `.noinit=0`. Static SRAM remains **1,503 bytes**, exactly the 1,343-byte baseline plus the allowed 160-byte delta. Adding the unchanged 512-byte stack reservation gives 2,015 bytes; the remaining 33 bytes are arithmetic headroom, not a measured stack margin. The linker still uses ATmega328P, 16 MHz, 32,768 physical flash bytes, 2,048 SRAM bytes and 1,024 EEPROM bytes. All thirteen compile intents retain the selected target/LTO flags.

[codegen-review.json](codegen-review.json) joins all **29 function roots plus `main`** to unique allocated sections and matching symbol addresses. The nine exact storage allocations are positive, non-overlapping, inside `.bss` and total its full 1,477 bytes. Public endpoint/standing/link headers, the target, fixture and retention specification remain byte-identical to the parent. No changed target, removed root, smaller clock domain or additional static scratch storage explains the reduction.

## Actual sharing and costs

All **19 private kernel leaves** have one body each in the retained assembly and map, without suffixed `hms_ep_*` clones. Their combined allocated size is **2,348 bytes**, already included in the 39,902-byte total. Every kernel body's instruction-width sum equals its allocated section size. `hms_ep_write32` and `hms_ep_write64` also supply the link and fixture writer aliases. The report retains both literal and alias-resolved incoming direct calls; these are static call sites, not execution frequencies.

The new kernel remains a portable full-width C implementation. For example, `hms_ep_time_cmp` occupies 198 bytes, saves 18 registers, allocates six local bytes and can call the 64-bit comparison helper twice. `hms_ep_cutoff_min` occupies 294 bytes, including its own decoder/comparison/addition calls; the three age/on-time sites in `evaluate` now call that one body. Native and encoded elapsed comparisons still use complete unsigned 64-bit subtraction. Their shared implementation does not make marshalling or register saves free.

The visible reduction of any one old monolithic body is not a net saving. Standing poll is now 1,370 bytes, with separate `feedback` 728, `evaluate` 1,808 and `loss_service` 1,402-byte bodies, plus shared helpers and `driver`. Standing handling similarly retains separate OPEN, mutation and describe bodies. Only the complete image's **1,908-byte** difference is attributed to this source increment.

## Generated frames and call boundaries

The finite handler routing wrapper is smaller, but it is not a zero-frame wrapper. Its complete definition was read at assembly lines **27335–27597**. It retains five local bytes and 18 saved-register bytes, then pushes 18 outgoing argument bytes before either `hms_standing_handle` or `handle_finite`. Both branches share the same cleanup. The parent retained 63 local + 18 saved + 18 outgoing bytes at the standing call. The new wrapper therefore retains **58 fewer caller-owned bytes at that call**; its backend `.su` value is 43, versus the parent's 101. These include the two-byte incoming return address and are local evidence, not transitive bounds.

| Current generated body | Local bytes | Saved bytes | Maximum outgoing bytes indicated by `.su` | Backend `.su` |
| --- | ---: | ---: | ---: | ---: |
| `hms_endpoint_handle` | 5 | 18 | 18 | 43 |
| `handle_finite` | 21 | 18 | 0 | 41 |
| `admit` | 48 | 18 | 0 | 68 |
| `hms_endpoint_poll` | 0 | 6 | 0 | 8 |
| `poll_finite` | 67 | 18 | 4 | 91 |
| `hms_standing_handle` | 15 | 18 | 0 | 35 |
| `hms_standing_poll` | 59 | 18 | 0 | 79 |
| `loss_service` | 40 | 18 | 16 | 76 |
| `evaluate` | 37 | 18 | 16 | 73 |
| `driver` | 0 | 16 | 10 | 28 |

The complete standing-poll definition at **23715–24607** keeps its 32-byte report within the caller's 59 local bytes and passes it to the selected phase. Its 79-byte `.su` value cannot replace the parent's 136-byte entry as an application-stack comparison: the new phase frames remain live beneath it. `loss_service` and `evaluate` each push 16 bytes for `dispatch_report`. The complete `driver` definition at **21163–21465** pushes ten callback argument bytes before its `icall` at **21323**, then retains those bytes during `sample_clock` at **21337** and `synchronize` at **21343**, reclaiming them only at **21346–21353**. A future whole-stack analysis must follow that actual lifetime.

Both complete interrupt wrappers and runtime helpers were read at **16676–17273**. The vectors each have a 17-byte local `.su` entry; the overflow helper has five, receive helper two, and the overflow path also calls `running_config`, which calls `source_config`. These are retained call/frame observations. No new cycle bound, UART timing qualification or complete interrupted-foreground maximum is claimed. Indirect callbacks, all reachable paths and library stack contributions still need a complete final-image analysis.

## Coverage and next decision

The JSON retains input hashes, root/storage allocations, all 19 kernel extents and width joins, 25 phase-body observations, 131 scanned function definitions, 676 direct call sites and 14 manually read assembly ranges. Manual coverage is explicitly separated from automated whole-file scans; this is not a manual semantic read of every generated body. Two early data-only parser assertions caught whitespace/label handling errors before report publication; corrected parsing joins all kernel sizes. No compiler, inspection executable, candidate import, test, emulator or device was executed by this reviewer, and no existing source/build artifact was changed.

A reviewed full-width bytewise kernel remains an option from the prior proposal, but it cannot be promised to close this gap. Even removing all 2,348 bytes of current kernel bodies for free would still leave **4,786 bytes of physical overflow** and **5,298 bytes of application overflow**. Further work needs whole-image accounting, including caller costs and retained behavior; a small kernel-only saving is insufficient. Keep this exact profile explicitly unsupported until a valid link, complete stack/timing evidence and separate installed-device qualification exist.
