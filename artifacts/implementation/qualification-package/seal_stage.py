"""Seal the stage with separate control success and actual deadline failure."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt75-qualification-package'

def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def row(p): return dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as out: json.dump(obj, out, indent=2); out.write('\n')
def verify(root, entries):
    for entry in entries:
        p = root / entry['path']
        assert not p.is_symlink() and p.is_file()
        assert p.stat().st_size == entry['bytes'] and sha(p) == entry['sha256'], str(p)

assert not (BASE / 'index.json').exists() and not CHECKPOINT.exists()
source = BASE / 'implementation03'
assert sha(source / 'index.json') == 'ec6df4066c89f38328030a28e2a5bd71d137abbc67cd51cb161cc246e2e8a268'
verify(ROOT, read(source / 'index.json')['files'])
for harness in BASE.glob('harness*'):
    if harness.is_dir(): verify(harness, read(harness / 'index.json')['files'])
core = list((source / 'project/hms').rglob('*.py'))
old = BASE.parent / 'pat-vault-catalog/implementation03/project'
assert len(core) == 83
assert all(p.read_bytes() == (old / p.relative_to(source / 'project')).read_bytes() for p in core)
controls = read(BASE / 'CONTROL_RESULTS.json')
assert controls['status'] == 'verified-controls' and controls['testsRun'] == 19
assert len(controls['readonlyDatabases']) == 76 and controls['originalOwnerAndWriterLocks'] == 99
failed = read(BASE / 'FAILED_ACTUAL_RESULTS.json')
assert failed['retentionAuditPassed'] and failed['qualificationPassed'] is False
assert failed['workerCaseDatabasesOpened'] == 0 and failed['writtenCaseManifests'] == 25
assert failed['workerEffectsUnresolved'] and not failed['sameSourceRetryPerformed']
assert read(BASE / 'harness01/attempts/attempt01-actual/result.json')['status'] == 'failed'
for n in range(3, 12): assert not (BASE / ('harness%02d' % n) / 'attempts').exists()
for n in range(12, 22):
    r = read(BASE / ('harness%02d' % n) / 'attempts/attempt01/result.json')
    assert r['status'] == 'passed' and r['sourceInputs'] == 304 and r['noWorkerLaunched']
continuity = read(BASE / 'runtime-source-continuity.json')
receipt = ROOT / continuity['runtimeReceipt']
assert sha(receipt) == continuity['receiptSha256']
runtime = read(receipt)
assert runtime['passed'] and runtime['tests'] == 861 and len(runtime['files_after']) == 161
for item in runtime['files_after']: assert sha(ROOT / item['path']) == item['sha256']
research = ROOT / 'research/host-contract/native-init-review'
verify(ROOT, read(research / 'index.json')['files'])
reading = read(research / 'reading.json')
assert reading['complete'] and reading['totalReadLfLines'] == reading['totalAcquiredLfLines'] == 5360
for item in reading['sources']:
    p = ROOT / item['retainedPath']
    assert p.stat().st_size == item['bytes'] and sha(p) == item['sha256']
    lines = p.read_bytes().splitlines(keepends=True)
    assert len(lines) == item['lfLines'] and item['readLfLines'] == item['lfLines']
    for segment in item['readRanges']:
        assert hashlib.sha256(b''.join(lines[segment['first']-1:segment['last']])).hexdigest() == segment['sha256']
links = read(ROOT / 'artifacts/verification/project-links.json')
assert links['missing'] == []
write(BASE / 'RESULTS.json', dict(status='namespace-controls-verified-actual-qualification-incomplete',
    goalStatus='active', publicRuntimeChanged=False, publicQualificationEnabled=False,
    sourceIndexSha256=sha(source / 'index.json'), unchangedCoreModules=83,
    importInspection=row(BASE / 'inspection04.json'), controlAudit=row(BASE / 'CONTROL_RESULTS.json'),
    controlTests=19, controlRetainedFiles=1149, controlOriginalLocks=99, controlReadOnlyDatabases=76,
    controlSemanticOracleSubstituted=True, actualQualificationPassed=False,
    actualFailureAudit=row(BASE / 'FAILED_ACTUAL_RESULTS.json'), actualWorkerAttempts=1,
    requiredCases=30, writtenCaseManifests=25, interruptedCase=25,
    actualRetainedFiles=3378, actualOriginalLocks=49, actualParentDatabases=4,
    workerCaseDatabasesOpened=0, actualEvidencePublished=False, actualApplicationPerformed=False,
    runtimeSourceContinuity=row(BASE / 'runtime-source-continuity.json'), previousFullRuntimeTests=861,
    runtimeRerunPerformed=False, researchIndex=row(research / 'index.json'),
    newResearchLfLines=2112, nativePacketReadLfLines=5360, nativePacketCompleteSources=6,
    review='primary-agent; no independent review claimed', physicalExecutionPerformed=False,
    originalLimitsPreserved=True, storageProviderQualified=False))

documents = ['README.md', 'PROGRESS.md', 'docs/pat-foundation.md', 'docs/prompt-to-pat.md',
             'docs/io-driver-hub-control.md', 'scripts/check_project_links.py',
             'artifacts/verification/project-links.json']
for name in documents:
    destination = BASE / 'final-documents' / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as out: out.write((ROOT / name).read_bytes())
paths = sorted(p for p in BASE.rglob('*') if p.is_file())
assert all(not p.is_symlink() for p in BASE.rglob('*'))
write(BASE / 'index.json', dict(files=[row(p) for p in paths],
    outcome='namespace-controls-verified-actual-qualification-incomplete', goalStatus='active'))
verify(ROOT, read(BASE / 'index.json')['files'])

checkpoint_paths = documents + [
    'artifacts/implementation/qualification-package/index.json',
    'artifacts/implementation/qualification-package/RESULTS.json',
    'artifacts/implementation/qualification-package/CONTROL_RESULTS.json',
    'artifacts/implementation/qualification-package/FAILED_ACTUAL_RESULTS.json',
    'artifacts/implementation/qualification-package/runtime-source-continuity.json',
    'research/host-contract/native-init-review/index.json',
    'research/host-contract/native-init-review/reading.json',
    'research/host-contract/native-init-review/README.md']
entries = []
for name in checkpoint_paths:
    destination = CHECKPOINT / 'snapshot' / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as out: out.write((ROOT / name).read_bytes())
    entries.append(row(destination) | dict(originalPath=name))
write(CHECKPOINT / 'index.json', dict(files=entries, stageIndexSha256=sha(BASE / 'index.json'),
    goalStatus='active', sourceRuntimeChanged=False, actualQualificationPassed=False))
verify(ROOT, read(CHECKPOINT / 'index.json')['files'])
print(json.dumps(dict(stageFiles=len(paths), stageIndexSha256=sha(BASE / 'index.json'),
    checkpointFiles=len(entries), checkpointIndexSha256=sha(CHECKPOINT / 'index.json'))))
