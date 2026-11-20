# Hierarchical storage: semantic controls pass; workload gate fails

Stage 91, 2026-11-09. The preceding split-supervisor integration remains verified
progress: 71 distinct controls and the complete original thirty-case simulated
qualification-to-PAT flow pass. This separate storage candidate adds a hierarchical
namespace to the fixed-block/shared-inode adapter. **All nine semantic scopes /
96 checks pass. The complete workflow replay fails its declared wall deadline.**
Nothing is installed into the public runtime.

The adapter provides nested UTF-8 names, directory handles, stable inode identity
across subtree moves, file/directory replacement and held unlinked objects. Each
inode has checked metadata; directory entries reference its identity. Recovery
validates the complete graph and physical inventory before adapter cleanup.
File data retains 4 KiB shared chunks, coherent handles and sparse/truncate
semantics. Limits are 8,192 inodes, 64 handles, 32 levels, 255-byte components,
4,095-byte paths, 16 MiB files and 64 KiB transfers. Available backing can fill
before these admission bounds. This is a private host API, not a POSIX mount or
an Arduino memory profile. [Design and review](REVIEW.md).

The [controls](attempt01/RESULTS.json) cover descriptor-relative access, Unicode,
global path bounds after moves, replacement, open-unlinked file/directory lifetime,
coherent data, sparse/regrown tails, invalid-request no-I/O, four creation
publication checkpoints, ownerless orphan recovery, missing chunks, duplicate
references, owner replacement and callback failure. Original interrupted images
are retained; recovery runs on copied bytes with new host-object anchors. The
checkpoint tests inject exceptions after completed native calls. They do not
qualify arbitrary process interruption or physical power loss.

The full replay requests **all 4,270 files / 35,508,922 bytes and 169 directories**
from the exact preceding workflow snapshot, with eight preallocated 16 MiB chunks.
Its writer reaches the **180-second wall deadline** and is terminated/reaped at
180.087 seconds, using 106.587 CPU seconds and 23,816 KiB peak RSS. It has no
complete writer receipt. There is no reported NOSPC error; this attempt does not
establish whether the entire workload fits. The dependent cold-reader process is
not started. No smaller workload, larger geometry, extended deadline or unchanged
retry follows. [Original process receipt](attempt01/replay_write/result.json).

The independent [read-only audit](EVIDENCE-AUDIT.json) checks all **19 retained
images / 26 backing chunks (416 MiB)**. Every fully recorded body is exact:
**675 files / 3,598,315 bytes**, plus all 169 directories. One further published
file has committed size zero. The partial prefix is evidence of the interrupted
attempt, not workload qualification. Original owner replacement, deliberate
corruptions and staged checkpoint states remain intact. All native write/erase/
sync callbacks are forbidden during audit; no adapter recovery or SQLite runs,
and every backing byte remains unchanged. The audit completes in 3.414 seconds
under its separate 90-wall/60-CPU limits.

Fifteen source inputs, compiler identity, dataset manifest and the native binary
were frozen before execution. The binary has a distinct 264-byte directory-entry
ABI and SHA-256 `7049dc14940b0f686f5cbe682e85f70944a8074936786e7f962c6ee29ed321de`.
The fixed-block implementation remains exact, including ownership checks on every
provider I/O; littlefs read/cache size stays 4,096 and program size 16. All 244
public runtime inputs remain exact against the existing 866-test receipt; that
unchanged suite was not repeated. Review is by the primary agent only.

[Next work](NEXT.md) investigates the workload cost before another implementation
candidate. Complete storage service behavior, SQLite temporary/journal handling,
hard aggregate enforcement and backed control continuations remain required.
Natural-language learning into PATs, persistent MCU control, actual device I/O,
driver and intelligence-hub providers, microscope commissioning, native Harness
installation, remaining research and domain qualification remain unfinished.
The original goal stays active.
