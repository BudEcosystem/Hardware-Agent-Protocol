"""Document complete historical inspection and incomplete fresh qualification."""
import collections,hashlib,json
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-group-history';R=B/'results'
assert not (R/'index.json').exists(), 'Sealed results are immutable'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
 p.write_text(json.dumps(v,indent=2)+'\n')
names=['attempt01-passed105','attempt02-failed-gpio-history','attempt03-launcher-refused','attempt04-passed106',
 'attempt05-failed-gpio-deadline','attempt06-failed-pwm-deadline','attempt07-failed-retained-history',
 'attempt08-passed107','attempt09-passed-retained-history','attempt10-failed-current-gpio-deadline']
passed=set();attempts=[]
for name in names:
 folder=R/name;proof=read(folder/'proof.json');result=read(folder/'attempt/result.json')
 if proof['status']=='refused_before_start':
  assert result['childState']=='not_started'and result['counts']is None
  detail='Parent refused a mismatched source-directory selector before child/scratch creation. No test or effect executed.'
  summary=dict(attempt=name,status='refused_before_start',testSeconds=None,rawScratchBytes=0)
 else:
  if proof['status']=='passed':passed.update(read(folder/'attempt/actual-tests.json')['executed'])
  detail=f"{proof['counts']['testsRun']} method(s); {proof['counts']['failures']} failure(s), {proof['counts']['errors']} error(s). {proof['testSeconds']:.3f} test seconds / {proof['elapsedSeconds']:.3f} harness seconds."
  detail+=f" Complete raw output retains {proof['rawScratchFiles']:,} files / {proof['rawScratchBytes']:,} bytes; {proof['sqliteConnections']} SQL connections."
  detail+=f" {proof['sourceFilesVerified']:,} project and {proof['frozenFilesVerified']:,} frozen inputs, six active harness inputs and 159 external pins remained stable; executed origins matched."
  summary=dict(attempt=name,status=proof['status'],testSeconds=proof['testSeconds'],elapsedSeconds=proof['elapsedSeconds'],
   rawScratchBytes=proof['rawScratchBytes'],rawScratchFiles=proof['rawScratchFiles'],sourceIndexSha256=proof['sourceIndexSha256'],counts=proof['counts'])
 text='# Retained group-history attempt\n\n'+detail+'\n\n[Acquisition proof](proof.json), [result](attempt/result.json).\n\n'
 if (folder/'attempt/output.log').exists():text+='[Complete log](attempt/output.log).\n\n'
 if (folder/'state-audit.json').exists():text+='[Closed state audit](state-audit.json), [storage audit](storage-audit.json); all database bytes unchanged.\n\n'
 text+='See the [stage result](../README.md) for the exact distinction between historical inspection and fresh current acceptance. No qualification or physical claim. Original artifacts and complete copies are retained.\n'
 (folder/'README.md').write_text(text);attempts.append(summary)
assert len(passed)==108
folder=R/'attempt09-passed-retained-history/attempt/scratch/test_complete_retained_gpio_and_archive_adversaries'
summary=read(folder/'summary.json');checks=read(folder/'checks.json')
assert checks['archiveAdversariesRefused']==4 and checks['currentGroupAccepted']is False and checks['independentReaderPure']is True
inspections=[read(folder/('case-%02d.json'%i))for i in range(30)]
for index,(row,value) in enumerate(zip(summary['cases'],inspections)):
 # File identities are checked from the actual bounded canonical outputs.
 p=folder/('case-%02d.json'%index)
 assert sha(p)==row['inspectionSha256']and p.stat().st_size==row['inspectionBytes']
profiles=collections.Counter(v['profile']for v in inspections);outcomes=collections.Counter()
for value in inspections:
 if 'staticOutcome'in value:outcomes[value['staticOutcome']]+=1
 else:
  full=value.get('trial',value);outcome=full['outcome'];outcomes[outcome.get('contractStatus',outcome.get('completionContract'))]+=1
groups=[]
for name in ('attempt02-failed-gpio-history','attempt05-failed-gpio-deadline','attempt06-failed-pwm-deadline','attempt10-failed-current-gpio-deadline'):
 folder=R/name;g=read(folder/'state-audit.json')['groups'][0];storage=read(folder/'storage-audit.json');proof=read(folder/'proof.json')
 effects={k:sum((s['effects'][i]or 0)for s in g['states'])for i,k in enumerate(('activations','completed','canceled'))}
 effects.update(claims=sum(s['claims']for s in g['states']),owners=sum(s['owners']for s in g['states']))
 groups.append(dict(attempt=name,captureStatus=g['groupStatus'],captureError=g['groupError'],completedCases=g['completedCases'],
  states=len(g['states']),endpointEffects=effects,rawScratchBytes=proof['rawScratchBytes'],sqliteBytes=storage['totalBytes'],
  activeScenario=next((s['scenario']for s in g['states']if s['caseId']==g['activeCaseId']),None),
  activeState=next((s for s in g['states']if s['caseId']==g['activeCaseId']),None)))
analysis=dict(scope='Corrected reader checks complete retained source01 GPIO history; fresh current-candidate qualification remains incomplete.',
 distinctPassingMethods=108,currentEvaluatorSourceIndexSha256=sha(B/'implementation04/index.json'),
 retainedSubjectSourceIndexSha256=sha(B/'implementation01/index.json'),attempts=attempts,captures=groups,
 retainedInspection=dict(cases=30,profiles=dict(profiles),outcomes=dict(outcomes),summary=summary,checks=checks),
 inspectedFreshGroups=0,checkedHistoricalGroups=1,qualificationPassed=False,independentAgentReview=False,
 currentSource04GpioCompletedCases=24,currentSource04PwmExecuted=False)
write(B/'GROUP-ANALYSIS.json',analysis)
text='''# Complete retained-group outcomes; fresh acceptance remains incomplete

**108 distinct methods pass:** 107 selected pure checks on source04 plus one
complete retained-history/adversary method. The latter checks all 30 source01
GPIO cases against separately retained pre-run setup, including every 25 fixed
challenge and nominal completion with replay/conflict. It rejects false aggregate
accounting, unreported archive files, a forged nominal report and changed trusted
authority. File, SQL and clock calls are forbidden during inspection.

| Attempt | Status | Test seconds | Raw bytes |
|---|---|---:|---:|
'''
for row in attempts:text+=f"| [{row['attempt']}]({row['attempt']}/README.md) | {row['status']} | {row['testSeconds'] if row['testSeconds'] is not None else '—'} | {row['rawScratchBytes']:,} |\n"
text+='''
Source01 captured all 30 GPIO cases but its wrapper failed on unavailable current
binding resolution after authority loss. Source02 corrects that exact boundary;
its fresh GPIO/PWM groups stop after 20/24 cases at the unchanged 60s deadline.
Source03 reuses the complete immutable source01 archive and exposes the distinct
four-actor resource environment shape. Source04 handles all four original/current
actor identities explicitly, while the existing semantic checker proves each
complete environment. Both wrapper failures and the source-selector pre-start
refusal remain retained. No old failure is relabeled or replaced.

The fresh source04 GPIO attempt also stops at the unchanged 60s capture deadline,
after 24 completed cases. The active permission-pending case retains a failed
child, canceled receipt and still-running parent, with no claims or owners.
Those endpoint observations do not establish complete settlement. Independent
inspection is unreached. The prepared source04 PWM harness14 remains unexecuted
after this GPIO gate fails. Source04 has no accepted fresh full group.

The passing historical inspection verifies 28 operations, 99 ticks, 3,832 worker
records, 10,149,988 producer bytes and 14,660,708 derived bytes. Its 30 inspection
documents total 216,187 bytes; the summary is an additional bounded record.
The complete test emits 32 files / 227,905 bytes and makes zero SQL connections.
The 70.718-second method includes the success and all four adversarial inspections;
it is not a single-pass benchmark. The 3972 retained subject/setup files and all
production files inherited into source03 remain unchanged; source04 changes only
the resource environment branch and its tests/metadata.

The reader matches trusted input identities and recomputes exact archive closure,
state layout, operation/tick/record/byte counters and expected outcomes. Its
historical matrix/outcome flags are true. Run/configuration/implementation
attestation, wall-time attestation, hard aggregate storage, physical measurement
and qualification remain false. The acquisition proof itself makes no semantic
claim; the separate inspection outputs carry the bounded historical conclusion.

[Design](../DESIGN.md), [corrections](../CORRECTION.md), [analysis](../GROUP-ANALYSIS.json),
[source04 review](../implementation04/source-review.json),
[inspection summary](attempt09-passed-retained-history/attempt/scratch/test_complete_retained_gpio_and_archive_adversaries/summary.json).
Primary-agent review only; existing helpers remain usage-limited. Live HMS and
the adjacent Harness are unchanged. No physical/MCU, inference or external
controller execution. Current qualification, public tools, learning, persistent
applications and real device/intelligence-hub providers remain required.
'''
(R/'README.md').write_text(text)
print(json.dumps(dict(distinctPassingMethods=108,profiles=dict(profiles),outcomes=dict(outcomes),captures=groups)))
