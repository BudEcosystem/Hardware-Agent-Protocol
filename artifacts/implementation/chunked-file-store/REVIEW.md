# Pre-execution review

Primary-agent review only. Stage 83 selected source reading and both exact seals
were reverified before this work. The reviewed native core is unchanged. The
original bridge supplies caller-owned caches, limits internal file/name sizes and
closes every native file before returning. Allocation traversal counts unique
reachable blocks using a fixed bitmap; it is an observation, not a reservation.

Whole adapter operations hold one Python owner lock. Fork checks precede that
lock. Per-owner handle tokens and monotonic slots prevent reuse of closed or
previous-session handles. All descriptors resolve the same in-memory inode record.
Rename-over-open-target and unlink preserve old backing until the final reference
closes. Recovery removes ownerless unlinked records only after validating all
namespace entries, directories, chunk names, exact referenced lengths and the
presence map. A missing referenced chunk refuses recovery without formatting.

The namespace carries image identity, finite monotonic inode IDs, file sizes and
exact presence maps in canonical JSON with SHA-256. The digest detects accidental
metadata alteration; it is not authentication against the trusted host owner.
Data chunks rely on the selected storage substrate; end-to-end payload digests
and physical media fault behavior are separate unqualified requirements.

Namespace writes sync a staging file and rename it. Writes to an existing data
chunk complete independently of other chunks; multi-chunk writes are not atomic.
Shrinking publishes smaller size/presence before reclamation. Growth zeros any
retained truncated tail before exposing it. Newly staged unreferenced chunks are
removed during recovery. Any filesystem/callback failure poisons the owner, keeps
the partial backing and prevents further operations. Request refusals happen before
storage I/O and do not poison otherwise usable state.

The native callback boundary catches exceptions and returns an I/O error; no
exception is permitted to escape a C callback. Once a callback fails, later
callbacks refuse further work. Resource release is distinct from a clean close.
The owner-loss test exits a real child after completed synchronization, leaving
handles/locks to the kernel; this is not an interruption at every commit phase.
One separate sync fault is injected, and one referenced chunk is deliberately
removed. Those interventions are labeled in their receipts.

The original runner freezes 12 exact input files (13 for the corrected second
attempt, including CORRECTION.md) and compiles only the selected
core, utility and bridge. It bounds every process, retains failed evidence, stops
the matrix after the first failed/inconclusive scope and preserves the 244-file
public baseline. Six backing images total 96 MiB if all scopes start. No fixture
database, mount, physical port, driver, hub service or public runtime is modified.

Acceptance here means the six declared private-adapter scopes complete under
their original limits. Full storage-service qualification, all-writer confinement,
disk exhaustion, the interrupted namespace matrix, SQLite integration, backed
control capacity and physical power loss remain unfinished regardless of outcome.

Attempt01 found an original bridge defect at cold reopen: directory size is an
undefined upstream field, but hm_stat copied it and inventory expected zero.
The second attempt initializes the structure and explicitly emits zero for a
directory without reading its size. Adapter and control sources are unchanged.
The original failed image is hash-inventoried and not reopened or repaired.
