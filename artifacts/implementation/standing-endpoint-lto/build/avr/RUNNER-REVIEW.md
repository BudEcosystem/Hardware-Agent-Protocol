# Runner delta for parent review

Baseline: sealed fit runner SHA256 `affe1b4e933a9a02b46e793edfc63bbf0fb38dc1d99acbabc96d9ed43eec6993`. [runner-diff.patch](runner-diff.patch) contains the complete proposed delta. Native commands and the required thirteen standing cases are unchanged.

The changes are: matching compile/link LTO options; archive-checked backend/plugin and selected specs pins; selected backend/plugin path and built-in-spec queries; pinned make and possible shell with explicit environment/private temporary directory; before/after symlink-target snapshots; 29 function/nine storage roots and exact/nonoverlapping storage checks; explicit pre-LTO fat-object stack labels; and post-settlement generated-artifact inventory with final-stack/runtime-fit fields kept unqualified/false.

Per-command records additionally retain the exact constructed environment and private working directory. No inherited make flags/jobserver state is accepted. The original one-command-at-a-time owner, unreaped-leader group authority, pidfd adoption cleanup, INT/TERM masking, fixed per-process limits, observed group RSS bound, strict empty-stderr criterion and immutable intent/start/result receipts remain. A new warning, compiler refusal or cleanup failure must be preserved instead of suppressed.

The compiler driver, LTO wrapper, backend, linker/plugin and possible make descendants are trusted pinned tools inside the existing orderly-cleanup model. This is not a cgroup or hostile-process sandbox, does not qualify runner SIGKILL/host death, and does not pin every host shared library. The final alias/file/source checks are observations, not an immutable-filesystem claim.

The runner saves conventional `.su` records before linking so a failed link cannot leave them ambiguous. Its final inventory may identify possible backend `.su` files, but does not automatically use them as a complete final graph. The exact linked API/vector symbols, all charged objects, library helpers, callbacks and ISR frames must later be reconciled against final instructions and backend evidence. No old finite or fat-object stack total is transferred to the LTO image.

This runner has not been imported or executed in the new lane. Parent review and a separately retained attempted invocation determine subsequent results.
