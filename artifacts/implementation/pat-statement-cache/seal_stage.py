"""Seal successful isolated qualification and the new public-runtime receipt."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt79-statement-cache-integration'

def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def row(p): return dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as out: json.dump(value, out, indent=2); out.write('\n')
def verify(prefix, rows):
    for r in rows:
        p = prefix / r['path']
        assert p.is_file() and not p.is_symlink() and p.stat().st_size == r['bytes']
        assert sha(p) == r['sha256'], str(p)
def copy(names, destination):
    rows = []
    for name in names:
        p, target = ROOT / name, destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as out: out.write(p.read_bytes())
        assert sha(p) == sha(target)
        rows.append(row(target) | dict(originalPath=name))
    return rows

assert not (BASE / 'index.json').exists() and not CHECKPOINT.exists()
source = BASE / 'implementation01'
assert sha(source / 'index.json') == '7ecd42fec5cef9374573ae8b3d0747060bdc8c4cd8ca552e9c3de4d64a2ec23e'
verify(ROOT, read(source / 'index.json')['files'])
for harness in sorted(BASE.glob('harness*')):
    if harness.is_dir(): verify(harness, read(harness / 'index.json')['files'])
controls, actual, runtime = [read(BASE / name) for name in ('CONTROL_RESULTS.json', 'RESULTS.json', 'RUNTIME_RESULTS.json')]
assert controls['status'] == 'verified-controls' and controls['testsRun'] == 19
assert len(controls['readonlyDatabases']) == 76 and controls['originalOwnerAndWriterLocks'] == 99
assert actual['actualScopePassed'] and actual['caseManifests'] == 30 and actual['catalogIntegrated']
assert actual['sourceApplicationInvocations'] == 1 and actual['catalogObservation']['oneCompletedApplication']
assert actual['workerCaseDatabasesOpened'] == 0 and len(actual['readonlySourceDatabases']) == 4
assert len(actual['ownerAndWriterLocks']) == 57
attempt = BASE / 'harness01/attempts/attempt01-actual'
assert read(attempt / 'result.json')['currentPass']
for n in range(12, 22):
    r = read(BASE / ('harness%02d' % n) / 'attempts/attempt01/result.json')
    assert r['status'] == 'passed' and r['sourceInputs'] == 304 and r['noWorkerLaunched']
assert runtime['passed'] and runtime['tests'] == runtime['previousTestIdsPreserved'] == 861
receipt_path = ROOT / runtime['runtimeReceipt']['path']
assert sha(receipt_path) == runtime['runtimeReceipt']['sha256']
receipt = read(receipt_path)
assert receipt['passed'] and receipt['inputs_stable'] and len(receipt['files_after']) == 161
verify(ROOT, receipt['files_after'])
assert (ROOT / 'hms/journal.py').read_bytes() == (source / 'project/hms/journal.py').read_bytes()
write(BASE / 'runtime-source-continuity.json', dict(runtimeReceipt=str(receipt_path.relative_to(ROOT)),
    receiptSha256=sha(receipt_path), fullRuntimeTests=861, currentInputsVerified=161,
    changedFromPreviousReceipt=['hms/journal.py'], mismatches=[], runtimeRerunPerformed=True,
    productionRuntimeChanged=True, qualificationPackageInstalled=False))
links_path = ROOT / 'artifacts/verification/project-links.json'
links = read(links_path)
assert not links['missing'] and sha(ROOT / 'scripts/check_project_links.py') == links['checker_sha256']
for r in links['files']: assert sha(ROOT / r['path']) == r['sha256']
write(BASE / 'STAGE_RESULTS.json', dict(status='qualified-simulation-and-public-runtime-verified',
    goalStatus='active', publicRuntimeChanged=True, changedProductionFiles=['hms/journal.py'],
    publicQualificationEnabled=False, sourceIndexSha256=sha(source / 'index.json'),
    sourceProjectFiles=304, sourceFrozenFiles=313, soleCandidateProductionChange=True,
    importInspection=row(BASE / 'inspection01.json'), catalogControls=19,
    controlsAudit=row(BASE / 'CONTROL_RESULTS.json'), actualFullMatrixAttempts=1,
    originalCases=30, actualQualificationPassed=True, actualAudit=row(BASE / 'RESULTS.json'),
    applicationInvocations=1, applicationCompleted=True, workerCaseDatabasesOpened=0,
    currentRuntimeAudit=row(BASE / 'RUNTIME_RESULTS.json'), currentRuntimeReceipt=runtime['runtimeReceipt'],
    fullRuntimeTests=861, previousTestIdsPreserved=861, stableRuntimeInputs=161,
    limitsUnchanged=True, deploymentTimingQualified=False, nativeStatementByteCapacityReserved=False,
    physicalExecutionPerformed=False, aggregateStorageProviderQualified=False,
    independentReview=False, researchNewlyReadLfLines=0))
documents = ['README.md', 'PROGRESS.md', 'docs/pat-foundation.md', 'docs/prompt-to-pat.md',
             'docs/io-driver-hub-control.md', 'scripts/check_project_links.py',
             'artifacts/verification/project-links.json']
copies = copy(documents, BASE / 'final-documents')
write(BASE / 'checkpoint-verification.json', dict(sourceFrozenInputsVerified=313,
    harnessesVerified=11, runtimeInputsVerified=161, fullRuntimeTests=861,
    projectMarkdownFiles=links['project_markdown_files'], localLinksChecked=links['local_links_checked'],
    missingLinks=[], linkReportSha256=sha(links_path), finalDocumentCopies=copies,
    databaseConnectionsOpenedBySeal=0, physicalExecutionPerformed=False, goalStatus='active'))
paths = sorted(p for p in BASE.rglob('*') if p.is_file())
assert all(not p.is_symlink() for p in BASE.rglob('*'))
write(BASE / 'index.json', dict(files=[row(p) for p in paths],
    outcome='qualified-simulation-and-public-runtime-verified', goalStatus='active'))
verify(ROOT, read(BASE / 'index.json')['files'])
selected = documents + ['artifacts/implementation/pat-statement-cache/' + name for name in
    ('README.md', 'NEXT.md', 'RESULTS.json', 'STAGE_RESULTS.json', 'CONTROL_RESULTS.json',
     'RUNTIME_RESULTS.json', 'runtime-source-continuity.json', 'checkpoint-verification.json', 'index.json')]
selected.append(str(receipt_path.relative_to(ROOT)))
entries = copy(selected, CHECKPOINT / 'snapshot')
write(CHECKPOINT / 'index.json', dict(files=entries, stageIndexSha256=sha(BASE / 'index.json'),
    goalStatus='active', sourceRuntimeChanged=True, actualQualificationPassed=True, fullRuntimeTests=861))
verify(ROOT, read(CHECKPOINT / 'index.json')['files'])
print(json.dumps(dict(stageFiles=len(paths), stageIndexSha256=sha(BASE / 'index.json'),
    checkpointFiles=len(entries), checkpointIndexSha256=sha(CHECKPOINT / 'index.json'),
    localLinksChecked=links['local_links_checked'], missingLinks=0, goalStatus='active')))
