# Findings and design consequences

Primary-agent full reading, 2026-11-09. No independent review is claimed.

## Allocation and persistence contracts

The installed `posix_fallocate(3)` manual describes allocation of the requested
range and the resulting protection against later lack-of-space write failures
within that range. Its glibc emulation warning matters: emulated allocation can
race concurrent changes and is not a general-purpose confinement mechanism.
Our candidate restricts creation to fresh private regular files on the observed
Linux/ext4 mount, preallocates each complete chunk, writes every byte, syncs it
and checks size/allocation. It does not silently substitute sparse allocation.

The `pread(2)` manual permits positive short transfers. Positional I/O avoids
shared descriptor cursor state, but Linux `O_APPEND` would defeat the requested
write offset. The original implementation uses no append mode, loops over
positive progress and treats zero progress as failure. These choices directly
address the stock littlefs block wrapper's cursor and nonprogress behavior.

The `fsync(2)` manual distinguishes file synchronization from persistence of the
containing directory entry. Creation syncs the owner, every chunk, manifest,
image directory and parent. A later explicit sync flushes all data chunks.
Closing is not a sync receipt. Device-reported completion is an assumption of
this host profile; neither the source reading nor injected errors qualify actual
power-loss behavior. Partial writes remain partial state after an error.

## littlefs candidate and stock wrapper

The upstream README describes a filesystem designed for power-loss resilience,
bounded memory and flash use. Its block contract supplies read, program, erase
and sync callbacks. File updates commit at sync/close, and the underlying sync
must actually flush cached data. These are upstream claims and interface
requirements; we have not yet reviewed the core algorithms or established HMS
host, SQLite, recovery or timing compatibility.

The README example formats after a failed mount. HMS must distinguish explicit
fresh installation from recovery: a mount failure must preserve existing state
and refuse, never erase unknown operation history by formatting automatically.
The separate retained image identity and external object anchors are intended
to support that distinction, but trusted installation publication is unfinished.

The complete stock FUSE wrapper uses API 26, while the retained host probe uses
libfuse3 API 31. It reports permissive fixed modes; chmod and timestamp calls
return success without persisting the requested metadata. Directory iteration
ignores its offset and filler stop result. Allocation paths call memset after
malloc without first checking for failure. A truncate error path leaves its
file handle open. Release delegates close, whose error is not a reliable client
durability acknowledgment under the FUSE contract reviewed in stage 81.
Reported free space does not implement inode admission or backed continuations.
These facts preclude adopting this wrapper unchanged for the current contract.

The complete stock block wrapper opens a supplied path read/write and can use
block-device ioctls to infer geometry. Its block-index assertion does not enforce
the full offset/length range and can disappear in assertion-disabled builds.
It uses lseek followed by read/write loops; zero-length read progress becomes an
error, but a zero-progress write can loop. An ioctl failure during initialization
can leave the descriptor open. Erase is a no-op and sync calls fsync. Our original
layer is a separate host implementation with explicit range checks, object
ownership, progress checks and fixed initialized backing. It is not a validated
littlefs integration or a model of physical flash programming constraints.

## fuse2fs candidate

The entire 5,841-line implementation was read, including startup, permissions,
inode and directory operations, I/O, extended attributes, ioctl/fallocate,
argument processing, teardown and error translation. Its internal lock
serializes libext2fs access. Writable mount may replay an existing journal, but
the source explicitly warns that it does not use the journal for new writes and
that ungraceful termination can cause corruption or data loss. Replaying prior
transactions therefore cannot establish crash-safe new control transactions.
This is sufficient to withhold adoption for the required control profile.

The allocation guard retains filesystem blocks and comments on problems at full
allocation. The environment can explicitly bypass that guard. Statfs exposes
block and inode availability; it does not assign guaranteed remaining capacity
to admitted HMS operations. Rename performs several separate updates, including
removing an existing destination before completing the new linkage. We infer
that the general rename interface alone cannot supply our missing crash contract;
no crash execution or library-wide correctness proof was performed.

Read/write and metadata paths translate errors with filesystem state changes.
The fsync handler flushes the filesystem for writable handles; some release and
shutdown paths have different flushing/error behavior. Directory fsync is bound
to the same handler, so actual directory durability semantics would require
specific qualification. It is insufficient to rely on a callback's name or a
successful process exit. Main also maps some post-initialization FUSE exits to
success. Teardown and receipts must be independently checked.

The implementation supplies real permission, ACL, timestamp, inode and attribute
handling, but this full file read does not cover all libext2fs dependencies.
Its optional kernel-like mode enables other-user access, setuid and devices.
That is outside the private noexec/nosuid/nodev host experiment. No fuse2fs binary,
image mount, driver, package installation or acquired controller was executed.

The supplemental manual documents read/write image mounts, directory flushing,
error policies and journal-recovery options. Its version differs from the
installed package. The pinned source, rather than this manual alone, establishes
the no-new-journal finding.

## Consequence for devices, drivers and hubs

Prompt-to-PAT execution needs durable operation identity for all three domains.
A hub storage provider must preserve ownership, dependency generations, original
requests and unresolved effects through crashes. Model training/evidence growth
must not consume capacity needed to settle admitted control operations. Finite
backing is one prerequisite; virtual inode limits, open-unlinked accounting,
every-writer confinement, transaction recovery and control reservations remain.

Before any littlefs integration, fully acquire/read its core, public/configuration
headers, design, specification and selected dependencies at the retained commit.
Decide explicitly whether its semantics can support the selected SQLite profile,
especially lock behavior, rename, sync, errors, open-unlinked files and recovery.
If not, reject that combination. A general filesystem wrapper is not mandatory;
the interface choice must follow the qualified storage contract. Keep physical
device stopping independent of the hub, filesystem daemon and model service.
