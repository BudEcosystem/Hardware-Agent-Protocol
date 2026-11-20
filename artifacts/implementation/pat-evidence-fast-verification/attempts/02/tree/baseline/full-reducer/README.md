# Staged original-worker evidence reduction and retention

This is an unmounted staging library. It consumes actual retained outputs from
the original isolated fan worker, independently reduces their emitted facts,
and atomically retains a bounded content-addressed closure in SQLite. It does
not run a Runtime, worker, model, controller or physical device. No live project
source or frozen verification tree was modified in this lane.

The test inputs are historical evidence. `baseline/producer/` is an exact copy
of the 43-input worker attempt04 tree, whose compiler digest differs from later
live source. `retained/` contains its eleven exact returned results and evidence
file sets: two successful runs (27 and 10 cases) and nine negative outcomes.
The original raw operation IDs, authority identities, sessions, times, index
pages and results are preserved. Qualification fixtures were not substituted
for execution. The original proof also retains scratch databases; this slice
does not use those databases as a qualification basis or copy them into its
SQLite evidence closure. Exact acquired inputs are pinned in `before.json`.

Tests deliberately supply an explicit historical trust binding. They do not
prove that the historical producer is current, that digest labels authenticate
a driver, or that those results are authorized for a live deployment. Importing
this staged module into the worker source closure would change its identity;
live integration requires fresh worker evidence with the final installed code.

## API and closed documents

`trusted_binding(value)` validates and detaches a bounded closed setup record:
`{profile, deployment, runId, evaluator, input}`. The evaluator includes its exact
ID, implementation/policy digests, four required check IDs/categories and the
evidence profile. `input` is the exact trusted worker capsule, including artifact,
installation, typed binding/semantics, configuration revision/digest, producer
identities, environment, matrix and ceilings. The service must independently
supply these pins. In particular the service's `runId` association is not present
in the worker output and is not worker authentication. The evaluator code pin
must include the reducer and its direct/transitive validation dependencies as
well as the worker/service implementation. The staged test pin hashes its source
and exact historical-input manifest; it is a test-specific trust setup.

`read_retained_attempt(trusted_directory)` acquires `test-return.json` and fixed
`evidence/NNNNNN.json` names using bounded no-follow reads. The root ancestry is
trusted setup, never caller JSON. Unknown names, symlinks, hard links, oversized
files and discontinuous enumeration refuse. Acquisition is separate from
eligibility. The returned result was retained by the original proof harness;
a supervisor must retain that exact return itself before using this API.

`reduce_attempt(trust, result_bytes, files)` is pure after module import. It
requires canonical bounded records and produces
`{profile, groupDigest, documents}`. Documents are an internal digest-to-bytes
map, not a public JSON transport. The group manifest pins the exact trust digest,
run/evaluator/configuration/artifact/environment/producer association, input and
result, original index pages, ordered case capsule references, byte/document
counts and limitations. Each case capsule contains its exact matrix/fault ID,
categories, expected result, independently derived observations, and references
to every original record in that trial. Document keys are SHA256 of exact bytes;
the profile and explicit domain-separated input identities prevent semantic
substitution. Duplicate/extra references, missing records, cycles, changed bytes
and unconsumed documents refuse.

`EvidenceStore(connection, trust, byte_quota=64MiB, document_quota=16384)` creates
three versioned tables or refuses a partial/unknown-prefix schema or missing
version. It does not repair an existing partial store. `import_bundle(bundle)`
validates the complete closure and links `(deployment, evaluatorId, runId)` in
one owned `BEGIN IMMEDIATE` transaction. Exact repeat import deduplicates bytes;
a different group under the same run key conflicts. Failed validation, quota
refusal and pre-commit process loss leave no partial group or run link. Import
returns the catalog result with four fixed checks (`fan:positive`,
`fan:boundary`, `fan:negative`, `fan:fault`) referring to the same complete group.
It does not publish, promote or record a catalog receipt.

Hash and semantic consistency do not authenticate arbitrary input bytes as an
actual worker execution. The future trusted supervisor must control the worker
input/output channel, wait for a settled producer and retain the provenance.
This API is not an ingress for caller-provided successful evidence.

`verify_evidence(context, receipt)` requires an already active authority
transaction. It compares exact check IDs/categories/outcomes, run and evaluator
identity, artifact/domain/environment hashes and the retained run link, reads
the bounded closure, and repeats reduction. It returns only exact `True` on
success. Missing, corrupt or unavailable evidence raises a non-filterable
error; it must never be treated as an ineligible candidate that creates false
uniqueness. The catalog must separately authenticate the enclosing stored
receipt's digest and row associations before selection filtering. A hook that
receives only the receipt cannot establish which catalog row supplied it.

## Independently checked facts and producer assertions

The reducer recreates the complete static matrix, checks conservative whole
declared domains and static applicability, and lowers each concrete case with
the original supplied identities and keys. It validates original simulation
installation/layout/type/resource/metadata compatibility and exact environment
closure. All matrix cases plus the five exact lifecycle cases must occur once,
in order, without omission, extras or duplicates. Categories do not substitute
for their concrete case sets. Finite boundaries are not exhaustive behavior.

Each trial must start with the original fresh simulated factory state for all
three installed devices. The reducer correlates every emitted bound intent,
digest, procedure link/projection, claim/fence, receipt identity and result,
operation sequence and gap-free event history. Final effects are attributed to
committed receipts, the fan value/count must match, and companion devices must
remain unchanged. Each emitted checkpoint is checked, including the completed
plant receipt that precedes host settlement in modeled evidence loss. Accepted
cancellation must prove no handoff; running cancellation must include the actual
dispatch/running event boundary. Reopen traces, cancellation reasons and explicit
resume state changes must match the named trial. Emitted virtual-time running
and completion boundaries obey strict start/completion/lease/maxRun limits;
this is not a physical or host real-time guarantee across commit.

The worker did not emit raw resource-floor/replay-key SQL rows or every request
and response for replay/conflict and refused-resume checks. Those remain
assertions of the exact pinned worker. Its replay/conflict log records are
validated but cannot independently reconstruct absent responses. Scheduler tick
totals, actual wall-deadline enforcement and scratch sizes likewise remain
producer assertions: the reducer checks their emitted bounds and arithmetic,
not missing scheduler/filesystem observations. This limitation is in every
returned result. No `passed` flag alone is accepted.

## Read, retention and authority boundaries

Each document is at most 65,536 bytes. Producer records are capped at 4,096 and
16 MiB (or the capsule's lower ceiling); at most 32 case capsules and one result
plus manifest are retained. The complete closure, including original index
pages, result, derived capsules and manifest, is capped at 4,130 documents and
20 MiB. Both the manifest's own bytes and every actual document count toward
that cap. Store-wide logical quotas include all retained document bytes and
all unique documents, including orphans. These are not SQLite file, index,
WAL, scratch or filesystem allocation quotas; a supervisor still needs storage
admission and lifecycle policy. There is no garbage collector here.

Verification does not trust a recorded byte count. It first reads only
`typeof(body)` and `typeof(byte_count)`, rejects anything except BLOB/integer,
then reads built-in `length(body)` and the scalar count. Only after checking
actual per-document and aggregate lengths does it fetch a BLOB and recheck its
length and SHA256. The two metadata stages are intentional: SQLite TEXT length
can stop at NUL and may itself materialize large text. Fixed-width document keys
are stored as BLOBs; import quota scans validate key type and actual byte length
before fetching them. Run linkage and schema-version checks SELECT a literal
against the exact expected value rather than returning arbitrary metadata.

These calls require a trusted connection that has not overridden the built-in
`typeof` or `length` functions and is not concurrently mutated or reconfigured.
The verifier installs no authorizer, starts no transaction and performs no
filesystem/provider/Runtime calls. It uses ordinary SELECTs plus those two
built-ins. The catalog version copied in this historical baseline forbids all
functions; the staged tests demonstrate that refusal and use an explicit
narrow allowance. Root is separately testing a newer live catalog allowance;
this is not an integration proof for it. Trusted Python is not a sandbox.

The SQLite primary documentation was acquired in `research/`. Its `length(X)`
section distinguishes BLOB bytes, TEXT code points/NUL behavior and BLOB metadata
access; `typeof(X)` identifies the storage class. See the retained acquisition
record and [SQLite's core function documentation](https://www.sqlite.org/lang_corefunc.html).

Full semantic verification recompiles and checks every case. The retained
example measured 7.009 seconds for the 27-case closure and 1.966 seconds for the
10-case alias closure. The larger import took 9.095 seconds. This is a material
service-integration blocker for synchronous full verification under the authority
lock, even though its work is finite and bounded. No authority-lock latency or real-time availability claim
is made. Integration must measure this cost and decide whether an independently
reviewed bounded import attestation plus ongoing content-integrity protocol is
needed. Do not silently drop evidence checks to improve routing speed.

## Verification and remaining integration

`run_attempt.py NN` copies source, tests, historical dependency closure and exact
retained data into a fresh immutable attempt tree. Tests import that tree only,
retain output and before/after hashes, and never rerun the worker. Earlier failed
attempts are preserved alongside later results; their source hashes distinguish
what they tested. The final index/attempt result gives the authoritative totals.

The tests cover actual successful/negative worker output, rehashed semantic
mutations, typed scalar and schema rejection, complete matrix/event/lifecycle
coverage, exact timing boundaries, missing/corrupt/oversized BLOBs and NUL text,
forged byte counts, key/link conflicts, schema and quota refusal, no filesystem
calls during reduction/verification, rollback, close/reopen and real process
exit immediately before and after the evidence import commit. These process
exits test this evidence store; they do not turn the worker's modeled completion
loss into an abrupt-worker-crash experiment.

Next work remains: trusted persisted configuration and current identity
construction; durable qualification-attempt admission/single-flight execution;
isolated worker supervision with explicit interrupted outcomes and storage
budgets; exact archived-result retry; current receipt-integrity/hook integration;
fresh current-code worker evidence; then catalog/service mounting and public
checked APIs. One latest environment per artifact/deployment remains unchanged.
Learning, persistent applications, I/O/drivers, hubs and physical qualification
remain required project scope.

## Final sealed result

Attempt05 passed all 26 tests in 178.563 seconds (180.294 seconds including
runner setup/imports). Its 436 copied source/data inputs remained unchanged.
Attempts01 and02 retain four errors each, caused by incorrect new-reducer
assumptions about resume event naming and pending/reopen receipts, respectively.
Attempt03 passed 23 tests; attempt04 passed 25 tests; their earlier source snapshots
remain distinct from the final strict-boundary checker.

The concrete stores under `attempts/05/examples/` retain both successful raw
worker evidence closures: case04 has 27 cases, 204 documents and 362932 logical
bytes; case01 has 10 cases, 87 documents and 159603 logical bytes. Their generated
receipt files are projections for review, not published catalog evaluations.
Independent read-only review confirmed the final source delta; that reviewer
ran no tests. `proof.json` and `index.json` record the exact scope and identities.
