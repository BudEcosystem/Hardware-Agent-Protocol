"""Seal the audited diagnostic failure and capture current project navigation."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PRIOR = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt61-vault-original-run/index.json'
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt62-vault-worker-profile'
def read(path): return json.loads(path.read_bytes())
def sha(path):
    assert not path.is_symlink() and path.stat().st_size <= 16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value):
    with path.open('x') as stream: json.dump(value, stream, indent=2); stream.write('\n')

assert not (BASE / 'index.json').exists() and not CHECKPOINT.exists()
assert sha(PRIOR) == '670adecaae3ea9e9b76b5e519a4c5a063835b03151b4c79e2f9692b9fdf0aa63'
report = read(BASE / 'RESULTS.json')
assert report['stageStatus'] == 'verified-diagnostic-actual-scope-failed' and report['goalStatus'] == 'active'
assert not report['productionChanged'] and not report['actualScopePassed'] and report['diagnosticProfileCaptured']
assert report['requestedCases'] == 30 and report['caseDirectories'] == 10 and report['caseManifests'] == 9
assert report['originalMaxWallMs'] == 60000 and report['supervisorReason'] == 'SUPERVISOR_DEADLINE'
assert report['workerUnresolvedEffects'] is None and not report['importReached']
assert report['sourceApplicationInvocations'] == report['catalogEvaluations'] == report['workerCaseDatabasesOpened'] == 0
assert len(report['readonlySourceDatabases']) == 3 and len(report['ownerAndWriterLocks']) == 15
for folder, pin, prefix in ((BASE / 'implementation01', report['sourceIndexSha256'], ROOT),
                           (BASE / 'harness01', report['harnessIndexSha256'], BASE / 'harness01')):
    assert sha(folder / 'index.json') == pin
    for row in read(folder / 'index.json')['files']:
        path = prefix / row['path']; assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
attempt = BASE / 'harness01/attempts/attempt01-profile'
assert sha(attempt / 'result.json') == report['resultSha256']
result = read(attempt / 'result.json'); assert result['status'] == 'failed' and result['childState'] == 'exited'
for row in read(attempt / 'scratch-index.json'):
    for folder in (Path(result['scratchPath']), attempt / 'scratch'):
        path = folder / row['path']; assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
links = read(ROOT / 'artifacts/verification/project-links.json')
assert not links['missing'] and sha(ROOT / 'scripts/check_project_links.py') == links['checker_sha256']
for row in links['files']: assert sha(ROOT / row['path']) == row['sha256']
files = []
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file(): files.append(dict(path=path.relative_to(BASE).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
write(BASE / 'index.json', dict(scope='Current worker diagnostic; original scope failed, production unchanged, full goal active', files=files))
selected = {ROOT / 'README.md', ROOT / 'PROGRESS.md', ROOT / 'docs/control-storage.md',
    ROOT / 'docs/prompt-to-pat.md', ROOT / 'docs/io-driver-hub-control.md',
    ROOT / 'scripts/check_project_links.py', ROOT / 'artifacts/verification/project-links.json', PRIOR}
selected.update(path for path in BASE.iterdir() if path.is_file())
selected.update(BASE.glob('implementation*/index.json'))
selected.update(BASE.glob('implementation*/README.md'))
selected.update(BASE.glob('harness*/index.json'))
copies = []
for path in sorted(selected):
    relative = path.relative_to(ROOT); target = CHECKPOINT / 'inputs' / relative
    target.parent.mkdir(parents=True, exist_ok=True); body = path.read_bytes()
    with target.open('xb') as stream: stream.write(body)
    assert target.read_bytes() == path.read_bytes() == body
    copies.append(dict(source=relative.as_posix(), copy=target.relative_to(ROOT).as_posix(), bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT / 'index.json', dict(stageIndexSha256=sha(BASE / 'index.json'), stageFiles=len(files),
    actualScopePassed=False, diagnosticCaptured=True, productionChanged=False, goalStatus='active',
    markdownFiles=links['project_markdown_files'], localLinks=links['local_links_checked'], missing=[], files=copies))
print(json.dumps(dict(stageFiles=len(files), stageIndexSha256=sha(BASE / 'index.json'),
    checkpointFiles=len(copies), checkpointIndexSha256=sha(CHECKPOINT / 'index.json'), goalStatus='active')))
