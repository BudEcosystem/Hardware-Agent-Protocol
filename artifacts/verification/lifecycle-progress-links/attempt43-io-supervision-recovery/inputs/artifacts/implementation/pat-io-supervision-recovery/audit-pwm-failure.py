"""Retain the failed PWM supervisor boundary without qualification or rerun."""
import hashlib,json,sqlite3
from pathlib import Path
B=Path.cwd()/'artifacts/implementation/pat-io-supervision-recovery';F=B/'results/attempt03-failed-pwm';A=F/'attempt'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
proof=read(F/'proof.json');root=next((A/'scratch').glob('*/supervisor'));database=root/'attempts.db';pin=sha(database)
db=sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)
try:
 assert db.execute('SELECT count(*),sum(active) FROM qs_attempts').fetchone()==(1,0)
 request_raw,record_raw,returned=db.execute('SELECT request,record,return_bytes FROM qs_attempts').fetchone()
finally:db.close()
assert sha(database)==pin and returned is None
request=json.loads(request_raw);record=json.loads(record_raw);archive=record['archive'];output=root/record['attemptId']/'output'
assert archive['supervisorReason']=='SUPERVISOR_DEADLINE' and archive['exitCode']==-15 and archive['transportComplete'] is False
assert archive['unresolvedEffects'] is None and archive['semanticQualificationVerified'] is False
assert archive['returnValidationFailure']=='QUALIFICATION_RETURN_UNAVAILABLE' and not(output/'result.json').exists()
assert request['groupLimits']['maxWallMs']==60000
matrix=read(output/'matrix.json');assert len(matrix['cases'])==30
states=read(F/'state-audit.json')['groups'][0]['states'];complete=[s for s in states if s.get('inspected',True)];partial=[s for s in states if not s.get('inspected',True)]
assert len(states)==25 and len(partial)==1 and partial[0]['caseIndex']==28
raw=Path(proof['rawScratch']['path']);original=next(raw.glob('*/supervisor/*/output'))
timelines=[]
for folder in sorted(original.glob('case-*')):
 files=[p for p in folder.rglob('*')if p.is_file()];times=[p.stat().st_mtime_ns for p in files]
 timelines.append(dict(case=folder.name,files=len(files),firstFileMtimeNs=min(times),lastFileMtimeNs=max(times),manifestPresent=(folder/'manifest.json').exists()))
report=dict(scope='Failed owned PWM attempt, read-only partial-state observations; file mtimes are diagnostic, not trusted run timing.',reason='Original supervisor60000ms deadline',cause='Not established by this run; no performance profile was collected.',history=record['history'],archive=archive,groupReturnAvailable=False,declaredCases=30,caseDirectories=len(timelines),manifestFiles=sum(x['manifestPresent']for x in timelines),states=len(states),completeStatePairs=len(complete),incompleteState=partial[0],observedEffectsInCompletePairs=dict(zip(('activations','completed','canceled'),[sum(s['effects'][i]or 0 for s in complete)for i in range(3)])),observedClaimsInCompletePairs=sum(s['claims']for s in complete),observedOwnersInCompletePairs=sum(s['owners']for s in complete),aggregateUnresolvedEffects=None,leaseQuiescence=read(A/'writer-quiescence.json'),fileMtimeDiagnostics=timelines,ledgerUnchanged=True,workerRerun=False,qualificationPassed=False)
with(F/'failure-audit.json').open('x')as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k]for k in ('history','declaredCases','caseDirectories','manifestFiles','completeStatePairs','observedEffectsInCompletePairs','observedClaimsInCompletePairs','aggregateUnresolvedEffects')}))
