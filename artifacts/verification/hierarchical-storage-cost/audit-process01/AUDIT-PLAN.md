# Read-only diagnostic audit

Run one independent process under 60-wall/40-CPU seconds, 512 MiB address space,
128 descriptors and a 16 MiB per-file limit. Freeze this audit, its runner and the
exact stage-91 retained-reader source. Import only the reader definitions, point
them at the byte-identical frozen binary, and inspect both original images using
read-only descriptors and original host anchors. Write, erase and sync callbacks
remain forbidden; no adapter recovery or SQLite runs.

Reconstruct all forty complete bodies and twenty directories independently,
compare both modes' image hashes and per-operation callback deltas, and verify
that exclusive span sums partition each phase's logical inclusive time. Check
the callback-to-verification, mount-check and eight-chunk fsync count identities.
Retain counts and overlapping inclusive/exclusive times separately. The result is
an intrusive local attribution screen; it proves neither a production speedup nor
the complete workload's timing or capacity. Preserve any audit failure.
