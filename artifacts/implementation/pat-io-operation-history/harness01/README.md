# Isolated combined operation-history112 harness

This adapts the retained pure74 runner to 38 new operation-history methods plus
the unchanged 74 board-history/reader methods. See [scope](SCOPE.md),
[selection](targets.json) and [index](index.json). The released command is:

```
python3 artifacts/implementation/pat-io-operation-history/harness01/run_attempt.py attempt01-pure112 --parent-released
```

The original 180-second outer deadline and all acquisition bounds are unchanged.
SQLite, network and subprocess creation are forbidden in the child. Original
scratch and every attempt are retained. Only historical JSON data is inspected.
