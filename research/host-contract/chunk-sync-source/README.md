# Synchronization path review

Pinned primary references: Linux v7.0 commit
`028ef9c96e96197026887c0f092424679298aae8`, Linux man-pages commit
`adb436b2e4471218021d86f188fb58dec3946eb8`, and glibc 2.39 commit
`ef321e23c20eebc6d6fb4044425c00e6df27b05f`. URLs and exact file hashes are in
`sources.json` and `glibc-sources.json`. Downloads and a separate shallow filtered
canonical glibc object store are retained; acquired code was not executed.
The earlier sealed glibc object store was not changed.

Complete reads: Linux fs/sync.c (381 LF), fs/ext4/fsync.c (189),
Documentation/filesystems/ext4/journal.rst (761); man/man2/fsync.2 (198);
glibc sysdeps/unix/sysv/linux/fsync.c (29) and sync_file_range.c (33).
These six full reads total 1,591 LF lines. Linux mm/filemap.c is acquired in full
(4,751 LF), but only lines 335–805 are read. This includes complete writeback,
wait and error routines; surrounding partial bodies are not counted as full
function reads. The remaining filemap ranges and remaining repository sources
are unread. This is not an audit of the running Ubuntu kernel or libc binary.

The fsync manual describes data and metadata flushing, device-cache flushing and
blocking until completion. Parent-directory durability still needs a directory
fsync. It explicitly describes deferred per-file writeback errors. The provider's
creation path already synchronizes owner, chunks, manifest, root and parent;
this candidate leaves that path exact.

Linux vfs_fsync covers the entire file and dispatches to the filesystem fsync
method; full fsync also calls sync_lazytime. ext4_sync_file checks emergency state,
handles no-journal and journal configurations, writes/waits for file data,
commits relevant journal metadata, issues a device flush when required, and
checks/advances file writeback errors. A generic assumption that a previously
clean file can simply be omitted would remove its deferred-error observation.

The reviewed sync_file_range WAIT_BEFORE and WAIT_AFTER paths reach
file_fdatawait_range, which waits for writeback and calls
file_check_and_advance_wb_err. The latter compares the descriptor's saved error
sequence to the mapping's current sequence, advances it under the file lock and
returns any error. The helper must propagate that error; ignoring it after
advancing the sequence would lose evidence. Neither wait flag flushes metadata
or disk caches. Even the WRITE combination is explicitly not sufficient for
crash durability. No such call may substitute for a pending file's full fsync.

The glibc fsync wrapper invokes the Linux syscall with cancellation support.
sync_file_range selects the architecture's sync_file_range or sync_file_range2
ABI, preserving offsets, length and flags. The candidate compiles against local
headers, requires 64-bit off_t, records compiler/header identities, validates
arguments and return values, and probes the actual syscall during admission.
Unsupported operation is a refusal, not silent emulation.

Candidate inference: under the existing exclusive-owner/trusted-host profile,
a chunk with no payload reads or writes since a successful full fsync has no new
provider-generated data or access-metadata obligation. Every open begins with
all chunks pending. Setting bits before nonempty reads/writes and clearing only
after a wholly successful barrier preserves that implication. Each other chunk
still receives its writeback error check. A full fsync on chunk zero finishes
every barrier. This is the basis for testing a narrower synchronization selection,
not a proof of physical power-loss behavior or protection against external writers.

The journal document is fully read, including journal layout, checksums,
revocation, commit records, fast-commit replay and checkpoint behavior. Its
idempotent reconstruction discussion also reinforces the distinction between
replaying stored outcomes and blindly repeating physical actions. No journal
checkpoint ioctl, mount change, administrator action or power interruption is
performed here. Further kernel journal/device paths remain outside this packet.
