"""Seal verified current results and the documentation checkpoint."""
import hashlib
import json
from pathlib import Path

ROOT = Path.cwd()
BASE = ROOT / 'artifacts/implementation/pat-io-definition-build'
DIAGNOSTIC = ROOT / 'artifacts/implementation/pat-io-catalog-worker-profile'
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt56-io-definition-build'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path, value):
    with path.open('x') as stream: stream.write(json.dumps(value, indent=2) + '\n')

assert not (BASE / 'index.json').exists() and not CHECKPOINT.exists()
result = read(BASE / 'RESULTS.json')
assert result['completedMethodsPassed'] == 22 and result['actualIntegrationScopePassed']
assert result['failedStartupScopes'] == 1 and not result['publicCatalogMounted']
assert sha(DIAGNOSTIC / 'index.json') == 'bc87c178516e2187a8aaca22d9bade060318d84e95e0d834d967b0753b614ec3'
links = read(ROOT / 'artifacts/verification/project-links.json')
assert links['missing'] == [] and sha(ROOT / 'scripts/check_project_links.py') == links['checker_sha256']
for row in links['files']: assert sha(ROOT / row['path']) == row['sha256']
rows = []
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file(): rows.append(dict(path=path.relative_to(BASE).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
write(BASE / 'index.json', dict(scope='One-call pure proof derivation: 21 pure controls and complete actual30-case recorded catalog/application/replay scope pass. Startup and previous deadline failures retained; full HMS goal active.', files=rows))
selected = {
    ROOT/'README.md', ROOT/'PROGRESS.md', ROOT/'docs/prompt-to-pat.md', ROOT/'docs/io-driver-hub-control.md',
    ROOT/'scripts/check_project_links.py', ROOT/'artifacts/verification/project-links.json',
    ROOT/'artifacts/verification/lifecycle-progress-links/attempt55-io-recorded-catalog/index.json',
    BASE/'results/README.md',
}
for folder in (BASE, DIAGNOSTIC):
    selected.update(path for path in folder.iterdir() if path.is_file() and path.suffix in ('.md','.json','.py','.patch'))
    selected.update(folder.glob('implementation*/index.json'))
    selected.update(folder.glob('harness*/index.json'))
copies = []
for source in sorted(selected):
    relative = source.relative_to(ROOT); destination = CHECKPOINT / 'inputs' / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    body = source.read_bytes()
    with destination.open('xb') as stream: stream.write(body)
    assert destination.read_bytes() == source.read_bytes() == body
    copies.append(dict(source=relative.as_posix(), copy=destination.relative_to(ROOT).as_posix(), bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT / 'index.json', dict(scope='Current diagnostic retained; one-call proof refactor and actual complete recorded-catalog integration pass. Public mounting and full HMS goal remain incomplete.',
    stageIndexSha256=sha(BASE/'index.json'), stageFiles=len(rows), diagnosticIndexSha256=sha(DIAGNOSTIC/'index.json'),
    pureControlsPassed=21, actualIntegrationScopesPassed=1, completeWorkerCases=30, failedStartupScopes=1,
    goalStatus='active', markdownFiles=links['project_markdown_files'], localLinks=links['local_links_checked'], missing=[], files=copies))
print(json.dumps(dict(stageFiles=len(rows),stageIndexSha256=sha(BASE/'index.json'),checkpointFiles=len(copies),
    checkpointIndexSha256=sha(CHECKPOINT/'index.json'),actualIntegrationScopesPassed=1,goalStatus='active')))
