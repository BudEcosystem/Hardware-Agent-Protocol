# Shared-resource capture: 72 tests pass

The [frozen candidate](../../implementation01/README.md) passes all 72 selected
methods in 112.181 test seconds and 129.006 elapsed seconds. The selection contains
three new resource methods, 30 revised matrix methods and 39 unchanged transcript
methods. See the [acquisition proof](proof.json), [raw-data audit](data-audit.json),
[test log](attempt/output.log) and [bounded harness](../../harness01/README.md).

Two instances of the same fixed shared-board challenge, associated with GPIO and
PWM candidate matrices, each complete four original operations. GPIO excludes PWM
and its cross-route alias; an independent pad progresses concurrently. Subsequent
alias and PWM actions reuse their originally refused request bytes. A separately
declared GPIO probe reaches RESOURCE_BUSY after four real admissions. Historical
GPIO completion remains readable while the alias actively owns the shared pad.
Exact replays add no effects, final claims are empty, and shared fences advance
through GPIO, alias and PWM without separate route-local ownership histories.

Matrix version 0.2 reserves five possible admissions for this challenge, including
the expected-refused probe. The unchanged global ceiling remains 512. Constant
and 16-step candidates reserve 43 and 58 operations respectively; expected actual
challenge completions remain four. The original 37-case parameterized example
still refuses the 32-case limit. See the [design](../../DESIGN.md).

The new explicit transcript 0.4 records four resolver registrations and all five
requests before effects. A pure checker independently derives the actor requests,
resolver identity, exact schedule and nine unchanged-state phases. Nine rehashed
attacks, old-profile refusal, three pre-runtime refusals and read-only purity
checks pass. Targeted assertions inspect concurrency, historical idle, effects,
final settlement and fences; complete independent multi-actor event/effect folds
remain unfinished. All qualification and full-matrix success flags remain false.

The two captures retain 438 execution records, 142 configuration records, 88
paired checkpoints, 14 scheduler ticks and eight completed activations. All 8,025
project inputs, 8,028 frozen entries, six active harness inputs and 159 external
pins remain stable. Compiler/driver identities match; 731 actual-origin records
have no violations. Four connections use only the two exact private trial states.
The complete 8,654-file attempt and original scratch (595 files, 3,214,434 bytes)
are retained. Original 180-second/16 MiB limits are unchanged. Review was by the
primary agent; helpers remain usage-limited. No live integration, physical/MCU
execution, hub service control, prompt learning or promotion is established.
