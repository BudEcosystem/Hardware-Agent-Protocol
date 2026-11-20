# Next: qualify a precise current-mount predicate

The preceding turn is progress: two diagnostic modes have byte-identical final
images and callback behavior, the nested trace identifies mount parsing as a
substantial CPU cost, and a synthetic stacked-mount counterexample changes the
correctness requirements. Keep the exact prior provider, failed full replay,
diagnostic images, source packet and all receipts sealed. Do not rerun unchanged
experiments or claim that this forty-file diagnostic qualifies the real workload.

The next candidate must fix mount resolution, not merely cache the old result.
Read the relevant pinned kernel/libc statx and mount-identity implementation bodies
in full and record their relationship to the explicit host profile. Design a small
bounded ABI that can query the held root descriptor and its current named path,
requires every requested result bit and refuses unsupported/error cases. The
manuals support investigating unique mount IDs, but no capability probe or new
helper has run yet. Do not add administrative privileges to obtain a faster API.

Initial exact filesystem-type admission must join the actual mount identity to
bounded mountinfo, rather than choose the largest textual ID. `fstatfs` magic
alone cannot distinguish ext2/ext3/ext4. Pin the accepted mount identity and check
fresh named/held identity before every provider I/O; preserve private ownership,
exact root inventory, every held/named file pin, owner/manifest bytes, allocation
and size checks, fork refusal and poison-on-uncertain-error. Specify behavior for
missing mask bits, absent syscalls, symlink/replacement, detached mounts, namespace
changes and races. Keep other callbacks, chunk geometry and fsync behavior exact.

Use separate bounded controls and native/header/ABI identity records. The earlier
24 provider tests are useful regression inputs but do not cover this new mount
predicate, and the 96 hierarchy controls do not cover all mutation interruptions.
Demonstrate the synthetic stacked-ID case is handled, measure the new candidate
under a declared comparison, and only then rerun the complete 4,270-file acceptance
workload with its original 128 MiB geometry and 180-wall/120-CPU writer/reader
limits. A faster small diagnostic is not grounds for public installation.

Fsync costs and the number of native block reads remain separate observations;
the current data does not justify disabling sync, trusting cached ownership,
changing layout simultaneously or predicting full-flow timing. If the new
predicate cannot complete the full gate, preserve that outcome and investigate
the next demonstrated cost without shrinking the original requirements.

The complete goal still requires SQLite/journal/temp-file compatibility, pre-
recovery capacity checks, every-writer aggregate limits and backed continuation
capacity; deterministic PAT reuse with fresh dependencies and agent reasoning for
new contexts; concrete I/O/driver/hub providers and independent endpoint behavior;
MCU programs, microscopy, Harness integration, full-source research and the home,
laboratory and manufacturing scenarios. None is replaced by this host diagnostic.
