"""Verify original evidence, unchanged runtime and current documents; seal once."""
import ast
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCOPES = {'semantics': 13, 'namespace': 12, 'recovery': 7, 'accounting': 5, 'caps': 11, 'fault': 6}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def inventory(directory):
    rows = []
    for path in sorted(directory.rglob('*')):
        assert not path.is_symlink(), path
        if path.is_file() and path != directory/'index.json':
            rows.append({'path': str(path.relative_to(directory)), 'bytes': path.stat().st_size, 'sha256': sha(path)})
    return rows


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')


def main():
    assert not (HERE/'AUDIT.json').exists() and not (HERE/'index.json').exists()
    prior = []
    for relative, expected in [
        ('artifacts/verification/littlefs-semantics', 'cba58c11e5c32471982a8875607beca5704ac165d4da446760049aefcc4eb231'),
        ('research/host-contract/littlefs-core', 'c149f635c72262102a1d5c2ff3f2fc08c56fc6dc1fc9a1306037114d1650fd0e'),
        ('artifacts/implementation/fixed-block-storage', 'f294c785dbe9d966e06a1c3b6b88dc5e14850027c39293fc9afda1cb67611972')]:
        base = ROOT/relative
        assert sha(base/'index.json') == expected
        rows = read(base/'index.json')['files']
        assert inventory(base) == rows
        prior.append({'path': relative, 'sha256': expected, 'filesExact': len(rows)})
    failed = read(HERE/'attempt01-preservation.json')
    assert failed['files'] == inventory(HERE/'attempt01')
    assert read(HERE/'attempt01/RESULTS.json')['status'] == 'failed-or-inconclusive'
    assert read(HERE/'attempt01/semantics/result.json')['returnCode'] == 1
    for name in list(SCOPES)[1:]:
        assert not (HERE/'attempt01'/name).exists()
    old = (HERE/'attempt01/frozen-inputs/bridge.c').read_text()
    corrected = old.replace('struct lfs_info info;\n    int rc=lfs_stat',
                            'struct lfs_info info={0};\n    int rc=lfs_stat', 1)
    corrected = corrected.replace('*type=info.type; *size=info.size;',
                                  '*type=info.type; *size=info.type==LFS_TYPE_REG ? info.size : 0;', 1)
    assert (HERE/'bridge.c').read_text() == corrected
    attempt = HERE/'attempt02'
    report = read(attempt/'RESULTS.json')
    assert report['status'] == 'passed' and report['inputsStable']
    assert set(report['scopes']) == set(SCOPES)
    inputs = read(attempt/'inputs.json')
    assert len(inputs['files']) == 13
    for row in inputs['files']:
        assert sha(ROOT/row['path']) == sha(attempt/'frozen-inputs'/row['frozen']) == row['sha256']
    for name in ['chunk_store.py', 'controls.py']:
        assert (HERE/name).read_bytes() == (HERE/'attempt01/frozen-inputs'/name).read_bytes()
    assert sha(Path(inputs['compiler'])) == inputs['compilerSha256']
    assert sha(attempt/'chunk-store.so') == report['librarySha256']
    terminal = []
    check_names = []
    for attempt_name, names in [('attempt01', ['compiler-version', 'build', 'semantics']),
                                ('attempt02', ['compiler-version', 'build', *SCOPES])]:
        for name in names:
            scope = HERE/attempt_name/name
            started = read(scope/'started.json')
            result = read(scope/'result.json')
            intent = read(scope/'intent.json')
            assert result['reaped'] and not result['timedOut']
            assert result['elapsedSeconds'] < intent['wallSeconds']
            assert not Path('/proc', str(started['pid'])).exists()
            if attempt_name == 'attempt02':
                assert result['returnCode'] == 0 and (scope/'stderr.txt').stat().st_size == 0
                if name in SCOPES:
                    checks = read(scope/'checks.json')
                    assert read(scope/'stdout.txt') == checks
                    assert checks['status'] == 'passed' and checks['scope'] == name
                    assert len(checks['checks']) == SCOPES[name] == report['scopes'][name]['checks']
                    assert sha(scope/'checks.json') == report['scopes'][name]['resultSha256']
                    check_names += [f'{name}:{check}' for check in checks['checks']]
            terminal.append({'attempt': attempt_name, 'scope': name, 'pid': started['pid'], **result})
    assert len(check_names) == len(set(check_names)) == 54
    child = read(attempt/'recovery/owner-started.json')
    assert not Path('/proc', str(child['pid'])).exists()
    assert read(attempt/'recovery/owner-result.json') == {'reaped': True, 'returnCode': 0}
    assert read(attempt/'recovery/owner-before-exit.json')['pid'] == child['pid']
    inspection = read(HERE/'image-readback.json')
    assert inspection['status'] == 'verified' and inspection['noImageBytesChanged']
    assert inspection['readOnlyObjectLocksHeld'] == 28 and inspection['noRecoveryOrFormatInvoked']
    assert len(inspection['images']) == 6
    for image in inspection['images']:
        for name, expected in image['backingFiles'].items():
            assert sha(attempt/image['scope']/'image'/name) == expected
        assert all(image['callbacks'][key] == 0 for key in ['programCalls', 'programBytes', 'erases', 'syncs'])
    backing = list(HERE.glob('attempt*/**/image/chunk-00'))
    assert len(backing) == 7 and sum(p.stat().st_size for p in backing) == 112*1024**2
    runtime = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert sha(runtime) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    baseline = read(runtime)
    assert baseline['tests'] == 866 and baseline['passed'] and len(baseline['files']) == 244
    assert all(sha(ROOT/r['path']) == r['sha256'] for r in baseline['files'])
    documents = [ROOT/name for name in ['README.md', 'PROGRESS.md', 'docs/control-storage.md', 'docs/io-driver-hub-control.md']]
    documents += sorted(HERE.glob('*.md'))
    local_links = 0
    missing = []
    for doc in documents:
        for target in re.findall(r'\]\(([^)]+)\)', doc.read_text()):
            if '://' in target or target.startswith(('#', 'mailto:')):
                continue
            target = unquote(target.split('#', 1)[0].split(' "', 1)[0].strip('<>'))
            if not target:
                continue
            local_links += 1
            path = (doc.parent/target).resolve()
            if not path.exists() and path not in {HERE/'AUDIT.json', HERE/'index.json'}:
                missing.append({'document': str(doc.relative_to(ROOT)), 'target': target})
    assert not missing, missing
    for path in HERE.glob('*.py'):
        ast.parse(path.read_text())
    files = [p for p in HERE.rglob('*') if p.is_file()]
    assert all(p.stat().st_size <= 16*1024**2 for p in files)
    assert sum(p.stat().st_blocks*512 for p in files) < 256*1024**2
    audit = {'schema': 'hms.chunk-store-stage-audit/1', 'auditedUnix': time.time(),
             'reviewer': 'primary agent only', 'priorSeals': prior, 'failedAttemptFilesExact': len(failed['files']),
             'correctedAttemptInputsExact': 13, 'checkNames': check_names, 'checksPassed': 54,
             'scopeResults': terminal, 'ownerExitPid': child['pid'], 'ownerExitPhase': 'after completed sync',
             'imageReadbackSha256': sha(HERE/'image-readback.json'), 'backingBytes': 112*1024**2,
             'runtimeFilesExact': 244, 'previousPublicTestsPassed': 866, 'publicSuiteRerun': False,
             'documents': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in documents],
             'localLinksChecked': local_links, 'missingLinks': [],
             'filesystemMounted': False, 'sqliteTested': False, 'physicalPowerLossTested': False,
             'serviceStorageQualified': False, 'aggregateServiceQuotaEnforced': False,
             'backedControlCapacity': False, 'allMutationInterruptionsTested': False}
    save(HERE/'AUDIT.json', audit)
    rows = inventory(HERE)
    save(HERE/'index.json', {'schema': 'hms.exact-file-index/1', 'files': rows})
    assert inventory(HERE) == rows
    print(json.dumps({'indexSha256': sha(HERE/'index.json'), 'indexedFiles': len(rows),
                      'checksPassed': 54, 'scopesPassed': 6, 'runtimeFilesExact': 244,
                      'localLinksChecked': local_links, 'backingBytes': 112*1024**2}, sort_keys=True))


if __name__ == '__main__':
    main()
