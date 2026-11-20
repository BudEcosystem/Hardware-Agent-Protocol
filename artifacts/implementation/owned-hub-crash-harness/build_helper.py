"""Build original local bindings and run finite attribute-only controls."""
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import threading
import time

HERE = Path(__file__).resolve().parent
OUT = HERE/'helper-attempt01'
PRIOR = HERE.parent/'owned-hub-jobs/helper-check01/libowner-preconditions.so'
PRIOR_SHA = '97a1a26fe0b954efc42f52420e552c286047ebbb11c188eed69870c452c850a1'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def save(path, value):
    with path.open('x') as target:
        json.dump(value, target, indent=2, sort_keys=True); target.write('\n')
        target.flush(); os.fsync(target.fileno())


def members(pgid):
    found = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            parts = (path/'stat').read_bytes().rsplit(b')', 1)[1].split()
            if int(parts[2]) == pgid:
                found.append(dict(pid=int(path.name), state=parts[0].decode('ascii')))
        except FileNotFoundError:
            pass
    return found


def run(argv, name, helper):
    child = None; started = time.monotonic(); reason = None; usage = None; remaining = None
    blocked = {signal.SIGINT, signal.SIGTERM}; previous = None
    def preexec():
        for kind, cap in [(resource.RLIMIT_CPU, 10), (resource.RLIMIT_AS, 512*1024**2),
                          (resource.RLIMIT_FSIZE, 4*1024**2), (resource.RLIMIT_NOFILE, 64),
                          (resource.RLIMIT_CORE, 0)]:
            resource.setrlimit(kind, (cap, cap))
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)
    def anchor():
        assert len(os.listdir('/proc/self/task')) == 1 and helper.hms_owner_signal_snapshot() == 1
        assert child is not None and child.returncode is None
        status = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        assert os.getpgid(child.pid) == child.pid
        return status
    with (OUT/(name+'.stdout')).open('xb') as out, (OUT/(name+'.stderr')).open('xb') as err:
        try:
            assert helper.hms_owner_signal_snapshot() == 1 and len(os.listdir('/proc/self/task')) == 1
            previous = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
            try:
                child = subprocess.Popen([str(x) for x in argv], cwd=OUT, stdin=subprocess.DEVNULL,
                    stdout=out, stderr=err, start_new_session=True, preexec_fn=preexec,
                    env={'PATH':'/usr/bin:/bin', 'LANG':'C', 'LC_ALL':'C'})
                save(OUT/(name+'.started.json'), dict(pid=child.pid, pgid=child.pid, argv=list(map(str, argv))))
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous)
            while anchor() is None:
                if time.monotonic()-started >= 25:
                    reason = 'WALL_LIMIT'; break
                time.sleep(.02)
        except BaseException as error:
            reason = type(error).__name__
        finally:
            restore = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
            try:
                if child is not None:
                    if anchor() is None or any(p['pid'] != child.pid for p in members(child.pid)):
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    pid, status, usage = os.wait4(child.pid, 0)
                    assert pid == child.pid
                    child.returncode = os.waitstatus_to_exitcode(status)
                    remaining = members(pid)  # No signal after reap.
                out.flush(); err.flush(); os.fsync(out.fileno()); os.fsync(err.fileno())
                result = dict(returnCode=None if child is None else child.returncode,
                    reaped=usage is not None, reason=reason, remainingGroupMembers=remaining,
                    elapsedSeconds=time.monotonic()-started,
                    cpuSeconds=None if usage is None else usage.ru_utime+usage.ru_stime,
                    peakRSSKiB=None if usage is None else usage.ru_maxrss)
                save(OUT/(name+'.result.json'), result)
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, restore)
    assert child is not None and child.returncode == 0 and usage is not None and reason is None and not remaining
    assert not (OUT/(name+'.stderr')).read_bytes()


def main():
    def terminated(signum, _):
        raise RuntimeError('helper runner interrupted '+str(signum))
    signal.signal(signal.SIGTERM, terminated)
    os.umask(0o077); OUT.mkdir(mode=0o700)
    names = ['subreaper.c', 'subreaper_control.c', 'owner_preconditions.c', 'build_helper.py']
    pins = {name: digest(HERE/name) for name in names}
    for name in names:
        shutil.copyfile(HERE/name, OUT/name); assert digest(OUT/name) == pins[name]
    gcc = Path(shutil.which('gcc')).resolve(); compiler = digest(gcc)
    save(OUT/'intent.json', dict(sources=pins, compiler=str(gcc), compilerSha256=compiler,
        limits=dict(cpuSeconds=10, wallSeconds=25, addressBytes=512*1024**2, fileBytes=4*1024**2, openFiles=64)))
    body = PRIOR.read_bytes(); assert hashlib.sha256(body).hexdigest() == PRIOR_SHA
    fd = os.memfd_create('prior-owner-query', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    assert os.write(fd, body) == len(body)
    fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE)
    helper = ctypes.CDLL('/proc/self/fd/'+str(fd))
    helper.hms_owner_signal_snapshot.argtypes = []; helper.hms_owner_signal_snapshot.restype = ctypes.c_int
    result = dict(passed=False, providerJobsExecuted=False, adoptionTested=False)
    try:
        flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Wconversion', '-Werror', '-fno-common']
        run([gcc, *flags, '-fPIC', '-shared', 'subreaper.c', 'owner_preconditions.c', '-o', 'libharness-owner.so'], 'compile-library', helper)
        run([gcc, *flags, 'subreaper_control.c', '-L.', '-lharness-owner', '-Wl,-rpath,$ORIGIN', '-o', 'control'], 'compile-control', helper)
        run([OUT/'control'], 'control', helper)
        result['control'] = json.loads((OUT/'control.stdout').read_text())
        assert result['control'] == dict(checks=9, attributeRestored=True, childrenCreated=0)
        result['librarySha256'] = digest(OUT/'libharness-owner.so'); result['passed'] = True
    finally:
        os.close(fd)
        result['sourcesStable'] = all(digest(HERE/name) == digest(OUT/name) == value for name, value in pins.items())
        result['compilerStable'] = digest(gcc) == compiler
        result['passed'] &= result['sourcesStable'] and result['compilerStable']
        save(OUT/'RESULTS.json', result)
    assert result['passed']; print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
