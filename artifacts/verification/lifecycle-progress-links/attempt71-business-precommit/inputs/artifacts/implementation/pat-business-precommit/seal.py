"""Seal the final business-commit candidate and all preceding local attempts."""
import hashlib
import json
import os
from pathlib import Path
import stat

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
SOURCE=BASE/'implementation03';HARNESS=BASE/'harness03';ATTEMPT=HARNESS/'attempts/attempt01'
PRIOR=ROOT/'artifacts/verification/lifecycle-progress-links/attempt70-integer-canonical/index.json'
CHECKPOINT=ROOT/'artifacts/verification/lifecycle-progress-links/attempt71-business-precommit'
def read(path):return json.loads(path.read_bytes())
def sha(path):
    info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_size<=16*1024*1024
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
def verify(prefix,row):
    path=prefix/row['path'];assert path.lstat().st_size==row['bytes'] and sha(path)==row['sha256']
assert not (BASE/'index.json').exists() and not CHECKPOINT.exists()
assert sha(PRIOR)=='2f59ed9ac61384271c95dbe537391b6ea8d709d1bf6311b5fbfa96af28b8e256'
assert sha(SOURCE/'index.json')=='2f1d6c5aeaf63e960058f9b838b5ecd1080fc17d78f207f0d0b14c248da2dad4'
assert sha(HARNESS/'index.json')=='dfd638911f42cd5f25d02ac21b2a0b59699c946c328eaeb0af040fc85c2a0689'
for folder,prefix in ((BASE/'implementation02',ROOT),(SOURCE,ROOT),
                       (BASE/'harness01',BASE/'harness01'),(BASE/'harness02',BASE/'harness02'),(HARNESS,HARNESS)):
    for row in read(folder/'index.json')['files']:verify(prefix,row)
audit=read(BASE/'RESULTS.json');result=read(ATTEMPT/'result.json');child=read(ATTEMPT/'child-result.json')
assert audit['status']=='verified-progress' and audit['testsRun']==child['testsRun']==51
assert audit['newTests']==29 and audit['inheritedJournalTests']==22
assert len(audit['readonlyDatabases'])==56 and len(audit['observations'])==29 and len(audit['vaultFixtures'])==5
assert audit['ownerLocks']==57 and audit['retainedFiles']==142 and audit['retainedBytes']==3948725
assert sha(ATTEMPT/'result.json')==audit['resultSha256']
assert sha(ATTEMPT/'child-result.json')==audit['childResultSha256']==result['childResultSha256']
assert result['status']==child['status']=='passed' and result['exitCode']==0 and not result['timedOut']
assert child['deniedEvents']==[] and all(child[key]==0 for key in ('failures','errors','skips','expectedFailures','unexpectedSuccesses'))
assert not any(audit[key] for key in ('publicRuntimeChanged','fullWorkerExecuted','catalogIntegrated','physicalObjectiveVerified'))
assert read(BASE/'harness01/attempts/attempt01/result.json')['status']=='failed'
assert read(BASE/'harness02/attempts/attempt01/child-result.json')['testsRun']==50
assert read(BASE/'harness02/attempts/attempt01/result.json')['status']=='passed'
assert read(BASE/'preparation-failure01.json')['projectCodeExecuted'] is False
for attempt in (BASE/'harness01/attempts/attempt01',BASE/'harness02/attempts/attempt01',ATTEMPT):
    for row in read(attempt/'scratch-index.json'):verify(attempt/'scratch',row)
links=read(ROOT/'artifacts/verification/project-links.json')
assert links['missing']==[] and links['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in links['files']:assert sha(ROOT/row['path'])==row['sha256']
files=[]
for parent,dirs,names in os.walk(BASE,followlinks=False):
    for name in dirs:assert not (Path(parent)/name).is_symlink()
    for name in names:
        path=Path(parent)/name
        files.append(dict(path=str(path.relative_to(BASE)),bytes=path.lstat().st_size,sha256=sha(path)))
write(BASE/'index.json',dict(scope='Final business commit boundary: 51 host controls and retained earlier preparation/harness results',
    files=sorted(files,key=lambda row:row['path']),publicRuntimeChanged=False,catalogIntegrated=False,goalStatus='active'))
selected={ROOT/'README.md',ROOT/'PROGRESS.md',ROOT/'docs/control-storage.md',ROOT/'docs/prompt-to-pat.md',
    ROOT/'docs/io-driver-hub-control.md',ROOT/'scripts/check_project_links.py',ROOT/'artifacts/verification/project-links.json',PRIOR}
selected.update(path for path in BASE.iterdir() if path.is_file())
for folder in (SOURCE,HARNESS):selected.update(path for path in folder.iterdir() if path.is_file())
for folder in (BASE/'harness01/attempts/attempt01',BASE/'harness02/attempts/attempt01',ATTEMPT):
    selected.update(path for path in folder.iterdir() if path.is_file())
selected.add(BASE/'implementation02/index.json')
selected.add(BASE/'harness01/index.json');selected.add(BASE/'harness02/index.json')
copies=[]
for path in sorted(selected):
    body=path.read_bytes();relative=path.relative_to(ROOT);target=CHECKPOINT/'inputs'/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(body)
    assert path.read_bytes()==target.read_bytes()
    copies.append(dict(source=str(relative),copy=str(target.relative_to(ROOT)),bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT/'index.json',dict(stageIndexSha256=sha(BASE/'index.json'),stageFiles=len(files),
    sourceIndexSha256=sha(SOURCE/'index.json'),harnessIndexSha256=sha(HARNESS/'index.json'),
    hostTests=51,newTests=29,inheritedTests=22,retainedFiles=142,readonlyDatabases=56,
    publicRuntimeChanged=False,catalogIntegrated=False,physicalObjectiveVerified=False,goalStatus='active',
    markdownFiles=links['project_markdown_files'],localLinks=links['local_links_checked'],missing=[],files=copies))
print(json.dumps(dict(stageFiles=len(files),stageIndexSha256=sha(BASE/'index.json'),checkpointFiles=len(copies),
    checkpointIndexSha256=sha(CHECKPOINT/'index.json'),tests=51,goalStatus='active')))
