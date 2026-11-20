"""Seal the bounded batch candidate and its verified 60-control scope."""
import hashlib
import json
import os
from pathlib import Path
import stat

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
SOURCE=BASE/'implementation01';HARNESS=BASE/'harness01';ATTEMPT=HARNESS/'attempts/attempt01'
PRIOR=ROOT/'artifacts/verification/lifecycle-progress-links/attempt71-business-precommit/index.json'
CHECKPOINT=ROOT/'artifacts/verification/lifecycle-progress-links/attempt72-vault-batch'
def read(path):return json.loads(path.read_bytes())
def sha(path):
    info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_size<=16*1024*1024
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
def verify(prefix,row):
    path=prefix/row['path'];assert path.lstat().st_size==row['bytes'] and sha(path)==row['sha256']
assert not (BASE/'index.json').exists() and not CHECKPOINT.exists()
assert sha(PRIOR)=='734713aeb25035e6aacab37b7d903b31ac97f381137b6e03c83c0e153cfddc59'
assert sha(SOURCE/'index.json')=='71595be27f62d50424ec996a2fdd4b4cad1732f7315026d4009c5213cd657171'
assert sha(HARNESS/'index.json')=='00451d06df2d9fd39a5c9868eec6df7d571e72f74de46df6e31c33fa42133107'
for folder,prefix in ((SOURCE,ROOT),(HARNESS,HARNESS)):
    for row in read(folder/'index.json')['files']:verify(prefix,row)
audit=read(BASE/'RESULTS.json');result=read(ATTEMPT/'result.json');child=read(ATTEMPT/'child-result.json')
assert audit['status']=='verified-progress' and audit['testsRun']==child['testsRun']==60
assert (audit['batchTests'],audit['singleSnapshotTests'],audit['businessCommitTests'])==(25,6,29)
assert audit['jointBatchAdmissionScenarios']==4 and len(audit['jointAdmissionRows'])==4
assert len(audit['readonlyDatabases'])==audit['ownerLocks']==70 and len(audit['observationFiles'])==54
assert audit['retainedFiles']==194 and audit['retainedBytes']==2976200
assert len(audit['intentionallyCorruptBodies'])==2 and len(audit['intentionallyCorruptManifestScopes'])==1
assert audit['maximumBatch']['manifests']==32 and audit['maximumBatch']['uniqueBodies']==1
assert sha(ATTEMPT/'result.json')==audit['resultSha256']
assert sha(ATTEMPT/'child-result.json')==audit['childResultSha256']==result['childResultSha256']
assert result['status']==child['status']=='passed' and result['exitCode']==0 and not result['timedOut']
assert child['deniedEvents']==[] and all(child[key]==0 for key in ('failures','errors','skips','expectedFailures','unexpectedSuccesses'))
assert not any(audit[key] for key in ('publicRuntimeChanged','fullWorkerExecuted','catalogIntegrated','physicalObjectiveVerified'))
for row in read(ATTEMPT/'scratch-index.json'):verify(ATTEMPT/'scratch',row)
for row in audit['readonlyDatabases']:assert sha(ATTEMPT/'scratch'/row['path'])==row['sha256']
links=read(ROOT/'artifacts/verification/project-links.json')
assert links['missing']==[] and links['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in links['files']:assert sha(ROOT/row['path'])==row['sha256']
files=[]
for parent,dirs,names in os.walk(BASE,followlinks=False):
    for name in dirs:assert not (Path(parent)/name).is_symlink()
    for name in names:
        path=Path(parent)/name
        files.append(dict(path=str(path.relative_to(BASE)),bytes=path.lstat().st_size,sha256=sha(path)))
write(BASE/'index.json',dict(scope='Bounded multi-manifest snapshot: 60 controls, including real Journal commit and cleanup/replay boundaries',
    files=sorted(files,key=lambda row:row['path']),publicRuntimeChanged=False,catalogIntegrated=False,goalStatus='active'))
selected={ROOT/'README.md',ROOT/'PROGRESS.md',ROOT/'docs/control-storage.md',ROOT/'docs/prompt-to-pat.md',
    ROOT/'docs/io-driver-hub-control.md',ROOT/'scripts/check_project_links.py',ROOT/'artifacts/verification/project-links.json',PRIOR}
for folder in (BASE,SOURCE,HARNESS,ATTEMPT):selected.update(path for path in folder.iterdir() if path.is_file())
copies=[]
for path in sorted(selected):
    body=path.read_bytes();relative=path.relative_to(ROOT);target=CHECKPOINT/'inputs'/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(body)
    assert path.read_bytes()==target.read_bytes()
    copies.append(dict(source=str(relative),copy=str(target.relative_to(ROOT)),bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT/'index.json',dict(stageIndexSha256=sha(BASE/'index.json'),stageFiles=len(files),
    sourceIndexSha256=sha(SOURCE/'index.json'),harnessIndexSha256=sha(HARNESS/'index.json'),
    hostTests=60,batchTests=25,singleSnapshotTests=6,businessCommitTests=29,jointBatchAdmissionScenarios=4,
    retainedFiles=194,readonlyDatabases=70,maximumManifestSet=32,
    publicRuntimeChanged=False,catalogIntegrated=False,physicalObjectiveVerified=False,goalStatus='active',
    markdownFiles=links['project_markdown_files'],localLinks=links['local_links_checked'],missing=[],files=copies))
print(json.dumps(dict(stageFiles=len(files),stageIndexSha256=sha(BASE/'index.json'),checkpointFiles=len(copies),
    checkpointIndexSha256=sha(CHECKPOINT/'index.json'),tests=60,goalStatus='active')))
