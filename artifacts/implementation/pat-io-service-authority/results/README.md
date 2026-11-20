# Durable authority configuration results

**249 of 249 distinct methods pass** on the corrected source: 206 inherited controls, 32 new authority controls and 11 process methods. The first attempt is retained with two failures and 30 errors, all caused by comparing a bounded SQLite row with a dictionary. No service configuration was committed in that failed run. The correction converts optional anchor rows and compares mandatory metadata fields explicitly; all test bytes and execution limits remain unchanged.

The new store explicitly authorizes creation/configuration, retains canonical authority-bound pins and revision/receipt history, resolves exact mutation replay before source or capacity checks, and reconstructs fresh preparation from actual installed resolver descriptors. Controls cover commit rollback/lost replies, same-key concurrency/conflicts, history/reopen, capacity, incomplete/corrupt state and changes during planning. Independent inspection checks 34 control authorities and 25 valid configuration versions. Deliberate corruptions remain present; source authorities have no operations, claims or board effects.

The actual authority-backed group commits configuration, closes/reopens the Runtime, reconstructs from its stored pin and actual descriptors, and retains input associations before the original supervisor starts its worker. Independent checks join the durable record to the run and original registry bindings/sessions. The full group has 30 cases, 26 retained states, 21 activations, 11 completions, 10 cancellations and no remaining claims or owners. The source authority itself has zero effects. Exact supervisor replay before/after reopen adds no worker; changed requests with the same key conflict.

Six full groups pass, including the new authority-backed group, legacy configured group, PWM and three owner-recovery cases. Original negative cutoff, pidfd, deadline and pre-launch owner-loss cases also pass their refusal/recovery expectations. Transport completion never establishes semantic qualification; `unresolvedEffects` remains unknown at the supervisor boundary. Code images contain 258 files, including seven supervisor source files and 157 dependency files. All original deadlines, effect and retention limits remain.

Every attempt verifies 244 project files, 247 frozen inputs, six active harness files and 159 external pins. Original raw trees and complete copies remain retained. Source-free read-only audits do not recover transaction sidecars. Primary-agent review only. One preliminary auditor path-expression failure is retained separately under tooling-failures; it produced no audit report and did not execute project code.

| Attempt | Methods | Result | Seconds |
|---|---:|---|---:|
| [attempt01-authority32](attempt01-failed-authority32/README.md) | 32 | failed | 16.197 |
| [attempt02-authority32](attempt02-passed-authority32/README.md) | 32 | passed | 40.819 |
| [attempt03-control206](attempt03-passed-control206/README.md) | 206 | passed | 80.113 |
| [attempt04-authority-owned](attempt04-passed-authority-owned/README.md) | 1 | passed | 65.849 |
| [attempt05-configured](attempt05-passed-configured/README.md) | 1 | passed | 67.361 |
| [attempt06-pwm](attempt06-passed-pwm/README.md) | 1 | passed | 71.985 |
| [attempt07-crash-archived](attempt07-passed-crash-archived/README.md) | 1 | passed | 78.023 |
| [attempt08-cutoff](attempt08-passed-cutoff/README.md) | 1 | passed | 16.979 |
| [attempt09-pidfd](attempt09-passed-pidfd/README.md) | 1 | passed | 5.332 |
| [attempt10-deadline](attempt10-passed-deadline/README.md) | 1 | passed | 7.228 |
| [attempt11-crash-admitted](attempt11-passed-crash-admitted/README.md) | 1 | passed | 5.476 |
| [attempt12-crash-launching](attempt12-passed-crash-launching/README.md) | 1 | passed | 6.869 |
| [attempt13-crash-settled](attempt13-passed-crash-settled/README.md) | 1 | passed | 67.23 |
| [attempt14-crash-spawned](attempt14-passed-crash-spawned/README.md) | 1 | passed | 68.655 |

This verifies an isolated host library for the finite synthetic I/O policy. It does not mount public qualification tools, import/promote evidence, enforce an aggregate filesystem quota, learn PATs from prompts or control real I/O, drivers or hub compute. Those remain required. See the [design](../DESIGN.md), [exact summary](../RESULTS.json) and [next work](../NEXT.md). The full HMS goal remains active.
