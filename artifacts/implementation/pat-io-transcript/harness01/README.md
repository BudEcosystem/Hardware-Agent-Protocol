# Isolated transcript39 harness

This adapts the retained pure65 harness to 39 pure transcript checks over copied,
sealed trial20 data. Source/dependency acquisition, isolated Python startup,
actual-origin recording, bytecode refusal, owned-child collection and original
scratch retention are unchanged. See [scope](SCOPE.md), [selection](targets.json)
and the [frozen index](index.json).

The released command is:

```
python3 artifacts/implementation/pat-io-transcript/harness01/run_attempt.py attempt01-pure39 --parent-released
```

The default outer deadline remains 180 seconds. The child cannot connect to
SQLite, use the network or start another process. It reads retained trial data;
it does not execute the original simulator again. Test success establishes only
the reader's covered serialization checks, not independent effect qualification.

Preparation uses static source/AST/hash checks. Actual attempts retain their own
source, data, logs and receipts. No failed attempt or original scratch is deleted.
