"""Seal verified progress without claiming the unfinished current selection passed."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt59-vault-authority'

def read(path): return json.loads(path.read_bytes())
def sha(path):
    assert not path.is_symlink() and path.stat().st_size <= 16 * 1024 * 1024
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')

assert not (BASE / 'index.json').exists() and not CHECKPOINT.exists()
result = read(BASE / 'PROGRESS-RESULTS.json')
assert result['status'] == 'progress-verified-incomplete' and result['goalStatus'] == 'active'
assert len(result['originalSourcePassingMethods']) == 11 and len(result['currentSourcePassingMethods']) == 3
assert len(result['currentSourceRemainingMethods']) == 17 and not result['currentFullSelectionPassed']
assert not result['originalAggregatePassed'] and len(result['failedScopesRetained']) == 5
assert result['readonlyDatabaseCount'] == 15 and result['ownerLocks'] == 20
assert not result['actualOriginalRunProfileVerified'] and not result['catalogIntegrated'] and not result['physicalCapacityReserved']
assert read(BASE / 'pending-methods.json')['methods'] == result['currentSourceRemainingMethods']
for name, expected in result['sourcePins'].items():
    index = BASE / name / 'index.json'; assert sha(index) == expected
    for row in read(index)['files']:
        path = ROOT / row['path'] if name.startswith('implementation') else index.parent / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
for path, expected in result['unchangedDatabaseHashes'].items(): assert sha(Path(path)) == expected
for folder in BASE.glob('harness[0-9][0-9]'):
    attempt = folder / 'attempts/attempt01'
    if not attempt.exists():
        assert folder.name in result['preparedUnexecutedScopes']; continue
    terminal = read(attempt / 'result.json'); assert terminal['childState'] == 'exited' and terminal['scratchRetained']
    config = read(attempt / 'child-config.json')
    for row in config['expectedInputs']:
        path = attempt / 'project' / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    for row in config['expectedExternalInputs']: assert sha(Path(row['resolvedPath'])) == row['sha256']
    inventory = read(attempt / 'scratch-index.json'); raw = Path(inventory.get('rawPath', attempt / 'scratch'))
    for row in inventory['files']:
        assert row['kind'] == 'file'
        for path in (raw / row['path'], attempt / 'scratch' / row['path']):
            assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
links = read(ROOT / 'artifacts/verification/project-links.json')
assert links['missing'] == [] and sha(ROOT / 'scripts/check_project_links.py') == links['checker_sha256']
for row in links['files']: assert sha(ROOT / row['path']) == row['sha256']
files = []
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file(): files.append(dict(path=path.relative_to(BASE).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
write(BASE / 'index.json', dict(scope='Authority-vault candidate with retained failures and corrected typed refusals; 3 current-source controls pass, 17 pending; full goal active', files=files))
selected = {ROOT / 'README.md', ROOT / 'PROGRESS.md', ROOT / 'docs/control-storage.md',
    ROOT / 'docs/prompt-to-pat.md', ROOT / 'docs/io-driver-hub-control.md',
    ROOT / 'scripts/check_project_links.py', ROOT / 'artifacts/verification/project-links.json',
    ROOT / 'artifacts/verification/lifecycle-progress-links/attempt58-evidence-vault/index.json'}
selected.update(path for path in BASE.iterdir() if path.is_file())
selected.update(BASE.glob('implementation*/index.json'))
selected.update(BASE.glob('implementation*/README.md'))
selected.update(BASE.glob('implementation*/correction.json'))
selected.update(BASE.glob('harness*/index.json'))
copies = []
for source in sorted(selected):
    relative = source.relative_to(ROOT); target = CHECKPOINT / 'inputs' / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    body = source.read_bytes()
    with target.open('xb') as stream: stream.write(body)
    assert target.read_bytes() == source.read_bytes() == body
    copies.append(dict(source=relative.as_posix(), copy=target.relative_to(ROOT).as_posix(),
        bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT / 'index.json', dict(scope='Verified authority-publication progress; corrected-source full verification incomplete',
    stageIndexSha256=sha(BASE / 'index.json'), stageFiles=len(files), previousSourcePassingMethods=11,
    currentSourcePassingMethods=3, currentSourcePendingMethods=17, failedScopesRetained=5,
    originalAggregatePassed=False, currentFullSelectionPassed=False, readonlyDatabases=15,
    authorityProfileActualOriginalRunVerified=False, physicalCapacityReserved=False,
    markdownFiles=links['project_markdown_files'], localLinks=links['local_links_checked'], missing=[],
    goalStatus='active', files=copies))
print(json.dumps(dict(stageFiles=len(files), stageIndexSha256=sha(BASE / 'index.json'),
    checkpointFiles=len(copies), checkpointIndexSha256=sha(CHECKPOINT / 'index.json'),
    currentSourcePassed=3, currentSourcePending=17, goalStatus='active')))
