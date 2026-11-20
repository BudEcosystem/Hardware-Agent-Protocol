"""Reconcile the ten exact scopes, including all negative outcomes and audit refusals."""
import json
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-supervision-recovery';R=B/'results'
def read(p):return json.loads(p.read_bytes())
entries=[];passed=set();tested=set()
for folder in sorted(R.iterdir()):
 if not(folder/'proof.json').exists()or folder.name=='attempt01-preparation-refused':continue
 p=read(folder/'proof.json');r=read(folder/'attempt/result.json');targets=read(folder/'attempt/actual-tests.json')['executed']
 assert p['status']==r['status'] and r['childState']=='exited' and r['errors']==r['childErrors']==[]
 assert p['sourceFilesVerified']==239 and p['frozenFilesVerified']==242 and p['externalPinsVerified']==159
 tested.update(targets)
 if p['status']=='passed':passed.update(targets)
 entries.append(dict(destination=folder.name,attempt=p['attempt'],harness=p['harness'],status=p['status'],counts=p['counts'],testSeconds=p['testSeconds'],elapsedSeconds=p['elapsedSeconds'],rawScratch=p['rawScratch'],rawScratchFiles=p['rawScratchFiles'],rawScratchBytes=p['rawScratchBytes'],attemptFiles=p['attemptFilesAcquired'],actualOrigins=p['actualOrigins']['recordCount'],parentSqliteConnections=p['sqliteConnections']))
 audits=[p for p in folder.glob('*audit.json')]
 (folder/'README.md').write_text(f"# {p['status'].title()} retained attempt\n\n[Proof](proof.json), [complete log](attempt/output.log), [terminal result](attempt/result.json).\n\n{p['counts']['testsRun']} tests; {p['counts']['failures']} failures; {p['counts']['errors']} errors; {p['testSeconds']:.3f} test seconds. All 239 project, 242 frozen, six active harness and 159 external inputs remain unchanged. Raw originals and complete copies retain {p['rawScratchFiles']} files/{p['rawScratchBytes']} bytes. Parent SQL opens: {p['sqliteConnections']}; fixed child worker/driver SQL is a separate scope.\n\n"+' '.join(f'[{q.stem}]({q.name})'for q in sorted(audits))+"\n\nSee the [stage results](../README.md) for limitations. Empty observed state sets do not establish resolved effects; supervisor unresolvedEffects remains null. No physical qualification or aggregate quota is claimed.\n")
assert len(entries)==10 and len(tested)==180
full=[]
for e in entries:
 f=R/e['destination'];a=f/'process-audit.json'
 if a.exists():
  report=read(a)
  if report['groupStatus']=='captured':full.append(dict(destination=e['destination'],cases=report['completedCases'],states=report['states'],effects=report['effects'],claims=report['claims'],owners=report['owners'],history=report['history'],archiveTransportComplete=report['archive']['transportComplete']))
analysis=dict(scope='I/O-specific durable control, failure and hard owner-loss checks; unchanged production supervisor. Exact nominal failures retained.',distinctTestedMethods=len(tested),distinctPassingMethods=len(passed),failedMethods=sorted(tested-passed),attempts=entries,completedOwnerLossGroups=full,productionUnchanged=True,preparationRefusalRetained=True,partialStateAuditRefusalsRetained=True,transactionSidecarsPreserved=True,originalsAndCopiesRetained=True,actualAggregateStorageEnforced=False,publicQualificationMounted=False,qualificationPassed=False,physicalMeasurementChecked=False,goalStatus='active')
(B/'RESULTS.json').write_text(json.dumps(analysis,indent=2)+'\n')
table='\n'.join(f"| [{e['destination']}]({e['destination']}/README.md) | {e['counts']['testsRun']-e['counts']['failures']-e['counts']['errors']} pass / {e['counts']['failures']} fail | {e['testSeconds']:.3f} | {e['rawScratchFiles']} / {e['rawScratchBytes']} |"for e in entries)
(R/'README.md').write_text(f'''# I/O supervision recovery: {len(passed)} of {len(tested)} distinct methods pass

All 237 inherited files, including the five production supervisor modules,
remain unchanged. Two original test files add 20 explicit methods. The control
scope passes 171 checks: the original 160 and eleven I/O-specific admission,
concurrency, retention, corruption, lease, malformed-return, deadline-edge and
input-detachment checks. No control subprocess runs. Independent read-only audits
confirm eleven corrupt rows remain corrupted and three malformed returns retain
their exact bytes; no fixture was repaired. Its 28 parent ledger opens cover
26 private databases. The raw control tree is 8,038,589 bytes under 16 MiB.

| Attempt | Result | Test seconds | Raw files / bytes |
|---|---|---:|---:|
{table}

The original 500-record cutoff, reduced 1 ms parent deadline and pidfd-acquisition
failure pass their negative tests. The cutoff delivers a complete failed group:
seven completed cases, four retained states, two activations, one completion and
one cancellation. One operation remains accepted with one claim. Transport success
does not make that PAT eligible for promotion, and unresolvedEffects remains null.
The original Popen handle survives pidfd failure and is settled without reconstructing
a signaling target from a stored PID.

Hard owner exit after admission and launch intent recovers without relaunching.
See [RESULTS](../RESULTS.json) and the individual audits for later crash phases.
Every process collection independently holds the actual owner and exact writer
lease through inventory/copy. Parent SQL receipts exclude the separate fixed
crash driver and supervised worker. Reparented zombies do not supply signaling
or success authority. Cooperative audit hooks are not an OS sandbox.

The PWM and archive-commit nominal tests fail the unchanged 60 s supervisor
boundary. PWM retains 29 case directories and 28 manifests, 24 complete state
pairs and an incomplete authority-only state for case 28. There is no group return.
The failed archive-commit run preserves its committed negative archive after owner
loss and retains an interrupted database journal. A separate read-only auditor
hashes that database and journal without opening SQLite or recovering them.
Initial audit assumptions requiring complete state pairs/no journals were refused;
those failures and the corrected audit helpers are retained. No original worker
was rerun, no corrupt state repaired and no timeout/effect/storage ceiling widened.
These attempts do not prove complete supervised PWM or nominal archive-commit
recovery. Their performance cause was not profiled and is not established.

The first outer-launcher invocation hid the approved user distribution directory
with -I and refused before any child, scratch root or SQL work. Its complete
preparation artifact is preserved. The correct historical outer invocation retains
all dependency pins; test children still start with -I -S -B.

Each actual attempt verifies 239 project/242 frozen inputs, six active harness
inputs and 159 external pins. Process acquisition stays within the existing
256 MiB root, 8192 files and 16 MiB single-file limits; normal groups retain 60 s,
32 cases and 20 MiB derived-output bounds. These are not hard aggregate quotas.
Observed zero counts in an absent state tree are not an effect-resolution claim.

Next: profile and address the nominal deadline failures without weakening guards,
then complete the current PWM/archive-commit tests on reviewed fresh code. Preserve
all failed keys and states. Trusted fixed service configuration, actual aggregate
storage, serialized public import, PAT synthesis/learning, persistent Arduino
applications, real device/driver/hub providers and microscope commissioning remain.
The full goal is active and public/physical qualification remains false.
''')
(B/'README.md').write_text('# I/O supervisor recovery evidence\n\n[Design](DESIGN.md), [results](results/README.md), [source](implementation01/README.md).\nNominal deadline failures remain unresolved; all original states are retained.\n')
(R/'attempt01-preparation-refused/README.md').write_text('# Preparation refused before execution\n\n[Proof](proof.json), [original result](attempt/result.json). The outer -I invocation hid the approved user distribution root. No child, worker, scratch root or SQL operation started. The original pins were retained for the correctly invoked next attempt.\n')
block=f'''\nThe subsequent [I/O recovery stage]({{prefix}}artifacts/implementation/pat-io-supervision-recovery/results/README.md)
passes **{len(passed)} of 180 distinct methods** on unchanged production code. Its 171
control checks and separate worker/owner-loss cases retain exact inputs and outcomes
without relaunching old attempts or signaling stored PIDs. The lowered record cutoff
delivers a failed group with one accepted operation and one claim; it cannot promote
a PAT. Completed owner-loss groups are independently inspected while their recovered
archives retain unknown exit/effect status.\n\nThe current PWM and archive-commit nominal tests hit the original 60 s deadline.
Their partial databases, an interrupted transaction journal, negative archives and
all audit refusals are preserved. No state is repaired and no ceiling is widened.
The next step profiles these failures before claiming complete supervised PWM or
archive-commit success. Trusted service configuration, hard aggregate quotas,
public qualification, prompt learning, persistent applications and real device,
driver and hub providers remain unfinished.\n'''
for name,prefix in [('docs/prompt-to-pat.md','../'),('docs/io-driver-hub-control.md','../')]:
 path=ROOT/name;text=path.read_text();assert 'subsequent [I/O recovery stage]'not in text;path.write_text(text+'\n'+block.format(prefix=prefix))
p=ROOT/'PROGRESS.md';text=p.read_text();anchor='The separate [qualification supervisor rebase]';assert text.count(anchor)==1;text=text.replace(anchor,block.format(prefix='')+'\n'+anchor);p.write_text(text)
p=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md';text=p.read_text();a='The next implementation extends the current owned path to PWM and I/O-specific\nowner-loss, interruption, lease, malformed-output and capacity failures.';assert a in text;text=text.replace(a,f'The [I/O recovery stage](../pat-io-supervision-recovery/results/README.md) now passes {len(passed)} of 180 distinct methods, including the new control and negative-worker cases. Current PWM and archive-commit nominal runs fail the original 60 s deadline; their partial states and transaction sidecars remain preserved. Profile and address these failures before treating those paths as complete.');p.write_text(text)
print(json.dumps(dict(distinctTestedMethods=len(tested),distinctPassingMethods=len(passed),failedMethods=sorted(tested-passed),completedOwnerLossGroups=full)))
