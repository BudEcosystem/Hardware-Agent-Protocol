"""Reconcile exact reviewed attempts and update current progress documents."""
import json
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-service-authority';R=B/'results'
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
entries=[];tested=set();passed=set();full=[]
for folder in sorted(R.iterdir()):
 if not(folder/'proof.json').exists():continue
 proof=read(folder/'proof.json');result=read(folder/'attempt/result.json');targets=read(folder/'attempt/actual-tests.json')['executed']
 assert proof['status']==result['status'] and result['childState']=='exited' and result['errors']==result['childErrors']==[]
 assert proof['sourceFilesVerified']==244 and proof['frozenFilesVerified']==247 and proof['externalPinsVerified']==159
 tested.update(targets)
 if proof['status']=='passed':
  assert not passed.intersection(targets);passed.update(targets)
 else:assert folder.name=='attempt01-failed-authority32' and read(folder/'failure-audit.json')['configurationCommits']==0
 storage=read(folder/'storage-audit.json');assert storage['databaseBytesUnchanged']
 item=dict(destination=folder.name,attempt=proof['attempt'],harness=proof['harness'],sourceIndexSha256=proof['sourceIndexSha256'],status=proof['status'],counts=proof['counts'],testSeconds=proof['testSeconds'],elapsedSeconds=proof['elapsedSeconds'],rawScratch=proof['rawScratch'],rawScratchFiles=proof['rawScratchFiles'],rawScratchBytes=proof['rawScratchBytes'],attemptFiles=proof['attemptFilesAcquired'],actualOrigins=proof['actualOrigins']['recordCount'],parentSqliteConnections=proof['sqliteConnections'],databases=len(storage['databases']))
 if(folder/'process-audit.json').exists():
  p=read(folder/'process-audit.json');item.update(groupStatus=p['groupStatus'],completedCases=p['completedCases'],states=p['states'],effects=p['effects'],claims=p['claims'],owners=p['owners'],transportComplete=p['archive']['transportComplete'],unresolvedEffects=p['archive']['unresolvedEffects'])
  if p['groupStatus']=='captured':full.append(folder.name)
 entries.append(item)
assert len(entries)==14 and len(tested)==len(passed)==249 and len(full)==6
authority=read(R/'attempt02-passed-authority32/authority-audit.json');assert authority['authorityCount']==34 and authority['validatedVersions']==25
owned=read(R/'attempt04-passed-authority-owned/authority-audit.json');assert owned['authorityCount']==1 and owned['validatedVersions']==1
joined=read(R/'attempt04-passed-authority-owned/authority-service-audit.json');assert joined['configurationPersistedByAuthorityStore'] and joined['sourceImageFiles']==258
analysis=dict(scope='Durable finite I/O service configuration under the actual Journal authority and installed resolver; isolated source snapshots only.',goalStatus='active',distinctTestedMethods=249,distinctPassingMethods=249,totalMethodExecutions=sum(x['counts']['testsRun']for x in entries),retainedFailedAttempts=1,correctedSourceIndexSha256='6215ff9c5fe621a704c1996af86fc6ad80da994ffb6d92e97f7bad71afb75470',authorityConfigurationLibraryVerified=True,publicServiceMounted=False,authorityConfiguredGroupPass=True,completedGroups=full,attempts=entries,qualificationPassed=False,physicalValidation=False,aggregateFilesystemQuotaEnforced=False)
write(B/'RESULTS.json',analysis)
for item in entries:
 folder=R/item['destination'];extra=''
 if(folder/'authority-audit.json').exists():extra+=' [Authority history and source state](authority-audit.json).'
 if(folder/'process-audit.json').exists():extra+=' [Process/image/outcome associations](process-audit.json).'
 if(folder/'failure-audit.json').exists():extra+=' [Failure diagnosis](failure-audit.json).'
 if(folder/'control-audit.json').exists():extra+=' [Original corruption/recovery audit](control-audit.json).'
 if(folder/'authority-service-audit.json').exists():extra+=' [Authority-to-run joins](authority-service-audit.json).'
 (folder/'README.md').write_text('# '+item['attempt']+'\n\n'+item['status']+': '+str(item['counts']['testsRun'])+' methods; '+str(item['counts']['failures'])+' failures, '+str(item['counts']['errors'])+' errors. [Exact acquisition](proof.json), [retained output](attempt/output.log), [storage observations](storage-audit.json).'+extra+'\n\nRaw originals and complete copies remain retained. No public or physical qualification is claimed.\n')
table='| Attempt | Methods | Result | Seconds |\n|---|---:|---|---:|\n'+'\n'.join('| ['+x['attempt']+']('+x['destination']+'/README.md) | '+str(x['counts']['testsRun'])+' | '+x['status']+' | '+str(x['testSeconds'])+' |'for x in entries)
(R/'README.md').write_text('''# Durable authority configuration results

**249 of 249 distinct methods pass** on the corrected source: 206 inherited controls, 32 new authority controls and 11 process methods. The first attempt is retained with two failures and 30 errors, all caused by comparing a bounded SQLite row with a dictionary. No service configuration was committed in that failed run. The correction converts optional anchor rows and compares mandatory metadata fields explicitly; all test bytes and execution limits remain unchanged.

The new store explicitly authorizes creation/configuration, retains canonical authority-bound pins and revision/receipt history, resolves exact mutation replay before source or capacity checks, and reconstructs fresh preparation from actual installed resolver descriptors. Controls cover commit rollback/lost replies, same-key concurrency/conflicts, history/reopen, capacity, incomplete/corrupt state and changes during planning. Independent inspection checks 34 control authorities and 25 valid configuration versions. Deliberate corruptions remain present; source authorities have no operations, claims or board effects.

The actual authority-backed group commits configuration, closes/reopens the Runtime, reconstructs from its stored pin and actual descriptors, and retains input associations before the original supervisor starts its worker. Independent checks join the durable record to the run and original registry bindings/sessions. The full group has 30 cases, 26 retained states, 21 activations, 11 completions, 10 cancellations and no remaining claims or owners. The source authority itself has zero effects. Exact supervisor replay before/after reopen adds no worker; changed requests with the same key conflict.

Six full groups pass, including the new authority-backed group, legacy configured group, PWM and three owner-recovery cases. Original negative cutoff, pidfd, deadline and pre-launch owner-loss cases also pass their refusal/recovery expectations. Transport completion never establishes semantic qualification; `unresolvedEffects` remains unknown at the supervisor boundary. Code images contain 258 files, including seven supervisor source files and 157 dependency files. All original deadlines, effect and retention limits remain.

Every attempt verifies 244 project files, 247 frozen inputs, six active harness files and 159 external pins. Original raw trees and complete copies remain retained. Source-free read-only audits do not recover transaction sidecars. Primary-agent review only. One preliminary auditor path-expression failure is retained separately under tooling-failures; it produced no audit report and did not execute project code.

'''+table+'''

This verifies an isolated host library for the finite synthetic I/O policy. It does not mount public qualification tools, import/promote evidence, enforce an aggregate filesystem quota, learn PATs from prompts or control real I/O, drivers or hub compute. Those remain required. See the [design](../DESIGN.md), [exact summary](../RESULTS.json) and [next work](../NEXT.md). The full HMS goal remains active.
''')
(B/'README.md').write_text('# Authority-owned I/O service configuration\n\n[Design](DESIGN.md), [results](results/README.md), [corrected source](implementation02/README.md), [exact attempts](RESULTS.json).\n\n249 distinct methods pass; the initial failed32 attempt and its unchanged tests remain retained. The store shares the Journal authority and obtains actual installed descriptors before run preparation. Public mounting, evidence promotion, learning and physical providers remain unfinished.\n')
(B/'NEXT.md').write_text('''# Next: serialized qualification import and configuration eligibility

Use the [corrected source](implementation02/index.json) and [exact results](RESULTS.json). The authority now owns immutable finite-I/O service configuration and obtains actual installed descriptors during preparation. Its consistency recheck does not reserve a future run or prove effect-time freshness.

Join a durable logical run reservation to configuration receipt, prepared request and the existing supervisor key. Resolve exact run replay from the retained request before fresh source/configuration checks; a changed configuration, descriptor or session must not silently rebind an existing run ID. Interrupted admission must remain distinguishable from executed work. Preserve status and reconciliation across source/configuration drift. Do not allow an opaque caller-supplied pin or success flag to establish authority.

The current `PatCatalog` environment is a closed profile containing deployment, compiler and role identities, with no service-configuration field. Its evaluator callback receives artifact and environment, without the logical run ID. A direct wrapper therefore cannot supply the new durable run identity or configuration eligibility correctly. Define a versioned invocation/environment contract or a separately checked service boundary while preserving existing fan behavior and historical readers. Current evaluator availability is checked before catalog evaluation replay; historical retrieval must remain available when new execution is disabled.

Implement serialized import from the archived supervisor attempt into the existing independent full semantic reader and evidence store/memo. Verify the original request, bundle, image and complete finite matrix before recording qualification evidence. Join import replay to the original mutation key and exact evidence identity. Keep incomplete, corrupt, cold or unavailable evidence unavailable. Supervisor transport success is insufficient. Recheck current active configuration/evaluator/environment and catalog eligibility before promotion; changing configuration must invalidate incompatible reuse without destroying historical status.

The existing `EvidenceStore` and its four-check result contract belong to the earlier fan policy. Its constructor/import own SQLite transactions. The finite-I/O profile needs an explicit bounded import/reducer contract for the complete 30-case group and serialization with the Journal mutex; do not pass the I/O group through the fan reducer or nest its import inside an authority transaction. Evidence verification inside catalog eligibility must remain pure and bounded on the same connection.

Public service mounting still needs enforced aggregate storage and protected control capacity. File scans and accounted encoded data do not provide quotas. Keep this candidate isolated until deployment prerequisites are met; no OS sandbox or real-time guarantee is established. Persistent Arduino event/controller applications, NL synthesis and trace learning, actual device I/O/driver/hub compute and lifecycle providers, streams, research/conformance expansion and microscope commissioning remain part of the full goal.
''')
block='''
The [authority-owned I/O configuration stage]({prefix}artifacts/implementation/pat-io-service-authority/results/README.md)
passes **249 of 249 distinct methods** on its corrected source. It adds durable
administrator-owned configuration history, authority-bound service pins, exact
mutation replay and revision conflicts inside the existing Journal. Fresh run
preparation obtains the complete actual installed descriptor inventory and refuses
configuration or session changes during planning. One full worker group starts
from a committed configuration after Runtime reopen; independent checks join its
record, registry bindings/sessions and run inputs. The source authority has zero
device effects while the isolated 30-case worker group retains its own outcomes.

The initial 32-method attempt failed before configuration commit because SQLite
rows were compared directly with dictionaries. Its raw state remains retained;
the bounded-row conversion correction passes the same unchanged tests. Inherited
controls and process recovery checks also pass, with no widened limits. This is
an isolated host-library result, not public mounting or physical qualification.
[Run reservation and serialized evidence import]({prefix}artifacts/implementation/pat-io-service-authority/NEXT.md),
configuration-aware promotion, aggregate storage enforcement, prompt learning,
persistent Arduino applications and real device/driver/hub providers remain.
The full goal stays active.
'''
for name,prefix in [('docs/prompt-to-pat.md','../'),('docs/io-driver-hub-control.md','../')]:
 p=ROOT/name;text=p.read_text();assert 'authority-owned I/O configuration stage'not in text
 text=text.replace('2026-11-07','2026-11-08',1);p.write_text(text+'\n'+block.format(prefix=prefix))
p=ROOT/'PROGRESS.md';text=p.read_text();anchor='The [trusted I/O service configuration stage]';assert text.count(anchor)==1
text=text.replace('enforced storage, fixed service configuration/public mounting, public PAT tools', 'enforced storage, public service mounting, serialized I/O evidence import, public PAT tools')
p.write_text(text.replace(anchor,block.format(prefix='')+'\n'+anchor))
p=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md';text=p.read_text();text+='\nThe [authority-owned configuration library](../pat-io-service-authority/results/README.md) now passes 249 distinct methods, including durable reopen and actual resolver-to-worker preparation. Continue with [run reservation, evidence import and configuration eligibility](../pat-io-service-authority/NEXT.md). Public mounting, aggregate quotas, learning and physical targets remain unfinished.\n';p.write_text(text)
p=ROOT/'scripts/check_project_links.py';text=p.read_text();anchor="        *ROOT.glob('artifacts/implementation/pat-io-service-config/*.md'),";assert text.count(anchor)==1
extra='\n'.join('        '+line for line in ["*ROOT.glob('artifacts/implementation/pat-io-service-authority/*.md'),","*ROOT.glob('artifacts/implementation/pat-io-service-authority/implementation*/README.md'),","*ROOT.glob('artifacts/implementation/pat-io-service-authority/harness*/README.md'),","*ROOT.glob('artifacts/implementation/pat-io-service-authority/harness*/SCOPE.md'),","ROOT/'artifacts/implementation/pat-io-service-authority/results/README.md',","*ROOT.glob('artifacts/implementation/pat-io-service-authority/results/*/README.md'),"])
p.write_text(text.replace(anchor,extra+'\n'+anchor))
print(json.dumps(dict(distinctTestedMethods=len(tested),distinctPassingMethods=len(passed),attempts=len(entries),completedGroups=len(full))))
