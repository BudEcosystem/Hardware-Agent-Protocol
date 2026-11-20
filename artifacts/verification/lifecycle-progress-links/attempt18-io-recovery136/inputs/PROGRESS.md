# Goal progress — 2026-11-07

Status: **active, incomplete — concrete progress this continuation**. The new
shared-board I/O profile is mounted through the explicit runtime factory and
`hctl` daemon, using the existing 14 CLI/UDS/MCP methods. GPIO pulses and PWM
bursts share durable board ownership across adapter routes; pin aliases cannot
bypass claims. [Operating instructions](docs/io-simulation.md) include an example
configuration generator pinned to the actual source.

**Latest full regression passed:** all 748 tests pass in 761.283 seconds, with
zero failures, errors, skips or expected failures. All 151 inputs and compiler
identity stayed unchanged. The [current receipt](artifacts/verification/local-runtime-current.json)
points to the immutable passing attempt. The earlier 747-test run retains its
746 passes and one error: the first procedure-status read in the new CLI test
hit the original two-second transport deadline. The
[retained diagnosis](artifacts/verification/io-status-read-timeout-diagnosis/diagnosis.json)
shows admitted work progressed during that read; it does not prove parent
completion or the exact cause of the delay. The test-only polling correction
passes all five focused transport tests in 53.855 seconds, within the original
15-second polling and two-second RPC deadlines; mutations remain one-attempt.
The [747-test receipt](artifacts/verification/runtime-attempts/20261107T011441.670375Z-c1003207c4ba/receipt.json)
retains the failed result. The [controlled before/after proof](artifacts/verification/io-status-read-timeout-resolution/proof.json)
retains one expected read-timeout error before the correction and five passing
transport cases afterward, plus an independent source review. The full748 run
also passes both real delayed-RPC recovery cases with identical IDs and unchanged
business/effect rows. Its 174 I/O observer reads succeed with zero BUSY retries.
The 696-test checkpoint remains a separate historical baseline.

The [public I/O integration evidence](artifacts/verification/io-provider-runtime-integration/README.md)
retains all three focused attempts. The first ran 37 tests with 1 failure and
9 errors: provider units passed, but the example used an invalid topology profile
and completed I/O responses hit an incompatible legacy result check. The second
ran 52 tests with 1 failure and 1 error: all 24 provider, 9 runtime/profile,
14 typed-API and 1 existing CLI lifecycle test passed, as did CLI and SIGKILL
transport cases. Both MCP tests incorrectly expected resume to rebind an
immutable child to a new board session. The corrected transport-only run passes
all four cases in 97.067 seconds, with 152 inputs including its runner unchanged.
Production source is identical between the failed52 and passing4 attempts; only
the MCP test expectation changed. No deadlines, leases, output limits or retry
rules were widened.

Each MCP protocol exercises all 14 tools with 32 validated replies in that
focused run. Both session-change refusals preserve parent status, reserved keys,
absent child operation, effects and business counts `[4, 0, 3, 2]` before explicit
cancellation. SIGKILL follows an independently observed pending receipt; reopen
preserves activation, cancels to modeled idle, and exact replay adds no effect.
All 150 read-only observer reads succeed with zero BUSY retries. These observations
do not establish physical timing, autonomous stopping or bounded availability.

Public output now uses `hms.synthetic-io-result/1`, keeping activation, completed
cycle and historical idle state distinct. A canceled pulse retains
`activationCommitted:true` and `mayHaveActed:true`. The original unprofiled API
validation body is unchanged. [Diagnosis](artifacts/verification/io-response-contract-diagnosis/README.md),
[independent correction review](artifacts/verification/io-response-contract-resolution-review/README.md)
and [session-test resolution](artifacts/verification/io-transport-session-resolution/README.md)
retain the source, actual failures and corrections. Startup refuses mixed profiles,
malformed primitives, stale source pins, and missing or identity-mismatched board
stores without replacing effect history.

The separate [fixed-unit compiler stage](artifacts/implementation/pat-fixed-schema-units/results/pure34-01/README.md)
passes 34 pure tests in 2.107 seconds: 20 existing methods and 14 new methods.
All 152 copied project inputs, 336 frozen preparation entries and 159 selected
external file pins remain stable. Explicit numeric unit metadata preserves exact
parameter matching and whole-domain checks without generating companion wire
arguments. No Runtime was constructed and no live source changed. The trusted
I/O resolver and timing policy remain isolated candidates; live integration and
the independent outcome oracle remain unfinished.
The [erratum](artifacts/implementation/pat-fixed-schema-units/supplements/01/ERRATUM.md)
also distinguishes the seven-package test inventory from the compiler's unchanged
five-package identity; the latter still excludes imported optional dependencies.

The [trusted I/O resolver candidate](artifacts/implementation/pat-io-binding-resolver/implementation02/README.md)
now has independently reviewed source and an actual
[29-test attempt](artifacts/implementation/pat-io-binding-resolver/results/resolver29-01/index.json):
28 pass and one fails in 68.647 test seconds. It joins the
complete installed GPIO/PWM inventory, explicit unit metadata, permissions and
retained binding/session evidence within an existing Journal transaction.
The failed purity method reads its own program fixture under its filesystem
veto before invoking the resolver; guarded selection and its later purity
assertions are unreached. No resolver production defect follows from that
traceback. The two-line test-only correction is followed by a
[passing focused purity check](artifacts/implementation/pat-io-binding-resolver/results/focused-purity-01/README.md)
in 3.800 test seconds. The actual resolver returns three assignments under the
unchanged SQL authorizer and file/clock/provider vetoes; transaction, change
counter, denied-operation and business-state assertions all pass. These transient
values were asserted in-process, not serialized as independent raw SQL traces.
The [independent result review](artifacts/verification/pat-io-binding-resolver-review/results-focused-one/review.json)
verifies the one-method result and retained bytes. The other 28 methods remain
historical passes from failed29, with no single clean29 rerun.
All 155 copied project inputs, 163 frozen preparation entries, six harness inputs,
159 external pins and compiler/provider identities remain unchanged. All 33
states and 66 database backups were captured (132 files); the original private
scratch root remains retained and empty. The focused follow-up preserves its
155 copied/162 preparation/six harness/159 external inputs, equal compiler and
driver identities, one state/two databases and original empty scratch root.
Its [append-only erratum](artifacts/implementation/pat-io-binding-resolver/results/focused-purity-01/ERRATUM.md)
corrects a frozen candidate README: the conservative driver identity covers HMS
source/vendor/schema/data, not tests; this test-only correction does not change it.
The
[independent result review](artifacts/verification/pat-io-binding-resolver-review/results-failed29/review.json)
confirms the failure scope and all actual method identities. No provider tick,
I/O qualification or public service ran. The
[source02 review](artifacts/verification/pat-io-binding-resolver-review/implementation02/review.json)
confirms corrections to role-map bounds and failed-test state retention.
Execution, I/O qualification and public PAT mounting remain unfinished.

A source-only [I/O timing and outcome handoff](artifacts/implementation/pat-io-timing-oracle-design/README.md)
now pins 19 selected source files and seven historical references. It defines a
sufficient whole-declared-domain timing check for an explicit virtual-clock
schedule, including early admission and lease waiting. Its independent reducer
design requires raw receipt versions, owners, fences, counters, authority claims,
replay rows and timed phase records. Activation alone cannot establish cycle
completion. No project module, Runtime, test or qualification worker was run for
this design. Worker/reducer implementation and independent final review remain
outstanding; the static component's later implementation is recorded below.

The subsequent isolated [timing/case-planning candidate](artifacts/implementation/pat-io-timing/results/attempt02-passed65/README.md)
passes **65 pure tests** in 7.469 test seconds: 20 existing compiler, 14 fixed-unit
and 31 new I/O contract methods. Whole declared duration domains, exclusive
sequential timing, early-admission leases, exact units, sparse enums and typed
negative case plans are checked. Generated cases agree with actual compiler
outcomes. Planning after trusted setup passes file/clock/SQLite/provider vetoes.
The static lease enclosure intentionally overapproximates correlations.

The [earlier failed65 attempt](artifacts/implementation/pat-io-timing/results/attempt01-failed65/README.md)
has 64 passes and one fixture expectation failure in 6.508 test seconds. An enum
equality predicate is refused by the existing parser before the new empty-domain
branch. Only that test changes: it now checks the parser refusal, then uses a
valid enum-hole range to reach the intended policy refusal. The production module
and all other 156 project files are unchanged between attempts. Both attempts
preserve their 157 copied project inputs, six active harness inputs and 159
external pins; frozen preparation has 163 entries before and 164 after correction.
All 689 recorded origins match, with no prohibited attempts, and compiler/provider
identities remain equal within and across runs. Original private scratch roots
remain retained and empty. These are actual pure host tests, not an I/O worker,
resolver execution, outcome qualification, live integration or physical result.
Independent review, the worker/reducer, combined fault budgets and public service
installation remain unfinished.

The next isolated [I/O phase-engine candidate](artifacts/implementation/pat-io-trial-engine/results/attempt01-passed20/README.md)
passes **20 integration tests** in 114.915 test seconds against actual private
IoRuntime, compiler, trusted resolver, procedures and shared-board GPIO/PWM state.
It drains durable progress before advancing virtual time, retains one immutable
compiled request and captures bounded raw tables and timed phases. Cases include
sixteen steps, exact replay, early-admission leases, cancellation, lost receipts,
restart and evidence/tick limits. Owner reopen changes the I/O session: accepted
work or an unstarted suffix refuses stale-session resume; a completed single-step
history can reconcile without another activation. No request is silently rebound.

All 159 project inputs, 162 preparation entries, six active harness inputs and
159 external pins remain unchanged; 691 actual origins match, with 209 bytecode
reads refused and no prohibited attempts. All twenty workspaces, nineteen engine
states, 38 databases and 2,619 records remain retained. Root rehashed the source
and originals, checked 352 checkpoints and 10,208 table references, and compared
551 final captured tables to copied databases opened read-only. The original
private scratch root and its 17,183,506 bytes remain unchanged. A failed root
acquisition path-base assumption and its corrected successful acquisition are
both preserved; the tests were not rerun. The missing-receipt fixture deliberately
retains one unresolved operation, board owner and authority claim.

This is a worker component and serialization proof. All qualification/independent
outcome flags remain false. Complete matrix/fault orchestration, configuration
attestation, the independent reducer, enforced aggregate storage and public
qualification remain unfinished. Helper usage limits prevented independent agent
review. No live runtime source, full748 verification, physical device or hub
provider changed.

The isolated [independent I/O transcript reader](artifacts/implementation/pat-io-transcript/results/attempt01-passed39/README.md)
now passes **39 pure tests** in 11.478 test seconds. It checks all nineteen retained
trial20 outputs: 2,619 records, 352 checkpoints and 153 calls, without constructing
a Runtime or connecting to SQLite. The closed grammar checks every table, column,
typed cell, page, primary key, reference and phase, including clock/reopen identity
and exact compiler-return/plan correspondence. Adversarial tests recompute hashes
and references, then still reject structural mutations. File/clock/database vetoes
also pass during inspection. Missing-receipt structural acceptance continues to
report unresolved work; it is not a qualification result.

All 2,800 project/data files, 2,803 preparation entries, six active harness files
and 159 external pins remain stable. All 655 origins match, 191 bytecode reads
are refused, and there are no prohibited attempts. Root verifies the exact method
log and fixture provenance, rehashes all 2,915 earlier trial20 result entries and
retains 2,833 copied attempt files. The new original private scratch root remains
empty and unchanged. Independent outcome flags remain false: GPIO/PWM state and
footprint derivation, receipt/intent/proof joins, counter/event/replay semantics,
complete configuration attestation and qualification orchestration remain needed.
The reader is isolated; the live runtime and full748 verification are unchanged.

The next isolated [board-history semantic component](artifacts/implementation/pat-io-board-history/results/attempt01-passed74/README.md)
passes **74 combined pure tests** in 65.925 test seconds: 35 new semantic methods
and all 39 reader methods. Eighteen coherent original histories account for
29 activations, 26 completed cycles and three canceled activations. The missing
current receipt is rejected. Typed GPIO/PWM footprints and model states are derived
without provider validators; complete receipt histories, counters, ownership,
fences, dispatch identities and captured transition times are compared. Provider
completion before authority settlement and historical idle under a later owner
remain valid. Every semantic mutation must first pass structural inspection after
recomputed page/record hashes, then fail the intended semantic check.

All 2,802 project/data inputs, 2,805 preparation entries, six active harness files
and 159 external pins remain unchanged. All 659 actual origins match, with 193
bytecode reads refused and no prohibited attempts. Root verifies method/log order,
source/fixture bytes and both earlier result packages (2,915 trial20 and 2,837
reader39 entries), then retains 2,835 attempt files. Original scratch remains empty
and unchanged. Outcome facts were asserted in-process, not emitted as a separate
qualification verdict. Complete authority/procedure/event/replay/floor semantics,
PAT-to-intent correspondence, no-start guard causes, auxiliary actors, configuration
attestation and matrix qualification remain unfinished. All complete-outcome and
qualification flags remain false; no live integration or physical execution ran.

The next isolated [operation-history component](artifacts/implementation/pat-io-operation-history/results/attempt01-passed112/README.md)
passes **112 combined pure tests** in 73.860 test seconds: 38 new operation methods,
35 board-history methods and 39 reader methods. It folds operation state from
immutable events, derives authority fences at admission, requires explicit claim
release, and joins exact historical receipt evidence to dispatch/session identity.
Namespace, replay and reserved keys agree with the captured child-request inventory.
All nineteen actual authority histories account for 32 admissions and 156 events;
the missing-current-receipt trial retains its one unresolved operation and claim.
The separate board checker still rejects that corruption. Neither successful
serialization nor coherent authority history can turn it into a qualified PAT.

All 2,804 project/data inputs, 2,807 preparation entries, six active harness files
and 159 external pins remain stable. All 663 actual origins match; 195 bytecode
reads are refused and no prohibited attempts occur. Root verifies exact method/log
order, origin and fixture bytes, all 2,915 trial20 and 2,839 board74 result entries,
and retains 2,837 copied attempt files. Original scratch remains empty and unchanged.
The result is sealed with 2,841 files. Parent event/control-flow semantics,
independent PAT-to-intent correspondence, live policy/configuration attestation,
no-start causes, auxiliary actors and matrix qualification remain unfinished.
All complete-outcome and qualification flags remain false. This isolated change
adds no physical provider or hub compute control and leaves live full748 unchanged.
Helper account limits prevent independent agent review.

The isolated [procedure-history component](artifacts/implementation/pat-io-procedure-history/results/attempt01-passed146/README.md)
now passes **146 combined pure tests** in 162.813 test seconds, within the original
180-second outer deadline. Its 34 new methods run alongside all 112 prior checks.
It derives parent state, cursor, events, cancellation delivery and child links
from the call schedule and independently checked operation histories. A cycle's
parent stages before and after adapters are distinct; post-adapter admissions
cannot already have dispatched. Prefix advancement requires completed children
with released claims. Exact control replies and every retained observation must
match the derived state. Mutations first pass operation-history inspection.

All nineteen trials retain 18 parents and 105 parent events: nine completed,
five canceled, one failed, one running, two accepted and one unsubmitted trial.
The missing receipt leaves its parent running with an unresolved child/claim.
All 2,806 project/data inputs, 2,809 preparation entries, six harness files and
159 external pins remain stable. All 667 origins match, 197 bytecode reads are
refused, and no prohibited attempts occur. Root rehashes actual origins, verifies
method/log order and fixture provenance, revalidates all 2,915 trial20 and 2,841
operation112 result entries, and retains 2,839 copied attempt files. The result
seal covers 2,843 files; original scratch remains empty and unchanged.
Independent PAT-to-intent correspondence, complete configuration/failure-cause
attestation, auxiliary actors, required fault composition and qualification remain
unfinished. All complete-outcome and qualification flags stay false. No live
runtime, physical provider or hub control changed; independent agent review was
unavailable due to helper account limits.

The isolated [PAT-correspondence component](artifacts/implementation/pat-io-correspondence/results/attempt01-passed41/README.md)
passes **41 focused pure tests** in 59.155 test seconds: 37 new methods and the
four prior methods covering all retained histories. The earlier full146 remains
a separate historical result. The new checker independently derives ordered
instructions from the intended finite PAT, tagged parameters, fixed units,
literal arguments, timing offsets and original worker session. Full plan hashes,
dependency metadata and original/reopened environment references must agree.
Adversaries first pass structural, operation and parent checks, then refuse when
the internally consistent execution belongs to different requested values or PAT.

The nineteen original trials contain eighteen successful lowerings with 35 child
requests and one correct refusal of an integral floating-point input for an
integer parameter. The four history methods retain the original unresolved work.
All 2,808 project/data inputs, 2,811 preparation entries, six harness files and
159 external pins stay stable. All 671 origins match; 199 bytecode reads are
refused and no prohibited attempts occur. Root verifies exact methods/log order,
origin/fixture bytes and all 2,915 trial20 plus 2,843 procedure146 result entries,
then retains 2,841 copied attempt files in a 2,845-file result seal. Original
scratch remains empty and unchanged. A consistent opaque compiler label proves
historical consistency only; current compiler identity is explicitly unattested.
Complete live configuration/authorization, static timing-policy composition,
required fault/auxiliary-actor coverage, aggregate limits and qualification remain
unfinished. Full-outcome and qualification flags remain false. No live runtime,
physical device or hub provider changed; helper account limits prevented
independent agent review.

The isolated [configuration-capture component](artifacts/implementation/pat-io-configuration-capture/results/attempt01-passed32/README.md)
passes **32 original host tests** in 133.470 test seconds: the prior 20 engine
methods and 12 new configuration methods. Fifteen registry tables now accompany
each execution checkpoint under the same authority/board locks. They retain
types, instances, capabilities, bindings/history, grants, presence/sessions,
observations/streams and resource requirements, plus actual resolver registration
identity. Public metadata excludes the cursor signing key; the private raw DB is
retained. Both streams share the original 4,096-record/16 MiB/60-second boundaries.

Permission withdrawal before parent acceptance and after child admission prevents
activation in the tested cases. Reopen captures changed session/owner identities;
the complete sixteen-step case stays within 1,109 combined records and 6,025,635
bytes. One new GPIO trial passes all five existing semantic readers, which do not
attest the new configuration stream or permission-failure histories. All 2,810
project/data inputs, 2,813 preparation entries, six active harness files and 159
external files stay stable. All 705 origins match, 216 bytecode reads are refused,
and no prohibited attempts occur.

Root acquisition verifies 4,340 execution records and 504 configuration records,
including 206 paired configuration snapshots. It compares 1,079 final table
snapshots to 62 closed copied databases using read-only immutable access and
retains 7,844 copied attempt files in a 7,848-file result seal. Original nonempty
scratch retains 5,000 files/31,583,933 bytes, including the original unresolved
missing-receipt case. This establishes capture integrity only. Independent
configuration/authorization attestation, compiler identity, timing composition,
fault/auxiliary-actor coverage, aggregate limits and qualification remain needed.
All attestation/full-outcome/qualification flags stay false. No live runtime,
physical provider or hub control changes; helper limits prevented independent
review.

The [independent configuration-history candidate](artifacts/implementation/pat-io-configuration-history/results/attempt02-passed87/README.md)
passes **87 pure tests** in 39.013 test seconds: 48 new methods plus all 39
transcript regressions. A separately trusted authority/revision and grant-change
plan prevents captured permissions from authorizing themselves. The checker
validates installed execution contracts, exact actor type/binding, instances,
bindings/history, routes, requirements, topology/generations/proofs and resolver
registration, then session/stream history and observation provenance/order.
New namespace, parent-step, admission and dispatch permissions must match the
captured configuration and trusted plan. Possible execution requires a dispatch
link; changed immutable intents or fabricated permission-refusal causes refuse.

The twelve original configuration fixtures retain 206 snapshots and 504
configuration records beside 1,721 execution records. Their decision counts are
twelve namespaces, eleven parents/27 steps, 21 admissions, twenty dispatches,
one refused parent and one permission refusal before dispatch. Consecutive
identical final checkpoints from two capture tests are now accepted; changed
execution/configuration recaptures refuse. All 39 transcript regressions pass.
The full historical board/operation/parent suites are not rerun by this selection.

The [first failed run](artifacts/implementation/pat-io-configuration-history/results/attempt01-failed87/README.md)
is retained with its exact failure/subtest receipts. It exposed an incorrect
sorted PWM required-field expectation. Source02 corrects one line to preserve
declaration order; all fixture/test bytes and permission checks remain unchanged.
All 5,050 current project/data files, 5,054 preparation entries, six active harness
files and 159 external pins remain stable. All 665 origins match, 196 bytecode
reads are refused and no prohibited attempts occur. Root rechecks all 2,915
trial20, 7,848 configuration32 and 5,085 failed87 result entries and retains 5,083
copied attempt files in a 5,086-file result seal. Original scratch stays empty.
These are independent configuration-history/decision checks over retained data;
current-source attestation, active permission withdrawal, intermediate sampling,
full timing/fault/auxiliary-actor composition, aggregate limits and qualification
remain unfinished. All full attestation/outcome/qualification flags stay false.
No live source, hardware, hub control or inference changes. Independent agent
review remains unavailable due to helper account limits.

The [active permission-withdrawal capture](artifacts/implementation/pat-io-active-revocation/results/attempt01-passed38/README.md)
passes **38 original host tests** in 235.119 test seconds: the prior 32 capture
methods and six new cases, with production source and inherited tests unchanged.
Withdrawal stops active GPIO, prevents its remaining PAT step and restores all
three PWM resources. At the exact modeled due time, withdrawal prevents completion.
A prior cancellation keeps its client-cancel cause, while a cycle completed before
withdrawal keeps its historical completed receipt. Separately declared grant
plans pin the changes; explicit read permission remains for status.

The six new activations yield one completed and five canceled cycles. Both
reply-loss cases retain terminal board receipts and modeled idle while authority
claims remain held with unknown outcomes; later reconciliation releases claims
without a second activation. Root checks all 4,948 execution and 739 configuration
records, 650 checkpoints and 298 paired configuration snapshots, then compares
1,343 final table snapshots against 74 copied closed databases. Original scratch
retains 5,873 files/36,344,139 bytes unchanged, including the inherited unresolved
missing-receipt case. All 5,051 project/data inputs, 5,054 preparation entries,
six active harness files and 159 external pins stay stable. All 707 origins match,
217 bytecode reads are refused and no prohibited attempts occur.

This captures and checks actual retained states; independent active-revocation
and guard-cause semantics remain unsupported by the existing pure readers.
Full attestation/outcome/qualification flags remain false. Current compiler
identity, full timing/fault/auxiliary-actor composition, aggregate enforcement and
public qualification remain unfinished. No live source, physical provider, hub
compute control or inference changed. Helper account limits prevented independent
agent review.

The [independent authorized-history composition](artifacts/implementation/pat-io-authorized-history/results/attempt01-passed103/README.md)
passes **103 pure tests** in 136.712 test seconds and 160.488 elapsed seconds,
within the original 180-second bound. Twenty new methods run alongside all 48
configuration and all 35 board regressions. The new checker joins trusted
configuration/grants, independent PAT requests, board state/receipts, operation
events and parent history. It derives pending-operation cancellation, temporal
veto, permission veto and due completion in order. Historical terminal receipts
remain unchanged after permission loss. The public standalone configuration and
board APIs still refuse these causes without the joined context.

All six actual active-withdrawal fixtures pass: six activations, one completed
cycle, five canceled cycles, four permission-caused stops and one prior client
cancellation. The derived parents are four failed, one completed and one canceled.
Both reply-loss histories retain board settlement separately from authority claim
release. Existing GPIO/PWM/reopen/sixteen-step configuration histories also compose.
Rehashed adversaries reject unsupported causes, wrong precedence, rewritten
completion, suppressed stops, early claim release, active resources or retained
owners after stopping, false counters/parent completion and stale guard context.
Filesystem/clock/SQL vetoes and input-immutability assertions pass.

The source preserves 5,049 inherited project/data files unchanged and changes two
pure readers for the private validation handoff. Its two new Python files and
850 fixture/index files yield 5,903 project/data inputs and 5,908 preparation
entries. All inputs, six active harness files and 159 external pins remain stable;
all 673 reported origins match and no prohibited attempts occur. New fixture
copies retain 608 execution records, 235 configuration records and 92 paired
snapshots. This closes the tested active permission-loss cause gap, while pending
unknown recovery, full read withdrawal, current compiler identity, intermediate
sampling, full timing/fault/auxiliary-actor composition, aggregate enforcement
and public qualification remain unfinished. All full attestation/outcome/
qualification flags stay false. No live runtime, physical provider, hub compute
control or inference changed; helper account limits prevented independent review.

Root acquisition also rechecks all 26,811 selected prior result entries, exact
fixture copies and actual import file hashes. It retains 5,936 complete attempt
files; 200 bytecode reads were refused. The original private scratch remains
empty with unchanged identity. No historical attempt or raw evidence was reset.

The [pending-output recovery capture](artifacts/implementation/pat-io-pending-recovery/results/attempt01-passed46/README.md)
passes **46 original host tests** in 334.815 test seconds and 355.192 elapsed
seconds, within the original 600-second bound. Eight new cases run alongside all
38 prior capture methods. All 5,903 inherited project/data inputs remain unchanged;
one new test file declares the fault schedules and verifies actual runtime state.

Seven post-commit activation replies, two pre-commit finish attempts and one
authority reconciliation are deliberately lost/failed at separately declared
points. Unknown authority state can retain an active output and pending receipt.
A failed recovery stop retains output ownership and authority claims; a committed
stop with a lost authority reply instead retains modeled idle and held authority
claims until reconciliation. GPIO/PWM recovery, due-time recovery, invocation
withdrawal and prior cancellation all preserve these distinctions. Eight new
activations yield zero completed cycles and eight recovery cancellations. Seven
parents fail; the already canceled parent stays canceled while its child settles
as failed with the original cancellation request still recorded.

The 45 engine states retain 90 closed databases, 5,771 execution records and
1,057 configuration records, with 434 paired configuration snapshots. All 5,904
project/data inputs, 5,907 preparation entries, six active harness files and 159
external pins remain stable. All 709 origins match, 218 bytecode reads are refused
and no prohibited attempts occur. Original raw scratch retains 42,800,037 bytes
unchanged, including the inherited unresolved missing-receipt case. The
[oracle handoff](artifacts/implementation/pat-io-pending-recovery/results/attempt01-passed46/ORACLE-HANDOFF.md)
defines independent schedule/cause/state obligations, implemented in the next
stage below.
The composed checker at that stage still refuses pending-unknown recovery. Broader
fault/auxiliary-actor coverage, current compiler identity, intermediate sampling,
aggregate enforcement and public qualification remain unfinished. All complete
outcome/qualification flags stay false. No live runtime, physical provider, hub
compute control or inference changed; helper account limits prevented independent
agent review.

The subsequent [independent recovery-history composition](artifacts/implementation/pat-io-recovery-history/results/attempts01-02/README.md)
passes **136 distinct pure tests** against one frozen candidate. All 83
configuration/board methods pass in 77.009 test seconds (84.888 elapsed); all 20
authorization methods and 33 new recovery methods pass in 112.575 test seconds
(123.602 elapsed). Each separate invocation retains its original 180-second
deadline. All 103 prior methods are included; the historical full748 suite and
live runtime source are unchanged.

The new composition derives fault targets and recovery causes from separately
trusted schedules and prior state, then checks complete board, authority and
parent histories. All eight actual fixtures retain eight activations, zero
completed cycles and eight recovery cancellations, with seven failed parents
and one previously canceled parent. Ten faults, ten guards, eight stops and
eight settlements are checked. The checker preserves active/unknown state at a
failed stop and terminal/unknown state at a failed reconciliation. A later
unfailed recovery must settle the existing receipt and release its claims.

An adversarial history first passes the independent operation-event fold while
remaining unknown after an unfailed recovery. The new checker rejects that
missing settlement. Rehashed mutations also reject invented/omitted faults,
wrong phase/error/reason, missing retained proof, early claim release, due-time
or cancellation relabeling, hidden activation and active PWM output after stopping.
The standalone APIs retain their original refusal without the private validated
cause handoff. I/O vetoes and input-immutability assertions pass.

All 7,056 project/data inputs, 7,061 preparation entries, six active harness
inputs and 159 external pins remain stable in each run. The two attempts record
665 and 677 matching origins, refuse 196 and 202 bytecode reads and contain no
prohibited attempts. Exact new fixture copies include 823 execution records,
318 configuration records and 136 paired snapshots. Acquisition rechecks the
12,999 original recovery46 result entries and keeps both complete attempts and
their original empty scratch roots. Runtime/provider/compiler and inherited
tests remain unchanged; only two inherited independent readers are extended.

This closes the tested pending-output recovery gap for the immutable simulation
profile. Full read withdrawal, recovery with reopen/clock loss, auxiliary actors,
intermediate sampling, current compiler identity, full timing/fault coverage,
aggregate enforcement and public qualification remain unfinished. Complete
attestation/outcome/qualification flags stay false. No physical provider, hub
compute control or live inference changed; helper limits prevented independent
agent review. The end-to-end goal remains active and incomplete.

The separate [qualification supervisor rebase](artifacts/verification/pat-supervisor-current-integration/README.md)
passes 19 tests against the exact frozen full696 source closure: 147 copied
inputs and 139 selected external inputs remain stable. Genuine closed test
configurations/evaluator identities were saved before launch; the four supervisor
implementation modules are unchanged. This does not qualify the subsequent live
I/O changes or mount a public qualification service. Its
[storage assessment](artifacts/verification/pat-supervisor-current-integration/storage-design/ASSESSMENT.md)
requires actual enforced aggregate storage and protected control capacity; no
quota, mount or service configuration was changed. The six retained documentation
acquisitions belong to that separate lane, not an inflated main-corpus count.

Receipt-gated driver/service lifecycle implementation remains isolated;
admission passes and generation-changing acceptance is underway.
[Draft01 review](artifacts/verification/io-lifecycle-preliminary-review/01/review.json)
found publication/proof association, type and final-timing gaps. The targeted
[draft02 review](artifacts/verification/io-lifecycle-preliminary-review/02/review.json)
finds those source issues addressed while preserving binding/release semantics
through explicit transaction helpers. The later combined run below passes all
30 lifecycle methods; additional boundaries and public lifecycle result support
remain unfinished. Neither source review establishes executed lifecycle control.
The [separate harness review](artifacts/verification/io-lifecycle-source-preparation-review/FINDINGS.md)
found five preparation gaps; [snapshot04](artifacts/verification/io-lifecycle-harness-remediation-review/04/review.json)
retains two further source findings. The targeted
[snapshot05 review](artifacts/verification/io-lifecycle-harness-remediation-review/05/review.json)
finds those addressed in source, with all 48 HMS files and 54 existing test-method
bodies unchanged from03. After the sealed 748-test milestone, the first 13
controlled harness probes ran separately: four assertion failures across three
methods, zero errors/skips, with copied inputs, selected external inputs and the
outer harness unchanged. The [retained result review](artifacts/verification/io-lifecycle-harness-probes-review/results-attempt01/review.json)
traces these failures to installed IDNA validation modules omitted from the
harness dependency manifest. All 12 owned fixture children were reaped without
emergency cleanup. Several negative outcomes also hit this dependency refusal,
so that failed attempt does not isolate their intended rejection cause. The
[corrected bookkeeping attempt](artifacts/verification/io-lifecycle-harness-probes/results/corrected-attempt01/index.json)
passes all 13 methods after adding only the explicit installed IDNA dependency
pin and selecting the corresponding frozen source snapshot. Its 194 copied and
159 selected external inputs remain unchanged; all 12 owned children were
reaped without emergency cleanup. The
[independent result review](artifacts/verification/io-lifecycle-harness-probes-review/results-corrected-attempt01/review.json)
confirms clean ordinary import ledgers and the intended negative causes,
including failed-backup and post-close raw-state retention. These bookkeeping
probes are separate from the passing full748 runtime. The subsequent single
[admission smoke](artifacts/verification/io-lifecycle-harness-probes-review/smoke06-attempt01/review.json)
stops in setup with `UNSAFE_STATE_ANCESTOR`: the controlled temporary path was
under a nonsticky, group-writable workspace ancestor. No Journal or board
database was constructed and the test body did not run. The runtime's pathname
policy remains unchanged. After the harness moved temporary state to a verified
private directory under `/tmp`, the
[corrected single admission test](artifacts/verification/io-lifecycle-admission-smoke/attempt02-corrected/index.json)
passed in 3.828 seconds, with 156 copied and 159 selected external inputs stable.
The [independent review](artifacts/verification/io-lifecycle-harness-probes-review/smoke07-attempt01/review.json)
confirms the receipt and retained bytes. Inspection of copied logical databases
shows one accepted operation with the exact five claims, revision 1, and no
dispatch, lifecycle receipt or publication. Administrative publication was
refused while those claims were held. This establishes admission only.
The subsequent [old-source regression attempt](artifacts/verification/io-lifecycle-regression-composition/results/attempt01-old-two/index.json)
runs two current tests against an explicitly composed earlier source snapshot,
retaining three assertion failures and one error. It reproduces acceptance of a
valid previous-generation proof and a boolean revision, an unstructured
error for a list-shaped binding record, and completion after the final start
window had expired. Both cases recorded one modeled generation change and publication;
these are reproduced defects, not successful lifecycle acceptance. The
[matching corrected-source attempt](artifacts/verification/io-lifecycle-regression-composition/results/attempt02-current-two/index.json)
passes both methods in 17.530 seconds with 156 copied and 159 selected external
inputs unchanged. The delayed case remains at revision 1 with
`generationApplied:false` and `rejected_before_start`; its terminal settlement
contains `publication:null`, and its claims are released after the no-effect
receipt. All three altered publication variants refuse; exact restored replay
still succeeds. The subsequent
[44-method attempt](artifacts/verification/io-lifecycle-regression-composition/source01/attempts/attempt03-lifecycle30-api14/result.json)
runs all 30 drafted lifecycle methods and 14 ordinary I/O result-contract methods:
43 pass and one errors in 259.645 seconds, with 156 copied and 159 selected
external inputs unchanged. The runtime rejects a boolean revision with
`JournalError(ARGUMENT_SCHEMA_MISMATCH)`; that test incorrectly expects
`ContractError`. Its later ordinary-grant/management-denial assertions were not
reached. The failed attempt is retained. A
[test-only correction](artifacts/verification/io-lifecycle-exception-correction/results/attempt01-focused/index.json)
then passes that method in 5.953 seconds, checking the exact refusal code and
zero operations/claims before continuing through the original grant test.
Copied database inspection confirms all three ordinary-user grants exist but
no operation, claim, dispatch or generation result was created. All 48 HMS
source files and every other test method remain unchanged. The subsequent
[combined 160-method attempt](artifacts/verification/io-lifecycle-shared-regression-results/attempt01-failed/index.json)
has **159 passes and one failure**, in 488.437 test seconds. The sole failure is
the inherited binding-extraction AST assertion: it compares the original body
with a wrapper that now delegates to an explicitly guarded transaction helper.
All 30 lifecycle, 14 I/O API, 24 provider, 21 topology, 17 Registry and 22 selected
Journal methods pass, along with 31 of 32 resource-admission methods. The two
Journal subprocess methods were deliberately excluded from this harness.
All 156 copied and 159 selected external inputs remain stable. The
[independent result review](artifacts/verification/io-lifecycle-regression-composition-review/results-failed160/review.json)
verifies every actual method identity and retains 58 logical snapshots for
lifecycle/provider cases; the other selected modules have no added per-case
database captures. This remains a failed suite, with no automatic retry.
The [corrected focused structural check](artifacts/verification/io-lifecycle-shared-regression-results/attempt02-structural-only/index.json)
passes in 1.017 seconds with 156 copied and 159 external inputs stable. It checks
the complete wrappers/transaction guards and all 20 original statements through
explicit helper composition and one deployment-parameter substitution. It has no
per-case database capture and does not relabel failed160 as a passing full suite.

A separate [partial-setup finding](artifacts/verification/io-lifecycle-cross-profile-review/source08/review.json)
is now [reproduced on unfixed source10](artifacts/verification/io-lifecycle-partial-setup-results/attempt02-reproduced/index.json):
ordinary IoRuntime returns successfully after lifecycle enrollment, creates the
wrong board profile and marks ordinary routes ready. Lifecycle reopen then
refuses `IO_STORAGE_SHAPE`; epochs advance 1→2→3 while operations, claims and
effects remain zero. The expected-refusal test fails in 5.993 seconds, with all
156 copied/159 external inputs stable, six logical snapshots and original raw
state retained. The earlier [source09 fixture failure](artifacts/verification/io-lifecycle-partial-setup-results/attempt01-fixture-failure/index.json)
stops before ordinary open because its expected digest used raw configuration
instead of normalized configuration. It remains separate from the reproduction.

The source11 gate [passes the matching after-case](artifacts/implementation/io-lifecycle-settlement/review-inputs/11/attempts/attempt01-partial-setup-after/result.json)
in 4.579 seconds, with 156 copied/159 external inputs stable. Its sole production
change checks both valid ordinary Registry profiles under the Journal mutex
before ordinary catalog construction. The ordinary opener now refuses
`IO_REGISTRY_PROFILE` with zero catalog/board constructor calls; exact lifecycle
reopen succeeds, preserves installation/enrollment/binding identity, creates only
initial generation history, and leaves all operation/effect counts zero. Six
logical snapshots are retained. The separate
[five ordinary regression cases](artifacts/verification/io-lifecycle-partial-setup-results/attempt04-ordinary-five/index.json)
pass in 12.916 seconds, with the same 156 copied and 159 external pins stable.
They exercise fresh creation, pending-operation reopen, changed bindings,
revoked administrative grants and refusal to reset missing or changed stores.
Five logical snapshots are retained. The
[independent review](artifacts/verification/io-lifecycle-cross-profile-review/results-ordinary-five/review.json)
verifies exact method identities and retained bytes. No four-method proposal or
full160 rerun was executed.
The
[live748 scope review](artifacts/verification/io-lifecycle-cross-profile-review/live748-scope/review.json)
confirms the live Registry rejects that lifecycle profile; this is an isolated
stage correction. Journal recovery may write before refusal, so the gate does
not promise byte-unchanged authority storage or migrate old source identities.
Remaining boundary cases and
public lifecycle result support are unfinished.

Three additional [source12 boundary tests now pass](artifacts/verification/io-lifecycle-boundary-results/attempt01-three-root-retention/README.md)
in 33.295 test seconds, with all 156 copied and 159 external inputs stable.
Direct driver changes retain the full sibling footprint and publish once on
replay. A service with no ordinary dependents changes only its own lifecycle
generation while preserving an existing ordinary receipt and binding history.
The literal maximum interoperable integer is refused as an expected revision
before admission, with no operation, replay key, claim or effect. Nine logical
snapshots were acquired; read-only inspection of all 18 copied databases leaves
their hashes unchanged. The root completed retention after helper agents reached
a usage limit; a final independent result-review seal is not claimed. Capacity,
post-effect revision exhaustion, other provisioning cuts and repeated history
remain planned boundaries.

The prior resource-admission32 and memo77 focused proofs, topology21 and the full
696 checkpoint remain unchanged, along with all earlier failures and checkpoints.
The new I/O profile now consumes resource admission; PAT compilation/routing,
evidence reduction and memo remain host libraries. Prompt synthesis/learning,
persistent Arduino applications, public PAT qualification, physical drivers,
compute/stream scheduling and complete hub self-management remain open.
The user's [ten-part goal](spec/00-scope.md), [prompt-to-PAT requirement](docs/prompt-to-pat.md)
and [I/O/driver/hub requirement](docs/io-driver-hub-control.md) remain active.

A [finite I/O PAT qualification design](artifacts/verification/io-pat-qualification-design/DESIGN.md)
pins 22 selected current inputs and identifies four concrete prerequisites: fixed
unit metadata, I/O-aware complete binding enumeration, strict whole-domain timing
fit, and activation/cycle/raw-ownership evidence. It proposes a narrow homogeneous
one-role GPIO or PWM sequence policy. All acceptance checks are planned; no
compiler, worker, reducer or public service was changed or executed for that design.

## Current evidence

- 323 acquisition records across the research lanes; 290 successful records, including extracted core files, a relocation page and multiple renditions of some works. Seventeen prior WoT artifacts and 41 Architecture image acquisitions are retained separately. Counts are not counts of distinct fully read works; failed, partial and wrong-document records remain visible. Instrumentation access failures are also preserved in its manifest's separate limitation list.
- Twenty-five repository/commit pins: thirteen shallow checkouts plus twelve snapshot pins (one Google Research commit, five home-automation repositories, two historical Harness commits, one VoxPoser selection, one MCP specification snapshot one Voyager selection and one LRLL website selection). File/cell coverage is recorded; whole-repository reading is not claimed. GR00T media/LFS acquisition remains incomplete. The `rfc8785.py` pin supplies two reviewed, unmodified Apache-2.0 modules intentionally vendored and executed by host tests.
- Complete extracted text and all numbered figures/tables reviewed for GR00T N1 v2 and OpenVLA v3, including appendices/references. Both reviews retain experimental limitations and source discrepancies. Timing, precision, controller mode and embodiment must be evaluated together.
- Complete TD 1.1 and Discovery text and eleven figures reviewed. The approved Architecture 1.1 Recommendation adds 8,405 fully read LF lines, appendices A–C, two tables and all 40 numbered figures (41 assets); history/errata and selected editor-source coverage remain separately labeled. Complete MQTT 5 and Sparkplug 3 text reviewed, with MQTT table-structure cross-checks and all fourteen Sparkplug figures. Archived contexts/Thing Model schema and other long standards remain distinct unfinished work.
- LabOP's complete paper and twelve numbered figures, two pinned Bluesky documentation pages, the Bluesky protocol module and selected implementation files reviewed. Laboratory records distinguish material identity, uncertain effects and physical resume from software checkpoint replay.
- Both SiLA 2 v1.1 specifications are fully read: 8,248 LF-addressable lines and semantic diagrams/numeric tables across forty-six retained page renders. The binding proposal distinguishes execution UUID validity from durable HMS identity, subscription cancellation from physical stop, and native metadata from enforced authority.
- Complete base CoAP, RFCs 9175/8974/9876 and four errata indexes reviewed (9,970 LF lines). Complete retained LwM2M Core 1.2 reviewed (11,164 LF lines and all 28 semantic figures). Current Core/Transport 1.2.2 available published HTML texts are now fully read, with all 48 semantic figures; the nine-source overlay totals 12,771 LF lines. Missing normative Appendix K content, separately acquired XSDs, publication inconsistencies and three unread PDF text renditions remain explicit. Concrete stacks and referenced security standards remain further work.
- Full RFC 8613 OSCORE (5,267 LF lines, appendices and vectors), RFC 9668 (1,235 lines), four metadata/errata sources and the 840-line key-limits draft reviewed. The draft remains nonstandard; KUDOS remains selected-only. A separate [EDHOC review](docs/edhoc-binding.md) now covers full RFC 9528 (4,671 LF lines), all thirteen ASCII figures and fifteen tables, metadata/errata and IANA allocation records; 25 of 82 PDF pages provide selected visual corroboration. Reported errata are not treated as verified corrections, and later allocated labels are not free HMS identifiers. Authentication, transcript reuse, CSPRNG/key storage, context persistence and HMS effect history remain distinct obligations; no crypto implementation or vector execution is claimed. Replay protection does not establish freshness of a delayed first arrival, and restart nonce continuity is distinct from HMS operation replay identity.
- Full RFCs 7641 Observe, 7959 Blockwise and 8323 reliable CoAP reviewed: 6,785 LF lines, 121 pages, all 39 figures, tables and appendices. Full [Q-Block](docs/qblock-binding.md) now adds RFC 9177's 2,154 LF lines, all 20 figures and five tables; 21/41 PDF pages provide selected visual corroboration. Six full text sources total 2,513 lines; the lane's offline verifier checks 82 hashes/52 files/14 coverage ranges and rejects twelve negative fixtures. Notification ordering is not acquisition freshness, and transfer completion is not durable HMS execution. No CoAP adapter was executed.
- Home Assistant/ESPHome: 38 acquisitions, five pinned repository snapshots and 32 full text/file reviews (11,599 LF lines), with three additional selected reviews and live provenance pages kept separate. Concrete state/cache, reconnect, REST cancellation, native API buffering, action-response and boot behavior inform the binding. Neither hardware nor acquired source programs were executed. Two socket-documentation pages have explicit partial coverage.
- Thirty-five full embedded source files across four pinned checkouts reviewed (11,542 LF lines), tracing parser bounds, scheduler allocation/rollover, motion stopping/completion and rclc callback behavior. No acquired code was executed.
- The [clock/boot platform review](docs/clock-boot-platform.md) adds 12 acquisitions: ten full files and selected sections of the ATmega328P family and RP2040 manuals, totaling 7,120 covered LF lines and 28 inspected pages. Six full Pico SDK timer/watchdog/flash files are separately pinned to SDK 2.3.1 commit `079c6f…`; this is not another full checkout or snapshot in the 23-pin count. Low-voltage CPU/write behavior, pending-overflow limitations, UART error ordering and page-flash failure units constrain real bindings. No acquired SDK, MCU or device was run.
- RFC 1662, its errata and the pinned UNO R3 manual fully reviewed, including board figures. Direct download of the Arduino R3/R4 comparison page failed 403 and remains a recorded gap.
- Fifteen complete Arduino AVR core files (2,653 LF lines) and selected board definitions reviewed from the pinned official archive. The original parser cross-links on ATmega328P: parser 219 bytes; minimal harness/startup 558 bytes flash and 221 bytes static RAM. UART/stack/application logic are excluded, and no target program ran. Stock Serial error propagation and blocking behavior remain concrete integration gaps.
- SayCan v2 and Code as Policies v4 fully reviewed: 3,053 LF lines and all substantive figures/tables on forty retained renders. Two official repository subtrees are acquired; two READMEs and nine notebook cells are read. Probability/feasibility/authority/effect evidence remain separate, and source discrepancies are retained.
- The [PAT learning lane](research/planning/pat-learning/README.md) fully reads Voyager arXiv v2, the official project text and thirteen selected repository files at `55e45a88…`: 15 complete sources/5,311 LF lines, 5,709 reviewed lines including selected metadata, all fourteen figures/six tables and eighteen selected PDF pages. The [critique](research/planning/pat-learning/notes/critique.md) distinguishes reusable code from zero-inference routing and identifies unbounded/stale-variable examples, mutable live skill replacement and continued model/embedding calls. Publisher-final access and queued newer papers remain gaps; no acquired planner/model executed.
- The [LRLL lane](research/planning/lrll-full/README.md) fully reads both arXiv v2 and the institutional publisher copy, every PDF page (17 across both renditions), four distinct figures and two tables. Three complete selected website files include one 248-line prompt-string artifact; no orchestration/retrieval implementation was identified. The [critique](research/planning/lrll-full/notes/critique.md) distinguishes library compression and LLM actor/critic reuse from deterministic PAT routing, and retains missing supplement/code and version-difference limitations. The lane adds 15 acquisitions, 12 successful, one repository snapshot pin and 19 coverage chunks; no acquired program was executed.
- The original [AVR Timer1 clock](docs/avr-clock-implementation.md) passes producer and independent host-model campaigns and a pinned cross-link. Producer runs each check 8,655,746 assertions; independent runs each cover 131,920 histories, 8,192,056 conversions, 100,000 sequence steps and twelve rejected compiled mutations. Isolated image: 1,754 flash bytes/47 static SRAM bytes. Multiple-wrap aliases and external source/service/continuity assumptions remain explicit; no MCU execution, measured timing or combined-firmware fit is claimed.
- Inner Monologue arXiv v1, published main/supplement and VoxPoser v2 fully read, with all numbered figures/tables, six official pages and ten selected VoxPoser files. The continuation receipt covers 7,306 LF lines and 44 chunks; 73 renders are retained and 31 substantive pages visually inspected. Publication/model/noise discrepancies and demo-only planner/controller limitations are documented; no robot, acquired planner or model client was run.
- Both retained Modbus application/TCP PDFs fully read: 5,638 LF lines and all 96 pages. A separate [serial V1.02 full-reading overlay](artifacts/verification/modbus-serial-full-read/README.md) now covers all 2,459 LF-split lines and all 44 pages, with appendix algorithms read but unexecuted. It preserves the earlier 312-line partial receipt and is not yet included in the consolidated corpus counts. SCPI-99 remains partial at 1,696/42,293 lines. Publisher CDN copies are not claimed byte-identical to current secure endpoints. Register writes, native completion and physical verification remain separate.
- RFC 8785 and current errata plus SQLite transaction/WAL text fully read; pragma sections selected. The host profile rejects duplicate keys, negative zero, precision loss and malformed/oversized JSON; pins JCS/domain-separated SHA-256 fixtures; and documents exact numerical and authority boundaries. SQLite syntax SVG geometry remains uninspected.
- The microscope-controller lane verifies four repository pins (two new checkouts), 31 complete source/test files (15,216 lines), 765 selected complete-function lines, and the full 14-page autofocus paper with all eight figures. Controller counters, scan-cancel return motion, camera timestamps, failure masking and cleanup gaps inform the [binding proposal](docs/microscope-controller-binding.md). Picamera2 manual coverage is selected. No acquired program/test or hardware was executed.
- The earlier complete MHS announcement-text review, microscopy papers and selected primary pages/code remain part of the corpus. Embedded MHS videos, linked studies and remaining repository paths are not thereby read.
- OPC UA: eight acquisitions pin Services 1.05.07 and Programs 1.05.00. All available Programs text (1,022 lines) and 15 available figures were reviewed; Services coverage is selected (1,711/5,827 lines, 22 sections and 16 figures). Two missing Programs figures and authoritative-download 403s remain explicit gaps. No OPC service or acquired implementation was executed.
- MCP: 22 acquisitions at one official repository pin, 19 complete bounded specification/license pages, selected TypeScript and legacy stdio text, 5,837 reviewed lines and 31 exact chunks. The retained generated schema is used for selected wire validation, not claimed fully read. Current 2026-07-28 and legacy 2025-11-25 semantics inform an original local stdio projection.
- Twenty-two selected Bud Meta Harness files remain pinned at `655d7cec…`; nineteen fully read, three partially. A subsequent source review pins 31 further files at `1f0762af…` and confirms the original 22 snapshots remain byte-identical. A detached checkout at that tested pin contains four HMS experimental packages, native/PTC tools and an opt-in profile. Actual Loader, Node PTC and scripted AgentLoop tests run against the local daemon there. The live adjacent checkout remains unmodified by this work and has advanced externally beyond the tested pins (last observed `3a7d9d67…`; no compatibility claim for that head). A [separate revalidation](integration/harness/revalidation-a1626788/verification.json) passes 16 native/PTC/Loader/AgentLoop, compact C and built SDK/profile tests, seven artifact stages and three aggregate checks at pin `a1626788…` against the retained 280-test runtime. A read-only observer lock race was repaired; an earlier intermittent `DEVICE_UNAVAILABLE` remains unexplained despite the final passing run. Older 335a and 1f receipts remain preserved. A [historical installed-support run](integration/harness/installed-support/verification.json) passes all 16 tests against the frozen 289-test runtime. The [frozen 315-test lane](integration/harness/multi-adapter/verification.json) passes 16/16 against the 315-test runtime, reruns lint and three aggregate checks, and preserves a copied test assertion repair. Seven artifact stages are reused at unchanged emitted inputs. Neither run explains the prior refusal. The SDK tests cover settled work replay/mismatch, normal reopen, actual Session history visibility and the distinction between work cancellation and explicit HMS cancellation. Release packaging, interrupted active-work recovery, production persistence and live-model behavior remain incomplete.
- A [GB10 deployment review](docs/gb10-deployment-evidence.md) adds six fully read bounded NVIDIA pages, 1,013 LF lines, eight tables and one figure. The hardware page is an explicit same-byte revisit. ARM64 dependencies, shared-memory pressure, allocation/transport limits and exact release/SKU scope constrain the proposed inference hub. No model, GPU, container or GB10 device ran.
- Twelve specification chapters cover architecture, execution, registry/runtime, scenarios, WoT descriptions, materials/workflows, constrained framing, host identity, local simulation, checked API contracts and a proposed compact endpoint wire/state profile. Binding/analysis documents additionally cover the researched domain/protocol lanes; earlier independent review resolutions remain recorded.
- An original Python framing codec and fixed-storage portable C decoder now implement the experimental frame specification, with retained wire vectors. Independent review found no substantive framing defect; its extra malformed-input probes were retained as regression tests. No authority, replay prevention, operation payloads or device execution are implemented by this component.
- The new single-owner SQLite journal implements durable replay namespaces/floors, atomic admission/resource claims, dispatch tickets, lifecycle/cancellation/evidence records and conservative restart recovery. Policies and effects in tests are synthetic. Independent reviews repaired trailing-line identifier acceptance, huge-exponent errors, clock-floor rollback on refusal, timestamp-quality sampling and mutable evidence. Review probes also covered competing admissions and dispatch/cancel races; no outstanding reproduced defect remains within their scoped reviews.
- Installed adapter support is now checked during preparation, transactional admission and dispatch. Unsupported adapter/type/instance/action/resource/encoding combinations cannot create new claims or reach the selected backend; unsupported additional local instances no longer break refresh/reopen. Existing replay and historical receipt reconciliation remain available. Nine regressions and five independent compact-C probes pass, including future-work/cancel/expiry checks before ARM under the authority mutex. The later multi-adapter catalog and route-scoped simulation recovery are implemented; physical providers and process isolation remain unfinished.
- The registry separates immutable type bundles, instance enrollment, binding generations, current presence and durable operation authority. Its narrow schema profile rejects unsupported features and contradictory TD projections. Admission combines action grants, installed limits, resource claims and fresh qualified observations. Endpoint session reuse, producer-stream replay, stale cursors and regressed clock epochs fail closed.
- A separate persistent virtual plant implements fan level, microscope position and an inspection counter. Primitive bounds, session checks and resource fences are enforced before synthetic state commits. Simulated effect and receipt are atomic within that plant DB; the runtime reconciles their separate journal transaction after a crash. Missing receipts retain unknown state and claims. Real-device atomicity is not implied.
- `python3 -m hms` now serves a private Linux Unix socket and provides discover/describe/observe/namespace/prepare/invoke/operation/events/cancel and five procedure methods. Peer UID determines the principal; every process of the same UID shares authority. The worker rechecks authorization, freshness, deadlines and clock floors before committing simulated effects. The 50 ms simulated delay and 20 ms polling interval are implementation choices, not physical timing bounds.
- Method-specific response schemas and semantic checks now reject mismatched identities, contradictory descriptions/evidence and malformed event pages. The checked client and Runtime snapshot input before policy/correlation and never retry automatically. A completed adapter receipt can legitimately precede journal settlement; that crash interval is tested without inventing physical completion.
- Independent review reproduced a state-directory pathname race. Runtime startup now checks protected ancestors, refuses symlinks and unsafe DB/owner/sidecar files, and permits trusted sticky-directory ancestry. This prevents untrusted-UID path replacement under the stated policy; it does not isolate the same UID/root or make stock SQLite rename-resilient. Original failure evidence and post-fix regressions are retained.
- The local MCP projection exposes fourteen checked tools, including five procedure methods, in current and legacy protocol modes. The retained native Harness overlay still has its nine primitive tools. Modern stdio tests and an independent installed legacy SDK exercise actual daemon calls; cancellation abandons a reply without inventing physical stop. SDK replay survives MCP restart and daemon reopen with exactly one simulated effect per scenario. Broader client/remote/extension conformance remains unfinished.
- The compact endpoint now has an original fixed-storage C executor/link and Python packet/receipt codec. It enforces one retained slot, exact duplicate/conflict handling, boot/control/context/call/fence domains, immutable cutoffs, cancellation/loss handling and explicit retirement. Fresh clock snapshots prevent backdated completion across a callback; commissioning-mode changes invalidate control; disputed outcomes retain remaining claims. Synthetic native and framed-process tests pass. The new [durable host binding](docs/compact-host-binding.md) stores exact OP bytes, full host fences and clock/context witnesses in the dispatch transaction; it reconciles actual C receipts after reply loss and owner restart. Qualified physical NVM/clock/UART, actual drivers and independent physical stop remain unfinished. The original 1,802-byte allocation is still a design budget, separate from target build evidence.
- An original [finite boot reservation module](protocol/platform/README.md) now preserves epoch uniqueness under an explicit stable-cell/target-only-torn-write model. Plain and sanitizer tests pass 11 cases, 1,792 torn-byte cases and 84 interruption boundaries; independent probes pass. A rollback counterexample is deliberately retained. The module cross-compiles for AVR (910 bytes function text, eight read-only constant bytes; reservation 12 bytes/configuration 14 bytes), without a linked-firmware or electrical qualification claim. No in-place erasure, wrapping, recycling or autoformat is implemented.
- Original [ATmega328P EEPROM callbacks](protocol/platform/avr_eeprom.h) now implement bounded readiness polling, saved interrupt state, erased-byte write-only programming and completion readback. Twelve plain/sanitizer cases and an inspected AVR launch sequence pass. The separate boot-plus-driver probe links to 1,902 flash bytes and 53 static SRAM bytes; it is not the endpoint image and has not run on a target. Physical voltage/reset, completed-cell stability and target-byte failure containment remain unqualified.
- Actual [native/PTC Harness tools](integration/harness/compact-endpoint/verification.json) and [modern/legacy MCP clients](artifacts/verification/compact-mcp/verification.json) now reach the compact C backend for all three scenarios. Each lane checks six scenario executions with exact OP-frame evidence; host SIGKILL after endpoint acceptance recovers by QUERY without another OP. MCP close is distinct from explicit cancellation of future host work. Fan/focus frame counts are handoff evidence, not independent physical effect counters. Inspection counter1 remains synthetic.
- The complete endpoint/framing/synthetic-fixture AVR cross-link retains all required API paths: 15,780 bytes flash, 1,335 bytes static SRAM including storage placeholders, and a conservative 231-byte foreground stack bound. A separate 512-byte stack reservation gives 1,847/2,048 bytes, with 201 unassigned by arithmetic. The IRQ/future-callback allowances are assumptions; no target program, stack high-water, interrupt load or physical timing was measured.
- A 32-entry type-preserving cache stores only pure successful bundle validation. Fresh authority/admission is never cached. Local read measurements retain all samples and conditions; cold CLI and per-call Python bridge costs, uncontrolled host load and large observed tails remain explicit performance limitations.
- Three original custom descriptions and three WoT fixtures remain explicitly synthetic and uncommissioned. WoT actions now project the complete host invocation envelope and pin static source-contract metadata. Runtime type bundles use their own versioned digest; neither placeholder HTTPS forms nor the custom format become installed transport endpoints.

- The [ordered procedure engine](docs/bounded-procedures.md) reserves parent/child keys and atomically links each child admission. Restart interrupts continuation; explicit resume retains exact IDs. Completed-but-held/disputed predecessors block the suffix, cancellation preserves current-child permissions, and parent timeout does not erase unknown effects. Twenty-eight engine tests include a five-step local-plus-two-native sequence and four abrupt crash boundaries. Twenty independent [API review tests](artifacts/verification/procedure-glue-review/verification.json) pass from frozen inputs; seven glue findings were addressed.
- Four [procedure transport cases](artifacts/verification/procedure-transport-trace.json) pass: real mixed-route CLI SIGKILL/reopen/explicit resume, modern and legacy MCP, and a virtual-clock paused-route fairness/expiry case. The CLI relays exactly two native OP frames and each MCP sequence one; 31 new MCP replies validate in this run. The separate paused case checks one synthetic dispatch and effect. Exact replay preserves child identities and frames. No physical evidence is claimed.
- The first 369-test run failed only the two modern/legacy compact MCP catalog assertions that still expected nine tools. Its [98-file failure snapshot](artifacts/verification/runtime-369-catalog-failed/index.json) retains the log and actual traces before updating that expected catalog to fourteen. The passing rerun pins current inputs; no production change was made for these two assertions.
- A [read-only Harness procedure/PAT integration map](integration/harness/procedure-design/README.md) pins 29 inputs and plans thirteen acceptance cases. It identifies the native nine-to-fourteen-tool extension, durable parent identity, explicit interruption and a future model-free PAT invocation path. No new Harness implementation or test execution is claimed.

- The [PAT foundation](docs/pat-foundation.md) now has strict immutable artifact parsing, a pure compiler and a trusted local promotion catalog. The compiler checks whole parameter domains, units/frames, exact dependency closures, caller-supplied keys and timing. Its 19 focused tests include six actual local Runtime procedures across three families and two installation aliases, with twelve child effects and effect-free replay; a fourth non-demo capability is compiled. Fan/inspection artifacts are reused across aliases; focus artifacts explicitly change calibrated-frame constraints.
- The [PAT execution proof](artifacts/verification/pat-execution-after/index.json) passes 23 tests with 41 relevant inputs unchanged. Six actual local procedures across three families/two aliases produce twelve child effects, then replay without additional effects. New instances pin selection inventory, registry/catalog revisions and evaluated bindings; process exits before/after the shared commit verify atomic identity. Scoped users need only their existing read/exact action grants; publication/promotion remain administrator operations. Source inspection preserves the original procedure transaction AST, and all 28 original procedure regressions pass.
- The registry-backed PAT binding provider passes eleven tests: actual installed rows and explicit semantics, full authorized inventory, missing registration/session refusal, exact qualification mapping and overflow without truncation. Busy resources and expired presence do not manufacture uniqueness. Compiler identity now includes catalog, routing and provider sources.
- The [independent PAT source review](artifacts/verification/pat-execution-review/README.md) pins twelve inputs and reads four complete files plus selected dependencies/tests: 2,488 LF lines across 25 chunks. It confirms the resolved typed-replay, authority-ordering, failed-provider filtering and inventory-provenance issues; it ran no runtime tests.
- Two reviewed pure components are now integrated: [simulation configuration and domain-case contracts](artifacts/implementation/pat-simulation-contracts/README.txt) supply 19 tests for exact applicability intersections, typed negative inputs, bounded generation and constant-program boundaries; [static environment extraction](artifacts/implementation/pat-environment-extraction/README.md) supplies 18 tests and preserved baseline-output comparisons. The stage receipts remain frozen. Normal repository tests consume only inventoried JSON data. All 126 combined PAT checks pass with 120 inputs unchanged; the new components make no qualification-success claim. The isolated worker and optional evidence hook are now integrated and covered by the current full run; retained qualification attempts and bounded evidence storage remain the next implementation.
- Sixteen focused catalog tests pass, including compiler/catalog environment-identity interoperability. [Twenty independent catalog tests](artifacts/verification/pat-catalog-review/review.json) pass with six abrupt-process phases, authority revocation, conflicting concurrent evaluation receipts, atomic promotion, revision exhaustion and dependency changes. New evidence suspends active entries; conflicting same-key results are retained and block promotion until a distinct evaluation. The evaluator fixtures are synthetic outcomes, not production qualification policies. The newer execution library now implements structured routing and durable linkage; public PAT projections remain absent.
- A read-only scope review clarified the [foundation's trust boundaries](docs/pat-foundation.md): driver/installation and evaluator identities come from trusted registrations, eligibility is checked on catalog calls, and retention of existing pinned instances is enforced by the separate execution library. Uncommitted evaluations have no durable in-flight record and can run again. The catalog itself does not manage instance lifecycle; the new execution store delegates it to the procedure engine.
- The latest [availability diagnosis](artifacts/verification/runtime-availability-diagnosis/README.md) pins the failed459 attempt and exact captured records. The focus request was refused before admission with `DEVICE_UNAVAILABLE`; two exact retries left counts at seven operations, zero claims and four compact commands, with no replay key. A later presence renewal cannot explain the earlier refusal. The exact decision-time presence row remains unknown, so no production scheduling defect or unique cause is asserted.
- The [failed522 observer diagnosis](artifacts/verification/runtime-522-observer-diagnosis/README.md) verifies 268 retained files, including all 112 before/after input pairs, 25 outputs and both failure captures. Both errors occur in SQLite observers before the affected prepare; the failed cases have zero admitted operations/procedures and zero effects. Separate successful transport cases remain distinct. Exact writer/lock ownership was not recorded, so this does not identify a production persistence defect.
- Four [deterministic availability probes](artifacts/verification/compact-availability-before/review.json) reproduce age loss during clock/publication commits and another route's service. The [new compact admission path](artifacts/verification/compact-admission-after/review.json) passes 25 targeted tests against 63 frozen inputs. It uses only a typed, statically authorized expiry, rechecks under the existing route/authority lock order, performs one HELLO without OP/ARM/BIND, then admits the exact request once. Retained replay and changed authority/identity/bounds do not refresh; prepare and procedure paths are unchanged. Arbitrary storage delays remain an availability limit.
- The [test-observer correction](artifacts/verification/endpoint-cli-observer/index.json) passes five focused tests in 24.586 seconds: four controlled read-only lock/error cases and the original three-scenario native CLI crash/reopen test. Each read has a three-second budget, retries only `SQLITE_BUSY`, and closes its connection; other SQL errors propagate. The actual scenarios complete with three total OP frames. This changes no production authority, operation identity, freshness or timing. Failed459 evidence remains frozen. The runner now retains this module's reports; its seven bookkeeping tests pass separately, without another full run.
- The subsequent [shared observer correction](artifacts/verification/shared-sqlite-observer/index.json) migrates all four live transport observers and combines admission counts/key presence into one SELECT. Five controlled tests pass; the nine-test transport run passes eight and fails one final freshness query in compact CLI, after that case's completion/replay checks. All 45 database reads succeed, with three BUSY retries. All 113 inputs remain unchanged during both runs. Missing raw evidence for that non-SQL assertion remains explicit; the later capture-only diagnostic below preserves a separate reproduction.
- The [expanded compact CLI failure capture](artifacts/verification/endpoint-cli-failure-capture/README.md) retains setup/test failures before cleanup, command timestamps, raw requests/relay/database records and process output. Three intentional diagnostic cases verify capture; an isolated fixture permission error remains separate. One unchanged actual diagnostic reproduces `OBSERVATION_STALE` after completion/replay with one OP. The later retained valid sample's age estimate crosses the unchanged ten-second bound during the final CLI call; this is not the exact service-read snapshot and does not reconstruct the earlier unretained failure.
- The [observation-semantics correction](artifacts/verification/endpoint-cli-observation-semantics/README.md) preserves that strict query and all operation/recovery bounds. Only an exact stale refusal can use a checked historical read, which must retain valid quality, known age above ten seconds and exact source/binding/value/acquisition identity. Seven focused checks pass with 113 inputs unchanged and three total OP frames. Their strict reads are all fresh. A separate [controlled aging run](artifacts/verification/endpoint-cli-aged-observation/README.md) waits eleven seconds once before the first final query, exercises exact stale refusal and historical age 18,777 ms, and still emits only three OPs. No production freshness rule or sample timestamp changed.

- The [local effect-boundary correction](docs/local-effect-boundary.md) retains the original four-case and extended six-case failing reproductions. Eleven focused corrected tests pass: fresh acquisition near boundaries, post-commit timing checks, a final veto inside the plant transaction, invalid/regressed clocks and rollback. Eighty existing local compatibility tests pass. Five procedure freshness tests distinguish qualified age expiry (defer with unchanged key/deadline) from unknown/invalid evidence or false predicates (refuse). These fixes do not retroactively explain the two first-run dispatch refusals whose event reasons were not retained.
- The subsequent [start-boundary correction](artifacts/verification/local-start-boundary-after/index.json) passes 22 start/freshness tests and a five-case before/after probe. The adapter checks current policy and timing after claim/plant transaction waits; explicit durable no-start evidence preserves replay identity and clears claims atomically. A start in time can finish after latest-start, within its original completion/run limits. Host SQLite checks do not establish hard real-time or physical guarantees.
- The final [23-test boundary proof](artifacts/verification/local-start-atomic-exclusion/index.json) adds an actual host crash immediately after the no-start journal commit. Inspection before recovery confirms zero claims and cleared `mayHaveActed`; reopen/replay preserves the result. This disproves the independent review's initial claim-release concern, which was retracted; no production change was needed for it.

- The [transport diagnosis](artifacts/verification/runtime-424-diagnosis/README.md) adds failure-only SQLite/event/request/relay/stderr retention. Five diagnostic self-checks pass. A separately pinned nine-test real CLI/MCP/IPC run passes in 169.271 s, with nine mixed scenarios/replays and no refusals, before the subsequent start-boundary correction; it does not explain unrecorded causes in the first failed run.
- The runtime checker now records every attempt in an immutable directory with before/after source copies, logs, actual traces and an explicit [current-attempt pointer](artifacts/verification/local-runtime-current.json). Seven isolated bookkeeping tests pass. Skipped/expected-failing tests, source inventory changes and compiler identity changes prevent success publication. The legacy failed424 archive explicitly has no pre-run input-stability proof. The failed459 and failed522 attempts have complete stable before/after snapshots; the original369 success remains historical.

## Verification actually run

| Command/check | Observed result | What it establishes |
|---|---|---|
| `python3 scripts/audit_corpus.py` | 2,251 hash assertions across 1,494 distinct files, 644 coverage chunks and 25 repository/commit pins; [current report](artifacts/verification/corpus-authorizer-audit.json) | Adds two fully read SQLite authorizer API bodies (136 LF lines, all 33 action-code rows) to the retained Q-Block, Voyager and LRLL work; acquisition and reading remain separate. Original corpus reports and source pins remain preserved |
| `python3 scripts/check_descriptions.py` | 3 examples passed | Exploratory shape, reference, unit and bounds checks |
| `python3 scripts/check_wot_profile.py` | 3 fixtures passed | Pinned informative TD schema plus selected HMS static checks; no normative/runtime conformance |
| `python3 scripts/check_runtime.py` | **748 tests pass**, zero failures/errors/skips, 761.283 s; [immutable receipt](artifacts/verification/runtime-attempts/20261107T014321.791506Z-b4b2085264e7/receipt.json) and [log](artifacts/verification/runtime-attempts/20261107T014321.791506Z-b4b2085264e7/outputs/local-runtime-tests.txt). All 151 inputs and compiler identity unchanged | Adds 24 I/O provider, 9 runtime/profile, 14 typed-result and 5 real I/O transport tests to the 696-test baseline. Both MCP modes exercise all 14 tools with 32 validated I/O replies each. Controlled status-read loss preserves IDs/effects; SIGKILL/reopen preserves activation truth. All 228 observer reads succeed with 12 BUSY retries, including 174 I/O reads with zero retries. Synthetic scope only |
| Current evidence-library integration | [46 tests pass](artifacts/verification/pat-evidence-live-integration/index.json), with 131 copied inputs unchanged; both attempts and three retention checks preserved | Fresh original worker outputs, actual catalog/instance gate, bounded evidence and receipt integrity; no installed qualification service |
| Pure topology integration | [21 tests pass](artifacts/verification/resource-topology-integration/index.json) | Bounded typed graphs, alias footprints and all-action lifecycle exclusion; no I/O effects |
| Live resource-admission integration | [32 tests pass](artifacts/verification/resource-admission-live-integration/index.json), 140 inputs stable, 88.594 s harness | Current Registry/catalog, bounded storage reads, exact inventory and original scalar-type refusals. Retains five failing-before storage methods and one scalar regression; no provider mounting |
| Live evidence-memo integration | [77 tests pass](artifacts/verification/pat-memo-live-integration/index.json), 139 inputs stable, 138.448 s | Includes 19 memo tests, real current worker output, cold/ambiguity/exact replay and corrected compiler resource identity. Retains two failing-before identity regressions; no public service or latency guarantee |
| Historical resource-admission stage | [26 tests pass](artifacts/implementation/io-resource-admission/index.json), 21 copied inputs stable | Original copied Journal/Registry admission proof before live storage-read and scalar compatibility corrections; no provider execution |
| Historical evidence-memo stage | [17 tests pass](artifacts/implementation/pat-evidence-fast-verification/index.json), 443 copied inputs stable | Original memo proof and benchmark against historical worker data; later integration is separate |
| Separate synthetic I/O provider stage | [24 tests pass](artifacts/implementation/io-synthetic-provider/index.json), 54 copied inputs/packages stable | Shared board GPIO/PWM effects, receipt/recovery and cross-route ownership; pre-hardening copied resource catalog, no live mounting, physical or driver lifecycle qualification |
| Current-baseline copied I/O provider | [24 tests pass](artifacts/verification/io-provider-current-integration/index.json), 146 copied inputs, compiler/provider identity and runner stable | Six unchanged reviewed provider modules on the exact 139-input full696 baseline, plus the copied state-path allowance and current test helper; no live or public mounting |
| Public shared-board I/O integration | [Focused family](artifacts/verification/io-provider-runtime-integration/index.json) retains failed37, failed52 and passing4 attempts; [status recovery](artifacts/verification/io-status-read-timeout-resolution/index.json) retains failing1 and passing5 attempts | Explicit CLI/UDS/MCP mounting, typed activation/cycle/idle results, shared alias claims, exact replay and stale-session resume refusal. Only status-read test polling retries; production requests and bounds unchanged |
| Lifecycle source and harness preparation | [13 bookkeeping probes pass](artifacts/verification/io-lifecycle-harness-probes/results/corrected-attempt01/index.json); [corrected single admission test passes](artifacts/verification/io-lifecycle-admission-smoke/attempt02-corrected/index.json), 156 copied and 159 selected external inputs stable | Preserves four earlier bookkeeping assertion failures and the unsafe-ancestry setup error. Explicit dependency pins and private `/tmp` scratch correct the harness; production pathname policy is unchanged. One admitted operation holds five claims and blocks administrative publication; no dispatch or generation effect. Public lifecycle support remains unfinished |
| Separate fixed-unit compiler stage | [34 pure tests pass](artifacts/implementation/pat-fixed-schema-units/results/pure34-01/index.json), 152 copied inputs and 159 selected external pins stable | Explicit numeric unit profile, exact semantics and full-domain validation; legacy validation preserved. Runtime method excluded; no live integration, trusted I/O registration or qualification. Compiler's own dependency identity scope is unchanged |
| Isolated lifecycle regression attempts | [44 methods: 43 pass, 1 error](artifacts/verification/io-lifecycle-regression-composition/source01/attempts/attempt03-lifecycle30-api14/result.json), followed by [corrected focused1 pass](artifacts/verification/io-lifecycle-exception-correction/results/attempt01-focused/index.json); each has 156 copied and 159 selected external inputs stable | Failed44 preserves the wrong exception expectation; its grant half was unreached. The corrected method checks exact ARGUMENT_SCHEMA_MISMATCH and then proves ordinary grants cannot authorize management, with no operation/claim created. Production unchanged; broader shared-code acceptance and public lifecycle mounting remain open |
| Shared lifecycle regression | [160 methods: 159 pass, 1 failure](artifacts/verification/io-lifecycle-shared-regression-results/attempt01-failed/index.json), followed by [corrected structural1 pass](artifacts/verification/io-lifecycle-shared-regression-results/attempt02-structural-only/index.json) | All 30 lifecycle methods pass in the failed160 attempt; two subprocess methods excluded and captures cover lifecycle/provider cases only. Corrected AST check preserves complete wrappers and composed original body. No clean full160 rerun or public lifecycle mount |
| Partial lifecycle setup profile gate | [Reproduced failure](artifacts/verification/io-lifecycle-partial-setup-results/attempt02-reproduced/index.json), [matching after-case1 pass](artifacts/verification/io-lifecycle-partial-setup-results/attempt03-after-gate/index.json), then [ordinary5 pass](artifacts/verification/io-lifecycle-partial-setup-results/attempt04-ordinary-five/index.json) | Isolated source11 refuses wrong-profile board creation and preserves exact lifecycle setup recovery plus ordinary creation/reopen behavior; 156 copied/159 external pins stable. Earlier fixture failure preserved; no live integration, old-source migration or physical control |
| Additional lifecycle boundaries | [3 tests pass](artifacts/verification/io-lifecycle-boundary-results/attempt01-three-root-retention/index.json), 156 copied/159 external inputs stable, nine logical snapshots | Direct driver scope and replay, unused-service change preserving real ordinary history, literal revision-ceiling refusal. Root retained all 215 attempt files and inspected only acquired DB copies; no final independent result-review seal, physical effects or true historical exhaustion |
| Trusted I/O PAT resolver candidate | [29 methods: 28 pass, 1 fixture failure](artifacts/implementation/pat-io-binding-resolver/results/resolver29-01/index.json), then [corrected focused1 pass](artifacts/implementation/pat-io-binding-resolver/results/focused-purity-01/index.json); 155 copied/159 external pins stable in both | Complete installed inventory and exact metadata cases pass; the corrected method reaches all original selection-purity guards/assertions. 33 states captured before, one after. Historical failed29 retained; no clean29 rerun, I/O qualification or live integration |
| Driver/service lifecycle design review | [Amended design reviewed](artifacts/verification/io-lifecycle-settlement-review/review.json), no remaining blocking contradiction found in that design scope | Exact claims through atomic generation/binding/terminal settlement; preserve current disabled state and historical receipts. Actual isolated execution results appear separately above; boundary acceptance remains open |
| Separate qualification supervisor stage | [19 tests pass](artifacts/implementation/pat-qualification-supervisor/index.json), 54 copied and 139 selected external inputs stable | Exact attempt/lease/archive recovery, real process crashes, pidfd/deadline and closed-record checks. Historical643 worker source; no current qualification, hard aggregate quota or service mounting |
| `python3 scripts/check_serial_native.py` | 1,000,086 synthetic input bytes; 3 exact expected frames recovered; ASan/UBSan clean; host parser size 220 bytes | Native original-code memory/undefined-behavior check; UART and total MCU resources are outside this check |
| `python3 scripts/check_serial_avr.py --toolchain-bin …` | Original ATmega328P component links: 558 B flash, 221 B static RAM, parser 219 B | Explicit physical memory bounds and retained ELF/map/disassembly/stack reports; no execution, full firmware or timing claim |
| `python3 scripts/check_host_journal.py` | 33 historical host tests retained; current variants included in the 369-test suite | Four durable-boundary process crashes and six interrupted transactions with on-disk rollback journals; no storage-power-loss or physical test |
| Independent host parser/journal reviews | 78,832 numeric and 4 complete-intent Python/Node comparisons; 32 admission contenders; 40 dispatch/cancel races; regression fixes verified | Scoped implementation evidence, with exact source hashes and probe methods in review artifacts |
| Registry independent review | 17 adversarial tests passed; 12 findings resolved | Exact tested historical hashes retained; later complete suite checks current integration |
| Simulator independent review | 21 tests passed; four findings resolved | Primitive bounds, session/fence checks, exclusive owner, atomic rollback, process exits and receipt persistence |
| Runtime integration | 19 direct integration tests plus 3 real CLI/daemon scenarios; 16 IPC tests | Four combined-runtime abrupt-exit phases, same-key restart replay, revocation, clock failures, cancellation, transport bounds and persisted effect counts |
| Independent checked-API/state-path reviews | 20 API and 14 state-path tests passed | Exact scoped receipts retained; final full suite checks current compact-host integration |
| Native Harness overlay baseline | 16 tests, seven artifact stages and three aggregate checks passed at `a1626788…`; [verification](integration/harness/revalidation-a1626788/verification.json) pins the archived 280-test runtime | Real native/PTC/AgentLoop, compact C and SDK/profile calls; earlier intermittent availability refusal remains unresolved; release and interrupted-work persistence incomplete |
| Historical Harness with installed support | One run passes 16/16, zero skips; [receipt](integration/harness/installed-support/verification.json) | Frozen 289-test HMS snapshot, six compact C scenarios and three QUERY-only crash recoveries; unchanged overlay/build reuse with 14,406 built files pinned before/after, inherited availability caveat |
| Historical 315-test native Harness regression | One run passes 16/16, zero skips, plus focused lint and three aggregate checks; [receipt](integration/harness/multi-adapter/verification.json) | Frozen 315-test runtime, 35 HMS inputs/47 fixture files, 39 overlay/test inputs, six C completions, three QUERY-only recoveries and 14,406 stable built files. Single-route primitive flows; does not validate later procedure implementation |
| Local MCP compatibility | 10 modern protocol/daemon tests and nine independent boundary tests pass; [archived legacy SDK receipt](artifacts/verification/mcp-sdk-compact-host.json) passes three simulated scenarios and 39 replies | Current full suite checks modern/legacy compact interoperability; the separate 39-reply SQLite SDK receipt predates installed-support changes; retained-request replay across projection/daemon restart; no physical or remote MCP claim |
| `python3 -I -B scripts/check_endpoint_vectors.py` | 41 independent frame/FCS checks, 13 response layouts and two intent mappings pass; [current layout receipt](artifacts/verification/endpoint-current-layout-result.json) | Layout/digest consistency only; actual endpoint behavior is checked separately by native and framed-process suites; fixture declarations are not themselves execution evidence |
| `python3 scripts/check_endpoint_native.py` | 26 cases, 2,548 assertions and 20,000 malformed inputs; ASan/UBSan clean; [receipt](artifacts/verification/endpoint-native.json) | Original C executor/link and synthetic callbacks, including exact admission/replay, deadlines, cancellation, reset and fault handling; no target/physical execution |
| Independent endpoint code review | 16 C sanitizer probes and 18 Python packet tests pass; [source snapshots and receipt](artifacts/verification/endpoint-code-review/endpoint-code-review.json) | Scoped independent findings and repairs; no physical clock, NVM, quiescence or stop qualification |
| `python3 scripts/check_endpoint_integration.py` | 13 real framed-process scenarios pass; [receipt](artifacts/verification/endpoint-integration.json) | Python/C correlation, lost-reply query, cancellation races, expiry, reset uncertainty, malformed evidence and callback overrun; exact native source/binary provenance, no host journal binding |
| `python3 scripts/check_endpoint_scenarios.py` | 15 actual framed scenarios pass in both plain and ASan/UBSan builds; [receipt](artifacts/verification/endpoint-scenarios.json) | Installed three-scenario C callbacks, UTF-8 bounds, counts, cancellation, reset and faults; no host authority or physical proof by this checker alone |
| Modern/legacy compact MCP | Two tests pass six scenario executions and 81 schema-validated replies; [receipt](artifacts/verification/compact-mcp/verification.json) | Historical 280-test transcript: actual C backend, same-reference QUERY recovery, exact OP counts and explicit cancellation. Current full suite reruns the flows with current code and a corrected current-status response assertion; no physical effect proof |
| Finite boot reservations | 11 native cases / 311,973 assertions per build; 546,374 independent assertions; [receipt](artifacts/verification/boot-epoch.json) | Explicit stable-cell/target-only-torn-write model, retained rollback counterexample, AVR object build; no qualified physical storage |
| AVR EEPROM callbacks | 12 cases / 25,948 assertions per native build, AVR cross-link and three negative instruction checks; [receipt](artifacts/verification/avr-eeprom/review.json) | Original register model, exact write-launch disassembly and bounded polling; no MCU execution or electrical qualification |
| AVR receive boundary | Twelve cases / 435,502 assertions per host build; independent 13,418 checks per build and five rejected regressions; [producer](artifacts/verification/avr-uart/review.json), [review](artifacts/verification/avr-uart-review/review.json) | Status-before-data, sticky continuity gate, atomic parser-reset acknowledgment and saved interrupt state; isolated AVR probe 1,142 B flash / 267 B static SRAM, no target execution or combined-firmware fit claim |
| Installed adapter support | Nine regressions in the full suite plus five [independent real-C probes](artifacts/verification/installed-support-review/review.json) pass | The independent receipt is scoped to the frozen 289-test runtime; its nine regression cases remain in the current suite. New coexistence evidence is separate |
| Multi-adapter routing | 26 new regressions in the 315-test suite, plus nine independent cases and nine isolated real-clock scenarios; [review](artifacts/verification/multi-adapter-code-review/review.json) | Exact catalog, two native endpoints plus local plant, historical routing, shared fences, faults, offline replay, migration, snapshot rollback and sample age; shared mutex/storage/host load remain availability limits. [Retry supplement](artifacts/verification/multi-adapter-code-review/cli-retry-supplement/review.json) is static review only |
| Compact host/CLI binding | 11 binding + 11 Journal + 14 independent review tests and all three real CLI SIGKILL/reopen scenarios pass; [host traces](artifacts/verification/compact-host-traces.json) | Exact dispatch mapping, no automatic OP replay, receipt continuity, full host/local fence mapping, conservative clock/sample age, lost BIND/ARM/RETIRE replies and disputed evidence; independent native effect/frame counts |
| `python3 scripts/check_endpoint_avr.py --toolchain-bin …` | 15,780 B flash, 1,335 B static SRAM, conservative foreground stack 231 B; [receipt](artifacts/verification/endpoint-avr.json) | Exact compiler/link/callback graph plus explicit planning reservations, no executed target or measured runtime fit |
| `python3 scripts/audit_endpoint_evidence.py` | **Passed: 63,484 hash assertions, 45,387 unique files**; [receipt](artifacts/verification/endpoint-evidence-audit.json) and [retained audit attempt](artifacts/verification/runtime-748-audit/20261107T015809.359107Z-65acc626a51a/index.json) | Current748 source/output closure, public I/O focused failures/passes and bounded status-read correction, historical696 supervisor rebase, unexecuted lifecycle snapshots03–05, and earlier archives. Historical source mappings remain exact; current source equality stays mandatory. Hash consistency is not a test rerun or physical validation |
| `python3 scripts/check_project_links.py` | **152 selected Markdown files, zero missing paths**; [report](artifacts/verification/project-links.json) | Project-authored local path links only; no remote URL, anchor or archived upstream link validation |
| Failed459 retained-byte check | [231 hash assertions pass](artifacts/verification/runtime-459-retention/result.json), covering 107 before/after inputs, 15 outputs and receipt lineage | Preserves the failed attempt without treating retention integrity as a successful test run or equivalence to subsequently changed sources |
| `python3 scripts/benchmark_local.py` | Raw 20-sample warm read sets and 5 cold CLI samples retained | [Historical single-route read paths](docs/local-performance.md); no current multi-route performance, physical timing, qualified tails or universal performance claim |
| `python3 research/embedded/verify.py` | 35 complete file records and 4 clean pinned checkouts verified | Static source/coverage integrity; no third-party execution |
| Local project Markdown link inspection | [Selected local-path check](artifacts/verification/project-links.json) passes with no missing targets | Root/docs/spec/research-plan plus integration, endpoint, MCP, constrained and microscopy navigation; upstream source/snapshot links excluded |
| Earlier MHS extraction reproduction | 243 unique content fields and matching content hash | Recoverable article-text extraction; not video coverage |

The corpus auditor now includes laboratory and constrained sources, embedded file coverage, unique repository pins, WoT ancillary artifacts and full-reading overlays. It checks hashed contiguous LF-based ranges where supplied. It caught terminal formfeed omissions and a splitlines-based line-count error; records were corrected after inspecting the source bytes. Acquisition manifests retain their original reading statuses; later receipts explicitly supersede them.

The fixture review removed reliance on an unmapped `additionalProperties` keyword in TD, added input units and a draft motion frame, restricted recipe IDs to integers, and made the TD schema hash pin executable. A separate consistency review caught write forms on read-only properties and scalar inputs disguised by object-schema keywords; the checker now rejects both and pins the draft root context. Strict request validation remains a separate HMS execution-contract obligation.

The local simulation path runs through actual CLI processes, Unix sockets and native/PTC Harness calls in an isolated checkout. No real device, live model inference, target binary or physical scenario has run. The native endpoint is connected to durable host authority through an explicitly synthetic same-host clock profile and a launcher-owned Unix stream; SQLite plants and compact endpoints can now coexist under an explicit stored catalog. Local read timing samples and synthetic fault tests do not complete the conformance matrix. Research controllers/planners remain unexecuted; the user-owned Harness, reviewed JCS dependency and official AVR compiler tools are intentionally used for development. Independent bounded stop, remote/per-agent authority, physical commissioning, actual-device fencing/leases and qualified synchronized clocks remain unfinished. General PAT control-flow/data-reference/stream contracts, process isolation and qualified shared-authority scheduling, quotas, retention and production Harness packaging/persistence gates are also pending.

## Requirement-by-requirement audit

| Original requirement | Present evidence | Completion decision and remaining work |
|---|---|---|
| 1. Extensive articles/papers/NVIDIA/best practices | Expanded corpus, full protocol/VLA reviews and laboratory critique | Incomplete: continue search matrix, bibliography expansion and full reading |
| 2. Universal protocol/runtime/tool manager/registry, fast execution | Local registry/admission/dispatcher, checked API/SDK, native tool overlay and scoped read timings | Incomplete: broader contracts, remote/per-agent authority, isolated adapters, stop path and deployment-scale measurements |
| 3. Microscope knob devices | Retrofit design, exact controller/imaging/autofocus source review and workflow constraints | Incomplete: actual microscope constraints, mechanical/electrical design, firmware and commissioning |
| 4. Broad processors; on-device and GB10 hub agents | Deployment profiles, GB10 source review, model/controller contracts and AVR endpoint/EEPROM cross-build evidence | Incomplete: qualified platform layers, real firmware/MCU/SBC/hub builds and measured behavior |
| 5. Physical-AI architectures/use cases and critique | Architecture taxonomy, full VLA and SayCan/CaP critiques, workflow/material model | Incomplete: wider planning/control/scientific/industrial literature and integration review |
| 6. Foundational tool analogous to bash | Executable local `hctl`, checked Python client, native/PTC tools and local MCP projection | Incomplete: portable adapters, watch and general PAT/procedure surface, broader MCP client/remote coverage, finished agent packaging and coverage/ergonomics evaluation; no universal preinstalled shell found |
| 7. Download/read fully with notes/thinking | Local raw/text sources, pins, hashes, exact reading receipts and critique | Incomplete: remaining standards, source files, linked works/media and recorded access gaps |
| 8. Evidence-derived standard/protocol/system structure | Working spec, WoT choice, host identity/journal and formal local request/result contracts | Incomplete: stable vocabulary, general PAT/stream/data-reference contracts, remote bindings and full conformance |
| 9. Arduino dynamic control through complex systems | Fixed-storage endpoint executor, 13 framed-process scenarios, Firmata/rclc/core review and AVR endpoint cross-link | Incomplete: physical binding qualification, qualified boot/clock, integrated UART TX/RX and interrupt timing, installed physical primitives, firmware/adapters and timing evidence |
| 10. Home/scientific/manufacturing scenarios | Three detailed designs plus local/compact synthetic coexistence and primitive traces | Incomplete: general PAT workflows beyond tested ordered synthetic procedures, imaging/material lineage, manual override and physical validation |
| Added requirement: prompt-to-PAT learning and deterministic routine execution | Typed compiler/catalog/router and atomic instances; finite fan worker, evidence store/memo and catalog gate; separately tested durable supervisor; checked procedures | Incomplete: enforced storage, fixed service configuration/public mounting, public PAT tools, agent synthesis, trace learning, persistent applications and reuse/novelty handling on actual targets |
| Added requirement: control device I/O, drivers and optional intelligence hub | Unified resource graph; persistent admission and explicit shared GPIO/PWM board mounted through the public tools; staged lifecycle source reviews | Incomplete: actual target/OS providers, qualified admitted lifecycle effects/reconciliation, public lifecycle results, streams/compute resources and combined-load measurements |

The evidence does not satisfy the completion audit. Leave the goal active. Missing microscope particulars do not block research or software work; the earlier text clarification about microscope model, target knobs and selected components remains pending.

## Next work in order

The new PAT and I/O/driver/hub requirements extend items 2–5 below. Implement and
evaluate the full prompt → contextual plan → durable execution → evidence → PAT
promotion → deterministic reuse path. Extend resource management across device
I/O and hub services, retaining explicit target support and dependency changes.

The next concrete implementation continues the
[PAT design review](artifacts/verification/pat-design-review/DESIGN.txt) after the
new typed compiler/catalog, deterministic router and atomic instance libraries:
implement the [trusted simulation qualification and service configuration plan](artifacts/verification/pat-service-design/PLAN.md) with its [required review corrections](artifacts/verification/pat-service-review/README.md), followed by checked PAT CLI/MCP
methods and native Harness integration, then the synthesis/learning loop. The narrow fan policy, actual isolated worker and bounded retained evidence now exist as host libraries. The reviewed memo is integrated as a library. Connect fixed trusted configuration, enforced aggregate storage, current-source worker reconstruction, serialized evidence import, memo capacity and durable supervision before exposing qualification. Preserve missing/corrupt/cold evidence as unavailable rather than removing candidates. The resource catalog now supports the finite synthetic I/O provider; finish receipt-gated lifecycle settlement and its public result contract, then add explicit target providers. Synthetic passing fixtures are not a deployment policy. Physical/production qualification remains separate. The review's 44 cases remain a design checklist,
not a claim that every case is covered by the new tests. Selection
predicates, runtime/effect guards and outcome checks are separate contracts;
dynamic or sustained guards need actual enforcement before that profile can be
accepted. Persistent Arduino event/controller applications remain required after
the finite sequence foundation.

1. Continue the primary-source queue in [research/PLAN.md](research/PLAN.md), especially current constrained transport/security, industrial/instrumentation models, planning and newer learned-control systems. Trace the actual relevant implementation paths and preserve conflicting evidence.
2. Extend the implemented immutable installed-route catalog beyond the demonstrated three primitive families and two synthetic drivers. Qualify refresh/load availability and contain adapter failures outside the shared authority process, preserving route-scoped queues, faults, mappings, evidence and recovery. Extend the checked ordered-procedure API with reusable PAT, data-reference and stream/gap contracts and a stable vocabulary. Extend the implemented synthetic compact host mapping/recovery to qualified physical clock/transport profiles; finish explicit feature negotiation.
3. Extend the local simulated registry and supervised dispatcher into physical commissioning, general bounded programs and isolated adapters. Add independent stop-under-log-failure, device fencing, qualified clocks and actual-adapter crash tests. Preserve the current conservative receipt and replay behavior.
4. Create a new standalone clone for Harness work, using the frozen `a1626788` revalidation as evidence without modifying its audited tree or the adjacent live checkout. Work toward release/package acceptance and interrupted-work/production persistence; extend the now-tested native Harness/MCP compact path to outer admission-reply loss, in-flight framework cancellation and production adapter deployment. Broaden the local MCP projection and add a lower-overhead native client path while preserving the checked CLI/SDK semantics.
5. Implement qualified platform layers and installed drivers for AVR-class and modern MCU targets, then measure target behavior and extend controller/domain bindings with an explicit support/evidence matrix.
6. Commission the microscope once hardware constraints are known; run the three scenarios, measure latency/resources and complete physical/conformance review.

A passing simulation, valid description or one supported board cannot stand in for the full goal or physical validation.
