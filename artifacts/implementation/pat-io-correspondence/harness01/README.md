# Isolated focused correspondence41 harness

Run the 37 new correspondence tests and the four prior methods covering all
retained histories. See [scope](SCOPE.md), [selection](targets.json) and
[index](index.json). This is a focused 41-test result, not a rerun of the prior146.

```
python3 artifacts/implementation/pat-io-correspondence/harness01/run_attempt.py attempt01-focused41 --parent-released
```

The original 180-second outer deadline, acquisition limits, source-only startup,
SQLite/network/subprocess prohibitions, child ownership and raw retention remain.
Only copied historical trial data is inspected; no runtime/device is executed.
