# Complete retained-group outcomes; fresh acceptance remains incomplete

**108 distinct methods pass:** 107 selected pure checks on source04 plus one
complete retained-history/adversary method. The latter checks all 30 source01
GPIO cases against separately retained pre-run setup, including every 25 fixed
challenge and nominal completion with replay/conflict. It rejects false aggregate
accounting, unreported archive files, a forged nominal report and changed trusted
authority. File, SQL and clock calls are forbidden during inspection.

| Attempt | Status | Test seconds | Raw bytes |
|---|---|---:|---:|
| [attempt01-passed105](attempt01-passed105/README.md) | passed | 25.948 | 738 |
| [attempt02-failed-gpio-history](attempt02-failed-gpio-history/README.md) | failed | 60.968 | 15,105,182 |
| [attempt03-launcher-refused](attempt03-launcher-refused/README.md) | refused_before_start | — | 0 |
| [attempt04-passed106](attempt04-passed106/README.md) | passed | 50.654 | 738 |
| [attempt05-failed-gpio-deadline](attempt05-failed-gpio-deadline/README.md) | failed | 63.113 | 9,044,965 |
| [attempt06-failed-pwm-deadline](attempt06-failed-pwm-deadline/README.md) | failed | 61.732 | 11,629,153 |
| [attempt07-failed-retained-history](attempt07-failed-retained-history/README.md) | failed | 34.497 | 0 |
| [attempt08-passed107](attempt08-passed107/README.md) | passed | 43.154 | 738 |
| [attempt09-passed-retained-history](attempt09-passed-retained-history/README.md) | passed | 70.718 | 227,905 |
| [attempt10-failed-current-gpio-deadline](attempt10-failed-current-gpio-deadline/README.md) | failed | 61.88 | 11,400,239 |

Source01 captured all 30 GPIO cases but its wrapper failed on unavailable current
binding resolution after authority loss. Source02 corrects that exact boundary;
its fresh GPIO/PWM groups stop after 20/24 cases at the unchanged 60s deadline.
Source03 reuses the complete immutable source01 archive and exposes the distinct
four-actor resource environment shape. Source04 handles all four original/current
actor identities explicitly, while the existing semantic checker proves each
complete environment. Both wrapper failures and the source-selector pre-start
refusal remain retained. No old failure is relabeled or replaced.

The fresh source04 GPIO attempt also stops at the unchanged 60s capture deadline,
after 24 completed cases. The active permission-pending case retains a failed
child, canceled receipt and still-running parent, with no claims or owners.
Those endpoint observations do not establish complete settlement. Independent
inspection is unreached. The prepared source04 PWM harness14 remains unexecuted
after this GPIO gate fails. Source04 has no accepted fresh full group.

The passing historical inspection verifies 28 operations, 99 ticks, 3,832 worker
records, 10,149,988 producer bytes and 14,660,708 derived bytes. Its 30 inspection
documents total 216,187 bytes; the summary is an additional bounded record.
The complete test emits 32 files / 227,905 bytes and makes zero SQL connections.
The 70.718-second method includes the success and all four adversarial inspections;
it is not a single-pass benchmark. The 3972 retained subject/setup files and all
production files inherited into source03 remain unchanged; source04 changes only
the resource environment branch and its tests/metadata.

The reader matches trusted input identities and recomputes exact archive closure,
state layout, operation/tick/record/byte counters and expected outcomes. Its
historical matrix/outcome flags are true. Run/configuration/implementation
attestation, wall-time attestation, hard aggregate storage, physical measurement
and qualification remain false. The acquisition proof itself makes no semantic
claim; the separate inspection outputs carry the bounded historical conclusion.

[Design](../DESIGN.md), [corrections](../CORRECTION.md), [analysis](../GROUP-ANALYSIS.json),
[source04 review](../implementation04/source-review.json),
[inspection summary](attempt09-passed-retained-history/attempt/scratch/test_complete_retained_gpio_and_archive_adversaries/summary.json).
Primary-agent review only; existing helpers remain usage-limited. Live HMS and
the adjacent Harness are unchanged. No physical/MCU, inference or external
controller execution. Current qualification, public tools, learning, persistent
applications and real device/intelligence-hub providers remain required.
