Current-baseline synthetic provider verification

All 24 focused provider tests passed in 101.898 seconds (103.61864149398752 seconds including harness work). The 146 copied inputs, compiler identity and provider source identity remained unchanged. The attempt retains 71 authority/board/context evidence files. No live source or earlier proof was changed.

The 139-file baseline exactly matches both snapshots in the passed full696 receipt `20261107T001334.443472Z-59acecf941d0`; every baseline and final snapshot hash was checked. The provider was not included in that parent full run. `parent-final-comparison.json` records this distinction. Source-preparation metadata remains historical, and its original README is retained as `README.source-preparation.md`.

All six provider modules are byte-identical to the sealed reviewed provider stage. The assembled copy only adds the exact hashed board-state filename allowance and changes its test helper import to the current normal `test_resource_topology` fixture, whose four helper ASTs match the old fixture. `assembly.json` retains the precise source origins. `run.py` imports only the copied image and preserves exact input/identity pairs, scoped imports, runner bytes, log and actual SQLite evidence under the one immutable attempt.

The covered original-model cases include shared cross-route GPIO/PWM exclusion, independent pad progress, exact replay/fences, safe idle before claim release, cancellation, restart/reconciliation, missing/contradictory receipts, delayed start/effect validation, invalidation/grant loss during historical recovery, and bounded poisoned receipt reads. The inherited ResourceCatalog is the hardened current version.

Erratum: the immutable result limits phrase “no ... model execution” is too broad. This run did execute the original synthetic SQLite I/O model. It executed no neural-model inference, acquired controller/program, native endpoint or physical I/O. The raw result and runner are preserved unchanged; `proof.json` records the correction.

This proof does not establish public Runtime/daemon/IPC/CLI/MCP mounting, PAT qualification, physical or autonomous stop timing, SQLite internal resource bounds, or driver lifecycle settlement. The independent lifecycle design review is separate at `../io-lifecycle-settlement-review/`; its acceptance tests remain future work.
