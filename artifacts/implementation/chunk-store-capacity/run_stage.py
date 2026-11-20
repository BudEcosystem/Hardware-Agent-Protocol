"""One frozen candidate, unchanged regressions and bounded full-geometry phases."""
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
OLD = ROOT/'artifacts/implementation/chunked-file-store'
INTERRUPT = ROOT/'artifacts/verification/chunk-store-interruptions'
ATTEMPT = HERE/'attempt01'
CAP = ATTEMPT/'capacity'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'}
BASE = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
BASE_HASH = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'


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
    for base, expected in [(OLD, '10f160e60aa7f866782dda1f28bb8627de5d8e48182397216097cf2d0262fa8e'),
                           (INTERRUPT, 'd2e6c479d06654485ca1577928471c47d7992456b83fa4bfca3bef06fb4aa7a3')]:
        assert sha(base/'index.json') == expected
        assert all(sha(base/r['path']) == r['sha256'] for r in read(base/'index.json')['files'])
    original = (INTERRUPT/'matrix.py').read_text()
    adapted = original.replace("LIBRARY = HERE/'chunk-store.so'", "LIBRARY = Path(os.environ['HMS_CHUNK_LIBRARY'])", 1)
    adapted = adapted.replace("LIBRARY_HASH = '68932ee6147e2072864f521c615685c3db0e79341bbfaf540ba09e5755d40cf7'",
                              "LIBRARY_HASH = os.environ['HMS_CHUNK_LIBRARY_SHA256']", 1)
    assert (HERE/'matrix.py').read_text() == adapted
    fs = os.statvfs(HERE)
    assert fs.f_bavail*fs.f_frsize > 1024**3+64*1024**2
    ATTEMPT.mkdir(mode=0o700)
    frozen = ATTEMPT/'frozen-inputs'
    frozen.mkdir(mode=0o700)
    sources = [(HERE/name, name) for name in ['PLAN.md', 'REVIEW.md', 'chunk_store.py', 'bridge.c',
                                            'matrix.py', 'capacity.py', 'seed.c', 'run_stage.py']]
    sources += [(OLD/'controls.py', 'controls.py'), (OLD/'audit_images.py', 'readonly_image.py'),
                (INTERRUPT/'cases.json', 'cases.json')]
    sources += [(OLD/'attempt02/frozen-inputs'/name, name) for name in ['fixed_block.py', 'lfs.c', 'lfs.h', 'lfs_util.c', 'lfs_util.h', 'LICENSE.md']]
    rows = []
    for source, name in sources:
        dest = frozen/name
        with dest.open('xb') as f:
            f.write(source.read_bytes())
            f.flush()
            os.fsync(f.fileno())
        rows.append({'path': str(source.relative_to(ROOT)), 'frozen': name,
                     'bytes': dest.stat().st_size, 'sha256': sha(dest)})
    compiler = Path('/usr/bin/cc').resolve(strict=True)
    compiler_hash = sha(compiler)
    save(ATTEMPT/'inputs.json', {'files': rows, 'compiler': str(compiler), 'compilerSha256': compiler_hash,
                               'baselineBefore': before, 'retainedInventoryLimitBytes': 1024**3})
    report = {'schema': 'hms.chunk-capacity-attempt/1', 'status': 'incomplete', 'semanticScopes': [], 'interruptionCases': [],
              'capacityPhases': [], 'physicalPowerLossTested': False, 'sqliteTested': False,
              'serviceStorageQualified': False, 'backedControlCapacity': False, 'aggregateServiceQuotaEnforced': False}
    try:
        run('compiler-version', [str(compiler), '--version'], ENV, 30, 20)
        binary_dir = ATTEMPT/'binaries'
        binary_dir.mkdir(mode=0o700)
        library, seed = binary_dir/'chunk-store.so', binary_dir/'seed-tool'
        common = [str(compiler), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                  '-DLFS_NO_MALLOC', '-DLFS_NO_DEBUG', '-DLFS_NO_WARN', '-DLFS_NO_ERROR', '-I', str(frozen)]
        run('build-library', common+['-shared', '-fPIC', str(frozen/'bridge.c'), str(frozen/'lfs.c'), str(frozen/'lfs_util.c'), '-o', str(library)], ENV, 30, 20)
        run('build-seed', common+[str(frozen/'seed.c'), str(frozen/'lfs.c'), str(frozen/'lfs_util.c'), '-o', str(seed)], ENV, 30, 20)
        lib_hash, seed_hash = sha(library), sha(seed)
        report.update(librarySha256=lib_hash, seedToolSha256=seed_hash)
        env = {**ENV, 'HMS_CHUNK_LIBRARY': str(library), 'HMS_CHUNK_LIBRARY_SHA256': lib_hash,
               'HMS_CAPACITY_ROOT': str(CAP)}
        for name, count in [('semantics', 13), ('namespace', 12), ('recovery', 7), ('accounting', 5), ('caps', 11), ('fault', 6)]:
            work = run('semantics/'+name, [sys.executable, '-B', str(frozen/'controls.py'), name], env)
            result = read(work/'checks.json')
            assert result == read(work/'stdout.txt') and result['status'] == 'passed' and len(result['checks']) == count
            report['semanticScopes'].append({'scope': name, 'checks': count, 'resultSha256': sha(work/'checks.json')})
        for case in read(frozen/'cases.json')['cases']:
            work = run('interruptions/'+case['id'], [sys.executable, '-B', str(frozen/'matrix.py'), 'case', case['id']], env)
            result = read(work/'case-result.json')
            assert result == read(work/'stdout.txt') and result['status'] == 'passed' and result['logical'] in case['expected']
            report['interruptionCases'].append({'caseId': case['id'], 'interruptions': len(case['cuts']), 'resultSha256': sha(work/'case-result.json')})
        work = run('capacity/seed-build', [str(seed), 'build'], env)
        prep = read(work/'stdout.txt')
        assert prep['status'] == 'prepared' and prep['failureCode'] == -28 and prep['blockCount'] == 4096
        report['capacityPhases'].append('seed-build')

        def phase(name, mode):
            work = run('capacity/'+name, [sys.executable, '-B', str(frozen/'capacity.py'), mode], env)
            assert read(work/'observation.json') == read(work/'stdout.txt')
            report['capacityPhases'].append(name)
            return read(work/'observation.json')

        final = phase('seed-finalize', 'finalize')
        work = run('capacity/seed-verify', [str(seed), 'inspect', str(CAP/'seed-finalize/seed.bin'),
                                          str(final['baseChunks']), str(final['baseChunks'])], env)
        assert read(work/'stdout.txt')['status'] == 'verified'
        report['capacityPhases'].append('seed-verify')
        phase('install', 'install')
        filled = phase('bulk-fill', 'fill')
        assert filled['allocatorEnospc'] and filled['failedAppend']['code'] == -28
        observed = phase('bulk-observe', 'observe-bulk')
        work = run('capacity/bulk-verify', [str(seed), 'inspect', str(CAP/'bulk/image/chunk-00'),
                                          str(observed['committedChunks']), str(final['baseChunks'])], env)
        assert read(work/'stdout.txt')['status'] == 'verified'
        report['capacityPhases'].append('bulk-verify')
        control = phase('control-after', 'control-after')
        assert control['coldReadExact'] and control['missingBulkErrno'] == 2
        phase('clone-bulk', 'clone-bulk')
        recovery = phase('recover', 'recover')
        recovered = phase('recovery-observe', 'observe-recovery')
        work = run('capacity/recovery-verify', [str(seed), 'inspect', str(CAP/'bulk-recovery/image/chunk-00'),
                                              str(recovered['committedChunks']), str(final['baseChunks'])], env)
        assert read(work/'stdout.txt')['status'] == 'verified'
        report['capacityPhases'].append('recovery-verify')
        assert sha(compiler) == compiler_hash and sha(library) == lib_hash and sha(seed) == seed_hash
        assert all(sha(ROOT/r['path']) == sha(frozen/r['frozen']) == r['sha256'] for r in rows)
        report['baselineAfter'] = baseline()
        files = [p for p in ATTEMPT.rglob('*') if p.is_file()]
        assert all(p.stat().st_size <= 16*1024**2 for p in files)
        assert sum(p.stat().st_blocks*512 for p in files) < 1024**3
        report.update(status='observed', inputsStable=True, actualAllocatorEnospc=True,
                      controlFullAndMissingBulkPassed=True, capacityRecovery=recovery)
    except BaseException as exc:
        report['status'] = 'failed-or-inconclusive'
        report['error'] = f'{type(exc).__name__}: {exc}'
        save(ATTEMPT/'RESULTS.json', report)
        raise
    save(ATTEMPT/'RESULTS.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in {'semanticScopes', 'interruptionCases', 'capacityPhases'}}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
