# Control storage for devices, drivers and the intelligence hub

The [standing-host integration plan](../artifacts/design/standing-host-deployment/HOST-DEPLOYMENT-PLAN.md)
requires durable activation collection before endpoint ACK and protected capacity
for owed loss/recovery work. The [partial native implementation](../artifacts/implementation/standing-host-deployment/RESULTS-REVIEW.md)
passes twenty cases / 173 checks in an explicit local SQLite ordering test scope.
Logical limits and actual commits do not establish protected aggregate capacity
or physical eligibility.

The [standing process-death controls](../artifacts/implementation/standing-host-owner-death/RESULTS-REVIEW.md)
now pass thirteen cuts after committed state or a consumed complete reply. A fresh
host acquires the same database after its owner is killed while the native peer
survives. Exact records survive reopen, collection precedes ACK, and uncertain
outboxes retain ownership without resend. Read-only final database checks are
separate from this execution. These controls do not cover death inside COMMIT,
partial frames, power loss or backing-storage exhaustion.

The [boundary successor](../artifacts/implementation/standing-host-boundaries/RESULTS.md)
passes ten synchronous storage-failure controls: exceptions before/after COMMIT
for four business boundaries, a rollback-call exception followed by reopen, and
SQLITE_FULL under a temporary page ceiling. Eight authority/replay controls also
pass. The first capacity attempt hits the unchanged thirty-second limit after
68 public never-handed-off mutation settlements; all original claims remain.
The remaining capacity profiles did not run. Separate per-owner/fixed partitions
sum to 16 MiB, but that arithmetic is neither a reachable full database nor a
reservation of SQLite/journal space. Complete accumulation and simultaneous
maximum histories remain unqualified.

The [history-cost diagnostic](../artifacts/implementation/standing-host-history-cost/RESULTS.md)
separately completes 32 prepared-only settlements under the original bound,
with 2,176 mutation validations and three retained shared claims. Its measured
wall spans point to catalog/authority work as well as history growth. This run
neither fills the partition nor passes the failed capacity profile. Current
storage reads, authority checks and durability barriers remain unchanged.

The [selection-reuse candidate](../artifacts/implementation/standing-host-selection-reuse/RESULTS.md)
then reduces repeated installation validation inside private compilation without
changing storage writers or durability barriers. Nine native management and
freshness cases pass, including late evidence/artifact withdrawal, shared claims
and prepared-mutation recovery. The subsequent
[original capacity run](../artifacts/implementation/standing-host-selection-capacity/RESULTS.md)
uses that exact host and still fails the thirty-second wall bound. It retains
110 settled never-handed-off STARTs, one prepared START and all three claims.
Its 63,046-check retained-data audit passes; the workload remains failed, with
no complete final native snapshot or 128-record qualification. Reduced call counts
and different interrupted prefixes do not establish a general timing improvement.

The [candidate's logical bound](../artifacts/implementation/standing-host-deployment/CAPACITY-REVIEW.md)
now partitions the original 16 MiB across all installed finite, standing, fixed and
route records. Ordinary writers cannot borrow another owner's continuation
partition. Purpose-specific finite event slots and bounded standing rows retain
loss/recovery headroom; unknown writer tables refuse at the shared transaction
boundary. A passed control fills eight ordinary finite events through the trusted
writer boundary, verifies ninth-write rollback, and then commits the four reserved
cancel/acknowledge/terminal/release continuations. This is a specific reserve-edge
check; full partition boundaries, SQLite/rollback-journal allocation and backed
physical capacity remain unqualified.

The isolated [compact-bitmap candidate](../artifacts/implementation/compact-bitmap-store/README.md)
uses a separately identified on-disk profile while retaining full in-memory maps,
strict canonical validation, current identity checks and all native/provider
sync barriers. Its 329 focused checks pass, including sparse maximum files,
bitmap boundaries, malformed metadata and interrupted publication/recovery on
clones. The exact prior native controls are revalidated, not rerun.

The paired 426-operation screen preserves full bodies, normalized metadata and
logical results. It observes 12,588 versus 12,012 fsync calls and 7.877 versus
7.508 seconds wall time; these finite observations establish no general speedup.
The original 4,270-file / 35,508,922-byte writer still times out at 180.114 wall /
39.074 CPU seconds within unchanged 128 MiB geometry. No dependent cold reader runs.

The independent audit verifies 35 retained images without changing backing bytes.
The interrupted writer contains 1,814 complete files / 7,800,513 bytes and all
169 directories, with no extra published file, pending entry, incomplete inode,
unlinked inode or partial progress tail. The first audit's erroneous empty-test-
stderr expectation and its exact reviewed correction are both preserved. All
19 workload children and both audit children are reaped with absent groups.
All 244 public inputs remain exact; no candidate is installed.

The earlier [full-workload attribution](../artifacts/verification/full-storage-attribution/README.md)
locates repeated fsync and provider-verification costs under intrusive tracing.
The new [existing-state overwrite hypothesis](../artifacts/verification/state-overwrite-hypothesis/README.md)
examines replacing an already valid native state file through its own commit.
Creation must retain staging because a new named file can become durable before
its body. This is source analysis only: modeled torn-write/erase cuts, native
consistency and compaction, exact old-or-new outcomes and a fresh complete replay
remain prerequisites to a materially changed candidate. An [unexecuted replacement
draft](../artifacts/implementation/existing-state-replacement/STATUS.md) now retains
the proposed finite in-memory model. Automatic review stopped its delegated
preparation; no model, native test or full replay ran, and no result is claimed.

The separate [hub recovery increment](../artifacts/implementation/owned-hub-recovery/RESULTS-REVIEW.md)
tests terminal-commit syscall-boundary exceptions and interrupted process cleanup.
The [owner-death harness](../artifacts/implementation/owned-hub-crash-harness/README.md)
also checks conservative recovery after actual process death. These tests neither
reserve storage capacity nor replace physical power-loss/aggregate-writer evidence.

Complete filesystem/SQLite behavior, temporary-file confinement, pre-recovery
capacity checks, every-writer aggregate enforcement and actually backed control
continuations remain required. Logical byte limits and passing component checks
do not supply those guarantees.

The [qualification-library installation](qualification-libraries.md) now places
the verified vault and publication code in the main project. Five original
held-vault commit checks join the public suite, which passes all 866 tests.
This preserves evidence validity through commit; it does not add aggregate
storage enforcement or backed control capacity. Public qualification mounting
still requires the complete storage and recovery profile described here.

The [main-runtime foundation](../artifacts/implementation/runtime-pat-foundation/README.md)
now includes the verified business-commit checks and opt-in compact SQLite layout,
with 861 passing runtime tests. A smaller page layout does not enforce aggregate
storage limits or back capacity owed to admitted operations. Public qualification
still requires that storage provider and an explicit control-only recovery mode.

The [authority-vault catalog](../artifacts/implementation/pat-vault-catalog/README.md)
now connects the separate evidence store to catalog promotion and deterministic
admission, with 19 passing controls and a complete thirty-case worker-to-application
flow. Evidence acquisition precedes the authority transaction; final commit checks
use bounded control reads and the held view. Backed capacity reservations, aggregate
filesystem enforcement and public mounting remain unfinished. Earlier notes below
describe the progression of individual storage and qualification stages.

The [vault batch candidate](../artifacts/implementation/pat-vault-batch/README.md)
passes 60 controls for complete multi-manifest read views and commit-time validity.
It charges every reference against an aggregate logical budget before fetching
selected bodies, while sharing identical immutable bytes. These bounds do not
reserve physical capacity or measure Python heap use. Catalog wiring, backed
capacity and aggregate filesystem enforcement remain unfinished.

The [business commit candidate](../artifacts/implementation/pat-business-precommit/README.md)
passes 51 controls for held-evidence checks immediately before a business commit.
Rollback preserves the independent clock floor, and a lost commit reply preserves
original-key replay. This supplies a tested transaction boundary; the catalog
still needs to register its complete evidence view. It does not reserve storage
capacity or enforce an aggregate quota.

The latest [actual authority-vault scope](../artifacts/implementation/pat-integer-canonical/README.md)
now passes the complete worker/import and cold-history path. The authority occupies
690,176 bytes and the vault 15,448,064 bytes, with every body/reference verified.
The 280,576 bytes remaining below the vault cap are unreserved headroom; the passing
trial establishes neither backed control capacity nor aggregate filesystem quota.
Those requirements and catalog wiring to the new commit check remain.

The preceding [native process diagnostic](../artifacts/verification/pat-native-worker-accounting/README.md)
verifies 3,960 retained files and four unchanged source databases under 55 original
owner/writer locks. Its full qualification still times out before import; no
interrupted case database is opened or repaired. Resource counters do not prove
filesystem waiting or backed capacity. Evidence/control isolation, aggregate
quota enforcement and capacity owed to admitted operations remain unfinished.

The [native supervisor candidate](../artifacts/implementation/pat-native-supervisor/README.md)
now executes scans through a verified sealed memory image. Its complete actual
worker still times out before import. The separate vault stays empty, and retained
state is audited under original owner/writer locks. This integration neither
enforces a hard filesystem quota nor supplies protected control capacity.

The [in-process metadata binding](../artifacts/verification/pat-native-retention-binding/README.md)
now passes 43 production-build controls, 20 separately instrumented controls and
three syscall scopes, including real descriptor pressure and signal cleanup.
It strengthens directory checks but remains isolated. It neither enforces a hard
disk quota nor completes protected control capacity or actual-worker import.

Status: required design, with bounded SQLite observations, 2026-11-08. The current
runtime does not yet implement protected control capacity or a qualified aggregate
quota provider. [Review and evidence](../artifacts/verification/pat-storage-capacity/README.md).

The first [independent vault candidate](../artifacts/implementation/pat-evidence-vault/README.md)
now implements bounded immutable manifests and owner-held current read snapshots
in a separate database. All 22 distinct methods have passing receipts, with the
original failed scopes retained. It preserves the complete retained I/O dataset
under a 15 MiB vault cap. The [authority-publication candidate](../artifacts/implementation/pat-vault-authority/README.md)
now connects administrator-owned installation, durable original import intents,
the existing semantic reducer and atomic reference publication under a held
snapshot. All [25 selected current-production controls](../artifacts/verification/pat-vault-authority-controls/README.md)
pass in separate scopes. Actual-run validation through this profile remains
incomplete; no physical capacity reservation or public mount is supplied.
The [fresh actual trial](../artifacts/implementation/pat-vault-original-run/README.md)
reached its original worker deadline before import and left the installed vault
empty. It supplies no complete actual-run qualification for this profile.

The [subsequent worker diagnostic](../artifacts/verification/pat-vault-worker-profile/README.md)
also stops before import. Its source databases and retained bytes pass a read-only
audit; the partial worker databases remain unopened. Profiling supplies an
optimization lead, not a passing vault-import or capacity result.

A [subsequent pure validator comparison](../artifacts/verification/pat-validation-walk-evaluation/README.md)
passes 468 differential cases but yields insufficient timing evidence for adoption.
It changes neither the storage profile nor the actual-run qualification status.

The [topology/proof-build candidate](../artifacts/implementation/pat-io-proof-batch/README.md)
passes 63 pure controls but its actual worker also times out before import, leaving
the installed vault empty. Its verified retained state remains distinct from a
complete import, catalog integration or backed control capacity.

The [whole-worker accounting scope](../artifacts/verification/pat-worker-accounting/README.md)
now records separate parent and child CPU usage, with unchanged project code and
storage bounds. It still fails before import and retains an empty installed vault.
Its verified measurement association does not supply the missing complete import,
aggregate quota, reservation or catalog commit integration.

A [native metadata-scan prototype](../artifacts/verification/pat-native-retention-prototype/README.md)
now passes isolated differential and syscall controls with reduced local CPU cost.
It is not integrated. Faster logical-size observation does not enforce a disk quota
or reserve capacity; those storage obligations remain unchanged.

A hub that runs the agent also stores observations, images, qualification results
and learned PATs. Those workloads must have bounded storage separate from the
capacity owed to ongoing device and driver operations. An accepted motor movement,
PWM burst or driver transition still needs its completion, cancellation and
recovery records when evidence ingestion runs out of room.

The proposed profile separates two durable stores:

| Store | Contents | Behavior when unavailable |
|---|---|---|
| Control authority | Operation identities, ownership, configuration, recovery state, import intents and published references | Refuse work that cannot be recorded; retain unknown outcomes and use the independently qualified local stop/fallback path |
| Bulk evidence | Exact observation/qualification bodies, references and sealed manifests | Refuse new evidence-dependent PAT selection or promotion; preserve access to already admitted control work through explicit control-only recovery |

The design uses separate connections and publishes an authority reference only
after the complete evidence manifest is durably sealed. A crash between those
steps leaves retained, unpublished evidence associated with the original intent.
Reconciliation finishes that same import; it does not launch another worker.
Current-body verification and original-run identity remain mandatory. Missing or
corrupt evidence is unavailable evidence, not a new situation for the agent to
silently relearn or retry.

Each store needs an enforced allocation ceiling, and all writers need aggregate
block/inode accounting that includes journals, temporary files and artifacts.
Admission additionally needs backed capacity for the bounded remaining writes of
accepted work. A quota caps usage; it does not by itself reserve physical space.
Limits must be checked before startup/recovery mutations and after reopening.
The [detailed design](../artifacts/verification/pat-storage-capacity/DESIGN.md)
defines publication states, the proposed evidence snapshot contract and acceptance
work. It is not an implemented deployment guarantee.

The current passing simulated catalog database is 16,199,680 bytes. A read-only
audit attributes 15,440,896 bytes to compact evidence and 758,784 bytes to other
authority btrees. Its remaining 577,536 bytes below the file ceiling are not
reserved capacity. Five small host experiments demonstrate why page caps,
freelist observations and journal retention limits are insufficient on their own.
All original runtime state remains unchanged.

This storage requirement is part of [unified I/O, driver and hub control](io-driver-hub-control.md)
and the [prompt-to-PAT path](prompt-to-pat.md). It does not replace endpoint
watchdogs, bounded local controllers, qualified OS providers or physical testing.
