# Controlled aged observation branch

One controlled original-native CLI run passed in 35.617 seconds, with the same
113 frozen inputs used by the separate seven-test proof. No production or test
source changed. An artifact-only subclass waited 11 seconds exactly once, after
the first operation completed and both exact replays returned, immediately before
the original final strict `observe --max-age-ms 10000` call.

The first strict query returned exactly `OBSERVATION_STALE`. The separate checked
historical Client observation returned valid quality, the expected value and
original identity/acquisition tick, with age upper bound **18777 ms**. The unchanged
test assertions checked the endpoint session, binding, control, calibration,
source and evidence kind. The pause retained one OP frame before and after; the
complete three-scenario run retained exactly three OP frames, matching its durable
transmissions. Focus and inspection remained strictly fresh at 6168 and 5654 ms.
Every original acquisition tick was preserved.

This deliberately exercises the historical branch. It is not a reproduction of
an earlier run's exact timing, a larger freshness limit, an operation retry, or a
new value sample. No operation deadline, lease, TTL or max-age argument changed.
The first operation had already completed, released claims and retired before the
pause; no new OP was sent during the wait. The native fixture's protocol results
and original byte relay establish synthetic completion/handoff evidence, not an
independent physical effect measurement.

`run.json` retains the actual report, strict error, historical projection, original
results/ticks and controlled-wait timestamps. `tests.log` is the actual unittest
output. `run.py` is the artifact-only subclass and runner. `input-references.json`
pins the existing immutable 113-file source tree without duplicating or changing
it, plus the preceding seven-test receipt. The earlier unchanged stale diagnostic
and seven-test fresh-path proof remain separate, immutable receipts.
