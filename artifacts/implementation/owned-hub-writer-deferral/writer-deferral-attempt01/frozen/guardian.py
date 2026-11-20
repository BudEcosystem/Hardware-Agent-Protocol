"""Original dedicated test-process owner; kernel child relation grants authority.

No process is selected from a durable job record. This module is not a public
provider, arbitrary-process manager, sandbox, or system-wide process reaper.
"""
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import threading
import time

HELPER_SHA = 'a6ee94bcf3dc03df19f0dd07a81663badd4875ef1a6c429afbc55d7b2373b977'
FLAGS = os.WEXITED | os.WNOHANG | os.WNOWAIT


class Guardian:
    def __init__(self, helper_path):
        self.pid = os.getpid(); self.tid = threading.get_native_id()
        self.handles = {}; self.records = []; self.registered = 0; self.closed = False
        body = Path(helper_path).read_bytes()
        assert len(body) < 1024*1024 and hashlib.sha256(body).hexdigest() == HELPER_SHA
        self.fd = os.memfd_create('hms-harness-binding', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        assert os.write(self.fd, body) == len(body)
        seals = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE
        fcntl.fcntl(self.fd, fcntl.F_ADD_SEALS, seals)
        self.helper = ctypes.CDLL('/proc/self/fd/'+str(self.fd))
        for name in ('hms_subreaper_get', 'hms_owner_signal_snapshot'):
            getattr(self.helper, name).argtypes = []; getattr(self.helper, name).restype = ctypes.c_int
        self.helper.hms_subreaper_set.argtypes = [ctypes.c_int]
        self.helper.hms_subreaper_set.restype = ctypes.c_int
        assert self.helper.hms_owner_signal_snapshot() == 1
        assert len(os.listdir('/proc/self/task')) == 1 and self.helper.hms_subreaper_get() == 0
        try:
            os.waitid(os.P_ALL, 0, FLAGS)
        except ChildProcessError:
            pass
        else:
            raise AssertionError('Dedicated guardian must begin without children')
        assert self.helper.hms_subreaper_set(1) == 0
        self.guard()

    def guard(self):
        assert not self.closed and os.getpid() == self.pid and threading.get_native_id() == self.tid
        assert len(os.listdir('/proc/self/task')) == 1
        assert self.helper.hms_owner_signal_snapshot() == 1 and self.helper.hms_subreaper_get() == 1

    @staticmethod
    def stat(pid):
        body = Path('/proc', str(pid), 'stat').read_bytes(); assert len(body) <= 4096
        fields = body.rsplit(b')', 1)[1].split()
        return dict(pid=pid, parent=int(fields[1]), group=int(fields[2]), session=int(fields[3]),
                    startTicks=int(fields[19]), state=fields[0].decode('ascii'))

    def register(self, pid):
        self.guard()
        if pid in self.handles:
            self.status(pid); return
        assert self.registered < 128
        # waitid is the authority check, including for an adopted running child.
        # No competing reaper exists in this sole-thread dedicated process.
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        fd = None
        try:
            os.waitid(os.P_PID, pid, FLAGS)
            info = self.stat(pid); assert info['parent'] == self.pid
            fd = os.pidfd_open(pid, 0)
            os.waitid(os.P_PID, pid, FLAGS)
            assert self.stat(pid)['startTicks'] == info['startTicks']
            self.handles[pid] = dict(pidfd=fd, identity=info); fd = None
            self.registered += 1
        finally:
            if fd is not None:
                os.close(fd)
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)

    def refresh(self):
        self.guard()
        body = Path('/proc/self/task', str(self.tid), 'children').read_bytes()
        assert len(body) <= 8192
        ids = [int(part) for part in body.split()]; assert len(ids) <= 128
        for pid in ids:
            assert 0 < pid < 2**31
            self.register(pid)
        return ids

    def status(self, pid):
        self.guard(); item = self.handles[pid]
        status = os.waitid(os.P_PID, pid, FLAGS)
        assert self.stat(pid)['startTicks'] == item['identity']['startTicks']
        return status

    def send(self, pid, action):
        self.status(pid)
        try:
            signal.pidfd_send_signal(self.handles[pid]['pidfd'], action)
        except ProcessLookupError:
            pass  # Original child remains unreaped; caller still collects it.

    def reap(self, pid):
        assert self.status(pid) is not None
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            got, status, usage = os.wait4(pid, 0); assert got == pid
            item = self.handles.pop(pid); os.close(item['pidfd'])
            result = dict(**item['identity'], exitCode=os.waitstatus_to_exitcode(status),
                          reaped=True, cpuSeconds=usage.ru_utime+usage.ru_stime, peakRSSKiB=usage.ru_maxrss)
            self.records.append(result)
            return result
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)

    def wait_exit(self, pid, seconds=5):
        end = time.monotonic()+seconds
        while self.status(pid) is None:
            assert time.monotonic() < end, 'Owned child did not exit within observed bound'
            time.sleep(.005)
        return self.reap(pid)

    def fork(self, fixed_child, *, cpu_seconds=5, address_bytes=256*1024**2):
        """Only original fixed functions from the reviewed harness call this."""
        self.guard()
        assert (cpu_seconds, address_bytes) in ((5, 256*1024**2), (30, 512*1024**2))
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        pid = None
        try:
            pid = os.fork()
            if pid == 0:
                try:
                    signal.signal(signal.SIGTERM, signal.SIG_DFL)
                    signal.signal(signal.SIGINT, signal.SIG_DFL)
                    signal.pthread_sigmask(signal.SIG_SETMASK, previous)
                    assert self.helper.hms_subreaper_get() == 0
                    for kind, cap in [(resource.RLIMIT_CPU, cpu_seconds), (resource.RLIMIT_AS, address_bytes),
                                      (resource.RLIMIT_FSIZE, 1024**2), (resource.RLIMIT_NOFILE, 64),
                                      (resource.RLIMIT_CORE, 0)]:
                        resource.setrlimit(kind, (cap, cap))
                    fixed_child()
                    os._exit(0)
                except BaseException:
                    os._exit(90)
            self.register(pid)
            return pid
        finally:
            if pid != 0:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous)

    def empty(self):
        self.refresh()
        try:
            os.waitid(os.P_ALL, 0, FLAGS)
        except ChildProcessError:
            assert not self.handles
            return True
        return False

    def settle(self, seconds=8):
        self.guard(); end = time.monotonic()+seconds
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            while True:
                self.refresh()
                for pid in list(self.handles):
                    self.send(pid, signal.SIGKILL)
                for pid in list(self.handles):
                    if self.status(pid) is not None:
                        self.reap(pid)
                if self.empty():
                    return
                assert time.monotonic() < end, 'Guardian retains unresolved children; no passing claim'
                time.sleep(.005)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)

    def close(self):
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            self.guard(); assert self.empty()
            assert self.helper.hms_subreaper_set(0) == 0 and self.helper.hms_subreaper_get() == 0
            os.close(self.fd); self.closed = True
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def write_record(fd, value):
    body = json.dumps(value, sort_keys=True, separators=(',', ':')).encode('ascii')+b'\n'
    assert len(body) <= 4096
    assert os.write(fd, body) == len(body)


def read_record(fd, seconds=5):
    os.set_blocking(fd, False); body = bytearray(); end = time.monotonic()+seconds
    while time.monotonic() < end:
        try:
            chunk = os.read(fd, 4097-len(body))
        except BlockingIOError:
            time.sleep(.005); continue
        assert chunk, 'Owner closed checkpoint pipe before its bounded record'
        body.extend(chunk); assert len(body) <= 4096
        if body.endswith(b'\n'):
            return json.loads(body)
    raise AssertionError('Checkpoint observation deadline')
