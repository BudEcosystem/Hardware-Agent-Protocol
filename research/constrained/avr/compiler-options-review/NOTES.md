# Possible later LTO profile: evidence and limits

Research only. The original ATmega328P limits, lifecycle, timestamp representation and reservations remain unchanged. No new compiler option is authorized by this packet.

## Optimization chapter

`-Os` targets size; enabled passes vary with target/configuration. Single-use static functions may disappear through inlining. The LTO guidance recommends matching optimization/LTO options at compilation and final linking through the GCC driver. GIMPLE-bearing inputs permit cross-unit optimization; ordinary machine-code inputs can coexist. Target options and ABI settings need consistency. Bytecode is GCC-version-specific. [Official chapter](https://gcc.gnu.org/onlinedocs/gcc-7.3.0/gcc/Optimize-Options.html); retained lines 23–27, 138–159, 244–249, 1315–1460.

Plugin support supplies symbol visibility and archive extraction; the chapter identifies gold or GNU ld 2.21+, and plugin-aware `gcc-ar`, `gcc-ranlib`, `gcc-nm`. Fat objects also contain conventional code; non-fat objects require LTO-aware tools. LTO jobs default to one; requested parallelism uses make. `-flto` with `-g` is described as experimental. [Official chapter](https://gcc.gnu.org/onlinedocs/gcc-7.3.0/gcc/Optimize-Options.html); retained lines 1429–1529.

The `-fwhole-program` subsection discourages combining it with LTO, while later passages discuss conditional use without plugin visibility information. These passages do not justify adding it here. `-Ofast` and `-fmerge-all-constants` explicitly relax language guarantees. [Official chapter](https://gcc.gnu.org/onlinedocs/gcc-7.3.0/gcc/Optimize-Options.html); retained lines 146–151, 309–317, 1307–1314, 1357–1365, 1449–1455.

## Developer chapter

`-fstack-usage` reports each function's bytes and qualifiers: `static` denotes fixed allocation; `dynamic,bounded` includes bounded adjustments; unbounded `dynamic` reports only the bounded portion. This is per-function information. [Official chapter](https://gcc.gnu.org/onlinedocs/gcc-7.3.0/gcc/Developer-Options.html); retained lines 647–669.

`-fdump-ipa-cgraph` describes call-graph optimization, removal and inlining; `-fdump-ipa-inline` dumps after inlining. `-flto-report` and its WPA variant expose version-dependent internals. Dump pass numbering is not stable. Optimization-info files can overwrite across translation units. `-save-temps=obj` bases ordinary intermediates on output names and avoids the documented shared-basename collision pattern. [Official chapter](https://gcc.gnu.org/onlinedocs/gcc-7.3.0/gcc/Developer-Options.html); retained lines 221–233, 334–354, 401–410, 514–547, 625–633.

Neither acquired chapter specifies complete AVR 7.3 post-LTO `.su` coverage, a final interprocedural stack bound, or exact LTRANS artifact naming. This developer chapter contains no `-fcallgraph-info` documentation. Absence is a coverage limit, not proof that the installed compiler rejects an option.

## Project-specific review requirements, not documented guarantees

A later proposal could retain the existing compile semantics and explicitly use `-Os -flto` consistently across eligible C units and the final GCC-driver link. It must identify the actual pinned LTO backend executables, plugin and dependencies from the retained toolchain/specs; these chapters do not enumerate that installed closure or establish its AVR configuration. Do not silently add whole-program assumptions, parallel make jobs, relaxed arithmetic, or different MCU/ABI options.

LTO can change inlining, function identity, register use and library interactions. A fat object's conventional disassembly and pre-LTO `.su` cannot establish the final LTO image's stack or timing. Retain actual final assembly/map and any generated backend stack/dump artifacts, account for every retained function, callback, library helper and ISR edge, and explicitly resolve missing entries. The prior combined-stack proof cannot be transplanted. If complete evidence cannot be obtained, report stack fit as unsupported even if linking succeeds.

Recheck vector retention, callback authority, volatile/register accesses, interrupt masking and UART handoff ordering against the generated final image. Preserve the existing stack/service allowances and native lifecycle controls. Any future build requires a separately reviewed bounded plan and owned-process/dependency accounting. No flash saving, linked fit or hardware behavior follows from this documentation review.
