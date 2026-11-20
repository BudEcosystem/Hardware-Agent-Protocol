# Staged memoized verification of immutable evidence

This is a separate staging increment. The original evidence reducer artifact
remains byte-exact and frozen. No live HMS, tests, schemas or service mounting
were changed. All behavioral examples use retained original-worker results
from the historical 27-case and 10-case fan runs. No Runtime, worker, model,
controller or physical device is executed by this stage.

## Profile and implementation choice

The retained `profiling/` run executed the original full pure reducer against
case04. Under cProfile it took 18.843 seconds: 55 environment validations cost
7.749 cumulative seconds, 27 compilations 3.359 seconds, 59 API validations
3.674 seconds and 1,099 schema checks 6.206 seconds. These are overlapping
cumulative costs and profiler overhead is substantial. Raw profiling data,
sorted reports, the exact script and the original reducer hash are retained.
The original reducer bytes used for that profile also remain in
`baseline/full-reducer/src/`.

Memoizing the entire pure reducer avoids both compilation and repeated schema
validation. It does not accept a stored `passed` flag or weaken the reducer.
`src/evidence_reducer.py` is the original source with only a private optional
`_load(..., _reduce=reduce_attempt)` seam. An AST regression proves all other
source structure is identical. Full import and audit keep the original reducer.
The new `src/fast_evidence.py` supplies the process-local memo and fast facade.
Live integration should use the private seam in the existing evidence store;
it should not redeploy another copy of that store.

## Closed semantic provenance and cache identity

`ValidatedReducerMemo.warm(trust, result_bytes, files)` is an explicit trusted
setup operation. It snapshots bounded inputs while preserving scalar types and
runs the full reducer before inserting a successful result. There is no public
method for inserting a purported passed result, imported flag, certificate or
attestation. Failed reduction is not cached. A warm hit is already the result
of precisely the same pure validation.

The key includes the imported validation implementation identity, a typed hash
of the whole trusted setup record (including evaluator, configuration, artifact,
environment, run/attempt identity and matrix), the exact returned-result bytes,
and every ordered source record path, byte length and SHA256. Integer, float,
Boolean and null have distinct tags; canonical JSON's `1.0` to `1` conversion
cannot create a hit. The raw records retain their original random IDs and times.
No normalization substitutes a logically similar run.

The imported implementation identity covers both staged modules, all copied
HMS Python source, schemas and example data, the compiler's validation-package
closure, Python executable/implementation/version, and SQLite extension/version.
It therefore includes runtime sources beyond the compiler pin. It is computed
at module import, outside eligibility. Old cache objects refuse after a changed
module identity. Imported-code monkeypatching or changing files underneath the
running deployment is unsupported; restart/reload requires fresh warming. The
trusted service registration must include this memo/reducer implementation in
its evaluator identity. A private memo key is not external producer, artifact or
configuration authentication.

`lookup(...)` is read-only and returns only an exact validated hit. It never
compiles, inserts, evicts, updates LRU state, caches a refusal, reads a file or
consults a clock/provider. A miss returns `PAT_EVIDENCE_CACHE_COLD`, which must
abort routing as indeterminate. It must not be filtered away to manufacture a
unique PAT. Returned document dictionaries are detached and retained payloads
are immutable bytes/strings. Changing a returned bundle or supplied trust cannot
poison an existing entry.

Capacity is independently bounded by entry count (maximum eight), retained
charged bytes (default 8 MiB, maximum 32 MiB), and the full reducer's document
count/size ceilings. Charges include raw records, result, case capsules,
manifest, digest keys, memo key and per-document metadata allowance. Separate
entry/document bounds constrain Python-object overhead; this is not a hard RSS
or allocator quota. Warm insertion uses FIFO eviction; lookup performs no
reordering. An entry larger than the configured capacity refuses rather than
quietly weakening verification or exceeding the cache budget.

## Every verification still checks current storage

`FastEvidenceStore(connection, trust, memo=memo)` uses the same receipt checks,
run linkage, actual SQLite BLOB type/length checks, index traversal, per-document
hash checks and complete derived closure comparison as the original store.
It substitutes memo lookup only at the pure reducer call. Every current document
is read again, with the same 65,536-byte per-fetch bound and aggregate closure
limits. A hot semantic result cannot hide deletion, corruption, malicious actual
length, a changed raw record, or a changed derived case/manifest. The all-document
reread regression checks the exact digest set and count.

A rehashed semantic mutation has a different full input key, refuses cold, and
fails explicit full warming. A derived-only mutation may still share the raw
input key; the original loader's post-reduction full bundle/digest comparison
then refuses it. No cache hit alone qualifies a DB graph. Warm-from-store can
populate a valid raw-input memo entry before a later derived-closure check
fails; that does not authenticate the bad graph, and future verification still
checks the same complete closure. Failed warm-from-store is therefore not
claimed to leave cache usage unchanged in every case.

`FastEvidenceStore.import_bundle` deliberately refuses. Use the original full
store for import. Its full import/audit behavior remains available and tested.
The catalog must authenticate the enclosing receipt digest and its stored row
associations before its eligibility filtering. This stage continues to enforce
exact receipt run/evaluator/artifact/environment/check references and retained
run linkage, but does not replace the catalog's separate responsibility.

The callback requires an existing authority transaction with only SELECT/READ
and the reviewed built-in `typeof`/`length` allowance. It changes neither DB rows
nor transaction state. Trusted code may not override those built-ins, replace
the authorizer or mutate the connection concurrently. The cache is trusted
process memory, not a Python or hostile-code sandbox.

## Restart and warming boundary

A process restart has an empty memo. A valid persisted evaluation does not turn
that into a cache hit. `warm_stored(full_store, group_digest)` reads a bounded
snapshot and performs full validation to populate the new memo. It owns a read
transaction and requires no existing transaction. It is setup/audit work, not a
callback: run it before workers, or through a separately reviewed authorized
export/warm design outside the authority lock. Holding a long read snapshot in
an active service may affect writers; no live scheduling solution is supplied.
Explicit warming and capacity admission must complete before an evaluation is
made eligible. Eviction afterward causes an explicit refusal, not inline cold
work or selection of an alternative.

The eight-entry memo bound is separate from the catalog's 128-artifact bound.
A service cannot promise every active catalog entry stays warm when its cache
capacity is smaller. It needs an explicit prewarm/admission policy outside the
authority lock and an atomic final eligibility/revision recheck before new work.
Cold or evicted evidence is an availability condition, never task novelty, a
reason to call a model, or a filter that creates a different unique candidate.
Existing admitted work retains its pins; cache eviction is not cancellation.
The generic catalog hook may map a verifier exception to evidence-unavailable;
trusted service diagnostics should retain the distinct cold reason without
allowing callback-provided error codes to alter selection policy.

No secret is needed for this scheme. `ATTESTATION-ALTERNATIVE.md` separately
assesses a process-secret authenticated import certificate. It is not
implemented or needed to establish the memo's semantic provenance.

## Evidence and next integration

`run_attempt.py` executes only copied-input tests. The final tests include actual
retained evidence, full-reducer AST equivalence, complete current-document
reads, read-only guarded hot/cold behavior, typed-key collisions, mutation and
rehashed-mutation refusals, source identity changes, bounded FIFO/capacity,
detached returns and a real subprocess restart followed by explicit full warm.
The subprocess uses a deliberate copied-tree working directory and asserts its
memo, reducer and HMS imports; PYTHONPATH alone is not relied upon.

`benchmark.py` compares the full verifier, three hot verifications and cold
refusal under the same read-only SQL guard on both actual historical groups.
It retains SQLite stores, receipt projections, imported identities, charged
cache usage and timings. No timing threshold is used as a correctness claim.
These measurements are host samples, not worst-case latency, real-time or
physical-task qualification. The finite 20 MiB/4,130-document closure still has
a proportional read/hash cost even when semantic work is cached.

After source review, the smallest live port is the private loader seam plus a
single memo module, fresh current-code test outputs, and explicit startup or
service cache admission. The current historical compiler/worker pins must not
be substituted for that qualification. Durable worker-attempt supervision,
trusted persisted service configuration, exact archived-result replay, public
mounting and the broader persistent-app/I/O/driver/hub/learning scope remain
separate required work.

## Final staged observations

Attempt01 passed 15 tests in 50.218 seconds; its 443 copied inputs were stable.
Attempt02 added explicit import provenance and complete reread assertions and
passed all 17 tests in 107.375 seconds (113.479 seconds including runner setup).
Its 443 copied inputs remained unchanged through both tests and benchmark.
The reviewer ran no tests and found no remaining memo/storage correctness
blocker at the final source pins.

For the 27-case, 204-document historical group, the full verifier took 11.591
seconds; three hot checks took 0.743, 0.636 and 0.441 seconds. The 10-case,
87-document group took 4.375 seconds full and 0.159, 0.386 and 0.200 seconds hot.
Cold verification refused in 0.471 and 0.154 seconds. Cache charges were 404660
and 178048 bytes, respectively. DB changes during all verifications were zero;
cache usage was unchanged. SQLite stores, receipt projections and raw measurements
are retained in `attempts/02/benchmark/`. These host-load-dependent observations
do not guarantee a sub-second authority lock, especially across multiple
candidates and final rechecks. No deadlines or freshness bounds were widened.
