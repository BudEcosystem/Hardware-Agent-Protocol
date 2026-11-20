"""One-time evidence checkpoint; hashes files without importing runtime code."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]
STAGE = Path(__file__).resolve().parent
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt76-current-qualification-profile'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_new(path, document):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(document, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def verify_index(path, base, expected):
    assert digest(path) == expected, str(path)
    document = json.loads(path.read_text())
    for row in document['files']:
        member = base / row['path']
        assert member.is_file() and not member.is_symlink(), str(member)
        assert member.stat().st_size == row['bytes'], str(member)
        assert digest(member) == row['sha256'], str(member)
    return {'path': str(path.relative_to(ROOT)), 'sha256': expected,
            'verifiedFiles': len(document['files'])}


def inventory(directory):
    rows = []
    for path in sorted(directory.rglob('*')):
        assert not path.is_symlink(), str(path)
        if path.is_file():
            rows.append({'path': str(path.relative_to(ROOT)),
                         'bytes': path.stat().st_size, 'sha256': digest(path)})
    return rows


def copy_documents(paths, destination):
    rows = []
    for relative in paths:
        original = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        assert not target.exists(), str(target)
        shutil.copyfile(original, target)
        assert digest(original) == digest(target), relative
        rows.append({'path': str(target.relative_to(ROOT)),
                     'bytes': target.stat().st_size, 'sha256': digest(target),
                     'originalPath': relative})
    return rows


def main():
    assert not (STAGE / 'index.json').exists(), 'Stage already sealed'
    assert not CHECKPOINT.exists(), 'Checkpoint already exists'
    verified = [
        verify_index(STAGE / 'implementation01/index.json', ROOT,
                     'c84c5e713d05d731086c456286339db53fca310038af09584c6038894248a28c'),
        verify_index(STAGE / 'harness01/index.json', STAGE / 'harness01',
                     'c4206939f3ed17c47fb9912f6224000c7c937d057187bf947b92332b28678434'),
        verify_index(STAGE / 'harness02/index.json', STAGE / 'harness02',
                     'f8a67c4f89f3681b085f2094e8568a1b948ad313589e6ed6b7af67d5265b3c2a'),
        verify_index(ROOT / 'artifacts/verification/pat-ascii-canonical-evaluation/index.json', ROOT,
                     'a41ccd9339c176800cc4dbe0b3d21d97f69b4e9d49c7ff7bc55cfd0553bb903e'),
    ]
    receipt_path = ROOT / 'artifacts/verification/runtime-attempts/20261108T225058.349199Z-7581b13279cb/receipt.json'
    receipt_sha = 'aca07fa6dcdc3a883c3d7266422eaaaeb52d4b5ae223b60756306d39a43e58dc'
    assert digest(receipt_path) == receipt_sha
    receipt = json.loads(receipt_path.read_text())
    assert receipt['passed'] and receipt['tests'] == 861
    assert len(receipt['files_after']) == 161
    for row in receipt['files_after']:
        path = ROOT / row['path']
        assert digest(path) == row['sha256'], str(path)
        assert path.stat().st_size == row['bytes'], str(path)
    continuity = {'runtimeReceipt': str(receipt_path.relative_to(ROOT)),
                  'receiptSha256': receipt_sha, 'previousFullTests': 861,
                  'currentInputsVerified': 161, 'mismatches': [],
                  'runtimeRerunPerformed': False, 'productionRuntimeChanged': False}
    write_new(STAGE / 'runtime-source-continuity.json', continuity)
    baseline = ROOT / 'artifacts/implementation/qualification-package/implementation03/project/hms'
    current = STAGE / 'implementation01/project/hms'
    modules = sorted(baseline.rglob('*.py'))
    assert len(modules) == 83
    assert {p.relative_to(current) for p in current.rglob('*.py')} == {p.relative_to(baseline) for p in modules}
    for path in modules:
        assert digest(path) == digest(current / path.relative_to(baseline)), str(path)
    audit = json.loads((STAGE / 'RESULTS.json').read_text())
    assert audit['retentionAuditPassed'] and not audit['qualificationPassed']
    assert audit['diagnosticOnly'] and not audit['profilerProductionAdoptionPermitted']
    assert audit['workerCaseDatabasesOpened'] == 0
    assert audit['originalCoreHmsModulesUnchanged'] == 83
    assert audit['writtenCaseManifests'] == 21 and audit['incompleteCases'] == [21]
    assert (STAGE / 'audit01.stderr.txt').stat().st_size == 0
    links_path = ROOT / 'artifacts/verification/project-links.json'
    links = json.loads(links_path.read_text())
    assert links['missing'] == []
    assert digest(ROOT / 'scripts/check_project_links.py') == links['checker_sha256']
    for row in links['files']:
        assert digest(ROOT / row['path']) == row['sha256'], row['path']
    documents = ['README.md', 'PROGRESS.md', 'docs/prompt-to-pat.md',
                 'docs/io-driver-hub-control.md', 'docs/pat-foundation.md',
                 'scripts/check_project_links.py', 'artifacts/verification/project-links.json']
    copies = copy_documents(documents, STAGE / 'final-documents')
    write_new(STAGE / 'checkpoint-verification.json', {
        'sourceAndHarnessIndices': verified,
        'unchangedCoreHmsModules': 83, 'runtimeInputsVerified': 161,
        'retentionAuditSha256': digest(STAGE / 'RESULTS.json'),
        'linkReportSha256': digest(links_path),
        'projectMarkdownFiles': links['project_markdown_files'],
        'localLinksChecked': links['local_links_checked'], 'missingLinks': [],
        'finalDocumentCopies': copies, 'physicalExecutionPerformed': False,
        'qualificationPassed': False, 'workerEffectsUnresolved': True,
        'newWorkerLaunchedByCheckpoint': False, 'databaseConnectionsOpened': 0,
        'reviewer': 'primary-agent', 'independentReview': False})
    write_new(STAGE / 'index.json', {
        'files': inventory(STAGE), 'goalStatus': 'active',
        'diagnosticOnly': True, 'retentionAuditPassed': True,
        'qualificationPassed': False, 'productionRuntimeChanged': False,
        'asciiCandidateAdopted': False, 'workerEffectsUnresolved': True})
    CHECKPOINT.mkdir()
    selected = documents + [
        'artifacts/verification/qualification-current-profile/' + name
        for name in ['README.md', 'NEXT.md', 'RESULTS.json', 'index.json',
                     'runtime-source-continuity.json', 'checkpoint-verification.json']
    ] + ['artifacts/verification/pat-ascii-canonical-evaluation/' + name
         for name in ['README.md', 'RESULTS.json', 'DECISION.json', 'index.json']]
    snapshots = copy_documents(selected, CHECKPOINT / 'snapshot')
    write_new(CHECKPOINT / 'index.json', {
        'files': snapshots, 'stageIndexSha256': digest(STAGE / 'index.json'),
        'goalStatus': 'active', 'sourceRuntimeChanged': False,
        'actualQualificationPassed': False, 'asciiCandidateAdopted': False})
    print(json.dumps({'stageFiles': len(json.loads((STAGE / 'index.json').read_text())['files']),
                      'stageIndexSha256': digest(STAGE / 'index.json'),
                      'checkpointCopies': len(snapshots),
                      'checkpointIndexSha256': digest(CHECKPOINT / 'index.json'),
                      'runtimeInputsVerified': 161,
                      'linkCheck': {'files': links['project_markdown_files'],
                                    'links': links['local_links_checked'], 'missing': 0}}))


if __name__ == '__main__':
    main()
