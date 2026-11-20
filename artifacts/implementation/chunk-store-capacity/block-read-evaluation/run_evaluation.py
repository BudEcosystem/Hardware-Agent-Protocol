"""Separate changed-cache evaluation, preserving the original failed attempt."""
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
STAGE = HERE.parent
ROOT = STAGE.parents[2]
ORIGINAL = STAGE/'attempt01'
CAP = HERE/'capacity'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'}


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


def limits(cpu):
    for key, amount in [(resource.RLIMIT_CPU, cpu), (resource.RLIMIT_AS, 512*1024**2),
                        (resource.RLIMIT_FSIZE, 16*1024**2), (resource.RLIMIT_NOFILE, 128), (resource.RLIMIT_CORE, 0)]:
        resource.setrlimit(key, (amount, amount))


def run(name, argv, env, wall=60, cpu=40):
    work = HERE/name
    work.mkdir(mode=0o700, parents=True)
    save(work/'process-intent.json', {'argv': argv, 'cwd': str(work), 'environment': env,
                                     'wallSeconds': wall, 'cpuSeconds': cpu})
    started = time.monotonic()
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
    result = {'returnCode': code, 'timedOut': timed_out, 'reaped': True, 'elapsedSeconds': time.monotonic()-started}
    save(work/'process-result.json', result)
    if code != 0 or timed_out:
        raise RuntimeError(f'{name}: failed or inconclusive; evaluation stopped')
    assert (work/'stderr.txt').stat().st_size == 0
    print(json.dumps({'phase': name, 'status': 'completed', 'seconds': round(result['elapsedSeconds'], 3)}), flush=True)
    return work


def main():
    os.umask(0o077)
    preserved = read(STAGE/'attempt01-preservation.json')['files']
    assert all(sha(ORIGINAL/r['path']) == r['sha256'] for r in preserved)
    assert read(ORIGINAL/'RESULTS.json')['status'] == 'failed-or-inconclusive'
    assert not (HERE/'RESULTS.json').exists()
    allocated = sum(p.stat().st_blocks*512 for p in STAGE.rglob('*') if p.is_file())
    assert allocated+72*1024**2 < 1024**3
    expected = (STAGE/'bridge.c').read_text().replace('CACHE=256, INTERNAL_MAX', 'CACHE=4096, INTERNAL_MAX', 1)
    expected = expected.replace('.read_size=16,.prog_size=16', '.read_size=4096,.prog_size=16', 1)
    assert (HERE/'bridge.c').read_text() == expected
    frozen = HERE/'frozen-inputs'
    frozen.mkdir(mode=0o700)
    sources = [(HERE/name, name) for name in ['PLAN.md', 'bridge.c', 'run_evaluation.py']]
    sources += [(ORIGINAL/'frozen-inputs'/name, name) for name in ['chunk_store.py', 'capacity.py', 'fixed_block.py',
                'readonly_image.py', 'lfs.c', 'lfs.h', 'lfs_util.c', 'lfs_util.h', 'LICENSE.md']]
    sources += [(ORIGINAL/'binaries/seed-tool', 'seed-tool')]
    rows = []
    for source, name in sources:
        dest = frozen/name
        with dest.open('xb') as f:
            f.write(source.read_bytes())
            f.flush()
            os.fsync(f.fileno())
        if name == 'seed-tool':
            dest.chmod(0o700)
        rows.append({'path': str(source.relative_to(ROOT)), 'frozen': name, 'bytes': dest.stat().st_size, 'sha256': sha(dest)})
    compiler = Path('/usr/bin/cc').resolve(strict=True)
    compiler_hash = sha(compiler)
    save(HERE/'inputs.json', {'files': rows, 'compiler': str(compiler), 'compilerSha256': compiler_hash,
                             'originalPreservationSha256': sha(STAGE/'attempt01-preservation.json'),
                             'retainedStageLimitBytes': 1024**3})
    report = {'schema': 'hms.block-read-capacity-evaluation/1', 'status': 'incomplete', 'phases': [],
              'readSize': 4096, 'cacheSize': 4096, 'programSize': 16, 'geometryBlocks': 4096,
              'completeRegressionMatrixRun': False, 'adopted': False, 'physicalPowerLossTested': False,
              'sqliteTested': False, 'serviceStorageQualified': False, 'backedControlCapacity': False}
    try:
        binaries = HERE/'binaries'
        binaries.mkdir(mode=0o700)
        library = binaries/'block-read.so'
        run('build', [str(compiler), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                      '-DLFS_NO_MALLOC', '-DLFS_NO_DEBUG', '-DLFS_NO_WARN', '-DLFS_NO_ERROR', '-I', str(frozen),
                      str(frozen/'bridge.c'), str(frozen/'lfs.c'), str(frozen/'lfs_util.c'), '-o', str(library)], ENV, 30, 20)
        library_hash = sha(library)
        report['librarySha256'] = library_hash
        env = {**ENV, 'HMS_CHUNK_LIBRARY': str(library), 'HMS_CHUNK_LIBRARY_SHA256': library_hash,
               'HMS_CAPACITY_ROOT': str(CAP)}
        (CAP/'seed-finalize').mkdir(mode=0o700, parents=True)
        (CAP/'seed-verify').mkdir(mode=0o700)
        source_seed = ORIGINAL/'capacity/seed-finalize/seed.bin'
        target_seed = CAP/'seed-finalize/seed.bin'
        with source_seed.open('rb') as source, target_seed.open('xb') as target:
            os.posix_fallocate(target.fileno(), 0, 16*1024**2)
            while data := source.read(1024**2):
                target.write(data)
            target.flush()
            os.fsync(target.fileno())
        assert sha(source_seed) == sha(target_seed)
        for old, new in [('seed-finalize/observation.json', 'seed-finalize/observation.json'), ('seed-verify/stdout.txt', 'seed-verify/stdout.txt')]:
            with (CAP/new).open('xb') as f:
                f.write((ORIGINAL/'capacity'/old).read_bytes())
                f.flush()
                os.fsync(f.fileno())
        save(HERE/'seed-lineage.json', {'source': str(source_seed.relative_to(ROOT)), 'sha256': sha(source_seed),
                                      'bytes': 16*1024**2, 'priorReadProofReusedByExactBytes': True,
                                      'priorProofSha256': sha(ORIGINAL/'capacity/seed-verify/stdout.txt')})

        def phase(name, mode):
            work = run('capacity/'+name, [sys.executable, '-B', str(frozen/'capacity.py'), mode], env)
            observation = read(work/'observation.json')
            assert observation == read(work/'stdout.txt')
            report['phases'].append(name)
            return observation

        phase('install', 'install')
        filled = phase('bulk-fill', 'fill')
        assert filled['allocatorEnospc'] and filled['failedAppend']['code'] == -28
        observed = phase('bulk-observe', 'observe-bulk')
        base_count = read(CAP/'seed-finalize/observation.json')['baseChunks']
        work = run('capacity/bulk-verify', [str(frozen/'seed-tool'), 'inspect', str(CAP/'bulk/image/chunk-00'),
                                          str(observed['committedChunks']), str(base_count)], env)
        assert read(work/'stdout.txt')['status'] == 'verified'
        report['phases'].append('bulk-verify')
        control = phase('control-after', 'control-after')
        assert control['coldReadExact'] and control['missingBulkErrno'] == 2
        phase('clone-bulk', 'clone-bulk')
        recovery = phase('recover', 'recover')
        restored = phase('recovery-observe', 'observe-recovery')
        work = run('capacity/recovery-verify', [str(frozen/'seed-tool'), 'inspect', str(CAP/'bulk-recovery/image/chunk-00'),
                                              str(restored['committedChunks']), str(base_count)], env)
        assert read(work/'stdout.txt')['status'] == 'verified'
        report['phases'].append('recovery-verify')
        assert sha(compiler) == compiler_hash and sha(library) == library_hash
        assert all(sha(ROOT/r['path']) == sha(frozen/r['frozen']) == r['sha256'] for r in rows)
        assert all(sha(ORIGINAL/r['path']) == r['sha256'] for r in preserved)
        files = [p for p in STAGE.rglob('*') if p.is_file()]
        assert all(p.stat().st_size <= 16*1024**2 for p in files)
        assert sum(p.stat().st_blocks*512 for p in files) < 1024**3
        baseline = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
        assert sha(baseline) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
        assert all(sha(ROOT/r['path']) == r['sha256'] for r in read(baseline)['files'])
        report.update(status='observed', inputsStable=True, originalAttemptUnchanged=True,
                      actualAllocatorEnospc=True, controlFullAndMissingBulkPassed=True, capacityRecovery=recovery,
                      runtimeFilesExact=244)
    except BaseException as exc:
        report['status'] = 'failed-or-inconclusive'
        report['error'] = f'{type(exc).__name__}: {exc}'
        save(HERE/'RESULTS.json', report)
        raise
    save(HERE/'RESULTS.json', report)
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
