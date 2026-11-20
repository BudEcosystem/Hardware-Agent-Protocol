"""Seal passing pure evidence, failed actual evidence and explicit retention loss."""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PRIOR=ROOT/'artifacts/verification/lifecycle-progress-links/attempt63-validation-walk-evaluation/index.json'
CHECKPOINT=ROOT/'artifacts/verification/lifecycle-progress-links/attempt64-io-proof-batch'
def read(path):return json.loads(path.read_bytes())
def sha(path):
    assert not path.is_symlink() and path.is_file() and path.stat().st_size<=16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
assert not (BASE/'index.json').exists() and not CHECKPOINT.exists()
assert sha(PRIOR)=='71c779046106b2671109ea79197bb70f065d75efe7251b510792b6c98733af7d'
actual=read(BASE/'RESULTS.json');pure=read(BASE/'PURE-RESULTS.json');retained=read(BASE/'RETENTION-RECHECK.json')
assert actual['stageStatus']=='verified-progress-actual-scope-failed' and not actual['actualScopePassed'] and actual['goalStatus']=='active'
assert actual['requestedCases']==30 and actual['caseManifests']==19 and actual['originalMaxWallMs']==60000
assert not actual['importReached'] and actual['workerUnresolvedEffects'] is None and actual['workerCaseDatabasesOpened']==0
assert len(actual['ownerAndWriterLocks'])==37 and len(actual['readonlySourceDatabases'])==4
assert pure['status']=='verified-pure-controls' and pure['tests']==63 and pure['sqliteOpens']==0
assert retained['status']=='retained-copies-verified' and retained['databasesOpened']==0 and not retained['attemptsRerun']
for name,pin in retained['sourcePins'].items():
    folder=BASE/name;assert sha(folder/'index.json')==pin
    for row in read(folder/'index.json')['files']:
        path=(ROOT if name.startswith('implementation') else folder)/row['path']
        assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
for scope in retained['scopes']:
    attempt=BASE/scope['harness']/'attempts'/scope['attempt']
    assert sha(attempt/'result.json')==scope['resultSha256']
    result=read(attempt/'result.json');assert result['status']==scope['originalStatus'] and result['childState']=='exited'
    for row in read(attempt/'scratch-index.json'):
        path=attempt/'scratch'/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
links=read(ROOT/'artifacts/verification/project-links.json')
assert links['missing']==[] and sha(ROOT/'scripts/check_project_links.py')==links['checker_sha256']
for row in links['files']:assert sha(ROOT/row['path'])==row['sha256']
files=[]
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():files.append(dict(path=path.relative_to(BASE).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
write(BASE/'index.json',dict(scope='63 pure controls pass; actual original 30-case scope fails before import; original raw trees later absent and retained copies reverified; full goal active',files=files))
selected={ROOT/'README.md',ROOT/'PROGRESS.md',ROOT/'docs/control-storage.md',
    ROOT/'docs/prompt-to-pat.md',ROOT/'docs/io-driver-hub-control.md',
    ROOT/'scripts/check_project_links.py',ROOT/'artifacts/verification/project-links.json',PRIOR}
selected.update(path for path in BASE.iterdir() if path.is_file())
selected.update(BASE.glob('implementation*/index.json'))
selected.update(BASE.glob('implementation*/README.md'))
selected.update(BASE.glob('harness*/index.json'))
copies=[]
for path in sorted(selected):
    relative=path.relative_to(ROOT);target=CHECKPOINT/'inputs'/relative
    target.parent.mkdir(parents=True,exist_ok=True);body=path.read_bytes()
    with target.open('xb') as stream:stream.write(body)
    assert target.read_bytes()==path.read_bytes()==body
    copies.append(dict(source=relative.as_posix(),copy=target.relative_to(ROOT).as_posix(),bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT/'index.json',dict(stageIndexSha256=sha(BASE/'index.json'),stageFiles=len(files),pureTests=63,
    actualScopePassed=False,requestedCases=30,caseManifests=19,importReached=False,
    rawRecheckStates=[s['currentRawState'] for s in retained['scopes']],retainedCopiesVerified=True,
    publicRuntimeChanged=False,goalStatus='active',markdownFiles=links['project_markdown_files'],
    localLinks=links['local_links_checked'],missing=[],files=copies))
print(json.dumps(dict(stageFiles=len(files),stageIndexSha256=sha(BASE/'index.json'),
    checkpointFiles=len(copies),checkpointIndexSha256=sha(CHECKPOINT/'index.json'),goalStatus='active')))
