# Simulation qualification design review

Design review only. This addendum tightens the frozen
[service plan](../pat-service-design/PLAN.md); it does not implement or test it.
The review used the plan and selected current catalog, compiler, execution and
binding code. Exact inspected source identities are recorded in `index.json`.
No claim of complete source reading, model execution or physical qualification
is made.

The next implementation should provide an executable isolated simulation
evaluator before exposing public PAT mutation tools. Its first outcome policy
remains a bounded fan set-level sequence. Six requirements need to be explicit.

1. Persist a small qualification-attempt record keyed by deployment, evaluator
   and run ID before launching a worker. Pin a complete input capsule and
   serialize fresh service evaluations. A completed archived result without a
   catalog receipt must be verified and reused byte for byte. Do not rerun it
   and normalize random operation identities to make results agree. Interrupted
   attempts remain visible; any rerun needs separate retained provenance and
   evidence that the previous worker cannot continue writing.
2. Catalog eligibility currently checks evaluator identity and environment, but
   does not verify referenced evidence bytes. Missing or corrupt evidence must
   be indeterminate and abort selection; filtering that candidate could create
   false uniqueness. Prefer a bounded evidence capsule retained with the
   receipt or in the authority database. Verification within a catalog
   transaction must be pure and bounded. Large external traces need an explicit
   verification protocol if they are required for continued eligibility; one
   hash check before the evaluator returns cannot enforce later integrity.
3. The evaluator callback receives the artifact and a digest-only environment.
   Associate it with one exact detached capsule containing installation,
   bindings, semantics, configuration revision and case matrix. Reconstruct and
   compare the worker environment before execution. Unsupported reconstruction
   must refuse rather than substitute defaults. Configuration or capsule drift
   under a retained run ID is a conflict, not permission for a new evaluation.
4. Define deterministic applicable integer intervals/enumerations by intersecting
   static predicates. Reject empty domains and specify case ordering and
   deduplication. Keep conservative whole-declared-domain compiler checks.
   Finite boundary trials do not prove all behavior over an integer domain.
5. The fan oracle must check each step's actual bound arguments, request identity
   and committed receipt, effect deltas from a retained baseline, absence of
   extra operations/effects and absence of remaining claims. Other installed
   focus/inspection devices must remain unchanged. This establishes only the
   declared simulation capability outcome.
6. Pin the actual execution closure: case generator, oracle, worker/supervisor,
   parser, Runtime, adapter, simulator, installation and validation dependencies.
   Configuration drift should disable fresh qualification/reuse while retaining
   status, cancellation and reconciliation for already admitted procedures.

The existing one-latest-environment-per-artifact-per-deployment limit remains
explicit. Simultaneous alternate qualified bindings require a separate catalog
change, not cosmetic artifact renaming.

Implement in three parts: pure configuration/policy contracts, environment
extraction, case generation and evidence capsule; then isolated worker, oracle
and durable attempt/result retention; then trusted Runtime reconstruction and
promotion/reuse integration. Checked public PAT tools follow. Device I/O,
driver/hub providers and persistent Arduino applications remain required work.
