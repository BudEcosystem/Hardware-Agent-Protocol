# Local observation freshness and effect timing

The failed 424-test run exposed live transport refusals. Follow-up deterministic
tests also established a local simulator defect: a clock sampled before a blocking
authority commit could be reused afterward, allowing a synthetic effect past its
maximum run time, completion deadline or shorter policy lease. The original
[four-case proof](../artifacts/verification/local-freshness-before/index.json)
and [six-case extension](../artifacts/verification/local-freshness-before/extended/index.json)
retain the failures before correction.

The local adapter now acquires observations again near dispatch and pending
effect checks when the previous sample is due for refresh. This is new acquisition,
not a timestamp change; publication latency still contributes to observation age.
A snapshot that is already too old when published remains a refusal.

`Journal.authority_time()` continues to establish the durable clock floor. Its
returned sample precedes its storage commits, so it cannot establish time after
those commits finish. The new `effect_veto_time(checkpoint)` supplies a bounded,
noncommitting check after that barrier. It may only withdraw already admitted
authority; it cannot authorize admission, renew a lease or supply an event time.
Invalid and regressed clocks refuse. The observed floor is retained during the
ensuing refusal or settlement.

The runtime also supplies a private veto to `SimulatedPlant.finish`. It runs after
the plant lock, transaction start and reads, immediately before the device-state
update. It repeats current authority, procedure/precondition and timing checks,
including a final wall/monotonic sample after policy checks. A callback exception
rolls back the plant transaction and leaves the pending operation and claims
available for reconciliation; it does not produce an effect.

The [eleven-case corrected proof](../artifacts/verification/local-freshness-after/index.json)
covers blocking authority and plant transactions, freshness, run/deadline/lease
expiry, clock faults, audit floor retention, negative readiness and callback
rollback. Eighty earlier local runtime, simulator and procedure tests also passed
in the focused compatibility run. The complete regression result is recorded
separately in [progress](../PROGRESS.md).

The subsequent [start-boundary probe](../artifacts/verification/local-start-boundary-probe/index.json)
showed that a claim commit or plant transaction could also delay registration
beyond the original latest-start deadline. The adapter now repeats current
authority and timing checks inside `SimulatedPlant.begin`, after those waits and
before pending registration or a plant fence change. A refusal creates an explicit
durable `startExcluded` receipt. Journal settlement records `rejected_before_start`,
clears `mayHaveActed` and releases claims in the same transaction. Exact replay and
restart retain that operation identity. A generic canceled receipt cannot establish
that execution never started.

The [22-test start/freshness proof](../artifacts/verification/local-start-boundary-after/index.json)
also retains a five-case probe: late claim, late plant transaction and invalid or
regressed clocks produce zero effects; the control starts in time and completes.
The final storage commit remains outside any hard real-time guarantee.

An additional [23-test proof](../artifacts/verification/local-start-atomic-exclusion/index.json)
kills the host immediately after the no-start journal commit, before settlement
continues. Direct inspection before recovery confirms the terminal record, cleared
effect uncertainty and zero claims. Reopen and replay preserve that result. This
disproves a review concern about claim release needing a later cleanup pass; no
production change was needed for that concern.

An unadmitted procedure child now distinguishes a known expired observation age
from invalid evidence. Only valid observations with known age beyond the required
limit receive the trusted internal `ObservationAgeExpired` marker. The public
error code remains `OBSERVATION_STALE`. The procedure can wait for a new sample
using its original reserved key and original deadlines. Unknown clocks/age,
invalid quality, mismatched evidence and false predicates do not receive that
deferral. Five focused tests check this boundary and single admission after fresh
adapter ingress.

These changes do not explain every captured live refusal. The first failed run
did not retain the event payloads identifying two dispatch rejection causes;
their status records alone are insufficient to assign a cause. Expanded
[failure capture](../artifacts/verification/runtime-424-diagnosis/README.md)
now retains database snapshots, event payloads and process diagnostics. Nor does this establish a physical
or hard real-time bound across the final state update/storage commit. Crash
recovery still depends on the durable operation identity and plant receipt, not
on assuming that every supplementary clock sample was persisted before effect.
