"""Summarize already acquired raw shared-resource captures; no project imports/SQL."""
from pathlib import Path
import hashlib,json
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-resource-challenge';R=B/'results/attempt01-passed72'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
proof=read(R/'proof.json');assert proof['status']=='passed';raw=Path(proof['rawScratch']['path']);cases=[]
for ep in sorted((R/'attempt/scratch').glob('*/engine-0.json')):
 e=read(ep);trial=ep.parent/'trial-0';docs={}
 for ref in e['records']:
  p=trial/'records'/ref['path'];assert p.stat().st_size==ref['bytes'] and sha(p)==ref['sha256'];docs[ref['path']]=read(p)
 def tables(cp):
  out={}
  for t in cp['tables']:
   rows=[]
   for ref in t['pages']:
    page=docs[ref['path']]['value'];assert page['table']==t['table']
    rows.extend(dict(zip(page['columns'],[c['value'] for c in r])) for r in page['rows'])
   assert len(rows)==t['rowCount'];out[t['table']]=rows
  return out
 checkpoints=[d['value']for d in docs.values()if d['kind']=='checkpoint'];calls=[d for d in docs.values()if d['kind']in{'call_returned','call_failed'}]
 final=tables(checkpoints[-1]);assert checkpoints[-1]['label']=='test_final'
 assert len(final['operations'])==4 and all(o['state']=='completed'for o in final['operations'])
 assert not final['claims'] and not final['io_owners'] and not final['pr_procedures']
 effects={k:sum(r[c]for r in final['io_effects'])for k,c in [('activations','activations'),('completedCycles','completed'),('canceledActivations','canceled')]}
 assert effects==dict(activations=4,completedCycles=4,canceledActivations=0)
 failed=[c['value']for c in calls if c['kind']=='call_failed'];assert [(c['label'],c['code'])for c in failed]==[('invoke:pwm','RESOURCE_BUSY'),('invoke:alias','RESOURCE_BUSY'),('probe:gpio_while_pwm','RESOURCE_BUSY')]
 probe=next(c for c in checkpoints if c['label']=='probe:gpio_while_pwm:before');assert len(tables(probe)['operations'])==4
 assert {r['caller_key']for r in final['replay_keys']}=={'trial:actor:'+r for r in ('gpio','pwm','alias','independent')}
 assert not e['report']['unresolvedOperations'] and e['report']['schedulerTicks']==7 and e['closed']
 assert e['resourceInspection']['exactResourceScheduleChecked'] and not e['resourceInspection']['completeHistoryChecked']
 cases.append(dict(testId=e['testId'],effects=effects,operationCount=4,declaredPossibleAdmissions=5,
  failedCalls=failed,schedulerTicks=7,checkpoints=len(checkpoints),executionRecords=len(e['records']),configurationRecords=len(e['configuration']['records']),
  rehashedRefusals=e['rehashedRefusals'],unresolvedOperations=[],independentInspection=e['resourceInspection'],
  finalAuthorityFloors=final['resource_floors'],finalBoardFloors=final['io_fences']))
assert len(cases)==2
value=dict(scope='Primary-agent raw acquired-capture audit; targeted synthetic assertions, not complete multi-actor semantics.',cases=cases,
 totals=dict(activations=8,completedCycles=8,canceledActivations=0,operations=8,declaredPossibleAdmissions=10,
             ticks=14,checkpoints=88,executionRecords=438,configurationRecords=142,rehashedRefusals=9),
 originalRawRetained=str(raw),sourceIndexSha256=proof['sourceIndexSha256'],qualificationPassed=False,
 completeMultiActorHistoryChecked=False,requiredMatrixCoverageChecked=False,physicalMeasurementChecked=False)
assert sum(c['executionRecords']for c in cases)==438 and sum(c['configurationRecords']for c in cases)==142
with (R/'data-audit.json').open('x')as f:f.write(json.dumps(value,indent=2)+'\n')
print(json.dumps(value['totals']))
