# Isolated combined procedure-history146 harness

This adapts the retained pure112 runner to 34 new procedure-history methods plus
all 112 prior operation, board-history and transcript tests. See [scope](SCOPE.md),
[selection](targets.json) and [index](index.json). The released command is:

```
python3 artifacts/implementation/pat-io-procedure-history/harness01/run_attempt.py attempt01-pure146 --parent-released
```

The original 180-second outer deadline and acquisition limits remain unchanged.
SQLite, network and subprocess creation are forbidden in the child. Every attempt
and original scratch are retained. Historical trial data is not executed again.
