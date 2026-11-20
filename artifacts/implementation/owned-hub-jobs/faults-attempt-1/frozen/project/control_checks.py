"""Original finite controls. Source-only until parent review authorizes execution.

Run with an external owned runner: python -I -S -B control_checks.py GROUP ROOT.
ROOT must be a new private artifact directory. No test executes a caller path.
Fault tests simulate owner-handoff boundaries; they are not process-crash tests.
"""
import copy
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from owned_hub_jobs import contracts as c, ledger as l, provider as p

CHECKS = 0
TERMINATING = False


class ControlTermination(BaseException):
    pass


def terminate(*_):
    global TERMINATING
    if not TERMINATING:
        TERMINATING = True
        raise ControlTermination('runner requested orderly cleanup')


def check(value):
    global CHECKS
    CHECKS += 1
    if not value:
        raise AssertionError('control failed')


def refused(fn, code=None):
    try:
        fn()
    except c.JobError as error:
        check(code is None or error.code == code)
        return
    raise AssertionError('expected refusal')


def request(host, operation='one', count=1000):
    return dict(profile=c.PROFILE, key=dict(deployment='control', caller='owner', operation=operation),
                artifact=host.artifact, input=dict(first=-7, step=3, count=count),
                limits=dict(c.DEFAULT_LIMITS))


def drive(host, value, seconds=8):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        view = host.poll(value['key'])
        if view['record']['phase'] == 'settled':
            return view
        time.sleep(.002)
    raise AssertionError('finite poll deadline exceeded')


def close(host):
    # Cleanup uses only the retained provider handles, never a stored numeric PID.
    for name in list(host._owned):
        row = host.ledger.get(name)
        try:
            host.cancel(row['request']['key'])
        except (c.JobError, OSError):
            pass
        end = time.monotonic()+6
        while name in host._owned and time.monotonic() < end:
            try:
                host.poll(row['request']['key'])
            except (c.JobError, OSError):
                pass
            time.sleep(.002)
    check(not host._owned)
    host.close()


def installed(root, mode='normal', cls=p.HostJobs):
    class Fixture(cls):
        def _installed_test_mode(self):
            return mode
    return Fixture(root, owner_contract=p.OWNER_CONTRACT, create=True)


def structural(root):
    host = installed(root/'identity')
    try:
        value = request(host, count=1)
        frozen = c.request(value)
        check(frozen == value and frozen is not value)
        for field, wrong in (('count', True), ('count', 1.0), ('step', False)):
            bad = copy.deepcopy(value); bad['input'][field] = wrong
            refused(lambda: c.request(bad))
        bad = copy.deepcopy(value); bad['command'] = 'anything'
        refused(lambda: c.request(bad))
        row = dict(id=c.identifier(value['key']), request=value, digest=c.request_digest(value),
                   nonce='a'*32, phase='admitted', history=['admitted'], lease=None,
                   ownerSession='b'*32, pid=None, releaseIntent=False,
                   cancelRequested=False, reason=None, receipt=None)
        out = dict(profile=c.OUTPUT_PROFILE, requestDigest=row['digest'], nonce=row['nonce'],
                   artifact=value['artifact'], result=c.expected_result(value['input']))
        check(c.validate_output(c.canonical(out), row) == out)
        sealed = p.sealed(b'original', 'hms-control-seals')
        try:
            check(fcntl.fcntl(sealed, fcntl.F_GET_SEALS) == p.SEALS)
            for mutate in (lambda: os.write(sealed, b'x'), lambda: os.ftruncate(sealed, 0)):
                try:
                    mutate()
                except OSError as error:
                    check(error.errno == errno.EPERM)
                else:
                    raise AssertionError('sealed bytes changed')
        finally:
            os.close(sealed)
        for field, wrong in (('count', True), ('count', 1.0),
                             ('sumSquaresMod64', 49), ('sumSquaresMod64', '049')):
            bad = copy.deepcopy(out); bad['result'][field] = wrong
            refused(lambda: c.validate_output(c.canonical(bad), row))
        before = {row['id']: row}
        refused(lambda: l.successor(before, {}), 'STATE_REMOVED_KEY')
        changed = copy.deepcopy(before); changed[row['id']]['nonce'] = 'c'*32
        refused(lambda: l.successor(before, changed), 'ORIGINAL_KEY_IMMUTABLE')
        host.ledger.save(row)
        check(host.ledger.get(row['id']) == row)
        changed = copy.deepcopy(row); changed['ownerSession'] = 'c'*32
        refused(lambda: host.ledger.save(changed), 'ORIGINAL_KEY_IMMUTABLE')
        terminal = copy.deepcopy(row); terminal['reason'] = 'OWNER_LOST'
        terminal['receipt'] = host._receipt(terminal, 'not_started', None, False, None,
                                            recovered=True, observed=[])
        terminal = host.ledger.save(terminal, 'settled')
        for wrong in (False, 0.0):
            changed = copy.deepcopy(terminal)
            changed['receipt']['observedLiveGroupMembers'] = wrong
            refused(lambda: l.validate_row(changed), 'RECEIPT_GROUP')
        changed = copy.deepcopy(terminal); changed['receipt']['reason'] = None
        refused(lambda: l.validate_row(changed), 'RECEIPT_REASON')
        changed = copy.deepcopy(terminal); changed['reason'] = 'DIFFERENT'
        changed['receipt']['reason'] = 'DIFFERENT'
        refused(lambda: host.ledger.save(changed), 'TERMINAL_IMMUTABLE')
    finally:
        close(host)
    # Two individually valid slots must also form one permitted successor.
    folder = root/'rollback'
    state = l.Ledger(folder, create=True); state.save(row); state.close()
    latest = folder/'state.1'
    # Create generation2 with a rewritten immutable nonce after gen1.
    envelope = c.parse(latest.read_bytes()); envelope['state']['generation'] = 2
    envelope['state']['rows'][row['id']]['nonce'] = 'c'*32
    envelope['sha256'] = hashlib.sha256(c.canonical(envelope['state'])).hexdigest()
    (folder/'state.0').write_bytes(c.canonical(envelope))
    refused(lambda: l.Ledger(folder), 'ORIGINAL_KEY_IMMUTABLE')


def live(root):
    host = installed(root/'success')
    try:
        value = request(host)
        first = host.start(value)
        check(first['record']['phase'] == 'associated' and not first['record']['releaseIntent'])
        check(host.start(value)['record'] == first['record'])
        bad = copy.deepcopy(value); bad['input']['count'] += 1
        refused(lambda: host.start(bad), 'KEY_CONFLICT')
        refused(lambda: host.start(request(host, 'other')), 'JOB_BUSY')
        final = drive(host, value)
        receipt = final['record']['receipt']
        check(receipt['execution'] == 'completed' and receipt['outputValidated'])
        check(receipt['result'] == c.expected_result(value['input']))
        check(not final['liveOwner'] and final['ownerSettlement']['streamEof'])
        check(host.start(value)['record'] == final['record'])
        # Historical replay does not call fresh checks. New-key launch does.
        original = p.bounded_image
        def drift(path):
            body = original(path)
            return body+b'\n' if path.name == 'provider.py' else body
        p.bounded_image = drift
        try:
            check(host.start(value)['record'] == final['record'])
            refused(lambda: host.start(request(host, 'new')), 'IMPLEMENTATION_CHANGED')
        finally:
            p.bounded_image = original
        previous = host.owner_thread; host.owner_thread = -1
        refused(lambda: host.lookup(value['key']), 'OWNER_SESSION')
        host.owner_thread = previous
    finally:
        close(host)
    host = installed(root/'cancel-gated')
    try:
        value = request(host, count=50_000_000); host.start(value)
        accepted = host.cancel(value['key'])
        check(accepted['record']['cancelRequested'] and accepted['record']['receipt'] is None)
        check(not accepted['record']['releaseIntent'])
        receipt = drive(host, value)['record']['receipt']
        check(receipt['execution'] == 'canceled' and receipt['cancellation'] == 'confirmed')
        check(not receipt['mayHaveActed'])
    finally:
        close(host)
    host = installed(root/'cancel-released')
    try:
        value = request(host, count=50_000_000); host.start(value); host.poll(value['key'])
        check(host.lookup(value['key'])['record']['releaseIntent'])
        host.cancel(value['key']); receipt = drive(host, value)['record']['receipt']
        check(receipt['execution'] == 'canceled' and receipt['mayHaveActed'])
    finally:
        close(host)
    class DelayedGate(p.HostJobs):
        def _checkpoint(self, phase, row):
            if phase == 'release_intent':
                time.sleep(.12)
    host = installed(root/'expired-gate', cls=DelayedGate)
    original_write = os.write
    gate_writes = []
    try:
        value = request(host); value['limits']['wallMs'] = 100
        view = host.start(value)
        gate = host._owned[view['record']['id']].gate
        def observe_write(fd, body):
            result = original_write(fd, body)
            if fd == gate and body == b'G':
                gate_writes.append(result)
            return result
        os.write = observe_write
        receipt = drive(host, value)['record']['receipt']
        check(receipt['reason'] == 'WALL_LIMIT' and not receipt['outputValidated'])
        check(receipt['mayHaveActed'] and gate_writes == [])
    finally:
        os.write = original_write
        close(host)
    for mode in ('wrong_result', 'wrong_nonce', 'malformed', 'bool_count', 'float_count',
                 'numeric_sum', 'leading_zero_sum', 'output_limit'):
        host = installed(root/mode, mode)
        try:
            value = request(host, count=1); host.start(value)
            receipt = drive(host, value)['record']['receipt']
            check(receipt['execution'] == 'failed' and not receipt['outputValidated'])
            check(receipt['reason'] == ('STREAM_LIMIT' if mode == 'output_limit' else 'OUTPUT_INVALID'))
        finally:
            close(host)
    host = installed(root/'writer-lingers', 'writer_lingers')
    try:
        value = request(host); host.start(value)
        end = time.monotonic()+3; saw_output_without_settlement = False
        while time.monotonic() < end:
            view = host.poll(value['key'])
            owned = host._owned.get(view['record']['id'])
            if owned is not None and owned.stdout:
                saw_output_without_settlement = True
                check(view['record']['receipt'] is None)
            if view['record']['phase'] == 'settled':
                break
            time.sleep(.002)
        check(saw_output_without_settlement and view['record']['receipt']['execution'] == 'completed')
    finally:
        close(host)


def faults(root):
    for boundary in ('admitted', 'launching', 'ownership_registered', 'spawned', 'associated', 'before_release',
                     'release_intent', 'gate_released', 'writer_settled', 'reaped'):
        class Interrupted(p.HostJobs):
            fired = False
            def _checkpoint(self, phase, row):
                if phase == boundary and not self.fired:
                    self.fired = True
                    raise c.JobError('INJECTED_BOUNDARY')
        host = installed(root/boundary, cls=Interrupted)
        value = request(host)
        try:
            try:
                host.start(value)
                drive(host, value)
            except c.JobError as error:
                check(error.code == 'INJECTED_BOUNDARY')
            check(host.fired)
            # Retain and settle the real original handles; only then simulate
            # reopening the persisted interrupted history. Never abandon a job.
            if host._owned:
                drive(host, value)
            recorded = host.lookup(value['key'])['record']
        finally:
            close(host)
        reopened = p.HostJobs(root/boundary, owner_contract=p.OWNER_CONTRACT)
        try:
            view = reopened.reconcile(value['key'])
            check(view['record']['phase'] == 'settled')
            check(reopened.start(value)['record'] == view['record'])
            check(not view['liveOwner'])
            if recorded['phase'] != 'settled':
                check(view['record']['receipt']['recovered'])
        finally:
            close(reopened)
    host = installed(root/'pidfd-failure')
    original = os.pidfd_open
    try:
        value = request(host)
        def fail(*args):
            raise OSError('installed pidfd failure')
        os.pidfd_open = fail
        try:
            host.start(value)
        except OSError:
            check(True)
        finally:
            os.pidfd_open = original
        view = drive(host, value)
        check(view['record']['receipt']['execution'] == 'not_started')
        check(not view['record']['releaseIntent'])
    finally:
        os.pidfd_open = original
        close(host)
    host = installed(root/'sigchld-refusal')
    previous = signal.getsignal(signal.SIGCHLD)
    try:
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)
        refused(lambda: host.start(request(host)), 'SIGCHLD_PRECONDITION')
        check(host.ledger.state['rows'] == {})
    finally:
        signal.signal(signal.SIGCHLD, previous)
        close(host)
    class InterruptRegistered(p.HostJobs):
        def _checkpoint(self, phase, row):
            if phase == 'ownership_registered':
                check(row['id'] in self._owned)
                os.kill(os.getpid(), signal.SIGINT)
                # Still blocked: delivery happens only when start restores mask.
                check(row['id'] in self._owned)
    host = installed(root/'registered-interrupt', cls=InterruptRegistered)
    try:
        value = request(host)
        try:
            host.start(value)
        except KeyboardInterrupt:
            check(True)
        else:
            raise AssertionError('pending interrupt was not delivered')
        check(len(host._owned) == 1)
        view = drive(host, value)
        check(view['record']['receipt']['execution'] == 'not_started')
        check(not view['record']['releaseIntent'])
    finally:
        close(host)
    class InterruptReaped(p.HostJobs):
        fired = False
        def _checkpoint(self, phase, row):
            if phase == 'reaped' and not self.fired:
                self.fired = True
                check(self._owned[row['id']].process.returncode is not None)
                os.kill(os.getpid(), signal.SIGINT)
                check(row['id'] in self._owned)
    host = installed(root/'reaped-interrupt', cls=InterruptReaped)
    try:
        value = request(host); host.start(value)
        try:
            drive(host, value)
        except KeyboardInterrupt:
            check(True)
        else:
            raise AssertionError('pending post-reap interrupt was not delivered')
        check(host.fired and not host._owned)
        check(host.poll(value['key'])['record']['receipt']['execution'] == 'completed')
    finally:
        close(host)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ('structural', 'live', 'faults'):
        raise SystemExit('expected fixed GROUP and new ROOT')
    group = sys.argv[1]; root = Path(sys.argv[2]).absolute()
    signal.signal(signal.SIGTERM, terminate)
    root.mkdir(mode=0o700)
    started = time.monotonic()
    {'structural': structural, 'live': live, 'faults': faults}[group](root)
    print(json.dumps(dict(group=group, checks=CHECKS, status='passed',
                          elapsedSeconds=round(time.monotonic()-started, 6)), sort_keys=True))


if __name__ == '__main__':
    main()
