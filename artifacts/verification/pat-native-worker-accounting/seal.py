"""Seal the composed diagnostic, failed actual scope, audit and reading follow-up."""
import hashlib
import json
import os
from pathlib import Path
import stat

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = ROOT / 'artifacts/implementation/pat-native-supervisor/implementation02'
HARNESS = BASE / 'harness01'
ATTEMPT = HARNESS / 'attempts/attempt01-accounting'
RESEARCH = ROOT / 'research/host-contract/native-binding-api-review'
PRIOR = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt68-native-supervisor/index.json'
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt69-native-worker-accounting'
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
assert sha(PRIOR) == '333c7818766891d1dd427bba0acade6b5fe5f7ec9e88f96dd839d33a7e7e1872'
assert sha(SOURCE / 'index.json') == '255b919194d150572c7b7876d941fb2e7d5866e36cdc119e91608da4b85ddc18'
assert sha(HARNESS / 'index.json') == '34bfe3567be9944a079d8c9809b62227e0967a59875c85a8bc84a6de53651b9a'
assert sha(RESEARCH / 'index.json') == 'ee30ed87fdfd03a7d78d28f40256cf2b4bea47c792e62a326d3fe76a098b6bf0'
for folder, prefix in ((SOURCE, ROOT), (HARNESS, HARNESS), (RESEARCH, RESEARCH)):
    for row in read(folder / 'index.json')['files']:
        verify(prefix, row)
controls = read(BASE / 'controls.json')
assert controls['status'] == 'passed' and controls['testsRun'] == 21 and controls['sourceUnchanged']
assert controls['deniedEvents'] == []
assert all(controls[key] == 0 for key in ('failures', 'errors', 'skips', 'expectedFailures', 'unexpectedSuccesses'))
for row in controls['before']:
    verify(BASE, row)
for row in read(BASE / 'audit-inputs.json')['files']:
    verify(BASE, row)
for row in read(BASE / 'path-review-inputs.json')['sourceFiles']:
    verify(ROOT, row)
prior_profile = read(BASE / 'path-review-inputs.json')['priorProfile']
assert sha(BASE / 'references/prior-worker-profile.json') == prior_profile['sha256']
reading = read(RESEARCH / 'reading.json')
assert reading['totalReadLfLines'] == 2064 and reading['newlyReadLfLines'] == 1708
assert reading['completeSources'] == 4 and not reading['complete']
result = read(BASE / 'RESULTS.json')
assert result['stageStatus'] == 'verified-progress-actual-scope-failed'
assert result['caseManifests'] == 29 and result['caseDirectories'] == 30
assert result['rawFiles'] == 3960 and result['rawBytes'] == 18697016
assert len(result['ownerAndWriterLocks']) == 55 and len(result['readonlySourceDatabases']) == 4
assert result['workerCaseDatabasesOpened'] == 0 and not result['importReached'] and not result['actualScopePassed']
assert not result['productionCandidateChanged'] and not result['publicRuntimeChanged']
assert result['nativeImageReceiptVerified'] and not result['nativeOriginReopenedAfterChildExit']
assert sha(ATTEMPT / 'result.json') == result['resultSha256']
observation = result['workerResourceObservation']
assert observation['associationVerified'] and observation['ownedObjectAndInheritedDescriptorsAssociated']
assert observation['directChildLaunches'] == 1 and not observation['pidBasedSampling']
assert sha(ATTEMPT / 'worker-accounting.json') == observation['accountingSha256']
assert sha(ATTEMPT / 'worker-accounting-launch-audit.json') == observation['launchAuditSha256']
for row in read(ATTEMPT / 'scratch-index.json'):
    verify(ATTEMPT / 'scratch', row)
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
write(BASE / 'index.json', dict(scope='Exact native project with harness-only accounting; 21 controls and audited failed original scope',
    files=sorted(files, key=lambda row: row['path']), projectChanged=False, publicRuntimeChanged=False, actualScopePassed=False))
selected = {ROOT / 'README.md', ROOT / 'PROGRESS.md', ROOT / 'docs/control-storage.md',
    ROOT / 'docs/prompt-to-pat.md', ROOT / 'docs/io-driver-hub-control.md', ROOT / 'scripts/check_project_links.py',
    ROOT / 'artifacts/verification/project-links.json', SOURCE / 'index.json', PRIOR}
selected.update(path for path in BASE.iterdir() if path.is_file())
selected.update(path for path in (BASE / 'references').iterdir() if path.is_file())
selected.update(path for path in HARNESS.iterdir() if path.is_file())
selected.update(path for path in RESEARCH.rglob('*') if path.is_file())
for name in ('result.json', 'worker-accounting.json', 'worker-accounting-launch-audit.json', 'imports.json', 'actual-tests.json'):
    selected.add(ATTEMPT / name)
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
    sourceIndexSha256=sha(SOURCE / 'index.json'), researchIndexSha256=sha(RESEARCH / 'index.json'),
    newlyReadLfLines=1708, totalApiReadLfLines=2064, totalApiAcquiredLfLines=5360,
    observerControls=15, compositionControls=6, actualScopePassed=False, caseManifests=29,
    originalProcessAssociationVerified=True, nativeImageAndScansObserved=True, originalStatePreserved=True,
    projectChanged=False, publicRuntimeChanged=False, crossTrialPerformanceQualified=False,
    goalStatus='active', markdownFiles=links['project_markdown_files'], localLinks=links['local_links_checked'],
    missing=[], files=copies))
print(json.dumps(dict(stageFiles=len(files), stageIndexSha256=sha(BASE / 'index.json'),
    checkpointFiles=len(copies), checkpointIndexSha256=sha(CHECKPOINT / 'index.json'), goalStatus='active')))
