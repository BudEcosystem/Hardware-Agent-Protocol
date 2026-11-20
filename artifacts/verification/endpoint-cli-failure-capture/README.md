# Endpoint CLI failure capture and unchanged diagnostic

The instrumented, otherwise unchanged endpoint CLI test reproduced the final
`observe --max-age-ms 10000 --evidence-kind simulation` failure: one test,
one assertion failure, 18.026 seconds. The first fan operation had completed,
released its claims, retired its endpoint slot, and returned the identical result
on both exact replays. The retained wire history contains one OP, one recovery
QUERY and one RETIRE. The value is 25 and its original sample tick remains 5698.

The strict observation CLI started at host monotonic 123034678 and returned
`OBSERVATION_STALE` at 123038180, 3502 ms later. The separately retained database
contains a valid observation for the same binding, owner epoch and original
sample: receipt 123038510, acquisition-latency bound 12603, zero clock uncertainty.
That later mapping gives an age of 8771 ms at CLI start and 12273 ms at return.
The threshold crosses during the CLI command. **This retained row was republished
after the response and is not the exact service-read snapshot.** It supports
legitimate age expiry without independently timestamping the service read or
proving the exact age in the earlier unretained focused failure.

`actual-runtime.json`, its log, and `diagnosis.json` retain the result and precise
scope. Its failure manifest and closure retain original request JSON, database,
relay request/reply/pending bytes, process output, timestamps, completion and both
replays. No extra live observation, description or refresh was inserted. The
main test's assertion/request-call AST is unchanged (`assertion-check.json`).

All setup/test failures now capture before process cleanup and temporary-state
deletion. A controlled selfcheck intentionally produced one non-SQL assertion
failure and two setup errors, including partial construction. All three retained
their reports; the cases with evidence preserved scratch SQLite, request JSON,
and original previously recorded raw HELLO bytes, then removed temporary state.
Those intentional selfcheck failures are not product test failures and execute
no native endpoint. Process lifetime was stubbed solely for that selfcheck.

The first isolated actual launch stopped before native/runtime execution because
the inherited source snapshot lacked executable permission on the fixture binary.
That startup error is retained as `actual.json`/`actual.log`. Only the new isolated
copy's execute mode was restored from the same-byte original binary; no earlier
snapshot was changed. `execution-mode-repair.json` records the correction. The
intended actual diagnostic was then run once and is the reproduced failure above.

All 113 copied inputs were checked before/after execution. The runner's output
label handling changed between the startup error and actual diagnostic; runtime
and test input bytes did not. Only `tests/test_endpoint_cli.py` changed in the
repository, adding capture/reporting. No runtime code, TTL, deadline, max age,
sample timestamp or action behavior changed. A later scoped test-semantic change,
if accepted, is separate evidence and must corroborate a strict stale refusal
with a valid, known-age historical observation before classifying age expiry.
