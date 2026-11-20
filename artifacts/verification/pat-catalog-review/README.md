# Independent PAT catalog review

The final independent run passed **20 tests**, with no failures, errors or skips,
in 12.088 seconds. The eleven imported project source files were unchanged across
that run. [The final receipt](attempt-002/run.json),
[test log](attempt-002/test.log), and [source pins](attempt-002/source-before.json)
are retained with copies of those sources under `attempt-002/inputs/`.

The reviewed implementation is a finite local PAT catalog foundation. These
tests exercise catalog authority, immutable evidence, concurrency and SQLite
process-loss behavior. They do not execute a PAT, prove a PAT's complete domain,
qualify an evaluator, or establish a physical objective. No model, acquired
controller program, native endpoint, emulator, or hardware I/O was executed.
The tests use original Python fixtures, the existing project dependencies and
temporary local SQLite databases.

## Scope and conclusions

The tests use the real `RegistryPolicy` and `Registry`, including actual admin
grant revocation while an evaluator callback is outside the Journal transaction.
Candidate inputs cannot inject receipts: registered evaluator code returns its
bounded result, and the catalog constructs the receipt. Administration is checked
at entry and again before evidence commits. Trusted environment and compiler
providers run inside the transaction and must remain pure, bounded and
non-reentrant. Evaluator callbacks remain trusted installed code, run outside the
transaction, and are restricted by the catalog contract to controlled simulation.
The library does not impose a callback execution timeout or sandbox.

The independent cases establish, for the pinned implementation:

- Admin and deployment scoping on publish, describe, artifact/evaluation reads,
  snapshots, events, evaluation and transitions; revocation during a callback
  prevents its catalog commit.
- Detached candidate and receipt ownership; exact run replay avoids reevaluation;
  a run key cannot silently attach to another artifact.
- Environment drift preserves the evaluated facts while preventing promotion;
  evaluator revocation inhibits both new evaluation and replay eligibility.
- Malformed results, exceptions and valid inconclusive trials retain evidence and
  suspend an active entry. A malformed result reports unknown unresolved effects
  as `null`, without copying an exception's potentially sensitive message.
- Concurrent identical results create one evaluation. Disagreeing results retain
  the conflicting receipt, set a durable conflict flag, and inhibit promotion.
  A pass promoted between callbacks is suspended when its conflict commits.
  Two identical conflicting callbacks create only one conflict event/revision.
  Replaying the original pass does not clear the flag; a distinct new evaluation
  can. A cross-artifact conflict inhibits both entries and preserves retirement.
- Revision compare-and-swap rejects stale promotion after new evidence; even a
  new passing trial suspends an active entry until a new promotion decision.
- Malformed environment data and host clock loss do not prevent
  authority reduction. Non-reentrant providers cannot mutate Registry authority.
  Revision exhaustion inhibits new reuse, and failed writes roll back atomically.
  Event cursors cannot advance beyond the committed deployment head.

The root implementation was corrected during review for provider-failure rollback
of suspend/retire, future event cursors, concurrent same-run disagreement, and
eligibility at revision exhaustion. The disagreement issue was identified jointly
with the root review; the independent tests verify its durable conflict behavior.
No unresolved implementation defect was found within this scope after those fixes.

## Abrupt process-loss evidence

One test executes six child-process cases using only the original Python test
module. Publish, evaluation and activation each have a case that calls
`os._exit(79)` after business writes and before the catalog event, and a case that
calls `os._exit(80)` after the operation commits.

For each interrupted transaction, a deliberately small SQLite cache and a test
table force dirty-page spill; the child checks and records a nonzero rollback
journal header before exiting. Reopening recovers exactly the prior catalog rows,
leaves no spill row and passes SQLite `integrity_check`. For each committed case,
the expected candidate/evaluated/active state and single new revision survive;
applicable exact replays do not create new rows. These are process-loss checks on
this filesystem, not power-loss, storage-device or physical-timing qualification.
The new conflict transaction is covered by concurrency and reopen tests, rather
than a separate abrupt process-loss injection.

## Bounds and remaining trust

The catalog limits entries to 128, installed evaluators to 32, required/result
checks to 128, evaluator identity to 8 KiB, environment to 16 KiB and evaluator
result to 32 KiB; event pages contain at most 100 events. Exact integers are used
for revisions and cursors. Evidence and event history is append-only and not given
a practical total storage quota by this foundation. The deployment revision bound
is a fail-closed exhaustion limit, not a storage-management policy.

An installed evaluator's policy and code identity, the environment provider,
compiler digest provider, Journal ownership and local storage remain trusted.
The receipt's artifact/domain digest and required check categories bind declared
inputs and policy; they do not manufacture a coverage or physical-qualification
claim. This review does not establish end-to-end PAT selection, instance admission,
CLI/MCP exposure, deterministic PAT invocation, or native Harness integration.

## Retention and rerun

`attempt-001/` retains the earlier successful 19-test run before adding the final
cross-artifact and exhaustion coverage. It is historical evidence; `attempt-002/`
is the final 20-test result. Existing unrelated receipts and source files were not
edited by this review. The independently owned test is
[`tests/test_pat_catalog_review.py`](../../../tests/test_pat_catalog_review.py).

Run again into a new, never-overwritten attempt directory:

```sh
python3 -B artifacts/verification/pat-catalog-review/run_review.py attempt-003
```

`review.json` records the final source and output hashes. Its own hash is reported
to the parent review, rather than included recursively in that manifest.
