"""Seal exact block-read regressions and distinguish remaining service obligations."""
import ast
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ATTEMPT = HERE/'attempt01'
PRIOR = ROOT/'artifacts/implementation/chunk-store-capacity'
PRIOR_HASH = 'bf56f465fc25384d32c1660a37cc4cff65207b1e83e1ce3c3010a55b59af03e9'


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
    assert sha(PRIOR/'index.json') == PRIOR_HASH
    prior_rows = inventory(PRIOR)
    assert prior_rows == read(PRIOR/'index.json')['files'] and len(prior_rows) == 1090
    frozen = ATTEMPT/'frozen-inputs'
    inputs = read(ATTEMPT/'inputs.json')
    assert len(inputs['files']) == 16 and inputs['unchangedRunnerFunctions'] == 6
    for row in inputs['files']:
        assert sha(ROOT/row['path']) == sha(frozen/row['frozen']) == row['sha256']
    result = read(ATTEMPT/'RESULTS.json')
    evidence = read(HERE/'EVIDENCE-AUDIT.json')
    assert result['status'] == 'passed' and result['inputsStable'] and result['completeSelectedRegressionMatrixRun']
    assert result['librarySha256'] == sha(frozen/'block-read.so') == sha(PRIOR/'block-read-evaluation/binaries/block-read.so')
    assert evidence['status'] == 'verified' and evidence['allAuditedImageBytesUnchanged']
    assert result['semanticChecks'] == evidence['semanticChecks'] == 54
    assert result['interruptionCaseCount'] == evidence['interruptionCases'] == 22
    assert result['selectedTerminations'] == evidence['selectedStopsVerified'] == len(evidence['stops']) == 24
    assert result['retainedImages'] == evidence['retained16MiBImages'] == len(evidence['regressionImagesReadOnly']) == 52
    assert evidence['distinctObjectAnchors'] == 208 and len(evidence['processes']) == 75
    assert not result['publicRuntimeInstalled'] and not result['serviceStorageQualified']
    for row in result['semanticScopes']:
        work = ATTEMPT/'semantics'/row['scope']
        assert sha(work/'checks.json') == row['resultSha256']
        assert read(work/'checks.json') == read(work/'stdout.txt')
        assert len(read(work/'checks.json')['checks']) == row['checks']
    cases = read(frozen/'cases.json')['cases']
    assert len(cases) == len(result['interruptionCases']) == 22
    for case, row in zip(cases, result['interruptionCases']):
        assert case['id'] == row['caseId'] and len(case['cuts']) == row['interruptions']
        work = ATTEMPT/'interruptions'/case['id']
        assert sha(work/'case-result.json') == row['resultSha256']
        assert read(work/'case-result.json') == read(work/'stdout.txt')
        assert read(work/'case-result.json')['logical'] in case['expected']
    for row in evidence['regressionImagesReadOnly']:
        role = ATTEMPT/'semantics'/row['scope'] if row['kind'] == 'semantic' else ATTEMPT/'interruptions'/row['caseId']/row['role']
        assert all(sha(role/'image'/name) == digest for name, digest in row['backingFiles'].items())
    for row in evidence['processes']:
        path = HERE/row['path']
        assert read(path)['pid'] == row['pid'] and not Path('/proc', str(row['pid'])).exists()
        terminal = read(path.with_name(path.name.replace('started', 'result')))
        assert terminal['reaped'] and terminal['returnCode'] == row['returnCode']
    assert sum(r['returnCode'] == -9 for r in evidence['processes']) == 24
    for number, code in [(1, 1), (2, 0)]:
        work = HERE/f'audit-process{number:02d}'
        terminal = read(work/'result.json')
        assert terminal['returnCode'] == code and terminal['reaped'] and not terminal['timedOut']
        assert not Path('/proc', str(read(work/'started.json')['pid'])).exists()
    correction = read(HERE/'audit-process01/correction.json')
    assert sha(HERE/'audit-process01/audit-source.py') == correction['originalSourceSha256']
    assert sha(HERE/'audit_evidence.py') == correction['correctedSourceSha256']
    assert correction['correctedSourceSha256'] == read(HERE/'audit-process02/intent.json')['sourceSha256']
    baseline = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert sha(baseline) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    runtime = read(baseline)
    assert runtime['passed'] and runtime['tests'] == 866 and len(runtime['files']) == 244
    assert all(sha(ROOT/r['path']) == r['sha256'] for r in runtime['files'])
    docs = [ROOT/n for n in ['README.md', 'PROGRESS.md', 'docs/control-storage.md', 'docs/io-driver-hub-control.md']]
    docs += sorted(HERE.glob('*.md'))
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
    for path in HERE.rglob('*.py'):
        ast.parse(path.read_text())
    files = [p for p in HERE.rglob('*') if p.is_file()]
    assert all(p.stat().st_size <= 16*1024**2 for p in files)
    assert sum(p.stat().st_size == 16*1024**2 for p in files) == 52
    allocated = sum(p.stat().st_blocks*512 for p in files)
    assert allocated < 1024**3
    audit = {'schema': 'hms.chunk-block-read-stage-audit/1', 'auditedUnix': time.time(),
             'reviewer': 'primary agent only', 'priorIndexSha256': PRIOR_HASH, 'priorFilesExact': 1090,
             'frozenInputsExact': 16, 'candidateAndBinaryUnchanged': True, 'unchangedProcessRunnerFunctions': 6,
             'evidenceAuditSha256': sha(HERE/'EVIDENCE-AUDIT.json'), 'semanticChecks': 54,
             'interruptionCases': 22, 'selectedTerminations': 24, 'retainedImages': 52,
             'distinctObjectAnchors': 208, 'recordedPidsAbsent': 75, 'backingBytes': 832*1024**2,
             'allocatedBytesBeforeSeal': allocated, 'runtimeFilesExact': 244,
             'previousPublicTestsPassed': 866, 'publicSuiteRerun': False, 'capacityExperimentRepeated': False,
             'localLinksChecked': links, 'missingLinks': [],
             'documents': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in docs],
             'publicRuntimeInstalled': False, 'serviceStorageQualified': False,
             'aggregateServiceQuotaEnforced': False, 'backedControlCapacity': False,
             'allMutationInterruptionsTested': False, 'physicalPowerLossTested': False, 'sqliteTested': False}
    save(HERE/'AUDIT.json', audit)
    rows = inventory(HERE)
    save(HERE/'index.json', {'schema': 'hms.exact-file-index/1', 'files': rows})
    assert rows == inventory(HERE)
    print(json.dumps({'indexSha256': sha(HERE/'index.json'), 'indexedFiles': len(rows),
                      'semanticChecks': 54, 'interruptionCases': 22, 'selectedTerminations': 24,
                      'retainedImages': 52, 'runtimeFilesExact': 244, 'localLinksChecked': links}, sort_keys=True))


if __name__ == '__main__':
    main()
