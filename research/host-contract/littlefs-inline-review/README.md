# Bounded inline-file source review

Stage 95, 2026-11-09. This review uses the existing fully acquired littlefs
commit `6cb4e86540eca0d9ba62500a298385c9d863c8be`. The previous
[source packet](../littlefs-core/README.md) and its complete file index are
revalidated; no source is silently updated. One additional source,
[test_files.toml](test_files.toml), is newly read in full: 539 LF lines.
The cumulative selected coverage is twelve files / 12,580 LF lines, with
57 repository files still not claimed fully read. No upstream test runner runs.

The exact core, public header, design and specification were fully read in
Stage 83. [Reading coverage](reading-coverage.json) records this turn's narrower
re-reads separately from that prior full coverage. A browser request for the
pinned GitHub tree was unavailable; the retained, hash-verified acquisition is
the source used here. This is not a fresh upstream-version assessment.

The core limits an inline file by cache size, attribute size and one eighth of
the metadata block. The existing 4096-byte block and cache permit an explicit
512-byte limit. New or truncated files start inline; writes beyond the limit
outline their data. For inline files, sync stores the body as a metadata
attribute. Directory commit still flushes, synchronizes and checks its CRC.
This changes which native operations are needed, without removing an upstream
barrier or changing its implementation. See [source notes](NOTES.md).

The inspected earlier probe plans declared inline files disabled but did not
document a correctness defect requiring that setting. That limited finding is
not proof about all earlier notes or all inline behavior. The new
[isolated candidate](../../../artifacts/implementation/inline-hierarchical-store/PLAN.md)
changes one bridge initializer and an explicit hierarchy profile, retaining the
statx provider's full fsync of every backing chunk at every block barrier.
Small superblock, directory and entry records are plausible beneficiaries;
large file metadata and 4096-byte payload chunks remain outlined. Performance,
capacity fit and physical durability require their own evidence.

Primary source: the pinned [littlefs tree](https://github.com/littlefs-project/littlefs/tree/6cb4e86540eca0d9ba62500a298385c9d863c8be).
The upstream [BSD license](../littlefs-core/repo/LICENSE.md) remains retained.
