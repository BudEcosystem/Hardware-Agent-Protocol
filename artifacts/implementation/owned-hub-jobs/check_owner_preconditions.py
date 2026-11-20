"""Build/test only the original read-only signal-state binding, in owned children."""
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
OUT = HERE / 'helper-check01'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def limits():
    for kind, value in [(resource.RLIMIT_CPU, 10), (resource.RLIMIT_AS, 512 * 1024**2),
                        (resource.RLIMIT_FSIZE, 4 * 1024**2), (resource.RLIMIT_NOFILE, 64),
                        (resource.RLIMIT_CORE, 0)]:
        resource.setrlimit(kind, (value, value))


def members(pgid):
    result = []
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            try:
                fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
                if int(fields[2]) == pgid:
                    result.append(int(path.name))
            except FileNotFoundError:
                pass
    return result


def run(argv, name):
    start = time.monotonic()
    reason = None
    with (OUT / (name + '.stdout')).open('xb') as out, (OUT / (name + '.stderr')).open('xb') as err:
        child = subprocess.Popen([str(arg) for arg in argv], cwd=OUT, stdin=subprocess.DEVNULL,
                                 stdout=out, stderr=err, start_new_session=True, preexec_fn=limits,
                                 env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
        save(OUT / (name + '.started.json'), dict(pid=child.pid, pgid=child.pid, argv=list(map(str, argv))))
        try:
            while os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
                if time.monotonic() - start >= 25:
                    reason = 'wall_limit'
                    break
                time.sleep(.02)
        except BaseException as error:
            reason = type(error).__name__
            raise
        finally:
            observed = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if observed is None or any(pid != child.pid for pid in members(child.pid)):
                os.killpg(child.pid, signal.SIGKILL)
            pid, status, usage = os.wait4(child.pid, 0)
            assert pid == child.pid
            child.returncode = os.waitstatus_to_exitcode(status)
            remaining = members(child.pid)  # Audit only after leader is reaped.
            receipt = dict(pid=pid, pgid=pid, returnCode=child.returncode, reaped=True,
                           remainingGroupMembers=remaining, reason=reason,
                           elapsedSeconds=time.monotonic() - start,
                           cpuSeconds=usage.ru_utime + usage.ru_stime, peakRSSKiB=usage.ru_maxrss)
            save(OUT / (name + '.result.json'), receipt)
    assert child.returncode == 0 and reason is None and not remaining
    assert not (OUT / (name + '.stderr')).read_bytes()


def main():
    OUT.mkdir(mode=0o700, exist_ok=False)
    names = ['owner_preconditions.c', 'owner_preconditions_control.c', Path(__file__).name]
    pins = {name: digest(HERE / name) for name in names}
    for name in names:
        shutil.copyfile(HERE / name, OUT / name)
        assert digest(OUT / name) == pins[name]
    gcc = Path(shutil.which('gcc')).resolve()
    compiler_sha = digest(gcc)
    save(OUT / 'intent.json', dict(sources=pins, compiler=str(gcc), compilerSha256=compiler_sha,
         limits=dict(cpuSeconds=10, wallSeconds=25, addressBytes=512*1024**2,
                     fileBytes=4*1024**2, openFiles=64, coreBytes=0)))
    result = dict(passed=False, candidateJobsExecuted=False)
    try:
        common = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Wconversion', '-Werror', '-fno-common']
        run([gcc, *common, '-fPIC', '-shared', 'owner_preconditions.c', '-o', 'libowner-preconditions.so'], 'compile-library')
        run([gcc, *common, 'owner_preconditions_control.c', '-L.', '-lowner-preconditions',
             '-Wl,-rpath,$ORIGIN', '-o', 'control'], 'compile-control')
        run([OUT / 'control'], 'control')
        result['control'] = json.loads((OUT / 'control.stdout').read_text())
        assert result['control'] == dict(cases=6, checks=12, signalStateRestored=True, childrenCreated=0)
        result['librarySha256'] = digest(OUT / 'libowner-preconditions.so')
        result['controlSha256'] = digest(OUT / 'control')
        result['passed'] = True
    finally:
        result['sourcesStable'] = all(digest(HERE / name) == digest(OUT / name) == sha for name, sha in pins.items())
        result['compilerStable'] = digest(gcc) == compiler_sha
        result['passed'] = result['passed'] and result['sourcesStable'] and result['compilerStable']
        save(OUT / 'RESULTS.json', result)
    assert result['passed']
    print(json.dumps(result))


if __name__ == '__main__':
    main()
