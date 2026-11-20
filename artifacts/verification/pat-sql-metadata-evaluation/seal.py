"""Seal reviewed outcomes and documentation without runtime or database activity."""
import hashlib
import json
from pathlib import Path
import shutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
RESEARCH = ROOT / 'research/host-contract/sqlite-statement-cache'
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt77-sql-metadata-evaluation'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


def verify_index(path, prefix, expected):
    assert sha(path) == expected, str(path)
    rows = read(path)['files']
    for row in rows:
        p = prefix / row['path']
        assert p.is_file() and not p.is_symlink() and p.stat().st_size == row['bytes']
        assert sha(p) == row['sha256'], str(p)
    return len(rows)


def copies(names, destination):
    rows = []
    for name in names:
        source, target = ROOT / name, destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        assert not target.exists()
        shutil.copyfile(source, target)
        assert sha(target) == sha(source)
        rows.append({'path': str(target.relative_to(ROOT)), 'bytes': target.stat().st_size,
                     'sha256': sha(target), 'originalPath': name})
    return rows


assert not (BASE / 'index.json').exists() and not CHECKPOINT.exists()
assert verify_index(BASE / 'inputs.json', BASE,
    'c1c79e17db9a9cc77ce1d1ed4e0ce11856e64ccb5f5dcca93adcabdcbed61c2b') == 39
assert verify_index(RESEARCH / 'index.json', ROOT,
    'e48140f30f37d555b6db3bdf0db4d217566ef96279b0416b7d40396f65cc9f9b') == 15
assert sha(BASE / 'RESULTS.json') == '7245cac4e70aa3404577884b6dff541bb540b02dd1aa93ba732bd6fca3c7ade9'
results, decision = read(BASE / 'RESULTS.json'), read(BASE / 'DECISION.json')
assert results['retentionAuditPassed'] and results['differentialCases'] == 410
assert not results['integrationScreenPassed'] and not decision['adopted']
receipt_path = ROOT / 'artifacts/verification/runtime-attempts/20261108T225058.349199Z-7581b13279cb/receipt.json'
receipt_sha = 'aca07fa6dcdc3a883c3d7266422eaaaeb52d4b5ae223b60756306d39a43e58dc'
assert sha(receipt_path) == receipt_sha
receipt = read(receipt_path)
assert receipt['passed'] and receipt['tests'] == 861 and len(receipt['files_after']) == 161
for row in receipt['files_after']:
    path = ROOT / row['path']
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], str(path)
write(BASE / 'runtime-source-continuity.json', {
    'runtimeReceipt': str(receipt_path.relative_to(ROOT)), 'receiptSha256': receipt_sha,
    'previousFullTests': 861, 'currentInputsVerified': 161, 'mismatches': [],
    'runtimeRerunPerformed': False, 'productionRuntimeChanged': False})
links_path = ROOT / 'artifacts/verification/project-links.json'
links = read(links_path)
assert not links['missing'] and sha(ROOT / 'scripts/check_project_links.py') == links['checker_sha256']
for row in links['files']:
    assert sha(ROOT / row['path']) == row['sha256'], row['path']
documents = ['README.md', 'PROGRESS.md', 'docs/pat-foundation.md', 'docs/prompt-to-pat.md',
             'docs/io-driver-hub-control.md', 'scripts/check_project_links.py',
             'artifacts/verification/project-links.json']
final_documents = copies(documents, BASE / 'final-documents')
write(BASE / 'checkpoint-verification.json', {
    'frozenEvaluationInputsVerified': 39, 'researchIndexFilesVerified': 15,
    'researchIndexSha256': sha(RESEARCH / 'index.json'), 'researchCoveredLfLines': 477,
    'runtimeInputsVerified': 161, 'previousFullRuntimeTests': 861,
    'projectMarkdownFiles': links['project_markdown_files'],
    'localLinksChecked': links['local_links_checked'], 'missingLinks': [],
    'linkReportSha256': sha(links_path), 'finalDocumentCopies': final_documents,
    'candidateAdopted': False, 'benchmarkRepeated': False,
    'newQualificationWorkerLaunched': False, 'databaseConnectionsOpenedBySeal': 0,
    'physicalExecutionPerformed': False, 'goalStatus': 'active'})
files = []
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink(), str(path)
    if path.is_file():
        files.append({'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': sha(path)})
write(BASE / 'index.json', {'files': files, 'goalStatus': 'active', 'candidateAdopted': False,
    'semanticComparisonPassed': True, 'performanceScreenPassed': False,
    'productionRuntimeChanged': False, 'qualificationWorkerLaunched': False})
CHECKPOINT.mkdir()
selected = documents + ['artifacts/verification/pat-sql-metadata-evaluation/' + name
    for name in ('README.md', 'NEXT.md', 'RESULTS.json', 'DECISION.json', 'index.json',
                 'runtime-source-continuity.json', 'checkpoint-verification.json')]
selected += ['research/host-contract/sqlite-statement-cache/' + name
             for name in ('README.md', 'OBSERVATION.json', 'reading.json', 'index.json')]
snapshots = copies(selected, CHECKPOINT / 'snapshot')
write(CHECKPOINT / 'index.json', {'files': snapshots, 'stageIndexSha256': sha(BASE / 'index.json'),
    'researchIndexSha256': sha(RESEARCH / 'index.json'), 'goalStatus': 'active',
    'sourceRuntimeChanged': False, 'candidateAdopted': False})
print(json.dumps({'stageFiles': len(files), 'stageIndexSha256': sha(BASE / 'index.json'),
    'checkpointCopies': len(snapshots), 'checkpointIndexSha256': sha(CHECKPOINT / 'index.json'),
    'runtimeInputsVerified': 161, 'localLinksChecked': links['local_links_checked'], 'missingLinks': 0}))
