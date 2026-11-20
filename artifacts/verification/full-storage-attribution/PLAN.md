# Full-workload storage attribution

This is an observation experiment, not a storage candidate. The Stage 95 source
seal is revalidated before freezing inputs. The inline512 hierarchy, provider,
native wrapper, native library, mount helper, original controls and dataset are
byte-exact. The original replay_write function runs unchanged on all 4,270 files,
35,508,922 payload bytes and 169 directories with a fresh eight-chunk 128 MiB
image. No failed image is reopened or modified.

Instrumentation wraps existing call boundaries and forwards all original
arguments, results and exceptions. It records fixed-label inclusive and nested
self wall/CPU time for logical methods, metadata publication methods, native
entry points, provider operations, ownership verification, current mount checks,
and selected pread/pwrite/fsync/allocation OS calls. It patches the actual
hierarchical_store._block_module loader and the statx provider's _host_current
path. The old small diagnostic's unused nested installer is not used.

Native read/write/rename calls are grouped by superblock, inode-state, payload
chunk and namespace-entry paths. Native-call self time excludes timed provider
callbacks but includes ctypes, native execution and instrumentation overhead.
It is explicitly not a measurement of individual C allocation or directory
traversal functions. Those costs remain an identified residual until direct
native instrumentation is justified. Provider verification self time contains
the remaining ownership/inventory/stat work after nested mount and read work.
No current ownership check, native call, checksum, sync or fsync is bypassed.

The original harness also reads and hashes source payloads, serializes progress,
and writes/flushes/fsyncs its progress receipt outside Store calls. These remain
uninstrumented harness work. The difference between child process totals and
top-level logical spans includes that work, startup and observer overhead; it
must never be labeled native execution. Only self time within Native.call after
nested provider spans is the explicitly limited native/ctypes residual. No
global os or Path object is patched to time the harness.

Observations are appended and fsynced outside the image at top-level logical
boundaries, at most once per second plus initial/final frames. Frames are bounded
to 64 KiB and the observation log to 12 MiB. There is no signal handler, pipe,
collector thread or native mutation callback. A kill can leave an incomplete
last line and an unobserved in-flight suffix; later inspection reports both
instead of extrapolating from completed work. Observer serialization/write/fsync
time and errors are recorded separately. Timing is intrusive and is not a
production-performance result.

Before the complete replay, run the original forty-file screen once without the
tracer and once with it. Require 426 logical steps, callback counts, full-body
receipts and backing-file hashes to match, excluding timings and observer-only
fields. This preflight validates the instrumentation on that screen. The
unchanged 192 Stage 95 checks are hash-revalidated, not repeated. A failure stops
the matrix. No fixed deadline, geometry or workload is reduced or enlarged.

Child limits: 60 wall/40 CPU seconds for each screen, 180 wall/120 CPU for the full
writer and its dependent cold reader; 512 MiB address space, 128 descriptors,
16 MiB per file and no core dumps. The runner freezes sources and binaries,
records intent/start/wait4 terminal receipts, kills the process group at the
deadline and reaps the child. Each backing chunk remains 16 MiB. The stage stays
below 1 GiB. The cold reader runs only after a complete writer receipt.

After execution, independently reconstruct retained images read-only using the
Stage 95 reader and explicit profile/library. Verify original source-prefix
bodies and directories, all pending/unlinked/incomplete state, and unchanged
backing hashes. No adapter recovery or SQLite may inspect failed images. Parse
only complete observation frames and match their callback/count monotonicity;
report observer overhead and unobserved suffix rather than claiming whole-run
attribution. Public runtime files and prior seals remain unchanged.

Prepared only: the parent must review these sources before execution.
