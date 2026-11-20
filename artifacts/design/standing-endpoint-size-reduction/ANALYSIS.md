# Evidence and feasibility

The failed link allocates `.text=41,784`, `.data=26`, `.bss=1,477`, `.noinit=0`. Flash is 41,810 bytes: 9,042 above the physical 32,768 and 9,554 above the application allowance 32,256. Static SRAM is 1,503, exactly baseline 1,343 plus the allowed 160-byte standing/glue delta. Adding the unchanged 512-byte stack reservation gives 2,015; the remaining 33 bytes are arithmetic headroom, not a stack proof or spare persistent-state allowance. No linked ELF exists.

| Allocated body | Bytes | Instructions | Own local/saved frame comment |
|---|---:|---:|---:|
| `hms_standing_poll` | 7,410 | 3,558 | 100 + 18 = 118 |
| `hms_standing_handle` | 5,692 | 2,691 | 23 + 18 = 41 |
| `hms_endpoint_handle` | 4,880 | 2,355 | 63 + 18 = 81 |
| Sum | 17,982 | 8,604 | Not a call-path sum |

The standing handler has 5,660 instruction bytes plus a 32-byte switch table. All other stated body sizes equal the instruction-width sums. Widths are computed from retained AVR assembly text and joined to allocated map sections; they are not disassembled final ELF measurements. These three bodies constitute about 43% of flash. Removing the physical excess solely from them would require over half their combined size. The small exact duplicates below cannot establish that outcome.

## Repetition that is actually observed

Raw lines refer to the pinned `ccnmby5y.ltrans0.ltrans.s`.

| Spans | Observed repetition | Meaning and limit |
|---|---|---|
| 18188–18240 / 18283–18335 | 48 identical instruction tokens, nominal 96 bytes per copy | Accepted-observation field-copy/quality/pending prefix, from standing.c545–546. Channel flag arguments immediately following differ. Validation paths are not duplicate engines. |
| 18951–19004 / 19091–19144 | 54 identical tokens, nominal 110 bytes each | Part of the two input-age saturation/min calculation in `dispatch_cutoff`. |
| 19007–19048 / 19146–19187 | 40 identical tokens, nominal 84 bytes each | Another part of the same two input-age calculation. Distinct surrounding branches and live values must be retained. |
| 21934–21967 / 22795–22828 | 30 identical tokens, nominal 66 bytes each | OPEN/RESUME native `now_tick` encoding and beginning of ABSENT initialization. Whole OPEN and RESUME are semantically different. |
| 26665–26691 / 26839–26865 | 26 identical tokens, nominal 54 bytes each | Finite HELLO/control serialization marshalling around `put64`. Field destinations differ outside the matching run. |

Matching is exact mnemonic/operand text; no register or label renaming was used. These are **not proven identical machine bytes**: the failed LTRANS object named in the map is no longer retained, and there is no final ELF. Branch/call relocations also make text equality insufficient in general. The packet retains complete token windows, rather than asserting an object-byte comparison that was not possible. Windows overlap other candidates; adding their lengths would double count. New helper bodies, address formation, calls and saved registers must be charged before any net saving is reported.

WPA lines6435–6638 explicitly show `accept_observation`, `feedback`, `loss_service`, `dispatch_cutoff`/`transition`/`evaluate`, `open_record`, `mutation`, finite `admit` and response writers incorporated into their callers. Several are called once. This is evidence of large inlined control paths and compiler-generated repeated subregions, **not** evidence of multiple separately linked copies of each engine. GCC's reported IR sizes are not byte estimates.

## Where a larger refactor can act

The three bodies have 69 static direct calls to 64-bit comparison/add/subtract helpers, 31 calls to 64-bit decoders and 15 calls to the shared 64-bit encoder. Counts describe static call sites, not execution frequency. The 115 call instructions themselves occupy 460 bytes, already inside the body sizes. Surrounding argument setup, preserving live wide values and stack addressing are additional costs, but no whole-body percentage has been labeled removable.

The source frequently needs only a Boolean or a bounded delta from an encoded timestamp, yet decodes eight bytes, returns a full native value and moves it into wide arithmetic argument registers. `dispatch_cutoff` also repeats two age calculations. This supports a shared private operation on pointers to already captured native values and encoded fields, returning a small result where appropriate. It does not support narrowing the time domain.

`put64` is already shared by `w64`, link `write64` and the fixture writer through assembly aliases. It occupies 92 bytes, saves eight registers, and calls `__lshrdi3` inside its eight-iteration loop. `read64`/`r64` occupy 48 bytes; finite `get64` is another 48-byte body with the same instruction structure except labels. `read32`/`r32` and finite `get32` similarly occupy 34 bytes each. At most 82 bytes of body duplication are directly identified in the two decoder pairs; merging names alone cannot close this gap. The map also retains `fresh`482, `lease_valid`266, `account_ok`490 and `dispatch_report`386 bytes. Some time work is already shared. Preserve `dispatch_report`'s existing ABI.

The allocated 64-bit shift/add/subtract/compare library sections total 210 bytes (50+58+18+24+18+18+24). They serve other retained paths, so none is assumed removable. Current libc sections are `memcmp`26, `memcpy`18, `memmove`36 and `memset`14. Additional calls or replacement helpers are never free.

Standing poll contains 438 literal Y-offset-adjust instructions (876 nominal bytes); finite handle contains 58 (116 bytes). These are recognizable `adiw`/`sbiw r28,N-N` adjustments for out-of-range stack offsets. Their count identifies register/frame pressure, not a saving: callee frames, outgoing arguments and different pointer work can replace them. Standing handle has no such matching adjustment pattern despite its large size.

Finite handle's raw23955–24250 prologue and v2 branch retain its 63-byte local frame plus 18 saved registers while pushing 18 outgoing argument bytes for `hms_standing_handle`. The actual standing-call path thus retains the finite caller frame before the standing frame is added. A thin routing wrapper with an explicit finite handling boundary is a justified stack/liveness proposal, analogous to the already observed poll separation. It may grow flash. The existing poll separation reduced retained caller bytes on the standing call by 95 but grew the wrapper-plus-finite sections by 18 bytes; that prior result cannot be generalized into a new saving estimate.

## Feasibility conclusion

The prior seven copies, twelve fills and poll boundary produced only **82 net fewer flash bytes**, including new libc sections. The measured observation prefix alone offers only one redundant 96-byte span before extraction costs. There is no evidence that a sequence of similarly local edits can remove 9,042 bytes.

A broader private time/serialization implementation and deliberate phase structure is the supported next direction. It addresses repeated call-site work across all three bodies, plus the existing time helpers, without removing policy or service paths. The source extent is substantial; measured savings are unknown. Even complete removal of the identified 992 bytes of Y adjustments, which is not achievable for free, would be insufficient. Original-board fit may remain unsupported after the refactor. A successful small first measurement must not be reported as evidence that the full gap will close.
