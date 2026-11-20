"""Read-only failed owner-loss test: retain committed failure, not success."""
import hashlib,json,sqlite3,sys
from pathlib import Path
B=Path.cwd()/'artifacts/implementation/pat-io-supervision-recovery';F=B/'results'/sys.argv[1];A=F/'attempt'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
p=read(F/'proof.json');assert p['status']=='failed';target=read(A/'harness/targets.json')['targets'][0];work=A/'scratch'/target.rsplit('.',1)[1];root=work/'supervisor';path=root/'attempts.db';pin=sha(path)
db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
try:
 assert db.execute('SELECT count(*),sum(active) FROM qs_attempts').fetchone()==(1,0)
 request_raw,record_raw,returned_raw=db.execute('SELECT request,record,return_bytes FROM qs_attempts').fetchone()
finally:db.close()
assert sha(path)==pin;request=json.loads(request_raw);record=json.loads(record_raw);archive=record['archive']
assert canonical(record)==record_raw and archive['transportComplete'] is False and archive['semanticQualificationVerified'] is False and archive['unresolvedEffects'] is None
receipt=read(work/'prepared/crash-receipt.json');driver=read(work/'driver-exit.json');assert driver['exitCode']==receipt['hardExitCode']==91
for name,value in driver['streams'].items():
 log=work/('driver-'+name+'.log');assert log.stat().st_size==value['bytes'] and sha(log)==value['sha256']
assert len(receipt['launches'])==1 and receipt['record']['attemptId']==record['attemptId']
if receipt['phase']=='archived':assert receipt['record']==record and archive['ownerRecovered'] is False
else:assert archive['ownerRecovered'] is True and archive['exitCode'] is None
attempt=root/record['attemptId'];assert read(attempt/'input.json')['request']==request
assert (attempt/'bundle/header.json').read_bytes()==canonical(request['bundleHeader'])
for row in request['bundleHeader']['manifest']:
 f=attempt/'bundle'/row['path'];assert f.stat().st_size==row['bytes'] and sha(f)==row['sha256']
quiescence=read(A/'writer-quiescence.json');assert quiescence['ownerQuiescent'] and quiescence['records'][0]['writerQuiescent']
report=dict(scope='Retained owner-loss test failure; no replay or semantic success inferred after failed assertion.',target=target,phase=receipt['phase'],driverExit=91,history=record['history'],archive=archive,returnAvailable=returned_raw is not None,committedArchiveUnchanged=receipt['phase']=='archived',prelaunchInputsMatch=True,writerQuiescence=quiescence,ledgerUnchanged=True,qualificationPassed=False,replayAssertionReached=False)
with(F/'failure-audit.json').open('x')as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k]for k in ('phase','history','returnAvailable','committedArchiveUnchanged','replayAssertionReached')}))
