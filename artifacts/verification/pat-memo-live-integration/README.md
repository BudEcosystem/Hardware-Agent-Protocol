# Live evidence memo integration

The [focused run](attempts/01/result.json) passes all **77 tests** in 138.448
seconds at 139 unchanged copied inputs and stable compiler identity. It includes
19 memo tests, 21 compiler tests, 18 environment tests, 12 hook tests and seven
evaluation-integrity tests. The [prior source snapshot](../pat-memo-resource-integration-before/index.json)
preserves the 643-test baseline. The [review](review/review.json) inspects the
ported memo, the full store's private reduction seam, current-worker tests and
the copied-source runner. The reviewer executed no tests.

The memo accepts entries only after full semantic reduction of exact typed trust,
result bytes and every ordered raw record. Eligibility rereads the full current
SQLite graph and checks the cached result against it. A cold entry refuses; it
does not run compilation under the catalog lock or disappear from selection.
The live tests retain fresh original worker output: two 27-case artifacts,
an aliased ten-case binding and an output-budget refusal with zero completed
cases. They cover cold
promotion, ambiguous warm selection, cold selection and preserved exact replay.

The [dependency reproduction](attempts/dependency-before/result.json) retains
two actual failures at 139 unchanged copied inputs. Changing an installed
extensionless vocabulary resource left the old compiler digest unchanged;
removing it also failed to refuse identity construction. The
[retained inventory and loader](dependency-identity-before/inventory.json)
identify fourteen such resources loaded by the installed specifications package.
The live correction includes the entire inventoried schema subtree and refuses
missing selected files. Existing qualification identities remain historical.

This integrates libraries only. Runtime/public qualification mounting, durable
supervision, memo capacity/prewarming policy and actual prompt learning remain
separate work. No physical device, model, MCU or acquired controller runs here.
No admission latency or total process-memory guarantee is established.
