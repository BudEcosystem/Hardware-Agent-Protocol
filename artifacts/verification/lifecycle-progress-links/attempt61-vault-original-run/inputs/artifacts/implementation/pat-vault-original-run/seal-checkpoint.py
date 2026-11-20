"""Seal audited failed actual execution and explicit next requirements."""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
CHECKPOINT=ROOT/'artifacts/verification/lifecycle-progress-links/attempt61-vault-original-run'
PRIOR=ROOT/'artifacts/verification/lifecycle-progress-links/attempt60-vault-authority-controls/index.json'
def read(path): return json.loads(path.read_bytes())
def sha(path):
    assert not path.is_symlink() and path.stat().st_size<=16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream: json.dump(value,stream,indent=2); stream.write('\n')
assert not (BASE/'index.json').exists() and not CHECKPOINT.exists()
assert sha(PRIOR)=='fd3bc4c0f23d9f66ae7b007148b4fe6d61034e19ee7f158fd1634beb654aff68'
report=read(BASE/'RESULTS.json')
assert report['stageStatus']=='verified-progress-actual-scope-failed' and report['goalStatus']=='active'
assert not report['productionChanged'] and not report['actualOriginalRunProfileVerified']
assert report['requestedCases']==report['caseDirectories']==30 and report['caseManifests']==29
assert report['originalMaxWallMs']==60000 and report['supervisorReason']=='SUPERVISOR_DEADLINE'
assert report['workerUnresolvedEffects'] is None and report['transportComplete'] is False
assert report['importIntents']==report['evidenceManifests']==report['publications']==report['sourceApplicationInvocations']==0
assert not report['importReached'] and not report['catalogIntegrated']
assert report['readonlyDatabases']==4 and len(report['ownerAndWriterLocks'])==57
assert report['producerImageFiles']==262 and report['sourceIdentitiesIndependentlyRecomputed']
for name,pin in report['sourcePins'].items():
    folder=BASE/name; assert sha(folder/'index.json')==pin
    for row in read(folder/'index.json')['files']:
        path=(ROOT if name.startswith('implementation') else folder)/row['path']
        assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
for row in report['retainedScopes']:
    attempt=BASE/row['scope']/'attempts/attempt01-actual'
    assert sha(attempt/'result.json')==row['resultSha256']
    result=read(attempt/'result.json'); assert result['status']=='failed' and result['childState']=='exited'
    for item in read(attempt/'scratch-index.json'):
        for folder in (Path(result['scratchPath']),attempt/'scratch'):
            path=folder/item['path']; assert path.stat().st_size==item['bytes'] and sha(path)==item['sha256']
for path,pin in report['unchangedDatabaseHashes'].items(): assert sha(Path(path))==pin
links=read(ROOT/'artifacts/verification/project-links.json')
assert links['missing']==[] and sha(ROOT/'scripts/check_project_links.py')==links['checker_sha256']
for row in links['files']: assert sha(ROOT/row['path'])==row['sha256']
files=[]
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file(): files.append(dict(path=path.relative_to(BASE).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
write(BASE/'index.json',dict(scope='Fresh actual 30-case run failed at original worker deadline before import; preparation failures and original bytes retained; full goal active',files=files))
selected={ROOT/'README.md',ROOT/'PROGRESS.md',ROOT/'docs/control-storage.md',
    ROOT/'docs/prompt-to-pat.md',ROOT/'docs/io-driver-hub-control.md',
    ROOT/'scripts/check_project_links.py',ROOT/'artifacts/verification/project-links.json',PRIOR}
selected.update(path for path in BASE.iterdir() if path.is_file())
selected.update(BASE.glob('implementation*/index.json'))
selected.update(BASE.glob('implementation*/README.md'))
selected.update(BASE.glob('implementation*/correction.json'))
selected.update(BASE.glob('harness*/index.json'))
copies=[]
for source in sorted(selected):
    relative=source.relative_to(ROOT); target=CHECKPOINT/'inputs'/relative
    target.parent.mkdir(parents=True,exist_ok=True); body=source.read_bytes()
    with target.open('xb') as stream: stream.write(body)
    assert target.read_bytes()==source.read_bytes()==body
    copies.append(dict(source=relative.as_posix(),copy=target.relative_to(ROOT).as_posix(),bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT/'index.json',dict(scope='Audited failed original-run attempt; control coverage remains historical; full goal active',
    stageIndexSha256=sha(BASE/'index.json'),stageFiles=len(files),failedScopes=3,requestedCases=30,
    retainedCaseManifests=29,actualOriginalRunProfileVerified=False,importReached=False,
    readonlyDatabases=4,originalOwnerAndWriterLocks=57,workerUnresolvedEffects=None,
    markdownFiles=links['project_markdown_files'],localLinks=links['local_links_checked'],missing=[],goalStatus='active',files=copies))
print(json.dumps(dict(stageFiles=len(files),stageIndexSha256=sha(BASE/'index.json'),
    checkpointFiles=len(copies),checkpointIndexSha256=sha(CHECKPOINT/'index.json'),goalStatus='active')))
