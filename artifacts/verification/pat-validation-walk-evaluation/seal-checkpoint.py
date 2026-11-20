"""Seal the evaluated, unadopted candidate and current progress documents."""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
PRIOR=ROOT/'artifacts/verification/lifecycle-progress-links/attempt62-vault-worker-profile/index.json'
CHECKPOINT=ROOT/'artifacts/verification/lifecycle-progress-links/attempt63-validation-walk-evaluation'
def read(path):return json.loads(path.read_bytes())
def sha(path):
    assert not path.is_symlink() and path.stat().st_size<=16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
assert not (BASE/'index.json').exists() and not CHECKPOINT.exists()
assert sha(PRIOR)=='a78171e49f58c2ef3bf804254d17d2363bb6648c7a1f893a8d00ed397343419f'
result=read(BASE/'RESULTS.json')
assert result['status']=='verified-pure-evaluation' and result['differentialCases']==468
assert result['adopted'] is False and result['productionChanged'] is False and result['goalStatus']=='active'
assert sha(BASE/'inputs.json')==result['inputIndexSha256']=='96436730209b848d37913ac7015adcfe2c7fd82cdd8636c70b7b4497ad849b4f'
rows=read(BASE/'inputs.json')['files']
assert rows==read(BASE/'attempt01/inputs-before.json')==read(BASE/'attempt01/inputs-after.json')
for row in rows:
    path=BASE/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
attempt=read(BASE/'attempt01/result.json')
assert attempt['status']=='passed' and attempt['currentPass'] and attempt['childState']=='exited' and attempt['exitCode']==0
assert attempt['candidateToReferenceMedianCpuRatio']==result['candidateToReferenceMedianCpuRatio']
links=read(ROOT/'artifacts/verification/project-links.json')
assert links['missing']==[] and sha(ROOT/'scripts/check_project_links.py')==links['checker_sha256']
for row in links['files']:assert sha(ROOT/row['path'])==row['sha256']
files=[]
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():files.append(dict(path=path.relative_to(BASE).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
write(BASE/'index.json',dict(scope='468 pure differential comparisons pass; modest inconsistent timing; candidate unadopted; goal active',files=files))
selected={ROOT/'README.md',ROOT/'PROGRESS.md',ROOT/'docs/control-storage.md',
    ROOT/'docs/prompt-to-pat.md',ROOT/'docs/io-driver-hub-control.md',
    ROOT/'scripts/check_project_links.py',ROOT/'artifacts/verification/project-links.json',PRIOR}
selected.update(path for path in BASE.iterdir() if path.is_file())
copies=[]
for path in sorted(selected):
    relative=path.relative_to(ROOT);target=CHECKPOINT/'inputs'/relative
    target.parent.mkdir(parents=True,exist_ok=True);body=path.read_bytes()
    with target.open('xb') as stream:stream.write(body)
    assert target.read_bytes()==path.read_bytes()==body
    copies.append(dict(source=relative.as_posix(),copy=target.relative_to(ROOT).as_posix(),bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT/'index.json',dict(stageIndexSha256=sha(BASE/'index.json'),stageFiles=len(files),
    differentialCases=468,adopted=False,productionChanged=False,goalStatus='active',
    markdownFiles=links['project_markdown_files'],localLinks=links['local_links_checked'],missing=[],files=copies))
print(json.dumps(dict(stageFiles=len(files),stageIndexSha256=sha(BASE/'index.json'),
    checkpointFiles=len(copies),checkpointIndexSha256=sha(CHECKPOINT/'index.json'),goalStatus='active')))
