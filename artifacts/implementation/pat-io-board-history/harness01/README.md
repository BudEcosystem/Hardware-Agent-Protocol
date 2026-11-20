# Isolated combined board-history74 harness

This adapts the retained pure39 runner to 35 new board-history methods plus the
unchanged 39 transcript-reader methods. See [scope](SCOPE.md),
[selection](targets.json) and [index](index.json). The released command is:

```
python3 artifacts/implementation/pat-io-board-history/harness01/run_attempt.py attempt01-pure74 --parent-released
```

The default outer deadline remains 180 seconds. SQLite connections, network and
child-process creation are forbidden. The child reads historical trial20 JSON
data; it does not construct a Runtime or execute the simulator again. Every
attempt retains its source/data closure, logs, origins and original scratch.
Preparation uses static AST/hash/source checks only.
