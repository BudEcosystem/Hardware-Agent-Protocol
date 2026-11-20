# Endpoint CLI observation semantics: scoped correction

Seven tests passed in 19.969 seconds: the original three-scenario CLI restart and
replay test, five controlled observer tests, and the existing native binding test
that proves query/restart retains the original sample age. All 113 isolated input
files matched before/after execution. No runtime source changed.

The final CLI `observe --max-age-ms 10000 --evidence-kind simulation` remains in
the same position, after both exact replays and retirement checks. A successful
strict result must be valid, correctly identified, and have a known age upper
bound at most 10000 ms. Only exit code 1, empty stdout, and the exact
`{"error":{"code":"OBSERVATION_STALE"}}` error may enter the other path.
That path makes one schema-checked Client observation without `maxAgeMs`, explicitly
for the historical projection. It must return valid quality, a known age bound
greater than 10000, the same binding/control/calibration/session/source, expected
value and original acquisition clock/tick. Other errors, unknown age/quality and
identity changes still fail. No request, deadline, TTL, sample or max-age limit is
changed, and no refresh or new operation is requested.

The test reports freshness separately from successful reconciliation and historical
value retention. In this seven-test run, all three final strict reads succeeded:

| Scenario | Known age upper bound | Cumulative OP frames |
| --- | ---: | ---: |
| Fan | 5306 ms | 1 |
| Focus | 4668 ms | 2 |
| Inspection | 4693 ms | 3 |

All three operations completed and retired; exact replay retained their identities,
results and original sample ticks. There were exactly three OP frames, matching
the original external relay bytes and durable transmitted frames. These are
synthetic native fixture results and handoffs, not independent physical effects.

This run exercised the strict-success branch. The historical branch was not
naturally reached in these seven tests. The separate preserved unchanged diagnostic
in `../endpoint-cli-failure-capture/` reproduced strict `OBSERVATION_STALE`, and its
later retained mapping crossed the 10000 ms threshold during the CLI call; it did
not retain the exact service-read snapshot. The existing virtual-clock binding
test independently verifies age preservation and strict stale refusal after aging.
Do not merge those scopes into a claim that the new historical branch was executed
in this particular run.

`run.json` contains actual test results and per-scenario freshness projections;
`tests.log` is the actual unittest log. `changes.diff` compares only the scoped
semantic change against the sealed capture-instrumented source. The source snapshot
and input pins preserve the runtime, schemas, original fixture provenance/binary,
observer helper and tests used. Existing capture hooks and ordinary CLI error
assertions remain; raw process execution was factored only to let this one strict
observation classify its exact stale response.

This is targeted evidence. It does not replace a subsequent complete-suite result
or attribute the earlier unretained focused failure to a measured exact age.
