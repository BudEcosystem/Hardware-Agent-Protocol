"""Qualify the exact block-read evaluation with unchanged selected regressions."""
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIOR = ROOT/'artifacts/implementation/chunk-store-capacity'
OLD = ROOT/'artifacts/implementation/chunked-file-store'
INTERRUPT = ROOT/'artifacts/verification/chunk-store-interruptions'
ATTEMPT = HERE/'attempt01'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'}
BASE = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
BASE_HASH = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
PRIOR_HASH = 'bf56f465fc25384d32c1660a37cc4cff65207b1e83e1ce3c3010a55b59af03e9'
LIBRARY_HASH = 'be8b43b7ad909ed65b9ee834fccee3a769f08091c6fc0d1ad48a8ad14bd9abc2'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def baseline():
    assert sha(BASE) == BASE_HASH
    rows = read(BASE)['files']
    assert len(rows) == 244 and all(sha(ROOT/r['path']) == r['sha256'] for r in rows)
    return {'receiptSha256': BASE_HASH, 'filesExact': 244}


def limits(cpu):
    for key, count in [(resource.RLIMIT_CPU, cpu), (resource.RLIMIT_AS, 512*1024**2),
                       (resource.RLIMIT_FSIZE, 16*1024**2), (resource.RLIMIT_NOFILE, 128), (resource.RLIMIT_CORE, 0)]:
        resource.setrlimit(key, (count, count))


def run(relative, argv, env, wall=60, cpu=40):
    work = ATTEMPT/relative
    work.mkdir(mode=0o700, parents=True)
    save(work/'process-intent.json', {'argv': argv, 'cwd': str(work), 'environment': env,
                                     'wallSeconds': wall, 'cpuSeconds': cpu})
    start = time.monotonic()
    timed_out = False
    with (work/'stdout.txt').open('xb') as out, (work/'stderr.txt').open('xb') as err:
        proc = subprocess.Popen(argv, cwd=work, env=env, stdout=out, stderr=err,
                                start_new_session=True, preexec_fn=lambda: limits(cpu))
        save(work/'process-started.json', {'pid': proc.pid, 'processGroup': proc.pid, 'unix': time.time()})
        try:
            code = proc.wait(timeout=wall)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait(timeout=5)
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        out.flush()
        err.flush()
        os.fsync(out.fileno())
        os.fsync(err.fileno())
    result = {'returnCode': code, 'timedOut': timed_out, 'reaped': True,
              'elapsedSeconds': time.monotonic()-start}
    save(work/'process-result.json', result)
    if code != 0 or timed_out:
        raise RuntimeError(f'{relative}: failed or inconclusive; subsequent phases not started')
    assert (work/'stderr.txt').stat().st_size == 0
    print(json.dumps({'phase': relative, 'status': 'completed', 'seconds': round(result['elapsedSeconds'], 3)}), flush=True)
    return work


def main():
    os.umask(0o077)
    before = baseline()
    assert hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal')
    assert sha(PRIOR/'index.json') == PRIOR_HASH
    assert all(sha(PRIOR/r['path']) == r['sha256'] for r in read(PRIOR/'index.json')['files'])
    prior_tree = ast.parse((PRIOR/'run_stage.py').read_text())
    this_tree = ast.parse(Path(__file__).read_text())
    for name in ['sha', 'read', 'save', 'baseline', 'limits', 'run']:
        a = next(n for n in prior_tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        b = next(n for n in this_tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert ast.dump(a) == ast.dump(b), name
    prior = read(PRIOR/'block-read-evaluation/RESULTS.json')
    assert prior['status'] == 'observed' and prior['actualAllocatorEnospc']
    assert prior['librarySha256'] == LIBRARY_HASH and not prior['completeRegressionMatrixRun']
    usage = os.statvfs(HERE)
    free = usage.f_bavail*usage.f_frsize
    assert free > 1024**3+64*1024**2
    ATTEMPT.mkdir(mode=0o700)
    frozen = ATTEMPT/'frozen-inputs'
    frozen.mkdir(mode=0o700)
    sources = [(HERE/n, n) for n in ['PLAN.md', 'REVIEW.md', 'run_regressions.py']]
    sources += [(PRIOR/'chunk_store.py', 'chunk_store.py'), (PRIOR/'matrix.py', 'matrix.py'),
                (PRIOR/'block-read-evaluation/bridge.c', 'bridge.c'),
                (PRIOR/'block-read-evaluation/binaries/block-read.so', 'block-read.so'),
                (OLD/'controls.py', 'controls.py'), (OLD/'audit_images.py', 'readonly_image.py'),
                (INTERRUPT/'cases.json', 'cases.json')]
    sources += [(OLD/'attempt02/frozen-inputs'/n, n) for n in ['fixed_block.py', 'lfs.c', 'lfs.h', 'lfs_util.c', 'lfs_util.h', 'LICENSE.md']]
    rows = []
    for source, name in sources:
        dest = frozen/name
        with dest.open('xb') as f:
            f.write(source.read_bytes()); f.flush(); os.fsync(f.fileno())
        rows.append({'path': str(source.relative_to(ROOT)), 'frozen': name,
                     'bytes': dest.stat().st_size, 'sha256': sha(dest)})
    assert len(rows) == 16 and sha(frozen/'block-read.so') == LIBRARY_HASH
    cases = read(frozen/'cases.json')['cases']
    assert len(cases) == 22 and sum(len(c['cuts']) for c in cases) == 24
    save(ATTEMPT/'inputs.json', {'files': rows, 'baselineBefore': before, 'priorStageIndexSha256': PRIOR_HASH,
                               'retainedInventoryLimitBytes': 1024**3, 'maximumBackingBytes': 832*1024**2,
                               'availableBytesBefore': free, 'unchangedRunnerFunctions': 6})
    report = {'schema': 'hms.chunk-block-read-regressions/1', 'status': 'incomplete',
              'librarySha256': LIBRARY_HASH, 'semanticScopes': [], 'interruptionCases': [],
              'readSize': 4096, 'cacheSize': 4096, 'programSize': 16, 'geometryBlocks': 4096,
              'physicalPowerLossTested': False, 'sqliteTested': False, 'publicRuntimeInstalled': False,
              'serviceStorageQualified': False, 'backedControlCapacity': False,
              'aggregateServiceQuotaEnforced': False, 'allMutationInterruptionsTested': False}
    try:
        env = {**ENV, 'HMS_CHUNK_LIBRARY': str(frozen/'block-read.so'), 'HMS_CHUNK_LIBRARY_SHA256': LIBRARY_HASH}
        for name, count in [('semantics', 13), ('namespace', 12), ('recovery', 7), ('accounting', 5), ('caps', 11), ('fault', 6)]:
            work = run('semantics/'+name, [sys.executable, '-B', str(frozen/'controls.py'), name], env)
            result = read(work/'checks.json')
            assert result == read(work/'stdout.txt') and result['status'] == 'passed' and len(result['checks']) == count
            report['semanticScopes'].append({'scope': name, 'checks': count, 'resultSha256': sha(work/'checks.json')})
        for case in cases:
            work = run('interruptions/'+case['id'], [sys.executable, '-B', str(frozen/'matrix.py'), 'case', case['id']], env)
            result = read(work/'case-result.json')
            assert result == read(work/'stdout.txt') and result['status'] == 'passed' and result['logical'] in case['expected']
            assert result['selectedInterruptions'] == len(case['cuts'])
            report['interruptionCases'].append({'caseId': case['id'], 'interruptions': len(case['cuts']), 'resultSha256': sha(work/'case-result.json')})
        assert all(sha(ROOT/r['path']) == sha(frozen/r['frozen']) == r['sha256'] for r in rows)
        assert sha(PRIOR/'index.json') == PRIOR_HASH
        assert all(sha(PRIOR/r['path']) == r['sha256'] for r in read(PRIOR/'index.json')['files'])
        report['baselineAfter'] = baseline()
        files = [p for p in ATTEMPT.rglob('*') if p.is_file()]
        images = list(ATTEMPT.glob('**/image/chunk-00'))
        assert len(images) == 52 and all(p.stat().st_size == 16*1024**2 for p in images)
        assert all(p.stat().st_size <= 16*1024**2 for p in files)
        assert sum(p.stat().st_blocks*512 for p in files) < 1024**3
        report.update(status='passed', inputsStable=True, completeSelectedRegressionMatrixRun=True,
                      semanticChecks=54, interruptionCaseCount=22, selectedTerminations=24, retainedImages=52)
    except BaseException as exc:
        report['status'] = 'failed-or-inconclusive'
        report['error'] = f'{type(exc).__name__}: {exc}'
        save(ATTEMPT/'RESULTS.json', report)
        raise
    save(ATTEMPT/'RESULTS.json', report)
    print(json.dumps({k:v for k,v in report.items() if k not in {'semanticScopes', 'interruptionCases'}}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
