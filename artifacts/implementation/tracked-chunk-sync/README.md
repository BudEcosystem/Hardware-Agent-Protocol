# Tracked chunk synchronization candidate

**221 focused controls pass, but the complete writer still exceeds its original
180-second deadline. The candidate remains isolated and uninstalled.**

The explicit `hms.block-image.linux-ext4.tracked-sync/0.1` profile conservatively
tracks which chunks need full fsync. Every open starts with all chunks pending.
Nonempty reads and writes set the relevant bit before transfer; reads count for
possible access metadata. Sync fully fsyncs pending chunks, checks deferred
writeback errors on each untouched chunk, and always finishes with full fsync
on chunk zero. Bits clear only after the entire operation succeeds. All creation
syncs, current mount checks, ownership and allocation checks, range guards, locks,
fork checks and failure poisoning remain in place. Close remains distinct from sync.

The native wait helper uses `sync_file_range` with WAIT_BEFORE|WAIT_AFTER only.
That call does not provide crash durability and never substitutes for full fsync
on a pending chunk. Admission checks that it is supported. The [source review](../../../research/host-contract/chunk-sync-source/README.md)
fully reads six primary source/document files (1,591 LF lines) and selected
complete filemap bodies, with unread ranges explicitly recorded. References are
upstream Linux v7.0, glibc 2.39 and pinned man-pages, not an audit of host binaries.

Passing scopes: **9 native helper controls**, **52 original mount controls**,
**24 original provider tests**, **40 new synchronization controls**, and **96
original hierarchy controls**. The new controls cover initial/cold sync, payload
read metadata, empty and invalid operations, short writes, deferred errors on
untouched files, failure after partial sync, clean-barrier failure, interrupts,
unsupported admission and descriptor cleanup. An independent generation model
checks 120 operations and 49 acknowledged barriers against actual fsync events.
This models ordering, not physical power loss. Seven raw fixtures retain all
failed state; none is reopened through the provider or repaired.

The paired screen uses identical lightweight call counters and the same 40 files,
623,624 bytes, 20 directories and fresh 128 MiB geometry. All **426 logical
operations**, per-step filesystem callbacks, full bodies and filesystem chunk
bytes match. The provider manifest changes only its explicit profile.

| One paired local screen | Prior statx provider | Candidate |
| --- | ---: | ---: |
| CPU seconds | 3.845989 | 3.663372 |
| Wall seconds | 9.818207 | 8.774409 |
| Full fsync calls | 13,724 | 3,467 |
| Whole-file wait/error calls | 0 | 10,259 |

The candidate total includes two additional owner-admission probes. Each block
sync still observes every backing chunk; there is no dropped durability barrier.
The large reduction in full fsync calls produces only a modest local timing
change. This does not establish a production speedup or explain the remaining
full-workload cost. The paired counters themselves add overhead in both variants.

The complete writer retains all **4,270 files / 35,508,922 bytes**, 169 directories,
eight 16 MiB chunks and the original 180-wall/120-CPU limits. It is killed and
reaped at **180.093973 wall seconds**, using **46.299746 CPU seconds**. It reports
no capacity error; capacity fit remains unknown. The dependent full cold reader
does not run, and there is no unchanged retry, resized geometry or repair.

The [independent read-only audit](EVIDENCE-AUDIT.json) reconstructs **21 filesystem
images** and separately verifies **seven raw fixtures / 13 chunks** under their
original anchors. It verifies **1,323 complete files / 5,945,432 bytes** and all
169 directories in the interrupted writer image. No extra published file,
incomplete physical inode, pending entry or unlinked inode is observed. The audit
passes in **5.614363 wall seconds**; every backing byte stays unchanged. Adapter
recovery, SQLite, mutation callbacks and actual mount changes are excluded.

The hierarchy, littlefs binary and statx helper are unchanged; the new wait-helper
hash is `12a4afa4f359454333e3daa6ae0a5cde424a988bb8adfddf2822e2caeb88fdbb`.
All 244 public files still match the existing 866-test receipt; that unchanged
suite is not rerun. Prior seals remain exact. Primary-agent review, with no helper
agent available. See [next work](NEXT.md); full service storage, prompt learning
and actual device/driver/hub qualification remain unfinished.
