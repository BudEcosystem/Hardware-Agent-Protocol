"""Read-only evidence audit; never imports HMS or opens a database."""
import ast
import hashlib
import json
import os
from pathlib import Path
import stat

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('x') as stream:json.dump(v,stream,indent=2);stream.write('\n')
def verify(index,prefix,pin):
    assert sha(index)==pin
    rows=read(index)['files']
    for row in rows:
        p=prefix/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
    return len(rows)
previous=ROOT/'artifacts/verification/service-storage-contract'
prior=verify(previous/'index.json',previous,'27b3a34cb57a9722808463e169c68f98a416dded83f9d34289974f45949a698d')
assert prior==146
frozen=verify(BASE/'implementation01/index.json',ROOT,'ffcace54bb02211d47e2f69febfb2f7f1566d6ee6dcb8264a3f10ecef5a8534f')
assert frozen==312
runtime=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
assert sha(runtime)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
receipt=read(runtime);assert receipt['passed'] and receipt['tests']==866 and len(receipt['files'])==244
for row in receipt['files']:assert sha(ROOT/row['path'])==row['sha256']
selection=read(BASE/'control-selection.json');assert selection['tests']==71 and len(selection['scopes'])==14
scope=BASE/'controls/legacy-authority-01';config=read(scope/'config.json')
result=read(scope/'result.json');child=read(scope/'child-result.json')
assert result['passed'] is False and result['exitCode']==1 and result['error'] is None and result['sourceUnchanged']
assert result['elapsedSeconds']<60 and result['scratchFiles']==0 and result['scratchBytes']==0
assert child['counts']==dict(testsRun=1,failures=0,errors=1,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert child['databaseOpens']==child['diagnosticLeaseChildren']==child['denied']==[]
assert child['executed']==[selection['scopes'][0]['targets'][0]]
assert read(scope/'scratch-index.json')==[]
assert (scope/'control_child.py').read_bytes()==(BASE/'control_child.py').read_bytes()
assert len(config['inputs'])==309
for row in config['inputs']:
    a=scope/'project'/row['path'];b=BASE/'implementation01/project'/row['path']
    assert a.stat().st_size==row['bytes'] and sha(a)==row['sha256']==sha(b)
log=(scope/'output.log').read_text();assert 'UNSAFE_STATE_ANCESTOR' in log and 'FAILED (errors=1)' in log
assert not list((scope/'scratch').rglob('*.db'))
assert len(list((BASE/'controls').iterdir()))==1
pid=read(scope/'started.json')['pid'];assert not Path('/proc',str(pid)).exists()
scratch=Path(config['scratch']);ancestors=[]
for path in [*reversed(scratch.parents),scratch]:
    info=path.lstat();ancestors.append(dict(path=str(path),uid=info.st_uid,device=info.st_dev,inode=info.st_ino,
        mode=oct(stat.S_IMODE(info.st_mode)),groupOrOtherWritable=bool(info.st_mode&0o022),sticky=bool(info.st_mode&stat.S_ISVTX)))
rejected=next(row for row in ancestors[:-1] if row['groupOrOtherWritable'] and not row['sticky'])
assert rejected['path']=='/home/bud/Desktop/bud' and rejected['mode']=='0o775'
inspection=read(BASE/'inspection02.json');assert inspection['importEffects'] is False and inspection['producerImageFiles']==268
assert (BASE/'inspection02.stderr').read_bytes()==b''
source_files=list((BASE/'implementation01/project').rglob('*.py'))
for p in source_files:ast.parse(p.read_bytes())
original=read(BASE/'original-inputs.json')['files'];changed=[]
for row in original:
    assert sha(ROOT/row['source'])==row['sha256']
    if sha(BASE/'implementation01/project'/row['path'])!=row['sha256']:changed.append(row['path'])
assert len(original)==306 and len(changed)==7
baseline=read(ROOT/'artifacts/implementation/pat-statement-cache/implementation01/identity-pins.json')
for name in ('tests/test_vault_catalog_process.py','tests/test_vault_original_run.py'):
    row=next(r for r in original if r['path']==name);body=(ROOT/row['source']).read_text()
    for field in ('consumer','host','vault','legacy'):body=body.replace(baseline[field],inspection[field])
    assert body==(BASE/'implementation01/project'/name).read_text()
write(BASE/'ancestor-audit.json',dict(ancestors=ancestors,firstRejected=rejected,permissionsModified=False))
files=[p for p in BASE.rglob('*') if p.is_file()]
assert not any(p.is_symlink() for p in BASE.rglob('*'))
assert sum(p.stat().st_size for p in files)<1024**3
audit=dict(status='verified-retained-failure',reviewer='primary-agent',independentReview=False,
    previousStageFilesVerified=prior,frozenSourceFilesVerified=frozen,copiedProjectFilesVerified=309,
    runtimeInputsUnchanged=244,publicBaselineTests=866,publicTestsRepeated=False,selectedControls=71,
    controlsStarted=1,controlsPassed=0,controlErrors=1,unrunControls=70,controlScopesPlanned=14,controlScopesExecuted=1,
    parentExitCode=1,originalParentAbsent=True,databaseOpens=0,diagnosticChildren=0,qualificationWorkers=0,
    splitLedgerCreated=False,completeActualMatrixExecuted=False,sourceAstParsed=len(source_files),
    importInspectionPassed=True,producerImageFiles=268,preparationFailuresPreserved=2,
    originalProjectFilesUnchanged=299,changedExistingProductionFiles=5,newProductionFiles=1,
    changedExistingTestsOnlyIdentityLiterals=2,sharedPermissionsChanged=False,retryPerformed=False,
    hardQuotaEnforced=False,backedControlCapacity=False,hotJournalRecoveryQualified=False,
    physicalDeviceExecuted=False,publicRuntimeChanged=False,scope='Evidence/source audit only; candidate validation incomplete')
write(BASE/'AUDIT.json',audit)
write(BASE/'RESULTS.json',dict(status='candidate-unvalidated-control-harness-refused',auditPassed=True,
    candidateTestsPassed=False,sourceIndexSha256=sha(BASE/'implementation01/index.json'),auditSha256=sha(BASE/'AUDIT.json'),
    controlsStarted=1,controlsPassed=0,controlErrors=1,controlsNotRun=70,completeActualRun='not started',
    cause='Scratch under non-sticky group-writable ancestors; stock pathname guard refused before SQLite',
    originalLimitsUnchanged=True,goalComplete=False))
print(json.dumps(audit,indent=2))
