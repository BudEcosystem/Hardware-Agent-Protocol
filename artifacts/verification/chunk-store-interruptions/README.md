# Chunk-store interruption matrix

Stage 85, 2026-11-09. **All 22 declared cases pass**, covering 24 selected owner
interruptions. The [stage 84 adapter](../../implementation/chunked-file-store/README.md)
and native library remain byte-identical; no public runtime source changes.
[Original case definitions](cases.json), [attempt receipt](attempt01/RESULTS.json),
[plan](PLAN.md), [review](REVIEW.md).

| Operation group | Cases | Verified outcome |
|---|---:|---|
| Create | 4 | Unpublished directories/staging are reclaimed; published empty file survives |
| Extend | 3 | Unpublished new chunk is discarded; published size/presence retains it |
| Overwrite | 2 | Selected within-chunk cut retains old data; completed first chunk yields the declared mixed result |
| Shrink | 2 | Reduced size/map survives and obsolete chunk is reclaimed |
| Grow | 2 | Old visible prefix remains valid; published growth exposes zeroes beyond it |
| Rename over open target | 3 | Complete old or new namespace, with old target reclamation after owner loss |
| Unlink | 1 | Ownerless unlinked data is reclaimed |
| Final-reference close | 3 | Recovery completes metadata removal and partial file/directory reclamation |
| Recovery itself | 2 | A second terminated owner can be recovered from another exact derived copy |

Each selected owner writes and synchronizes a checkpoint, then stops itself.
The parent verifies its PID, Linux start ticks, intent digest and stopped state,
sends SIGKILL through the original pidfd, and reaps terminal -9. The checkpoint
is not inferred from a timeout or missing reply. All 24 selected stops were reached;
there were no retries or changed checkpoints. Each outer case finished in roughly
2.9–6.2 seconds under the original 60-second limit.

Every interrupted image is retained unchanged. Recovery runs only on a fresh,
fully allocated copy with exact source block bytes and new host object anchors.
The two recovery-interruption cases retain a second interrupted copy and recover
from a third image. There are **46 images / 736 MiB backing**, within the matrix's
predeclared 1 GiB retained-file ceiling; each backing file is 16 MiB. These private
artifact copies share a logical image identity for lineage testing and are not
deployed concurrent authorities.

The [read-only evidence audit](EVIDENCE-AUDIT.json) reinspects all 46 images, joins
all 24 stop/kill records and 24 copy lineages, and compares final adapter reads with
raw chunk-map reconstruction and the original expected inode/name/size/digest
outcomes. It holds four original object locks per image, checks 184 distinct host
anchors, verifies all 68 recorded case/owner PIDs are absent, and changes no image
bytes. Final recovery leaves no orphan records, extra directories, stale staging
files or unreferenced chunks.

The before-rename-sync case recovered the complete new namespace on this host.
That is allowed by its original old-or-new oracle: process termination leaves
the kernel and caches running. It does **not** prove power-loss durability or that
an unsynchronized mutation is generally durable. The two program-boundary cases
stop before the second callback, not at every possible torn sector or byte offset.

Fifteen exact source, binary and review inputs are frozen. All 244 public runtime
inputs match the existing 866-test passing receipt; neither that suite nor the
thirty-case worker is repeated. No upstream scripts, new dependency, FUSE mount,
SQLite database or physical device is executed. Review is by the primary agent.

This completes the declared matrix, not every interruption state or the storage
service. Actual block/metadata exhaustion, every-writer confinement, SQLite
DELETE/EXTRA recovery, backed continuations and physical power loss remain required.
[Next work](NEXT.md) keeps those gates and the complete prompt-to-PAT and
device/driver/hub goal. [Stage audit](AUDIT.json) and [exact inventory](index.json).
