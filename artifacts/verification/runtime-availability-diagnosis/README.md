# Mixed-route availability refusal: exact retained evidence

The full attempt `20261106T203848.199512Z-167d040b9d57` failed: **459 tests,
one assertion failure, one separate observer error**, with stable inputs and
compiler identity. This lane diagnoses only the mixed-route assertion failure.
The exact attempt receipt, failure capture and nine relevant source files are
copied and pinned in `input-pins.json`; `diagnosis.json` contains the extracted
facts. No source/test file was changed and no test or native program was executed
for this diagnosis.

The failure is **fresh invoke admission refused with `DEVICE_UNAVAILABLE`** for
`sim:cli-c2-focus`. It is not an accepted operation rejected before dispatch.
Seven preceding scenarios completed. Both failed focus attempts retained exactly
the same request/key and observed unchanged operation/claim/compact-command counts
of `(7, 0, 4)`, with no replay-key row. The captured database independently confirms
those counts and contains no focus operation. One earlier `cli-c1-inspection`
admission had the same refusal and recovered within the already existing bounded
retry policy; the focus request exhausted that policy's three-second window.

All times below are UTC on 2026-11-06:

| Retained fact | Time |
|---|---|
| Previous compact C2 fan accepted | 20:43:59.546 |
| Previous fan dispatch claimed | 20:44:00.610 |
| Previous fan completion and resource release recorded | 20:44:02.413 |
| Focus request `notBefore` | 20:44:02.543 |
| Focus request latest start | 20:44:07.543 |
| Shared replay namespace expiry | 20:44:07.765 |
| Failure capture began | 20:44:07.798225 |
| Authority backup began | 20:44:07.799037 |
| Later captured authority clock floor | 20:44:08.071 |

The admission path checks namespace and latest-start bounds before calling the
live presence guard. `DEVICE_UNAVAILABLE` comes from missing presence or a sampled
authority time at/after its expiry. Exact refusal-time samples and the specific
presence rows read by those two attempts were not retained. Therefore the code
identifies the guard and stage, but the snapshot cannot establish the exact expiry
chronology or which wait/commit caused it.

The captured C2 presence expires at 20:44:08.935. With this adapter's fixed 1000 ms
TTL, its assignment origin was 20:44:07.935—after capture began. It is a later
renewal, not evidence that either earlier refusal saw valid presence. The captured
ready observation is valid/true, the compact fault field is null, and subsequent
HELLO packets exist. Those later facts do not reverse the original refusal.
Retained C2 HELLO ticks include inter-sample gaps of 1259, 1471 and 1515 ms near
the preceding fan/focus transition; these are endpoint-sample intervals, not
measurements of the admission mutex wait or exact presence expiry.

The guard failed closed, and the test's existing bounded exact-request retry
exhausted. No specific production safety defect or unique scheduling/storage root
cause is proved. Increasing TTL, deadlines, namespace lifetime or retry duration
would not diagnose it. A blind full rerun is likewise not a diagnosis.

The next useful evidence is a deterministic multi-route availability probe or
refusal-time diagnostic recording of the exact presence row, authority sample and
guard stage. Only after that evidence should a change be selected. One candidate
to evaluate is a bounded refresh of the specifically requested route before a
fresh admission, outside any Journal transaction, followed by the unchanged full
admission checks on the same request/key. It must never retry an accepted/uncertain
handoff, change identities or extend any original bound; this lane does not claim
that the candidate would recover this run within its remaining bounds.

The separate `test_endpoint_cli` observer's `database is locked` error is recorded
in the pinned attempt receipt and is being reviewed in another lane.
