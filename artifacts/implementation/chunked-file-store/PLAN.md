# Shared-file and chunk adapter gate

Stage 84, 2026-11-09. Implement the next candidate selected by stage 83 over the
exact reviewed littlefs core and stage 82 fixed block-image implementation. Keep
the public runtime unchanged. This is an original private single-owner adapter,
not a mounted filesystem or SQLite VFS.

The native bridge exposes finite whole-file operations with no persistent
littlefs file handles. Python owns one shared inode record per logical file,
serializes complete operations and uses bounded 4 KiB data chunks. A checksummed
namespace is replaced through a synchronized staging file and atomic littlefs
rename. Stable inode IDs separate unlink/recreate and rename-over-open-target.
Unlinked backing remains until the last reference closes. Mount validates the
whole bounded inventory before recovery mutation and never formats on failure.

Profile: 16 logical inodes, 64 live handles, 63-byte flat names, 4 KiB chunks,
16 MiB maximum logical file size, 16 KiB maximum internal file, 16 MiB fixed
backing per fixture. Sparse logical extents are zero-filled; they are not backed
reservations. These feasibility limits are not the final qualification-service
capacity profile. Writes may have partial effects on error; poison blocks new
operations until the owner is replaced and recovery runs.

Each inode includes an exact 4,096-bit chunk-presence map in the checksummed
namespace. A missing referenced chunk is corruption, not a sparse zero extent.
Unreferenced staged chunks are reclaimed only after full inventory validation.

Six fresh scopes: shared descriptor/data semantics; namespace and retained
unlinked files; actual owner-process exit and cold recovery; 256 KiB update-cost
and block accounting; logical caps and invalid inventory refusal; injected sync
failure and poisoned-handle refusal. Each uses one 16 MiB image. Scope wall limit
60 seconds, CPU 40 seconds, address space 512 MiB, 128 descriptors and 16 MiB per
file. Compiler wall 30/CPU 20 seconds. Parent retains inputs, process handles,
stdout/stderr and terminal outcomes, stops after the first failure, and never
retries unchanged work. Total original retained fixture inventory below 256 MiB.

Freeze exact sources before building. Execute no upstream Makefile, scripts,
emulator or test harness. All acquired compiled dependencies were fully read in
stage 83; the original fixed block provider was read again before this change.
Inspect the actual retained state and verify the unchanged 244-file runtime
baseline after execution. Do not rerun the unchanged 866-test public suite.

Unfinished gates remain: actual disk/metadata exhaustion, interrupted namespace
mutation matrix, service-writer confinement, locks and directory durability at a
FUSE/VFS boundary, current SQLite DELETE/EXTRA recovery, backed continuation
capacity and physical power loss. A passing private adapter is not completion of
the service or the device/driver/hub and prompt-to-PAT goal.
