# Reading notes and implications

These notes cover the exact selected sources in [reading coverage](reading-coverage.json).
Source facts refer to the pinned local files. Proposed HMS behavior is a design
decision, not an upstream guarantee. Review was performed by the primary agent.

## Configuration and version

[lfs.h](repo/lfs.h) identifies software 2.11 and on-disk version 2.1. SPEC introduces
2.1 but retains a 2.0 statement in the superblock discussion; the exact core/header
defines the selected implementation. DESIGN describes an inline cutoff of a
quarter block; the current core limits it by cache size, attribute size and one
eighth of the metadata limit. The probe disables inline files explicitly.

Program/read sizes and cache/block relationships require validation. The core
asserts a minimum 128-byte block; the design's theoretical minimum is not a valid
configuration promise. Zero block_cycles is invalid; -1 disables wear relocation.
Many parameter and permission conditions use assertions. Any provider must reject
invalid profiles itself even when an upstream release disables assertions.

LFS_THREADSAFE locks a single API call. It does not make a seek-plus-read/write
sequence atomic or serialize an entire application transaction. Unlock callback
errors are not propagated. The original probe is single-threaded with assertions
enabled and all buffers provided by its caller.

## Data layout and allocation

[lfs.c](repo/lfs.c), particularly lfs_file_flush at line 3353, copies the unchanged
suffix when committing a non-tail overwrite of a CTZ file. The copy loop passes
one byte at a time through cached read/write helpers; it is not a separate device
I/O per byte. Switching from writing to reading or seeking can trigger a flush
before the eventual sync. Repeated random page writes may therefore copy suffixes
repeatedly; no whole-SQLite performance result follows from the source alone.

Old and new COW blocks coexist until the metadata reference changes. Logical
file size and SQLite page caps do not bound this transient physical allocation.
The fixed lookahead bitmap limits allocation memory, and checkpoint accounting
terminates an exhausted scan with NOSPC. Traversal and repeated allocation still
do not supply a hard application latency bound.

Metadata uses pairs of blocks containing appendable commits, compaction and
splitting. The approximate half-full metadata policy is not an unconditional
capacity reservation: degraded compaction can fill a pair when space is scarce.
Superblock expansion is not generally reclaimed. The filesystem's size query is
best effort and can count shared COW blocks more than once. A unique-block walk
can refine an observation, but neither observation reserves future capacity.

The metadata-cost plot illustrates rapidly increasing amortized update cost as
the log fills; the relationship is not a measured host benchmark. The file-cost
plot illustrates inline versus CTZ overhead with allocation discontinuities. The
wear plot illustrates dynamic spreading from randomized starts plus sequential
allocation; it does not establish uniform lifetime wear or static wear leveling.

## Sync, recovery and errors

File sync flushes data and orders device sync before publishing the new metadata
reference. Metadata commits have CRC checks and readback; FCRC checks the expected
erased program area. These are corruption checks, not authentication, ECC or proof
of the device's actual power-loss behavior. The configured block callbacks remain
part of the durability contract.

lfs_unmount_ at line 4655 only deinitializes. It does not synchronize open writes.
An adapter needs an explicit successful drain and sync sequence before a clean
shutdown receipt. A close after an earlier file error may free resources without
establishing fresh durability; error state is not a permanent provider poison.
The outer provider must retain uncertain outcomes and control its recovery policy.

Mount reads metadata and recovery state. First mutation can force consistency,
including pending move/orphan work or an older-minor superblock update. The explicit
mkconsistent operation also writes. Enforce provider bounds before either path;
do not admit new business operations before required recovery is settled. Never
format after a failed recovery mount. The upstream library does not autoformat;
some examples/tests choose that policy for their own fixtures.

Rename uses distributed move state and ordered metadata updates. This does not
create an application transaction across separate control and bulk domains.
Recovery may repeat after relocation. Fixed capacity alone does not bound recovery
time or implement an independent physical stop. Migration code was fully read as
part of lfs.c but was not enabled in the build. Grow, migration and implicit format
changes are excluded from the proposed fixed profile.

## File handles and POSIX gaps

Each lfs_file_t holds its own CTZ state, size and cache. Sync marks other handles
LFS_F_DUSTY at line 3491 without replacing their view. The allocation walk retains
dirty/dusty/writing blocks, allowing old handles to keep older data. A second writer
can branch from its own state; treating each POSIX descriptor as an independent
littlefs handle does not supply a coherent shared inode.

Removal updates open-handle metadata references. Do not infer POSIX retention of
every clean open-unlinked file from the presence of a handle list: the allocation
walk does not protect all such handles equally. An adapter needs explicit shared
inode ownership and retained backing until the last open reference is released.

The core does not supply POSIX inode numbers, uid/gid/mode/timestamps, advisory
locks, mmap/shared-memory semantics or an aggregate virtual inode budget. Attributes
can store adapter metadata, but read lengths can be padded/truncated; validate the
stored identity and exact size. The stock FUSE wrapper reviewed in stage 82 does
not discharge these obligations.

## Selected tests and local observations

test_interspersed.toml primarily interleaves distinct files, includes removal
while open and an emulator-driven reentrant append fixture. It does not establish
coherence for separate live handles to the same file. test_powerloss.toml exercises
revision and partial-program cases through the upstream emulator, including direct
memory mutation. test_exhaustion.toml explores wear/bad-block exhaustion and
superblock expansion. These sources were read; their harness/emulator was not run.
They do not establish backed continuation reservations for HMS.

The original [probe receipt](../../../artifacts/verification/littlefs-semantics/attempt01/observations.json)
records a 4 KiB overwrite in a 256 KiB file. At offset zero, it programmed 262,688
bytes with 65 erases; at the final 4 KiB, 4,640 bytes with two erases. Complete
file readback verified the intended changed page and all remaining original data.
This measures the declared RAM callback configuration, not flash latency or SQL.

After a writer synchronized 16 replacement bytes, the existing reader returned
the old A bytes while a newly opened reader returned B. The local native POSIX
two-descriptor comparison returned B through the existing reader. Unsynchronized
write followed by unmount made zero unmount sync callbacks; a fresh mount returned
the preceding A bytes. These observations agree with the fully read source.

Current HMS Journal and evidence-vault connections require DELETE journaling and
EXTRA synchronization; selected vault connections use memory temporary storage.
Only the relevant connection portions were inspected here, not those entire files.
The candidate must preserve the current contract. Switching to WAL or weaker sync
to accommodate a provider would be a separate, unqualified behavioral change.
