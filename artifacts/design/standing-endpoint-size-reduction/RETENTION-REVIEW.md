# Stronger retained-address evidence

This is a narrow strengthening of the source/data-only measurement script, not a correction to missing generated fields. The previously frozen `measure.py` SHA `217d6355aee7f2f8621f2da635e1c4cb2d32124d537d9eac65a41e8fd7afb9ec` already checked symbol presence/storage sizes and emitted `function_roots_plus_main_present=30` and `charged_storage_roots_exact=9`. Root's initial concern came from associating an earlier script read with the later hash; both parties reconciled the current source. No fields had been manually added to the measurement output.

The previous script, measurements, coverage and evidence receipt are preserved byte-for-byte in `history/pre-retention-address-join/`. [retention-address-join.diff](retention-address-join.diff) contains the complete script delta. No original input or sealed parent file changes.

The stronger script requires unique retained names, exactly one allocated section and symbol line per root, matching symbol/section start addresses, positive sizes contained in the aggregate `.text` or `.bss`, non-overlapping root allocations, exact nine-object storage sizes, and their total equal to the aggregate1,477-byte `.bss`. The existing thirty function symbols include `main`, whose allocated section is `.text.startup.main`.

Its two new generated arrays, `function_root_allocations` and `charged_storage_allocations`, retain names, sections, addresses and sizes. All sixteen prior top-level measurement fields remain identical; `coverage.json` remains byte-identical. The unchanged counts are now backed by the stronger joins. This is still failed-map text evidence, not a linked ELF or complete resource/stack proof.

The strengthened stdlib-only analysis passed, and a second invocation is checked for exact reproduction of both complete JSON outputs in `reproduction.json`. No candidate code, compiler, inspection binary, emulator or device ran.
