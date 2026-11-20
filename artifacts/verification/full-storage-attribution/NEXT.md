# Next storage hypothesis after attribution

Keep this as an intrusive diagnostic. Its paired screen preserves callbacks and
bytes, but the complete writer still misses its original deadline. Preserve all
failed images and receipts. Do not retry unchanged, extend limits, enlarge the
image, reduce the dataset, skip fsync calls or weaken current identity checks.

The measured prefix identifies full synchronization and provider verification as
large observed costs. The source shape gives a specific possible way to reduce
the amount of native work: every file inode currently serializes a full 512-byte
bitmap, making its wrapped metadata larger than the native inline limit even
for small files. Most hypothetical records sized to the declared file would
fit inline. Neither observation establishes the performance of a new format.

Review an explicit new disk profile that retains the existing full 512-byte map
in memory but serializes exactly enough bitmap bytes to cover the declared file
size. With 4 KiB payload chunks, the candidate length is
`ceil(ceil(size / 4096) / 8)`. It is bounded by the existing maximum file size.
Directory records and payload chunk size need not change. A single large or
sparse file may still need the full disk bitmap; it must remain supported.

Before implementing, read and map every bitmap consumer: canonical packing,
unpacking, inode validation, creation, pwrite and partial-chunk updates,
extension, truncation, recovery inventory, orphan cleanup, capacity accounting
and the independent reader. A new decoder must reject the wrong exact length,
noncanonical base64 and nonzero bits beyond the declared logical end. Padding
to the full in-memory map must not turn missing or invalid disk evidence into
valid data. A serializer must prove that discarded tail bits are zero. Do not
relax the current fixed-length validator or silently accept both formats.

Targeted controls need empty and sparse files; byte and bit boundaries around
7/8/9 chunks; growth and shrink across bitmap-length and inline/outline boundaries;
partial final chunks; the existing maximum file size; invalid lengths/tail bits;
and interrupted metadata publication with held handles and orphan recovery.
Wrong anchors/profiles must still refuse before recovery. Each observer/auditor
adaptation requires its own exact diff and retained-byte checks.

Only after source review and those controls should a candidate attempt run all
original provider/hierarchy checks and a paired semantic comparison, then the
unchanged 4,270-file / 169-directory writer and cold reader with original geometry
and limits. Physical encodings may differ across declared profiles, but each
retained image must remain byte-exact through read-only audit. Do not combine
this proposal with tracked synchronization or larger payload chunks without
separate evidence. No performance or service-storage adoption is established now.

A successful replay would still leave SQLite semantics, locking, interruption,
temporary-file confinement, pre-recovery caps, every-writer aggregate bounds and
actually backed control continuations to establish. Work on persistent endpoint
applications, concrete I/O/driver/hub providers, independent local stopping,
microscope commissioning, native Harness integration and remaining full-source
research remains part of the original goal.
