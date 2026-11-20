"""Audit all distinct control evidence and release one complete actual run."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
SOURCE=ROOT/'artifacts/implementation/supervisor-storage-bindings/implementation01'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('x') as stream:json.dump(v,stream,indent=2);stream.write('\n')
def verify(index,prefix,pin):
    assert sha(index)==pin
    for row in read(index)['files']:
        p=prefix/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
def identity(path):
    info=path.lstat();assert stat.S_ISDIR(info.st_mode) and not path.is_symlink()
    return dict(device=info.st_dev,inode=info.st_ino,uid=info.st_uid,mode=stat.S_IMODE(info.st_mode),sticky=bool(info.st_mode&stat.S_ISVTX))
def inventory(root):
    rows=[]
    for p in sorted(root.rglob('*')):
        assert not p.is_symlink()
        if p.is_file():
            assert p.stat().st_size<=16777216
            rows.append(dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    assert sum(r['bytes'] for r in rows)<=268435456
    return rows
verify(SOURCE/'index.json',ROOT,'ffcace54bb02211d47e2f69febfb2f7f1566d6ee6dcb8264a3f10ecef5a8534f')
verify(BASE/'control-harness-index.json',BASE,'6c45843e89b771776eae5e608f920a3aeafd4a33efbd619e521c5b4d78e65e24')
verify(BASE/'harness02/index.json',BASE/'harness02','c131c5b7947ed9267765738b534b413a63bba9dd416d9f3fd3a18db6ef36bf99')
verify(BASE/'harness01/index.json',BASE/'harness01','b53a90f96fbe5e15b4531c3b3474eb212d98a3d0fcb14f06111e82f1434e5873')
assert not (BASE/'harness01/attempts').exists()
assert read(BASE/'harness02/CONTROL_RESULTS.json')['passed']
selection=read(BASE/'control-selection.json')
expected=[t for s in selection['scopes'] for t in s['targets']]
assert len(expected)==len(set(expected))==71
records=[];certified=[];diagnostics=0;retained_failures=[];raw_bytes=0
for parent in (BASE,BASE/'harness02'):
    selected=read(parent/'control-selection.json')
    for scope in selected['scopes']:
        out=parent/'controls'/scope['name']
        if not out.exists():
            assert parent==BASE;continue
        result=read(out/'result.json');config=read(out/'config.json');intent=read(out/'intent.json')
        assert config['targets']==scope['targets']==intent['targets']
        assert result['sourceUnchanged'] and result['error'] is None and result['elapsedSeconds']<60
        assert intent['wallSeconds']==60 and intent['cpuSeconds']==40 and intent['addressSpaceBytes']==536870912 and intent['fdLimit']==128
        assert intent['maxFileBytes']==16777216 and intent['maxScratchBytes']==268435456
        assert len(config['inputs'])==309
        for row in config['inputs']:
            p=out/'project'/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']==sha(SOURCE/'project'/row['path'])
        assert sha(out/'control_child.py')==intent['childSha256']==sha(BASE/'control_child.py')
        for row in config['externalInputs']:
            p=Path(row['resolvedPath']);assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
        assert not Path('/proc',str(read(out/'started.json')['pid'])).exists()
        before=read(out/'raw-scratch-before.json');after=read(out/'raw-scratch-after.json');raw=Path(before['path'])
        assert identity(raw)==before['identity']==after['identity']
        assert identity(raw.parent)==before['parentIdentity']==after['parentIdentity']
        held=[]
        try:
            for lease in read(out/'writer-quiescence.json')['held']:
                p=raw/lease['path'];fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW);held.append(fd);info=os.fstat(fd)
                assert info.st_dev==lease['device'] and info.st_ino==lease['inode'] and info.st_size==0 and info.st_nlink==1
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            rows=inventory(raw);assert rows==read(out/'scratch-index.json')==inventory(out/'scratch')
            assert sum(r['bytes'] for r in rows)==result['scratchBytes'] and len(rows)==result['scratchFiles']
            raw_bytes+=result['scratchBytes']
        finally:
            for fd in held:os.close(fd)
        if result['passed']:
            child=result['child'];counts=child['counts']
            assert child==read(out/'child-result.json') and child['passed'] and child['executed']==scope['targets']
            assert not child['errors'] and not child['denied'] and result['exitCode']==0
            assert counts['testsRun']==len(scope['targets']) and all(v==0 for k,v in counts.items() if k!='testsRun')
            certified+=scope['targets'];diagnostics+=len(child['diagnosticLeaseChildren'])
            if parent.name=='harness02':assert 0<=sum(result['childCpu'].values())<=41
        else:
            assert parent==BASE and scope['name']=='legacy-handoff-02' and result['exitCode']==-9 and result['child'] is None
            retained_failures.append(str(out.relative_to(BASE)))
        records.append(dict(scope=str(out.relative_to(BASE)),passed=result['passed'],elapsedSeconds=result['elapsedSeconds'],
            resultSha256=sha(out/'result.json'),rawFiles=len(rows),rawBytes=result['scratchBytes']))
assert len(certified)==len(set(certified))==71 and set(certified)==set(expected) and diagnostics==1
assert retained_failures==['controls/legacy-handoff-02'] and len(records)==48
receipt=read(ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json')
for row in receipt['files']:assert sha(ROOT/row['path'])==row['sha256']
stage_bytes=sum(p.stat().st_size for p in BASE.rglob('*') if p.is_file())
assert stage_bytes+raw_bytes<1024**3
write(BASE/'CONTROL_AUDIT.json',dict(status='verified-71-distinct-controls',tests=71,originalCompletePasses=28,
    individualCompletePasses=43,completePassingScopes=47,retainedFailedScopes=retained_failures,
    originalFourteenScopeProfilePassed=False,diagnosticBatchingChanged=True,aggregateDiagnosticBudgetIncreased=True,
    candidateUnchanged=True,childUnchanged=True,diagnosticLeaseChildren=1,qualificationWorkers=0,
    runtimeInputsUnchanged=244,rawScratchBytes=raw_bytes,retainedStageBytes=stage_bytes,records=records,
    sourceIndexSha256=sha(SOURCE/'index.json'),reviewer='primary-agent',independentReview=False))
write(BASE/'actual-release.json',dict(controlAuditSha256=sha(BASE/'CONTROL_AUDIT.json'),distinctControls=71,
    sourceIndexSha256=sha(SOURCE/'index.json'),harnessIndexSha256=sha(BASE/'harness01/index.json'),
    originalCases=30,workerMaxWallMs=60000,parentSeconds=180,maxParentSqliteOpens=6,
    maxFileBytes=16777216,maxScratchBytes=268435456,plannedWorkerLaunches=1,plannedApplicationInvocations=1,
    oracleSubstitution=False,physicalExecution=False,publicRuntimeChanged=False,reviewer='primary-agent',independentReview=False))
print(json.dumps(dict(status='released-one-complete-actual-run',controls=71,passingScopes=47,retainedFailedScopes=1,stageBytes=stage_bytes,rawBytes=raw_bytes)))
