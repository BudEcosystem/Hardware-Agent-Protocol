"""Audit acquired authority captures without project imports, SQL or runtime."""
from pathlib import Path
import hashlib,json
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-authority-challenges';R=B/'results/attempt01-passed76'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
proof=read(R/'proof.json');assert proof['status']=='passed';cases=[]
for ep in sorted((R/'attempt/scratch').glob('*/engine-0.json')):
 e=read(ep);trial=ep.parent/'trial-0';docs={};cfg={}
 for refs,folder,out in [(e['records'],'records',docs),(e['configuration']['records'],'configuration',cfg)]:
  for ref in refs:
   p=trial/folder/ref['path'];assert p.stat().st_size==ref['bytes'] and sha(p)==ref['sha256'];out[ref['path']]=read(p)
 def tables(cp,source):
  out={}
  for t in cp['tables']:
   rows=[]
   for ref in t['pages']:
    page=source[ref['path']]['value'];assert page['table']==t['table']
    rows.extend(dict(zip(page['columns'],[c['value']for c in r]))for r in page['rows'])
   assert len(rows)==t['rowCount'];out[t['table']]=rows
  return out
 name=e['expectedCase']['definition']['scenario'];before=name=='binding_before_dispatch';withdraw=name=='full_authority_withdrawal'
 checkpoints=[d['value']for d in docs.values()if d['kind']=='checkpoint'];snapshots=[d['value']for d in cfg.values()if d['kind']=='snapshot']
 calls=[d for d in docs.values()if d['kind']in{'call_returned','call_failed'}]
 final=tables(checkpoints[-1],docs);configuration=tables(snapshots[-1],cfg)
 assert checkpoints[-1]['label']==snapshots[-1]['label']=='test_final'
 operation,=final['operations'];parent,=final['pr_procedures'];assert operation['state']==('rejected_before_dispatch'if before else'canceled')
 assert parent['state']==('failed'if before else'canceled') and not final['claims'] and not final['io_owners']
 assert len(final['pr_steps'])==2 and final['pr_steps'][1]['operation_id']is None
 assert len(final['namespaces'])==1 and final['series'][0]['next_epoch']==2
 assert len(configuration['reg_grants'])==(0 if withdraw else 1)
 effects={k:sum(r[c]for r in final['io_effects'])for k,c in [('activations','activations'),('completedCycles','completed'),('canceledActivations','canceled')]}
 assert effects==dict(activations=0 if before else 1,completedCycles=0,canceledActivations=0 if before else 1)
 failed=[c['value']for c in calls if c['kind']=='call_failed']
 expected=[] if before else [('resume','PROCEDURE_DEPENDENCY_UNRESOLVED'),('probe:inactive_binding','BINDING_INACTIVE')]
 if withdraw:expected=[(label,'ACCESS_DENIED')for label in ('read:operation','read:parent','submit','probe:namespace')]*2
 assert [(c['label'],c['code'])for c in failed]==expected
 assert e['report']['statusAccess']=='privileged_trial_observation' and not e['report']['unresolvedOperations']
 assert e['report']['schedulerTicks']==3 and e['closed'] and not e['cleanupErrors']
 check=e['authorityInspection'];assert check['exactAuthorityScheduleChecked'] and not check['completeHistoryChecked']
 cases.append(dict(testId=e['testId'],scenario=name,effects=effects,operationCount=1,
  declaredPossibleAdmissions=e['expectedCase']['plannedChildOperations'],failedCalls=failed,schedulerTicks=3,
  checkpoints=len(checkpoints),executionRecords=len(e['records']),configurationRecords=len(e['configuration']['records']),
  rehashedRefusals=e['rehashedRefusals'],unresolvedOperations=[],independentInspection=check,
  finalGrantCount=len(configuration['reg_grants']),finalParentState=parent['state']))
assert len(cases)==6
totals=dict(activations=sum(c['effects']['activations']for c in cases),completedCycles=0,
 canceledActivations=sum(c['effects']['canceledActivations']for c in cases),operations=6,
 declaredPossibleAdmissions=sum(c['declaredPossibleAdmissions']for c in cases),ticks=18,
 checkpoints=sum(c['checkpoints']for c in cases),executionRecords=sum(c['executionRecords']for c in cases),
 configurationRecords=sum(c['configurationRecords']for c in cases),rehashedRefusals=sum(c['rehashedRefusals']for c in cases),
 publicDenials=sum(len(c['failedCalls'])for c in cases if c['scenario']=='full_authority_withdrawal'))
assert totals['activations']==totals['canceledActivations']==4 and totals['declaredPossibleAdmissions']==14
assert totals['checkpoints']==140 and totals['rehashedRefusals']==15 and totals['publicDenials']==16
value=dict(scope='Primary-agent acquired-capture audit; targeted synthetic assertions, not complete authority semantics.',
 cases=cases,totals=totals,originalRawRetained=proof['rawScratch']['path'],sourceIndexSha256=proof['sourceIndexSha256'],
 qualificationPassed=False,completeAuthorityHistoryChecked=False,requiredMatrixCoverageChecked=False,physicalMeasurementChecked=False)
with (R/'data-audit.json').open('x')as f:f.write(json.dumps(value,indent=2)+'\n')
print(json.dumps(totals))
