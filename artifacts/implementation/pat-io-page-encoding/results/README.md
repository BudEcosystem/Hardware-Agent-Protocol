# Exact page encoding passes; current capture still misses its deadline

**118 distinct methods pass:** all 107 prior pure checks plus ten new encoding
checks, followed by the actual record-cutoff test. The cutoff retains exactly
977,425 raw bytes, matching the previous encoding stage. Exact page bytes/digests,
typed keys, caller mutation, profile/metadata changes, eviction, both streams,
budget precedence and failed-write retention pass. Closed fake-query fixtures
also verify that warm pages still reread SQL shape/count/size/type/rows and
revalidate blob documents. The actual group runs use private SQLite states.

| Attempt | Status | Test seconds | Raw bytes |
|---|---|---:|---:|
| [attempt01-passed117](attempt01-passed117/README.md) | passed | 80.577 | 2,528 |
| [attempt02-passed-cutoff](attempt02-passed-cutoff/README.md) | passed | 11.309 | 977,425 |
| [attempt03-failed-gpio-history](attempt03-failed-gpio-history/README.md) | failed | 63.086 | 10,905,540 |
| [attempt04-profiled-gpio-failure](attempt04-profiled-gpio-failure/README.md) | failed | 68.216 | 4,737,778 |

The uninstrumented GPIO attempt stops after 23 of 30 cases at the original 60s
capture deadline. Its active permission-before-dispatch case has a rejected child,
failed parent and no receipt/effect/claim/owner. The instrumented run stops after
11 cases; its active not-before-boundary case retains an accepted child, running
parent and one claim, with no receipt or activation. That unresolved state remains
unchanged. Neither attempt reaches independent inspection. PWM harness04 remains
unexecuted after the GPIO gate fails.

The profile reports 16,976 canonical calls with 31.450 cumulative seconds, and
substantial overlapping runtime setup, installation/topology and cell-validation
work. Whole-method process CPU/wall totals are 55.803/68.217 seconds, including
pre-run setup and instrumentation. These are not benchmarks; cumulative times
cannot be added, and no exact cause of run-to-run variation is established.

The source contains all 225 inherited current-worker inputs, with two new files
and two modified writer modules. Historical fixture data and its dedicated test
are explicitly excluded from this worker closure; original inputs remain pinned
and untouched. The memo holds at most 128 exact pages / 1MiB of encoded bytes.
Every SQL capture/validation method, reservation and durable storage body remains
unchanged. All four attempts preserve 227 project/230 frozen inputs, six active
harness files, 159 external pins, actual origins and within-run identities.

[Design](../DESIGN.md), [source review](../implementation01/source-review.json),
[unchanged method proof](../source-invariant-review.json), [group analysis](../GROUP-ANALYSIS.json),
[profile analysis](../PROFILE-ANALYSIS.json).
Primary-agent review only; helpers remain usage-limited. Live HMS, adjacent
Harness, physical devices/MCUs, inference and external controllers are untouched.
Fresh complete capture/inspection, trusted process/run association, hard aggregate
storage, public qualification, persistent applications, learning and real
device/driver/intelligence-hub providers remain required.
