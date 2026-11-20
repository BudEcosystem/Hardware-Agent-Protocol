"""Seal separate regression and capacity conclusions without repairing evidence."""
import ast
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def inventory(base):
    rows = []
    for p in sorted(base.rglob('*')):
        assert not p.is_symlink(), p
        if p.is_file() and p != base/'index.json':
            rows.append({'path': str(p.relative_to(base)), 'bytes': p.stat().st_size, 'sha256': sha(p)})
    return rows


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')


def main():
    assert not (HERE/'AUDIT.json').exists() and not (HERE/'index.json').exists()
    prior = [
        ('research/host-contract/fixed-block-storage', 'b6fb69fe4bc77b8184e6e426093c1d9cae7292ee055238f2eddf73ab78144467'),
        ('artifacts/implementation/fixed-block-storage', 'f294c785dbe9d966e06a1c3b6b88dc5e14850027c39293fc9afda1cb67611972'),
        ('research/host-contract/littlefs-core', 'c149f635c72262102a1d5c2ff3f2fc08c56fc6dc1fc9a1306037114d1650fd0e'),
        ('artifacts/verification/littlefs-semantics', 'cba58c11e5c32471982a8875607beca5704ac165d4da446760049aefcc4eb231'),
        ('artifacts/implementation/chunked-file-store', '10f160e60aa7f866782dda1f28bb8627de5d8e48182397216097cf2d0262fa8e'),
        ('artifacts/verification/chunk-store-interruptions', 'd2e6c479d06654485ca1577928471c47d7992456b83fa4bfca3bef06fb4aa7a3'),
    ]
    prior_rows = []
    for path, digest in prior:
        base = ROOT/path
        assert sha(base/'index.json') == digest
        rows = inventory(base)
        assert rows == read(base/'index.json')['files']
        prior_rows.append({'path': path, 'indexSha256': digest, 'filesExact': len(rows)})
    original = HERE/'attempt01'
    evaluation = HERE/'block-read-evaluation'
    frozen = []
    for base, count in [(original, 17), (evaluation, 13)]:
        rows = read(base/'inputs.json')['files']
        assert len(rows) == count
        for r in rows:
            assert sha(ROOT/r['path']) == sha(base/'frozen-inputs'/r['frozen']) == r['sha256']
        frozen.append({'path': str(base.relative_to(HERE)), 'filesExact': count})
    preserved = read(HERE/'attempt01-preservation.json')['files']
    assert len(preserved) == 892
    assert all(sha(original/r['path']) == r['sha256'] for r in preserved)
    first = read(original/'RESULTS.json')
    second = read(evaluation/'RESULTS.json')
    evidence = read(HERE/'EVIDENCE-AUDIT.json')
    assert first['status'] == 'failed-or-inconclusive'
    assert second['status'] == 'observed' and second['actualAllocatorEnospc']
    assert not second['adopted'] and not second['completeRegressionMatrixRun']
    assert evidence['status'] == 'verified' and evidence['allAuditedImageBytesUnchanged']
    assert evidence['smallCacheSemanticChecks'] == 54 and evidence['smallCacheInterruptionCases'] == 22
    assert evidence['selectedStopsVerified'] == 24 and len(evidence['regressionImagesReadOnly']) == 52
    assert len(evidence['blockReadCapacityImages']) == 3 and evidence['confirmedPayloadBytesVerified'] == 16080896
    assert evidence['originalAttemptFilesExact'] == 892 and evidence['retained16MiBImages'] == 61
    assert not evidence['failedPendingAppendPublished'] and evidence['newMetadataAllocationFailed']
    assert all(not Path('/proc', str(r['pid'])).exists() for r in evidence['processes'])
    for i, code in [(1, 1), (2, 0)]:
        work = HERE/f'audit-process{i:02d}'
        result = read(work/'result.json')
        assert result['returnCode'] == code and result['reaped'] and not result['timedOut']
        assert not Path('/proc', str(read(work/'started.json')['pid'])).exists()
    fix = read(HERE/'audit-process01/correction.json')
    assert sha(HERE/'audit-process01/audit-source.py') == fix['originalSourceSha256']
    assert sha(HERE/'audit_evidence.py') == fix['correctedSourceSha256']
    assert fix['correctedSourceSha256'] == read(HERE/'audit-process02/intent.json')['sourceSha256']
    baseline = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert sha(baseline) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    runtime = read(baseline)
    assert runtime['tests'] == 866 and runtime['passed'] and len(runtime['files']) == 244
    assert all(sha(ROOT/r['path']) == r['sha256'] for r in runtime['files'])
    docs = [ROOT/n for n in ['README.md', 'PROGRESS.md', 'docs/control-storage.md', 'docs/io-driver-hub-control.md']]
    docs += sorted(HERE.glob('*.md')) + [evaluation/'PLAN.md']
    links = 0
    for doc in docs:
        for target in re.findall(r'\]\(([^)]+)\)', doc.read_text()):
            if '://' in target or target.startswith(('#', 'mailto:')):
                continue
            target = unquote(target.split('#', 1)[0].split(' "', 1)[0].strip('<>'))
            if target:
                links += 1
                path = (doc.parent/target).resolve()
                assert path.exists() or path in {HERE/'AUDIT.json', HERE/'index.json'}, (doc, target)
    for p in HERE.rglob('*.py'):
        ast.parse(p.read_text())
    files = [p for p in HERE.rglob('*') if p.is_file()]
    assert all(p.stat().st_size <= 16*1024**2 for p in files)
    assert sum(p.stat().st_size == 16*1024**2 for p in files) == 61
    allocated = sum(p.stat().st_blocks*512 for p in files)
    assert allocated < 1024**3
    audit = {'schema': 'hms.chunk-capacity-stage-audit/1', 'auditedUnix': time.time(),
             'reviewer': 'primary agent only', 'priorStages': prior_rows, 'frozenInputs': frozen,
             'evidenceAuditSha256': sha(HERE/'EVIDENCE-AUDIT.json'), 'originalFilesPreserved': 892,
             'smallCacheSemanticChecks': 54, 'smallCacheInterruptionCases': 22, 'selectedTerminations': 24,
             'originalHostCapacityIncomplete': True, 'blockReadActualAllocatorEnospc': True,
             'blockReadFullRegressionsRun': False, 'blockReadAdopted': False,
             'retainedImages': 61, 'backingBytes': 976*1024**2, 'allocatedBytesBeforeSeal': allocated,
             'runtimeFilesExact': 244, 'previousPublicTestsPassed': 866, 'publicSuiteRerun': False,
             'localLinksChecked': links, 'missingLinks': [],
             'documents': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in docs],
             'serviceStorageQualified': False, 'aggregateServiceQuotaEnforced': False,
             'backedControlCapacity': False, 'physicalPowerLossTested': False, 'sqliteTested': False}
    save(HERE/'AUDIT.json', audit)
    rows = inventory(HERE)
    save(HERE/'index.json', {'schema': 'hms.exact-file-index/1', 'files': rows})
    assert rows == inventory(HERE)
    print(json.dumps({'indexSha256': sha(HERE/'index.json'), 'indexedFiles': len(rows),
                      'priorFilesExact': sum(r['filesExact'] for r in prior_rows),
                      'runtimeFilesExact': 244, 'localLinksChecked': links}, sort_keys=True))


if __name__ == '__main__':
    main()
