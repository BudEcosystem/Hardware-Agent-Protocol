This packet is source/data-only. No compiler, target, candidate, candidate import, existing Python reader or new reader was executed. Standard read/copy/hash/text-query tools were used. Two TSV/JSON projections use jq directly against the already sealed measurements; they introduce no new generated-code parser or new build result.

Parent index SHA: `b80a6ec4119dd822bfa451929e7fba4f7994f9fca27134eb9361c88785f63dd6`. Continuation106 receipt SHA: `be776f2d1bce37cd8adf88508f45f9fe7d060f782483fa74f35c3a38cb6e54ad`. Ordinary `jq -r '.files[] | "\(.sha256)  \(.path)"' index.json | sha256sum -c --quiet -` from the parent directory checked all852 indexed byte hashes successfully. This check does not itself inspect a running device or execute the indexed files.

Thirteen exact local input copies are retained below inputs, preserving their original workspace-relative paths. [inputs.sha256](inputs.sha256) pins those copies; the source values also match the immutable parent where applicable. The avr-libc header is from the already restored, archive-derived private toolchain; this continuation read and pinned the header but did not repeat archive extraction or execute toolchain programs.

| Fully read source in this continuation | Lines |
| --- | ---: |
| endpoint.c | 1–643 |
| endpoint.h | 1–143 |
| standing.c | 1–745 |
| standing.h | 1–85 |
| endpoint_kernel.c | 1–225 |
| endpoint_kernel.h | 1–68 |

Those six files total1,909 lines. The current parent RESULTS, CODEGEN-REVIEW and codegen-review.json were read completely. The prior phase-size PROPOSAL was read completely as historical scope, not as a restriction silently extended to this new descriptor proposal. No broader full reading of the workspace or all toolchain source is claimed.

Manual generated assembly coverage uses the parent's `build/avr/compiler-tmp/ccyhFurg.ltrans0.ltrans.s`, SHA `e78c50ce5dbae980a41a1fc0fe2fedf59060da8dc0c0ceb0aba2b3187bfef5db`:

| Lines | Complete bodies read; extra adjacent lines do not imply more complete bodies |
| --- | --- |
| 9088–9360 | admission_times; only the beginning of context_matches follows |
| 11895–12416 | standing describe, write_control, write_hello |
| 13842–13977 | write_receipt |
| 15462–16644 | handle_finite |
| 20350–21428 | open_record |
| 25545–26941 | hms_standing_handle |

Complete current standing poll/loss/acquisition/transition source was read; the full manual generated review of those bodies is the explicitly retained parent CODEGEN-REVIEW/codegen-review.json, not a claim that their complete assembly was reread here. Whole-function sizes, static transfers and owner totals come from the sealed complete inventory. The raw map remains SHA `12336960e81dbb8d6dd998ea2d061fabb5db1df8a509a1bd8d9a50585610328c`; backend .su remains `882f38944c3d9cd56dbdd411e20c6f5c45f0657cb291aae75966bc73df0ad525`. They were pinned, not regenerated.

The copied1,791-line avr/pgmspace.h has SHA `5e8af74a13ecaf167738a51d5c1179d523d35057fc13d4ac0114e07f41c50f45`. Read ranges:44–125 (program-space contract and PROGMEM definition),408–452 (complete byte LPM alternatives),608–646 (selection and near-byte macro),1040–1057 (ordinary byte alias). All other header contents are retained but not claimed read. These definitions support the proposed flash-table mechanism; they are not generated-code proof of its future selection, placement or size.

[function-inventory.tsv](function-inventory.tsv) is a direct146-row projection of the existing measurements: name, address, bytes, emitted owner, first/last assembly line, local bytes, saved-register bytes, backend .su bytes. It was produced with:

```
jq -r '.current.emittedFunctions[] | [.name,.address,.bytes,.emittedOwner,.firstLine,.lastLine,.frameLocalBytes,.savedRegisterBytes,.backendFrame.bytes] | @tsv' codegen-measurements.json
```

[direct-call-counts.json](direct-call-counts.json) is the exact jq projection `.current.directCallCounts`. Calls are static sites from that retained reader, not execution frequencies. Both projections are convenience views; original fields, range hashes, aliases, all146 bodies, allocated sections and30/9 retained roots/storage remain in the copied complete measurements.

The source catalogue is manually specified; no implementation, row generator, table validator, test runner, result claim or seal has been created here. The next review must check literal C rows and actual call-site substitutions against these source locations before executing a candidate.
