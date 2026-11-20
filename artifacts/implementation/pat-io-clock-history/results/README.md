# Independent clock-history results

The corrected [source03](../implementation03/README.md) passes **201 distinct methods**
across six bounded pure-inspection runs. All 33 new checks pass, including the six
original GPIO/PWM captures and rehashed adversarial histories. The remaining 168
unchanged tests cover board, operation, configuration, observation and authorization
history. No device action or runtime database connection is replayed.

| Selection | Tests | Test seconds | Elapsed seconds | Result |
|---|---:|---:|---:|---|
| Clock semantics | 33 | 43.068 | 55.137 | [Pass](attempt03-passed33/README.md) |
| Board and operation | 73 | 123.283 | 142.750 | [Pass](attempt04-passed73/README.md) |
| Configuration | 48 | 111.379 | 132.094 | [Pass](attempt07-passed48/README.md) |
| Observation A | 14 | 25.444 | 34.207 | [Pass](attempt09-passed14/README.md) |
| Observation B | 13 | 33.470 | 42.836 | [Pass](attempt10-passed13/README.md) |
| Authorization | 20 | 78.120 | 98.861 | [Pass](attempt06-passed20/README.md) |

The first two 33-test runs are retained: [receipt-key shadow](attempt01-failed33/README.md)
and [missing atomic release in the model](attempt02-failed33/README.md). Each had
two errors and one failed assertion. Corrections use fresh source snapshots; all
tests, fixtures, producer, runtime, provider and compiler bytes remain unchanged.

The [combined 75-test timeout](attempt05-timeout75/README.md) and later
[observation 27-test timeout](attempt08-timeout27/README.md) are also retained.
Their incomplete child evidence cannot count as passes. The identical 75 methods
finally run in 48+14+13 selections with the original deadline and every other
bound unchanged.

The composed checker independently derives exact clock/call controls, whole-domain
static timing, PAT correspondence, configuration/authorization, board effects,
operation events/claims, parent state and observation sampling. It verifies:

- Original dispatch at 1,000,000, guard at 1,000,099 and due equality at the reserved
  run limit: no activation or board fence; atomic authority claim release.
- Wall/monotonic faults: all 29 execution and 15 configuration tables remain
  unchanged. Cached samples retain their original timestamps. Restoring the
  monotonic source under the same owner does not clear the failure latch.
- New-owner reopen: retain request, replay keys, floors and claims; stop the
  original-owner receipt; reconcile before releasing claims; refuse resume;
  cancel the parent without admitting its suffix.

Across the six original cases: four activations, zero completed cycles and four
cancellations. All six completion contracts fail as intended, all six expected
fault responses pass, and all are settled/quiescent. They cover 116 paired
checkpoints, 664 execution records and 270 configuration records. A failed clock
refresh leaves output pending until explicit recovery; this proves no autonomous
or physical stopping deadline.

Private timing/cause handoffs are derived from exact context and must be consumed.
Old public profiles/default folds preserve their refusals. Receipt attacks retain
coherent digests and event references; table attacks retain valid serialization
and configuration joins. Pure inspection rejects file/SQL/live-clock use.

Original 180-second/16 MiB scratch/8,192-file and other acquisition limits remain.
All ten attempt directories and original empty raw roots are retained, including
failures. Primary-agent review only: helpers remain usage-limited. Live HMS and
the adjacent Harness were not changed.

Full matrix execution, current source/configuration attestation, aggregate quotas,
public qualification, persistent prompt applications, PAT learning, physical
drivers and intelligence-hub lifecycle/compute management remain incomplete.
The [remaining qualification audit](../../pat-io-outcome-history/NEXT-QUALIFICATION.md)
continues to apply. These histories do not qualify a PAT.
