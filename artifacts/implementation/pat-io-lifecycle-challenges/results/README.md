# Fixed lifecycle captures: 21 methods pass

The [frozen worker and reader](../implementation01/README.md) pass all 21 distinct
methods in four disjoint bounded selections. Twenty actual trials cover ten fixed
cases on both GPIO and PWM. The additional method verifies two refusals before
runtime construction. No failed test run or project source correction occurred in this stage.
See the [design](../DESIGN.md) and [read-only JSON audit](data-audit.json).
A [retained ordering error](../AUDIT-ORDERING.json) records a read-only audit
started before the fourth acquisition had finished writing its proof. It emitted
no audit output; the unchanged audit passed after acquisition completed.

| Selection | Methods | Test seconds | Elapsed seconds |
|---|---:|---:|---:|
| [GPIO cancellation, restart and completion loss](attempt01-passed6/README.md) | 6 | 69.348 | 85.964 |
| [PWM cancellation, restart and completion loss](attempt02-passed5/README.md) | 5 | 46.864 | 59.616 |
| [GPIO pending loss and retained-read withdrawal](attempt03-passed5/README.md) | 5 | 42.708 | 55.924 |
| [PWM pending loss and retained-read withdrawal](attempt04-passed5/README.md) | 5 | 29.556 | 38.929 |

Accepted cancellation/restart has no modeled activation and retains the resource
floor. Pending cancellation restores modeled idle before claim release. New-owner
recovery preserves original requests and sessions in historical receipts; stale
resume and an unstarted suffix refuse instead of being rebound. A lost completion
reply retains a completed first effect, while a lost activation reply keeps the
unknown operation's claims until reconciliation stops the pending effect.

Invocation withdrawal before parent admission creates no parent, child or claim.
Withdrawal before dispatch prevents a handoff. Withdrawal while pending records
an authority-loss stop; withdrawal after committed completion reconciles the
historical success. Explicit read access is retained and invocation is never
restored. Only the single-step after-completion permission case satisfies its
whole completion objective; correct cancellation or a completed prefix does not
satisfy a two-step PAT.

The pure reader independently reconstructs exact fixed artifacts/cases, immutable
lowering, actual resolved environments, call/clock/reopen/failure schedules and
trusted grant snapshots. Thirty coherent/rehash attacks are refused and ten
I/O/clock purity checks pass. Targeted runtime assertions inspect actual receipts,
effects, unknown states, claims, final state and absent suffix work. The reader
explicitly does not yet compose full independent semantic/outcome histories.

Across the twenty captures there are 1866 execution records, 758
configuration records, 292 paired checkpoints and 64 scheduler ticks.
Eighteen children produce twelve activations, four completed cycles and eight
canceled activations. Six injected losses are retained. All final captures have
zero unresolved operations or held claims. These totals describe separate fresh
trials, not one admitted candidate group or aggregate storage/time compliance.

All 8,101 project inputs, 8,104 frozen entries, six active harness inputs and 159
external pins remain stable in each run; every actual import origin and both
compiler/driver identities match. Original runtime, provider, compiler, matrix,
transcript and inherited tests are unchanged. Only exact private synthetic state
SQL paths are allowed. Complete attempts and original scratch trees are acquired;
no network, subprocess, physical/MCU, inference or live-service work ran in the
children. All original bounds remain. Review is by the primary agent; helpers
remain usage-limited. Live HMS and the adjacent Harness are untouched.

Complete independent fixed-case outcome composition, current candidate matrix
execution, attestation, aggregate quotas and public qualification remain pending.
Persistent prompt applications, automatic PAT learning/promotion and actual
device, driver and intelligence-hub control remain part of the unfinished goal.
