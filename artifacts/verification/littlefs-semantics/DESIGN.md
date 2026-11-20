# Storage-provider decision after core review

The HMS protocol controls typed resources across endpoints, drivers and the
intelligence hub. Its universal capability model does not require every target
to run the same filesystem, SQLite, Python or model. The Arduino-class profile
can execute commissioned firmware primitives and validated local PAT programs;
a hub can own synthesis, learning and richer evidence storage. Deployment and
outage dependencies are explicit parts of each PAT's applicability.

The reviewed littlefs core offers a useful finite-block substrate, but direct
POSIX descriptor mapping is rejected. The retained experiment demonstrates stale
handles and update cost proportional to the unchanged file suffix. These are not
claims that littlefs violates its own documented API. They show that the proposed
HMS host contract needs more than the stock interface.

## Selected next candidate

Investigate an original, bounded filesystem adapter over the reviewed core and
stage 82 fixed block devices. Use fixed-size data chunks and one shared live inode
object per logical file. Chunking limits the unchanged suffix copied by one data
update; it does not itself reserve space, bound total transaction work or solve
metadata exhaustion. Start with a 4 KiB chunk feasibility profile, measuring its
real metadata overhead before fixing any production chunk size or capacity.

1. A single trusted owner serializes each whole adapter operation. Descriptors
   reference shared inode state; no independently stale littlefs file handle is
   exposed as a POSIX file descriptor. Actual multi-process coordination belongs
   to the owner and later FUSE/VFS boundary, not individual LFS_THREADSAFE calls.
2. Namespace entries refer to stable bounded inode IDs. Logical offsets select
   fixed-size chunks. Validate identity, length and generation for metadata and
   chunk references. Bound directories, chunks, descriptors and orphan records.
3. Keep unlinked inodes and their backing until the last live reference closes.
   Persist sufficient orphan ownership to reclaim them after owner loss without
   treating missing identity as a fresh file. Rename and truncate need explicit
   atomic metadata protocols; ordinary successful littlefs calls do not establish
   the adapter's multi-file transaction semantics.
4. Separate bulk and control images. Account for old/new chunks, namespace COW,
   recovery records, journal side files, temporary work and retained unlinked
   objects. Reject admission unless actual backing covers all remaining control
   continuations, including recovery. A quota, NOSPC result or free-block counter
   alone does not meet that requirement.
5. Synchronize data and required directory metadata in the order required by the
   current DELETE/EXTRA SQLite contract. Model lock acquisition/release, file-size
   changes, fsync, rename/unlink and owner death explicitly. Do not claim SQLite
   compatibility until actual SQL recovery tests exercise the selected interface.
6. Reopen existing images only with exact commissioned profile/identity. Apply
   limits before recovery can mutate storage. No automatic format, migration,
   expansion or fallback provider. An uncertain I/O failure stops new admissions
   and retains the original operation identity for bounded reconciliation.

This is a candidate design, not accepted production storage. The next gate is
shared-file semantics and bounded chunk allocation on original fresh fixtures.
It must include same-file simultaneous handles, open-unlinked retention, namespace
recovery and honest physical accounting before an actual SQLite integration.
If those requirements cannot be met within the fixed profile, record that result
and select a separately provisioned native storage profile; do not weaken them.

## Endpoint PAT storage

Immutable validated PAT packages are a distinct workload from hub SQL databases.
An endpoint candidate can stage a finite package, validate its digest and firmware/
capability bindings, synchronize it, then activate through a recoverable generation
record. That sequence still needs its own power-loss, capacity and rollback tests.
This stage implements none of those activation semantics and commissions no board.

Hub/model loss must leave the endpoint in its declared local operating mode with
its commissioned stop and watchdog behavior. A driver update, changed calibration,
rewiring or hub restart can invalidate a PAT dependency. Missing evidence is an
unavailable state, not proof that a scenario is novel and eligible for improvisation.

The selected storage candidate advances one infrastructure obligation. Physical
I/O providers, driver lifecycle, hub compute/service management, actual learning,
MCU persistence, microscope commissioning and end-to-end scenario qualification
remain part of the active goal.
