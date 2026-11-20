"""Single original bounded adapter attempt. Preserve all failures; no retry loop."""
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
REPO = ROOT/'research/host-contract/littlefs-core/repo'
ATTEMPT = HERE/'attempt01'
BASE = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
BASE_HASH = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
SCOPES = ['semantics', 'namespace', 'recovery', 'accounting', 'caps', 'fault']
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'}


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def baseline():
    assert digest(BASE) == BASE_HASH
    rows = json.loads(BASE.read_text())['files']
    assert len(rows) == 244 and all(digest(ROOT/r['path']) == r['sha256'] for r in rows)
    return {'filesExact': 244, 'receiptSha256': BASE_HASH}


def limits(cpu):
    for key, amount in [(resource.RLIMIT_CPU, cpu), (resource.RLIMIT_AS, 512*1024**2),
                        (resource.RLIMIT_FSIZE, 16*1024**2), (resource.RLIMIT_NOFILE, 128),
                        (resource.RLIMIT_CORE, 0)]:
        resource.setrlimit(key, (amount, amount))


def run(name, argv, env, wall=60, cpu=40):
    work = ATTEMPT/name
    work.mkdir(mode=0o700)
    save(work/'intent.json', {'argv': argv, 'environment': env, 'cwd': str(work),
                             'wallSeconds': wall, 'cpuSeconds': cpu})
    started = time.monotonic()
    timed_out = False
    with (work/'stdout.txt').open('xb') as out, (work/'stderr.txt').open('xb') as err:
        proc = subprocess.Popen(argv, cwd=work, env=env, stdout=out, stderr=err,
                                start_new_session=True, preexec_fn=lambda: limits(cpu))
        save(work/'started.json', {'pid': proc.pid, 'processGroup': proc.pid, 'unix': time.time()})
        try:
            code = proc.wait(timeout=wall)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait(timeout=5)
        finally:
            # Also settle any descendant after an early scope error.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        out.flush()
        err.flush()
        os.fsync(out.fileno())
        os.fsync(err.fileno())
    result = {'returnCode': code, 'timedOut': timed_out, 'reaped': True,
              'elapsedSeconds': time.monotonic()-started}
    save(work/'result.json', result)
    if code != 0 or timed_out:
        raise RuntimeError(f'{name} failed or inconclusive; matrix stopped')
    return work


def main():
    os.umask(0o077)
    before = baseline()
    assert not ATTEMPT.exists()
    for relative, wanted in [
        ('artifacts/verification/littlefs-semantics', 'cba58c11e5c32471982a8875607beca5704ac165d4da446760049aefcc4eb231'),
        ('research/host-contract/littlefs-core', 'c149f635c72262102a1d5c2ff3f2fc08c56fc6dc1fc9a1306037114d1650fd0e')]:
        directory = ROOT/relative
        assert digest(directory/'index.json') == wanted
        assert all(digest(directory/r['path']) == r['sha256'] for r in json.loads((directory/'index.json').read_text())['files'])
    ATTEMPT.mkdir(mode=0o700)
    frozen = ATTEMPT/'frozen-inputs'
    frozen.mkdir(mode=0o700)
    sources = [HERE/name for name in ['PLAN.md', 'REVIEW.md', 'bridge.c', 'chunk_store.py', 'controls.py', 'run_scopes.py']]
    sources += [ROOT/'artifacts/implementation/fixed-block-storage/fixed_block.py']
    sources += [REPO/name for name in ['lfs.c', 'lfs.h', 'lfs_util.c', 'lfs_util.h', 'LICENSE.md']]
    rows = []
    for source in sources:
        target = frozen/source.name
        with target.open('xb') as f:
            f.write(source.read_bytes())
            f.flush()
            os.fsync(f.fileno())
        rows.append({'path': str(source.relative_to(ROOT)), 'frozen': source.name,
                     'bytes': target.stat().st_size, 'sha256': digest(target)})
    compiler = Path('/usr/bin/cc').resolve(strict=True)
    compiler_hash = digest(compiler)
    save(ATTEMPT/'inputs.json', {'files': rows, 'compiler': str(compiler),
                               'compilerSha256': compiler_hash, 'baselineBefore': before})
    report = {'schema': 'hms.chunk-store-attempt/1', 'status': 'incomplete', 'scopes': {},
              'filesystemMounted': False, 'sqliteTested': False, 'physicalPowerLossTested': False,
              'serviceStorageQualified': False, 'backedControlCapacity': False,
              'aggregateServiceQuotaEnforced': False}
    try:
        run('compiler-version', [str(compiler), '--version'], ENV, 30, 20)
        library = ATTEMPT/'chunk-store.so'
        run('build', [str(compiler), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                      '-shared', '-fPIC', '-DLFS_NO_MALLOC', '-DLFS_NO_DEBUG', '-DLFS_NO_WARN', '-DLFS_NO_ERROR',
                      '-I', str(frozen), str(frozen/'bridge.c'), str(frozen/'lfs.c'),
                      str(frozen/'lfs_util.c'), '-o', str(library)], ENV, 30, 20)
        library_hash = digest(library)
        report['librarySha256'] = library_hash
        env = {**ENV, 'HMS_CHUNK_LIBRARY': str(library), 'HMS_CHUNK_LIBRARY_SHA256': library_hash}
        for name in SCOPES:
            work = run(name, [sys.executable, '-B', str(frozen/'controls.py'), name], env)
            if (work/'stderr.txt').stat().st_size or (work/'stdout.txt').stat().st_size > 65536:
                raise ValueError('unexpected scope output')
            summary = json.loads((work/'checks.json').read_text())
            if json.loads((work/'stdout.txt').read_text()) != summary or summary['scope'] != name or summary['status'] != 'passed':
                raise ValueError('scope association mismatch')
            if not summary['checks'] or len(summary['checks']) != len(set(summary['checks'])):
                raise ValueError('invalid check identities')
            report['scopes'][name] = {'checks': len(summary['checks']), 'resultSha256': digest(work/'checks.json')}
            print(json.dumps({'scope': name, 'checks': len(summary['checks']), 'status': 'passed'}), flush=True)
        assert digest(compiler) == compiler_hash and digest(library) == library_hash
        assert all(digest(ROOT/r['path']) == digest(frozen/r['frozen']) == r['sha256'] for r in rows)
        report['baselineAfter'] = baseline()
        files = [p for p in ATTEMPT.rglob('*') if p.is_file()]
        assert all(p.stat().st_size <= 16*1024**2 for p in files)
        assert sum(p.stat().st_blocks*512 for p in files) < 256*1024**2
        report['status'] = 'passed'
        report['inputsStable'] = True
    except BaseException as exc:
        report['status'] = 'failed-or-inconclusive'
        report['error'] = f'{type(exc).__name__}: {exc}'
        save(ATTEMPT/'RESULTS.json', report)
        raise
    save(ATTEMPT/'RESULTS.json', report)
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
