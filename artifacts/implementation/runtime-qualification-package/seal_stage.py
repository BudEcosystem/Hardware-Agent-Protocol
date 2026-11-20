"""Seal byte-exact library integration and verified public regression evidence."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt80-runtime-qualification-package'

def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def row(p): return dict(path=str(p.relative_to(ROOT)), bytes=p.stat().st_size, sha256=sha(p))
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
assert sha(BASE / 'inputs.json') == '86d64218d50e23fd12ec4c9faec2d1baf4819e7b110c6c921d948873a51c5189'
inputs = read(BASE / 'inputs.json')['files']
assert len(inputs) == 244
verify(ROOT, inputs); verify(BASE / 'inputs', inputs)
selected = read(BASE / 'selected-source.json')
assert len(selected['installedLibraryFiles']) == 82
verify(ROOT, selected['installedLibraryFiles'])
verify(BASE / 'selected-source', selected['installedLibraryFiles'])
baseline = read(BASE / 'baseline/receipt.json')
assert baseline['tests'] == 861 and baseline['passed']
verify(BASE / 'baseline', baseline['files_after'])
runtime = read(BASE / 'RUNTIME_RESULTS.json')
assert runtime['passed'] and runtime['tests'] == 866 and runtime['previousTestIdsPreserved'] == 861
assert runtime['installedIdentityMatchesQualifiedCandidate'] and len(runtime['newHeldVaultCommitTests']) == 5
receipt_path = ROOT / runtime['runtimeReceipt']['path']
assert sha(receipt_path) == runtime['runtimeReceipt']['sha256']
receipt = read(receipt_path)
assert receipt['passed'] and receipt['inputs_stable'] and len(receipt['files_after']) == 244
verify(ROOT, receipt['files_after'])
assert read(BASE / 'inspection01.json') == read(BASE / 'references/identity-pins.json')
write(BASE / 'runtime-source-continuity.json', dict(runtimeReceipt=runtime['runtimeReceipt'],
    fullRuntimeTests=866, currentInputsVerified=244, previousTestIdsPreserved=861,
    addedLibraryFiles=82, addedTestFiles=1, changedPreviousFiles=['scripts/check_runtime.py'],
    unchangedPreviousInputs=160, mismatches=[], qualificationLibrariesInstalled=True,
    publicQualificationMounted=False, qualificationWorkerRepeated=False))
links_path = ROOT / 'artifacts/verification/project-links.json'
links = read(links_path)
assert not links['missing'] and sha(ROOT / 'scripts/check_project_links.py') == links['checker_sha256']
for r in links['files']: assert sha(ROOT / r['path']) == r['sha256']
write(BASE / 'RESULTS.json', dict(status='installed-libraries-and-public-regressions-verified',
    goalStatus='active', sourceCandidateIndexSha256=selected['sourceIndexSha256'],
    installedLibraryFiles=82, finiteIoHostModulesAdded=40, qualificationPackageFilesAdded=42,
    existingHostModulesUnchanged=43, schemaFilesUnchanged=7,
    importInspection=row(BASE / 'inspection01.json'), qualifiedIdentityPreserved=True,
    legacyNamePoisons=17, initializerDriftRefusals=4, packageModuleOrigins=39, producerImageFiles=267,
    sourceReview=row(BASE / 'source-review.json'), currentRuntimeAudit=row(BASE / 'RUNTIME_RESULTS.json'),
    currentRuntimeReceipt=runtime['runtimeReceipt'], publicTests=866, originalTestsPreserved=861,
    newOriginalVaultCommitChecks=5, stableInputs=244, nativeAndCSourceCaptured=True,
    publicQualificationMounted=False, qualificationWorkerRepeated=False,
    physicalExecutionPerformed=False, nativeProfileBroadened=False,
    aggregateStorageProviderQualified=False, independentReview=False, newResearchLfLines=0))
documents = ['README.md', 'PROGRESS.md', 'docs/pat-foundation.md', 'docs/prompt-to-pat.md',
             'docs/io-driver-hub-control.md', 'docs/control-storage.md', 'docs/qualification-libraries.md',
             'scripts/check_project_links.py', 'artifacts/verification/project-links.json']
final = copy(documents, BASE / 'final-documents')
write(BASE / 'checkpoint-verification.json', dict(runtimeInputsVerified=244, fullPublicTests=866,
    originalTestIdsPreserved=861, installedLibraryFilesVerified=82,
    projectMarkdownFiles=links['project_markdown_files'], localLinksChecked=links['local_links_checked'],
    missingLinks=[], linkReportSha256=sha(links_path), finalDocumentCopies=final,
    databaseConnectionsOpenedBySeal=0, goalStatus='active'))
paths = sorted(p for p in BASE.rglob('*') if p.is_file())
assert all(not p.is_symlink() for p in BASE.rglob('*'))
write(BASE / 'index.json', dict(files=[row(p) for p in paths],
    outcome='installed-libraries-and-public-regressions-verified', goalStatus='active'))
verify(ROOT, read(BASE / 'index.json')['files'])
selected_paths = documents + ['artifacts/implementation/runtime-qualification-package/' + name for name in
    ('README.md', 'NEXT.md', 'RESULTS.json', 'RUNTIME_RESULTS.json', 'source-review.json',
     'runtime-source-continuity.json', 'checkpoint-verification.json', 'index.json')]
selected_paths.append(str(receipt_path.relative_to(ROOT)))
copies = copy(selected_paths, CHECKPOINT / 'snapshot')
write(CHECKPOINT / 'index.json', dict(files=copies, stageIndexSha256=sha(BASE / 'index.json'),
    goalStatus='active', qualificationLibrariesInstalled=True, fullPublicTests=866,
    publicQualificationMounted=False))
verify(ROOT, read(CHECKPOINT / 'index.json')['files'])
print(json.dumps(dict(stageFiles=len(paths), stageIndexSha256=sha(BASE / 'index.json'),
    checkpointCopies=len(copies), checkpointIndexSha256=sha(CHECKPOINT / 'index.json'),
    localLinksChecked=links['local_links_checked'], missingLinks=0, goalStatus='active')))
