"""Bounded outer owner for the original provider-owner-death subprocess."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guardian import Guardian

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FILES = ['guardian.py', 'owner_crash_checks.py', 'run_owner_crashes.py', 'CRASH-PLAN.md', 'provider-pins.json',
         'helper-attempt01/libharness-owner.so'] + [r['target'] for r in json.loads((HERE/'provider-pins.json').read_bytes())['files']]
BASELINE = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
BASELINE_SHA = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def save(path, value):
    with path.open('x') as target:
        json.dump(value, target, indent=2, sort_keys=True); target.write('\n')
        target.flush(); os.fsync(target.fileno())


def baseline():
    assert digest(BASELINE) == BASELINE_SHA
    rows = json.loads(BASELINE.read_bytes())['files']
    assert len(rows) == 244 and all(digest(ROOT/r['path']) == r['sha256'] for r in rows)


def provider_sources():
    rows = json.loads((HERE/'provider-pins.json').read_bytes())['files']
    assert len(rows) == 7
    assert all(digest(ROOT/r['source']) == digest(HERE/r['target']) == r['sha256'] for r in rows)


def main():
    def terminate(signum, _):
        raise RuntimeError('outer guardian interrupted '+str(signum))
    signal.signal(signal.SIGTERM, terminate)
    os.umask(0o077); attempt = HERE/'owner-crash-attempt01'; attempt.mkdir(mode=0o700)
    frozen = attempt/'frozen'; frozen.mkdir(mode=0o700)
    baseline(); provider_sources(); pins = {}
    for name in FILES:
        source = HERE/name; target = frozen/name
        assert source.stat().st_size <= 1024**2
        pins[name] = digest(source); target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(source, target); assert digest(target) == pins[name]
    executable = Path(sys.executable).resolve(); runtime = digest(executable)
    assert digest(Path('/proc/self/exe')) == runtime
    save(attempt/'intent.json', dict(sourcePins=pins, executable=str(executable), executableSha256=runtime,
        baselineSha256=BASELINE_SHA, controlWallSeconds=30, cleanupTermGraceSeconds=10,
        guardianSettlementSeconds=8, controlCpuSeconds=30, controlAddressBytes=512*1024**2,
        controlFileBytes=1024**2, controlOpenFiles=64,
        authority='Dedicated live subreaper; kernel child relation and pidfd; no stored-PID signals'))
    guardian = Guardian(frozen/'helper-attempt01/libharness-owner.so')
    reason = None; child = None; exit_record = None; leftovers = []; started = time.monotonic()
    runtime_fd = os.open(executable, os.O_RDONLY | os.O_CLOEXEC)
    with (attempt/'stdout.txt').open('xb') as out, (attempt/'stderr.txt').open('xb') as err:
        try:
            def fixed_control():
                os.dup2(out.fileno(), 1); os.dup2(err.fileno(), 2)
                devnull = os.open('/dev/null', os.O_RDONLY); os.dup2(devnull, 0); os.close(devnull)
                os.chdir(frozen)
                os.execve('/proc/self/fd/'+str(runtime_fd), [str(executable), '-I', '-S', '-B',
                    str(frozen/'owner_crash_checks.py'), str(attempt/'state'),
                    str(frozen/'helper-attempt01/libharness-owner.so')], {'LANG':'C', 'LC_ALL':'C'})
            child = guardian.fork(fixed_control, cpu_seconds=30, address_bytes=512*1024**2)
            save(attempt/'started.json', guardian.stat(child))
            while guardian.status(child) is None:
                if time.monotonic()-started >= 30:
                    reason = 'CONTROL_WALL_LIMIT'; break
                time.sleep(.01)
        except BaseException as error:
            reason = type(error).__name__+': '+str(error)
        finally:
            previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
            try:
                if child is not None and child in guardian.handles:
                    if guardian.status(child) is None:
                        guardian.send(child, signal.SIGTERM)
                        deadline = time.monotonic()+10
                        while guardian.status(child) is None and time.monotonic() < deadline:
                            time.sleep(.01)
                    if guardian.status(child) is not None:
                        exit_record = guardian.reap(child)
                guardian.refresh(); leftovers = list(guardian.handles)
                guardian.settle(); guardian.close()
                out.flush(); err.flush(); os.fsync(out.fileno()); os.fsync(err.fileno())
                os.close(runtime_fd)
                baseline(); provider_sources()
                stable = all(digest(HERE/name) == digest(frozen/name) == pin for name, pin in pins.items())
                assert digest(executable) == digest(Path('/proc/self/exe')) == runtime
                output = None
                try:
                    output = json.loads((attempt/'stdout.txt').read_bytes())
                except (ValueError, UnicodeError):
                    reason = reason or 'INVALID_CONTROL_OUTPUT'
                pending = sorted(int(value) for value in signal.sigpending() & {signal.SIGINT, signal.SIGTERM})
                expected = (type(output) is dict and set(output) == {'passed', 'cases', 'ownersKilled', 'childrenReaped', 'subreaperRestored'}
                    and output['passed'] is True and output['cases'] == output['ownersKilled'] == 12
                    and type(output['childrenReaped']) is int and 20 <= output['childrenReaped'] <= 21
                    and output['subreaperRestored'] is True)
                passed = (reason is None and exit_record is not None and exit_record['exitCode'] == 0
                    and not leftovers and stable and not pending and expected and not (attempt/'stderr.txt').read_bytes())
                result = dict(passed=passed, reason=reason, sourceStable=stable, publicInputsExact=244,
                    interruptsPendingAfterCleanup=pending,
                    priorTestsRerun=False, control=output, controlExit=exit_record,
                    adoptedAfterControlExit=leftovers, outerChildrenReaped=guardian.records,
                    elapsedSeconds=time.monotonic()-started, providerJobsExecuted=True, actualOwnerDeaths=12 if passed else None, recoverySourcesStable=True,
                    guardianAliveRequired=True, universalContainment=False)
                save(attempt/'RESULTS.json', result)
                print(json.dumps(result, sort_keys=True))
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous)
    assert result['passed']


if __name__ == '__main__':
    main()
