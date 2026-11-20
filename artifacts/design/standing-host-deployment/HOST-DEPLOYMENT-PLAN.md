# Durable host standing deployment

Status: source-grounded implementation plan, not implemented or executed. This is
the next host half of the existing standing controller, not a replacement endpoint
design. Public inputs and sealed packets remain unchanged. [SOURCE-EVIDENCE.json](SOURCE-EVIDENCE.json)
records hashes and the actual source ranges consulted; partial reads are explicit.

The smallest coherent increment is a single installed standing-kernel deployment
over one explicitly selected endpoint route, with durable host identity, shared
finite/standing resource ownership, renewal, activation collection and recovery.
It must use the actual version-2 controller protocol and retain its original
requests. A separate standing PAT parser/compiler supplies its immutable program
and qualification identity. A finite OP loop, renewed ARM, a catalog entry alone,
or a second independent resource lock table cannot implement this contract.

Existing APIs provide useful local transaction and evidence mechanisms, but do
**not** permit this deployment unchanged. In particular, claims currently reference
finite operations, PAT instances require finite procedures, and the installed
compact route speaks version 1. No existing service supplies a backed reservation
for all future control-storage writes. The initial executable implementation can
therefore establish host lifecycle semantics with the original native synthetic
endpoint and an explicit local SQLite storage contract. It cannot honestly expose
physical standing deployment, protected aggregate capacity or the current AVR
image as supported.

## Current facts and concrete reuse

The authoritative [progress](../../../PROGRESS.md) records a final native standing
pass and failed ATmega328P fit: 43,646 flash-load bytes, 10,878 bytes beyond physical
flash, and 168 new static bytes against the proposed 160-byte ceiling. The
[controller results](../../implementation/standing-endpoint-controller/RESULTS-REVIEW.md)
and [version-2 wire](../../implementation/standing-endpoint-controller/WIRE.md)
supersede prospective statements in the sealed design. Use the implemented
66-byte response prefix, echoed request sequence and 124-byte state page; do not
implement the older 62/128-byte proposal.

| Existing source and exact location | Reuse | Required change or limit |
| --- | --- | --- |
| `hms/journal.py:174–255,272–389` | One POSIX owner, authority/owner epoch, short transactions, DELETE/EXTRA SQLite mode, pure final commit checks | New opt-in storage profile; conservative standing recovery. EXTRA is a configured durability mode, not a proof of future disk space or physical power-loss behavior. |
| `hms/journal.py:570–665` | Original-key lookup before new admission, all-or-nothing claims/fences, committed dispatch mapping before I/O | Generalize claim ownership; add standing reservation/outbox APIs rather than extending finite timing or calling `submit` with an invented operation. |
| `hms/journal.py:163–166,798–807` | Existing exclusive resource key and evidence-gated finite release | The current foreign key is `operations(id)` and finite terminal release rules do not express standing ownership. |
| `hms/resource_topology.py:372–407,439–463` | Exact binding proof, transitive aliases, full affected consumer set for generation changes | Resolve acquisition, output, local clock/transport, driver lifecycle and declared hub/storage dependencies. The graph alone grants no reservation or physical capability. |
| `hms/resource_catalog.py:242–262,278–327` | Current/historical proof equality and atomic quiescent generation publication | All claim lookups, including joins through `operations` at lines 98 and 312, must include standing owners. This API still does not execute a driver restart. |
| `hms/registry.py:440–483,739–891` | Authenticated policy, current binding/presence/action/argument checks, pure installed resource resolver | Add a distinct standing policy and update the finite-only binding claim join at line 456; current policy is finite and explicitly refuses non-simulation bindings and physical evidence. Do not weaken that refusal. |
| `hms/runtime.py:51–168,201–277,362–397,451–520` | Installed routes, route serialization, explicit request allowlists, per-route failure isolation | New opt-in coordinator/mount and methods. Current threads/20 ms waits have no hard service bound and the ordinary route must not issue v1 HELLO while standing owns the endpoint. |
| `hms/endpoint_binding.py:148–189,468–508,529–677` | Reserve exact bytes and association before exchange; validate monotonic evidence; recover by original identity | Sibling standing route, not subclassing v1 HELLO/ARM assumptions. Do not retain every polling packet in the unbounded `ep_packets` pattern. |
| `hms/endpoint_transport.py:17–95` | Fixed original AF_UNIX stream, bounded exchange, response correlation, no internal write retry | Source reuse for a native fixture only. It does not open a serial device, authenticate physical hardware, or launch a replacement endpoint. |
| `hms/endpoint_wire.py:12–33,191–239` | Strict typed frames, fixed bounds, pure codecs | Separate version-2 request/response codecs. Existing `Request` rejects version 2 and cannot be reused as-is. |
| `hms/pat_contracts.py:1–120`, `hms/pat_execution.py:23–76,309–365` | Closed typed values, immutable selection provenance and replay-before-selection principle | Both profiles are finite/simulation-only; `px_instances.procedure_id` is mandatory. Introduce a standing profile/store, retaining the old refusals. |
| `hms/pat_bindings.py:26–191`, `hms/pat_compiler.py:285–370` | Complete installed inventory, typed domains, driver/installation/binding provenance | New standing descriptors and compiler. Existing compiler environment excludes endpoint session from evaluation identity; a running deployment must separately pin current boot/session and authority. |
| `hms/pat_catalog.py:483–545` | Evidence-dependent eligibility, immutable promotion decisions, retained admitted versions | Standing evaluator and policy; catalog suspension inhibits new deployment/extension but is not evidence an existing endpoint stopped. |
| `hms_qualification/vault_recorded_io/execution.py:40–104`, `bridge.py:165–208,235–257` | Complete relevant evidence inventory, held snapshots outside the authority transaction, pure commit-time revalidation, replay without fresh vault access | Reuse this pattern with a separately versioned standing evaluation; these concrete classes parse finite PATs and cannot accept standing receipts unchanged. |
| `hms_qualification/supervisor/io_service_execution.py:230–302` | Original reservation/attempt association committed before launch; recovery never silently launches another original run | Qualification remains off the renewal/control path. This service executes finite I/O qualification, not standing endpoint applications. |
| `hms_qualification/supervisor/worker_entry.py:1–74` | Fixed original worker image and bounded controlled execution | Current worker calls `run_io_group`. A standing evaluator needs its own installed original worker and evidence matrix; no caller program, module, path or subprocess command. |
| `hms_qualification/evidence_vault/connection.py:16–125`, `store.py:181–265` | Independent immutable byte store, strict capacity limits, checked read snapshots | Page/record caps do not reserve aggregate filesystem space; hot-journal startup currently refuses. Do not use this immutable qualification vault as the live ACK ledger. |
| `hms_qualification/evidence_authority/store.py:1–85` | Separate import intent, independent seal, authority publication, explicit lock ordering | Imports accept original evaluator/run names and do not grant PAT eligibility or control-write capacity. |

## One isolated integration, with one resource authority

Prepare `artifacts/implementation/standing-host-deployment/` from exact source
copies. Introduce a fresh, opt-in `hms-ledger/standing-host/0.1` database profile.
The public factories and old Journal must refuse it. No automatic migration of
existing authority databases is part of this increment.

In that copied profile, add `resource_owners(id, kind, principal, deployment)` with
closed kinds `finite_operation` and `standing_deployment`, and
`resource_owner_instances(owner_id, instance_id)` for every affected instance.
Generalize the existing single `claims` table to reference `owner_id`; retain its
unique `(deployment, resource)` key and the existing `resource_floors`. Finite
operation admission atomically creates its owner and claims exactly as before.
Standing admission creates a different owner in the same transaction. Unknown or
quiescent-but-retained standing records continue to own their claims.

Update every copied direct claim query/release and per-instance binding guard,
not only the friendly standing API. Finite `claim_dispatch`, cancellation,
terminal release, endpoint settlement, Registry binding, ResourceCatalog creation
and generation publication must use the common owner helpers. Audit SQL call
sites and test both directions of finite/standing alias conflict. A higher fence
never displaces a holder. The first endpoint profile also claims one installed
endpoint-slot atom, so retained finite and standing records exclude each other
even if their peripheral masks would otherwise be disjoint.

Keep logical exclusive atoms distinct from quantitative storage/CPU reservations.
Structural hub containment must not lock the whole hub. An active controller
retains the dependencies needed for acquisition, output, authority enforcement and
loss handling; a driver/hub change must check the complete affected owner set and
cannot publish a replacement generation while those obligations remain.

## Closed host records and API

These are proposed implementation ceilings, not measured memory or disk quotas.
Installation fixes one route, one live standing deployment, at most 16 retained
deployment keys, 256 ordinary activations per deployment, 128 retained host
mutation intents (including refused intents) and 32 retained loss/lifecycle episodes. Refuse before counter/retention
exhaustion; no LRU deletion or reset through renewal. A deployment is renewable
within these admitted cumulative limits, rather than a promise of unlimited
offline operation. Smaller test bounds exercise exhaustion without long runs.

All JSON documents use exact keys, strict integer types, canonical bytes and
domain-separated digests. Booleans/floats cannot pass integer checks. A compact
u64 endpoint tick is retained as eight bytes or a canonical decimal string when
outside the existing JSON-safe integer range. No truncation/hash substitutes for
boot, counter or input epoch identity.

| Proposed durable record | Required contents and bound |
| --- | --- |
| `sd_installation` | Installed route, codec/compiler/provider identities, firmware/manifest/incarnation, kernel/schema, source epoch mapping, clock model, topology closure, host management/storage contracts and evidence mode. Exact immutable installation, at most 64 KiB; caller cannot choose descriptors or executables. |
| `sd_deployments` | Principal/authority deployment/original replay namespace/key, immutable request digest, selected PAT/evaluation/decision/compiler and exact binding evidence, host owner, admitted limits, endpoint namespace, exact 134-byte OPEN, lifecycle knowledge and uncertainty flags. Immutable bundle at most 64 KiB. |
| `sd_mutations` | Host deployment, immutable host mutation key, proposed endpoint sequence, exact 66-byte typed body, expected endpoint revision, admitted effect/lease/ACK bound, retained frame association, commit/handoff/reply knowledge and evidence references. At most 1 KiB per row and one unresolved ordinary mutation. Accepted endpoint sequences are unique; OPEN has a separate retained original reservation. |
| `sd_activations` | Full `(incarnation, boot, standing, activation)` identity, exact 44-byte record, original response frame/receive identity, typed outcome, previous versions needed to show pending→terminal, supporting loss witness where required, and prefix eligibility. At most 1 KiB per admitted activation; conflicting terminal bytes latch dispute. |
| `sd_episodes` | Original state/ownership/loss summary, full aggregate witness and its association to the installed predicate, immutable collected bytes, resume/retire references. At most 2 KiB per episode; witness validity is not inferred from output value. |
| `sd_route_state` | Boot/session, current installed control binding, allocated/observed standing and fence floors, TX/RX high-water, bounded clock witness, transport-fault state and current owner. Fixed-size replacement record; diagnostic samples use a 16-entry bounded buffer rather than an append-only packet history. |
| `sd_capacity` | Accounted logical charges and separate ordinary/loss continuation reservations joined to the installed capacity provider and owner. This row is accounting, not proof of physical reservation. |

The aggregate initial logical record budget is 16 MiB, including retained keys,
indexes/encoding allowance in the accounting model and explicit loss reservations.
The implementation must publish and test its exact charge formula before execution;
the ceiling is not a claim that SQLite fits in that many allocated bytes. Ordinary
mutation admission must preserve eight reserved control records and eight episode
records for the reviewed loss/ACK/retire path. Demonstrate that this reserve covers
the selected one-owner/two-event endpoint's maximum owed continuation; if the
calculation fails, reduce admission or revise the profile before tests. Repeated
exact requests reuse their retained record and cannot consume the reserve again.

The installed service exposes `standing_prepare`, `standing_deploy`,
`standing_status`, `standing_events`, `standing_suspend`, `standing_resume`,
`standing_stop` and `standing_reconcile`, with closed typed requests. Preparation
is read-only and reserves nothing. `deploy` selects an eligible standing artifact
from a complete installed inventory and stores its exact selection. It does not
accept raw OPEN bytes, fences, provider paths or caller-supplied evidence. Renewal,
STATUS collection, ACK and RETIRE are installed coordinator work, not model tools
that let a caller assert evidence was committed. Explicit installation/admin
authority remains separate from application invocation authority.

The deployment request has exactly `protocol`, `replayNamespace`, `deploymentKey`,
`taskKind`, `inputProfile`, `parameters`, `evidenceMode` and `limits`. Limits have
exactly `activationCap`, `commandedOnMs`, `mutationRecords`, `episodeRecords` and
`leaseHorizonMs`, all strict positive integers at or below installation/artifact
bounds. Parameters are limited to the declared typed kernel domain. The initial
test profile accepts only `evidenceMode=simulation`. Explicit lifecycle requests
carry the deployment ID, stable control key and expected host control revision;
the coordinator constructs the endpoint mutation, including fixed reason codes.
No public API accepts an arbitrary endpoint mutation sequence or ACK watermark.

A definitive BAD_REVISION refusal does not consume an endpoint mutation sequence.
Preserve the refused host intent; a fresh request with a new host mutation key may
use that still-unconsumed sequence only after the serialized transport establishes
the original request was refused and has no unresolved handoff. Never rewrite the
original body or reuse an uncertain sequence with different bytes. A new read of
STATUS alone cannot turn an ambiguously sent old request into a definitive refusal.

Historical replay authenticates result access and looks up the retained deployment
key before current catalog, source, clock, device or storage readiness. Compare the
original request bytes/digest; changed content conflicts. Copy replay namespace and
owner into the retained key without a deletion cascade from finite namespace
pruning. Expired/pruned namespaces cannot admit a new deployment but cannot erase
retained standing identity or make its original key create another effect. Status
by deployment ID remains subject to read authority. Initial fresh-key checks must
also reject collisions with finite procedure/operation/PAT keys.

## Host state and handoff ordering

Endpoint lifecycle and host knowledge are separate fields. Host states are
`RESERVED`, `OPEN_UNCERTAIN`, `PREPARED`, `START_UNCERTAIN`, `ACTIVE`,
`SUSPEND_PENDING`, `DRAINING`, `SUSPENDED_COLLECTED`, `STOPPED_COLLECTED`,
`RETIRE_UNCERTAIN`, `RETIRED` and `RECONCILE_REQUIRED`. These names do not override
the endpoint's PREPARED/ACTIVE/DRAINING/SUSPENDED/STOPPED/FAULT state. Keep
`everPossiblyActed`, unresolved acquisition/output intervals, disputed evidence,
held claims and known quiescence independently; PREPARED may perform bus effects.

1. Outside a transaction, acquire the installed evidence/capacity handles and a
   bounded, read-only DESCRIBE bracket. Validate both descriptor pages against the
   exact installed identity and qualified boot, kernel, source epochs and limits.
   Pages are time-separated observations, not an atomic snapshot. Initial BIND is
   a separately admitted installation action and must refuse occupied state.
2. In one short authority transaction, recheck current policy, catalog/binding
   evidence and complete resources; allocate host owner/fences and a non-reused
   endpoint standing namespace; reserve owed record capacity; retain the complete
   deployment and exact OPEN. Register pure final checks on the already held
   evidence handles. Commit before any OPEN byte: OPEN itself begins acquisition.
3. After commit, take fresh clocks and current local authority veto checks; send
   the exact committed OPEN once, outside the SQL transaction, through the single
   route executor. Retain possible-handoff knowledge before send. Late, partial or
   lost exchanges become unresolved; they do not regenerate OPEN with fresh times.
4. Validate and commit the response. Before START, collect current bound state
   and fresh input pages, recheck the original baseline, authority, evidence mode,
   budget and installed dependency closure. Commit a separately admitted exact
   START mutation before its handoff. New input bytes do not rewrite deployment
   parameters or qualification identity. The local endpoint repeats its guards.
5. While ACTIVE, the deterministic coordinator collects bounded pages and renews
   only within the existing lease, current installed maximum horizon and admitted
   lifetime/output limits. A renewal changes only the absolute authority interval;
   it never resets activation accounting, input epochs, history or configuration.
   Commit exact RENEW bytes before handoff and check freshness again after commit.
   Host scheduling delay can cause refusal/loss; it cannot justify a later deadline.
6. Suspend/stop is admitted against the same retained owner. Acknowledgement means
   accepted intent, not quiescence. Retain claims through drain, evidence collection
   and RETIRE. RESUME requires a collected eligible suspended episode, unchanged
   context/epochs/ownership and complete eligible ACK prefix; it prepares a new
   lease, then a separate START uses fresh acquisition. Source drift, revoke,
   unknown outcomes and unsupported causes cannot be cleared by RESUME.

Use an explicit lock order: installed evidence/capacity ownership, route executor,
then short Journal transaction. Do not perform transport, vault acquisition,
source-file reads or worker execution inside a policy/commit callback. Do not
hold the authority mutex over a blocking exchange merely to simulate an atomic
distributed transaction. Authority withdrawal latches locally, blocks fresh work
and uses the installed endpoint revoke/loss path; endpoint lease/fence/cutoff
enforcement remains necessary during the host check-to-send interval.

## Commit-before-ACK collector

Read STATUS state and then the at-most-two retained activation pages. Validate
identity, opcode/echoed sequence, boot, resource ownership, counters, typed flags,
source epochs, acquisition ordering and exact installed evidence semantics. Store
each page with its own frame and observed revision; sample/pending-feedback changes
do not necessarily advance lifecycle revision. Never fabricate a simultaneous
snapshot by matching only that revision.

Only a contiguous eligible prefix above the durable watermark may be collected.
Pending, unknown or disputed activation records block the prefix. The implemented
FEEDBACK_INTERRUPTED state remains possibly acted and unverified; it is eligible
only with the separately collected valid full-mask loss witness and no unresolved
or disputed loss. A successful ACK must never relabel it successful feedback.

In one authority transaction, validate/store the exact prefix and required episode,
advance `durableCollectedThrough`, and reserve the exact ACK body and expected
revision. Commit all three together. **Only after that commit returns and current
guards pass may ACK be sent.** A storage exception, lost commit reply, expired
evidence handle or interrupted process cannot send the ACK speculatively. Reopen
the same ledger and establish whether the committed prefix/outbox exists first.

Track three separate watermarks: endpoint high-water, host durable collected
prefix and endpoint acknowledged prefix. `endpointAck <= durableCollectedThrough`
must always hold. If an ACK reply is lost, STATUS can establish acceptance of the
exact retained mutation; it must not generate another activation or a higher ACK.
If endpoint ACK is ahead of durable evidence, latch a storage/history discrepancy,
retain claims and refuse normal continuation. An OLD_OR_FORGOTTEN activation below
the host's committed ACK is expected; a missing record above it is uncertainty.

Collection is the live control ledger's responsibility. Learning export to the
independent evidence vault happens afterward under its own limits and provenance.
Vault availability cannot gate an already owed stop or make uncommitted control
evidence eligible for ACK. Conversely, a vault manifest alone never proves that
the control ledger committed or that an activation achieved its physical goal.

## Reconnect, crash and retention rules

On host reopen, mark every nonretired standing owner recovery-required before
starting the route scheduler. Preserve all request bytes, fences, epochs, budgets
and claims. First reconnect operations are read-only DESCRIBE/STATUS against the
original namespace; do not initialize, BIND, OPEN, START, RENEW or RESUME as a
side effect of discovery. The endpoint may still act under its previously admitted
lease; absence of new host handoffs is not a claim of no device effects.

| Retained/observed condition | Required host result |
| --- | --- |
| Same boot/identity, exact record, known mutation comparison | Join to original deployment; collect bounded evidence. Record already accepted mutations without resending them. Normal continuation needs the declared recovery policy and fresh authority/evidence checks. |
| OPEN or ordinary mutation may have been sent, but reply is unavailable | Query; do not auto-retry an unaccepted/unknown effect or allocate a new identity. Exact retained accepted comparison can resolve acknowledgement, not manufacture missing outcome evidence. |
| An outstanding mutation's acceptance cannot be settled | Block all ordinary mutations and ACK that could reopen activation capacity. Use only the separately installed bounded-loss authority where available. A common-context REVOKE can inhibit without guessing the uncertain next standing mutation sequence. |
| Boot changed, standing record absent, identity drift, counter/epoch regression or missing suffix | Retain possible acquisition/output uncertainty and all corresponding claims. No automatic replacement deployment. A fresh empty boot is not physical quiescence of prior work. Bound any unknown suffix by the original admitted activation cap, never invent an exact recovered count. |
| Terminal prefix and quiescence committed, RETIRE may have been sent | Check same-boot descriptor/record status and retained retirement intent. Release host claims only after validated retirement, or a qualified empty-slot/old-forgotten observation joined to the complete original retirement preconditions. A bare refusal is insufficient. |
| Control store unavailable or poisoned | No ordinary admission, renewal, RESUME or ACK. Keep already held bounded-loss authority available only within its commissioned contract; the endpoint's lease/loss behavior remains independent. Report missing durable recovery evidence explicitly. |
| Catalog suspended/new revision, driver/hub/configuration changed | Preserve historical deployment/receipts. Do not silently reselect or rewrite the deployment. Current extension/start eligibility follows the declared policy; settlement uses the original installed predicate. |

Exact replay does not require current eligibility and does not relaunch. No
unknown result becomes `not_started` because a process exited, a socket closed,
the endpoint rebooted or its record was forgotten. No resource release follows
host lease expiry alone. Persistent process IDs in the hub dependency record are
association data, never recovered signaling authority.

## PAT, qualification and the intelligence hub

Add a closed `hms.pat.standing-controller/0.1` artifact for the installed kernel
only. It declares task/input profile, parameter domains and units, two input roles,
output role, hysteresis/feedback configuration, freshness/dwell/response limits,
activation/on-time budgets, evidence/outage/loss contracts, exact placement and
required device/driver/hub/storage capabilities. The compiler proves entire
parameter domains and emits a typed immutable deployment template, not an OP
sequence. Preserve the old parser's rejection of this profile.

A standing catalog evaluation needs its own evaluator/worker/profile identity and
retained case closure. The current finite `run_io_group` success is not standing
qualification. Reuse original-run association, independent immutable evidence
publication and held-evidence validation at promotion/admission. Start with one
installed reviewed artifact and one original native standing evaluator; the
ordinary selector must still reject ambiguous compatible entries or incomplete
inventory. A manual installation receipt may support a clearly labelled test
fixture but must not be relabelled a learned/passed catalog evaluation.

Separate qualified program-domain evidence from the exact live deployment
binding. Pin device incarnation, current boot/session, calibration, configuration,
source epochs, resource closure, installed driver/firmware/provider image and
current control generation at deployment. Pin the host coordinator implementation,
storage authority, OS/runtime/service contract and any selected model/inference
provider too. Renew/start must recheck live applicable generations without
rebinding the admitted identity. Unrelated hub changes should not invalidate an
application outside their declared dependency closure.

The first controller's renewal and collection work needs no model call. A prompt
or learned proposal may supply a candidate through a separate authorized compiler
and qualification path; it cannot assert evidence, choose executable code, ACK a
record, widen a driver capability or grant itself hub administration. Stable
contexts reuse the qualified artifact deterministically. Novel evidenced context
or new intent can request planning; missing observations, unavailable storage,
changed bindings and unresolved effects remain refusal/reconciliation states.

Perception or broader applications can later compose separately admitted hub jobs
and device procedures with this standing owner, retaining partial/unknown results.
The isolated owned CPU provider is useful evidence for that host effect component,
but it is not publicly mounted or aggregate-capacity-qualified. There is no current
GB10/GPU/physical-driver capability to infer from a label. A requested dependency
without its installed supported provider must refuse. Hub self-management must
retain or explicitly transfer the owner and recovery dependencies before removing
the process/service that manages this deployment.

## Storage decision and executable next action

The Journal's SQLite transactions can implement durable ordering under its stated
local POSIX/SQLite contract. A successful commit can authorize a later ACK; an
ambiguous commit cannot. The current Journal has no aggregate byte reservation,
record cap or protected completion budget, and its single authority DB is shared
with other control/catalog records. The vault's `max_page_count` and logical
limits do not cover journal/WAL/temp/metadata/allocation, other writers or future
stop/reconcile writes. The existing logical supervisor scanner expressly makes no
allocated-space/quota claim. The failed full storage replay does not prohibit a
small isolated lifecycle implementation, but it cannot qualify protected service
storage by analogy.

Define an installed `ControlCapacity` boundary before source implementation:
reserve the declared whole continuation obligation outside the authority
transaction; retain an owner-bound immutable reservation identity; check its held
validity at admission/renewal commit; and retain it through terminal settlement.
A production implementation must identify its actual backing, all controlled
writers, database/journal/temp/allocation footprint, crash recovery and service
interference bounds. A scalar free-space check, preflight charge, unrelated file
preallocation or test boolean is insufficient. If that provider is absent, report
`CONTROL_CAPACITY_UNQUALIFIED` for physical/public deployment.

For the next isolated source candidate, install an explicit
`local-sqlite-ordering-test` capacity scope: bounded records and fail-closed fault
injection, with `protectedCapacity=false` and `physicalEligible=false` in its
descriptor/results. It may exercise actual file commits and process-crash ordering
against the native synthetic endpoint. It must never emit a production capacity
receipt. This is the honest executable route available now; the production
capacity and fitting/commissioned endpoint remain independent gates.

Implement these files as one reviewable candidate: `standing_wire.py` (v2 codecs),
`standing_contracts.py` (strict deployment/mutation/evidence records),
`standing_store.py` (original keys, common owners, outbox/prefix/episodes),
`standing_endpoint.py` (single installed route and recovery coordinator), and
`standing_pat.py` (narrow parser/compiler and qualification adapter). Copy and
minimally modify Journal, Registry/resource admission and opt-in runtime wiring;
retain a complete diff and original source pins. Use the sealed standing core and
fixture unchanged where possible; a new bounded original native pipe entry can
provide its actual v2 request/response path under a fixed test schedule. No physical
port, AVR target, dynamic worker or caller-selected program is needed.

Prepare the complete slice, controls and owned bounded runner for source review
before execution. Do not begin a new full qualification/storage replay or change
the current AVR target to make this host work appear deployed.

| Proposed executable control group | Required evidence |
| --- | --- |
| Codec and exact C correspondence | All v2 shapes, lengths/reserved fields, request correlation, u64/typed bounds, state/activation/witness flags, interrupted feedback, v1 occupancy refusal; compare retained C responses rather than only encode/decode round trips. |
| Shared authority | Finite→standing and standing→finite alias conflicts through direct APIs; lifecycle/binding change exclusion while PREPARED, suspended, unknown and retire-pending; unrelated endpoint progress; common fence floors never reset. |
| Original identity and deployment | Same-key replay after catalog/source/clock disappearance returns original record without effects; changed key body conflicts; namespace expiry/pruning and 16-key exhaustion preserve historical access; no hidden new deployment on reconnect. |
| Commit ordering and real owner death | Cuts before/after deployment, OPEN, START, renewal, collected-prefix and ACK commits; instrumented child exchange proves no outbound effect before commit. Use the reviewed living guardian for actual owner-death families and retain original endpoint/host identities. |
| ACK collection | Pending/unknown/disputed/gapped records block prefix; repeated terminal bytes are idempotent and changed terminal bytes dispute; lost ACK response reconciles exact sequence; ACK-ahead-of-durable-prefix refuses; FEEDBACK_INTERRUPTED retains unverified status and requires the separate loss witness. |
| Renewable lifecycle | Expiry during host fsync/check-to-send, delayed old renewal, exhausted mutation/event budgets, complete suspended collection before RESUME, fresh observations before later START, no accounting reset, retirement release only after eligible exact evidence. |
| Reconnect and boot loss | Same-boot accepted mutation reconciliation, uncertain next mutation, endpoint reset with missing suffix, foreign owner/counter/source drift, occupied binding refusal; query/loss-only recovery produces no automatic OPEN/START/RENEW/RESUME. |
| Storage failures | Inject before/after commit and reopen ambiguous commits; logical ordinary exhaustion preserves the tested loss reserve; no ACK after failed collection; poisoned storage does not call the model or relaunch. Describe these as process/syscall controls, not power-loss or aggregate-allocation qualification. |
| PAT and installed context | A real standing evaluation receipt selects its exact kernel; finite receipts refuse; missing/ambiguous installed inventory refuses; changed driver/calibration/boot/hub provider or held evidence before commit refuses fresh work; historical settlement still uses original bindings. |

This plan is implementation-ready for the isolated host lifecycle and its native
standing endpoint controls. Production admission remains blocked on a real
control-capacity provider, fitting/commissioned endpoint and concrete physical
I/O/driver/hub providers. The broader prompt synthesis and experience-driven
qualification service must supply genuine standing evaluations before learned
promotion can be claimed; completing this host path gives those services one
durable application interface to target.
