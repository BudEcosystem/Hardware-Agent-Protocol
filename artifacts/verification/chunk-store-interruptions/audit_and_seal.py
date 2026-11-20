"""Seal exact successful interruption evidence and current-state documentation."""
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


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def inventory(base):
    rows = []
    for path in sorted(base.rglob('*')):
        assert not path.is_symlink(), path
        if path.is_file() and path != base/'index.json':
            rows.append({'path': str(path.relative_to(base)), 'bytes': path.stat().st_size, 'sha256': sha(path)})
    return rows


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')


def main():
    assert not (HERE/'AUDIT.json').exists() and not (HERE/'index.json').exists()
    prior = ROOT/'artifacts/implementation/chunked-file-store'
    prior_hash = '10f160e60aa7f866782dda1f28bb8627de5d8e48182397216097cf2d0262fa8e'
    assert sha(prior/'index.json') == prior_hash
    assert read(prior/'index.json')['files'] == inventory(prior)
    inputs = read(ATTEMPT/'inputs.json')
    assert len(inputs['files']) == 15
    for row in inputs['files']:
        assert sha(ROOT/row['path']) == sha(ATTEMPT/'frozen-inputs'/row['frozen']) == row['sha256']
    assert (HERE/'cases.json').read_bytes() == (ATTEMPT/'frozen-inputs/cases.json').read_bytes()
    cases = read(HERE/'cases.json')['cases']
    attempt = read(ATTEMPT/'RESULTS.json')
    evidence = read(HERE/'EVIDENCE-AUDIT.json')
    assert attempt['status'] == 'passed' and attempt['inputsStable']
    assert len(cases) == len(attempt['cases']) == evidence['casesVerified'] == 22
    assert evidence['originalStopsVerified'] == attempt['selectedInterruptions'] == 24
    assert evidence['imagesReinspectedReadOnly'] == attempt['retainedImages'] == 46
    assert evidence['status'] == 'verified' and evidence['allImageBytesUnchanged'] and evidence['noRecoveryInvokedByAudit']
    assert len(evidence['stops']) == 24 and len(evidence['images']) == 46 and len(evidence['outcomes']) == 22
    assert len(evidence['originalPidsAbsent']) == 68
    assert all(not Path('/proc', str(pid)).exists() for pid in evidence['originalPidsAbsent'])
    for row in attempt['cases']:
        work = ATTEMPT/row['caseId']
        assert sha(work/'case-result.json') == row['resultSha256']
        assert read(work/'scope-result.json')['returnCode'] == 0
        assert read(work/'case-result.json') == read(work/'scope-stdout.txt')
    for row in evidence['images']:
        role = ATTEMPT/row['caseId']/row['role']
        for name, value in row['backingFiles'].items():
            assert sha(role/'image'/name) == value
    for row in evidence['stops']:
        role = ATTEMPT/row['caseId']/row['role']
        assert sha(role/'checkpoint.json') == row['checkpointSha256']
        assert read(role/'owner-result.json')['returnCode'] == -9
    for row in evidence['outcomes']:
        case = next(c for c in cases if c['id'] == row['caseId'])
        assert row['logical'] == case['expected'][row['matchedExpectedIndex']]
        assert sha(ATTEMPT/row['caseId']/'operation-intent.json') == row['intentSha256']
    backing = list(ATTEMPT.glob('*/**/image/chunk-00'))
    assert len(backing) == 46 and sum(p.stat().st_size for p in backing) == 736*1024**2
    runtime = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert sha(runtime) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    baseline = read(runtime)
    assert baseline['tests'] == 866 and baseline['passed'] and len(baseline['files']) == 244
    assert all(sha(ROOT/r['path']) == r['sha256'] for r in baseline['files'])
    documents = [ROOT/name for name in ['README.md', 'PROGRESS.md', 'docs/control-storage.md', 'docs/io-driver-hub-control.md']]
    documents += sorted(HERE.glob('*.md'))
    missing = []
    links = 0
    for doc in documents:
        for target in re.findall(r'\]\(([^)]+)\)', doc.read_text()):
            if '://' in target or target.startswith(('#', 'mailto:')):
                continue
            target = unquote(target.split('#', 1)[0].split(' "', 1)[0].strip('<>'))
            if not target:
                continue
            links += 1
            path = (doc.parent/target).resolve()
            if not path.exists() and path not in {HERE/'AUDIT.json', HERE/'index.json'}:
                missing.append({'document': str(doc.relative_to(ROOT)), 'target': target})
    assert not missing, missing
    for path in HERE.glob('*.py'):
        ast.parse(path.read_text())
    files = [p for p in HERE.rglob('*') if p.is_file()]
    assert all(p.stat().st_size <= 16*1024**2 for p in files)
    allocated = sum(p.stat().st_blocks*512 for p in files)
    assert allocated < 1024**3
    audit = {'schema': 'hms.chunk-interruption-stage-audit/1', 'auditedUnix': time.time(),
             'reviewer': 'primary agent only', 'priorStageIndexSha256': prior_hash, 'priorStageFilesExact': 141,
             'evidenceAuditSha256': sha(HERE/'EVIDENCE-AUDIT.json'), 'frozenInputsExact': 15,
             'casesPassed': 22, 'selectedOwnerTerminations': 24, 'retainedImages': 46,
             'backingBytes': 736*1024**2, 'allocatedBytesBeforeSeal': allocated,
             'runtimeFilesExact': 244, 'previousPublicTestsPassed': 866, 'publicSuiteRerun': False,
             'documents': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in documents],
             'localLinksChecked': links, 'missingLinks': [], 'candidateChanged': False,
             'physicalPowerLossTested': False, 'sqliteTested': False, 'allMutationInterruptionsTested': False,
             'serviceStorageQualified': False, 'aggregateServiceQuotaEnforced': False, 'backedControlCapacity': False}
    save(HERE/'AUDIT.json', audit)
    rows = inventory(HERE)
    save(HERE/'index.json', {'schema': 'hms.exact-file-index/1', 'files': rows})
    assert rows == inventory(HERE)
    print(json.dumps({'indexSha256': sha(HERE/'index.json'), 'indexedFiles': len(rows),
                      'casesPassed': 22, 'selectedOwnerTerminations': 24, 'retainedImages': 46,
                      'runtimeFilesExact': 244, 'localLinksChecked': links}, sort_keys=True))


if __name__ == '__main__':
    main()
