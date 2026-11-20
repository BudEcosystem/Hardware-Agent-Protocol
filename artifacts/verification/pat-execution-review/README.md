# Independent PAT execution source review

The final read-only review found no remaining blocking defect within the inspected host-library scope. The exact reviewed inputs are retained under `inputs/`; `reading.json` distinguishes four complete production-file reads from selected dependency and test-source reads. Acquisition does not imply reading. No HMS module, test, model, controller, emulator or hardware was executed by this reviewer during this review.

The draft review identified and the frozen implementation addresses:

- Integral-float parameters could alias integer replay digests because the scalar predicate's result was ignored. The run parser now rejects unsupported scalar types before hashing.
- An inaccessible east-qualified artifact could block an authorized west-qualified alternative. Authorized compiled assignments now match the stored passing environment before current environment/evaluator callbacks run.
- Unavailable evaluators and invalid/unsupported environment providers could disappear from selection. Only explicit known ineligibility reasons are filtered; service failures refuse the run.
- Unregistered compatible installed devices could disappear from enumeration. The provider now checks current installed maps and refuses missing semantic registration for an authorized compatible candidate.
- Accidental resolver/selection SQL mutation is detected before admission. The selected inventory digest, registry revision and optional registration identity are retained, and compiler identity includes the new PAT source files.

The reviewed path keeps both clock checkpoints before legitimate business writes, reuses the procedure admission helper, and commits procedure, key reservations, PAT instance and trigger linkage together. Exact replay precedes current selection and clock checks, validates owner/read access and retained linkage, and cannot adopt an existing plain procedure. Namespace pruning still refuses replay. Catalog suspension does not rewrite an admitted instance. Cancellation and recovery reuse procedure and child-operation semantics.

The boundary remains trusted in-process code: callbacks must be pure, bounded, non-reentrant and stable under the authority lock. SQL change detection is not a sandbox against malicious callbacks, explicit commits, external mutation or unbounded execution. Inventory hashes identify the observed resolver output; they do not independently prove a custom resolver's completeness. Installation/driver labels and evaluator evidence remain trusted registrations, not binary or physical attestation.

These are finite, simulation-only Python libraries, not mounted PAT CLI/MCP/runtime methods. This review does not establish prompt interpretation, learning, production qualification, persistent controllers, device I/O, driver lifecycle, hub management, target timing or distributed/physical exactly-once effects. Selection bounds do not bound retained database history. The single-owner SQLite transaction assumption remains material.

`source-after.json` records matching before/snapshot/after hashes for all twelve inputs. This detects endpoint drift, not transient edit-and-restore or an atomic filesystem snapshot. `verify.py` checks the frozen receipt and coverage without importing project code. Add `--compare-live` to compare the current checkout; historical verification otherwise remains independent of later source changes. Test sources were inspected only in the recorded ranges; test results belong to the implementation agents' separate receipts.
