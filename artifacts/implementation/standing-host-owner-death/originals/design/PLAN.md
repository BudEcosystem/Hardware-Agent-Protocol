# Fixed standing-host process-death controls

Status: design only. No runner or test implementation is added here. The reference
host is revision04, `SOURCE-REVIEW.json` SHA-256
`8f02d1dc5dc8724904e29c2fb2656e1c2836d6ae13b68c3fc25b849da3899878`.
Its 275 indexed files were verified as data after the author declared it stable,
and again at `history/source-freeze04` after its successor appeared. The earlier
reads of its changing draft are not an execution or qualification. Revision05's
complete patch was also read: its fixture uses the existing synthetic topology
profiles and its runner assigns fresh attempt02 provenance. Those corrections
do not alter the checkpoint methods below. Any implementation must select the
latest reviewed host version, rather than execute revision04's obsolete fixture.

## Process and descriptor ownership

Use the existing dedicated, single-thread Guardian contract. An outer owner
executes one fixed control process through a held interpreter image. The inner
control has one Guardian and runs thirteen cases sequentially. For each case it
owns three direct children: one native endpoint, one host owner intentionally
killed at a declared checkpoint, and one recovery host that exits normally.
The expected successful inner total is therefore 39 reaps: 13 native exit-zero,
13 owner exit-minus-nine, and 13 recovery exit-zero records. The outer control
process is separately joined and reaped. No child of a host owner is expected;
unexpected descendants fail the case and are settled by kernel child ownership.

The inner parent creates the two Unix socketpairs and starts the native image
before any Journal exists. Its native launch keeps only standard descriptors,
the held executable and the private native control descriptor, as in the current
fixture. It closes all host/notice/gate descriptors in the native child. The
parent retains the raw host-side wire descriptor and native control descriptor
through both host lifetimes. It does not read or write protocol bytes through
the wire descriptor while either host is alive. Keeping that descriptor open
prevents host death from being mistaken for endpoint EOF.

Each host is forked from this parent while the parent has no Journal, SQLite
connection, journal owner-lock descriptor, or active policy/catalog evidence
lease. The original host opens `authority.db` with `create=True` only inside its
child. The recovery host opens the same exact pathname with `create=False` only
after the original owner is killed and reaped. Each host constructs a fresh
LocalEndpointStream from its inherited raw wire descriptor, closes the extra raw
descriptor after duplication, and constructs fresh policy/driver/catalog/store
objects. No inherited Python Journal object is reused.

The parent and native process must never inherit a Journal opened by another
process. Journal obtains an exclusive nonblocking flock on `authority.db.owner`;
duplication of its open file description would extend that ownership after the
writer dies. The owner does not fork after Journal creation. The parent neither
opens nor repairs the database while the owner is paused. A successful recovery
Journal acquisition, with the native endpoint and parent still alive, is part of
the lock-lifetime check. Failure to acquire it is a failing retained result,
not a reason to unlink or replace the owner-lock file.

Only the parent owns the native control socket. Fixed stage messages ask the
parent to perform the known setup cycles or demand change, each while the host
is paused after a complete host method has returned and released its temporary
image/evidence leases. The selected death cut, which never resumes, is separate.
The parent waits for each exact
nine-byte native acknowledgment before releasing the host. Neither child chooses
an arbitrary native command, endpoint, path or executable. The death checkpoint
is distinct from setup stages and is matched by fixed case ID, phase and opcode.
The parent never advances virtual time or changes native state during the
read-only recovery assertions unless the case's declared stage requires it.

Before every child launch, close unneeded descriptors explicitly. Host children
keep only their one wire endpoint, stage/notice and gate endpoints, fixed log
descriptors and standard descriptors; they do not retain the private native
control socket or another case's descriptors. Native-image evidence locks held
by the parent are not Journal writer locks and must be identified separately.

## Checkpoint protocol

Use private StandingHost/StandingStore subclasses. Existing hooks suffice for
these thirteen cuts; no new wire or application-request feature is needed.
Every selected cut is after a committed transaction, or after a complete reply
was consumed, receive continuity committed and semantic decoding succeeded.
The hook verifies `journal._db.in_transaction` is false before publishing its
notice. A wrong phase, opcode, deployment, mutation number or occurrence fails.

The checkpoint writes an exclusive, bounded canonical snapshot file and fsyncs
it and its directory, then sends at most 4096 bytes through Guardian's existing
notice protocol. A deployment may exceed 4096 bytes, so the complete row must not
be sent through that pipe. The notice carries only case/phase/opcode, original
deployment and mutation identity, fixed snapshot name, byte count and SHA-256.
The original owner then blocks on a gate whose sole writer belongs to its parent.
Closing that gate on parent loss permits only a fixed failing exit, never normal
continuation past the cut.

Checkpoint snapshots are capped at 128 KiB. Read only bounded fixture records:
one deployment, at most eight mutations, two activations, four activation
versions, two loss episodes, three resource claims and the two instance aliases,
plus route, authority/owner epoch and required catalog identities. Query one
extra row to detect cap violations. Include canonical original request/body
bytes, not just decoded fields. These fixture bounds do not replace the larger
production logical capacities. No database copying while a writer is live is
used as a durability oracle.

The parent verifies the complete bounded snapshot and notice association, records
fresh native observations using the private control channel, and sends SIGKILL
only through Guardian's retained pidfd for its registered direct owner child.
It joins the owner with expected exit `-SIGKILL` before recovery. A PID reported
in the snapshot never supplies signal authority. The checkpoint's durable state
and subsequent recovery records are evidence; the parent's knowledge of whether
the wire call was reached does not downgrade a committed possible effect.

## Exact thirteen cases

The three cuts for an operation mean: **prepared** is committed before the
possible-send transaction; **possible** is committed before `_exchange` starts;
**reply** is `StandingHost.after_exchange`, filtered to the exact opcode, after
the full response and receive-watermark commit but before `record_open` or
`record_mutation`. The response filter uses the existing decoded `opcode` field.

| Case | Existing hook and condition | Required durable and native state at cut | Required recovery result |
|---|---|---|---|
| OPEN prepared | Host `after_deployment_commit` | OPEN prepared; no possible effect; native slot empty; allocated number/fences retained | Original prepare/open replay sends no OPEN. Explicit `abandon_prepared` joins NOT_SEEN plus empty descriptor, records `never_handed_off`, retires and releases claims without lowering allocated counters. |
| OPEN possible | Store `after_open_handoff_commit` | OPEN possible; native has not received it | Original replay sends no OPEN. NOT_SEEN does not prove absence of a possible handoff; reconciliation remains unresolved, abandonment refuses and claims remain held. |
| OPEN reply | Host `after_exchange`, OPEN | Native slot prepared; host OPEN still possible; original response sequence already committed | Read-only STATUS joins the exact deployment and accepts the original OPEN. It does not START or reopen under a new identity; claims remain held. |
| START prepared | Host `after_mutation_reservation_commit`, START | OPEN accepted; START prepared; native mutation sequence unchanged | Original key returns its prepared record without sending. Explicit abandonment marks only that original `never_handed_off`; claims remain held. A separately requested new key may later be admitted. |
| START possible | Store `after_mutation_handoff_commit`, START | START possible; native sequence remains the previous value | STATUS cannot resolve the pending next sequence. Original key never sends, abandonment refuses, ordinary extension stays refused and claims remain held. |
| START reply | Host `after_exchange`, START | Native accepted the exact next sequence; host mutation still possible | STATUS's sequence and exact last-comparison bytes accept that original mutation. No second START is sent and no output activation is inferred merely from START acceptance. |
| Collection before ACK | Host `after_collection_before_ack` | One completed activation is committed; collected=1, acknowledged=0; no ACK outbox exists | Reopen preserves the exact record/version bytes. Read-only reconciliation does not ACK. A subsequent explicit collect request may separately reserve and send one ACK for the committed prefix. |
| ACK prepared | Host `after_mutation_reservation_commit`, ACK | Prefix committed; ACK prepared; native ACK remains 0 | Collect's original pending ACK is not resent. Explicit abandonment preserves the old key/body and allows a later caller-requested collect to admit the new deterministic ACK key. |
| ACK possible | Store `after_mutation_handoff_commit`, ACK | Prefix committed; ACK possible; native still has prior sequence and ACK 0 | Read-only reconciliation leaves possible acceptance unresolved. No ACK resend or prepared-only abandonment is allowed; committed records and claims remain held. |
| ACK reply | Host `after_exchange`, ACK | Native ACK=1 and next sequence accepted; host ACK mutation still possible | STATUS joins the exact ACK and advances host acknowledgment only within the already committed prefix. Activation evidence remains retained even though native ledger entries can be gone. |
| RETIRE prepared | Host `after_mutation_reservation_commit`, RETIRE | Terminal loss episode, exact witness and full committed/acknowledged prefix; RETIRE prepared | Original key never sends. Explicit prepared-only abandonment retains claims; only a separately requested new RETIRE may later release them. Quiescence alone is not retirement. |
| RETIRE possible | Store `after_mutation_handoff_commit`, RETIRE | Same terminal proof; RETIRE possible; native slot still present | STATUS cannot accept an unseen next mutation. No resend/abandonment or claim release; a terminal endpoint is still owned. |
| RETIRE reply | Host `after_exchange`, RETIRE | Native slot empty; host RETIRE possible with original terminal proof intact | Only joined OLD_OR_FORGOTTEN plus same-boot empty descriptor, original number/fences/epochs and the retained retirement preconditions accepts RETIRE and releases claims. A refusal alone is insufficient. |

Setup uses the existing literal synthetic domain and fixed virtual ticks. OPEN
and START cases have no output dispatch before the cut. ACK/collection/RETIRE
cases use the existing demand=35000, cycle12 and cycle24 transition recipe; the
RETIRE cases additionally use explicit STOP, cycle40 and committed collection.
Each stage waits for the corresponding completed wire exchange before parent
control commands. Exact snapshot expectations must be checked against the
frozen sources during implementation, not inferred from elapsed wall time.

After each reopen, compare immutable request, mapping, selection, original body,
transmit sequence, namespace, deployment key, standing number and fences. Owner
epoch, host revision and recovery flags legitimately change on reopen; whole-row
byte equality is therefore not the recovery invariant. Check exact allowable
changes, retain their before/after snapshots and require the same authority ID.

Recovery first performs historical replay and read-only reconciliation. A bounded
test-only `before_exchange` audit records opcode, transmit sequence and body
digest for every recovery exchange. Its maximum is 64 entries. Historical ACK
collection can send STATUS queries, so an unchanged response counter alone is
not the appropriate assertion: the audit must contain no new effect opcode until
the case explicitly requests a newly admitted action. Correlate that audit with
native mutation/ACK/activation/output counters and stored outbox states. After
settling a prepared original, replay its old identity again and verify it remains
terminal `never_handed_off`, without adopting the new request's result.

Common REVOKE is absent in these fixed setups. The revision04 independent-outbox
guards must remain intact. These cases do not qualify a possible REVOKE's eventual
settlement or relax any dispute, effect-unknown or recovery restriction.

## Evidence provenance and limits

Before implementation is executed, the chosen host revision must also complete
its original bounded living-owner control matrix; these process-death cases do
not replace that prerequisite or turn a failed baseline into a qualified one.

The native prerequisite is the reviewed original qualification run, with its
actual reservation, held executable/argv association, completed twelve-case /
638-assertion child, exit-zero/reaping record and immutable published manifest.
A passing JSON field supplied by this new harness is not a substitute.

Reuse that exact verified bundle at its original installed root; its manifest
binds an absolute original argv. Do not relocate the consumed bundle and rewrite
reservation/receipt paths to make it appear newly executed. Exact byte copies
may be retained for audit, but the producer reads its original root. Pin the
original manifest, reservation, receipt, binary, stdout/stderr, source closure and
parent attempt evidence before/after this run. If the original run is unavailable,
changed or not validated, this design has no qualifying prerequisite and the run
must refuse. The unchanged native image can be held and reused from that attempt;
do not rebuild it silently with different inputs.

Frozen host production files remain byte-identical to the reviewed revision.
New harness files stay outside the thirteen source names used for the installed
host image digest. Each child obtains its own current policy/image/driver and
catalog evidence leases as the real API requires; no fake always-valid lease or
parent's stale copied lease is accepted. Pausing at a cut may expire a lease,
which is acceptable because that owner is killed rather than allowed to continue.
The recovery owner reacquires evidence for any separately requested admission.

Keep the existing outer control bound of 30 seconds wall/CPU, 512 MiB address
space, 1 MiB per file and 64 descriptors. Original and recovery hosts and native
children use Guardian's existing 5 CPU seconds / 256 MiB profile. Keep its
eight-second observed settlement limit and a bounded three-second TERM grace
for the outer control. A complete case must reach its cut within the existing
five-second notice bound, and the entire matrix must finish inside the outer
bound. These are per-process limits and observed deadlines, not aggregate kernel
quotas. No deadline or limit is enlarged on a failed attempt.

For normal per-case cleanup, finish and reap recovery first, close the parent's
wire/control keepers, and require the surviving original native process to exit
cleanly on EOF. Only failure cleanup may kill it; that makes the case fail. Do
not call Guardian.settle while the native endpoint is intentionally surviving
between the two hosts, because settle targets every registered child. Assert
the expected live set during that interval and the empty set after cleanup.

Both inner and outer reducers independently try all cleanup actions, retain any
cleanup error, require exact expected exit classifications and no extra children,
and fail on pending/deferred interrupts. Preserve the corrected host runner's
terminal exception/unmask handling; do not copy the older owner-crash runner's
success-publication structure without those corrections. A failing case remains
retained and stops the matrix; it is not replaced by a successful rerun in the
same attempt directory.

Per-case evidence joins the fixed intent and source pins, native and owner start
identities, checkpoint notice/snapshot, kill/reap record, native observations
before/after death, recovery start/reap, before/after database snapshots, outgoing
opcode audit, exact expected classification, and final native EOF/reap. Final
evidence concatenates all per-case reaps and joins them to inner/outer ownership
records. It states `actualOwnerDeath=true`, `nativePeerSurvivedOwner=true`, and
`historicalPossibleEffectsResent=false` only after these joins pass.

This slice requires a living guardian and the fixed synthetic native peer. It
does not cover death during partial frame I/O, an arbitrary native queue, inside
a SQLite transaction/COMMIT, an expired or disputed evidence view, a changed
endpoint boot, power loss, full backing-storage pressure, physical/GPU settlement,
or guardian loss. Those remain separate completion gates; this plan must not
relabel them as qualified by the thirteen fixed cuts.
