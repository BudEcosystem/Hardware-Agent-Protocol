"""Bounded external control runner; review this source before executing it.

The owned control process launches separate-session provider jobs. On abnormal
owner death this runner reports unresolved observations; its group signal does
not contain those jobs. Never signal a job from persisted PID metadata.
"""
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BASELINE = REPO/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
BASELINE_SHA = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
RESTORE_MASK = None
GROUPS = {'structural': 15, 'live': 30, 'faults': 40}
GROUPS.update(recovery=40, limits=30)
FILES = ['DESIGN.md', 'PLAN.md', 'README.md', 'owner_preconditions.c',
         'helper-check01/libowner-preconditions.so', 'project/control_checks.py',
         'project/owned_hub_jobs/__init__.py', 'project/owned_hub_jobs/contracts.py',
         'project/owned_hub_jobs/ledger.py', 'project/owned_hub_jobs/provider.py',
         'project/owned_hub_jobs/worker.py', 'run_controls.py']
FILES += ['project/recovery_checks.py', 'parent-pins.json', 'baseline/index-parent.json',
          'source-diff.patch', 'change-pins.json']
BASELINE_FILES = ['project/owned_hub_jobs/__init__.py', 'project/owned_hub_jobs/contracts.py',
                 'project/owned_hub_jobs/ledger.py', 'project/owned_hub_jobs/provider.py',
                 'project/owned_hub_jobs/worker.py', 'project/control_checks.py', 'run_controls.py',
                 'owner_preconditions.c', 'helper-check01/libowner-preconditions.so']
FILES += ['baseline/'+name for name in BASELINE_FILES]
PARENT_INDEX_SHA = 'a0b6be34cab423581e8f9a80efd42791e17946cc96ff7e7e5226112e1273b229'
HELPER = '97a1a26fe0b954efc42f52420e552c286047ebbb11c188eed69870c452c850a1'


class RunnerTermination(BaseException):
    pass


def terminate(*_):
    raise RunnerTermination('runner TERM')


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def public_baseline():
    assert digest(BASELINE) == BASELINE_SHA
    receipt = json.loads(BASELINE.read_bytes())
    entries = receipt['files']
    assert len(entries) == 244 and len({item['path'] for item in entries}) == 244
    assert receipt['tests'] == 866 and receipt['passed'] is True
    mismatches = []
    for item in entries:
        path = REPO/item['path']
        assert path.is_relative_to(REPO) and '..' not in Path(item['path']).parts
        try:
            actual = digest(path)
        except OSError as error:
            actual = type(error).__name__
        if actual != item['sha256']:
            mismatches.append(dict(path=item['path'], expected=item['sha256'], actual=actual))
    return dict(receipt=str(BASELINE.relative_to(REPO)), receiptSha256=BASELINE_SHA,
                files=244, priorTests=866, priorTestsRerun=False, passed=not mismatches,
                mismatches=mismatches)


def interpreter():
    path = Path(sys.executable).absolute()
    return dict(path=str(path), resolved=str(path.resolve()), pathSha256=digest(path),
                runningSha256=digest(Path('/proc/self/exe')), version=sys.version)


def parent_baseline():
    parent = HERE.parent/'owned-hub-jobs'
    assert digest(parent/'index.json') == PARENT_INDEX_SHA
    assert digest(HERE/'baseline/index-parent.json') == PARENT_INDEX_SHA
    manifest = json.loads((parent/'index.json').read_bytes())
    mismatches = []
    for item in manifest['files']:
        path = parent/item['path']
        assert path.is_relative_to(parent) and '..' not in Path(item['path']).parts
        if not path.is_file() or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            mismatches.append(item['path'])
    pins = json.loads((HERE/'parent-pins.json').read_bytes())
    assert pins['indexSha256'] == PARENT_INDEX_SHA
    indexed = {entry['path']: entry for entry in manifest['files']}
    assert set(BASELINE_FILES) == {entry['path'] for entry in pins['files']}
    for item in pins['files']:
        assert indexed[item['path']]['sha256'] == item['sha256']
        assert digest(HERE/'baseline'/item['path']) == item['sha256']
    return dict(indexSha256=PARENT_INDEX_SHA, files=len(manifest['files']),
                matching=len(manifest['files'])-len(mismatches), mismatches=mismatches,
                originalCopiesMatched=True, passed=not mismatches)


def save(path, value):
    with path.open('x') as target:
        os.chmod(path, 0o600)
        json.dump(value, target, sort_keys=True, indent=2)
        target.write('\n'); target.flush(); os.fsync(target.fileno())


def processes():
    records = {}; scanned = 0
    with os.scandir('/proc') as entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            scanned += 1
            assert scanned <= 16384
            try:
                with open('/proc/'+entry.name+'/stat', 'rb') as source:
                    body = source.read(4097)
                assert len(body) <= 4096
                fields = body.rsplit(b')', 1)[1].split()
                pid = int(entry.name)
                records[pid] = dict(pid=pid, parent=int(fields[1]), group=int(fields[2]),
                                    session=int(fields[3]), startTicks=int(fields[19]),
                                    state=fields[0].decode('ascii'))
            except (FileNotFoundError, ProcessLookupError):
                pass
    return records


def run(attempt, group, frozen, helper):
    global RESTORE_MASK
    child = None; pidfd = None; previous_mask = None
    observed = {}; reason = None; reaped = False; return_code = None
    remaining = None; started = time.monotonic()
    limits = dict(cpuSeconds=30, addressBytes=512*1024**2, fileBytes=1024**2,
                  openFiles=128, wallSeconds=GROUPS[group])
    entry = 'recovery_checks.py' if group in ('recovery', 'limits') else 'control_checks.py'
    argv = [sys.executable, '-I', '-S', '-B', str(frozen/'project'/entry),
            group, str(attempt/'control-state')]
    save(attempt/'intent.json', dict(group=group, argv=argv, limits=limits,
        interpreterSha256=digest(Path('/proc/self/exe')),
        containment='owned control group only; provider jobs use separate sessions'))
    def preexec():
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        for kind, cap in ((resource.RLIMIT_CPU, limits['cpuSeconds']),
                          (resource.RLIMIT_AS, limits['addressBytes']),
                          (resource.RLIMIT_FSIZE, limits['fileBytes']),
                          (resource.RLIMIT_NOFILE, limits['openFiles']), (resource.RLIMIT_CORE, 0)):
            resource.setrlimit(kind, (cap, cap))
    def anchor():
        assert len(os.listdir('/proc/self/task')) == 1 and helper.hms_owner_signal_snapshot() == 1
        assert child is not None and child.returncode is None
        status = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        assert status is None or status.si_pid == child.pid
        assert os.getpgid(child.pid) == child.pid and os.getsid(child.pid) == child.pid
        return status
    def observe():
        current = processes(); ids = {child.pid}
        for _ in range(16):
            children = {pid for pid, value in current.items() if value['parent'] in ids}
            newer = ids | children
            if newer == ids:
                break
            ids = newer
        assert len(ids) <= 128
        for pid in ids:
            if pid in current:
                value = current[pid]; identity = (pid, value['startTicks'])
                assert identity in observed or len(observed) < 128
                observed[identity] = value
        return current
    def send(action, group_signal=False):
        anchor()
        try:
            if group_signal or pidfd is None:
                os.killpg(child.pid, action)
            else:
                signal.pidfd_send_signal(pidfd, action)
        except ProcessLookupError:
            # An exit race is benign; the original unreaped child still must
            # pass the anchor before any next signal or its final reap.
            pass
    with (attempt/'control.stdout').open('xb') as out, (attempt/'control.stderr').open('xb') as err:
        try:
            assert helper.hms_owner_signal_snapshot() == 1 and len(os.listdir('/proc/self/task')) == 1
            previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
            try:
                child = subprocess.Popen(argv, cwd=frozen, stdin=subprocess.DEVNULL,
                    stdout=out, stderr=err, env={'LANG':'C','LC_ALL':'C'},
                    start_new_session=True, preexec_fn=preexec, close_fds=True)
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            pidfd = os.pidfd_open(child.pid, 0)
            save(attempt/'started.json', dict(pid=child.pid, pgid=child.pid))
            while True:
                observe()
                if anchor() is not None:
                    break
                if time.monotonic()-started >= GROUPS[group]:
                    reason = 'CONTROL_WALL_LIMIT'; break
                time.sleep(.01)
        except BaseException as error:
            reason = type(error).__name__
        finally:
            RESTORE_MASK = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
            if child is not None:
                try:
                    current = observe()
                    status = anchor()
                    if status is None:
                        # The fixed control converts TERM into an exception
                        # whose finally blocks settle its provider handles.
                        send(signal.SIGTERM)
                        grace = time.monotonic()+8
                        while anchor() is None and time.monotonic() < grace:
                            observe(); time.sleep(.01)
                        status = anchor(); current = observe()
                    if status is None or any(v['group'] == child.pid and v['pid'] != child.pid
                                              for v in current.values()):
                        # Original leader remains waitable; no numeric group
                        # signal is issued after its reaping below.
                        if pidfd is not None:
                            send(signal.SIGKILL)
                        send(signal.SIGKILL, group_signal=True)
                    end = time.monotonic()+3
                    while anchor() is None and time.monotonic() < end:
                        time.sleep(.01)
                    if anchor() is None:
                        reason = reason or 'CONTROL_UNREAPED'
                    else:
                        return_code = child.wait(); reaped = True
                    # Audit only: reused PIDs are distinguished by start ticks.
                    current = processes()
                    remaining = [v for identity, v in observed.items()
                                 if identity[0] in current and current[identity[0]]['startTicks'] == identity[1]
                                 and current[identity[0]]['state'] not in ('Z', 'X')]
                except BaseException as error:
                    reason = reason or ('CLEANUP_'+type(error).__name__)
            if pidfd is not None:
                os.close(pidfd)
    output = (attempt/'control.stdout').read_bytes()
    errors = (attempt/'control.stderr').read_bytes()
    parsed = None
    try:
        assert len(output) <= 4096
        parsed = json.loads(output)
        assert parsed['group'] == group and parsed['status'] == 'passed' and type(parsed['checks']) is int
    except (AssertionError, ValueError, KeyError, TypeError):
        reason = reason or 'CONTROL_OUTPUT_INVALID'
    result = dict(passed=reason is None and return_code == 0 and reaped and not remaining and not errors,
        group=group, reason=reason, returnCode=return_code, reaped=reaped,
        observedProcesses=list(observed.values()), remainingObservedLiveProcesses=remaining,
        observationCompleteness='bounded snapshots; not universal descendant enumeration',
        abnormalOwnerCrashQualified=False, control=parsed, elapsedSeconds=time.monotonic()-started)
    save(attempt/'process-result.json', result)
    return result


def main():
    global RESTORE_MASK
    assert len(sys.argv) == 3 and sys.argv[1] in GROUPS
    group, name = sys.argv[1:]
    signal.signal(signal.SIGTERM, terminate)
    assert re.fullmatch(r'[a-z0-9][a-z0-9-]{0,47}', name)
    attempt = HERE/name; attempt.mkdir(mode=0o700)
    before = public_baseline(); save(attempt/'public-before.json', before)
    assert before['passed']
    parent_before = parent_baseline(); save(attempt/'parent-before.json', parent_before)
    assert parent_before['passed']
    runtime_before = interpreter()
    assert runtime_before['pathSha256'] == runtime_before['runningSha256']
    save(attempt/'interpreter-before.json', runtime_before)
    frozen = attempt/'frozen'; frozen.mkdir(mode=0o700)
    pins = {}
    for name in FILES:
        source = HERE/name; target = frozen/name
        assert source.stat().st_size <= 1024**2
        pins[name] = digest(source)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(source, target); target.chmod(0o600)
        assert digest(target) == pins[name]
    save(attempt/'source-pins.json', pins)
    body = (frozen/'helper-check01/libowner-preconditions.so').read_bytes()
    assert hashlib.sha256(body).hexdigest() == HELPER
    fd = os.memfd_create('hms-control-owner-query', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        assert os.write(fd, body) == len(body)
        seals = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
        assert fcntl.fcntl(fd, fcntl.F_GET_SEALS) == seals
        helper = ctypes.CDLL('/proc/self/fd/'+str(fd))
        helper.hms_owner_signal_snapshot.argtypes = []
        helper.hms_owner_signal_snapshot.restype = ctypes.c_int
        result = run(attempt, group, frozen, helper)
    finally:
        os.close(fd)
    try:
        after = public_baseline(); save(attempt/'public-after.json', after)
        parent_after = parent_baseline(); save(attempt/'parent-after.json', parent_after)
        runtime_after = interpreter(); save(attempt/'interpreter-after.json', runtime_after)
        result['sourceStable'] = all(digest(HERE/name) == digest(frozen/name) == sha for name, sha in pins.items())
        result['publicBaselineStable'] = before['passed'] and after['passed']
        result['sealedParentStable'] = parent_before['passed'] and parent_after['passed']
        result['interpreterStable'] = runtime_before == runtime_after
        pending = sorted(int(value) for value in signal.sigpending() & {signal.SIGINT, signal.SIGTERM})
        result['interruptsPendingAfterCleanup'] = pending
        result['passed'] = (result['passed'] and result['sourceStable'] and result['publicBaselineStable']
                            and result['sealedParentStable'] and result['interpreterStable'] and not pending)
        save(attempt/'RESULTS.json', result)
        print(json.dumps(result, sort_keys=True))
    finally:
        if RESTORE_MASK is not None:
            signal.pthread_sigmask(signal.SIG_SETMASK, RESTORE_MASK)
            RESTORE_MASK = None
    assert result['passed']


if __name__ == '__main__':
    main()
