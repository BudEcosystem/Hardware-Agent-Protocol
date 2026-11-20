# Provider source preparation on the current baseline

This directory currently records **source preparation only**. No provider
imports, tests or Runtime execution have occurred in this lane. Live sources
and the earlier provider stage remain unchanged.

`baseline/` contains the 139 exact files from
`runtime-attempts/20261107T001334.443472Z-59acecf941d0/inputs-before/`.
The parent full696 run was still pending during preparation. Since its final
receipt had not yet serialized the input rows, `baseline-inputs.json` derives
the inventory from those retained files and records each original snapshot
path. Every byte also matched the frozen live counterpart at acquisition.
This is source provenance, not a claim that the parent run passed.

`provider-source/` preserves the exact six reviewed provider modules, tests,
helper, state-path change, design, README, proof and index from the sealed
`io-synthetic-provider` stage. Its index is
`b8ec279e86b8cea07173b6ce67cf521058535441d2feb8926dd1800641f19b2d`.
No earlier stage file or proof was edited.

`tree/` combines those current baseline files with the provider. All six new
modules are byte-identical to the sealed stage. The copied `state_path.py`
receives only the previously reviewed exact hashed board-database prefix. The
copied provider test imports the current normal `test_resource_topology`
helpers instead of a stage-local helper module; their four function ASTs match.
No other integration change was needed by source inspection. The prepared
tree contains 146 files, pinned by `prepared-inputs.json` and `assembly.json`.

This baseline includes the corrected ResourceCatalog/Registry storage reads,
scalar-preserving binding validator and compiler dependency-resource identity.
The parent compiler identity copied here is acquisition evidence only. Adding
the provider changes its whole-project implementation identity; no prepared
`implementation_digest()` was invoked during source preparation. A later run
must capture the actual prepared compiler and provider identities separately.

`run.py` is prepared for the 24 provider tests after the parent's execution
hold is released. It copies the prepared tree before imports and retains
source/compiler/provider identity checks, imports, logs and actual authority
and board evidence. It has not been invoked. Any failure must be retained and
diagnosed without widening deadlines or replacing the old source proof.

This is an internal original SQLite model. It adds no stock Runtime, daemon,
IPC, CLI or MCP configuration path, PAT qualification, physical I/O or driver
lifecycle settlement. Controlled clocks do not establish native availability,
physical pulse timing, bounded stop latency or SQLite internal resource bounds.
