# I/O supervision recovery: 178 of 180 distinct methods pass

All 237 inherited files, including the five production supervisor modules,
remain unchanged. Two original test files add 20 explicit methods. The control
scope passes 171 checks: the original 160 and eleven I/O-specific admission,
concurrency, retention, corruption, lease, malformed-return, deadline-edge and
input-detachment checks. No control subprocess runs. Independent read-only audits
confirm eleven corrupt rows remain corrupted and three malformed returns retain
their exact bytes; no fixture was repaired. Its 28 parent ledger opens cover
26 private databases. The raw control tree is 8,038,589 bytes under 16 MiB.

| Attempt | Result | Test seconds | Raw files / bytes |
|---|---|---:|---:|
| [attempt02-passed171](attempt02-passed171/README.md) | 171 pass / 0 fail | 86.669 | 608 / 8038589 |
| [attempt03-failed-pwm](attempt03-failed-pwm/README.md) | 0 pass / 1 fail | 72.025 | 3769 / 17510341 |
| [attempt04-passed-cutoff](attempt04-passed-cutoff/README.md) | 1 pass / 0 fail | 20.303 | 818 / 6433258 |
| [attempt05-passed-pidfd](attempt05-passed-pidfd/README.md) | 1 pass / 0 fail | 7.549 | 299 / 4474587 |
| [attempt06-passed-deadline](attempt06-passed-deadline/README.md) | 1 pass / 0 fail | 9.097 | 301 / 4474557 |
| [attempt07-passed-crash-admitted](attempt07-passed-crash-admitted/README.md) | 1 pass / 0 fail | 6.999 | 47 / 556412 |
| [attempt08-failed-crash-archived](attempt08-failed-crash-archived/README.md) | 0 pass / 1 fail | 69.100 | 3814 / 17827386 |
| [attempt09-passed-crash-launching](attempt09-passed-crash-launching/README.md) | 1 pass / 0 fail | 8.131 | 343 / 4989467 |
| [attempt10-passed-crash-settled](attempt10-passed-crash-settled/README.md) | 1 pass / 0 fail | 88.434 | 4283 / 19608401 |
| [attempt11-passed-crash-spawned](attempt11-passed-crash-spawned/README.md) | 1 pass / 0 fail | 85.220 | 4281 / 19608268 |

The original 500-record cutoff, reduced 1 ms parent deadline and pidfd-acquisition
failure pass their negative tests. The cutoff delivers a complete failed group:
seven completed cases, four retained states, two activations, one completion and
one cancellation. One operation remains accepted with one claim. Transport success
does not make that PAT eligible for promotion, and unresolvedEffects remains null.
The original Popen handle survives pidfd failure and is settled without reconstructing
a signaling target from a stored PID.

Hard owner exit after admission and launch intent recovers without relaunching.
See [RESULTS](../RESULTS.json) and the individual audits for later crash phases.
Every process collection independently holds the actual owner and exact writer
lease through inventory/copy. Parent SQL receipts exclude the separate fixed
crash driver and supervised worker. Reparented zombies do not supply signaling
or success authority. Cooperative audit hooks are not an OS sandbox.

The PWM and archive-commit nominal tests fail the unchanged 60 s supervisor
boundary. PWM retains 29 case directories and 28 manifests, 24 complete state
pairs and an incomplete authority-only state for case 28. There is no group return.
The failed archive-commit run preserves its committed negative archive after owner
loss and retains an interrupted database journal. A separate read-only auditor
hashes that database and journal without opening SQLite or recovering them.
Initial audit assumptions requiring complete state pairs/no journals were refused;
those failures and the corrected audit helpers are retained. No original worker
was rerun, no corrupt state repaired and no timeout/effect/storage ceiling widened.
These attempts do not prove complete supervised PWM or nominal archive-commit
recovery. Their performance cause was not profiled and is not established.

The first outer-launcher invocation hid the approved user distribution directory
with -I and refused before any child, scratch root or SQL work. Its complete
preparation artifact is preserved. The correct historical outer invocation retains
all dependency pins; test children still start with -I -S -B.

Each actual attempt verifies 239 project/242 frozen inputs, six active harness
inputs and 159 external pins. Process acquisition stays within the existing
256 MiB root, 8192 files and 16 MiB single-file limits; normal groups retain 60 s,
32 cases and 20 MiB derived-output bounds. These are not hard aggregate quotas.
Observed zero counts in an absent state tree are not an effect-resolution claim.

Next: profile and address the nominal deadline failures without weakening guards,
then complete the current PWM/archive-commit tests on reviewed fresh code. Preserve
all failed keys and states. Trusted fixed service configuration, actual aggregate
storage, serialized public import, PAT synthesis/learning, persistent Arduino
applications, real device/driver/hub providers and microscope commissioning remain.
The full goal is active and public/physical qualification remains false.
