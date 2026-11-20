"""Reconcile prose only after every exact lifecycle selection and JSON audit pass."""
import json
from pathlib import Path
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-lifecycle-challenges';R=B/'results'
specs=[('attempt01-passed6',6,'GPIO cancellation, restart and completion loss'),
 ('attempt02-passed5',5,'PWM cancellation, restart and completion loss'),
 ('attempt03-passed5',5,'GPIO pending loss and retained-read withdrawal'),
 ('attempt04-passed5',5,'PWM pending loss and retained-read withdrawal')]
proofs=[]
for name,count,title in specs:
 p=json.loads((R/name/'proof.json').read_bytes());proofs.append(p)
 assert p['status']=='passed' and p['counts']==dict(testsRun=count,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
 assert p['sourceIndexSha256']=='0a3360ba3a6e9ee0fd5c9db8d8a38ef64761b9bda69969fae42264e4556c2e87'
 with (R/name/'README.md').open('x')as f:f.write('# '+title+'\n\n'+
  str(count)+' exact methods pass in '+str(p['testSeconds'])+' test seconds ('+format(p['elapsedSeconds'],'.3f')+' elapsed).\n'+
  'There are no failures, errors, skips or expected failures. See the\n'+
  '[complete attempt](attempt/result.json), [acquisition proof](proof.json),\n'+
  '[stage results](../README.md) and [frozen source](../../implementation01/README.md).\n\n'+
  'All 8,101 project inputs, 8,104 frozen entries and 159 external pins remain\n'+
  'stable, together with actual imports and compiler/driver identities. The\n'+
  str(p['attemptFilesAcquired'])+'-file attempt and original raw scratch at\n`'+p['rawScratch']['path']+'` are retained.\n'+
  'Scratch contains '+str(p['rawScratchFiles'])+' files / '+str(p['rawScratchBytes'])+' bytes.\n'+
  'Original 180-second, 16 MiB and 8,192-input-file limits remain unchanged.\n\n'+
  'These synthetic captures and partial request/schedule checks do not establish\n'+
  'complete independent outcome validation, candidate qualification, physical\n'+
  'control or actual group budget enforcement.\n')
audit=json.loads((R/'data-audit.json').read_bytes());t=audit['totals'];assert len(audit['cases'])==20
rows='\n'.join('| ['+title+']('+name+'/README.md) | '+str(count)+' | '+str(p['testSeconds'])+' | '+format(p['elapsedSeconds'],'.3f')+' |'for (name,count,title),p in zip(specs,proofs))
with (R/'README.md').open('x')as f:f.write('''# Fixed lifecycle captures: 21 methods pass

The [frozen worker and reader](../implementation01/README.md) pass all 21 distinct
methods in four disjoint bounded selections. Twenty actual trials cover ten fixed
cases on both GPIO and PWM. The additional method verifies two refusals before
runtime construction. No failed test run or project source correction occurred in this stage.
See the [design](../DESIGN.md) and [read-only JSON audit](data-audit.json).
A [retained ordering error](../AUDIT-ORDERING.json) records a read-only audit
started before the fourth acquisition had finished writing its proof. It emitted
no audit output; the unchanged audit passed after acquisition completed.

| Selection | Methods | Test seconds | Elapsed seconds |
|---|---:|---:|---:|
'''+rows+'''

Accepted cancellation/restart has no modeled activation and retains the resource
floor. Pending cancellation restores modeled idle before claim release. New-owner
recovery preserves original requests and sessions in historical receipts; stale
resume and an unstarted suffix refuse instead of being rebound. A lost completion
reply retains a completed first effect, while a lost activation reply keeps the
unknown operation's claims until reconciliation stops the pending effect.

Invocation withdrawal before parent admission creates no parent, child or claim.
Withdrawal before dispatch prevents a handoff. Withdrawal while pending records
an authority-loss stop; withdrawal after committed completion reconciles the
historical success. Explicit read access is retained and invocation is never
restored. Only the single-step after-completion permission case satisfies its
whole completion objective; correct cancellation or a completed prefix does not
satisfy a two-step PAT.

The pure reader independently reconstructs exact fixed artifacts/cases, immutable
lowering, actual resolved environments, call/clock/reopen/failure schedules and
trusted grant snapshots. Thirty coherent/rehash attacks are refused and ten
I/O/clock purity checks pass. Targeted runtime assertions inspect actual receipts,
effects, unknown states, claims, final state and absent suffix work. The reader
explicitly does not yet compose full independent semantic/outcome histories.

Across the twenty captures there are '''+str(t['executionRecords'])+' execution records, '+str(t['configurationRecords'])+'''
configuration records, '''+str(t['checkpoints'])+' paired checkpoints and '+str(t['schedulerTicks'])+''' scheduler ticks.
Eighteen children produce twelve activations, four completed cycles and eight
canceled activations. Six injected losses are retained. All final captures have
zero unresolved operations or held claims. These totals describe separate fresh
trials, not one admitted candidate group or aggregate storage/time compliance.

All 8,101 project inputs, 8,104 frozen entries, six active harness inputs and 159
external pins remain stable in each run; every actual import origin and both
compiler/driver identities match. Original runtime, provider, compiler, matrix,
transcript and inherited tests are unchanged. Only exact private synthetic state
SQL paths are allowed. Complete attempts and original scratch trees are acquired;
no network, subprocess, physical/MCU, inference or live-service work ran in the
children. All original bounds remain. Review is by the primary agent; helpers
remain usage-limited. Live HMS and the adjacent Harness are untouched.

Complete independent fixed-case outcome composition, current candidate matrix
execution, attestation, aggregate quotas and public qualification remain pending.
Persistent prompt applications, automatic PAT learning/promotion and actual
device, driver and intelligence-hub control remain part of the unfinished goal.
''')
p=ROOT/'PROGRESS.md';s=p.read_text();mark='The separate [qualification supervisor rebase]';assert s.count(mark)==1
addition='''The next [fixed lifecycle capture stage](artifacts/implementation/pat-io-lifecycle-challenges/results/README.md)
passes **21 distinct methods in four bounded runs**. Twenty actual GPIO/PWM trials
cover all ten remaining fixed cancellation, restart, reply-loss and retained-read
withdrawal cases; one method checks two pre-runtime refusals. There are eighteen
admitted children, twelve activations, four completed cycles and eight canceled
activations, with no final unresolved operations or held claims. Original requests
and child keys survive reopen; stale resume/suffix execution refuses. A historical
completed first step is not relabeled as completion of the entire two-step PAT.

The independent partial reader verifies exact artifacts/cases, lowering, call,
clock, reopen and failure schedules and trusted grant snapshots. Thirty coherent
or rehashed alterations refuse; ten I/O/clock purity checks pass. Targeted runtime
assertions verify receipts, effects, unknown ownership and terminal state. Complete
independent semantic/outcome composition is explicitly still pending. All 8,101
project inputs, 8,104 frozen entries, six active harness inputs and 159 external
pins remain stable, as do actual imports and compiler/driver identities. All
original limits remain; complete attempts and original scratch trees are retained.
No test run failed or project source changed after freezing. A premature read-only
audit encountered the still-pending fourth acquisition proof; its ordering error
is retained and the unchanged audit passed after acquisition completed. Runtime,
provider, compiler, policy,
matrix, transcript and inherited tests are unchanged. Live HMS and the adjacent
Harness remain untouched. Candidate-group execution, aggregate budgets,
attestation, public qualification, PAT learning and physical/hub control remain
unfinished.

'''
s=s.replace(mark,addition+mark);p.write_text(s)
p=ROOT/'docs/prompt-to-pat.md';s=p.read_text();mark='An operator says, for example,';assert s.count(mark)==1
s=s.replace(mark,'''The [fixed lifecycle captures](../artifacts/implementation/pat-io-lifecycle-challenges/results/README.md)
now pass 21 methods spanning ten additional cases on GPIO and PWM: cancellation,
restart, reply loss and retained-read invocation withdrawal. Requests remain
immutable across restart, and correct fault handling is distinguished from
completion of the requested PAT. Exact request/schedule and targeted runtime
checks pass; full independent outcome composition and current-candidate group
qualification remain unfinished.

'''+mark);p.write_text(s)
p=ROOT/'docs/io-driver-hub-control.md';s=p.read_text();s+='''
The [fixed lifecycle capture stage](../artifacts/implementation/pat-io-lifecycle-challenges/results/README.md)
passes 21 methods, including twenty actual GPIO/PWM trials for cancellation,
restart, lost replies and invocation withdrawal with retained read authority.
Claims survive unknown effects until historical receipt reconciliation; stale
requests and unstarted suffixes are never rebound after restart. Actual captures
end with no unresolved operations or claims. The independent reader currently
checks exact requests/schedules and grant snapshots; complete semantic outcomes,
group qualification and actual driver/hub lifecycle execution remain pending.
''';p.write_text(s)
p=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md';s=p.read_text()
s=s.replace('Put every mandated case into the paired-configuration matrix and verify its exact trusted schedule, authority and terminal state',
 'The [fixed lifecycle stage](../pat-io-lifecycle-challenges/results/README.md) now captures both primitives for every mandated cancellation/reopen case with exact request/schedule checks and targeted state assertions. Complete independent semantic/outcome composition and current-candidate group execution remain')
s=s.replace('Execute the required variants on the actual candidate/environment and account for them in one group; historical fixtures are not a current candidate\'s matrix',
 'The [fixed lifecycle stage](../pat-io-lifecycle-challenges/results/README.md) captures all fixed pending/completion-loss and retained-read permission variants, including unknown claims and historical success. Compose complete independent outcome checks, then execute required variants on the actual candidate/environment in one group; historical fixtures are not a current candidate\'s matrix')
p.write_text(s)
p=ROOT/'scripts/check_project_links.py';s=p.read_text();mark="        ROOT/'artifacts/implementation/pat-io-authority-semantics/DESIGN.md',";assert s.count(mark)==1
paths=['DESIGN.md','implementation01/README.md','results/README.md']
for i,(name,count,title)in enumerate(specs,1):paths+=['harness%02d/README.md'%i,'harness%02d/SCOPE.md'%i,'results/'+name+'/README.md']
s=s.replace(mark,''.join("        ROOT/'artifacts/implementation/pat-io-lifecycle-challenges/"+v+"',\n"for v in paths)+mark);p.write_text(s)
print(json.dumps(dict(methods=21,captures=20,totals=t)))
