"""New fixed recovery/limit controls. Source-only until root review.

No owner is killed and no early-leader-exit fixture runs in these groups.
Storage faults are explicit syscall-boundary exceptions, not power failures.
"""
import errno
import json
import os
from pathlib import Path
import signal
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import control_checks as base
from owned_hub_jobs import contracts as c, provider as p

check, refused, request, drive, close, installed = (
    base.check, base.refused, base.request, base.drive, base.close, base.installed)
PHASES = ('before_file_fsync', 'after_file_fsync', 'before_replace', 'after_replace',
          'before_directory_fsync', 'after_directory_fsync', 'before_publish', 'after_publish')


def save(root, value):
    body = json.dumps(value, sort_keys=True, indent=2)+'\n'
    check(len(body.encode()) <= 65536)
    with (root/'observations.json').open('x') as target:
        os.chmod(target.name, 0o600)
        target.write(body)


def recovery(root):
    observations = []
    class TerminalInterrupted(p.HostJobs):
        fired = False
        def _checkpoint(self, phase, row):
            if phase == 'reaped' and not self.fired:
                self.fired = True
                raise c.JobError('TERMINAL_REAP_INTERRUPTED')
    host = installed(root/'terminal-reconcile', cls=TerminalInterrupted)
    try:
        value = request(host, count=1); host.start(value)
        refused(lambda: drive(host, value), 'TERMINAL_REAP_INTERRUPTED')
        before = host.lookup(value['key'])
        check(before['record']['phase'] == 'settled' and before['liveOwner'])
        owned = host._owned[before['record']['id']]
        check(owned.process.returncode == 0)
        after = host.reconcile(value['key'])
        check(after['record'] == before['record'] and not after['liveOwner'])
        check(after['ownerSettlement']['writerLeaseQuiescent'])
        observations.append(dict(case='terminal-reconcile', terminalReceiptUnchanged=True,
                                 retainedHandleReleased=True))
    finally:
        close(host)
    for boundary in PHASES:
        for interrupt in ('none', 'before_reap', 'reaped', 'reaped_sigint'):
            class Compound(p.HostJobs):
                storage_fired = False
                reap_fired = False
                def _checkpoint(self, phase, row):
                    target = 'reaped' if interrupt == 'reaped_sigint' else interrupt
                    if self.storage_fired and not self.reap_fired and phase == target:
                        self.reap_fired = True
                        if interrupt == 'reaped_sigint':
                            os.kill(os.getpid(), signal.SIGINT)
                        else:
                            raise c.JobError('REAP_INTERRUPTED')
                def _signal(self, owned, action):
                    check(owned.settlement is None)
                    return super()._signal(owned, action)
            folder = root/(boundary+'-'+interrupt)
            host = installed(folder, cls=Compound)
            def fail(phase, state):
                if phase == boundary and not host.storage_fired and any(
                        row['phase'] == 'settled' for row in state['rows'].values()):
                    host.storage_fired = True
                    raise OSError(errno.ENOSPC, 'installed terminal commit fault')
            host.ledger._checkpoint = fail
            value = request(host, count=1)
            try:
                host.start(value)
                caught = None
                try:
                    drive(host, value)
                except (OSError, c.JobError, KeyboardInterrupt) as error:
                    caught = type(error).__name__
                    if interrupt == 'none':
                        check(isinstance(error, OSError) and error.errno == errno.ENOSPC)
                    elif interrupt == 'reaped_sigint':
                        check(isinstance(error, KeyboardInterrupt))
                    else:
                        check(isinstance(error, c.JobError) and error.code == 'REAP_INTERRUPTED')
                check(caught is not None and host.storage_fired and host.ledger.poisoned)
                check(interrupt == 'none' or host.reap_fired)
                current = host.lookup(value['key'])
                check(host.start(value)['record'] == current['record'])
                refused(lambda: host.start(request(host, 'new')), 'CONTROL_STORAGE_UNRESOLVED')
                if host._owned:
                    result = host.reconcile(value['key'])
                    check(not result['liveOwner'] and result['controlStoragePoisoned'])
                    check(result['record'] == current['record'])
                check(not host._owned)
                check(host.lookup(value['key'])['ownerSettlement']['processExitCode'] == 0)
            finally:
                close(host)
            reopened = p.HostJobs(folder, owner_contract=p.OWNER_CONTRACT)
            try:
                restored = reopened.lookup(value['key'])
                committed = boundary not in PHASES[:3]
                check(restored['record']['phase'] == ('settled' if committed else 'released'))
                final = reopened.reconcile(value['key'])
                receipt = final['record']['receipt']
                check(receipt['execution'] == ('completed' if committed else 'unknown'))
                check(receipt['recovered'] is (not committed))
                check(receipt['mayHaveActed'] and not final['liveOwner'])
                check(receipt['outputValidated'] is committed)
                check(reopened.start(value)['record'] == final['record'])
                if not committed:
                    check(receipt['result'] is None and receipt['processExitCode'] is None)
                observations.append(dict(boundary=boundary, interruption=interrupt,
                    caught=caught, reopenedExecution=receipt['execution'],
                    recovered=receipt['recovered'], retainedHandlesSettled=True,
                    poisonedFreshLaunchRefused=True))
            finally:
                close(reopened)
    save(root, observations)


def limits(root):
    observations = []
    host = installed(root/'bootstrap', 'bootstrap_failure')
    try:
        value = request(host, count=1); view = host.start(value)
        owned = host._owned[view['record']['id']]
        end = time.monotonic()+3
        while host._waitable(owned) is None and time.monotonic() < end:
            time.sleep(.002)
        check(host._waitable(owned) is not None)
        receipt = drive(host, value)['record']['receipt']
        check(receipt['execution'] == 'not_started' and not receipt['mayHaveActed'])
        check(receipt['processExitCode'] == 74 and receipt['reason'] == 'BOOTSTRAP_EXIT')
        observations.append(dict(case='bootstrap', execution=receipt['execution'], exitCode=74))
    finally:
        close(host)
    host = installed(root/'wall-after-release', 'writer_lingers')
    try:
        value = request(host, count=1); value['limits']['wallMs'] = 150
        host.start(value)
        first = host.poll(value['key'])
        check(first['record']['phase'] == 'released' and first['record']['releaseIntent'])
        receipt = drive(host, value)['record']['receipt']
        check(receipt['execution'] == 'failed' and receipt['reason'] == 'WALL_LIMIT')
        check(receipt['mayHaveActed'] and not receipt['outputValidated'])
        observations.append(dict(case='wall-after-release', reason=receipt['reason'],
                                 mayHaveActed=receipt['mayHaveActed']))
    finally:
        close(host)
    class CpuObserved(p.HostJobs):
        diagnostic = None
        def _checkpoint(self, phase, row):
            if phase == 'writer_settled':
                self.diagnostic = json.loads(bytes(self._owned[row['id']].stderr))
    host = installed(root/'cpu-hard-limit', 'cpu_limit', cls=CpuObserved)
    try:
        value = request(host, count=1)
        value['limits'].update(cpuSeconds=1, wallMs=10000)
        host.start(value); receipt = drive(host, value, seconds=12)['record']['receipt']
        check(receipt['execution'] == 'failed' and receipt['reason'] == 'PROCESS_FAILED')
        check(receipt['processExitCode'] == 76 and receipt['mayHaveActed'])
        check(host.diagnostic['childSignal'] == signal.SIGKILL)
        check(.8 <= host.diagnostic['childCpuSeconds'] <= 2)
        observations.append(dict(case='cpu-hard-limit', diagnostic=host.diagnostic,
                                 childReapedByInstalledLeader=True))
    finally:
        close(host)
    host = installed(root/'retention')
    values = []; terminal = []
    try:
        for number in range(16):
            value = request(host, 'retained-'+str(number), count=1)
            values.append(value); host.start(value)
            terminal.append(drive(host, value)['record'])
            check(terminal[-1]['receipt']['execution'] == 'completed')
        check(len(host.ledger.state['rows']) == 16 and not host._owned)
        refused(lambda: host.start(request(host, 'seventeenth', count=1)), 'RETENTION_FULL')
        for value, record in zip(values, terminal):
            check(host.start(value)['record'] == record)
        check(len(host.ledger.state['rows']) == 16 and not host._owned)
        observations.append(dict(case='retention', retained=16, seventeenthRefused=True,
                                 historicalReplays=16))
    finally:
        close(host)
    save(root, observations)


def main():
    assert len(sys.argv) == 3 and sys.argv[1] in ('recovery', 'limits')
    group = sys.argv[1]; root = Path(sys.argv[2]).absolute()
    signal.signal(signal.SIGTERM, base.terminate)
    root.mkdir(mode=0o700)
    started = time.monotonic()
    {'recovery': recovery, 'limits': limits}[group](root)
    print(json.dumps(dict(group=group, checks=base.CHECKS, status='passed',
                          elapsedSeconds=round(time.monotonic()-started, 6)), sort_keys=True))


if __name__ == '__main__':
    main()
