"""Seal reviewed outcomes and documentation without runtime or database activity."""
import hashlib
import json
from pathlib import Path
import shutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
RESEARCH = ROOT / 'research/host-contract/sqlite-cache-binding'
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt78-statement-cache-evaluation'


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
    '4701ceda4a10ac8443822753944e0935ddbb6c7688da1c97dcac5a28fb6764e5') == 85
assert verify_index(BASE / 'evaluation02/inputs.json', BASE / 'evaluation02',
    'd6238ac531a8d8b26ebda66a361d937d348abef7511b0e85ed6e7f2019d7f807') == 91
assert verify_index(RESEARCH / 'index.json', ROOT,
    'c1a9eca2686e7d0d3ee0a27321e859845732cc400ac3f3427e38d3b9c77ad2d9') == 6
assert sha(BASE / 'RESULTS.json') == '8232ef9b3c286d877b23b53c8752565de39fb8dbec77404b19593dcd1c2f729a'
results, decision = read(BASE / 'RESULTS.json'), read(BASE / 'DECISION.json')
assert results['retentionAuditPassed'] and results['differentialCases'] == 62
assert results['integrationScreenPassed'] and decision['advanceToIsolatedWorkerIntegration']
assert not decision['productionAdopted'] and results['timingRunsPerformed'] == 1
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
    'frozenEvaluationInputsVerified': 91, 'frozenFailedInputsVerified': 85,
    'researchIndexFilesVerified': 6,
    'researchIndexSha256': sha(RESEARCH / 'index.json'), 'researchCoveredLfLines': 4025,
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
    'semanticComparisonPassed': True, 'performanceScreenPassed': True,
    'productionRuntimeChanged': False, 'qualificationWorkerLaunched': False})
CHECKPOINT.mkdir()
selected = documents + ['artifacts/verification/pat-statement-cache-evaluation/' + name
    for name in ('README.md', 'NEXT.md', 'RESULTS.json', 'DECISION.json', 'index.json',
                 'runtime-source-continuity.json', 'checkpoint-verification.json')]
selected += ['research/host-contract/sqlite-cache-binding/' + name
             for name in ('README.md', 'acquisition.json', 'reading.json', 'index.json')]
snapshots = copies(selected, CHECKPOINT / 'snapshot')
write(CHECKPOINT / 'index.json', {'files': snapshots, 'stageIndexSha256': sha(BASE / 'index.json'),
    'researchIndexSha256': sha(RESEARCH / 'index.json'), 'goalStatus': 'active',
    'sourceRuntimeChanged': False, 'candidateAdopted': False})
print(json.dumps({'stageFiles': len(files), 'stageIndexSha256': sha(BASE / 'index.json'),
    'checkpointCopies': len(snapshots), 'checkpointIndexSha256': sha(CHECKPOINT / 'index.json'),
    'runtimeInputsVerified': 161, 'localLinksChecked': links['local_links_checked'], 'missingLinks': 0}))
