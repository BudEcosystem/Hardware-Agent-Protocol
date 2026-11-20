"""Reconcile documentation only after all four exact pure selections pass."""
import json
from pathlib import Path
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-authority-semantics';R=B/'results'
specs=[('attempt01-passed34',34,'New authority semantics'),('attempt02-passed72',72,'Existing operation/procedure histories'),
       ('attempt03-passed48',48,'Existing configuration histories'),('attempt04-passed27',27,'Existing observation histories')]
proofs=[]
for name,count,title in specs:
 p=json.loads((R/name/'proof.json').read_bytes())
 assert p['status']=='passed' and p['counts']==dict(testsRun=count,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
 assert p['sourceIndexSha256']=='56f5beaad09b6fd4233f07c403c9d3716fa6c664ae3899e905347cd9005a95f7'
 assert p['rawScratchFiles']==p['rawScratchBytes']==p['sqliteConnections']==0
 proofs.append(p)
 for q in [R/name/'README.md']:
  with q.open('x')as f:f.write('# '+title+': '+str(count)+' tests pass\n\n'+
   'All selected methods pass with no failures, errors, skips or expected failures.\n'+
   'Test time is '+str(p['testSeconds'])+' s; elapsed time is '+format(p['elapsedSeconds'],'.3f')+' s.\n'+
   'See the [complete attempt](attempt/result.json), [acquisition proof](proof.json),\n'+
   '[stage results](../README.md), and [frozen source](../../implementation01/README.md).\n\n'+
   'All 8,098 project inputs, 8,101 frozen entries and 159 external pins remain\n'+
   'stable. Compiler/driver identity and all actual import origins match. SQL,\n'+
   'network, subprocess, physical/MCU, inference and live-service execution are\n'+
   'forbidden. The complete 8,132-file attempt and empty original scratch at\n'+
   '`'+p['rawScratch']['path']+'` remain retained.\n'+
   'Original 180-second, 16 MiB and 8,192-file bounds are unchanged.\n\n'+
   'This selection supports the fixed historical authority challenges. It does\n'+
   'not qualify a whole PAT, establish current implementation attestation, enforce\n'+
   'aggregate group storage or verify physical hardware.\n')
table='\n'.join('| ['+title+']('+name+'/README.md) | '+str(count)+' | '+str(p['testSeconds'])+' | '+format(p['elapsedSeconds'],'.3f')+' |'
    for (name,count,title),p in zip(specs,proofs))
with (R/'README.md').open('x')as f:f.write('''# Complete authority histories: 181 selected tests pass

The [frozen composition](../implementation01/README.md) passes 181 distinct methods
across four bounded pure runs. No failed attempt or source correction occurred
in this stage. See the [design](../DESIGN.md).

| Selection | Tests | Test seconds | Elapsed seconds |
|---|---:|---:|---:|
'''+table+'''

All six retained GPIO/PWM captures now receive independent complete-history and
expected-response checks. The checker derives the exact authorized administrative
change, registry revision, grants, binding and historical configuration, namespace,
parent/child admissions, dispatch refusal or handoff, board ownership/effects,
operation and parent events, observations, returned replies and final settlement.

Binding invalidation clears target presence while preserving its binding document,
endpoint session and cached samples through reopen. It cannot silently refresh or
rebind the original command. Complete grant removal leaves the installed binding
intact; eight public read/replay/namespace probes per primitive remain denied before
and after recovery. The separate original inactive-binding probe is refused by
the binding check, without reusing a parent-reserved key or exhausting the budget.

Across all six histories there are six admitted children, four activations, zero
completed cycles and four canceled activations. Each pending operation becomes
unknown with claims retained when the new owner stops the historical receipt;
reconciliation then settles the child and releases its claims. Owner cancellation
withdraws the existing parent without restoring public read or invoke authority.
Every history has no admitted suffix or unresolved claim. All 140 paired
checkpoints and the sample production counts are checked:28 per pre-dispatch
invalidation case,36 per pending invalidation case and40 per full-withdrawal case.

Coherently altered grants, presence, receipts, binding history, sample epochs,
session refreshes, revision changes, claims/fences, hidden effects, event causes,
cancellation replies and final observations are refused. Old private folds still
refuse the new unsupported causes without independently derived context. Existing
public readers retain their original profiles and all 147 selected regressions.

All 8,098 project inputs, 8,101 frozen entries and 159 external pins remain stable
in every run, together with compiler/driver identity and actual imports. Every SQL
connection is forbidden. Complete attempts and empty original scratch roots are
retained. The original 180-second, 16 MiB and 8,192-file bounds remain. The explicit
source closure excludes 585 resource-only fixtures and adds 1,013 acquired
authority fixture files; original sealed evidence stays intact. Runtime, provider,
compiler and capture producer source are unchanged. Review is by the primary agent
because delegated reviewers remain usage-limited. Live HMS and the adjacent Harness
remain untouched.

Complete-history success is limited to the fixed authority challenges. Current
candidate matrix execution, current implementation attestation, aggregate budget
enforcement, public qualification, persistent prompt applications, PAT learning
and promotion, and actual device/driver/hub control remain unfinished.
''')
p=ROOT/'PROGRESS.md';s=p.read_text();mark='The separate [qualification supervisor rebase]';assert s.count(mark)==1
addition='''The subsequent [independent authority-history composition](artifacts/implementation/pat-io-authority-semantics/results/README.md)
passes **181 distinct methods across four bounded pure runs**:34 new checks and
147 unchanged operation, procedure, configuration and observation regressions.
All six retained binding/full-withdrawal captures now have complete independent
expected-response validation. The checker derives the trusted change, exact
revision/grants/binding transition, original requests, admissions/dispatches,
board effects, operation/parent events, sample history and returned results.
Invalidated bindings retain historical sessions/samples and lose current presence;
complete grant removal preserves installed bindings while all16 public probes deny.
Recovery retains claims through unknown outcomes, settles historical receipts and
permits owner withdrawal without restoring public authority. No suffix or unresolved
claim remains. All140 paired checkpoints and exact sample production are checked.

The new private contexts are derived by the closed composition; old public readers
retain their original unsupported-case refusals. Coherent false grants, presence,
receipts, samples/epochs, bindings, revisions, claims/fences, hidden effects,
event causes, cancellation replies and final reports refuse. All8098 project inputs,
8101 frozen entries and159 external pins remain stable in each run; actual origins
and compiler/driver identities match. Every SQL connection is forbidden. The
original180s/16MiB/8192-file bounds remain. The explicit closure excludes585
resource-only fixture files and adds1013 authority fixture files; original sealed
evidence remains intact. All four complete attempts and empty original scratch
roots are acquired. No failed run or source correction occurred. Review is by the
primary agent; live HMS and the adjacent Harness remain untouched.

The current-candidate matrix, implementation attestation, aggregate enforcement,
public qualification, persistent prompt applications, automatic PAT learning,
physical drivers and hub lifecycle/compute control remain unfinished.

'''
for a,z in {'runs**:34':'runs**: 34','all16':'all 16','All140':'All 140','All8098':'All 8,098','8101 frozen':'8,101 frozen','and159':'and 159','original180s/16MiB/8192-file':'original 180-second/16 MiB/8,192-file','excludes585':'excludes 585','adds1013':'adds 1,013'}.items():addition=addition.replace(a,z)
s=s.replace(mark,addition+mark);p.write_text(s)
p=ROOT/'docs/prompt-to-pat.md';s=p.read_text();mark='An operator says, for example,';assert s.count(mark)==1
s=s.replace(mark,'''The [complete authority-history checker](../artifacts/implementation/pat-io-authority-semantics/results/README.md)
now passes 181 selected tests and independently validates those six retained
histories. It derives authority changes, effects, ownership, samples and replies;
invalidated bindings keep historical samples while fresh control is refused.
Recovery never restores withdrawn public permissions. These fixed challenges are
now checked, while current-candidate matrix execution, aggregate enforcement,
attestation, public qualification and automatic PAT promotion remain unfinished.

'''+mark);p.write_text(s)
p=ROOT/'docs/io-driver-hub-control.md';s=p.read_text();s+='''
The [complete authority-history composition](../artifacts/implementation/pat-io-authority-semantics/results/README.md)
passes 181 selected tests. It independently derives all six retained binding and
full-withdrawal responses, including historical stop/reconciliation, retained
claims until settlement, inactive cached samples, exact public denials and owner
parent withdrawal without restored permission. Full current-candidate qualification,
physical I/O, driver lifecycle and hub service/compute control remain unfinished.
''';p.write_text(s)
p=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md';s=p.read_text()
old='Implement complete independent authority/binding semantic composition for these retained captures, then integrate exact current-candidate group execution.'
new='The [complete authority composition](../pat-io-authority-semantics/results/README.md) now passes181 distinct tests and independently validates all six exact histories. Integrate the complete checks into exact current-candidate group execution with attestation and aggregate budgets.'
assert old in s;s=s.replace(old,new.replace('passes181','passes 181'));p.write_text(s)
p=ROOT/'scripts/check_project_links.py';s=p.read_text();mark="        ROOT/'artifacts/implementation/pat-qualification-supervisor/README.md',";assert s.count(mark)==1
names=['DESIGN.md','implementation01/README.md']
for n in range(1,5):names+=['harness%02d/README.md'%n,'harness%02d/SCOPE.md'%n]
names+=['results/README.md']+['results/'+name+'/README.md' for name,_,_ in specs]
s=s.replace(mark,''.join("        ROOT/'artifacts/implementation/pat-io-authority-semantics/"+n+"',\n" for n in names)+mark);p.write_text(s)
print(json.dumps(dict(distinctTests=181,resultsReadmes=5,sourceFiles=8098,documentationReadyForLinkCheck=True)))
