"""Single-owner Linux CPU-job provider. Source preparation, not a public mount."""
import ctypes
import fcntl
import hashlib
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid

from . import contracts, ledger
from .contracts import (JobError, MAX_KEYS, canonical, parse, require, request,
                        request_digest, identifier, key, validate_output)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parent
OWNER_CONTRACT = 'single-native-thread-no-competing-reaper/v1'
SEALS = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE
HELPER_SHA = '97a1a26fe0b954efc42f52420e552c286047ebbb11c188eed69870c452c850a1'
HELPER_SOURCE_SHA = '94a123dad1388da22418e806d3249edab8065410a735e2f8100a8238ab0dad25'
MODES = {'normal', 'early_leader_exit', 'writer_lingers', 'bootstrap_failure',
         'wrong_result', 'wrong_nonce', 'malformed', 'output_limit',
         'bool_count', 'float_count', 'numeric_sum', 'leading_zero_sum', 'cpu_limit'}
# These capture the protected imported image, not current path bytes recomputed
# at replay time. The runner must freeze/check source before importing it.
IMPORTED_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
IMPORTED = {'project/owned_hub_jobs/provider.py': IMPORTED_SOURCE_SHA256,
            'project/owned_hub_jobs/contracts.py': contracts.IMPORTED_SOURCE_SHA256,
            'project/owned_hub_jobs/ledger.py': ledger.IMPORTED_SOURCE_SHA256}
for _name in ('project/owned_hub_jobs/__init__.py', 'project/owned_hub_jobs/worker.py'):
    IMPORTED[_name] = hashlib.sha256((ROOT/_name).read_bytes()).hexdigest()
WORKER_BYTES = (PACKAGE/'worker.py').read_bytes()
require(hashlib.sha256(WORKER_BYTES).hexdigest() == IMPORTED['project/owned_hub_jobs/worker.py'], 'IMPORT_CHANGED')


def bounded_image(path):
    with open(path, 'rb') as source:
        body = source.read(1024*1024+1)
    require(len(body) <= 1024*1024, 'IMAGE_SIZE')
    return body


def sealed(body, name):
    require(type(body) is bytes and len(body) <= 1024*1024, 'IMAGE_SIZE')
    fd = os.memfd_create(name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        ledger.write_all(fd, body); os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, SEALS)
        require(fcntl.fcntl(fd, fcntl.F_GET_SEALS) == SEALS, 'SEAL_FAILED')
        return fd
    except BaseException:
        os.close(fd); raise


def fd_digest(fd):
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 64*1024*1024, 'RUNTIME_FILE')
    os.lseek(fd, 0, os.SEEK_SET); h = hashlib.sha256(); total = 0
    while True:
        body = os.read(fd, 65536)
        if not body:
            break
        total += len(body); require(total <= info.st_size, 'RUNTIME_CHANGED'); h.update(body)
    require(total == info.st_size, 'RUNTIME_CHANGED'); os.lseek(fd, 0, os.SEEK_SET)
    return h.hexdigest()


def group_members(pgid):
    """Bounded observation, never authority to signal a recovered numeric PID."""
    result = []; seen = 0
    with os.scandir('/proc') as entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            seen += 1; require(seen <= 16384, 'PROCESS_SCAN_LIMIT')
            try:
                with open('/proc/'+entry.name+'/stat', 'rb') as source:
                    body = source.read(4097)
                require(len(body) <= 4096, 'PROCESS_RECORD_LIMIT')
                fields = body.rsplit(b')', 1)[1].split()
                if int(fields[2]) == pgid:
                    require(len(result) < 16, 'PROCESS_GROUP_LIMIT')
                    result.append(dict(pid=int(entry.name), state=fields[0].decode('ascii'),
                                       startTicks=int(fields[19]), session=int(fields[3]),
                                       rssBytes=int(fields[21])*os.sysconf('SC_PAGE_SIZE')))
            except (FileNotFoundError, ProcessLookupError):
                continue
            except (PermissionError, ValueError, IndexError) as error:
                raise JobError('PROCESS_OBSERVATION_UNKNOWN') from error
    return result


class Owned:
    def __init__(self, process, gate, start):
        self.process, self.gate, self.started = process, gate, start
        self.pidfd = None
        self.stop_at = None
        self.killed = False
        self.ownership_error = None
        self.settlement = None
        self.stdout = bytearray(); self.stderr = bytearray()
        self.eof = {'stdout': False, 'stderr': False}
        self.observed = {}


class HostJobs:
    def __init__(self, root, *, owner_contract, create=False):
        require(owner_contract == OWNER_CONTRACT, 'OWNER_CONTRACT_REQUIRED')
        require(sys.platform == 'linux' and os.uname().machine == 'x86_64' and
                sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12), 'PLATFORM')
        require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal') and
                hasattr(os, 'WNOWAIT') and hasattr(os, 'memfd_create'), 'PLATFORM')
        self.owner_pid = os.getpid(); self.owner_thread = threading.get_native_id()
        self.session = uuid.uuid4().hex
        self._owned = {}; self._settled = {}; self._closed = False; self._busy = False
        self._helper_fd = self._runtime_fd = None
        self.ledger = None
        try:
            body = bounded_image(ROOT/'helper-check01/libowner-preconditions.so')
            require(hashlib.sha256(body).hexdigest() == HELPER_SHA and
                    hashlib.sha256(bounded_image(ROOT/'owner_preconditions.c')).hexdigest() == HELPER_SOURCE_SHA,
                    'HELPER_IDENTITY')
            self._helper_fd = sealed(body, 'hms-owner-preconditions')
            self._helper = ctypes.CDLL('/proc/self/fd/'+str(self._helper_fd))
            self._helper.hms_owner_signal_snapshot.argtypes = []
            self._helper.hms_owner_signal_snapshot.restype = ctypes.c_int
            self._session(launch=True)
            self._runtime_fd = os.open('/proc/self/exe', os.O_RDONLY | os.O_CLOEXEC)
            self._runtime_sha = fd_digest(self._runtime_fd)
            mode = self._installed_test_mode(); require(mode in MODES, 'INSTALLED_MODE')
            self._mode = mode
            self.manifest = dict(profile=contracts.PROFILE, artifact='integer-series-squares/v1',
                sources=dict(IMPORTED), helperSource=HELPER_SOURCE_SHA, helperBinary=HELPER_SHA,
                interpreter=dict(sha256=self._runtime_sha, version=sys.version, implementation='cpython'),
                installedTestMode=mode,
                dependencyScope='Pinned original bytes and interpreter ELF; host stdlib, dynamic loader and system shared libraries are trusted unpinned dependencies; not a sandbox')
            self.artifact = contracts.digest(b'HMS-INSTALLED-HOST-ARTIFACT-v1\0'+canonical(self.manifest))
            self._fresh()
            self.ledger = ledger.Ledger(root, create=create)
        except BaseException:
            self._dispose()
            raise

    def _installed_test_mode(self):
        """Private installed-fixture seam. Never populated from a job request."""
        return 'normal'

    def _checkpoint(self, phase, row):
        """Private owned harness crash/fault seam, never a caller callback."""

    def _session(self, launch=False):
        require(not self._closed and os.getpid() == self.owner_pid and
                threading.get_native_id() == self.owner_thread, 'OWNER_SESSION')
        require(len(os.listdir('/proc/self/task')) == 1, 'OWNER_THREADS')
        if launch:
            require(self._helper.hms_owner_signal_snapshot() == 1, 'SIGCHLD_PRECONDITION')

    def _fresh(self):
        self._session(launch=True)
        for name, expected in IMPORTED.items():
            require(hashlib.sha256(bounded_image(ROOT/name)).hexdigest() == expected, 'IMPLEMENTATION_CHANGED')
        require(hashlib.sha256(bounded_image(ROOT/'owner_preconditions.c')).hexdigest() == HELPER_SOURCE_SHA,
                'IMPLEMENTATION_CHANGED')
        require(hashlib.sha256(bounded_image(ROOT/'helper-check01/libowner-preconditions.so')).hexdigest() == HELPER_SHA,
                'IMPLEMENTATION_CHANGED')
        require(fd_digest(self._runtime_fd) == self._runtime_sha, 'RUNTIME_CHANGED')

    def _row(self, original_key):
        key(original_key)
        row = self.ledger.get(identifier(original_key)); require(row is not None, 'NOT_FOUND')
        return row

    def _view(self, row):
        owned = self._owned.get(row['id'])
        return dict(record=parse(canonical(row)), liveOwner=owned is not None,
                    ownershipError=None if owned is None else owned.ownership_error,
                    ownerSettlement=self._settled.get(row['id']),
                    controlStorageQualified=False, controlStoragePoisoned=self.ledger.poisoned,
                    deadlineService='poll-driven; no scheduling guarantee')

    def lookup(self, original_key):
        self._session(); return self._view(self._row(original_key))

    def start(self, value):
        self._session(); require(not self._busy, 'REENTRY')
        value = request(value); name = identifier(value['key'])
        old = self.ledger.get(name)
        if old is not None:
            require(old['digest'] == request_digest(value), 'KEY_CONFLICT')
            return self._view(old)
        require(not self.ledger.poisoned, 'CONTROL_STORAGE_UNRESOLVED')
        self._fresh(); require(value['artifact'] == self.artifact, 'ARTIFACT_MISMATCH')
        require(len(self.ledger.state['rows']) < MAX_KEYS, 'RETENTION_FULL')
        require(not any(row['phase'] != 'settled' for row in self.ledger.state['rows'].values()), 'JOB_BUSY')
        self._busy = True
        row = dict(id=name, request=value, digest=request_digest(value), nonce=uuid.uuid4().hex,
                   phase='admitted', history=['admitted'], lease=None, ownerSession=self.session,
                   pid=None, releaseIntent=False, cancelRequested=False, reason=None, receipt=None)
        lease = source = code = gate_read = gate_write = None
        try:
            row = self.ledger.save(row); self._checkpoint('admitted', row)
            lease_name = 'lease-'+name
            lease = os.open(lease_name, os.O_RDONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600, dir_fd=self.ledger.fd)
            info = ledger.safe(lease, 0); fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.fsync(lease); os.fsync(self.ledger.fd)
            row['lease'] = dict(device=info.st_dev, inode=info.st_ino)
            row = self.ledger.save(row, 'launching'); self._checkpoint('launching', row)
            envelope = dict(profile='hms.host.cpu-launch/0.1', request=value, digest=row['digest'],
                            nonce=row['nonce'], installedTestMode=self._mode)
            source = sealed(canonical(envelope), 'hms-job-input')
            code = sealed(WORKER_BYTES, 'hms-job-code')
            gate_read, gate_write = os.pipe2(os.O_CLOEXEC)
            limits = dict(value['limits'])
            previous_mask = None
            def child_limits():
                # The verified sole-native-thread profile makes this small
                # original pre-exec hook permissible. It changes only the child.
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
                for kind, cap in ((resource.RLIMIT_CPU, limits['cpuSeconds']),
                                  (resource.RLIMIT_AS, limits['addressBytes']),
                                  (resource.RLIMIT_FSIZE, limits['fileBytes']),
                                  (resource.RLIMIT_NOFILE, limits['openFiles']),
                                  (resource.RLIMIT_CORE, 0)):
                    resource.setrlimit(kind, (cap, cap))
            self._fresh()
            started = time.monotonic()
            owned = Owned(None, gate_write, started)
            previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
            try:
                process = subprocess.Popen([sys.executable, '-I', '-S', '-B', '/proc/self/fd/'+str(code),
                    str(source), str(code), str(gate_read), str(lease)],
                    executable='/proc/self/fd/'+str(self._runtime_fd),
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=self.ledger.root, env={'LANG':'C','LC_ALL':'C'}, close_fds=True,
                    pass_fds=(source, code, gate_read, lease, self._runtime_fd),
                    start_new_session=True, preexec_fn=child_limits)
                owned.process = process
                self._owned[name] = owned
                gate_write = None
                for stream in (process.stdout, process.stderr):
                    os.set_blocking(stream.fileno(), False)
                self._checkpoint('ownership_registered', row)
            finally:
                # A pending Python interrupt can run only after the live child
                # is retained (or Popen itself failed). Child restores its own
                # original mask before exec, so our guard never leaks to it.
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            # No poll()/wait() has reaped the original child. Failure is not an
            # excuse to reconstruct ownership from a later numeric PID.
            owned.pidfd = os.pidfd_open(process.pid, 0)
            self._anchor(owned)
            self._checkpoint('spawned', row)
            row['pid'] = process.pid
            row = self.ledger.save(row, 'associated')
            self._checkpoint('associated', row)
            return self._view(row)  # Gate remains closed until a serviced poll.
        except BaseException:
            owned = self._owned.get(name)
            if owned is not None:
                self._close_gate(owned)
                owned.ownership_error = owned.ownership_error or 'LAUNCH_INTERRUPTED'
            raise
        finally:
            self._busy = False
            for fd in (lease, source, code, gate_read, gate_write):
                if fd is not None:
                    os.close(fd)

    @staticmethod
    def _close_gate(owned):
        if owned.gate is not None:
            os.close(owned.gate); owned.gate = None

    def _waitable(self, owned):
        self._session(launch=True)
        require(owned.process.returncode is None, 'OWNERSHIP_UNRESOLVED')
        try:
            status = os.waitid(os.P_PID, owned.process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            require(status is None or status.si_pid == owned.process.pid, 'OWNERSHIP_UNRESOLVED')
            require(os.getpgid(owned.process.pid) == owned.process.pid and
                    os.getsid(owned.process.pid) == owned.process.pid, 'GROUP_OWNERSHIP_CHANGED')
            return status
        except (ChildProcessError, ProcessLookupError) as error:
            owned.ownership_error = 'OWNERSHIP_UNRESOLVED'
            raise JobError('OWNERSHIP_UNRESOLVED') from error

    def _anchor(self, owned):
        require(owned.pidfd is not None, 'OWNERSHIP_UNRESOLVED')
        return self._waitable(owned)

    def _signal(self, owned, action):
        # A pidfd signal targets the leader only. killpg is separately justified
        # by the waitable unreaped leader and its unchanged owned session/group.
        self._anchor(owned)
        try:
            signal.pidfd_send_signal(owned.pidfd, action)
        except ProcessLookupError:
            pass
        self._anchor(owned)
        try:
            os.killpg(owned.process.pid, action)
        except ProcessLookupError:
            pass

    def _stop(self, row, owned, reason, cancellation=False):
        self._close_gate(owned)
        row['cancelRequested'] = row['cancelRequested'] or cancellation
        row['reason'] = row['reason'] or reason
        if owned.stop_at is None:
            owned.stop_at = time.monotonic()
            try:
                self._signal(owned, signal.SIGTERM)
            except (JobError, OSError):
                owned.ownership_error = 'OWNERSHIP_UNRESOLVED'
        if not self.ledger.poisoned:
            row = self.ledger.save(row, None if row['phase'] == 'stopping' else 'stopping')
        return row

    def cancel(self, original_key):
        self._session(); require(not self._busy, 'REENTRY')
        row = self._row(original_key)
        if self._finish_retained_settlement(row):
            return self._view(row)
        if row['phase'] == 'settled':
            self._finish_terminal(row)
            return self._view(row)
        owned = self._owned.get(row['id'])
        require(owned is not None, 'NO_LIVE_OWNERSHIP')
        row = self._stop(row, owned, 'CANCEL_REQUESTED', cancellation=True)
        return self._view(row)

    def _streams(self, row, owned):
        limit = row['request']['limits']['streamBytes']; overflow = False
        # At most8KiB read per stream per poll; output retained never exceeds cap.
        for name in ('stdout', 'stderr'):
            if owned.eof[name]:
                continue
            stream = getattr(owned.process, name)
            os.set_blocking(stream.fileno(), False)
            try:
                body = os.read(stream.fileno(), 8192)
            except BlockingIOError:
                continue
            if not body:
                owned.eof[name] = True; stream.close(); continue
            kept = getattr(owned, name); room = max(0, limit-len(kept))
            kept.extend(body[:room]); overflow |= len(body) > room
        return overflow

    def _lease(self, row):
        if row['lease'] is None:
            return None
        fd = os.open('lease-'+row['id'], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.ledger.fd)
        try:
            info = ledger.safe(fd, 0)
            require(row['lease'] == dict(device=info.st_dev, inode=info.st_ino), 'WRITER_IDENTITY_UNKNOWN')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd); return False
            return fd
        except BaseException:
            os.close(fd); raise

    def poll(self, original_key):
        self._session(); require(not self._busy, 'REENTRY')
        row = self._row(original_key)
        if self._finish_retained_settlement(row):
            return self._view(row)
        if row['phase'] == 'settled':
            self._finish_terminal(row)
            return self._view(row)
        owned = self._owned.get(row['id'])
        if owned is None:
            return self.reconcile(original_key)
        self._busy = True
        try:
            now = time.monotonic(); limits = row['request']['limits']
            if self.ledger.poisoned and owned.stop_at is None:
                row = self._stop(row, owned, 'CONTROL_STORAGE_UNRESOLVED')
            if row['phase'] == 'associated' and not row['cancelRequested']:
                if owned.gate is None:
                    row = self._stop(row, owned, 'LAUNCH_INTERRUPTED')
                elif now-owned.started >= limits['wallMs']/1000:
                    row = self._stop(row, owned, 'WALL_LIMIT')
                else:
                    try:
                        self._fresh()
                        if self._anchor(owned) is not None:
                            row = self._stop(row, owned, 'BOOTSTRAP_EXIT')
                            return self._view(row)
                        self._checkpoint('before_release', row)
                        row['releaseIntent'] = True
                        row = self.ledger.save(row, 'released')
                        self._checkpoint('release_intent', row)
                        # Source checks/fsync may have consumed the remaining
                        # observed wall budget. The earlier sample authorizes
                        # no gate byte after those potentially slow operations.
                        if time.monotonic()-owned.started >= limits['wallMs']/1000:
                            row = self._stop(row, owned, 'WALL_LIMIT')
                        else:
                            require(os.write(owned.gate, b'G') == 1, 'GATE_WRITE')
                            self._close_gate(owned); self._checkpoint('gate_released', row)
                    except BaseException:
                        self._close_gate(owned)
                        raise
            if self._streams(row, owned):
                row = self._stop(row, owned, 'STREAM_LIMIT')
            if now-owned.started >= limits['wallMs']/1000 and owned.stop_at is None:
                row = self._stop(row, owned, 'WALL_LIMIT')
            if owned.stop_at is not None and not owned.killed and now-owned.stop_at >= limits['stopGraceMs']/1000:
                try:
                    self._signal(owned, signal.SIGKILL); owned.killed = True
                except (JobError, OSError):
                    owned.ownership_error = 'OWNERSHIP_UNRESOLVED'
            if owned.stop_at is not None and now-owned.stop_at >= (
                    limits['stopGraceMs']+limits['settleGraceMs'])/1000:
                owned.ownership_error = owned.ownership_error or 'SETTLEMENT_DEADLINE_OBSERVED'
            # Failed pidfd acquisition permits passive collection only. The
            # original waitable-child contract still must hold; no signal uses
            # this weaker path, and no recovered numeric PID enters it.
            status = self._waitable(owned)
            members = group_members(owned.process.pid)
            for member in members:
                entry = {name: member[name] for name in ('pid', 'startTicks', 'session')}
                identity = (entry['pid'], entry['startTicks'])
                require(identity in owned.observed or len(owned.observed) < 16, 'PROCESS_GROUP_LIMIT')
                owned.observed[identity] = entry
            live = [member for member in members if member['state'] not in ('Z', 'X')]
            if status is not None and not live and all(owned.eof.values()):
                lease = self._lease(row)
                if lease is not False:
                    try:
                        self._checkpoint('writer_settled', row)
                        code = status.si_status if status.si_code == os.CLD_EXITED else -status.si_status
                        result = None; valid = False; reason = row['reason']
                        if (row['releaseIntent'] and code == 0 and not owned.stderr and
                                reason in (None, 'CANCEL_REQUESTED')):
                            try:
                                result = validate_output(bytes(owned.stdout), row)['result']; valid = True
                            except JobError:
                                reason = reason or 'OUTPUT_INVALID'
                        if valid:
                            outcome = 'completed'
                        elif row['cancelRequested']:
                            outcome = 'canceled'
                        elif not row['releaseIntent']:
                            outcome = 'not_started'
                        else:
                            outcome = 'failed'; reason = reason or 'PROCESS_FAILED'
                        row['reason'] = reason
                        row['receipt'] = self._receipt(row, outcome, code, valid, result, recovered=False,
                                                       observed=list(owned.observed.values()))
                        owned.settlement = dict(processExitCode=code, writerLeaseQuiescent=True,
                                                streamEof=True, observedLiveGroupMembers=0)
                        try:
                            if not self.ledger.poisoned:
                                row = self.ledger.save(row, 'settled')
                        finally:
                            # All group signals precede this reap. A failed
                            # durable commit retains ambiguity in the ledger;
                            # only separate ephemeral cleanup evidence survives.
                            self._reap_settled(row['id'], owned)
                        if row['phase'] == 'settled':
                            self._checkpoint('terminal_committed', row)
                        else:
                            row = self._row(original_key)
                    finally:
                        if lease is not None:
                            os.close(lease)
            return self._view(row)
        finally:
            self._busy = False

    def _reap_settled(self, name, owned):
        require(owned.settlement is not None, 'SETTLEMENT_REQUIRED')
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            # Already-reaped recovery uses this retained live object's proven
            # settlement, never a recovered PID or invented wait result.
            if owned.process.returncode is None:
                self._checkpoint('before_reap', self.ledger.get(name))
                self._waitable(owned)
                code = owned.process.wait()
            else:
                code = owned.process.returncode
            require(code == owned.settlement['processExitCode'], 'EXIT_CHANGED')
            self._checkpoint('reaped', self.ledger.get(name))
            self._settled[name] = dict(owned.settlement)
            self._release_owned(name)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)

    def _finish_terminal(self, row):
        owned = self._owned.get(row['id'])
        if owned is not None:
            self._reap_settled(row['id'], owned)

    def _finish_retained_settlement(self, row):
        owned = self._owned.get(row['id'])
        if owned is None or owned.settlement is None:
            return False
        # A terminal write can fail while the kernel child is already settled.
        # Finish only this retained object's cleanup before any stop/signal or
        # ordinary collection. The poisoned ledger is not retried or repaired.
        self._busy = True
        try:
            self._reap_settled(row['id'], owned)
            return True
        finally:
            self._busy = False

    @staticmethod
    def _receipt(row, outcome, code, valid, result, *, recovered, observed):
        return dict(execution=outcome,
            cancellation=('confirmed' if outcome == 'canceled' and not recovered else
                          'not_effective' if outcome == 'completed' and row['cancelRequested'] else
                          'unknown' if row['cancelRequested'] else 'none'),
            mayHaveActed=row['releaseIntent'], processExitCode=code,
            writerLeaseQuiescent=True, observedLiveGroupMembers=None if recovered else 0,
            streamEof=None if recovered else True, outputValidated=valid, result=result,
            reason=row['reason'], recovered=recovered, observedProcesses=observed,
            evidenceKind='owned-host-process', resourceReleased=True)

    def reconcile(self, original_key):
        self._session(); require(not self._busy, 'REENTRY')
        row = self._row(original_key)
        if self._finish_retained_settlement(row):
            return self._view(row)
        if row['phase'] == 'settled':
            self._finish_terminal(row)
            return self._view(row)
        if row['id'] in self._owned:
            return self.poll(original_key)
        lease = self._lease(row)
        if lease is False:
            return self._view(row)
        try:
            # No stored PID is polled/signaled and no lost stdout is reconstructed.
            outcome = 'unknown' if row['releaseIntent'] else 'not_started'
            row['reason'] = row['reason'] or 'OWNER_LOST'
            row['receipt'] = self._receipt(row, outcome, None, False, None, recovered=True, observed=[])
            return self._view(self.ledger.save(row, 'settled'))
        finally:
            if lease is not None:
                os.close(lease)

    def _release_owned(self, name):
        owned = self._owned.pop(name)
        self._close_gate(owned)
        for stream in (owned.process.stdout, owned.process.stderr):
            if not stream.closed:
                stream.close()
        if owned.pidfd is not None:
            os.close(owned.pidfd)

    def _dispose(self):
        if self.ledger is not None:
            self.ledger.close(); self.ledger = None
        for name in ('_helper_fd', '_runtime_fd'):
            fd = getattr(self, name, None)
            if fd is not None:
                os.close(fd); setattr(self, name, None)
        self._closed = True

    def close(self):
        self._session()
        require(not self._owned, 'OWNED_JOB_UNSETTLED')
        self._dispose()
