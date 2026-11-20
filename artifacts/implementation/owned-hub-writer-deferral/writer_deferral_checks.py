"""Deterministic fixed live-writer controls. No timing-only hold or PID authority."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE/'provider-inputs/project'))
from guardian import Guardian, read_record, write_record
from owned_hub_jobs import contracts as c, provider as p

CASES = ('release', 'eof', 'guardian_stop')


def save(path, value):
    with path.open('x') as target:
        json.dump(value, target, indent=2, sort_keys=True); target.write('\n')
        target.flush(); os.fsync(target.fileno())


def state_bytes(folder):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(folder.glob('state.[01]'))}


def lease_probe(folder, row, *, held):
    # A distinct open-file description, never the inherited writer's handle.
    fd = os.open(folder/('lease-'+row['id']), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
        assert info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == 0
        identity = dict(device=info.st_dev, inode=info.st_ino)
        assert identity == row['lease']
        blocked = False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            blocked = True
        assert blocked is held
        return dict(**identity, independentlyOpened=True, held=blocked)
    finally:
        os.close(fd)


def owner(folder, case, writer_hold, writer_notice, notice, hold):
    os.setsid()
    class InstalledBarrier(p.HostJobs):
        def _installed_test_mode(self):
            return 'writer_barrier'
        def _installed_fixture_fds(self):
            return (writer_hold, writer_notice)
    host = InstalledBarrier(folder, owner_contract=p.OWNER_CONTRACT, create=True)
    value = dict(profile=c.PROFILE,
        key=dict(deployment='writer-deferral', caller='fixed-guardian', operation=case),
        artifact=host.artifact, input=dict(first=-7, step=3, count=1000), limits=dict(c.DEFAULT_LIMITS))
    first = host.start(value)
    assert first['record']['phase'] == 'associated' and not first['record']['releaseIntent']
    current = host.poll(value['key'])
    assert current['record']['phase'] == 'released' and current['record']['receipt'] is None
    owned = host._owned[current['record']['id']]
    end = time.monotonic()+5
    status = host._waitable(owned)
    while status is None:
        assert time.monotonic() < end, 'Leader did not reach observed normal exit'
        time.sleep(.002)
        status = host._waitable(owned)
    assert status.si_code == os.CLD_EXITED and status.si_status == 0
    assert owned.process.returncode is None  # Never poll()/wait() away the retained leader.
    leader = Guardian.stat(owned.process.pid)
    assert leader['parent'] == os.getpid() and leader['state'] == 'Z'
    write_record(notice, dict(ownerPid=os.getpid(), record=current['record'], manifest=host.manifest,
                              leader=leader, leaderNormalExitObserved=True, leaderRetainedUnreaped=True))
    # The guardian is the only writer; there is no normal owner continuation.
    assert os.read(hold, 1) == b''
    os._exit(87)


def one(guardian, root, case):
    assert guardian.empty()
    folder = root/case; folder.mkdir(mode=0o700)
    writer_read, writer_write = os.pipe2(os.O_CLOEXEC)
    ready_read, ready_write = os.pipe2(os.O_CLOEXEC)
    notice_read, notice_write = os.pipe2(os.O_CLOEXEC)
    owner_read, owner_write = os.pipe2(os.O_CLOEXEC)
    opened = {writer_read, writer_write, ready_read, ready_write,
              notice_read, notice_write, owner_read, owner_write}
    def close_fd(fd):
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT,signal.SIGTERM})
        try:
            opened.remove(fd)
            os.close(fd)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
    installed = []
    for fd, role, access in ((writer_write, 'writerHoldReader', os.O_RDONLY),
                             (ready_read, 'readyNoticeWriter', os.O_WRONLY)):
        info = os.fstat(fd)
        installed.append(dict(role=role, device=info.st_dev, inode=info.st_ino, access=access))
    records_begin = len(guardian.records)
    reopened = None
    try:
        def fixed_owner():
            # Closing these before HostJobs forks is the writer-ownership proof:
            # neither the owner nor any job descendant inherits a hold writer.
            for fd in (writer_write, ready_read, notice_read, owner_write):
                os.close(fd)
            assert guardian.helper.hms_subreaper_get() == 0
            owner(folder/'ledger', case, writer_read, ready_write, notice_write, owner_read)
        owner_pid = guardian.fork(fixed_owner)
        for fd in (writer_read, ready_write, notice_write, owner_read):
            close_fd(fd)
        checkpoint = read_record(notice_read)
        ready = read_record(ready_read)
        save(folder/'checkpoint.json', checkpoint); save(folder/'writer-ready.json', ready)
        row = checkpoint['record']; value = row['request']
        assert checkpoint['ownerPid'] == owner_pid and checkpoint['leaderNormalExitObserved'] is True
        assert checkpoint['leaderRetainedUnreaped'] is True
        assert checkpoint['manifest']['installedTestMode'] == 'writer_barrier'
        assert checkpoint['manifest']['installedFixture'] == dict(profile='hms.writer-barrier-installation/1', roles=installed)
        assert value['artifact'] == c.digest(b'HMS-INSTALLED-HOST-ARTIFACT-v1\0'+c.canonical(checkpoint['manifest']))
        assert row['phase'] == 'released' and row['releaseIntent'] is True and row['receipt'] is None
        assert set(ready) == {'profile','stage','requestDigest','nonce','artifact','child','originalLeader','lease','result'}
        assert ready['profile'] == 'hms.writer-barrier-ready/1' and ready['stage'] == 'computed-before-writer-hold'
        assert (ready['requestDigest'],ready['nonce'],ready['artifact']) == (row['digest'],row['nonce'],value['artifact'])
        assert ready['lease'] == row['lease']
        assert set(ready['child']) == {'pid','startTicks','group','session'}
        assert all(type(value) is int and value > 0 for value in ready['child'].values())
        assert type(ready['originalLeader']) is int
        expected = sum((-7+3*i)**2 for i in range(1000)) % (1<<64)
        assert type(ready['result']['count']) is int and ready['result'] == dict(count=1000,sumSquaresMod64=str(expected))
        # Choose authority from kernel children first. The notice is only an
        # identity/association cross-check after refresh acquires real handles.
        actual_children = guardian.refresh()
        candidates = [pid for pid in actual_children if pid != owner_pid]
        assert len(candidates) == 1
        writer_pid, = candidates
        writer_identity = guardian.handles[writer_pid]['identity']
        assert writer_pid == ready['child']['pid']
        assert writer_identity['startTicks'] == ready['child']['startTicks']
        assert writer_identity['parent'] == guardian.pid
        leader_observation = checkpoint['leader']
        assert ready['originalLeader'] == leader_observation['pid'] == row['pid']
        assert writer_identity['group'] == ready['child']['group'] == row['pid']
        assert writer_identity['session'] == ready['child']['session'] == row['pid']
        assert guardian.status(writer_pid) is None and guardian.status(owner_pid) is None
        held_before = lease_probe(folder/'ledger', row, held=True)
        guardian.send(owner_pid, signal.SIGKILL)
        owner_exit = guardian.wait_exit(owner_pid)
        assert owner_exit['exitCode'] == -signal.SIGKILL
        close_fd(owner_write)
        adopted = guardian.refresh()
        remaining = [pid for pid in adopted if pid != writer_pid]
        assert len(remaining) == 1
        leader_pid, = remaining
        assert leader_pid == leader_observation['pid']
        assert guardian.handles[leader_pid]['identity']['startTicks'] == leader_observation['startTicks']
        leader_exit = guardian.wait_exit(leader_pid)
        assert leader_exit['exitCode'] == 0
        assert guardian.status(writer_pid) is None
        held_after = lease_probe(folder/'ledger', row, held=True)
        # Owner death released the ledger owner lock. The writer still holds
        # only the effect/writer lease, so recovery can inspect but must defer.
        reopened = p.HostJobs(folder/'ledger', owner_contract=p.OWNER_CONTRACT)
        before = reopened.lookup(value['key']); stable_slots = state_bytes(folder/'ledger')
        assert before['record'] == row and not before['liveOwner']
        assert reopened.start(value)['record'] == row and not reopened._owned
        deferred = reopened.reconcile(value['key'])
        assert deferred['record'] == row and deferred['record']['receipt'] is None
        assert state_bytes(folder/'ledger') == stable_slots
        held_deferred = lease_probe(folder/'ledger', row, held=True)
        occupied = json.loads(c.canonical(value))
        occupied['key']['operation'] += '-new'; occupied['artifact'] = reopened.artifact
        try:
            reopened.start(occupied)
        except c.JobError as error:
            assert error.code == 'JOB_BUSY'
        else:
            raise AssertionError('Held writer did not retain admission')
        assert guardian.refresh() == [writer_pid] and len(reopened.ledger.state['rows']) == 1
        if case == 'release':
            assert os.write(writer_write, b'R') == 1
            close_fd(writer_write)
        elif case == 'eof':
            close_fd(writer_write)
        else:
            guardian.send(writer_pid, signal.SIGKILL)
        writer_exit = guardian.wait_exit(writer_pid)
        assert writer_exit['exitCode'] == {'release':0,'eof':79,'guardian_stop':-signal.SIGKILL}[case]
        if writer_write in opened:
            close_fd(writer_write)
        assert guardian.empty()
        free_after = lease_probe(folder/'ledger', row, held=False)
        final = reopened.reconcile(value['key']); receipt = final['record']['receipt']
        assert final['record']['phase'] == 'settled' and receipt['execution'] == 'unknown'
        assert receipt['recovered'] is True and receipt['mayHaveActed'] is True
        assert receipt['result'] is None and receipt['processExitCode'] is None and receipt['outputValidated'] is False
        assert receipt['writerLeaseQuiescent'] is True and not final['liveOwner']
        assert reopened.start(value)['record'] == final['record'] and not reopened._owned
        assert len(reopened.ledger.state['rows']) == 1 and guardian.empty()
        family = guardian.records[records_begin:]
        assert len(family) == 3 and {item['pid'] for item in family} == {owner_pid,leader_pid,writer_pid}
        assert all(item['reaped'] is True for item in family)
        save(folder/'recovery.json', dict(before=before,deferred=deferred,final=final,
            heldBeforeOwnerDeath=held_before,heldAfterOwnerDeath=held_after,
            heldAfterDeferredReconcile=held_deferred,freeAfterWriterReaped=free_after,
            kernelSelectedWriter=writer_identity,normalLeaderExit=leader_exit,
            childrenReaped=family,sourceKnownComputation=ready['result'],
            historicalReplaySpawned=False,heldReconcileChangedSlots=False))
        return dict(case=case,leaderExit=0,writerExit=writer_exit['exitCode'],childrenReaped=3,
                    heldLeaseObserved=True,reconcileDeferred=True,finalExecution='unknown',replayedWithoutLaunch=True)
    finally:
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT,signal.SIGTERM})
        try:
            try:
                for fd in list(opened):
                    close_fd(fd)
            finally:
                try:
                    guardian.settle()
                finally:
                    if reopened is not None:
                        reopened.close()
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def main():
    def terminate(signum, _):
        raise RuntimeError('writer deferral control interrupted '+str(signum))
    signal.signal(signal.SIGTERM, terminate)
    assert len(sys.argv) == 3
    root = Path(sys.argv[1]); root.mkdir(mode=0o700)
    guardian = Guardian(sys.argv[2]); cases=[]
    try:
        for case in CASES:
            cases.append(one(guardian,root,case))
    finally:
        previous=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        try:
            guardian.settle();guardian.close()
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK,previous)
    save(root/'checks.json',dict(cases=cases,reaped=guardian.records,deterministicWriterBarrier=True,
        guardianAliveRequired=True,universalContainment=False,deviceOrGpuAccess=False,publicMount=False))
    print(json.dumps(dict(passed=True,cases=3,ownersKilled=3,normalLeaderExits=3,
                          heldLeaseDeferrals=3,childrenReaped=9,subreaperRestored=True),sort_keys=True))


if __name__=='__main__':
    main()
