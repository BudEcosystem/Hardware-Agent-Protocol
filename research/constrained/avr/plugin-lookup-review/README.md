# GCC 7.3 linker-plugin lookup source review

This packet explains the preserved `-print-file-name=liblto_plugin.so` refusal in the separate standing-endpoint LTO build lane. It retains official upstream release-tag source, exact HTTPS acquisition metadata and a precise partial-file reading ledger. The relevant driver lookup/print/link functions and complete `collect2` main were read; neither whole-file reading nor exact downstream Arduino build-source identity is claimed.

[NOTES.md](NOTES.md) records the finding: ordinary file-name queries search start-file prefixes, while actual linking searches executable prefixes with `R_OK` and no multilib traversal. The `programs` search-directory output uses the same ordered prefix traversal as that lookup. Program-name queries use `X_OK` and are not substituted for plugin readability. The correction requires the first readable candidate to satisfy the existing archive/path/alias pins; it cannot skip an unexpected winner.

[SOURCE-COVERAGE.json](SOURCE-COVERAGE.json) records exact line ranges, file hashes and complete functions read. [acquisition.json](acquisition.json) records the three official URLs, response headers and bytes. `acquire.py` downloaded source data only; no acquired source or compiler was executed for this research. Compiler queries and attempted builds belong to the separately retained [LTO lane](../../../../artifacts/implementation/standing-endpoint-lto/README.md), with their own frozen inputs and process receipts.

The index seals these research bytes and scope. It establishes no plugin load, build success, target operation, stack bound or runtime fit.
