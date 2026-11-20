# Read-only diagnosis of the 424-test failure

The retained run has **four failure records and one error record** after 545.650
seconds. It proves one next-child observation refusal and two terminal refusals
before dispatch. It does **not** retain enough evidence to attribute both dispatch
refusals to observation age, or to attribute any failure to machine load.

This diagnosis reads the frozen `runtime-424-failed` lane. Nineteen inputs are
pinned in `input-pins.json`; all matched the live files when captured. Fifteen
source files are copied under `inputs/`. `failure-tail.txt` retains the five
failure records, and `failure-summary.json` extracts the available transport
evidence without repeating the large tool schemas. The initial analysis was
read-only. The separately authorized instrumentation checks and focused transport
rerun are described below. The earlier PAT review and failed-run receipts were
not edited.

## What the failed run establishes

| Case | Retained state | What remains unknown |
|---|---|---|
| Named-stream compact focus | `sim:cli-c1-focus`, `rejected_before_dispatch`, event sequence 2, `mayHaveActed=false`, no claims | The rejection event's reason; the triggering observation and timing |
| CLI procedure after explicit restart/resume | Child 0 completed; accepted local fan child 1 became `rejected_before_dispatch`; child 2 remained unstarted; parent reason `CHILD_REJECTED_BEFORE_DISPATCH` | Child 1's rejection event reason and its observation/policy snapshot |
| Legacy MCP procedure | Child 0 completed; cursor advanced to 1; child 1 has no operation ID and remains `unstarted`; parent failed with `OBSERVATION_STALE` | Whether stale meant known age expiry, invalid quality, missing bounds, or another combined stale condition |
| Runtime IPC local fan | `failed`, `mayHaveActed=true`; simulator result says `effectCommitted=false`, `authority_or_precondition_lost` | The underlying policy error, which the local adapter aggregates into that reason |
| Runtime IPC final plant assertion | Fan value/effect count remained `(0,0)` instead of `(37,1)` | This is a consequence of the preceding fan failure, not a separate demonstrated runtime defect |

The named-stream trace retains the three completed local scenarios and the first
compact fan scenario, but appends each scenario only after its success assertions.
It therefore omits the failing compact focus request/status/events. Both failed
procedure cases have `passed=false` and no pre-admission refusal retries. The CLI
trace retains submit, interrupted status, exact parent replay and explicit resume;
the final failing status survives only in the unittest traceback. The legacy MCP
trace preserves three distinct status transitions: first child accepted, first
child running, then first child completed with the next child unstarted and the
parent failed. The modern MCP case and paused-route regression passed.

## Relevant control paths

The actual daemon starts a separate procedure worker and one worker per route
(`hms/runtime.py`, `_run_procedures` and `_run_route`). They share the Journal
authority mutex. A procedure can attempt its next child before that route's next
refresh. `Runtime.tick` has a sequential order for direct tests, but it is not the
daemon's scheduling model.

`ProcedureStore.tick` currently defers resource contention and not-yet-startable
conditions. Other admission errors, including `OBSERVATION_STALE`, terminally fail
the parent. In the legacy MCP failure, this branch is directly evidenced: no child
operation was allocated at the failing cursor.

`LocalSimulation.tick` refreshes, performs expiry work, and then claims dispatch.
`CompactEndpoint.tick` refreshes and reconciles, then force-refreshes a selected
accepted operation, arms, and claims dispatch. Both adapters terminally reject
most claim/recheck failures while the operation is still `accepted`. A successful
refresh does not promise that its sample will remain fresh through later storage,
transport or mutex delay. Conversely, the compact rejection could be any rejected
arm/reservation/clock/identity condition; the status alone does not establish age
expiry.

The sample age calculation is conservative: current receipt-clock elapsed time
plus acquisition latency bound plus uncertainty. Acquisition time is not replaced
with publication time. The fixture precondition requires `ready=true`, simulation
evidence, and a maximum age of 1000 ms. Both adapters normally throttle refresh to
200 ms, but those periods are not latency guarantees.

`Registry._observation` raises the same `OBSERVATION_STALE` code for several cases:
age above the requested limit; quality other than valid; unknown age; receipt
epoch mismatch; unavailable/regressed monotonic clock; inactive or changed binding.
`RegistryPolicy._check` only compares the predicate's value after that check, and
uses `PRECONDITION_FAILED` for a fresh value that differs. These distinctions must
survive an availability change.

## Narrow deferral proposal

Use an internal trusted subtype or structured reason for **known-age expiry**,
while retaining the external error code if API compatibility requires it. It
should require valid stored quality, a known conservative age, matching receipt
epoch and current binding/session/evidence identity, with the failure caused only
by `age > maxAgeMs`. It must not be constructed from caller JSON. Unknown quality,
unknown clock bounds, identity changes and a fresh false predicate do not become
refreshable simply because they currently share a code.

| Boundary | Permissible response to narrowly classified age expiry |
|---|---|
| Advisory prepare or fresh invoke rejected before admission | An explicit exact request retry may be valid within unchanged bounds after proving no admission/key/claim/mapping was created. Existing tests already constrain this behavior. |
| Managed parent, next child not yet allocated | Leave the same cursor and immutable child request pending; let its route refresh; retry admission on a later bounded tick. Do not replay earlier completed children. |
| Child already accepted, no dispatch ticket or mapping issued | Leave that same operation accepted, retain its existing claims, and recheck later. Cancellation, namespace/lease/start/completion bounds and parent inhibition still win. |
| Ticket issued, dispatching/running, uncertain handoff | Do not return to accepted or issue another OP. Reconcile the exact durable identity; apply cancellation/failure rules for execution-time authority loss. |
| Already terminal refusal/failure | Preserve it and exact replay. A later fresh sample must not resurrect it or silently create a new key/child. |

Deferral should perform no synchronous refresh while inside policy/admission
transactions. Return to the worker, allowing the installed route to acquire and
publish a new sample. Every later admission/handoff must rerun all authority and
semantic checks. Deadline exhaustion must terminate and release claims as before.
Repeated waiting must not create unbounded duplicate events or hold the authority
mutex while sleeping. A deferred head item must not starve independently ready
work on the same route; the compact `limit=1` selection needs explicit consideration
if the new behavior can keep that first item accepted.

## Evidence to retain on the next transport failure

Capture before temporary-directory cleanup, and preferably before daemon shutdown
changes the recovery state. Failure capture itself must be bounded and must never
replace the original assertion with a capture error.

1. Save the canonical prepared child requests and parent request immediately when
   constructed, along with identifiers and timing. Append the accepted response
   and last observed status before asserting success. Preserve terminal statuses
   immediately rather than polling them until a success-only timeout expires.
2. Fetch `procedure_events` and `events` for every linked child/ordinary operation.
   `rejected_before_dispatch.payload.reason` is the missing decisive fact in two
   cases. Preserve complete bounded pagination and cursor/head values.
3. Take a consistent read-only SQLite backup of `authority.db`, plus each plant DB,
   before cleanup. Label these as separate snapshots, since authority and plant
   databases are not one atomic snapshot. At minimum retain operation/replay/claim
   rows, procedure links/events, grants and binding history, presence, streams,
   observations, adapter state, compact command mappings/receipts and packet rows.
4. Retain daemon/fixture stderr, exit status, and external relay frames even when
   completion assertions fail. For named streams without an external relay,
   `ep_packets` is durable host packet evidence, not independent wire-delivery or
   physical-effect evidence. Keep SQLite plant effect counters similarly scoped.
5. For each actual policy refusal, preserve the internal error code and stage.
   The local adapter currently collapses execution-time recheck failures into
   `authority_or_precondition_lost`; a database backup cannot recover a discarded
   underlying exception. A bounded diagnostic hook or dedicated durable diagnostic
   event should include the original code, operation identity and guard stage.
6. For age and deadline investigations, record the exact sample used by the guard:
   binding/session, stream epoch/sequence, quality, acquisition and receipt clocks,
   latency/uncertainty, computed age and limit, wall/monotonic samples, durable clock
   floor, lease/start/completion bounds, and the last potentially blocking step.
   A later `observe` call is useful context but cannot reconstruct the rejected
   sample if refresh has already replaced it.

Transport failures should remain failures. This collection does not authorize new
keys, wider timing limits, weakened freshness checks, or retries after uncertain
handoff.

## Deterministic acceptance tests

Use original fixtures and controlled clocks, not longer sleeps. The following
tests should precede another expensive full run:

1. Complete child 0, expire only the qualified ready sample for child 1, then tick
   the parent before its adapter. Assert no child 1 operation/key/claim/mapping or
   terminal parent transition. Publish a fresh matching sample and assert exactly
   one child 1 admission/OP, with the original request and child 0 untouched.
2. Make an accepted local and compact child's sample expire before claim. Assert
   same operation, no ticket/mapping/OP/effect, and later exactly one dispatch after
   a fresh sample. Include cancel, lease/start expiry and explicit paused-parent
   cases while waiting; expiry must release existing claims.
3. While waiting, publish a fresh false predicate, change binding/session, revoke
   permission, or publish invalid/unknown quality. Assert no broad stale retry
   bypasses those semantic/authority losses. Test the exact `age == maxAgeMs`
   boundary and the first value above it.
4. Keep the first candidate deferred while independently ready work exists on its
   route. Assert bounded selection makes progress without issuing multiple OPs for
   either child or skipping its resource guard.
5. Inject delay after snapshot publication, authority-floor commits, dispatch
   reservation and policy checks. Assert no expired run/completion/lease permits a
   synthetic effect, and permanently stale publication does not relabel acquisition
   time as fresh. Separately verify running/uncertain children never revert to an
   unstarted retry path.
6. Crash while deferred, reopen, and require the existing explicit procedure
   resume policy. Verify exact replay retains the original child linkage and any
   prior terminal facts; no automatic continuation or new key appears.
7. Force each real-transport test to fail after acceptance and verify its failure
   artifact contains the request, terminal status, exact rejection event and a
   readable DB snapshot. This validates diagnosis rather than merely adding log
   statements to a success-only path.

## Clock boundary review

The root's companion deterministic test lane reports an additional timing defect:
local elapsed-time checks used a monotonic sample from before a blocking authority
checkpoint. This diagnosis did not execute that companion test; its independently
retained before-fix evidence is under `artifacts/verification/local-freshness-before/`.

Static inspection confirms that `Journal._now` reads wall time, persists the sample
with `COMMIT`/`BEGIN`, and returns the pre-commit sample. `authority_time` then adds
the enclosing transaction commit. Its return value is a durable authority-floor
barrier, not a timestamp sampled after all blocking work. Repeatedly calling it
cannot solve that distinction and can chase a moving clock indefinitely.

A bounded design should preserve that durable barrier and add a separately named,
conservative final veto after refresh/policy/blocking work, under the same authority
mutex. The veto must validate exact clock values and regression, check monotonic
run duration and fresh wall completion/lease bounds, and only withdraw existing
authority; it must not issue tickets, extend leases or provide an admission/event
timestamp. If it advances the Journal's observed clock floor, refusal and settlement
paths must retain that floor. Simply changing `_now` to return an unpersisted final
sample would weaken its documented anti-rollback behavior.

The plant's `finish` also takes a lock and begins a separate transaction before
updating synthetic state. A guard placed only in the adapter can become stale
during that work. A final guard belongs as close to the mutation as the declared
simulator contract supports, after those blocking boundaries. SQLite commit itself
can still block. No bounded method can both persist its last wall sample before an
effect and guarantee that the same sample is fresh after an arbitrarily blocking
commit. Exact commit-time or physical deadline guarantees require an additional
qualified time/latency contract or a stronger shared execution mechanism; these
host checks must not claim them. The root must make the supplemental-veto/floor
contract explicit rather than resolving this with a commit loop.

## Failure-retention implementation and checks

After the read-only diagnosis, the root authorized failure-only instrumentation in
`tests/test_multi_cli.py`, `tests/test_procedure_transport.py` and
`tests/test_runtime_ipc.py`. The shared helper in the first file uses unique
`artifacts/verification/transport-failures/<case-uuid>/` directories. Each report
contains additive `failureArtifacts` entries naming root-relative manifest paths.
The manifest hashes every retained file other than itself and is finalized again
after shutdown output has been added. The runner is to copy only directories
referenced by that run's actual reports.

Captures contain read-only SQLite backups and decoded table/event rows, early
requests and accepted/latest statuses, copied request JSON, process stdout/stderr,
and existing procedure relay request/response/held-reply bytes. The separate
database backup processes are bounded; incomplete capture is labeled and does not
replace the original test failure. Full database backups retain rows even where a
human-readable table summary reaches its explicit 4096-row cap. Runtime IPC's
cleanup detects unittest subtest failures before deleting temporary state.

`check_failure_capture.py` exercises original scratch SQLite and Python diagnostic
code. Its five checks passed, recorded in `capture-self-check.json`: exact rejection
reason and read-only backup integrity, original relay bytes, cleanup stderr in the
final manifest, subtest failure retained before temporary cleanup, and capture-error
containment. The one unittest failure in `capture-self-check.log` is intentional
test input to that checker, not a product failure. Its three referenced output
directories are likewise deliberately generated diagnostic evidence.

No original success assertion was removed or weakened. The legacy MCP stderr
assertion now checks the same captured string instead of consuming the file at
the assertion. Retry behavior, operation keys, freshness limits, timing windows
and timeout values were not changed by this instrumentation. It does not add a
client retry after accepted or uncertain work.

## Focused transport rerun

The root authorized one run of all tests in the three instrumented modules after
freezing the production fixes. `focused-transport/` retains the unittest result,
all three actual reports on success or failure, and before/after source hashes.
The project Python inputs are copied there; schemas, examples, endpoint documents,
the original native binary and its provenance receipt are also hash-pinned. This
run uses real local CLI/UDS and modern/legacy MCP with original SQLite/native C
simulation fixtures. It does not execute hardware, an MCU, an emulator, an LLM or
an acquired controller program and provides no physical or latency qualification.

The production changes selected by the root include age-only deferral before a
procedure's next child is admitted, local sample reacquisition, and a final
conservative time/policy veto inside the synthetic plant transaction. The broader
accepted-child deferral described above remains a design option, not a claim that
it was implemented. A known accepted child's terminal refusal remains terminal.

The focused run passed **9/9 tests in 169.271 seconds**, with no failures, errors,
skips or pre-admission freshness refusals. All 51 pinned inputs matched before and
after. Named streams completed and replayed all nine scenarios; both MCP versions,
CLI restart/resume and the paused-route test passed; all three Runtime IPC tests
passed. `focused-transport/outcome-summary.json` includes the actual retained
procedure events and the three Runtime IPC event replies. No new transport failure
directory was produced by this run. Its success does not recover the missing
rejection reasons in the original failed run or establish an availability bound.

After this run terminated, the root released production for a separately proven
local start-boundary fix concerning delays in dispatch-claim commit and plant
begin. The focused receipt applies only to its archived pre-start-fix sources; it
must not be presented as validation of those subsequent edits. The three
instrumented test files remain frozen for that next verification.
