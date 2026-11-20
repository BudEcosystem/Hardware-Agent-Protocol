# Binding and complete permission withdrawal:76 selected tests pass

The [complete attempt](attempt/result.json) passes all 76 methods with zero
failures, errors, skips or expected failures:7 new authority methods,30 matrix
checks and39 unchanged transcript methods. Test time is 141.116 s and total harness
time 157.274 s, within the original 180 s limit. No failed attempt or source correction
occurred in this stage. See [acquisition proof](proof.json), [capture audit](data-audit.json),
[frozen source](../../implementation01/README.md) and [design](../../DESIGN.md).

| Fixed scenario, each on GPIO and PWM | Observed behavior |
|---|---|
| Binding invalidated before dispatch | One admitted child rejects before dispatch; no board handoff or effect; claims release and parent fails |
| Binding invalidated while pending | Reopen stops the historical receipt, retains claims while authority is unknown, then reconciles the child; resume refuses, owner cancels the parent and the predeclared original probe receives BINDING_INACTIVE |
| Every grant removed while pending | Public operation/parent reads, exact parent replay and namespace issuance receive ACCESS_DENIED before and after recovery; historical recovery settles the child with no rescue grant, and owner cancellation withdraws the parent |

The six trials retain 696 execution records and 304 configuration records, with140
paired checkpoints and 18 scheduler ticks. There are six admitted children, four
activations, zero completed cycles and four canceled activations. All finish with
zero unresolved child operations and no held claims or later child admission.
All 16 public probes in the two full-withdrawal trials deny access. Fifteen
rehashed transcript attacks and three pre-runtime plan refusals also pass.

Matrix 0.3 declares a separate original inactive-binding probe before effects;
using a parent-reserved child key would test a different refusal. Its possible
admission raises that case's reservation to 3, and constant/16-step combined totals
to 44/59. The original 512-operation ceiling is unchanged. Across these six fixed
trials 14 possible admissions are reserved; six occur.

Transcript 0.5 explicitly records the actual resolver's PAT_BINDING_NOT_APPLICABLE
response after reopen with a null current environment. The old compiled request
is never rebound. The final internal status is labeled privileged trial
observation; it is not a successful public status read. Original owner cancellation
remains permitted as withdrawal of the owner's parent, without restoring grants.

The pure reader checks exact fixed cases, original lowering, resolver identity,
predeclared probe, schedule, reopen placement and unchanged denial snapshots.
Targeted runtime assertions establish the observations above. Complete independent
binding/authority state-transition semantics remain unfinished; complete-history,
independent-outcome and qualification flags stay false.

All 7668 project inputs,7671 frozen entries and159 external pins remain stable;
compiler/driver identities and all 731 actual origins match. Twenty SQLite opens
are confined to the six private original trial authority/board paths. No network,
subprocess, physical/MCU, inference or live-service execution occurred. Raw scratch
remains at `/tmp/hms-io-authority-challenges-authority76-lnnlsqty`: 1043 files,
5591633 bytes. The complete8745-file attempt is acquired unchanged. All original
storage/file/time ceilings remain. Review was by the primary agent; delegated
reviewers remain usage-limited. Live HMS and the adjacent Harness are untouched.

Current candidate group execution, implementation attestation, enforced aggregate
budgets, public qualification, persistent prompt applications, learning/promotion,
physical device drivers and hub lifecycle/compute control remain unfinished.
