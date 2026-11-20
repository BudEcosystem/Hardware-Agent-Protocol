"""Seal verified controls and current documentation without broadening their claim."""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
RESEARCH=ROOT/'research/host-contract/pragma-completion'
CHECKPOINT=ROOT/'artifacts/verification/lifecycle-progress-links/attempt60-vault-authority-controls'
def read(path): return json.loads(path.read_bytes())
def sha(path):
    assert not path.is_symlink() and path.stat().st_size<=16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2); stream.write('\n')

assert not (BASE/'index.json').exists() and not CHECKPOINT.exists()
result=read(BASE/'RESULTS.json')
assert result['status']=='controls-verified-incomplete-system' and result['goalStatus']=='active'
assert result['distinctPassingMethods']==25 and result['remainingSelectedMethods']==[]
assert result['currentScopeMethods']==22 and result['priorCurrentProductionMethods']==3
assert not result['productionChanged'] and result['inheritedFilesUnchanged']==284
assert result['interruptedScopes']==['harness03','harness07'] and result['interruptedScopesRetainedUnverified']
assert not result['originalAggregatePassed'] and not result['singleAggregateSelectionRun']
assert result['readonlyDatabaseCount']==45 and result['ownerLocks']==60
assert not result['actualOriginalRunProfileVerified'] and not result['catalogIntegrated']
assert not result['physicalCapacityReserved'] and not result['publicMounted']
assert result['noWorkerExecuted'] and not result['physicalEffects']
assert sha(BASE/'implementation01/index.json')==result['sourceIndexSha256']
for row in read(BASE/'implementation01/index.json')['files']:
    path=ROOT/row['path']; assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
for entry in result['scopes']:
    attempt=ROOT/entry['path']; assert sha(attempt/'result.json')==entry['resultSha256']
    for row in read(attempt/'scratch-index.json')['files']:
        path=attempt/'scratch'/row['path']; assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
for path,expected in result['unchangedDatabaseHashes'].items(): assert sha(Path(path))==expected
assert sha(RESEARCH/'index.json')=='10ab6f232141cd2136a2119cfec4dcc6295db392b8d8a70d63f090cc19572802'
for row in read(RESEARCH/'index.json')['files']:
    path=RESEARCH/row['path']; assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
links=read(ROOT/'artifacts/verification/project-links.json')
assert links['missing']==[] and sha(ROOT/'scripts/check_project_links.py')==links['checker_sha256']
for row in links['files']: assert sha(ROOT/row['path'])==row['sha256']
files=[]
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file(): files.append(dict(path=path.relative_to(BASE).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
write(BASE/'index.json',dict(scope='25 current-production controls pass in separate scopes; two interrupted attempts retained unverified; actual-run and wider system remain incomplete',files=files))
selected={ROOT/'README.md',ROOT/'PROGRESS.md',ROOT/'docs/control-storage.md',
    ROOT/'docs/prompt-to-pat.md',ROOT/'docs/io-driver-hub-control.md',
    ROOT/'scripts/check_project_links.py',ROOT/'artifacts/verification/project-links.json',
    ROOT/'artifacts/verification/lifecycle-progress-links/attempt59-vault-authority/index.json',
    RESEARCH/'index.json',RESEARCH/'README.md',RESEARCH/'reading.json',RESEARCH/'visual-review.json'}
selected.update(path for path in BASE.iterdir() if path.is_file())
selected.update(BASE.glob('implementation*/index.json'))
selected.update(BASE.glob('implementation*/README.md'))
selected.update(BASE.glob('harness*/index.json'))
selected.add(BASE/'interruption07/observation.json')
copies=[]
for source in sorted(selected):
    relative=source.relative_to(ROOT); target=CHECKPOINT/'inputs'/relative
    target.parent.mkdir(parents=True,exist_ok=True); body=source.read_bytes()
    with target.open('xb') as stream: stream.write(body)
    assert target.read_bytes()==source.read_bytes()==body
    copies.append(dict(source=relative.as_posix(),copy=target.relative_to(ROOT).as_posix(),bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT/'index.json',dict(scope='Authority-vault control coverage and full retained PRAGMA page reading; broader goal active',
    stageIndexSha256=sha(BASE/'index.json'),stageFiles=len(files),distinctPassingMethods=25,
    originalAggregatePassed=False,interruptedScopesRetained=2,readonlyDatabases=45,
    actualOriginalRunProfileVerified=False,physicalCapacityReserved=False,
    researchIndexSha256=sha(RESEARCH/'index.json'),pragmaProseLines=2688,inlineDiagramsRead=3,
    markdownFiles=links['project_markdown_files'],localLinks=links['local_links_checked'],missing=[],goalStatus='active',files=copies))
print(json.dumps(dict(stageFiles=len(files),stageIndexSha256=sha(BASE/'index.json'),
    checkpointFiles=len(copies),checkpointIndexSha256=sha(CHECKPOINT/'index.json'),goalStatus='active')))
