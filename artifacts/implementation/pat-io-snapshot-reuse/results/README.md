# Complete current GPIO and PWM histories independently checked

**132 distinct methods pass:** 129 pure checks, the actual record-cutoff test,
and both complete current GPIO/PWM history pipelines. Each full pipeline checks
one constant, single-step candidate, its negative cases and all 25 fixed
challenges (30 total cases). This is two representative finite synthetic
candidates, not arbitrary applications or physical qualification.

| Attempt | Status | Test seconds | Raw bytes |
|---|---|---:|---:|
| [attempt01-failed129](attempt01-failed129/README.md) | failed | 36.531 | 2,528 |
| [attempt02-passed129](attempt02-passed129/README.md) | passed | 37.369 | 2,528 |
| [attempt03-passed-cutoff](attempt03-passed-cutoff/README.md) | passed | 4.640 | 977,425 |
| [attempt04-passed-gpio-history](attempt04-passed-gpio-history/README.md) | passed | 65.224 | 15,333,173 |
| [attempt05-passed-pwm-history](attempt05-passed-pwm-history/README.md) | passed | 65.659 | 15,575,194 |

The first pure run retains 128 passes and one new test expectation failure.
Source02 changes only that assertion to require containment, dependency and alias
graph checks. Production matches source01. The corrected 129-method run passes,
including the subsequent repeated-cycle refusals. Original failures, scratch
and complete copies remain immutable.

The full test durations include setup, capture, independent inspection and three
early forged-archive refusals. The original 60s capture checks and 180s harness
deadline remain; these observations are not benchmarks or independent wall-time
attestation. No required case, effect, record, file or byte ceiling is widened.

| Verified group | GPIO | PWM |
|---|---:|---:|
| Cases / fixed challenges | 30 / 25 | 30 / 25 |
| Actual operations / reserved admissions | 28 / 44 | 28 / 44 |
| Ticks / charged worker records | 99 / 3,832 | 99 / 3,832 |
| Producer bytes | 10,149,988 | 10,289,708 |
| Retained state bytes | 4,510,720 | 4,585,472 |
| Derived bytes | 14,660,708 | 14,875,180 |
| Case-inspection bytes (30 documents) | 216,187 | 217,881 |
| Complete inspection output (32 files) | 227,991 | 229,685 |

Each full run retains 26 states / 52 databases. Closed read-only audits find
21 activations, 11 completions, 10 cancellations and no claims or owners; integrity
checks and hashes pass. These endpoint audits supplement the separate complete
history checks. The actual record-cutoff test retains the same 977,425 raw bytes
as before and stops the group at its original lowered record budget.

Independent readers run with file/SQL/clock access forbidden and dispatch exactly
8 timing, 3 clock, 10 lifecycle, 3 authority and 1 shared-resource checks. Separate
pre-run setup is preserved. Every case response, nominal completion, negative
outcome, archive file and operation/tick/record/byte association is checked.
The reader's matrix, outcome, accounting, trusted-setup and identity-match flags
are true. The acquisition proof itself makes no semantic claim.

Configuration/implementation/run/wall attestation, hard aggregate storage,
physical measurement and qualification flags remain false. The next required
work is trusted process/run association, actual aggregate enforcement and
supervised public qualification. Persistent applications, prompt learning and
real device/driver/intelligence-hub providers remain required by the full goal.

[Design](../DESIGN.md), [test correction](../CORRECTION.md),
[source01 review](../implementation01/source-review.json), [source02 review](../implementation02/source-review.json),
[unchanged semantic methods](../source-invariant-review.json), [analysis](../GROUP-ANALYSIS.json),
[GPIO inspection](attempt04-passed-gpio-history/attempt/scratch/test_complete_gpio_history/inspection/summary.json),
[PWM inspection](attempt05-passed-pwm-history/attempt/scratch/test_complete_pwm_history/inspection/summary.json).

All attempts preserve 228 project/231 frozen inputs, six active harness inputs,
159 external pins, actual origins and within-run identities. Review is by the
primary agent; helpers remain usage-limited. Live HMS, adjacent Harness,
physical devices/MCUs, inference and external controllers remain untouched.
