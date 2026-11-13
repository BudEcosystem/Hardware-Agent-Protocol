# FUSE host storage boundary

The complete selected packet was read: **12 files, 4,378 LF lines**. These are
the libfuse 3.14.0 public high-level API and included headers, its example and
license material, two installed manuals, and Linux v6.8's FUSE overview. This is
not a claim to have read the entire libfuse or kernel implementation. Sources,
byte counts and SHA-256 identities are in [sources.json](sources.json).

The libfuse release tag resolves to commit
`3f65bb699cd2f0afe2b9519c39d29922229f2168`. The installed distribution library and
helper identify as 3.14.0 (`3.14.0-5build1` packages). Matching the release's API
does not attest that the upstream tag reproduces the distribution binary. The
installed kernel is 7.0.0-42-generic; the retained v6.8 document supplies framework
semantics, not complete documentation or source attestation for that kernel.

| Fully read source | LF lines | Notes |
|---|---:|---|
| [fuse.h](include/fuse.h) | 1326 | Callback and lifecycle contracts; original probe API |
| [fuse_common.h](include/fuse_common.h) | 934 | Capability negotiation, cache modes, request limits, signals |
| [fuse_opt.h](include/fuse_opt.h) | 271 | Option ownership and parsing; no caller-supplied options in probe |
| [fuse_log.h](include/fuse_log.h) | 82 | Logging API and lifetime |
| [include/meson.build](include/meson.build) | 4 | Installed public-header list |
| [hello.c](example/hello.c) | 179 | Read-only API usage; retained for research, not compiled or run |
| [LICENSE](LICENSE) | 13 | Distribution's license map |
| [LGPL2.txt](LGPL2.txt) | 502 | Retained complete license text |
| [GPL2.txt](GPL2.txt) | 339 | Retained complete license text |
| [fusermount3 manual](installed/fusermount3.1) | 44 | Helper and unmount interface |
| [mount.fuse3 manual](installed/mount.fuse3.8) | 258 | Permissions, options, cache and helper behavior |
| [Linux FUSE overview](kernel/fuse.rst) | 426 | Mount ownership, connection lifetime, interrupts, abort and deadlock |

The initial kernel URL used a directory layout absent from v6.8 and returned
404. The old COPYING.LIB filename mentioned in header comments also returned
404; the release's LICENSE identifies LGPL2.txt and GPL2.txt instead. Both
acquisition failures are recorded. No missing source is counted as read.

## Findings and design implications

FUSE supplies the request transport between the kernel and a userspace
filesystem. The filesystem still supplies data, metadata and persistence.
Consequently a mount or advertised statfs capacity cannot demonstrate an
allocator limit or durable backing. The next implementation needs a real bounded
allocator or an established bounded filesystem with verified backing.
[Kernel overview](https://www.kernel.org/doc/html/latest/filesystems/fuse/fuse.html).

The API makes several distinctions material to the HMS provider:

- High-level unlink normally renames open files to hidden names until release.
  Turning on hard_remove breaks specified operations on open-unlinked files.
  Accounting must retain both storage and inode charges through actual release,
  including overwritten names and retained mappings. A path scan is insufficient.
- flush is not fsync, may occur more than once and may not occur at a convenient
  point. Release return values are ignored. Durable acknowledgement must use an
  implemented persistence contract, including directory metadata and failure.
- Kernel data caching, writeback and direct I/O have distinct timing and error
  behavior. A later allocator must account before acknowledgement and define its
  supported caching modes; this read-only probe chooses direct I/O for its file.
- fallocate has an explicit space-guarantee contract. Merely implementing a
  success reply without actual allocation would violate it. It must remain
  unsupported until a backend can satisfy the contract.
- Local kernel locks may work without remote lock callbacks. This is useful for
  the current single-host ownership model, but does not extend that model to
  bypass access to backing files or clients on another machine.
- The single-threaded loop serializes callbacks but can deadlock on recursive
  access to its own mount. A provider's executable, dependencies, logs and backing
  handles must not require reads through the filesystem it serves.

These points come from the fully read
[pinned public API](https://github.com/libfuse/libfuse/blob/3f65bb699cd2f0afe2b9519c39d29922229f2168/include/fuse.h).
They motivate acceptance tests; they do not establish a qualified writable
filesystem for HMS.

The kernel overview separately distinguishes lazy detachment from terminating a
filesystem connection. Interrupt requests may be ignored. Killing a process or
detaching a path is therefore not evidence of durable settlement or a physical
control deadline. Do not route a device's independent local stop through this
filesystem. Control and bulk storage also need independent failure behavior so
an unavailable evidence daemon cannot prevent control-only reconciliation.

## Observed host result

The [original read-only probe](../../../artifacts/verification/pat-fuse-mount-probe/README.md)
passes 14 checks with the installed library/helper. It creates one fixed document
in a fresh owned mount, verifies refusal of mutations, ordinarily unmounts and
reaps both original children. Its retained mount record shows a shared propagation
entry. The path is private by ownership and mode; no private mount namespace was
created or qualified. A production provider must explicitly address propagation,
mount replacement and owner loss. No permanent service, quota or mount remains
from this probe in the inspected namespace.

Hard aggregate storage, reserved physical capacity, crash durability, writable
SQLite behavior and production admission remain unqualified. In particular,
neither the raw FUSE mechanism nor this in-memory read-only fixture supplies the
three obligations in the [control-capacity design](../../../artifacts/verification/pat-storage-capacity/DESIGN.md).
