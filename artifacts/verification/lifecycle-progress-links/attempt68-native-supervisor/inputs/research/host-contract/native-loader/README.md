# Immutable native-image loading

Three Linux manuals, the upstream Linux v6.12 executable-memfd policy document
and the installed memfd UAPI header were read in full: **836 LF lines**. Raw HTML,
extracted manual text, surrounding navigation, source URLs and hashes are retained.
The manuals' book-cover and analytics images are decorative. Linked references,
kernel/libc/dynamic-loader implementations and the earlier CPython packet's
unread ranges remain separate gaps. No acquired example was executed.

[memfd_create](https://man7.org/linux/man-pages/man2/memfd_create.2.html) provides
an anonymous file with an owned descriptor and optional close-on-exec/sealing
flags. Its label is diagnostic, so the label cannot authenticate content. An
immutable loader must verify bytes and actual inode/seals. Holding the descriptor
also prevents its procfd pathname from being reused while a dynamic-loader cache
may retain that path. This last requirement is our conservative design inference,
not a claim of complete loader-cache source review.

[File seals](https://man7.org/linux/man-pages/man2/F_ADD_SEALS.2const.html) attach
to the inode and affect every descriptor. Write, shrink and grow are separate
restrictions; a write seal alone does not freeze size. FUTURE_WRITE permits
pre-existing shared writable mappings, so it is insufficient for this immutable
image. Our loader applies WRITE, SHRINK, GROW and SEAL together before loading,
then checks both seals and content. Tests exercise writes, resizing, adding seals
and access through a second descriptor.

[proc_pid_fd](https://man7.org/linux/man-pages/man5/proc_pid_fd.5.html) explains
the descriptor paths and their access constraints. A held fd and its procfd path
refer to the same underlying file, but procfs access is not universally available.
The selected loader profile therefore requires that access. It never treats a
retained procfd number as a later process's live descriptor.

The retained [Linux executable-memfd policy](https://github.com/torvalds/linux/blob/v6.12/Documentation/userspace-api/mfd_noexec.rst)
distinguishes explicit executable creation from non-executable sealed memfds.
The namespace policy can reject executable creation. The loader explicitly
requests MFD_EXEC and refuses on denial; it changes no sysctl or privilege and
does not fall back through another execution path. The installed header confirms
its flag value. The memfd manual does not itself enumerate this newer flag, so
the separate policy source is material to the design.

The [isolated supervisor candidate](../../../artifacts/implementation/pat-native-supervisor/README.md)
uses these contracts for original, digest-pinned code. Sealing does not sandbox
that code, protect interpreter state against arbitrary same-process changes,
attest all system libraries or establish support for other operating systems.
