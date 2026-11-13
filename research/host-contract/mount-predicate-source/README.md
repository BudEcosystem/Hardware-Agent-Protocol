# Mount predicate source review

Primary source acquisition supports the isolated statx mount-provider candidate.
Linux references are tag v7.0, commit
`028ef9c96e96197026887c0f092424679298aae8`, from the
[kernel Git mirror](https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux/+/028ef9c96e96197026887c0f092424679298aae8/).
glibc references are tag glibc-2.39, peeled commit
`ef321e23c20eebc6d6fb4044425c00e6df27b05f`, from the
[canonical glibc repository](https://sourceware.org/git/glibc.git).
`sources.json` records hashes, sizes, LF counts and revisions for ten extracted
files. The glibc object store is a shallow, filtered acquisition without checkout;
it is not a claim that the full repository was acquired or read. Acquired code
was not compiled, imported or executed.

The first glibc Google-mirror request returned HTTP 404 after all five Linux
files had been retained. Acquisition continued through canonical sourceware Git
in a separate script. The terminal handle for that extraction was unavailable
after context compaction; its completed manifest and all ten file hashes were
verified directly. This is not a fabricated process-exit receipt.

## Reading coverage

Complete reads: Linux `fs/stat.c` (968 LF), `fs/mount.h` (266),
`include/linux/stat.h` (72), `include/uapi/linux/stat.h` (260); glibc
`sysdeps/unix/sysv/linux/statx.c` (38), `io/statx_generic.c` (90),
`sysdeps/unix/sysv/linux/bits/statx.h` (39), `io/bits/statx-generic.h` (65),
`io/bits/types/struct_statx.h` (55).

Linux `fs/namespace.c` is acquired completely (6,501 LF), but read only at
1–350, 700–750 and 1125–1325. Complete selected bodies include `mnt_alloc_id`,
`mnt_free_id`, `alloc_vfsmnt`, `free_vfsmnt`, `delayed_free_vfsmnt`, `setup_mnt`,
`vfs_create_mount`, `fc_mount`, `fc_mount_longterm`, `vfs_kern_mount`, `clone_mnt`,
`cleanup_mnt` and `__cleanup_mnt`. Other ranges and the remaining kernel/glibc
sources remain unread. Search results elsewhere in namespace.c are not counted
as full reads. The selected source review is not an audit of the running Ubuntu
kernel or libc binaries.

## Findings and implications

`vfs_statx_path` fills mount identity from `real_mount(path->mnt)`, preferring
the unique-ID field when requested and returning the corresponding result-mask
bit. Both descriptor and pathname paths reach that helper. The descriptor route
uses the held file's path. The named route performs lookup with explicit final
symlink and automount behavior. The copy-out routine clears the ABI structure
and copies the mount field and supported result bits.

`mnt_alloc_id` allocates a reusable legacy ID and increments a separate unique
counter under the mount-ID lock. `mnt_free_id` releases the legacy slot. Creation
and cloning allocate a new mount object before associating its superblock.
Therefore a unique mount ID is suitable for checking the identity of an already
admitted mount during one running kernel lifetime. This is an implementation
inference supported by those bodies and the previously read statx manual; it
does not assert that every mount attribute is immutable.

The glibc wrapper calls the syscall. Builds without an assumed statx syscall may
emulate ENOSYS through fstatat64. That emulation returns BASIC_STATS, with no
mount identity. The candidate requires TYPE, INO and the requested mount-ID bit
from each result, so it refuses both an absent syscall and this emulation. The
glibc headers use the Linux stat header when available; the candidate checks the
compiled ABI size, mount-field offset and mask constants at build time.

Exact ext4 admission still requires mountinfo: the shared statfs magic does not
distinguish ext2, ext3 and ext4. The new admission path joins mountinfo to the
kernel-reported legacy ID, then rechecks unique identity. It does not choose a
record by lexicographic ID, mountpoint length or guessed stack ordering. Current
checks use fresh queries of both held and named directories.

Multiple calls remain subject to concurrent namespace changes. This preserves
the earlier trusted-host/exclusive-owner model; it is not an atomic transaction
against arbitrary privileged interference. Mutable idmaps and mount flags are
not fully reviewed here. Existing provider metadata checks remain enabled.
