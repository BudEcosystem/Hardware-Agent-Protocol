# Installation normalization reuse: 194 of 194 methods pass

The fresh uninstrumented PWM and archive-commit nominal tests both pass. Historical failed attempts, incomplete states and transaction sidecars remain unchanged. No old logical key was retried. Each current scope ran once on a fresh fixture. These are regression results, not repeated reliability measurements or a controlled benchmark.

Only the pure installation normalizer changes in production. The original semantic body remains AST-identical. Every call still bounds the original input, rejects unsupported types and floats, detaches it, checks its closed profile and recomputes current driver source identity. Eight exact canonical byte keys retain at most 512 KiB plus bounded immutable normalized trees; results are detached. Selected helper/validator/configuration changes disable reuse. The 14 new tests establish these specific boundaries, including concurrent callers and changes during validation. No authority, current permissions, binding/generation/session, clock, effect or receipt is cached. See the [design](../DESIGN.md) for trusted-process and private-validator limits.

| Attempt | Result | Test seconds | Raw files / bytes |
|---|---|---:|---:|
| [attempt01-passed-control185](attempt01-passed-control185/README.md) | 185 pass / 0 fail | 59.857 | 608 / 8046701 |
| [attempt02-passed-pwm](attempt02-passed-pwm/README.md) | 1 pass / 0 fail | 69.839 | 4269 / 19559645 |
| [attempt03-passed-crash-archived](attempt03-passed-crash-archived/README.md) | 1 pass / 0 fail | 67.455 | 4283 / 19616938 |
| [attempt04-passed-cutoff](attempt04-passed-cutoff/README.md) | 1 pass / 0 fail | 17.054 | 818 / 6441370 |
| [attempt05-passed-pidfd](attempt05-passed-pidfd/README.md) | 1 pass / 0 fail | 5.497 | 299 / 4482699 |
| [attempt06-passed-deadline](attempt06-passed-deadline/README.md) | 1 pass / 0 fail | 7.586 | 301 / 4482669 |
| [attempt07-passed-crash-admitted](attempt07-passed-crash-admitted/README.md) | 1 pass / 0 fail | 5.306 | 47 / 556416 |
| [attempt08-passed-crash-launching](attempt08-passed-crash-launching/README.md) | 1 pass / 0 fail | 7.130 | 343 / 4997583 |
| [attempt09-passed-crash-settled](attempt09-passed-crash-settled/README.md) | 1 pass / 0 fail | 68.076 | 4283 / 19616521 |
| [attempt10-passed-crash-spawned](attempt10-passed-crash-spawned/README.md) | 1 pass / 0 fail | 77.978 | 4281 / 19616388 |

The unchanged 171 control selection plus 14 new pure tests passes 185 checks. Independent read-only inspection confirms eleven corrupt control records and three malformed replies remain intact, and three unknown lease fixtures remain unresolved. SQL allowances remain restricted to 28 original control ledger opens; new normalization tests open no SQL or worker.

The same nine process selections exercise PWM, archive commit, lowered record cutoff, pidfd failure, lowered deadline and hard owner loss at admission, launch intent, producer settlement and spawn. Original deadlines and effect/storage bounds remain unchanged. Complete group outputs are checked by the independent reader. Transport of a failed group does not qualify a PAT; recovery without trustworthy original exit information retains unknown status. See each process/state audit for its exact observed counts.

All 240 project / 243 frozen inputs, six active harness inputs and 159 external pins remain stable in each attempt. Original owner and writer leases are held during collection. Database audits do not recover sidecars. Cooperative audit hooks and byte accounting do not provide OS isolation or enforced aggregate storage. The public runtime and adjacent Harness checkout remain unchanged. No physical device, MCU/emulator, live inference or service was executed.

The full HMS goal remains active. [Next work](../NEXT.md) includes trusted service configuration, enforced storage, public qualification and lifecycle mounting, PAT synthesis/learning, persistent Arduino applications and actual device/driver/hub providers.
