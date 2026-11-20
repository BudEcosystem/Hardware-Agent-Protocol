# Durable logical I/O run results

**276 of 279 distinct methods pass; 3 distinct methods fail.** All 267 control methods pass, including 29 new reservation controls. All selected methods were executed; 17 retained attempts include the extra passive diagnostic. The reserved-worker method failed in both its ordinary and diagnostic attempts at the original 60-second worker deadline. The later configuration/session-change replay portion was not reached. There is no end-to-end reserved-worker acceptance claim.

The store shares the existing Journal authority and atomically retains each logical run's candidate/configuration intent, request, receipt and complete original bundle. Exact replay precedes fresh planning, source, session and capacity checks, while current administrative authorization and retained-state validation remain mandatory. Changed intent under the same key conflicts. Controls cover concurrency, lost replies, rollback, lowered capacity, source/configuration/session drift, detached results and deliberately corrupt history. A reservation is an input commitment, not an execution receipt.

Independent read-only audits join the two failed workers to their original authority records and all 37 retained documents each. The first failure retains 12 synthetic states, seven activations, four completions, three cancellations and one claim; the diagnostic retains 16 states, ten activations, five completions, five cancellations and no claims. Neither has a complete return. Source authorities have zero device effects. No state was reset, repaired or relaunched.

The passive observer recorded 34.68 worker CPU seconds across a 59.118-second sampled interval. System CPU pressure was present, but this does not establish causality or a deployment capacity guarantee. It changed neither scheduling nor deadlines. The separate inherited regression methods exercise the expanded worker image and original recovery expectations; their successes cannot repair either reserved-worker failure.

The inherited owner-loss-after-settlement method also fails. Its original crash receipt records `SUPERVISOR_DEADLINE` before the planned owner exit; reopening archives `OWNER_LOST` with no worker return or known exit code. Eight retained states contain five activations, two completions, three cancellations and one claim. The complete-group and later replay assertions were not reached. The initial generic failure auditor rejected this different archive shape; its log is retained, and a separate read-only audit joins the pre-crash deadline to the recovered archive without changing the source or state.

The owner-loss-after-spawn method returns a canonical failed group with `PAT_IO_GROUP_WALL_LIMIT` at the unchanged 60,000 ms limit. It records 26 completed-case entries of the required 30, 23 retained states, fifteen activations, seven completions, eight cancellations and one claim. Its complete retained output closure is verified, but neither full semantic inspection nor the later replay assertions was reached. The separate failed-return auditor and the generic auditor's initial assertion-failure log are both retained. None of these partial results is promoted.

Every attempt verifies 246 project files, 249 frozen inputs, six active harness files and 159 external pins. Where created, code images contain 259 files, including eight supervisor sources and 157 runtime dependencies. All original limits remain. The source differs from its baseline only by the new run module/test and the supervisor source-list addition; inherited tests are unchanged. Primary-agent review only.

| Attempt | Methods | Result | Test seconds |
|---|---:|---|---:|
| [attempt01-runs15](attempt01-passed-runs15/README.md) | 15 | passed | 112.301 |
| [attempt02-runs14](attempt02-passed-runs14/README.md) | 14 | passed | 142.854 |
| [attempt03-reserved-owned](attempt03-failed-reserved-owned/README.md) | 1 | failed | 83.14 |
| [attempt04-diagnostic-reserved](attempt04-failed-diagnostic-reserved/README.md) | 1 | failed | 77.883 |
| [attempt05-control206](attempt05-passed-control206/README.md) | 206 | passed | 101.313 |
| [attempt06-authority32](attempt06-passed-authority32/README.md) | 32 | passed | 36.161 |
| [attempt07-authority-owned](attempt07-passed-authority-owned/README.md) | 1 | passed | 77.268 |
| [attempt08-configured](attempt08-passed-configured/README.md) | 1 | passed | 64.42 |
| [attempt09-pwm](attempt09-passed-pwm/README.md) | 1 | passed | 77.2 |
| [attempt10-crash-archived](attempt10-passed-crash-archived/README.md) | 1 | passed | 76.719 |
| [attempt11-cutoff](attempt11-passed-cutoff/README.md) | 1 | passed | 18.166 |
| [attempt12-pidfd](attempt12-passed-pidfd/README.md) | 1 | passed | 7.554 |
| [attempt13-deadline](attempt13-passed-deadline/README.md) | 1 | passed | 18.553 |
| [attempt14-crash-admitted](attempt14-passed-crash-admitted/README.md) | 1 | passed | 9.443 |
| [attempt15-crash-launching](attempt15-passed-crash-launching/README.md) | 1 | passed | 11.483 |
| [attempt16-crash-settled](attempt16-failed-crash-settled/README.md) | 1 | failed | 75.149 |
| [attempt17-crash-spawned](attempt17-failed-crash-spawned/README.md) | 1 | failed | 73.279 |

See the [exact summary](../RESULTS.json), [design](../DESIGN.md) and [next work](../NEXT.md). Public mounting, protected compute/storage capacity, durable supervisor-authority handoff, serialized evidence import and configuration-aware promotion remain unfinished. So do prompt learning, persistent Arduino applications and real device/driver/hub providers. The full HMS goal remains active.
