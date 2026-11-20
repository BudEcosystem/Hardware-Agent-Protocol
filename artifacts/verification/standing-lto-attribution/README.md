# Retained standing/LTO attribution

This source/data-only packet compares the sealed fit parent and failed LTO image. It changes no C source, runner, target, protocol or memory budget, and runs no compiler, binary inspection tool, probe, target or emulator. The two parent indexes were revalidated before parsing. Exact input hashes, source coverage, extracted instructions and reproducible stdlib text calculations are retained.

| Large section | Fit bytes | LTO bytes | Change |
| --- | ---: | ---: | ---: |
| Standing poll | 7462 | 7462 | 0 |
| Standing handle | 5816 | 5784 | -32 |
| Finite endpoint poll | 2874 | 2874 | 0 |
| Finite endpoint handle | 4976 | 4880 | -96 |

The four bodies total 21000 LTO bytes. Their 128-byte reduction is only part of the combined compiler-profile/root-policy reduction. The standing poll's complete instruction sequence is unchanged between the retained fat-object and LTRANS listings after local-label renumbering. Large single-caller inlining is not, by itself, duplicated code.

[STANDING-ATTRIBUTION.md](STANDING-ATTRIBUTION.md) records wide-value/serialization call sites, 896 bytes of emitted frame-address adjustments, a measured 96-byte duplicated observation-commit prefix, and two duplicated reader bodies totaling 82 bytes. [FINITE-ATTRIBUTION.md](FINITE-ATTRIBUTION.md) records the finite path and a concrete stack concern: the generated endpoint poll frame remains allocated while it calls the standing poll, contrary to the source comment's intended lifetime. [STANDING-HANDLE-REVIEW.md](STANDING-HANDLE-REVIEW.md) independently reviews the standing response/mutation body. These measurements identify bounded follow-up candidates; they are not net savings predictions or a solution to the remaining 9124-byte physical flash overflow.

[attribution.py](attribution.py) and [attribution.json](attribution.json) reconcile every instruction and embedded switch-table byte in the four extracted units to the failed map. [supplement.py](supplement.py) and [supplement.json](supplement.json) reproduce the normalized listing and exact duplicated-prefix comparisons. [standing-coverage.json](standing-coverage.json) and [finite-coverage.json](finite-coverage.json) distinguish complete source/function reads, complete instruction streams, selected dump ranges and computed-only evidence. The initial parser's explicit refusal on inline switch-table data is preserved under `analysis-history/attempt-1/`; the corrected parser accounts for those 32 bytes.

Any proposed implementation needs its own source and controlled-build review. No final ELF, complete stack graph, UART timing qualification, physical commissioning or durable hub/PAT completion is established here.
