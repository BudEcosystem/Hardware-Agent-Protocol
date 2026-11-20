"""Bounded outer guardian for the fixed writer-deferral subprocess."""
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
ORIGINALS = json.loads((HERE/'parent-pins.json').read_bytes())
FILES = list(dict.fromkeys(['writer_deferral_checks.py', 'PLAN.md', 'DESIGN.md', 'README.md',
    'parent-pins.json', 'change-pins.json', 'source-diff.patch',
    'baseline/recovery-index.json', 'baseline/guardian-index.json'] +
    [entry['target'] for entry in ORIGINALS['files']] +
    ['baseline/'+entry['target'] for entry in ORIGINALS['files']]))
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


def sealed_sources():
    indices = {}
    for parent in ORIGINALS['parents']:
        source = ROOT/parent['path']
        assert digest(source/'index.json') == digest(HERE/'baseline'/(parent['kind']+'-index.json')) == parent['indexSha256']
        index = json.loads((source/'index.json').read_bytes())
        expected = {entry['path'] for entry in index['files']}
        assert {str(path.relative_to(source)) for path in source.rglob('*') if path.is_file()} == expected|{'index.json'}
        for entry in index['files']:
            path = source/entry['path']
            assert path.stat().st_size == entry['bytes'] and digest(path) == entry['sha256']
        indices[parent['kind']] = {entry['path']:entry for entry in index['files']}
    assert len(ORIGINALS['files']) == 10
    for entry in ORIGINALS['files']:
        assert indices[entry['parent']][entry['source']]['sha256'] == entry['sha256']
        assert digest(HERE/'baseline'/entry['target']) == entry['sha256']
        if entry['target'] in ('guardian.py','helper-attempt01/libharness-owner.so'):
            assert digest(HERE/entry['target']) == entry['sha256']
    changes = json.loads((HERE/'change-pins.json').read_bytes())
    assert digest(HERE/'source-diff.patch') == changes['sourceDiffSha256']
    assert all(digest(HERE/entry['path']) == entry['candidateSha256'] for entry in changes['files'])


def main():
    def terminate(signum, _):
        raise RuntimeError('outer guardian interrupted '+str(signum))
    signal.signal(signal.SIGTERM, terminate)
    os.umask(0o077); attempt = HERE/'writer-deferral-attempt01'; attempt.mkdir(mode=0o700)
    frozen = attempt/'frozen'; frozen.mkdir(mode=0o700)
    baseline(); sealed_sources(); pins = {}
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
                    str(frozen/'writer_deferral_checks.py'), str(attempt/'state'),
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
                baseline(); sealed_sources()
                stable = all(digest(HERE/name) == digest(frozen/name) == pin for name, pin in pins.items())
                assert digest(executable) == digest(Path('/proc/self/exe')) == runtime
                output = None
                try:
                    output = json.loads((attempt/'stdout.txt').read_bytes())
                except (ValueError, UnicodeError):
                    reason = reason or 'INVALID_CONTROL_OUTPUT'
                pending = sorted(int(value) for value in signal.sigpending() & {signal.SIGINT, signal.SIGTERM})
                expected = (type(output) is dict and output == dict(passed=True, cases=3,
                    ownersKilled=3,normalLeaderExits=3,heldLeaseDeferrals=3,childrenReaped=9,subreaperRestored=True)
                    and output['passed'] is True and output['subreaperRestored'] is True
                    and all(type(output[key]) is int for key in ('cases','ownersKilled','normalLeaderExits','heldLeaseDeferrals','childrenReaped')))
                passed = (reason is None and exit_record is not None and exit_record['exitCode'] == 0
                    and not leftovers and stable and not pending and expected and not (attempt/'stderr.txt').read_bytes())
                result = dict(passed=passed, reason=reason, sourceStable=stable, publicInputsExact=244,
                    interruptsPendingAfterCleanup=pending,
                    priorTestsRerun=False, control=output, controlExit=exit_record,
                    adoptedAfterControlExit=leftovers, outerChildrenReaped=guardian.records,
                    elapsedSeconds=time.monotonic()-started, providerJobsExecuted=True, actualOwnerDeaths=3 if passed else None,
                    deterministicHeldWriterDeferrals=3 if passed else None, sealedParentsStable=True,
                    guardianAliveRequired=True, universalContainment=False)
                save(attempt/'RESULTS.json', result)
                print(json.dumps(result, sort_keys=True))
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous)
    assert result['passed']


if __name__ == '__main__':
    main()
