# Pre-execution review

The exact littlefs core/design/specification/header were fully read in the
sealed core packet. This turn re-reads complete relevant file open, close,
relocate, outline, flush, sync, read, write, truncate and initialization paths,
and metadata commit/CRC, compact, split, relocate, orphan and commit paths.
test_files.toml is newly read in full. Prior plans disabled inline storage for
their declared probes; inspected notes do not document a correctness defect
requiring that choice. This absence is not proof of every inline behavior.

The current core bounds inline_max by cache_size, attr_max and one eighth of the
metadata/block size. With the existing 4096-byte block/cache and default metadata
limit, 512 is valid. The bridge supplies a full 4096-byte file cache and closes
each native file before returning. Its exposed reads/writes are whole-file
operations; the hierarchy retains shared logical inode ownership as before.

New/truncated files begin inline; a write whose resulting size exceeds the limit
outlines the data into allocated blocks. Inline sync commits the complete body
as a directory metadata attribute. It does not need the separate outlined-data
barrier, but metadata commit still runs the upstream CRC/flush/sync/readback path.
No upstream sync call, checksum or publication ordering is removed. Compaction
and splitting remain upstream behavior. Larger files retain the CTZ path.

The profile constant changes both anchor admission and the on-disk superblock.
Wrong anchors reject before opening the provider; wrong on-disk profiles reject
after read-only native mount and before inventory recovery. Dedicated controls
must verify no backing changes or recovery on these refusals. Native library
hashes remain explicit in every owner; the original profile is a separate
comparison baseline with its original binary.

All other Python/provider/native wrapper bodies are exact. The bridge diff is
one initializer value. The original native probe includes that exact bridge and
core, inspects lfs_file_t's inline flag, tests boundary transitions, and treats a
callback sync as a modeled durability snapshot. This is not a power-cut proof.
Comparison wrappers count actual provider fsyncs symmetrically. Changed disk
encoding means raw hashes are expected to differ across variants; each run's
own retained bytes must remain stable under independent audit.

The host cache footprint, disabled wear relocation, trusted-host ownership,
hash-before-dlopen prototype and lack of physical qualification remain explicit
limits. This is not an Arduino RAM or flash-endurance profile. Primary-agent
implementation review; separate evidence-audit preparation. A passing storage replay would still not
complete SQLite, aggregate reservations, prompt learning or real I/O providers.
