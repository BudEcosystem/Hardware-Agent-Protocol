"""Fixed owner-death controls for the original, pinned CPU-job provider."""
import json
import os
from pathlib import Path
import signal
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE/'provider-inputs/project'))
from guardian import Guardian, read_record, write_record
from owned_hub_jobs import contracts as c, provider as p

PHASES = ('admitted', 'launching', 'ownership_registered', 'spawned', 'associated',
          'before_release', 'release_intent', 'gate_released', 'writer_settled',
          'before_reap', 'reaped', 'terminal_committed')
TERMINAL = ('before_reap', 'reaped', 'terminal_committed')
RELEASED = ('release_intent', 'gate_released', 'writer_settled') + TERMINAL


def save(path, value):
    with path.open('x') as target:
        json.dump(value, target, indent=2, sort_keys=True); target.write('\n')
        target.flush(); os.fsync(target.fileno())


def owner(folder, phase, notice, hold):
    os.setsid()
    class FixedCheckpoint(p.HostJobs):
        def _checkpoint(self, actual, row):
            if actual != phase:
                return
            owned = self._owned.get(row['id']); job = None; reaped = None
            if owned is not None:
                reaped = owned.process.returncode is not None
                if not reaped:
                    # An unreaped owned child supplies identity evidence here;
                    # the receiving guardian does not gain authority from it.
                    os.waitid(os.P_PID, owned.process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    job = Guardian.stat(owned.process.pid)
                    assert job['parent'] == os.getpid()
            write_record(notice, dict(checkpoint=actual, record=row, jobObservation=job,
                                      ownedChildAlreadyReaped=reaped))
            # Only the parent guardian retains a writer. Its loss closes the
            # gate and terminates this fixed owner; no normal continuation.
            assert os.read(hold, 1) == b''
            os._exit(87)
    host = FixedCheckpoint(folder, owner_contract=p.OWNER_CONTRACT, create=True)
    value = dict(profile=c.PROFILE,
        key=dict(deployment='owner-crash', caller='fixed-control', operation=phase),
        artifact=host.artifact, input=dict(first=-7, step=3, count=1000),
        limits=dict(c.DEFAULT_LIMITS))
    host.start(value)
    end = time.monotonic()+6
    while time.monotonic() < end:
        host.poll(value['key']); time.sleep(.002)
    raise AssertionError('Fixed checkpoint not reached')


def one(guardian, root, phase):
    assert guardian.empty()
    folder = root/phase; folder.mkdir(mode=0o700)
    notice_read, notice_write = os.pipe2(os.O_CLOEXEC)
    hold_read, hold_write = os.pipe2(os.O_CLOEXEC)
    opened = {notice_read, notice_write, hold_read, hold_write}
    started = len(guardian.records)
    try:
        def fixed_owner():
            os.close(notice_read); os.close(hold_write)
            owner(folder/'ledger', phase, notice_write, hold_read)
        child = guardian.fork(fixed_owner)
        os.close(notice_write); opened.remove(notice_write)
        os.close(hold_read); opened.remove(hold_read)
        checkpoint = read_record(notice_read)
        assert checkpoint['checkpoint'] == phase
        save(folder/'checkpoint.json', checkpoint)
        row = checkpoint['record']; value = row['request']
        assert row['releaseIntent'] is (phase in RELEASED)
        assert (row['phase'] == 'settled') is (phase in TERMINAL)
        # The owner is our direct kernel child and has a retained pidfd.
        guardian.send(child, signal.SIGKILL)
        owner_exit = guardian.wait_exit(child)
        assert owner_exit['exitCode'] == -signal.SIGKILL
        os.close(hold_write); opened.remove(hold_write)
        adopted = guardian.refresh()
        observed = checkpoint['jobObservation']
        if observed is not None:
            # Adoption authority was acquired independently by refresh().
            assert observed['pid'] in adopted
            assert guardian.handles[observed['pid']]['identity']['startTicks'] == observed['startTicks']
        elif phase in ('admitted', 'launching', 'reaped', 'terminal_committed'):
            assert not adopted
        reopened = p.HostJobs(folder/'ledger', owner_contract=p.OWNER_CONTRACT)
        try:
            before = reopened.lookup(value['key'])
            assert before['record'] == row and not before['liveOwner']
            assert reopened.start(value)['record'] == row and not reopened._owned
            initial = reopened.reconcile(value['key'])
            # A live lease can defer reconciliation. Its absence never proves
            # that released work did or did not complete.
            lease_deferred = initial['record']['phase'] != 'settled'
            if lease_deferred:
                assert initial['record'] == row
            guardian.settle()
            assert guardian.empty()
            final = reopened.reconcile(value['key']); receipt = final['record']['receipt']
            expected = 'completed' if phase in TERMINAL else 'unknown' if phase in RELEASED else 'not_started'
            assert final['record']['phase'] == 'settled' and receipt['execution'] == expected
            assert receipt['recovered'] is (phase not in TERMINAL)
            assert receipt['mayHaveActed'] is (phase in RELEASED)
            assert receipt['writerLeaseQuiescent'] and not final['liveOwner']
            if phase in TERMINAL:
                assert final['record'] == row and receipt['outputValidated']
                independent = sum((-7+3*i)**2 for i in range(1000)) % (1 << 64)
                assert receipt['result'] == dict(count=1000, sumSquaresMod64=str(independent))
                assert receipt['processExitCode'] == 0
            else:
                assert receipt['result'] is None and receipt['processExitCode'] is None
                assert not receipt['outputValidated']
            assert reopened.start(value)['record'] == final['record'] and not reopened._owned
            assert len(reopened.ledger.state['rows']) == 1 and guardian.empty()
            save(folder/'recovery.json', dict(before=before, initial=initial, final=final,
                leaseDeferredBeforeGuardianSettlement=lease_deferred,
                ownerKilled=True, ownedChildrenReaped=guardian.records[started:],
                historicalReplaySpawned=False, expectedExecution=expected))
            return dict(checkpoint=phase, execution=expected, leaseDeferred=lease_deferred,
                        childrenReaped=len(guardian.records)-started)
        finally:
            reopened.close()
    finally:
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            for fd in opened:
                os.close(fd)
            guardian.settle()
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def main():
    def terminate(signum, _):
        raise RuntimeError('owner-death control interrupted '+str(signum))
    signal.signal(signal.SIGTERM, terminate)
    assert len(sys.argv) == 3
    root = Path(sys.argv[1]); root.mkdir(mode=0o700)
    guardian = Guardian(sys.argv[2]); cases = []
    try:
        for phase in PHASES:
            cases.append(one(guardian, root, phase))
    finally:
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            guardian.settle(); guardian.close()
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
    save(root/'checks.json', dict(cases=cases, reaped=guardian.records,
        actualOwnerDeath=True, guardianAliveRequired=True, universalContainment=False,
        deviceOrGpuAccess=False, publicMount=False))
    print(json.dumps(dict(passed=True, cases=len(cases), ownersKilled=len(cases),
                          childrenReaped=len(guardian.records), subreaperRestored=True), sort_keys=True))


if __name__ == '__main__':
    main()
