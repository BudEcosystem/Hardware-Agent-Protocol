# Private read-only FUSE mechanism probe

Stage 81, 2026-11-09. This is an original host experiment, outside the public
runtime and all retained qualification attempts. It investigates a possible
storage-provider mechanism for device/driver/hub control. It does not implement
hard writable quotas, persistent storage or reserved continuation capacity.

Use the installed libfuse 3.14.0 shared library and fusermount3 helper. Compile
only the original probe against the fully read upstream 3.14.0 public headers.
Do not build or execute the acquired example, library implementation or controller
code. An original empty libfuse_config.h selects the public headers' default
symbol declarations; this probe uses only fuse_main, fuse_version and
fuse_pkgversion, which do not depend on that configuration. Record the installed
library/helper/compiler hashes and the compile command. No package installation.

One fresh owned directory, mode 0700, contains one empty mountpoint. The probe
has a fixed single read-only document and no backing file. Mount foreground,
single-threaded, ro,nosuid,nodev,noexec,default_permissions, without allow_other.
Callbacks never access the mount or another file. The child checks the installed
library version, sets a 20-second alarm and a parent-death signal. The parent
owns the server/client/helper processes and records mount identity from procfs.

The client verifies directory/content/offset/EOF/ownership and missing-path
semantics, plus refused create/write/unlink operations. Run it only after the
expected mount is observed. The parent requests ordinary unmount of that exact
owned mount, reaps the server, verifies the mount is absent and the underlying
directory is empty. On failure, retain outputs and terminate only owned children;
cleanup must settle before reporting success. No lazy unmount or unrelated mount
or quota change. The client has five seconds, startup five seconds, ordinary
unmount three seconds and server exit three seconds. The server independently
limits address space to 64 MiB, CPU to three seconds, descriptors to 64 and
each output file to 16 MiB. These are probe bounds, not service guarantees.

Freeze source/dependency identities before execution; preserve failures. A
successful mount proves only this mechanism on this host. Writable block/inode
accounting, open-unlinked ownership, actual backing, fsync/crash semantics,
owner-loss behavior and separate control/bulk recovery require subsequent work.
Do not repeat the unchanged 866-test public suite for this isolated probe.
