"""Read-only independent reduction of the acquired owned GPIO run and image."""
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-supervision';F=B/'results/attempt06-acquired-gpio';A=F/'attempt'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(raw):return 'sha256:'+hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
proof=read(F/'proof.json');result=read(A/'result.json');assert result['status']=='passed' and result['childState']=='exited'
assert not (Path('/proc')/str(result['pid'])).exists()
work=A/'scratch/test_complete_owned_gpio_group_retains_inputs_before_launch_and_replays';root=work/'supervisor'
database=root/'attempts.db';pin=sha(database)
db=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
try:
    assert db.execute('SELECT count(*),sum(active) FROM qs_attempts').fetchone()==(1,0)
    request_raw,record_raw,returned_raw=db.execute('SELECT request,record,return_bytes FROM qs_attempts').fetchone()
finally:db.close()
assert sha(database)==pin
request=json.loads(request_raw);record=json.loads(record_raw);returned=json.loads(returned_raw)
assert canonical(request)==request_raw and canonical(record)==record_raw and canonical(returned)==returned_raw
identifier=record['attemptId'];attempt=root/identifier;archive=record['archive']
assert record['state']=='archived' and record['history']==['admitted','launching','running','archived']
assert record['requestDigest']==digest(b'HMS-PAT-IO-SUPERVISOR-REQUEST-v0.1\0'+request_raw)==returned['requestDigest']
assert returned['attemptId']==identifier and returned['bundleDigest']==request['bundleDigest'] and returned['status']=='captured'
assert archive['exitCode']==0 and archive['transportComplete'] is True and archive['ownerRecovered'] is False
assert archive['semanticQualificationVerified'] is False and archive['totalDiskQuotaEnforced'] is False and archive['unresolvedEffects'] is None
assert archive['supervisorReason'] is None and archive['returnValidationFailure'] is None
assert archive['returnDigest']==digest(returned_raw) and (attempt/'worker-return.json').read_bytes()==returned_raw
launch=read(attempt/'input.json');assert launch['attemptId']==identifier and launch['request']==request
header=(attempt/'bundle/header.json').read_bytes();assert canonical(request['bundleHeader'])==header
assert request['bundleDigest']==digest(b'HMS-PAT-IO-RUN-BUNDLE-v0.1\0'+header)
for row in request['bundleHeader']['manifest']:
    p=attempt/'bundle'/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
output=attempt/'output';group=read(output/'result.json');matrix=read(output/'matrix.json')
assert group['status']=='captured' and group['error'] is None and len(group['cases'])==len(matrix['cases'])==30
assert returned['groupResultDigest']==digest((output/'result.json').read_bytes())
assert group['matrixDigest']==request['bundleHeader']['matrixDigest']==digest(b'HMS-PAT-IO-COMBINED-MATRIX-v0.1\0'+canonical(matrix))
chain=hashlib.sha256(b'HMS-PAT-IO-OUTPUT-CLOSURE-v0.1\0');files=[]
def walk(folder):
    for p in sorted(folder.iterdir(),key=lambda p:p.name):
        assert not p.is_symlink()
        if p.is_dir():walk(p)
        else:
            row=dict(path=p.relative_to(output).as_posix(),bytes=p.stat().st_size,sha256=sha(p))
            chain.update(canonical(row)+b'\n');files.append(row)
walk(output)
closure=dict(fileCount=len(files),bytes=sum(r['bytes'] for r in files),orderedDigest='sha256:'+chain.hexdigest())
assert closure==archive['evidenceIntegrity'] and closure['bytes']<=20*1024*1024
image=root/('code-'+request['supervisorIdentity'][7:]);project=A/'project'
expected={}
sources={*(project/'hms').rglob('*.py'),*(project/'schemas').glob('*.json'),*(project/'examples/wot').glob('*.json'),
    project/'research/protocols/wot-artifacts/td-schema-1.1.json',project/'protocol/endpoint/scenario-manifest.json'}
for p in sources:expected[p.relative_to(project).as_posix()]=dict(bytes=p.stat().st_size,sha256=sha(p))
tree=ast.parse((project/'supervisor/supervisor_contracts.py').read_bytes())
names=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SOURCE_FILES' for t in n.targets)))
supervisor_rows=[]
for name in names:
    p=project/'supervisor'/name;expected['supervisor/'+name]=dict(bytes=p.stat().st_size,sha256=sha(p))
    supervisor_rows.append(dict(path=name,sha256=sha(p)))
packages={}
for row in read(A/'external-before.json')['files']:
    if 'package' in row:
        value=dict(bytes=row['bytes'],sha256=row['sha256'])
        assert row['path'] not in packages or packages[row['path']]==value
        packages[row['path']]=value;expected['dependencies/'+row['path']]=value
actual={}
for p in image.rglob('*'):
    assert not p.is_symlink()
    assert p.stat().st_mode&0o777==(0o700 if p.is_dir() else 0o600)
    if p.is_file():actual[p.relative_to(image).as_posix()]=dict(bytes=p.stat().st_size,sha256=sha(p))
assert actual==expected
runtime=hashlib.sha256(b''.join(canonical(dict(path=p,sha256=packages[p]['sha256']))+b'\n' for p in sorted(packages))).hexdigest()
identity=digest(b'HMS-PAT-QUALIFICATION-SUPERVISOR-v0.1\0'+canonical(dict(sources=supervisor_rows,worker=request['implementation'],
    runtimeFiles=len(packages),runtimeDigest='sha256:'+runtime)))
assert identity==request['supervisorIdentity']
original=Path(proof['rawScratch']['path'])/'test_complete_owned_gpio_group_retains_inputs_before_launch_and_replays/supervisor'/identifier
lease=original/'writer.lease';info=lease.stat()
assert record['lease']==dict(device=str(info.st_dev),inode=str(info.st_ino)) and not (Path('/proc')/str(record['pid'])).exists()
fd=os.open(lease,os.O_RDONLY|os.O_NOFOLLOW)
try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
finally:os.close(fd)
checked=read(work/'inspection/supervisor-checks.json');summary=read(work/'inspection/summary.json')
assert checked['archive']==archive and checked['physicalAttemptId']==identifier and checked['phases']==['admitted','launching','spawned','producer_settled','archived']
for key in ('completeGroupCaptured','independentGroupInspection','exactReplayBeforeAndAfterReopen','changedSameKeyRefused','preLaunchInputsMatched','oneWorkerLaunched'):assert checked[key] is True
assert summary['independentOutcomeChecked'] is True and summary['qualificationPassed'] is False
states=read(F/'state-audit.json')['groups'][0]['states'];assert len(states)==26 and all(s['claims']==s['owners']==0 for s in states)
effects=[sum(s['effects'][i] or 0 for s in states) for i in range(3)]
report=dict(scope='Independent read-only retained input/result/image/control association and closure; no physical/service/quota attestation.',
    physicalAttemptId=identifier,logicalContext=request['context'],history=record['history'],archive=archive,outputClosure=closure,
    codeImageFiles=len(actual),codeImageBytes=sum(r['bytes'] for r in actual.values()),codeImageExactClosure=True,selectedRuntimeFiles=len(packages),
    originalLeaseIdentityMatched=True,originalLeaseCurrentlyFree=True,ownedWorkerNoLongerPresent=True,ledgerDatabaseUnchanged=True,
    cases=30,states=26,endpointEffects=dict(activations=effects[0],completed=effects[1],canceled=effects[2]),claims=0,owners=0,
    groupAccounting=group['accounting'],independentSummary=summary,qualificationPassed=False)
with (F/'owned-audit.json').open('x') as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('physicalAttemptId','history','outputClosure','codeImageFiles','codeImageBytes','selectedRuntimeFiles','cases','states','endpointEffects','claims','owners')}))
