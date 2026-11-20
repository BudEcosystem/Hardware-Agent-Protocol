# littlefs suitability observations

Stage 83, 2026-11-09. The full pinned core, headers, utility implementation,
design, on-disk specification and three selected upstream test files have been
read. README/license match the prior fully read acquisition. The whole 69-file
repository is retained, but the remaining files are not claimed read.

Build only lfs.c and lfs_util.c with the original probe and the fully read headers.
Do not invoke the upstream Makefile, scripts, emulator or test runner. Four fresh
bounded child scopes observe a 4 KiB overwrite at either end of a 256 KiB file,
two simultaneously open handles after a sync, and unmount with a pending write.
Use a 2 MiB RAM block device with explicit aligned range checks and erased-bit
programming checks. Retain one 2 MiB image and raw output per scope. A separate
tiny native POSIX file supplies a local two-descriptor coherence comparison.

Each execution has a 20-second wall limit, 10-second CPU limit, 512 MiB address
space, 16 MiB per-file limit and 64 descriptors. The compilation has a 30-second
wall limit and 20-second CPU limit. Keep the finite retained experiment below
256 MiB. Fresh paths only, no retries or cleanup after failure. A timeout is
inconclusive; stop subsequent scopes if an execution or interpretation fails.
Verify all inputs before/after and the unchanged 244-file public baseline.

The experiment measures API behavior and callback counts, not SQLite performance,
hardware flash, FUSE semantics, physical power loss or production durability.
The RAM sync callback is deliberately only a counter. The unmount case is an
explicit demonstration of the documented release-only operation, not a claim
that normal close loses synchronized writes. Retained images are research data.
