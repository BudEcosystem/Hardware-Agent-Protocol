The failed-link image uses **39,186 flash bytes**, 716 fewer than the sealed shared-kernel parent. It still exceeds the ATmega328P's physical 32,768 bytes by **6,418**, and the unchanged 32,256-byte application budget by **6,930**. There is no valid ELF and no combined stack qualification.

The root reviewed and ran [codegen_measure.py](codegen_measure.py); [codegen-measurements.json](codegen-measurements.json) retains the complete parent/current inventory, exact input hashes, function extents, instruction/table widths, explicit calls and jumps, aliases, backend frames and charged roots. The reader's first assertion failure and narrow correction remain in [reader-history/draft01](reader-history/draft01/REVIEW.md). I read retained data and source only; I did not invoke a reader, compiler, candidate, target or inspection executable.

The current map contains 146 emitted C function bodies totaling 38,606 bytes, plus 554 bytes of startup, vectors and library sections, giving `.text=39,160`. `.data=26`, `.bss=1,477` and `.noinit=0`. All 29 required function roots plus `main`, all nine exact charged storage roots and all six fixture/writer aliases remain. Static storage stays 1,503 bytes: baseline 1,343 plus the full 160-byte allowance. Adding the planned 512-byte stack reserve gives 2,015 bytes as arithmetic only. The failed-link map and backend records do not prove the stack stays inside that reserve.

| Emitted owner, including inlined descendants | Parent bytes | Current bytes | Difference |
| --- | ---: | ---: | ---: |
| Numeric/serialization kernel | 2,348 | 1,674 | −674 |
| Finite endpoint | 10,002 | 10,160 | +158 |
| Standing controller | 15,726 | 15,526 | −200 |
| All other emitted bodies | 11,246 | 11,246 | 0 |
| Startup/vector/library text | 554 | 554 | 0 |

These are combined emitted-owner changes, not isolated savings for individual edits. Compiler `.lto_priv` suffixes changed; the inventory's exact-name comparison must not treat a renamed body as removed functionality. For example, the constant, describe, guard and reference private families retain the same member sizes under different suffixes.

The byte backend is present as shared loops. The four elapsed wrappers each occupy 20 bytes and call the single 142-byte `elapsed_bytes`; the two native/encoded time wrappers each occupy 8 bytes and call the single 62-byte `byte_compare`. Encoded comparison/ABSENT checks occupy 42/32 bytes. `add_bytes` and `commit_bytes` cost 36/20 bytes. Snapshot/cutoff/duration helpers and their caller setup are also charged in the 1,674-byte kernel subtotal. The 48-byte age writers load their two relevant source bytes before writing; they project only the exported low-16 age, without narrowing a timing predicate. The assembly views confirm eight-digit loops for full-width comparison, subtraction and sum, with explicit encoded/native addressing.

Smaller phase callers do not imply equivalent image savings. These exact groups show the cost of extracted bodies and calls:

| Caller plus newly emitted phase bodies | Parent bytes | Current bytes | Difference |
| --- | ---: | ---: | ---: |
| `admit` + admission time phases | 1,556 | 1,224 + 300 + 90 = 1,614 | +58 |
| `poll_finite` + `finite_limits` + `apply_report` | 2,190 | 1,208 + 302 + 804 = 2,314 | +124 |
| `hms_standing_poll` + `accept_observation` | 1,370 | 690 + 754 = 1,444 | +74 |
| `evaluate` + `dispatch_cutoff` | 1,808 | 1,464 + 506 = 1,970 | +162 |

Other finite/standing changes offset some of this growth. In particular, `account_ok` changes 436→286 bytes, `fresh` 426→366, loss service 1,402→1,288, and `cutoff_reason` 206→182. These totals do not separate numeric changes from extraction, altered inlining or register allocation.

The manually read generated frames also show a tradeoff. Local and saved columns exclude the two-byte return PC. Outgoing columns identify observed pushes and their cleanup in these bodies; the `.su` column is the compiler's function-local maximum, not the transitive call stack.

| Current function | Local | Saved | Outgoing | Current backend `.su` | Parent `.su` |
| --- | ---: | ---: | ---: | ---: | ---: |
| `hms_endpoint_poll` | 0 | 6 | 0 | 8 | 8 |
| `hms_endpoint_handle` | 5 | 18 | 18 | 43 | 43 |
| `handle_finite` | 21 | 18 | 0 | 41 | 41 |
| `hms_standing_handle` | 15 | 18 | 0 | 35 | 35 |
| `admit` | 50 | 18 | 0 | 70 | 68 |
| `poll_finite` | 58 | 18 | 4 | 82 | 91 |
| `hms_standing_poll` | 32 | 17 | 0 | 51 | 79 |
| `accept_observation` | 21 | 18 | 0 | 41 | previously inlined |
| `evaluate` | 25 | 18 | 16 | 61 | 73 |
| `dispatch_cutoff` | 22 | 18 | 0 | 42 | previously inlined |
| `loss_service` | 46 | 18 | 16 | 82 | 76 |
| `driver` | 0 | 16 | 10 | 28 | 28 |

The standing poll's 49 caller-owned bytes remain live when it calls loss service, evaluation, acquisition driver or observation acceptance. Its 28-byte reduction is therefore not a transitive stack reduction. Loss service grew six local bytes. The finite poll now nests `finite_limits` (backend 20) and `apply_report` (12); admission nests its new time phases (15 and 8). The driver retains ten outgoing argument bytes across both `sample_clock` and `synchronize` after its indirect step call. Finite poll similarly retains four outgoing bytes across `sample_clock`. Both public wrapper boundaries remain explicit; the finite and standing branch call frames are mutually exclusive at the wrapper, not at all ancestor frames.

The complete manually read loss body still copies witness fields before the accounting check, computes the modulo elapsed snapshot before checking chronological order, and only publishes valid quiescence after successful accounting. The generated admission body captures all four eight-byte fields before `describe`, then calls the pre/post-guard time phases at the original callback boundaries. These are targeted source/assembly observations; differential controls and whole-stack proof remain distinct evidence.

For the next reduction, numerical leaf replacement alone has insufficient scope. Even the impossible free removal of the entire remaining 1,674-byte kernel would leave a 5,256-byte application gap. The seven retained wide arithmetic/shift library sections total 210 bytes and are unchanged; removing them alone would leave 6,720 bytes. They still have callers outside the new backend, including scalar setup in finite limits, dispatch cutoff and protocol session/ARM handling. No library-removal saving is credited here.

The next coordinated proposal should first charge complete callback-separated paths, then replace repeated *aggregate* validation/serialization work across finite admission/poll and standing activation/loss. The visible targets are the 1,614-byte admission group, 2,314-byte finite polling/report group, 1,970-byte evaluation/cutoff group and 1,288-byte loss service, plus the unchanged 1,640-byte finite handler and 1,870-byte standing handler. Keeping captured byte views through pure adjacent time checks can avoid decode/store/reload and register-wide argument setup; compact shared request-envelope and response-field routines can address repeated pointer/copy scaffolding. Such a proposal must charge descriptor tables, helper calls, all destination writes and additional live frame storage. It must preserve exact early-error precedence, per-store snapshot/alias behavior, callback and freshness barriers, first-loss versus actual handoff timestamps, and partial witness writes. It must not merge distinct finite and standing state semantics merely because their checks look similar.

The unchanged runtime owner is still 4,668 bytes, including `hms_avr_runtime_start` 2,148 and `clock_snapshot` 808; the required synthetic fixture remains 3,120 bytes, including `standing_step` 1,762. These costs and the real boot/EEPROM/clock/UART services remain in the whole-image accounting. Their size is not proof of duplicate inlining, and this review does not remeasure WPA inline-copy costs. A broader runtime/driver-boundary proposal needs its own source/call evidence and must retain every service, assurance check, root and reservation. No candidate or savings estimate for that broader change is established here. The remaining gap makes another isolated tiny substitution inadequate to establish original-board feasibility.

[codegen-review.json](codegen-review.json) records the exact manual coverage and pins. The automated scope covers every emitted body and allocated text section; manual instruction reading is confined to the listed ranges. There is no complete library/ISR/indirect-call stack graph, no valid final ELF, no qualified elapsed-time bound and no device execution.
