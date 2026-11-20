# Pre-execution review and durability argument

Primary sources are in `research/host-contract/chunk-sync-source`: complete
Linux fs/sync.c and ext4/fsync.c, complete journal documentation and fsync manual,
complete glibc fsync/sync_file_range wrappers, and the relevant complete filemap
write/wait/error bodies. Unread filemap ranges are recorded separately. These
upstream revisions are references, not a binary audit of the running Ubuntu host.

The invariant is conservative: a clear bit means this owner's chunk has crossed
a successful full fsync and no subsequent nonempty payload read or write has
occurred through the provider. Every chunk begins pending on every open. A bit
is set before transfer, not after a successful return, covering short writes and
interrupts. Reads count to cover their possible access-metadata changes. The
existing mutex encloses verification, bit updates, I/O and synchronization.
Invalid ranges remain outside that path and do not change state.

A successful sync fully fsyncs each pending chunk, then clears all bits only
after the entire operation succeeds. Chunk zero is always fully fsynced last,
including a clean barrier. Each other clear-bit chunk receives a whole-file
sync_file_range WAIT_BEFORE|WAIT_AFTER call. The reviewed kernel route waits for
writeback and checks/advances that descriptor's error sequence. It does not flush
disk caches or metadata and is never treated as durability for a pending chunk.
glibc routes the operation to the appropriate Linux syscall; unsupported calls
refuse admission. The helper rejects invalid descriptors and propagates errors.

Thus every acknowledged payload generation is covered by full fsync since its
last write. Retaining an untouched file's error check avoids the naive design
that simply skips such files. The final full fsync retains the ext4 emergency,
journal and device-flush path at each successful barrier. Creation still fsyncs
all chunks, owner, manifest, root and parent exactly as before. No fdatasync,
background acknowledgement, deferred barrier or writeback-only durability is used.

Synchronization order changes to chunks 1..N-1 then chunk zero. Any observed
exception still poisons the owner; partial progress does not clear bits and
cannot be retried through that owner. This is not a claim that identical errno
races occur under arbitrary concurrent kernel or external-file changes. Backing
files remain under the existing trusted-host/exclusive-owner model; foreign
payload or metadata writers are outside it. Failure receipts and physical power
loss still need their separate qualification. The wait helper uses the existing
private hash-before-dlopen convention, not a newly qualified public native loader.

Source diff review: explicit profile/import/wrapper; initialization of one bounded
integer mask; an admission probe; mask updates inside read/write; and the sync
selection loop. All mount, ownership, inventory, allocation, metadata, range,
fork, lock, poison and close bodies otherwise remain exact. The hierarchy/base,
native littlefs and mount helper remain exact. Comparison instrumentation counts
actual provider fsync and wait calls through identical wrappers in both variants;
it does not suppress them. Primary-agent review; helper quota remains unavailable.
