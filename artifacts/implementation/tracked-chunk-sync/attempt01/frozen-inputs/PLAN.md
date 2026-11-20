# Isolated synchronization candidate

The previous statx provider passes focused controls but its complete 4,270-file
writer still times out. This candidate changes only synchronization bookkeeping
and the explicit block profile. Every opened chunk starts needing full fsync.
Before every nonempty payload read or write its bit is set under the existing
owner mutex; reads count because they may update access metadata. Erase uses
the same write path. Bits clear only after the complete sync succeeds.

For chunks 1..N-1, sync calls full fsync if touched, otherwise a native
sync_file_range WAIT_BEFORE|WAIT_AFTER call to retain per-file writeback error
observation. Chunk 0 always receives full fsync last. The wait call is never
used as durability for a touched chunk: it does not flush disk caches or
metadata. Constructor admission probes syscall support without clearing any
pending bits. Any helper, I/O, verification or synchronization failure retains
the existing poison behavior; close is still not sync. Creation fsyncs stay exact.

Source review precedes execution. Freeze all inputs and inspect the source diff.
Run native wait-helper controls; original 52 mount controls and 24 provider tests;
new tracking/error controls; the original 96 hierarchy controls; one paired
40-file/20-directory coarse screen with lightweight fsync/wait counters. Compare
all 426 logical steps, callbacks, full bodies and filesystem chunk bytes. If
these pass, run the complete original writer and dependent cold reader with
4,270 files, 35,508,922 bytes, 169 directories and eight 16 MiB chunks.

Ordinary child bounds: 60 wall / 40 CPU seconds, 512 MiB address space, 128 FDs,
16 MiB per file. Builds: 30 wall / 20 CPU. Complete writer and reader: original
180 wall / 120 CPU seconds each. Retained stage allocation below 1 GiB. Stop at
the first failed scope, retain all evidence, no unchanged retry or resized image.
Failed images may only receive the independent read-only reconstruction.

The hierarchy, native littlefs binary, statx helper and mount admission/checks
stay exact. Public runtime, prior images/seals and adjacent Harness stay untouched.
No physical ports, mount/namespace changes, administrative privileges, power
cuts or public installation. This trusted-host exclusive-owner profile does not
authorize external modification of backing files or establish physical durability
on every device. Full service storage and device/driver/hub qualification remain.
