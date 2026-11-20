"""Read acquired JSON only; audit retained lifecycle captures without project imports."""
import hashlib,json
from pathlib import Path
B=Path('artifacts/implementation/pat-io-lifecycle-challenges');R=B/'results'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def documents(directory,refs):
 out=[]
 for i,r in enumerate(refs):
  assert r['path']=='%06d.json'%i
  p=directory/r['path'];assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256'];out.append(read(p))
 return out
def tables(records,checkpoint):
 result={}
 for table in checkpoint['value']['tables']:
  rows=[]
  for ref in table['pages']:
   v=records[int(ref['path'].split('.')[0])]['value'];assert v['table']==table['table']
   rows += [{k:c['value'] for k,c in zip(v['columns'],row)} for row in v['rows']]
  assert len(rows)==table['rowCount'];result[table['table']]=rows
 return result
cases=[];totals=dict(executionRecords=0,configurationRecords=0,checkpoints=0,schedulerTicks=0,operations=0,
    activations=0,completedCycles=0,canceledActivations=0,rehashedRefusals=0,injectedFaults=0,runtimeOpens=0,
    publicRefusals=0,plannedChildReservations=0,producerBytes=0)
for number in range(1,5):
 result=R/('attempt%02d-passed%d'%(number,6 if number==1 else 5));proof=read(result/'proof.json');assert proof['status']=='passed'
 scratch=result/'attempt/scratch'
 for request in sorted(scratch.glob('*/requested-case.json')):
  requested=read(request);where=request.parent;manifest=read(where/'trial-manifest.json');engine=read(where/'engine-0.json')
  records=documents(where/'trial-0/records',manifest['records'])
  config=documents(where/'trial-0/configuration',manifest['configuration']['records'])
  assert engine['lifecycleInspection']['exactControlScheduleChecked'] and engine['lifecycleInspection']['patCorrespondenceChecked']
  assert not engine['lifecycleInspection']['completeHistoryChecked'] and not engine['lifecycleInspection']['qualificationPassed']
  assert 'inspectionError' not in engine and manifest['closed'] and not manifest['report']['unresolvedOperations']
  case=requested['case'];assert case['caseId']==manifest['caseId'] and case['programDigest']==manifest['programDigest']
  checkpoints=[r for r in records if r['kind']=='checkpoint'];final=checkpoints[-1];assert final['value']['label']=='test_final'
  state=tables(records,final);assert not state['claims'] and not state['io_owners']
  effects=tuple(sum(row[k] for row in state['io_effects'])for k in ('activations','completed','canceled'))
  expected=tuple(case['definition']['expected'][k]for k in ('activations','completedCycles','canceledActivations'));assert effects==expected
  supplied=manifest['injectedFaults'];faults=requested['expectedFaults'];assert len(supplied)==len(faults)
  for actual,wanted in zip(supplied,faults):
   assert {k:v for k,v in actual.items()if k!='operationId'}==wanted
   cp=next(c for c in checkpoints if c['value']['phase']==wanted['phase'] and c['value']['label']==('drive:adapters:after' if wanted['point']=='board.begin.after_commit' else 'drive:adapters:after_error'))
   unknown=tables(records,cp);assert unknown['operations'][0]['id']==actual['operationId'] and unknown['operations'][0]['state']=='outcome_unknown' and unknown['claims']
  row=dict(testId=requested['testId'],scenario=case['definition']['scenario'],targetRole=case['targetRole'],caseId=case['caseId'],
      matrixDigest=manifest['matrixDigest'],programDigest=manifest['programDigest'],executionRecords=len(records),configurationRecords=len(config),
      checkpoints=len(checkpoints),schedulerTicks=manifest['report']['schedulerTicks'],operations=len(state['operations']),
      activations=effects[0],completedCycles=effects[1],canceledActivations=effects[2],rehashedRefusals=engine['rehashedRefusals'],
      injectedFaults=len(supplied),runtimeOpens=sum(r['kind']=='runtime_opened' for r in records),
      publicRefusals=sum(r['kind']=='call_failed' and r['value']['label'] in {'resume','submit'} for r in records),
      plannedChildReservations=manifest['childOperationReservation'],producerBytes=sum(r['bytes']for r in manifest['records'])+sum(r['bytes']for r in manifest['configuration']['records']),
      parentState=state['pr_procedures'][0]['state'] if state['pr_procedures'] else None,
      childState=state['operations'][0]['state'] if state['operations'] else None,
      requestedCaseSha256=sha(request),trialManifestSha256=sha(where/'trial-manifest.json'),targetedAssertions=engine['targetedRuntimeAssertions'])
  for k in totals:totals[k]+=row[k]
  cases.append(row)
assert len(cases)==20 and len({(c['scenario'],c['targetRole'])for c in cases})==20
assert len({c['scenario']for c in cases})==10 and {c['targetRole']for c in cases}=={'gpio','pwm'}
assert all(len({c['matrixDigest']for c in cases if c['targetRole']==role})==1 for role in ('gpio','pwm'))
assert totals['activations']==12 and totals['completedCycles']==4 and totals['canceledActivations']==8
assert totals['operations']==18 and totals['injectedFaults']==6 and totals['rehashedRefusals']==30 and totals['runtimeOpens']==26
out=dict(scope='Read-only acquired JSON/count audit; targeted runtime assertions and partial independent schedule checks, not complete semantic outcome proof.',
    cases=cases,totals=totals,projectModulesImported=False,databasesOpened=False,
    completeLifecycleHistoryChecked=False,requiredMatrixCoverageChecked=False,qualificationPassed=False)
with (R/'data-audit.json').open('x')as f:f.write(json.dumps(out,indent=2)+'\n')
print(json.dumps(totals))
