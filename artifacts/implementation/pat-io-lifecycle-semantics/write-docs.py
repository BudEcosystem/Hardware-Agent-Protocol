"""Reconcile complete lifecycle evidence after acquiring failed57 and passing58."""
import hashlib,json
from pathlib import Path
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-lifecycle-semantics';R=B/'results'
def read(p):return json.loads(p.read_bytes())
f=read(R/'attempt01-failed57/proof.json');p=read(R/'attempt02-passed58/proof.json')
assert f['counts']==dict(testsRun=57,failures=0,errors=7,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert p['status']=='passed' and p['counts']==dict(testsRun=58,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
for proof in (f,p):
 assert proof['sourceFilesVerified']==7755 and proof['frozenFilesVerified']==7758 and proof['externalPinsVerified']==159
 assert proof['rawScratchFiles']==proof['rawScratchBytes']==proof['sqliteConnections']==0
for label in ('compiler','driver'):
 assert read(R/'attempt01-failed57/attempt'/(label+'-before.json'))==read(R/'attempt02-passed58/attempt'/(label+'-before.json'))
for name,proof,title,source in [('attempt01-failed57',f,'Original 57:50 pass and7 adversarial construction errors','implementation01'),('attempt02-passed58',p,'Corrected 58:all 58 methods pass','implementation02')]:
 with (R/name/'README.md').open('x')as stream:stream.write('# '+title+'\n\n'+
  'Test time: '+str(proof['testSeconds'])+' seconds; elapsed: '+format(proof['elapsedSeconds'],'.3f')+' seconds.\n'+
  'See the [complete attempt](attempt/result.json), [acquisition proof](proof.json),\n'+
  '[stage results](../README.md), [diagnosis](../../DIAGNOSIS.json) and\n'+
  '[frozen source](../../'+source+'/README.md).\n\n'+
  'All 7,755 project inputs, 7,758 frozen entries, six active harness inputs and\n'+
  '159 external pins remain stable. Every actual import and compiler/driver\n'+
  'identity matches. The complete '+str(proof['attemptFilesAcquired'])+'-file attempt and empty original scratch at\n'+
  '`'+proof['rawScratch']['path']+'` are retained.\n'+
  'SQL, network and subprocess operations are forbidden; no physical/MCU,\n'+
  'inference or live-service execution occurs. Original 180-second, 16 MiB and\n'+
  '8,192-file limits remain unchanged. This does not qualify a current PAT group.\n')
with (R/'README.md').open('x')as stream:stream.write('''# Complete lifecycle histories: 58 tests pass

The [corrected test selection](attempt02-passed58/README.md) passes all 58 methods
in '''+str(p['testSeconds'])+''' test seconds. The production checker is unchanged from
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
''')
pth=ROOT/'PROGRESS.md';s=pth.read_text();mark='The separate [qualification supervisor rebase]';assert s.count(mark)==1
addition='''The [complete lifecycle-history composition](artifacts/implementation/pat-io-lifecycle-semantics/results/README.md)
now passes **58 pure methods** and independently checks all 20 retained lifecycle
captures,292 paired checkpoints and 720 produced samples. Trusted faults/grants,
exact requests and configuration decisions, receipt/effect/owner/fence histories,
child/parent events, observations and returned results are composed. Unknown
outcomes retain claims until exact historical reconciliation. Accepted restart has
no handoff; pending owner reopen stops the historical receipt; completion loss
cannot erase a completed effect or satisfy an unfinished two-step PAT. All eighteen
children settle, with twelve activations,four completed cycles,eight cancellations
and no final unresolved work. Only post-completion single-step withdrawal satisfies
its entire completion objective.

The retained failed57 has 50 passes and 7 adversarial construction errors; all 20
actual-history positives passed. A test-only correction reconstructs typed,
deduplicated pages and paired references, and moves malicious changes after
lowering. All seven cases still require partial transcript success before full
semantic refusal. One added six-case no-op byte check brings the passing total
to58. Production and7,754 other project inputs are unchanged; no rule or limit
was weakened. Both complete attempts and empty raw scratch roots are retained.
All7,755 project inputs, 7,758 frozen entries, six active harness inputs and 159
external pins remain stable in each attempt; all imports and compiler/driver
identities match, including both identities across attempts. SQL/network/subprocess
execution is forbidden. Original 180-second, 16 MiB and8,192-file bounds remain.
The explicit fixture closure excludes 3,013 old files and adds 2,665 lifecycle files,
while original archives remain immutable. Live HMS and the adjacent Harness are
unchanged; review is by the primary agent.

All 25 fixed challenges now have staged capture/outcome components. The
current-candidate matrix, source/configuration attestation, actual aggregate
budgets, public qualification, automatic PAT learning/promotion and real device,
driver and hub control remain unfinished.

'''
for a,z in {'all 20':'all 20','captures,292':'captures, 292','and 720':'and 720','activations,four':'activations, four','cycles,eight':'cycles, eight','has50':'has 50','and7 ':'and 7 ','to58':'to 58','and7,754':'and 7,754','All7,755':'All 7,755','inputs, 7,758':'inputs, 7,758','entries, six':'entries, six','and 159':'and 159','180-second, 16':'180-second, 16','and8,192':'and 8,192','excludes 3,013':'excludes 3,013','adds 2,665':'adds 2,665','All 25':'All 25'}.items():addition=addition.replace(a,z)
s=s.replace(mark,addition+mark);pth.write_text(s)
pth=ROOT/'docs/prompt-to-pat.md';s=pth.read_text();mark='An operator says, for example,';assert s.count(mark)==1
s=s.replace(mark,'''The [complete lifecycle-history checker](../artifacts/implementation/pat-io-lifecycle-semantics/results/README.md)
passes 58 pure methods and independently validates all twenty of those captures.
It distinguishes correct fault response from completion of the entire PAT, retains
claims through uncertain effects and verifies historical reconciliation without
rebinding. All named fixed challenges now have staged capture/outcome
components; current-candidate group qualification, aggregate enforcement,
attestation and automatic learning/promotion remain unfinished.

'''+mark);pth.write_text(s)
pth=ROOT/'docs/io-driver-hub-control.md';s=pth.read_text();s+='''
The [complete lifecycle-history composition](../artifacts/implementation/pat-io-lifecycle-semantics/results/README.md)
passes 58 pure methods. It independently checks all twenty lifecycle captures,
including uncertain effects, retained claims, original requests across restart,
historical completion, permission changes and final settlement. All 292 paired
checkpoints and 720 produced samples are checked. Correct cancellation is
separate from completing a PAT. These are synthetic fixed-case results; current
candidate group qualification, aggregate quotas and actual device/driver/hub
management remain unfinished.
''';pth.write_text(s)
pth=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md';s=pth.read_text()
s=s.replace('Complete independent semantic/outcome composition and current-candidate group execution remain',
 'The [complete lifecycle composition](../pat-io-lifecycle-semantics/results/README.md) passes 58 pure methods and checks all 20 captured lifecycle histories independently. Current-candidate group execution with attestation and actual aggregate bounds remains')
s=s.replace('Compose complete independent outcome checks, then execute required variants on the actual candidate/environment in one group;',
 'The [complete lifecycle composition](../pat-io-lifecycle-semantics/results/README.md) now checks exact independent outcomes and unknown/fault causes in these fixed histories. Execute required variants on the actual candidate/environment in one group;')
s=s.replace('The\nnext implementation continues the remaining phase-engine extensions, followed\nby fresh candidate trials, group budget enforcement and independent expected-outcome\nreduction.',
 'All 25 named fixed challenges now have staged capture and independent\noutcome components. The next implementation binds them to exact current-candidate\ngroup execution, closes the current identity scope and enforces aggregate budgets\nbefore any public qualification or promotion decision.')
s=s.replace('The closed combined matrix and preflight now exist as an isolated library. All 25 named fixed challenges now have staged capture and independent\noutcome components.', 'The closed combined matrix and preflight now exist as an isolated library.\nAll 25 named fixed challenges now have staged capture and independent outcome\ncomponents.')
s=s.replace('before any public qualification or promotion decision. The planner separates candidate executions from fixed provider/authority\nchallenges,','before any public qualification or promotion decision. The planner separates\ncandidate executions from fixed provider/authority challenges,')
s=s.replace('count that exceeds the original limits. Its passing planning tests do not establish\nthat the present engine can execute all of those challenges or fit actual evidence\nand wall-time limits.','count that exceeds the original limits. These components have not yet executed\nas one exact current-candidate group or demonstrated compliance with its actual\naggregate evidence and wall-time limits.')
pth.write_text(s)
pth=ROOT/'scripts/check_project_links.py';s=pth.read_text();mark="        ROOT/'artifacts/implementation/pat-io-lifecycle-challenges/DESIGN.md',";assert s.count(mark)==1
paths=['DESIGN.md','implementation01/README.md','implementation02/README.md','harness01/README.md','harness01/SCOPE.md',
 'harness02/README.md','harness02/SCOPE.md','results/README.md','results/attempt01-failed57/README.md','results/attempt02-passed58/README.md']
s=s.replace(mark,''.join("        ROOT/'artifacts/implementation/pat-io-lifecycle-semantics/"+v+"',\n"for v in paths)+mark);pth.write_text(s)
print(json.dumps(dict(passingMethods=58,retainedFailedMethods=57,captures=20,checkpoints=292,samples=720)))
