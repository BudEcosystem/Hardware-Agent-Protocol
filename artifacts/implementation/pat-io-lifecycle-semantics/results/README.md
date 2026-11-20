# Complete lifecycle histories: 58 tests pass

The [corrected test selection](attempt02-passed58/README.md) passes all 58 methods
in 76.03 test seconds. The production checker is unchanged from
[failed57](attempt01-failed57/README.md), which had 50 passes and 7 errors in
adversarial fixture construction. All 20 real-history positives passed there.
The [diagnosis](../DIAGNOSIS.json) and [test-only correction](../test-only-correction.patch)
retain the exact causes and change. No checker rule, limit or unsupported-case
refusal was weakened.

All twenty fixed GPIO/PWM histories now pass complete independent expected-response
checks: accepted/pending cancellation and reopen, lost activation/completion replies,
and invocation withdrawal before parent admission, before dispatch, while pending
and after committed completion. The composition checks trusted fault/authority
plans, exact artifacts and requests, current configuration decisions, all receipt,
effect, owner/fence, operation and parent events, samples, returned replies and
final settlement. All 292 paired checkpoints and 720 produced samples are checked.

The fault plan is a separate closed input. Every unknown event must occur at its
exact fault cut or pending-owner reopen. A lost activation retains claims until
reconciliation stops the pending effect. A lost completion preserves the completed
receipt and claims until its historical result settles. Reopen cannot rewrite a
completed receipt or rebind the original request. Accepted cancellation/reopen has
no board handoff, while pending cancellation restores modeled idle before release.

There are eighteen admitted children, twelve activations, four completed cycles
and eight canceled activations across the twenty separate histories. All end with
no unresolved operations or held claims. Completing a first child does not satisfy
a canceled two-step PAT; only the single-step post-completion permission challenge
satisfies its whole completion objective. Correct fault handling is kept separate
from PAT completion.

Adversaries cover undeclared/wrong fault plans, false unknown causes, early claim
release, missing floors/owners/receipts, changed historical owner/completion/stop
causes, hidden effects, sample clocks/values, bindings/admission revisions,
replacement sessions, aliased suffix children and false returned parent status.
Seven corrected adversaries now pass the original partial exact transcript check
before the full semantic checker rejects them. A new six-case no-op check confirms
the test-only checkpoint rewriter preserves original bytes. Existing generic
readers retain unsupported pending-recovery and active-withdrawal refusals; AST
and I/O/clock purity checks pass.

Both attempts preserve 7,755 project inputs, 7,758 frozen entries, six active harness
inputs and 159 external pins, all actual origins and compiler/driver identities.
Those two implementation identities also match across attempts. Every SQL,
network and subprocess operation is prohibited; original 180-second, 16 MiB and
8,192-file limits remain. The source closure explicitly excludes 3,013 old fixture
files and adds 2,665 lifecycle fixture files; original sealed evidence is unchanged.
Complete attempts and original empty scratch roots are acquired. Review is by the
primary agent because existing delegated reviewers remain usage-limited. Live HMS
and the adjacent Harness remain untouched.

All 25 named fixed challenges now have staged capture and independent
outcome components. This does not establish a current candidate's exact combined
matrix, current implementation/configuration attestation, actual aggregate quotas,
public qualification or automatic promotion. Those remain next, followed by the
unfinished persistent prompt applications, PAT learning, physical drivers and
intelligence-hub lifecycle/compute controls.
