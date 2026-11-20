"""Summarize a retained terminal process attempt for choosing its specific audit."""
import hashlib,json,sqlite3,sys
from pathlib import Path
B=Path.cwd()/'artifacts/implementation/pat-io-execution-handoff';F=B/'results'/sys.argv[1];A=F/'attempt'
def read(p):return json.loads(p.read_bytes())
result=read(A/'result.json');assert result['childState']=='exited' and not Path('/proc',str(result['pid'])).exists()
paths=list((A/'scratch').glob('*/supervisor/attempts.db'));assert len(paths)==1
p=paths[0];assert not any(p.with_name(p.name+s).exists() for s in ('-wal','-shm','-journal'))
pin=hashlib.sha256(p.read_bytes()).hexdigest();db=sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True)
try:rows=db.execute('SELECT record,return_bytes FROM qs_attempts').fetchall()
finally:db.close()
assert hashlib.sha256(p.read_bytes()).hexdigest()==pin and len(rows)==1
record=json.loads(rows[0][0]);returned=json.loads(rows[0][1]) if rows[0][1] is not None else None
states=[s for g in read(F/'state-audit.json')['groups'] for s in g['states']]
groups=[dict(status=g['groupStatus'],error=g['groupError'],completedCases=g['completedCases']) for g in read(F/'state-audit.json')['groups']]
work=p.parent.parent;crash=work/'prepared/crash-receipt.json';before=read(crash) if crash.exists() else None
print(json.dumps(dict(status=result['status'],target=read(A/'harness/targets.json')['targets'][0],
    counts=result['counts'],history=record['history'],reason=record['reason'],archive=record['archive'],
    returned=returned is not None,groups=groups,states=len(states),uninspectedStates=sum(s.get('inspected') is False for s in states),
    crashPhase=before['phase'] if before else None,preCrashReason=before['record']['reason'] if before else None,
    logTail=(A/'output.log').read_text()[-5000:]),indent=2))
