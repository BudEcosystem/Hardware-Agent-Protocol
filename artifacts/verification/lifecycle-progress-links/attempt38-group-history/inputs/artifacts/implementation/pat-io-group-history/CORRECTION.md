# Preserve unavailable current bindings after authority loss

Source01 passes 105 pure checks. Its fresh GPIO group completes all original
capture assertions, then independent inspection fails while reading the reopen
record for full authority withdrawal. The original environment remains recorded,
but current binding resolution is explicitly unavailable and `workerEnvironment`
is null. Binding-pending recovery has the same intended representation. The
group wrapper incorrectly indexed both as resolved environments.

Source02 always verifies the original compiler identity. It accepts an absent
current environment only in those two exact authority scenarios, on reopen,
with the original explicit unavailable marker. The complete existing authority
semantic checker must still independently establish the withdrawal/inactive
binding cause. Every resolved current environment must match the trusted compiler.
Other absence, changed identity, wrong marker and initial creation refuse.

The source01 attempt and all 30 captured cases remain unchanged. One focused
pure method covers the added branch and invalid contexts. No runtime behavior,
case, guard, filesystem/effect limit or deadline changes. Both fresh full-history
groups remain required for source02 acceptance.

The first source02 launcher retained the source01 directory selector despite
pinning source02's hash/prefix. It refused before creating a child or scratch.
Fresh harnesses correct that selector only; the pre-start refusal remains.
Source02 passes 106 pure methods, but its fresh GPIO/PWM captures stop at the
unchanged deadline after 20/24 completed cases. They do not reach inspection.

Source03 adds the exact complete source01 capture and its separately retained
pre-run setup as immutable input. Production matches source02. Pure inspection
then reaches the resource case and exposes another wrapper assumption: that
case records original/current environments as four actor maps, not one single
environment. No inspection success is emitted from that failed attempt.

Source04 requires exact GPIO/PWM/alias/independent maps in both environment sets,
initial creation and matching compiler identity for every actor. The existing
resource inspector still verifies each complete actor environment. A new pure
method tests each actor for omission, null, missing/changed compiler, extra
actors and forbidden reopen. The retained test identifies this evaluator version.
All fixture bytes and prior failures remain. Retrospective inspection cannot
replace fresh current-candidate execution or establish deployment attestation.

Source04 passes 107 selected pure methods and the complete retained inspection
with four archive/setup adversaries. Its fresh GPIO run then reaches only 24 of
30 cases before the unchanged capture deadline. The active permission-pending
case has a failed child and canceled receipt, but its parent remains running.
There are no endpoint claims or owners; that does not prove complete settlement.
All raw state remains unchanged. The source04 PWM harness14 is prepared but
unexecuted after this gating failure. No cause of the wall-time variation has
been established, and no deadline or resource limit has been widened.
