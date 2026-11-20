# Compact bitmap hierarchy candidate, Stage 97

This is an isolated, unexecuted candidate derived from the exact sealed Stage 95
inline hierarchy. Stage 96 identifies expensive synchronization/provider checks
in an observed prefix and separately calculates that 4,269 of 4,270 hypothetical
short-map inode records could fit the existing 512-byte native inline threshold.
Those observations motivate this format experiment; they do not predict its
runtime or establish an end-to-end success.

The new declared profile is `hms.hierarchical-chunk-store.compact-bitmap/0.1`.
File inode state serializes exactly `ceil(ceil(size / 4096) / 8)` bytes of bitmap,
encoded as canonical base64 inside the unchanged canonical/checksummed envelope.
An empty file has an empty disk map. The memory representation stays exactly
512 bytes. Encoding validates the full map, proves discarded bytes and unused
high bits zero, and packs a shallow copy; the caller's inode is not modified.
Decoding validates strict integer size before length arithmetic, exact schema,
exact encoded/decoded lengths, canonical base64 and unused high bits before
padding. A wrong-length map is never repaired by padding. The previous profile
is refused at the anchor/superblock gates. No migration or dual-format admission
is included. Directory schema, native payloads, ordering and recovery stay exact.

The source review fully read all 472 lines of the baseline hierarchy, 573 lines
of its base and 215 lines of its independent reader. `source-reading.json` joins
these reads to source hashes and revalidation of the Stage 95 seal (340 files,
812,410,778 bytes, one explicit symlink) and the Stage 96 seal (96 files). The
consumer mapping and independent reader differences are in REVIEW.md and the
retained patches. Native and provider sources/binaries are unchanged: 4 KiB
payload chunks, 512-byte native inline limit, full current fsync barriers and
statx-backed identity checks. Each image is at most eight 16 MiB chunks.

Before any execution, review all sources and diffs. `run_scopes.py` then creates
one new attempt, freezes exact inputs, revalidates all original data and public
244 files, and uses the exact Stage 95 native/mount binaries. Its unchanged 12
native cases / 1,294 assertions are hash revalidated, not re-executed. It runs:

- Original 52 mount checks and 24 provider tests; eight profile checks adapted
  to refuse the immediately preceding inline profile.
- Four targeted scopes (77 codec, 27 edge, 12 corruption and 33 interruption checks): independent codec vectors and malformed maps; real
  empty/sparse/7-8-9-chunk/maximum-size and inline-size crossing cases; three
  checksum-valid corrupt disk fixtures; four interrupted publication/write/
  shrink cases with a second held handle and recovery only on exact-byte clones.
- All original nine hierarchy scopes, unchanged, totaling 96 checks.
- The original 40-file / 426-operation coarse screen on both profiles. Logical
  result fields and full expected bodies must match. Callback counts and raw
  encodings may differ. Both still require the original full provider fsync
  relation; the candidate is not expected to preserve callback counts.
- The exact original 4,270-file, 169-directory, 35,508,922-byte writer and separate
  cold reader, each with 180 seconds wall and 120 seconds CPU. No reduced data,
  extended deadline, alternate order, or unchanged retry is authorized.

Focused children retain the prior 60-second wall / 40-second CPU bounds. Every
child has 512 MiB address space, 128 descriptors and 16 MiB per-file limits; core
dumps are disabled. The runner records process-group launch, monitors exit with waitid WNOWAIT,
keeps its owned unreaped leader as the group-signal anchor, then uses wait4 to
reap and retain CPU/RSS. Timeout, monitor exceptions and SIGTERM use this same
cleanup. It never signals a numeric group after reaping and requires a read-only
post-reap absence check. It saves exit/CPU/RSS receipts and stops at first failure. The
cold reader runs only after the complete writer succeeds. Images and partial
progress survive failure. Total retained stage allocation must remain below
1 GiB; the new target fixtures add twelve 16 MiB images (192 MiB). Nothing is
installed into the public runtime.

Independent retained-byte audit is a separate reviewed, bounded action after
results exist. `retained_reader.py` is a library with no old standalone audit
main. Its read-only provider/native wrapper imports are unchanged. It never
constructs a hierarchy adapter, invokes its recovery, or permits program/erase/
sync callbacks. Profile/bitmap encoding is explicitly selected. Compact maps
normalize to full memory-shaped maps only after strict wire checks. The separate
expected-corruption helper checks exact intentionally malformed states and
sentinels without interpreting those maps as valid. Every read keeps backing
hashes unchanged. A later audit must join receipts, exact bodies, prefix progress
if incomplete, corruption expectations and original/clone lineage; merely
importing this reader or passing focused controls is not that audit.

No physical power-loss, POSIX mount, SQLite compatibility, concurrent-writer,
service-storage adoption, or hardware I/O claim follows from this candidate.
