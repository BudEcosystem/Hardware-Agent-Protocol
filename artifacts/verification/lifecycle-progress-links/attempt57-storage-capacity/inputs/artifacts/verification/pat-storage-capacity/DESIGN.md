# Control capacity across device, driver and intelligence-hub operations

Status: researched design and bounded host observations, 2026-11-08. No production
storage separation, quota provider or active-work reservation is implemented here.
The unified resource graph already requires hub storage and compute to be managed
alongside device I/O and driver lifecycle. This review addresses one concrete
dependency of the prompt → validated PAT → deterministic execution path.

## Evidence and decision

The [read-only allocation audit](allocation.json) reacquired 56 existing
owner/writer locks. Original and retained authority files still match the sealed
passing scope. SQLite 3.45.1 reports 15,820 pages of 1,024 bytes, with no freelist:

| Allocation in the existing file | Bytes |
|---|---:|
| Compact evidence bodies and their index | 14,641,152 |
| Remaining compact evidence metadata, references and indexes | 799,744 |
| Other authority btrees, including the schema | 758,784 |
| Total | 16,199,680 |
| Unallocated room below the existing 16 MiB file ceiling | 577,536 |

The evidence family therefore occupies 15,440,896 bytes. These are current btree
allocation measurements, not predictions for a newly created schema. DBSTAT omits
freelist and some special pages; the audit separately checks freelist, page count,
auto-vacuum mode and the exact accounting identity in this file.

The next implementation should separate the complete imported evidence family
from the control authority, with independently bounded storage and connections.
Moving only bodies would leave nearly 800 KiB of evidence references in control
storage. Import intents and published evidence references still consume bounded
control space and must be admitted explicitly. Separation alone is insufficient:
active work needs a qualified capacity reservation and actual filesystem backing.

An always-attached SQLite database is not the preferred availability boundary.
The [passing experiment](attempts/attempt02/stdout.log) establishes separate file
growth limits and ordinary rollback, but not independence from an unavailable
attached database, lock contention, common filesystem exhaustion or I/O failure.
SQLite multi-file commit also introduces super-journals and deployment constraints.
The design below instead permits retained, unpublished evidence after a crash,
while publishing its reference atomically in the control authority.

## Preserve the authority and evidence contracts

Introduce a new explicit storage/evidence profile. Do not reinterpret the current
`hms.pat.io-evidence-compact/0.1` schema, open a missing bulk store with CREATE,
mutate sealed test databases, or silently migrate an oversized failed scope.
Current profile readers continue to refuse an incompatible schema. A fresh store
pair has independent durable identities and a committed association in the
authority. The service owns private directories and exact database files; it must
verify their actual identities and access policy rather than trust caller paths.

The authority keeps operation and procedure history, claims, fencing, clock
floors, configuration/run/handoff associations, import intent, publication
references and catalog decisions. The evidence store holds exact immutable bodies,
document references, complete manifests and import receipts. A sealed manifest
includes the original authority/configuration/reservation/supervisor/attempt
association, all body identities, the consumer identity and the complete logical
receipt. Every body remains available for current-byte verification. A digest
alone must not replace the existing body and semantic checks.

The proposed publication order is:

1. Under control admission, reserve bounded control and bulk capacity and commit
   one import intent tied to the original run and mutation key. Capacity failure
   before this commit performs no import. An accepted intent survives restart.
2. Outside the control writer lock, independently inspect the original archive
   and source associations, and commit a complete immutable manifest plus exact
   bodies to the evidence store. Validate existing digest matches byte-for-byte.
   Incomplete or conflicting state remains unavailable. Flush according to the
   qualified storage profile before allowing authority publication.
3. Hold a bounded evidence read transaction/lease for that complete manifest,
   then enter the control transaction. Recheck authority, authorization, original
   intent and source associations, and atomically publish the reference and exact
   receipt. The evidence lease must prevent store mutation/replacement throughout
   the check and commit under the supported owner/filesystem model.
4. Replay returns the original association. An interruption after evidence seal
   but before authority publication leaves an unpublished, charged manifest.
   Explicit reconciliation may finish the same import; it may not launch another
   qualification worker or invent a replacement mutation key. An interruption
   after publication retrieves the existing result.

This is not a distributed rollback transaction. Unpublished retained data is an
intentional state, with durable ownership and capacity charges. No automatic
cleanup of unresolved imports is part of the initial profile. If a published
manifest disappears or becomes corrupt, fresh PAT reuse is unavailable, never
novelty. Historical evidence lookup can also be unavailable; primitive operation
history and cancellation must remain reachable through control-only recovery.

The current catalog callback performs guarded reads in the main database. A new
profile must explicitly support an authority-bound evidence snapshot acquired
before the control lock and held through admission. Do not disable the current
SQL authorizer or permit arbitrary attached schemas to make it work. Check every
selected current body against the prepared interpretation; prohibit a stale
cache or unheld connection from impersonating the evidence lease. Define and
test the lock order: evidence read lease before control transaction, and no
evidence writes while holding the control writer lock. Profile-specific preparation
must have finite work, memory and lease lifetimes. Existing profiles stay intact.

## Three separate capacity obligations

| Obligation | Required enforcement | Insufficient substitute |
|---|---|---|
| Per-store allocation ceiling | Read back each actual connection's page size and cap before its first mutation; cover reopen/recovery | A configuration value, prior connection setting or row-byte count |
| Aggregate durable storage bound | Qualified hard block/inode accounting for every writer and sidefile, with a documented total across domains | Post-run scan, free-space observation, RLIMIT_FSIZE, or `journal_size_limit` |
| Capacity owed to admitted control work | Backed reservation for the bounded remaining writes and sidefiles of all accepted obligations | The gap below a cap, an unbacked counter, or bulk/control filenames |

The [earlier filesystem review](../pat-supervisor-current-integration/storage-design/ASSESSMENT.md)
remains applicable. A quota caps consumption; it does not itself reserve physical
blocks against unrelated writers. A provider must establish actual backing and
ownership, account for metadata and inode use, and state its device/filesystem
failure assumptions. Shared or thin backing cannot be labeled reserved solely
because logical caps add up. No such provider is currently qualified on this host.

Do not multiply the old budget by adding files. Future bounded verification must
retain the original 16 MiB per-file ceiling and 256 MiB scratch ceiling. Also
declare an explicit combined main-data budget when evaluating a split store.
For comparison only, 1 MiB control plus 15 MiB evidence sums to the existing
16 MiB main-file budget; current btrees fall below those arithmetic partitions
before new schema overhead. This is not an adopted reservation or a migration
result. Future record-size and recovery bounds must determine any actual partition.

Each admission must account for retained control history, outstanding obligations
and the new operation's entire bounded continuation. Include parent/child keys,
events, receipts, cancellation/reconciliation records, configuration transitions,
import intents, catalog references, owner recovery and clock-floor persistence.
Variable-size results must have admitted bounds. Unknown outcomes keep their
remaining obligations. Retrying or restarting cannot erase a charge or grant a
fresh budget. Evidence publication has a distinct bounded metadata allowance;
it cannot consume the remaining capacity owed to active device control.

Page allocation, index splits, rollback journals, super-journals if used,
temporary files and startup/recovery writes all need explicit bounds or a provider
that conservatively reserves them. The current Journal changes owner epoch and
recovery state during construction; a capacity policy installed after construction
is too late. The independent clock-floor transaction after a business rollback
also needs capacity. A failed clock-floor write retains the existing poisoned
mutation behavior; it cannot be disguised as a clean capacity refusal.

Startup should establish the control store's supported policy before any recovery
mutation. Missing or full evidence storage disables new evidence/PAT work, while
a separately qualified control-only recovery mode serves already admitted work.
This requires an explicit runtime mode and tests; simply aborting the entire
runtime because its evidence attachment is absent would defeat the requirement.

## Failure semantics and next implementation

SQLite may roll back one statement or an entire transaction on SQLITE_FULL and
other failures. Inspect transaction state, roll back any remaining transaction,
and verify required durable state before classifying the outcome. Do not resend
an effect because its status record failed. A successful synthetic write after
rollback proves neither general future capacity nor power-loss durability.

Control storage can still fail physically. Keep the independent bounded stop or
local fallback path outside the journal writer and model worker. Its concrete
target/OS implementation remains required. Storage isolation cannot replace
qualified endpoint behavior during hub loss.

The next production candidate must implement the new pair identity and publication
states, bounded evidence snapshot contract, pre-recovery page-cap enforcement,
and explicit provider/admission gates. Start with fresh host fixtures. Acceptance
must cover full bulk storage with active control completion/cancellation, retained
unpublished manifests, both publication crash boundaries, missing/replaced stores,
original-key recovery, cap reset on reopen, current-body mutation refusal, failed
control/clock-floor writes and unchanged legacy profile behavior. Actual hard quota
and reserved-space tests require a real qualified provider; fake fixtures must
remain labeled as fixtures. Public qualification stays disabled until its declared
storage profile is enforceable. Natural-language synthesis, persistent Arduino
applications and actual I/O/driver/hub providers remain separate unfinished work.
