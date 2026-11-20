"""Inspect original deliberately invalid control rows without repair or Runtime."""
import hashlib,json,sqlite3,sys
from pathlib import Path
B=Path.cwd()/'artifacts/implementation/pat-io-execution-handoff';F=B/'results'/sys.argv[1];R=F/'attempt/scratch'
def read(p):return json.loads(p.read_bytes())
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
proof=read(F/'proof.json');assert proof['status']=='passed' and proof['sqliteConnections']==28
cases=[]
work=R/'test_each_corrupt_control_record_is_refused_and_left_unrestored'
for i in range(11):
 check=read(work/('case-%02d.json'%i));dbpath=work/('case-%02d'%i)/'attempts.db';pin=sha(dbpath)
 db=sqlite3.connect(dbpath.as_uri()+'?mode=ro&immutable=1',uri=True)
 try:rows=db.execute('SELECT record FROM qs_attempts').fetchall()
 finally:db.close()
 assert sha(dbpath)==pin and len(rows)==1 and rows[0][0]==canonical(check['retainedCorruptRecord'])
 assert rows[0][0]!=canonical(check['originalRecord']) and check['restored'] is False and check['workerExecuted'] is False
 cases.append(dict(case=i,originalSha256=hashlib.sha256(canonical(check['originalRecord'])).hexdigest(),retainedCorruptSha256=hashlib.sha256(rows[0][0]).hexdigest(),databaseSha256=pin,corruptionStillPresent=True))
leases=[];work=R/'test_held_missing_and_replaced_leases_remain_unknown'
for kind in ('held','missing','replaced'):
 check=read(work/(kind+'.json'));record=check['record'];root=work/kind;dbpath=root/'attempts.db';pin=sha(dbpath)
 db=sqlite3.connect(dbpath.as_uri()+'?mode=ro&immutable=1',uri=True)
 try:rows=db.execute('SELECT record,active FROM qs_attempts').fetchall()
 finally:db.close()
 assert sha(dbpath)==pin and rows==[(canonical(record),1)] and record['state']=='running'
 original=root/record['attemptId']/('writer.lease'if kind=='held'else'retained-writer.lease')
 assert original.is_file() and original.stat().st_size==0 and check['workerExecuted'] is False and check['diagnosticPidOnly'] is True
 leases.append(dict(kind=kind,state=record['state'],diagnosticPid=record['pid'],originalLeaseBytesRetained=True,workerExecuted=False))
malformed=[];work=R/'test_malformed_return_bytes_are_preserved_without_success'
for i,expected in enumerate((b'',b'not canonical JSON',b'{}')):
 check=read(work/('case-%02d.json'%i));record=check['record'];root=work/('case-%02d'%i);dbpath=root/'attempts.db';pin=sha(dbpath)
 db=sqlite3.connect(dbpath.as_uri()+'?mode=ro&immutable=1',uri=True)
 try:rows=db.execute('SELECT record,return_bytes,active FROM qs_attempts').fetchall()
 finally:db.close()
 assert sha(dbpath)==pin and rows==[(canonical(record),expected,0)]
 assert (root/record['attemptId']/'worker-return.json').read_bytes()==expected
 assert record['archive']['transportComplete'] is False and record['archive']['unresolvedEffects'] is None
 malformed.append(dict(case=i,returnBytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),retainedExactly=True,transportComplete=False))
report=dict(scope='Independent read-only retained corrupt-row and malformed-return checks; simulated diagnostic ownership fixtures have no child.',corruptRecords=cases,unknownLeases=leases,malformedReturns=malformed,databasesUnchanged=True,workerExecuted=False,corruptStateRepaired=False,qualificationPassed=False)
with(F/'control-audit.json').open('x')as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(corruptRowsRetained=len(cases),unknownLeases=len(leases),malformedReturnsRetained=len(malformed),databasesUnchanged=True)))
