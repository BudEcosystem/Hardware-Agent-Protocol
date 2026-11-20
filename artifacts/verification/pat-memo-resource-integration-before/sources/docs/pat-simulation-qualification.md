# PAT simulation qualification components

The host libraries now contain a closed simulation configuration/case planner,
shared static environment extraction, an isolated original SQLite fan worker,
an optional catalog evidence verifier, and a bounded evidence reducer/store. The
supervisor, durable qualification attempts and Runtime/public mounting remain
unfinished. The store's corrected integration run passes 46 tests, using fresh
worker output and the real catalog gate. The complete runtime run passes 643 tests
with all 131 captured inputs and compiler identity unchanged.
These components do not yet provide a user-facing qualification service or
prompt-to-program learning.

## What the worker executes

The installed policy `hms.pat.eval.sqlite-fan-sequence/0.1` accepts one fan role,
one to sixteen `set_level` steps, explicit percent units and at most two varying
declared integer domains. Whole declared domains must fit the installed binding;
an applicability predicate cannot hide an invalid declared domain. The finite
matrix includes nominal/boundary values, invalid types, missing/extra parameter assignments,
domain and applicability exclusions, and wrong task/profile/evidence context.
Sampling is not exhaustive behavioral verification over every integer tuple.

`hms/pat_simulation_contracts.py` parses the closed setup document and generates
the cases. Configuration contains explicit registered instances and artifact-to-
role assignments; it cannot supply Python paths, commands, callbacks or results.
The compiler's `evaluation_environment` derives static dependency identity
without inventing input parameters, operation keys or timestamps. `compile_pat`
uses the same validation helpers and still checks concrete inputs and envelopes.

`hms/pat_simulation_worker.py` accepts a bounded detached capsule and a trusted,
private empty output directory. It reconstructs a fresh original SQLite Runtime
and plant for every trial, with new authority, sessions and replay namespaces.
It does not copy a live authority database or admitted operations. The exact
installation, supported binding generation, units and static environment must
reconstruct successfully. Captured configuration hashes are provenance, not
proof that a live service authorized that configuration.

Applicable cases execute through the actual compiler, ProcedureStore, Journal
and original simulation adapter. The oracle checks intended arguments, linked
operation and receipt identities, fences, exact completed effect counts, final
fan value, no remaining claims and unchanged unrelated simulated devices. It
tests parent/child exact replay and conflicting request keys. A modified receipt
that substitutes integer `1` for Boolean `true` fails the typed oracle.

Five additional nominal trials exercise cancellation before dispatch, cancellation
while pending, owner reopen before dispatch followed by explicit resume, owner
reopen of pending work, and lost completion evidence after the plant commit.
The last uses a one-shot exception and reopen; it is not an abrupt process-crash
test. Unknown or contradictory effect accounting remains inconclusive, including
unexpected extra effects on the fan or another device.

The worker retains canonical paged evidence containing the input, reconstructed
dependencies, exact compiled requests, checkpoints, operations, receipts, event
pages and trial results. It retains scratch databases and raw random identities.
Every emitted evidence file is read back and hashed before success. A future
supervisor must independently verify retained bytes before importing evidence;
the worker's return object alone cannot qualify an artifact.

## Bounds and unfinished supervisor

The current policy ceilings are 32 cases including lifecycle trials, 512 child
operations, 2,048 scheduler ticks, 16 MiB of emitted canonical evidence, and a
60-second deadline checked at Python boundaries. Setup may lower the ceilings;
the policy digest changes with those limits. Required cases cannot be truncated
to fit. Existing application deadlines and execution limits are preserved.

The emitted-byte bound excludes scratch databases and the small return object.
Scratch size is reported separately with `totalDiskQuotaEnforced:false`;
return-object retention is a supervisor responsibility.
Boundary time checks cannot terminate a blocked process. Total retained storage,
process termination, durable attempt identity and concurrent-call serialization
belong to the unfinished supervisor. It must preserve interrupted work and
reconcile unknown outcomes. Removing a database is not evidence that effects
were resolved. A completed archived attempt must be reused byte-for-byte after
a crash before catalog commit; generating fresh random IDs would create a
different evaluation result for the same key.

This is trusted original code, not a malicious-code sandbox. No model, device,
acquired controller, MCU or emulator runs during these tests. Fresh synthetic
state and fan set-level receipts do not establish physical airflow, enclosure
temperature control, electrical behavior or general task success.

## Catalog evidence gate

`hms/pat_simulation_evidence.py` reduces the actual worker records into a complete
content-addressed group and imports it atomically into SQLite. The group retains
the original input, result, index pages and records, plus independently derived
case summaries. Reads check storage type and actual BLOB size before materializing
bytes; every referenced content hash and the complete expected group must match.
The test inputs are captured independently before each fresh worker execution.
There is no caller-supplied successful-evaluation interface.

The current library repeats full semantic reduction during eligibility. It
reconstructs the finite case matrix, compiled requests, receipt/effect attribution,
event ordering and lifecycle boundaries. Raw replay-key/resource-floor SQL rows,
some refused-request replies and scheduler/storage counters were not emitted by
the worker and remain assertions of its pinned implementation. Logical store
quotas do not bound SQLite/WAL/filesystem allocation. A supervisor must still
authenticate the producer channel, retain interrupted attempts and enforce storage
and process lifecycle policy. This library is not mounted as a Runtime service.

`Evaluator` may configure both `evidence_profile` and `verify_evidence`.
Legacy evaluators retain their exact original identity shape. Configured
verifiers contribute their profile to identity; their installed code must be
covered by the evaluator implementation digest.

The verifier runs after exact evaluator/environment matching, inside the
authority transaction, and receives a detached receipt. Only exact `True`
succeeds. Missing, corrupt, unavailable or malformed evidence gets a distinct
`PAT_EVIDENCE_*` refusal. Those refusals abort deterministic selection rather
than removing one candidate and accidentally making another look unique.
Final selection rechecks evidence before allocating an instance. Historical
exact run replay still precedes new qualification checks.

A scoped SQLite authorizer permits ordinary reads of the owned main database
and the built-in `typeof` and `length` functions needed to bound BLOB reads.
It denies writes, schema/connection/transaction commands and other SQL functions.
Attempted denial or verifier reentry aborts the outer transaction even if the
callback catches the exception. The prior ordinary connection behavior is
restored afterward. Journal owns this connection and installs no other authorizer;
replacing connection policy or using another writer/service violates the trusted
provider contract. This guard does not isolate arbitrary Python effects or
enforce verifier CPU/memory bounds. The [two retained primary API pages](../research/host-contract/authorizer-followup/NOTES.md)
document the compilation-time limitations; cached-statement behavior is covered
by the installed-host regression test.

The original hook tests use explicitly synthetic retained capsules. The evidence
reducer/store validates content hashes, receipt associations, the complete case
plan and emitted outcome facts using bounded reads. Full semantic verification
currently takes seconds and remains unsuitable for routine admission under the
authority lock. A separate staged bounded memo reuses only a previously validated
exact input/result/record closure under the same imported code identity. It still
reads and hashes every current SQLite document. Cold or evicted entries refuse;
they cannot silently disappear from selection or trigger model-based novelty
handling. Explicit warming outside eligibility and the capacity policy still need
service integration. Public
PAT tools must wait for that service and attempt lifecycle to be connected.

## Retained checks

- The [live evidence integration proof](../artifacts/verification/pat-evidence-live-integration/index.json)
  retains two 46-test passes with 131 copied inputs. Attempt02 fixes child import
  provenance and exceptional evidence retention; three separate runner checks
  cover copy failure, report failure and successful retention. Each attempt keeps
  fresh 27-case and 10-case worker outputs, a real output-budget refusal and all
  scratch databases. A real catalog/instance test accepts the complete evidence,
  refuses a new run after a required document is removed, and preserves historical
  exact replay.
- The [separate memo stage](../artifacts/implementation/pat-evidence-fast-verification/index.json)
  passes 17 tests on its retained historical producer inputs. It checks exact
  typed cache keys, corruption and rehashed semantic changes, cold/restart/eviction
  behavior, bounded retained payloads and rereading every current document.
  The [measurement](../artifacts/implementation/pat-evidence-fast-verification/attempts/02/benchmark/result.json)
  records full verification at 11.591 seconds versus three hot checks at
  0.441–0.743 seconds for the 27-case group. This is an observed comparison, not a
  current-service or worst-case latency result. The eight-entry cache and the
  128-artifact catalog require an explicit capacity and warming policy.

Stored catalog evaluation receipts are now read with type and size checks,
canonical-byte and digest verification, and exact deployment/artifact/evaluator/
run associations before outcome or environment filtering. Conflict receipts must
point to the original evaluation for that exact run. An active entry with a
missing or contradictory evaluation aborts selection. This prevents damaged
evidence from eliminating one candidate and making another appear uniquely
eligible. The [seven regression checks](../artifacts/verification/pat-evaluation-integrity/index.json)
retain their failing reproductions and corrected pass; the
[independent resolution review](../artifacts/verification/pat-evaluation-integrity-review/resolution-01/review.json)
records the inspected source. Hashes detect damaged bytes and associations;
they do not authenticate arbitrary database writers.

The [bounded-read hook checks](../artifacts/verification/pat-bounded-evidence/index.json)
pass all 12 tests, including BLOB versus NUL-containing TEXT handling and denial
of SQL functions other than the two metadata built-ins. Earlier hook and full-run
evidence below retains its original, narrower source scope.

- The [pure integration proof](../artifacts/verification/pat-service-pure-integration/index.json)
  passes 126 tests: 89 earlier PAT checks, 19 new configuration/domain tests and
  18 environment tests, at its exact copied 120 inputs.
- The [worker proof](../artifacts/verification/pat-simulation-worker/index.json)
  retains all four focused attempts. Its final 16 tests pass on 43 copied inputs;
  the full fan fixture runs 27 trials and 25 child operations. An aliased instance
  with a noninitial, narrowed binding runs ten trials and nine operations. These
  inputs predate the catalog hook; current integration is checked separately.
- The [evidence-hook proof](../artifacts/verification/pat-evidence-hook/index.json)
  retains an initial nine-test run with one incorrect expected SQLite error number,
  followed by ten passing tests, including reentry hardening. No production
  mutation bypass was observed in that initial failure. The separate
  [read-only review](../artifacts/verification/pat-evidence-hook-review/review.json)
  found no remaining blocker in its stated source scope.

The [current runtime receipt](../artifacts/verification/local-runtime-current.json)
records the combined full-suite attempt separately. The catalog still supports
one latest qualified environment per artifact per deployment; these components
do not add simultaneous environment alternatives, persistent controllers,
GPIO/PWM policies, driver management or hub compute scheduling.
