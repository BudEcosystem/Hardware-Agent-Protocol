"""Freeze and run the complete declared interruption matrix once."""
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
STAGE84 = ROOT/'artifacts/implementation/chunked-file-store'
ATTEMPT = HERE/'attempt01'
BASE = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
BASE_HASH = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'}


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def baseline():
    assert sha(BASE) == BASE_HASH
    rows = json.loads(BASE.read_text())['files']
    assert len(rows) == 244 and all(sha(ROOT/r['path']) == r['sha256'] for r in rows)
    return {'receiptSha256': BASE_HASH, 'filesExact': 244}


def limits():
    for key, amount in [(resource.RLIMIT_CPU, 40), (resource.RLIMIT_AS, 512*1024**2),
                        (resource.RLIMIT_FSIZE, 16*1024**2), (resource.RLIMIT_NOFILE, 128),
                        (resource.RLIMIT_CORE, 0)]:
        resource.setrlimit(key, (amount, amount))


def run(case, frozen):
    work = ATTEMPT/case['id']
    work.mkdir(mode=0o700)
    argv = [sys.executable, '-B', str(frozen/'matrix.py'), 'case', case['id']]
    save(work/'scope-intent.json', {'case': case, 'argv': argv, 'environment': ENV,
                                   'cwd': str(work), 'wallSeconds': 60, 'cpuSeconds': 40})
    started = time.monotonic()
    timed_out = False
    with (work/'scope-stdout.txt').open('xb') as out, (work/'scope-stderr.txt').open('xb') as err:
        proc = subprocess.Popen(argv, cwd=work, env=ENV, stdout=out, stderr=err,
                                start_new_session=True, preexec_fn=limits)
        save(work/'scope-started.json', {'pid': proc.pid, 'processGroup': proc.pid, 'unix': time.time()})
        try:
            code = proc.wait(timeout=60)
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
    terminal = {'returnCode': code, 'reaped': True, 'timedOut': timed_out,
                'elapsedSeconds': time.monotonic()-started}
    save(work/'scope-result.json', terminal)
    if code != 0 or timed_out:
        raise RuntimeError(f'{case["id"]}: failed or inconclusive; remaining matrix not started')
    assert (work/'scope-stderr.txt').stat().st_size == 0 and (work/'scope-stdout.txt').stat().st_size <= 65536
    result = json.loads((work/'case-result.json').read_text())
    assert result == json.loads((work/'scope-stdout.txt').read_text())
    assert result['caseId'] == case['id'] and result['status'] == 'passed'
    assert result['selectedInterruptions'] == len(case['cuts']) and result['logical'] in case['expected']
    return {'caseId': case['id'], 'selectedInterruptions': len(case['cuts']),
            'resultSha256': sha(work/'case-result.json'), 'elapsedSeconds': terminal['elapsedSeconds']}


def main():
    os.umask(0o077)
    assert hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal')
    before = baseline()
    assert sha(STAGE84/'index.json') == '10f160e60aa7f866782dda1f28bb8627de5d8e48182397216097cf2d0262fa8e'
    for row in json.loads((STAGE84/'index.json').read_text())['files']:
        assert sha(STAGE84/row['path']) == row['sha256']
    usage = os.statvfs(HERE)
    free = usage.f_bavail*usage.f_frsize
    assert free > 1024**3+64*1024**2
    ATTEMPT.mkdir(mode=0o700)
    frozen = ATTEMPT/'frozen-inputs'
    frozen.mkdir(mode=0o700)
    sources = [(HERE/name, name) for name in ['PLAN.md', 'REVIEW.md', 'cases.json', 'matrix.py', 'run_matrix.py']]
    sources += [(STAGE84/'chunk_store.py', 'chunk_store.py'), (STAGE84/'bridge.c', 'bridge.c'),
                (STAGE84/'audit_images.py', 'readonly_image.py'),
                (STAGE84/'attempt02/frozen-inputs/fixed_block.py', 'fixed_block.py'),
                (STAGE84/'attempt02/chunk-store.so', 'chunk-store.so')]
    sources += [(STAGE84/'attempt02/frozen-inputs'/name, name) for name in ['lfs.c', 'lfs.h', 'lfs_util.c', 'lfs_util.h', 'LICENSE.md']]
    rows = []
    for source, name in sources:
        dest = frozen/name
        with dest.open('xb') as f:
            f.write(source.read_bytes())
            f.flush()
            os.fsync(f.fileno())
        rows.append({'path': str(source.relative_to(ROOT)), 'frozen': name,
                     'bytes': dest.stat().st_size, 'sha256': sha(dest)})
    assert len(rows) == 15
    cases = json.loads((frozen/'cases.json').read_text())['cases']
    assert len(cases) == 22 and len({c['id'] for c in cases}) == 22 and sum(len(c['cuts']) for c in cases) == 24
    save(ATTEMPT/'inputs.json', {'files': rows, 'baselineBefore': before, 'availableBytesBefore': free,
                               'retainedInventoryLimitBytes': 1024**3, 'maximumBackingBytes': 736*1024**2})
    report = {'schema': 'hms.chunk-interruption-attempt/1', 'status': 'incomplete', 'cases': [],
              'physicalPowerLossTested': False, 'sqliteTested': False,
              'serviceStorageQualified': False, 'backedControlCapacity': False,
              'aggregateServiceQuotaEnforced': False, 'allMutationInterruptionsTested': False}
    try:
        for case in cases:
            result = run(case, frozen)
            report['cases'].append(result)
            print(json.dumps({'caseId': case['id'], 'status': 'passed', 'interruptions': len(case['cuts'])}), flush=True)
        assert all(sha(ROOT/r['path']) == sha(frozen/r['frozen']) == r['sha256'] for r in rows)
        report['baselineAfter'] = baseline()
        files = [p for p in ATTEMPT.rglob('*') if p.is_file()]
        assert all(p.stat().st_size <= 16*1024**2 for p in files)
        assert sum(p.stat().st_blocks*512 for p in files) < 1024**3
        images = list(ATTEMPT.glob('*/**/image/chunk-00'))
        assert len(images) == 46 and sum(p.stat().st_size for p in images) == 736*1024**2
        report.update(status='passed', inputsStable=True, selectedInterruptions=24, retainedImages=46)
    except BaseException as exc:
        report['status'] = 'failed-or-inconclusive'
        report['error'] = f'{type(exc).__name__}: {exc}'
        save(ATTEMPT/'RESULTS.json', report)
        raise
    save(ATTEMPT/'RESULTS.json', report)
    print(json.dumps({'status': 'passed', 'cases': 22, 'selectedInterruptions': 24,
                      'retainedImages': 46, 'runtimeFilesExact': 244}), flush=True)


if __name__ == '__main__':
    main()
