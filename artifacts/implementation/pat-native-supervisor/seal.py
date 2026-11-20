"""Seal both source stages, retained failures, controls and failed actual trial."""
import hashlib
import json
import os
from pathlib import Path
import stat

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
RESEARCH = ROOT / 'research/host-contract/native-loader'
PRIOR = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt67-native-retention-binding/index.json'
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt68-native-supervisor'
def read(path):
    return json.loads(path.read_bytes())
def sha(path):
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_size <= 16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2);stream.write('\n')
def verify(prefix, row):
    path = prefix / row['path']
    assert path.lstat().st_size == row['bytes'] and sha(path) == row['sha256']
assert not (BASE / 'index.json').exists() and not CHECKPOINT.exists()
assert sha(PRIOR) == '5dcad16e76694ff180cf93ce43dd18ceb9169d8e96f8a8ecc99cf8d7e18ae379'
assert sha(RESEARCH / 'index.json') == '1de7cbbeb662841d35fbd3fd44417b81cbc2cdfe2fb23fe2c7ea9351b54888ac'
for row in read(RESEARCH / 'index.json')['files']:
    verify(RESEARCH, row)
assert read(RESEARCH / 'reading.json')['totalLfLines'] == 836
for stage, pin in [('implementation01', 'ffe9af2582f56ab198a92f58598d378fc07a3c69cfe223c73b353a91c59c319b'),
                   ('implementation02', '255b919194d150572c7b7876d941fb2e7d5866e36cdc119e91608da4b85ddc18')]:
    assert sha(BASE / stage / 'index.json') == pin
    for row in read(BASE / stage / 'index.json')['files']:
        verify(ROOT, row)
for name, pin in [('harness01', 'eb800da5af2e49f99d8f8a3de176d8088654c8d9c92f9bc153f37f8cc59fa88b'),
                  ('harness02', '6fd4be31a43dca75bfcda3fdb9f9e75dba5c19f57b879ef1a271b5650aa10930')]:
    folder = BASE / name
    assert sha(folder / 'index.json') == pin
    for row in read(folder / 'index.json')['files']:
        verify(folder, row)
for suffix in ('01', '02'):
    folder = BASE / ('controls' + suffix)
    assert read(folder / 'result.json')['status'] == 'passed'
    for row in read(folder / 'inputs.json'):
        verify(BASE, row)
    results = [read(folder / mode / 'result.json') for mode in
               ('normal', 'replace-after-verify', 'bad-digest', 'veto-load', 'veto-image', 'load-failure')]
    assert all(value['status'] == 'passed' and value['error'] is None for value in results)
    assert sum(len(value['checks']) for value in results) == 13
    guard = read(BASE / ('guard-controls' + ('' if suffix == '01' else '02') + '.json'))
    assert guard['status'] == 'passed' and len(guard['checks']) == 16
    assert guard['harnessChildSha256'] == sha(BASE / ('harness' + suffix) / 'attempt_child.py')
startup = BASE / 'harness01/attempts/attempt01-actual'
failed = read(startup / 'result.json')
assert failed['status'] == 'failed' and failed['exitCode'] == 1 and failed['counts'] is None
assert read(startup / 'scratch-index.json') == read(startup / 'sqlite-connections.json') == []
for name in ('inputs', 'harness', 'frozen'):
    assert read(startup / (name + '-before.json')) == read(startup / (name + '-after.json'))
for name in ('freeze-source01-failure.json', 'freeze-source02-failure.json'):
    assert read(BASE / name)['status'] == 'failed-before-project-mutation'
result = read(BASE / 'RESULTS.json')
assert result['stageStatus'] == 'verified-progress-actual-scope-failed'
assert result['caseManifests'] == 15 and result['rawFiles'] == 1927 and result['rawBytes'] == 11352470
assert len(result['ownerAndWriterLocks']) == 29 and len(result['readonlySourceDatabases']) == 4
assert result['workerCaseDatabasesOpened'] == 0 and not result['importReached'] and not result['actualScopePassed']
assert result['nativeImageReceiptVerified'] and not result['nativeOriginReopenedAfterChildExit']
assert sha(BASE / 'harness02/attempts/attempt01-actual/result.json') == result['resultSha256']
links = read(ROOT / 'artifacts/verification/project-links.json')
assert links['missing'] == [] and links['checker_sha256'] == sha(ROOT / 'scripts/check_project_links.py')
for row in links['files']:
    assert sha(ROOT / row['path']) == row['sha256']
files = []
for parent, dirs, names in os.walk(BASE, followlinks=False):
    for name in dirs:
        assert not (Path(parent) / name).is_symlink()
    for name in names:
        path = Path(parent) / name
        files.append(dict(path=str(path.relative_to(BASE)), bytes=path.lstat().st_size, sha256=sha(path)))
write(BASE / 'index.json', dict(scope='Native isolated supervisor, six loader scopes and sixteen guard controls; full worker still fails; startup and preparation failures retained',
    files=sorted(files, key=lambda row: row['path']), publicRuntimeChanged=False, actualScopePassed=False))
selected = {ROOT / 'README.md', ROOT / 'PROGRESS.md', ROOT / 'docs/control-storage.md',
    ROOT / 'docs/prompt-to-pat.md', ROOT / 'docs/io-driver-hub-control.md', ROOT / 'scripts/check_project_links.py',
    ROOT / 'artifacts/verification/project-links.json', PRIOR}
selected.update(path for path in BASE.iterdir() if path.is_file())
selected.update(path for path in RESEARCH.rglob('*') if path.is_file())
for folder in ('implementation01', 'implementation02', 'harness01', 'harness02'):
    selected.update(path for path in (BASE / folder).iterdir() if path.is_file())
for suffix in ('01', '02'):
    selected.update([BASE / ('controls' + suffix) / 'inputs.json', BASE / ('controls' + suffix) / 'result.json',
                     BASE / ('harness' + suffix) / 'attempts/attempt01-actual/result.json'])
copies = []
for path in sorted(selected):
    body = path.read_bytes()
    relative = path.relative_to(ROOT)
    target = CHECKPOINT / 'inputs' / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(body)
    assert path.read_bytes() == target.read_bytes()
    copies.append(dict(source=str(relative), copy=str(target.relative_to(ROOT)), bytes=len(body),
                       sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT / 'index.json', dict(stageIndexSha256=sha(BASE / 'index.json'), stageFiles=len(files),
    researchIndexSha256=sha(RESEARCH / 'index.json'), fullSelectedReadingLfLines=836,
    loaderScopes=6, guardControls=16, actualScopePassed=False, caseManifests=15,
    nativeImageAndScansObserved=True, originalStatePreserved=True, publicRuntimeChanged=False,
    goalStatus='active', markdownFiles=links['project_markdown_files'], localLinks=links['local_links_checked'],
    missing=[], files=copies))
print(json.dumps(dict(stageFiles=len(files), stageIndexSha256=sha(BASE / 'index.json'),
    checkpointFiles=len(copies), checkpointIndexSha256=sha(CHECKPOINT / 'index.json'), goalStatus='active')))
