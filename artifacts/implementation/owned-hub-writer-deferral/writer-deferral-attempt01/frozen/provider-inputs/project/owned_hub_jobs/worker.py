"""Fixed original CPU artifact. No caller code/path/module selection.

The parent supplies only inherited sealed input/code descriptors, a pipe gate
and a writer lease. Installed diagnostic modes are private harness fixtures.
This program and its one computation child retain the lease through exit.
"""
import fcntl
import json
import os
import resource
import signal
import stat
import sys
import time

SEALS = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE


def output(value):
    body = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')
    view = memoryview(body)
    while view:
        amount = os.write(1, view)
        if amount <= 0:
            raise RuntimeError('short output')
        view = view[amount:]


def compute(launch, fixture=(), lease=None, leader=None):
    request = launch['request']; inp = request['input']; mode = launch['installedTestMode']
    if mode == 'cpu_limit':
        # Installed finite fault fixture. The hard CPU limit is below this
        # process-CPU deadline; no caller selects this mode. The waiting leader
        # reaps the child and reports its actual signal/resource observation.
        until = time.process_time()+request['limits']['cpuSeconds']+1
        while time.process_time() < until:
            pass
    if mode == 'output_limit':
        os.write(1, b'x' * 8192)
        return 0
    total = 0; term = inp['first']; step = inp['step']
    for _ in range(inp['count']):
        total = (total + term * term) & ((1 << 64)-1)
        term += step
    result = {'count': inp['count'], 'sumSquaresMod64': str(total)}
    if mode == 'bool_count':
        result['count'] = True
    if mode == 'float_count':
        result['count'] = float(inp['count'])
    if mode == 'numeric_sum':
        result['sumSquaresMod64'] = total
    if mode == 'leading_zero_sum':
        result['sumSquaresMod64'] = '0' + str(total)
    if mode == 'wrong_result':
        result['sumSquaresMod64'] = str((total+1) % (1 << 64))
    returned = dict(profile='hms.host.cpu-series-result/0.1', requestDigest=launch['digest'],
                    nonce=launch['nonce'], artifact=request['artifact'], result=result)
    if mode == 'wrong_nonce':
        returned['nonce'] = '0' * 32
    if mode == 'malformed':
        os.write(1, b'{'); return 0
    output(returned)
    if mode == 'writer_barrier':
        # Computation is released only by the original G gate. This second
        # pipe holds the writer lifetime after its valid output, without sleep.
        hold, notice = fixture
        info = os.fstat(lease)
        with open('/proc/self/stat', 'rb') as source:
            body = source.read(4097)
        if len(body) > 4096:
            return 80
        fields = body.rsplit(b')', 1)[1].split()
        record = dict(profile='hms.writer-barrier-ready/1', stage='computed-before-writer-hold',
            requestDigest=launch['digest'], nonce=launch['nonce'], artifact=request['artifact'],
            child=dict(pid=os.getpid(), startTicks=int(fields[19]), group=os.getpgrp(), session=os.getsid(0)),
            originalLeader=leader, lease=dict(device=info.st_dev, inode=info.st_ino), result=result)
        body = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')+b'\n'
        if len(body) > 4096 or os.write(notice, body) != len(body):
            return 81
        os.close(notice)
        released = os.read(hold, 1)
        os.close(hold)
        return 0 if released == b'R' else 79
    if mode in ('early_leader_exit', 'writer_lingers'):
        # Bounded installed fault fixture. Inherits the same writer lease and
        # standard-stream descriptors, so leader exit must not prove settlement.
        time.sleep(0.4)
    return 0


def main():
    if len(sys.argv) not in (5, 7) or not sys.flags.isolated or not sys.flags.no_site:
        return 70
    source, code, gate, lease = (int(value) for value in sys.argv[1:5])
    fixture = tuple(int(value) for value in sys.argv[5:])
    if fcntl.fcntl(source, fcntl.F_GET_SEALS) != SEALS or fcntl.fcntl(code, fcntl.F_GET_SEALS) != SEALS:
        return 71
    size = os.fstat(source).st_size
    if not 0 < size <= 4096:
        return 72
    os.lseek(source, 0, os.SEEK_SET)
    body = os.read(source, size+1)
    if len(body) != size:
        return 72
    launch = json.loads(body)
    if set(launch) != {'profile', 'request', 'digest', 'nonce', 'installedTestMode'} or launch['profile'] != 'hms.host.cpu-launch/0.1':
        return 72
    request = launch['request']; limits = request['limits']
    if launch['installedTestMode'] == 'writer_barrier':
        if len(fixture) != 2 or len(set((source, code, gate, lease, *fixture))) != 6:
            return 82
        for fd, access in zip(fixture, (os.O_RDONLY, os.O_WRONLY)):
            if not stat.S_ISFIFO(os.fstat(fd).st_mode) or fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != access:
                return 82
    elif fixture:
        return 82
    # The owner installs these same per-process hard limits before interpreter
    # exec. Reapplying them here verifies the fixed worker's inherited profile.
    # Fork gives the single computation child its own limits, not a shared quota.
    for kind, value in ((resource.RLIMIT_CPU, limits['cpuSeconds']),
                        (resource.RLIMIT_AS, limits['addressBytes']),
                        (resource.RLIMIT_FSIZE, limits['fileBytes']),
                        (resource.RLIMIT_NOFILE, limits['openFiles']),
                        (resource.RLIMIT_CORE, 0)):
        resource.setrlimit(kind, (value, value))
    os.umask(0o077)
    if launch['installedTestMode'] == 'bootstrap_failure':
        return 74
    # The leader remains to reap its fixed child on ordinary cancellation.
    # The computation child restores default TERM behavior after fork. KILL
    # cannot run cleanup; observed quiescence never claims universal reaping.
    signal.signal(signal.SIGTERM, lambda *_: None)
    # EOF or any other byte exits before computation or descendant creation.
    accepted = os.read(gate, 1)
    os.close(gate)
    if accepted != b'G':
        return 73
    leader = os.getpid()
    child = os.fork()
    if child == 0:
        try:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os._exit(compute(launch, fixture, lease, leader))
        except BaseException:
            os._exit(75)
    if launch['installedTestMode'] == 'writer_barrier':
        for fd in fixture:
            os.close(fd)
        return 0
    if launch['installedTestMode'] == 'early_leader_exit':
        return 0
    _, status, usage = os.wait4(child, 0)
    if launch['installedTestMode'] == 'cpu_limit':
        diagnostic = dict(childSignal=os.WTERMSIG(status) if os.WIFSIGNALED(status) else None,
                          childCpuSeconds=usage.ru_utime+usage.ru_stime)
        body = json.dumps(diagnostic, sort_keys=True, separators=(',', ':')).encode('ascii')
        if os.write(2, body) != len(body):
            return 78
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    return 76


if __name__ == '__main__':
    try:
        status = main()
    except BaseException:
        status = 77
    # Never explicitly release the inherited writer lease before process exit.
    os._exit(status)
