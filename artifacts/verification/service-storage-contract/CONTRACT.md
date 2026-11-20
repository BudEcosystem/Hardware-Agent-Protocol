# Service storage interface and ownership contract

This is a required integration contract grounded in the current sources, not an
implemented filesystem or admission guarantee. [Static inventory](call-inventory.json)
parses 123 Python modules and freezes 124 Python/C sources. All 156 selected
syntactic call candidates have a [reviewed classification](site-review.json).
Names such as `bind`, `replace`, `remove` and serialization `write` include
non-filesystem operations; the inventory does not treat them all as disk writes.
Five actual `sqlite3.connect` sites define the native database boundaries.

## Storage domains and consumers

| Required domain | Current consumer and retained data | Availability obligation |
| --- | --- | --- |
| Control authority | `Journal`; registry, operations, procedures, configuration, exact prepared run inputs, handoffs, publication references and PAT decisions | Original-key history, cancellation/reconciliation and clock-floor persistence remain reachable without bulk |
| Supervisor control | `AuthorityAttemptLedger`; `attempts.db`, owner lock, original request, producer association, phase history and archive receipt | Opening/status must not require code images, output trees or the evidence vault |
| Endpoint state | `SyntheticIoBoard` / `SimulatedPlant` in the current simulation; real providers need their own durable-state contract | Preserve current ownership/fencing and uncertainty; simulated atomic commits do not prove physical effects |
| Worker bulk | Code/dependency image; attempt bundle, input, writer lease, stdout/stderr, case state and evidence, return file | Account for all producers, directories, temporary files and open-unlinked objects through actual release |
| Evidence bulk | Independent `EvidenceVault`, database/journal and owner lock | Unavailable evidence prevents fresh PAT reuse; it does not erase prior control history or become novelty |
| Ephemeral transport / memory | Unix socket namespace, inherited pipes, sealed executable memfd | Explicit separate limits and ownership; these are not durable capacity reservations |

These are failure and ownership domains, not permission to multiply the existing
budgets. A deployment must bind each domain to exact provider identities and
account for the sum, including metadata and temporary allocations. Control and
bulk must not depend on the same blocked storage daemon for control-only recovery.
Provider logs, executable dependencies and backing handles must be outside any
filesystem they serve, with separately declared accounting.

The current `IoServiceRunStore` deliberately retains the exact prepared documents
in the authority, with an 8 MiB logical ceiling. They must not silently move to
unavailable bulk to make a small control partition fit. The previous 1 MiB/15 MiB
control/evidence arithmetic was explicitly a comparison, not an adopted partition.

## Concrete incompatibilities found

The current supervisor uses `ledger.root`/`ledger.fd` for both `attempts.db` and
the code/attempt trees. `_image`, `_launch`, `_collect`, recovery, admission scans
and `evidence.archive.read_original` all consume that shared location. Merely
moving the database pathname leaves the launch and archive readers bound to the
old root. An explicit control handle plus an optional bulk binding must replace
that implicit relationship in a new profile.

`AttemptLedger.__init__` opens a connection, sets DELETE/FULL, enters a write
transaction and marks active attempts interrupted. `Journal.__init__` performs
owner-epoch and uncertain-outcome recovery writes. `SyntheticIoBoard._open` and
the simulated plant also have recovery mutations. No later service constructor
can retroactively protect those writes. The vault differs: it refuses existing
journal/WAL/SHM paths before opening, sets a page cap and checks it on subsequent
transactions. That refusal is not a qualified hot-journal recovery path.

The flat adapter accepts only 16 inodes and 63-byte names. Current generated
names already need 69 bytes for code images, 86 for a board database, 92 for its
owner file and 94 for its rollback journal. The historical successful workflow
retained 267 code-image files and 3,936 output files. Its supervisor tree held
4,248 regular files plus 164 inferred non-root directories, with relative file
depth seven. A new hierarchical namespace and scalable metadata representation
are required. Raising `MAX_INODES` alone would also outgrow the current bounded
single-document namespace and does not implement that representation.

The historical layout in [RESULTS.json](RESULTS.json) is reconstructed from exact
retained index rows; no database was opened. It measures one completed workload,
not a worst-case bound. Its supervisor request has a 64 MiB `maxFileBytes` default,
while the verification policy retains a 16 MiB per-file ceiling. The child applies
the minimum of its request and inherited hard limit. Production integration must
make the approved ceiling explicit before admission; it must not assume the test
parent's limit will always exist. The 256 MiB scratch ceiling remains unchanged.

## Native SQLite writes and synchronization

SQLite rollback journals share the database directory, while some temporary files
may use another directory. Unix temporary-location selection can reach standard
temporary directories. Memory settings do not eliminate all durability files.
Consequently, bounding only a database pathname is insufficient. The complete
[official temporary-file article](https://sqlite.org/tempfiles.html) is retained
and read locally; its own version caveat means the installed build still needs
syscall-level qualification. [Acquisition](sources/acquisition.json).

The integration must bind every native temporary path to its owning allocation
domain or prove a bounded memory-only behavior for that exact operation/build.
Setting an environment variable without testing fallback, inheritance and
unlinked lifetimes is not that proof. Do not change DELETE/EXTRA authority/vault
durability to make integration easier. The existing supervisor ledger uses FULL;
any stronger new profile needs explicit semantics and qualification.

Backing and namespace caps must be active before SQLite can recover a hot journal.
Reading connection PRAGMAs after SQLite has already accessed a hot database does
not prove the earlier writes were bounded. Define a qualified pre-open provider
gate and explicit recovery protocol; refuse unsupported recovery states. Read back
the actual connection page size and cap before business/schema mutations. Keep
the independent clock-floor transaction and its poisoning behavior within the
remaining control-capacity obligation.

## Required filesystem behavior

The selected interface must support the actual stock pathname VFS and all other
declared writers. A SQLite-only VFS would leave the Python writers outside its
accounting unless the design separately confines them. A FUSE transport supplies
no allocator or capacity guarantee by itself; the earlier wrapper review remains
applicable.

Required behavior includes:

- Hierarchical regular files/directories, stable inode identities, private owner
  modes, exact link counts and descriptor-relative traversal with `O_NOFOLLOW`.
  Preserve existing names and input/image identities; no hidden name shortening.
- Exclusive creation, shared current data through multiple descriptors, positional
  reads/writes, truncate/grow/zero semantics, rename-over-target, and open-unlinked
  lifetime/accounting. Reject unsupported kinds or operations explicitly.
- File sync and directory sync with propagated errors. Flush/release/close alone
  cannot stand in for the requested persistence barrier. Verify worker evidence
  publication and its directory entries as part of the final archive boundary.
- Owner `flock` semantics, inherited writer leases and SQLite byte-range locking
  under the supported single-host process model. A parent dying does not release
  a lease still held by a descendant. Restart must preserve unresolved ownership.
- Honest capacity information, bounded namespace/handles, metadata/COW accounting,
  and actually backed reservations if `fallocate` or continuation admission claims
  them. Successful example writes and reachable-block counts are insufficient.
- Explicit daemon loss, blocked I/O, mount replacement and stale-handle behavior.
  No database owner or producer may access the raw backing through a bypass path.
  The current trusted-code model must not be described as a hostile-code sandbox.

The aggregate limit must include worker databases and their journals, code images,
input/output files, logs, directories, locks, retained failures and allocations
whose names have been removed. The native retention scanner measures logical
names/sizes only and explicitly reports no quota enforcement. It remains useful
for evidence inspection but cannot substitute for allocator admission.

## Control-only recovery and implementation order

First introduce explicit control/bulk bindings in an isolated supervisor candidate.
Keep original identities, request digests, association ordering and single-flight
ownership. The binding must be recorded in control state and verified before fresh
admission. Opening control and looking up committed records must not open bulk.
If bulk is missing or unavailable, retain unresolved producer/evidence obligations;
do not archive them as settled, reacquire a new attempt key or relaunch a worker.
Retained live pidfds remain the only authority for signalling owned producers.

Then implement the hierarchical allocator/interface and pre-open connection gates
against this complete writer set. Choose explicit physical partitions only after
bounding remaining control writes, metadata splits/reclamation and SQLite sidefiles.
Exercise full/missing bulk with actual pending completion/cancellation and cold
control recovery, followed by the complete original worker → vault → catalog → PAT
flow. No public qualification mount precedes those gates.

This sequence advances unified device, driver and intelligence-hub control without
putting independent local stopping behind the journal, model or filesystem daemon.
Prompt synthesis/learning, persistent MCU execution and physical provider/scenario
qualification remain required parts of the larger goal.
