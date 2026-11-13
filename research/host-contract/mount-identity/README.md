# Current mount identity: complete manual-source review

Stage 92, 2026-11-09. The cost diagnostic found 23,780 invocations of the current
mount parser in a forty-file screen. This packet acquires and fully reads four
manual sources at Linux man-pages commit
`adb436b2e4471218021d86f188fb58dec3946eb8` (`man-pages-6.19`): **1,703 LF lines**.
The [acquisition manifest](sources.json) records exact URLs, status, bytes and
hashes. No acquired external code is executed. The kernel/libc implementation and
other manual pages referenced by these documents are not claimed fully read here.

| Complete source | LF lines | Consequence for the provider |
|---|---:|---|
| [statx.2](statx.2) | 728 | Query the held descriptor and current pathname separately; require returned mask bits. A successful call alone does not establish that a requested field exists. |
| [statfs.2](statfs.2) | 395 | Filesystem magic alone cannot establish the current exact ext4 policy: ext2, ext3 and ext4 share a value. |
| [statmount.2](statmount.2) | 460 | Mount-specific type/identity information exists, but documented privilege, ABI, mask and buffer requirements prevent assuming it is an unprivileged drop-in replacement. |
| [proc_pid_mountinfo.5](proc_pid_mountinfo.5) | 120 | Stacked mounts are related through parent IDs. Lexicographic or numeric maximum ID is not a valid selection rule. |

The `statx` manual distinguishes ordinary mount IDs, which correspond to
mountinfo, from `STATX_MNT_ID_UNIQUE`, available since Linux 6.8 and documented as
not reused during a running system. Descriptor lookup uses an empty path and
`AT_EMPTY_PATH`; pathname lookup can avoid following the final symlink. Returned
metadata is not an atomic snapshot of concurrent attribute changes. The candidate
must preserve ownership checks and cannot use `AT_STATX_DONT_SYNC` to silently
weaken the existing local-file metadata contract.

The [synthetic counterexample](COUNTEREXAMPLE.json) runs the exact original `_host`
function against substituted `fstat` and proc-file data. An initial mount with ID
`9` is then covered by mount `100`, whose parent is `9`, at the same path. The
function returns ID `9` for both inventories because its tuple comparison treats
the ID as a string. Thus its equality check misses this synthetic change. This
is a parser counterexample, not an actual mount-switch or full-provider attack
test. The diagnostic field `actualHostIOPerformed: false` refers specifically to
the substituted `_host` probe: the script does read local source and write its
result artifact. No mounts, namespaces, permissions or administrator state change.

The next design should resolve the actual named and held mount identities
directly, then join the ordinary ID to bounded mountinfo for initial exact ext4
type admission. A fresh unique ID check on both views before each I/O is a
candidate way to retain current identity without reparsing the complete inventory
on every callback. This is an inference requiring kernel/libc source review,
ABI/capability probes, race/error controls and explicit qualification. Cached
ownership or missing required mask bits must not be accepted. Older kernels need
an explicit separately qualified provider profile; universal HMS does not imply
that every host supports this particular Linux mechanism.

The local header inventory exposes both mount-ID constants and the local kernel
reports Linux 7.0.0-42-generic/x86-64. No `statx` capability probe, new native helper,
privileged `statmount` call or replacement provider is run in this packet. Those
facts do not establish support on GB10 or another intelligence host. The current
provider remains uninstalled, and the previous workload timeout remains failed.

Primary references: [statx(2)](https://man7.org/linux/man-pages/man2/statx.2.html),
[statfs(2)](https://man7.org/linux/man-pages/man2/statfs.2.html),
[statmount(2)](https://man7.org/linux/man-pages/man2/statmount.2.html), and
[mountinfo(5)](https://man7.org/linux/man-pages/man5/proc_pid_mountinfo.5.html).
