"""Seal verified catalog controls and the complete original application scope."""
import hashlib
import json
import os
from pathlib import Path
import stat

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
SOURCE=BASE/'implementation03';HARNESS=BASE/'harness23';ATTEMPT=HARNESS/'attempts/attempt01-actual'
PRIOR=ROOT/'artifacts/verification/lifecycle-progress-links/attempt72-vault-batch/index.json'
CHECKPOINT=ROOT/'artifacts/verification/lifecycle-progress-links/attempt73-vault-catalog'
def read(path):return json.loads(path.read_bytes())
def sha(path):
    info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_size<=16*1024*1024
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
def row(path,root):return dict(path=str(path.relative_to(root)),bytes=path.lstat().st_size,sha256=sha(path))
def verify(prefix,value):assert row(prefix/value['path'],prefix)=={k:value[k] for k in ('path','bytes','sha256')}
assert not (BASE/'index.json').exists() and not CHECKPOINT.exists()
assert sha(PRIOR)=='46110f196298ffc66430691e27929cd9b18e156215a93a0c468ce3262a69c10f'
assert sha(SOURCE/'index.json')=='5ffd155119c12c73d6090a6684973f7f14474ebbfdb0fce228f880476df4e3a9'
assert sha(HARNESS/'index.json')=='eb5a17ffdffaaa5ef208fd623f0db8e7c19b7634cf26e370b9fe00880d827437'
for source in sorted(BASE.glob('implementation*')):
    for value in read(source/'index.json')['files']:verify(ROOT,value)
for harness in sorted(BASE.glob('harness*')):
    if not harness.is_dir():continue
    values=read(BASE/'harness23-inputs-correction.json')['files'] if harness==HARNESS else read(harness/'index.json')['files']
    for value in values:verify(harness,value)
controls=read(BASE/'CONTROL_RESULTS.json');actual=read(BASE/'RESULTS.json');result=read(ATTEMPT/'result.json')
assert controls['status']=='verified-controls' and controls['testsRun']==19 and len(controls['readonlyDatabases'])==76
assert controls['retainedFiles']==1149 and controls['originalOwnerAndWriterLocks']==99 and len(controls['admissions'])==4
assert len(controls['intentionallyMissingBodies'])==2 and len(controls['failedScopesRetained'])==4
assert actual['stageStatus']=='verified-progress-actual-scope-passed' and actual['actualScopePassed']
assert actual['catalogControls']==19 and actual['catalogIntegrated'] and actual['sourceApplicationInvocations']==1
assert actual['caseManifests']==actual['requestedCases']==actual['caseDirectories']==30
assert actual['workerCaseDatabasesOpened']==0 and len(actual['readonlySourceDatabases'])==4 and len(actual['ownerAndWriterLocks'])==57
assert actual['rawFiles']==4264 and actual['rawBytes']==35484362
assert actual['catalogObservation']['oneCompletedApplication'] and actual['catalogObservation']['originalKeyReplay']
assert actual['catalogObservation']['activations']==actual['catalogObservation']['completions']==1
assert actual['catalogObservation']['cancellations']==0 and actual['catalogObservation']['coldVaultAndBridgeHistory']
assert result['status']=='passed' and result['currentPass'] and result['exitCode']==0 and result['childState']=='exited'
assert result['elapsedSeconds']<=180 and actual['observedSpawnToSettledMs']<=60000
assert sha(ATTEMPT/'result.json')==actual['resultSha256']
assert not actual['publicRuntimeChanged'] and not actual['physicalObjectiveVerified']
for scope in controls['scopes']:
    attempt=BASE/scope['harness']/'attempts/attempt01'
    assert sha(attempt/'result.json')==scope['resultSha256']
    for value in read(attempt/'scratch-index.json')['files']:verify(attempt/'scratch',value)
for value in read(ATTEMPT/'scratch-index.json'):verify(ATTEMPT/'scratch',value)
first_actual=read(BASE/'harness22/attempts/attempt01-actual/result.json')
assert first_actual['status']=='failed' and first_actual['childState']=='exited' and first_actual['scratchRetainedBytes']==0
assert read(BASE/'harness22/attempts/attempt01-actual/worker-accounting-launch-audit.json')==[]
verified=dict(source=str(SOURCE.relative_to(BASE)),sourceIndexSha256=sha(SOURCE/'index.json'),
    controls=controls['scopes'],actualHarness=HARNESS.name,actualHarnessIndexSha256=sha(HARNESS/'index.json'),
    actualHarnessIndexCorrectionSha256=sha(BASE/'harness23-inputs-correction.json'),
    actualResultSha256=sha(ATTEMPT/'result.json'),actualAudit='audit_actual02.py',actualAuditSha256=sha(BASE/'audit_actual02.py'),
    testCount=19,actualMatrixCases=30,applicationInvocations=1,aggregateControlTimingPass=False,
    originalFailedScopesRetained=True,publicRuntimeChanged=False,physicalObjectiveVerified=False)
write(BASE/'VERIFIED_SELECTION.json',verified)
links=read(ROOT/'artifacts/verification/project-links.json')
assert links['missing']==[] and links['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for value in links['files']:assert sha(ROOT/value['path'])==value['sha256']
files=[]
for parent,dirs,names in os.walk(BASE,followlinks=False):
    for name in dirs:assert not (Path(parent)/name).is_symlink()
    for name in names:files.append(row(Path(parent)/name,BASE))
write(BASE/'index.json',dict(scope='Authority-vault recorded catalog: 19 controls and complete 30-case worker through one completed simulated PAT and cold original-key history',
    files=sorted(files,key=lambda value:value['path']),sourceIndexSha256=sha(SOURCE/'index.json'),
    controls=19,actualMatrixCases=30,applicationInvocations=1,publicRuntimeChanged=False,
    physicalObjectiveVerified=False,goalStatus='active'))
selected={ROOT/'README.md',ROOT/'PROGRESS.md',ROOT/'docs/control-storage.md',ROOT/'docs/prompt-to-pat.md',
    ROOT/'docs/io-driver-hub-control.md',ROOT/'scripts/check_project_links.py',ROOT/'artifacts/verification/project-links.json',PRIOR}
for folder in (BASE,SOURCE,HARNESS,ATTEMPT):selected.update(path for path in folder.iterdir() if path.is_file())
for scope in controls['scopes']:
    folder=BASE/scope['harness'];selected.add(folder/'index.json')
    for name in ('result.json','test-return.json','actual-tests.json','imports.json'):
        selected.add(folder/'attempts/attempt01'/name)
copies=[]
for path in sorted(selected):
    body=path.read_bytes();relative=path.relative_to(ROOT);target=CHECKPOINT/'inputs'/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(body)
    assert sha(target)==sha(path)
    copies.append(dict(source=str(relative),copy=str(target.relative_to(ROOT)),bytes=len(body),sha256=sha(path)))
write(CHECKPOINT/'index.json',dict(stageIndexSha256=sha(BASE/'index.json'),stageFiles=len(files),
    sourceIndexSha256=sha(SOURCE/'index.json'),harnessIndexSha256=sha(HARNESS/'index.json'),
    controlTests=19,actualMatrixCases=30,completedApplicationInvocations=1,
    controlRetainedFiles=1149,actualRetainedFiles=4264,readonlyControlDatabases=76,readonlyActualSourceDatabases=4,
    publicRuntimeChanged=False,physicalObjectiveVerified=False,goalStatus='active',
    markdownFiles=links['project_markdown_files'],localLinks=links['local_links_checked'],missing=[],files=copies))
print(json.dumps(dict(stageFiles=len(files),stageIndexSha256=sha(BASE/'index.json'),checkpointFiles=len(copies),
    checkpointIndexSha256=sha(CHECKPOINT/'index.json'),controlTests=19,actualMatrixCases=30,
    completedApplicationInvocations=1,goalStatus='active')))
