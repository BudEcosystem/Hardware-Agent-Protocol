# Current private-adapter contract

This original candidate combines the unchanged stage 82 Linux/ext4 fixed block
provider, the exact stage 83 littlefs core and an original finite C/Python adapter.
It supplies coherent logical files over 4 KiB chunks. It does not expose POSIX
permissions, directories, locks, mmap, device nodes, FUSE requests or SQLite VFS
methods. No public service mounts it.

## Identity, ownership and layout

Fresh creation first creates a private fully allocated 16 MiB block image and
records its externally held object anchors. Reopen requires those anchors and
never formats. The fixed block layer retains its filesystem, owner, mode, link,
extent and replacement checks. The native library and block-source identities
are checked before loading in the trusted research process; this is not a hardened
untrusted-code loader or a hostile same-user confinement boundary.

One Python lock serializes the entire adapter operation; fork rejection precedes
the lock. A handle is an owner-session token plus a non-reused slot. It resolves
one shared inode record. All native file opens are temporary and closed on return,
so no separate stale littlefs file view crosses an adapter operation.

The namespace stores profile and image identity, monotonic next inode ID, and at
most 16 records containing ID, name (or unlinked state), size and an exact 4,096-bit
presence map. Its canonical JSON envelope includes SHA-256. IDs and names are
unique; names are flat bounded ASCII, file size at most 16 MiB, live handles at
most 64 and one transfer at most 64 KiB. Internal files are capped at 16 KiB.

Each inode owns a directory named from its ID. Its present data chunks each have
an exact 4 KiB length and an index encoded in the filename. A missing referenced
chunk refuses recovery. Absent map bits represent zero extents, not physically
reserved capacity. The namespace digest is a corruption check, not authentication;
end-to-end data checksums and media faults remain outside this candidate.

## Mutation and recovery

The namespace is written to state.tmp, synchronized, then renamed over state.
Creating an inode makes its directory before publishing the namespace entry.
An unpublished directory is an orphan to reclaim after a complete inventory check.
Write operations replace bounded chunks, then publish changed size/presence if
needed. Existing chunks can change independently; a multi-chunk write is not atomic.

Shrinking publishes the reduced size/map before removing obsolete chunks. Growing
first zeroes any truncated tail still present in a retained last chunk. Unlink and
rename-over-target remove the old name while retaining the old inode for open
handles. Final-reference release removes the namespace record before reclaiming
its files. After owner loss, there are no inherited valid handles; recovery removes
ownerless unlinked records and unreferenced chunks/directories.

Reopen validates all bounded namespace and directory entries before the first
adapter recovery mutation. It does not reinterpret missing referenced chunks as
zero, adopt unknown names, repair malformed metadata or format failed storage.
The underlying littlefs first-writer consistency work remains part of the future
interruption and latency qualification; this adapter does not establish a bound
on that work merely by limiting storage capacity.

Invalid requests are refused before storage I/O. Filesystem and callback errors
poison the owner; all later operations refuse until a new owner reopens. Partial
effects remain possible and retained. Release without a clean-close receipt is
explicitly separate from a successful drain/sync. Closing with live handles is
refused; deliberate resource disposal preserves their orphan records for recovery.

## Boundary to the requested system

This is a real persistent provider slice, not a substitute for the full service
profile. Its flat namespace and current caps do not yet cover every worker,
temporary file, code image and database side file. The final profile must place
all writers inside enforced aggregate bounds, with backed remaining control
continuations, limits before startup mutation and control-only recovery when bulk
evidence is unavailable. It must preserve the current SQLite DELETE/EXTRA contract.

The storage interface is one hub resource in the unified device/driver/hub graph.
It changes no public runtime method, learned PAT selection, physical endpoint,
driver or hub lifecycle provider. Endpoint firmware and immutable PAT-package
storage need their own qualified profiles and outage behavior.
