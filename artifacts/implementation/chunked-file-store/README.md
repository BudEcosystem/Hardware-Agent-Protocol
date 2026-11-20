# Persistent chunked-file adapter candidate

Stage 84, 2026-11-09. **All six bounded scopes / 54 distinct checks pass** against
real, fully allocated host block images. This implements the next shared-file
candidate selected by the [littlefs review](../../verification/littlefs-semantics/README.md).
It remains a private single-owner adapter, not a mounted filesystem, SQLite VFS
or public storage service.

| Scope | Checks | Evidence |
|---|---:|---|
| Shared descriptors and data | 13 | Cross-chunk writes, truncation, zero-filled growth, stale handles and full cold readback |
| Namespace and unlink | 12 | Rename-over-open-target, unlink/recreate, shared old views and final-reference reclamation |
| Owner loss | 7 | Real child exit with open files; cold linked-data recovery and orphan reclamation |
| Allocation and update cost | 5 | Full 256 KiB readback, unique reachable blocks and callback counts |
| Bounds and invalid inventory | 11 | Inode/handle/transfer bounds and missing referenced chunk refusal without mutation |
| Injected sync failure | 6 | Poisoned owner, no subsequent callbacks and complete old/new single-chunk recovery |

[Passing receipt](attempt02/RESULTS.json). In the update-cost fixture, replacing
either the first or last 4 KiB programs **4,128 bytes**, with one erase and two
sync callbacks. The 256 KiB logical payload occupies 69 unique reachable blocks
(282,624 bytes) before and after the updates, inside a fully allocated 16 MiB
backing image. This excludes free blocks from the reachable count; it is not a
reservation or SQLite throughput result. The six scopes took approximately
2.4, 5.1, 2.6, 38.8, 21.4 and 0.9 seconds on this host under their 60-second limits.

The adapter serializes whole operations. Open descriptors share inode state and
carry an owner-session token. Data uses 4 KiB chunks; a checksummed canonical
namespace records exact chunk presence, so missing referenced data cannot silently
become a sparse hole. Unlinked backing remains until its last reference closes.
Cold recovery validates the bounded inventory before removing ownerless backing.
Every native file handle is closed before the bridge returns. See
[the implementation contract](DESIGN.md).

Attempt01 failed at cold reopen because the original bridge consumed a directory
size field that littlefs defines only for regular files. [The correction](CORRECTION.md)
initializes that structure and explicitly reports zero for directory size.
The adapter and all six control scopes are byte-identical across attempts.
The original failed image and logs remain exact; no repair or filesystem reopen
was performed on that failed image.

[Read-only retained-state inspection](image-readback.json) holds 28 original
object locks, reconstructs the passing fixtures' payloads independently of the
adapter's read/recovery methods, verifies the deliberately missing chunk, and
confirms no image bytes changed. It reads the failed image only as raw hashed
bytes. Seven images total **112 MiB** backing, including the failed
attempt. All backing files are at most 16 MiB. This finite fixture inventory is
not aggregate service quota enforcement.

The native bridge/core build uses assertions and warnings as errors. All acquired
compiled code was fully read in stage 83; no upstream build/test scripts run.
The corrected attempt freezes 13 exact source/review files. All 244 public runtime
inputs remain unchanged against the existing 866-test passing receipt; the public
suite and thirty-case worker were not repeated. Review is by the primary agent.

SQLite integration, actual full-disk exhaustion, interrupted namespace/reclamation
coverage, mounted file/lock semantics, every-writer confinement, backed control
continuations and physical power loss remain unfinished. The owner-loss test exits
after successful sync; it is not a power cut or complete interruption matrix.
[Next work](NEXT.md) retains those gates and the full device/driver/hub goal.

[Audit](AUDIT.json) and [exact inventory](index.json) seal this stage.
