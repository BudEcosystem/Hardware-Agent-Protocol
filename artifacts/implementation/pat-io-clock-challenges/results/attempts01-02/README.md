# Guard-delay and clock-fault capture results

All **50 distinct selected methods pass across two bounded invocations** on the
[frozen source](../../implementation01/README.md). The 46-method selection runs
seven new methods and 39 unchanged transcript regressions in 89.324 test seconds
and 102.021 elapsed seconds. Four unchanged configured runtime regressions pass
in 79.506 test seconds and 92.644 elapsed seconds. Both keep the original
180-second deadline and 16 MiB scratch ceiling. These are separate verification
runs, not a qualification group or timing benchmark.

Six fresh private trials exercise each of these required cases on GPIO and PWM:

| Case | Captured behavior |
|---|---|
| In-call guard delay | Both clocks advance 99 ms after dispatch reservation; the requested 1 ms cycle would finish at the original 100 ms run limit. A `duration_budget_excluded` receipt proves no start, activation or board fence |
| Wall regression | Wall time regresses by 1 ms while monotonic time stays fixed. Refresh fails without changing any of the 44 captured tables; the pending output and authority claims remain |
| Clock mapping invalidation | Monotonic time regresses by 1 ms. Restoring the source still produces `CLOCK_MAPPING_INVALID` under the same owner; pending output/claims remain unchanged |

All four fault cases reopen the same databases with sources above the retained
floor. Owner epoch 2 and a new session are recorded. The original request,
operation, dispatch link, receipt, replay identity and ownership floors remain.
The modeled board stops the old pending output; the authority first records
`outcome_unknown` with claims held, then reconciles the original receipt and
releases claims. Resume refuses unresolved dependencies; parent cancellation
admits no remaining step. Final totals for the six cases are four activations,
zero completed cycles, four cancellations and 28 scheduler ticks.

The opt-in 0.3 recorder retains wall and monotonic clocks separately, including
the exact in-call control point. Older 0.1/0.2 readers reject it. The pure new
reader checks the closed grammar, named fixed-case identity/program timing,
exact call/control schedule and paired configuration serialization. Ten rehashed
control/case alterations, two pre-runtime refusals and a filesystem/SQL/clock
purity veto pass. The four old runtime regressions cover GPIO, PWM, reopen and
sixteen-step execution with unchanged legacy behavior.

**Full independent clock-outcome checking remains unfinished.** The new reader
does not compose the board/operation/parent/sample semantic folds. Its full-history,
expected-response, independent-outcome and qualification flags stay false.
The [semantic handoff](SEMANTIC-HANDOFF.md) lists the required next changes.
A failed refresh followed by a modeled reopen stop establishes no autonomous
bounded stop or physical clock guarantee.

The [acquisition proof](proof.json) rechecks stable 7,073 project files, 7,076
frozen preparation entries, six active harness files and 159 selected external
pins. All 731/703 actual origins match, 229/215 bytecode reads are refused, and
compiler/driver receipts remain stable. Complete attempts contain 8,084 and 8,700
files. Original raw directories retain their identities and complete copies:
977 files/5,363,993 bytes and 1,593 files/9,461,523 bytes. The [data audit](data-audit.json)
checks all six captures, including unchanged failed phases, retained ownership at
reopen, and final aggregate counts: 116 paired checkpoints, 664 execution records
and 270 configuration records.

Runtime/provider/compiler business logic and all old tests/data remain unchanged.
Review was by the primary agent; helpers remain usage-limited. No physical device,
MCU/emulator, live inference/service or acquired controller ran. Live HMS and the
adjacent Harness remain unchanged. Binding/full-read withdrawal, auxiliary actors,
complete candidate execution, current-source attestation, aggregate enforcement,
public qualification, persistent prompt applications and physical driver/hub
lifecycle and compute control remain required unfinished work.
