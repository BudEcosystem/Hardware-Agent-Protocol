"""Seal the terminal candidate and copy the updated documentation checkpoint."""
import hashlib
import json
from pathlib import Path

ROOT = Path.cwd()
BASE = ROOT / 'artifacts/implementation/pat-io-recorded-catalog'
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt55-io-recorded-catalog'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')

assert not (BASE / 'index.json').exists() and not CHECKPOINT.exists()
result = json.loads((BASE / 'RESULTS.json').read_bytes())
assert result['passingScopes'] == 19 and result['failedScopes'] == 6
assert result['actualIntegrationScopesPassed'] == 0
coverage = json.loads((BASE / 'control-coverage.json').read_bytes())
assert coverage['allDeclaredControlsPassed'] and len(coverage['passedControls']) == 19
links = json.loads((ROOT / 'artifacts/verification/project-links.json').read_bytes())
assert links['missing'] == []
assert sha(ROOT / 'scripts/check_project_links.py') == links['checker_sha256']
for row in links['files']:
    assert sha(ROOT / row['path']) == row['sha256']
rows = []
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink(), str(path)
    if path.is_file():
        rows.append(dict(path=path.relative_to(BASE).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
write(BASE / 'index.json', dict(scope='Recorded I/O catalog candidate: 19 fixture controls pass; both actual process scopes remain failed. All original failures retained. Full HMS goal active.', files=rows))
selected = {
    ROOT / 'README.md', ROOT / 'PROGRESS.md', ROOT / 'docs/prompt-to-pat.md', ROOT / 'docs/io-driver-hub-control.md',
    ROOT / 'scripts/check_project_links.py', ROOT / 'artifacts/verification/project-links.json',
    ROOT / 'artifacts/verification/lifecycle-progress-links/attempt54-io-catalog-design/index.json',
    BASE / 'results/README.md',
}
selected.update(path for path in BASE.iterdir() if path.is_file() and path.suffix in ('.md', '.json', '.py', '.patch'))
selected.update(BASE.glob('implementation*/index.json'))
selected.update(BASE.glob('harness*/index.json'))
copies = []
for source in sorted(selected):
    relative = source.relative_to(ROOT)
    destination = CHECKPOINT / 'inputs' / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    body = source.read_bytes()
    with destination.open('xb') as stream:
        stream.write(body)
    assert destination.read_bytes() == source.read_bytes() == body
    copies.append(dict(source=relative.as_posix(), copy=destination.relative_to(ROOT).as_posix(),
                       bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT / 'index.json', dict(scope='Recorded catalog controls pass; actual integration failures preserved and next diagnosis required.',
    stageIndexSha256=sha(BASE / 'index.json'), stageFiles=len(rows), goalStatus='active',
    fixtureControlsPassed=19, actualIntegrationScopesPassed=0, failedScopes=6,
    markdownFiles=links['project_markdown_files'], localLinks=links['local_links_checked'], missing=[], files=copies))
print(json.dumps(dict(stageFiles=len(rows), stageIndexSha256=sha(BASE / 'index.json'),
    checkpointFiles=len(copies), checkpointIndexSha256=sha(CHECKPOINT / 'index.json'),
    goalStatus='active', actualIntegrationScopesPassed=0)))
