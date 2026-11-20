"""Seal the audited vault component, full-text follow-up and current documents."""
import hashlib
import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
RESEARCH = ROOT / 'research/host-contract/vault-followup'
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt58-evidence-vault'

def read(path):
    return json.loads(path.read_bytes())

def sha(path):
    assert not path.is_symlink()
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')

assert not (BASE / 'index.json').exists() and not (RESEARCH / 'index.json').exists() and not CHECKPOINT.exists()
result = read(BASE / 'RESULTS.json')
assert result['distinctMethodsWithPassingReceipts'] == 22 and result['correctedMethodScopePassed']
assert not result['originalFullScopePassed'] and result['startupFailuresRetained'] == result['fullScopeTestFailuresRetained'] == 1
assert result['productionIdenticalAcrossSelections'] and result['allOriginalAndStoredBytesMatched']
assert result['actualVaultBytes'] == 15439872 and result['maximumVaultBytes'] == 15728640
assert result['failedClaimRemainsHeld'] and result['correctedControlQuiescenceVerified']
assert not result['authorityPublicationImplemented'] and not result['physicalCapacityReserved']
for folder, expected in result['sourcePins'].items():
    index = BASE / folder / 'index.json'
    assert sha(index) == expected
    for row in read(index)['files']:
        path = ROOT / row['path'] if folder.startswith('implementation') else index.parent / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
for path, expected in result['unchangedDatabaseHashes'].items():
    assert sha(Path(path)) == expected
for folder in ('harness01', 'harness02', 'harness03'):
    attempt = BASE / folder / 'attempts/attempt01'
    terminal = read(attempt / 'result.json')
    assert terminal['childState'] == 'exited' and terminal['scratchRetained']
    for row in read(attempt / 'scratch-index.json')['files']:
        path = attempt / 'scratch' / row['path']
        if row['kind'] == 'retained-negative-symlink':
            assert path.is_symlink() and os.readlink(path) == row['target']
            assert hashlib.sha256(row['target'].encode()).hexdigest() == row['sha256']
        else:
            assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    config = read(attempt / 'child-config.json')
    for row in config['expectedInputs']:
        path = attempt / 'project' / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    for row in config['expectedExternalInputs']:
        assert sha(Path(row['resolvedPath'])) == row['sha256']
links = read(ROOT / 'artifacts/verification/project-links.json')
assert links['missing'] == [] and sha(ROOT / 'scripts/check_project_links.py') == links['checker_sha256']
for row in links['files']:
    assert sha(ROOT / row['path']) == row['sha256']
reading = read(RESEARCH / 'reading.json')
assert reading['lines'] == 765 and reading['coverage'] == 'complete extracted prose'
assert sha(RESEARCH / 'raw/corruption.html') == reading['rawSha256']
assert sha(RESEARCH / 'text/corruption.txt') == reading['textSha256']
research_files = []
for path in sorted(RESEARCH.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        research_files.append(dict(path=path.relative_to(RESEARCH).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
write(RESEARCH / 'index.json', dict(scope='Complete 765-line extracted prose reading of official SQLite corruption/locking reference; linked works remain separate', files=research_files))
files = []
retained_links = []
for path in sorted(BASE.rglob('*')):
    if path.is_symlink():
        relative = path.relative_to(BASE).as_posix()
        assert relative == 'harness02/attempts/attempt01/scratch/test_reopen_refuses_retained_or_dangling_sidefile/dangling/evidence.db-journal'
        target = os.readlink(path)
        assert Path(target).is_relative_to(BASE) and not path.exists()
        retained_links.append(dict(path=relative, kind='retained-negative-symlink', target=target,
            bytes=path.lstat().st_size, sha256=hashlib.sha256(target.encode()).hexdigest()))
    elif path.is_file():
        files.append(dict(path=path.relative_to(BASE).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
assert len(retained_links) == 1
write(BASE / 'index.json', dict(scope='Immutable byte-vault component: 22 distinct passing method receipts on identical production, two failed scopes retained; authority publication and full goal incomplete',
    files=files, retainedSymlinks=retained_links))
selected = {
    ROOT / 'README.md', ROOT / 'PROGRESS.md', ROOT / 'docs/control-storage.md',
    ROOT / 'docs/prompt-to-pat.md', ROOT / 'docs/io-driver-hub-control.md',
    ROOT / 'scripts/check_project_links.py', ROOT / 'artifacts/verification/project-links.json',
    ROOT / 'artifacts/verification/lifecycle-progress-links/attempt57-storage-capacity/index.json'}
for folder in (BASE, RESEARCH):
    selected.update(path for path in folder.iterdir() if path.is_file())
selected.update(BASE.glob('implementation*/index.json'))
selected.update(BASE.glob('implementation*/correction.json'))
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
write(CHECKPOINT / 'index.json', dict(scope='Independent vault component verified; source and historical failures retained; full HMS goal active',
    stageIndexSha256=sha(BASE / 'index.json'), stageRegularFiles=len(files), retainedNegativeSymlinks=1,
    researchIndexSha256=sha(RESEARCH / 'index.json'), researchFiles=len(research_files),
    distinctMethodsWithPassingReceipts=22, failedScopesRetained=2, originalFullScopePassed=False,
    authorityPublicationImplemented=False, goalStatus='active', markdownFiles=links['project_markdown_files'],
    localLinks=links['local_links_checked'], missing=[], files=copies))
print(json.dumps(dict(stageRegularFiles=len(files), retainedNegativeSymlinks=1,
    stageIndexSha256=sha(BASE / 'index.json'), researchFiles=len(research_files),
    researchIndexSha256=sha(RESEARCH / 'index.json'), checkpointFiles=len(copies),
    checkpointIndexSha256=sha(CHECKPOINT / 'index.json'), goalStatus='active')))
