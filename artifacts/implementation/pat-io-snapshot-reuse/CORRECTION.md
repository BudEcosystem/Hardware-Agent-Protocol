# Require containment, dependency and alias graph checks

The initial 129-method pure run has 128 passes and one assertion failure. The
new warm-snapshot test expects two graph checks, but the unchanged alias-closure
function invokes the third graph check. Source contains exactly the containment,
dependency and alias DAG call sites. The snapshot result and parser-veto assertions
pass before the count fails; the later repeated-cycle assertions are unreached.

Source02 changes only that assertion to require the exact ordered three refusal
codes. Every production file and all other project/test bytes remain unchanged.
The failed run, original scratch and complete copy stay retained. This correction
does not change the parser, cache, graph semantics, budget or acceptance criteria.
Fresh selection and complete capture checks are still required.

The corrected source subsequently passes all 129 selected pure methods, the
actual record-cutoff method and both complete fresh GPIO/PWM history pipelines.
Every full pipeline captures and independently checks all 30 cases, including
all 25 fixed challenges. See the [retained results](results/README.md); the original
failure remains failed, and no production code changed in the correction.
