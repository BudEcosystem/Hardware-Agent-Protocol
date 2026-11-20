# Multiple installed adapters under one authority

This is a source-derived implementation proposal against the retained 289-test
baseline. It is not an implementation, a new test result, or physical
qualification. Production files were not changed by this review.

## Minimal durable model

Use `binding.adapterId` as a unique installed route identity, not a driver-kind
label shared by different endpoints. Persist an append-only installation catalog
in `authority.db`, for example:

```text
runtime_installations(
  adapter_id PRIMARY KEY,
  profile, descriptor_digest, descriptor,
  active_for_new_admission
)
```

The canonical descriptor contains a supported built-in backend profile, exact
host-instance to primitive map, type/argument/resource contracts, and either a
generated private plant-store key or expected compact identity/manifest/clock
profile. A stream FD is a process attachment and never persistent identity.
Do not accept an executable import path, arbitrary filesystem path or model
supplied configuration through `prepare`/`invoke`. The installation seam stays
trusted provisioning. A descriptor cannot change under an existing adapter ID;
a replacement needs a new identity plus explicit binding transitions.

The existing immutable `reg_binding_history(instance,generation)` already pins
the route of an operation. Resolve `op.intent.instanceId` and
`op.intent.bindingGeneration` there, verify the stored type digest, and select
that historical record's adapter ID. Do not select the current binding when
reading results, canceling, reconciling, or routing retained operations. This
avoids changing generic Journal admission format. An optional materialized
operation-route index must be populated in the admission transaction and be
validated against that immutable historical record.

Keep `claims` and `resource_floors` scoped by deployment/resource, as today.
Making them route-local would permit two adapters to control one shared
workspace concurrently. Route IDs and global physical-resource identities are
different concepts.

## Required storage changes

| Current state | Required route scope |
|---|---|
| `ep_state(singleton=1,document)` | One state document per adapter ID: boot, context, tx/rx, fences, clock anchor, arm-pending, fault |
| `ep_commands(operation_id,...)` | Add route identity; retain globally unique operation ID; every slot/result/retirement lookup checks route |
| `ep_packets(id,direction,boot,sequence,wire)` | Add route identity; tx/rx sequence continuity is per endpoint; a globally ordered storage ID is still acceptable |
| One plant file and fixed device IDs | One protected store per installed plant or explicitly route-keyed tables; exact descriptor digest stored/checked; aliased host instances map to installed primitive kinds |
| Runtime `_pending`, `_streams`, `_last_sample` | Owned by each backend/route object or keyed by route in every access |

Migrate legacy compact tables in one SQLite transaction, preserving exact
payloads, receipt bytes, mapping documents, counters, retired flags and packet
order. Assign them only to the unambiguous legacy adapter ID. Verify every old
operation's historical binding agrees. A conflicting catalog, ambiguous owner,
unknown table version or unmatched mapping must refuse migration, not reset
state. Existing SQLite plant data and session must also remain intact. Record
schema/version metadata and test rollback at migration interruption points.

New route-specific plant filenames need the same protected-path checks as the
current fixed files. `private_state_directory` currently checks only
`authority.db` and `simulated-plant.db` plus their sidecars. Generate names from
an installation key/digest and validate each file, owner file and SQLite
sidecar for symlinks, hard links, ownership and mode before opening. Do not
silently weaken that existing protection.

## Runtime and adapter changes

`Runtime` owns `adapters[adapter_id]` and a persisted catalog. The installed
support callback selects the catalog's exact route from the current binding
for new admission; it never installs code from a description. Each backend
implements support checking, refresh, a bounded scheduler step, result lookup
and close. Result lookup remains possible when transport is unavailable.

Add a Runtime-owned work query joining operations to immutable binding history
and filtering adapter ID **before** ordering/limit. Keep the generic Journal
independent of Registry-specific tables. Filtering the first global 64 rows in
Python can permanently starve a route whose work is later in the ledger.

Replace every compact global scan: `_fault`'s running/dispatching operations,
expiry handling, missing-mapping checks, active-slot queries, accepted work,
sample restoration and presence deletion. `_row`, `_settle`, `_retire` and
`result` must reject a mapping belonging to another route. A bad endpoint must
not mark another endpoint's operations unknown, delete its presence or consume
its call/fence counters. Apply the same selection to local plant pending work,
unknown reconciliation, terminal claim release and result lookup. Evidence
source becomes the exact route's adapter ID and still checks historical
bindings through `RegistryPolicy.evidence`.

The current local primitive implementations key behavior directly by three
literal instance IDs. Parameterize installed instance-to-kind/resource/frame
maps, and preserve the actual primitive limits separately from permissive
registry schemas. Renaming two microscope IDs while retaining the same
coordinate frame would make their descriptions misleading. Generate exact
per-instance frame contracts or introduce an explicit binding frame mapping.

The current native C fixture already accepts `--incarnation`, `--manifest` and
`--firmware`. Two synthetic endpoints can therefore use distinct incarnation
bytes without changing the C executor. Keep the manifest/enrollment relation
explicit: derive a canonical per-route simulation manifest with the unchanged
supported primitive semantics and matching digest, or version the host profile
to separate a capability-template hash from enrolled endpoint identity. Do not
silently contradict the original manifest's embedded incarnation field.

## Restart, offline routes and fairness

The Journal's process-owner restart still legitimately marks all previously
dispatching/running operations unknown. Adapter recovery after that transition
must be route-local. A missing stream is an offline route, not permission to
autoformat, relaunch, rebind or select another handler. Keep its stored results
readable, preserve unknown claims and prevent new admission by clearing its
presence and refusing support while detached. Accepted but undispatched work
may wait until its declared start deadline or be explicitly rejected according
to documented policy; never turn missing transport into an uncertain handoff.

Round-robin routes and catch/report failures per route. One route's refusal
must not prevent later route steps in the same scheduling round. Within a route,
an early future operation must not block an eligible operation using independent
resources: select eligible starts before applying the small dispatch limit,
while separately expiring accepted work. Preserve one retained slot per compact
endpoint, not one slot across all endpoints.

Functional coexistence does not establish adapter isolation. Current compact
exchanges can wait 0.5 seconds by default (up to two seconds configured), and
`_arm_for` holds the shared authority mutex through ARM exchange. Per-route
threads alone therefore do not protect other routes' latency. Bounded sequential
steps can demonstrate eventual progress with an explicit limitation. Stronger
deadline/blocked-adapter claims need supervised or split send/receive I/O and a
durable handoff protocol that preserves authorization and cancellation ordering
without holding the global authority lock across response waits.

## Required behavior checks

1. Two local installations with distinct instances and independent state/results;
   two compact processes with distinct enrolled identities/context digests; local
   and compact routes in the same deployment.
2. One route's missing stream, timeout, malformed reply, reset or disputed evidence
   cannot alter another's presence, counters, mappings, claims or result.
3. Queue more than 64 operations on one route and place another route's work later;
   verify selection before the limit. Put future work ahead of eligible work.
4. Shared resource identities still conflict across different routes. Same-key
   replay, changed-payload rejection and full host fences remain unchanged.
5. Host crash after one endpoint's acceptance: exact operation recovers by QUERY
   on that endpoint only, no OP retransmission, while the other route progresses.
6. Reopen with one FD absent; historical results remain readable and uncertain
   claims retained. Swapped FDs fail identity checks before BIND/ARM/OP. Reattaching
   the same route cannot reset its durable sequence/context state.
7. Reject duplicate route IDs/instance IDs, unsupported profiles, descriptor drift,
   unsafe store paths and migration conflicts without creating or rewriting plant
   state. Rollback an interrupted legacy-table migration.
8. Preserve owner/action authorization, private state-directory checks, exact
   `claim_dispatch(...,_reserve=...)` transaction semantics, and the current
   pre-ARM state/timing/authority ordering tests.

These checks establish only the implemented synthetic profiles. Remote/per-agent
authority, untrusted driver isolation, physical clocks/NVM/UART, independent stop,
and arbitrary third-party adapters remain distinct work.
