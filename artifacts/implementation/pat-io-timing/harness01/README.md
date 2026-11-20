# Isolated pure65 harness

This is a narrow adaptation of the retained pure34 runner/child, with the stronger
original-scratch retention checks from resolver harness03. Borrowed input hashes,
exact targets and source diffs are retained beside the harness. The primary agent
read the borrowed runner/child and the complete adaptation diff before release.

See [scope](SCOPE.md), [targets](targets.json) and [index](index.json). The exact
execution command is:

```
python3 artifacts/implementation/pat-io-timing/harness01/run_attempt.py attempt01-pure65 --parent-released
```

Preparation itself imports no project modules and runs no tests. Actual results
belong to the unique attempt directory. A passed pure suite establishes static
validation/planning behavior only, not I/O execution qualification, live source
integration, physical behavior or the complete HMS goal.
