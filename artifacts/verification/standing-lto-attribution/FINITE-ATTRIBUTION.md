# Finite endpoint attribution

The two common endpoint handler sections occupy 7,754 bytes in the retained LTO failed map, 96 bytes less than the exact fit baseline. These sections include standing delegation; this is not a finite-only implementation size. The measurements do not establish flash fit, a successful linked image, or a combined stack bound.

| Section | Fit map | LTO map | Change |
| --- | ---: | ---: | ---: |
| `hms_endpoint_handle` | `0x1370` / 4,976 B | `0x1310` / 4,880 B | −96 B |
| `hms_endpoint_poll` | `0xb3a` / 2,874 B | `0xb3a` / 2,874 B | 0 B |
| Combined sections | 7,850 B | 7,754 B | −96 B |

The baseline is `standing-endpoint-fit/build/avr/runtime.map`; the comparison is `standing-endpoint-lto/build/avr-attempt-2/runtime.map`. The pinned `endpoint.c` copies in those two build directories are byte-identical (SHA256 `ede804ea4df5ccb61c2c7254f3dcdbb91a6e53edcafad43d045147bf42df64d7`). Earlier pre-fit object disassemblies were not used. The evidence is the final retained LTRANS assembly, not pre-LTO fat-object assembly.

The complete 620-line endpoint source was read, including handle lines 366–442, poll lines 596–604, and the full admission, finite polling, report, and serialization helpers. Both raw assembly units were read completely: poll lines 22166–24054 and handle lines 24055–27246 of `cc1w4vmK.ltrans0.ltrans.s`, SHA256 `f463e23cdf9238632feed38d7fe90de0d696b7e2ea965b18af034d5a7b2aadde`. Independent instruction-width sums equal the map sizes: 1,386 poll instructions / 2,874 bytes and 2,355 handle instructions / 4,880 bytes. Neither unit contains inline data. Exact input pins, read-range hashes, call sites, and measurement scope are in [finite-coverage.json](finite-coverage.json).

| Direct static call sites | Handle | Poll |
| --- | ---: | ---: |
| All direct calls | 78 | 51 |
| `__cmpdi2` | 14 | 13 |
| `__cmpdi2_s8` | 4 | 1 |
| `__subdi3` | 4 | 1 |
| `__adddi3` | 0 | 1 |
| `get64` / `get32` | 5 / 7 | 10 / 5 |
| `put64` / `put32` | 7 / 7 | 0 / 0 |
| `memcpy` | 2 | 1 |
| Indirect `icall` sites, separately | 1 | 1 |

The 38 direct wide-arithmetic/comparison calls occupy 152 bytes of CALL instructions across both handlers. They invoke shared helpers; they are not 38 duplicated arithmetic bodies. The retained map separately has 18-byte `_cmpdi2.o`, 24-byte `_cmpdi2_s8.o`, 18-byte `_subdi3.o`, and 18-byte `_adddi3.o` sections. The shared `put64`, `put32`, `get64`, and `get32` sections are 92, 12, 48, and 34 bytes respectively. Argument loads, register moves/spills, result use, shared callee instructions, and execution frequency are not included in CALL-byte totals. These counts alone cannot predict savings from outlining or changing representations.

The read WPA inline excerpts explicitly show `admit`, `syntax`, `arm_context`, `write_hello`, `write_control`, and `write_receipt` entering handle, and `apply_report` entering `poll_finite`, followed by the single-use `poll_finite` entering poll. `hms_standing_finite_slot` also enters admission. This establishes inlining into the measured callers, not duplication of large admission or execution engines. Compiler intermediate “size,” “time,” and “net change” estimates are not interpreted as machine-byte savings or runtime measurements. Only the recorded WPA excerpts were fully read, not the whole dump.

As a diagnostic, charging each instruction to its most recent `.loc` gives 1,844 handle bytes at admission source lines 269–333 (including 540 at lines 297–303), 430 at arm-context lines 254–265, and 824 at serialization lines 335–365. Another 44 bytes carry inlined `put16` locations. Poll has 1,900 bytes at finite-poll lines 531–594 (including 456 at pre-start time checks 544–554 and 404 at limits construction 575–581), and 718 at report handling 454–506. These are compiler debug-location buckets, not exclusive semantic budgets or removable bytes. Subsets overlap their parent buckets; optimization can move or merge source operations.

The generated stack behavior is a concrete limit on the source-level sibling-service comment at endpoint lines 599–600. Poll allocates an 83-byte local frame and saves 18 register bytes before the standing branch; the call to `hms_standing_poll` at assembly line 22299 occurs while that allocation remains live. The assembly annotations at 22260–22261 report frame 83 / stack 101; the `.su` entry reports 107 bytes, `dynamic,bounded`. Handle similarly has frame 63 / saved registers 18 (assembly 24148–24149); its standing call at 24341 follows 18 outgoing argument pushes, and its `.su` entry is 101 bytes, `dynamic,bounded`. The generated code, not the sibling-service comment, must govern any future combined graph/ISR analysis. These are local compiler observations, not an aggregate stack proof.

Admission's repeated time/authority checks span guard and clock callbacks. Poll likewise rechecks pre-start authority after callbacks and checks cutoffs after the driver returns before accepting its report. Those checks are behaviorally distinct, even when similar instructions recur. The hello/control/receipt wire formats, query/retire paths, shared ownership, exclusive cutoff rules, and conservative effect reporting remain part of the contract. This review authorizes no removal, flag change, or implementation. It ran no compiler, nm, objdump, candidate import, native test, probe, emulator, or target code; only retained text was read and counted.
