"""Staged Linux original-worker process ownership; no catalog or public mounting."""
import fcntl
import hashlib
import os
from pathlib import Path
import re
import selectors
import select
import signal
import stat
import subprocess
import sys
import threading
import time

from hms.contracts import canonical
from hms import pat_simulation_worker as worker
from hms_qualification.supervisor.bundle_io import retain_bundle, output_integrity, launch_input
from hms_qualification.supervisor.attempt_ledger import AttemptLedger, tree_usage
from hms_qualification.supervisor.supervisor_contracts import SOURCE_FILES, SupervisorError, require, digest, document, parse_request, validate_fresh, run_key, request_digest, safe_file, read_file, write_file, same, runtime_files, snapshot_bundle, source_files


def _directory(parent, name, *, create=False):
    if create: os.mkdir(name, 0o700, dir_fd=parent); os.fsync(parent)
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    info = os.fstat(fd)
    try:
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, 'QUALIFICATION_UNSAFE_FILE')
        return fd
    except BaseException:
        os.close(fd); raise


def _image_rows():
    """Bounded unique original-source/resource inventory, before admission."""
    rows = [(row['path'], worker._ROOT / row['path'], row['sha256'])
            for row in worker._IMPORTED_IDENTITY['sources']]
    # The conservative I/O driver identity also includes this non-Python input.
    manifest = worker._ROOT / 'protocol/endpoint/scenario-manifest.json'
    rows.append(('protocol/endpoint/scenario-manifest.json', manifest, hashlib.sha256(manifest.read_bytes()).hexdigest()))
    rows += source_files()
    # -I excludes the user's site directory. Copy only the already installed
    # validation distributions named and code-pinned by the original compiler;
    # neither capsule nor caller chooses a module, package or executable.
    rows += [('dependencies/' + relative, source, expected) for relative, source, expected in runtime_files()]
    unique={}
    for relative,source,expected in rows:
        require(relative not in unique or unique[relative][1]==expected,'QUALIFICATION_PACKAGE_LAYOUT')
        unique[relative]=(source,expected)
    require(len(unique)<=8192,'QUALIFICATION_PACKAGE_LIMIT')
    return [(path,source,expected) for path,(source,expected) in sorted(unique.items())]


def _image_charge(ledger, request):
    rows=_image_rows();target=ledger.bulk_root/('code-'+request['supervisorIdentity'][7:])
    if target.exists():
        _image(ledger,request)  # Existing bytes must match; no new image writes.
        return {'logicalBytes':0,'files':0}
    directories=set()
    for path,_,_ in rows:
        directories.update(str(parent) for parent in Path(path).parents)
    size=sum(source.stat().st_size for _,source,_ in rows)
    require(size<=64*1024*1024,'QUALIFICATION_PACKAGE_LIMIT')
    return {'logicalBytes':size,'files':len(rows)+len(directories)}


def _image(ledger, request):
    """Retain an exact private image from the code actually imported here."""
    rows=_image_rows()
    name = 'code-' + request['supervisorIdentity'][7:]
    target = ledger.bulk_root / name
    if target.exists():
        fd = _directory(ledger.bulk_fd, name)
        os.close(fd)
        for relative, _, expected in rows:
            path = target / relative
            # Every ancestry component was created below this trusted image.
            parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try: body = read_file(parent, path.name, maximum=4*1024*1024)
            finally: os.close(parent)
            require(hashlib.sha256(body).hexdigest() == expected, 'QUALIFICATION_CODE_IMAGE_CHANGED')
        return target
    target.mkdir(mode=0o700); os.fsync(ledger.bulk_fd)
    for relative, source, expected in rows:
        body = source.read_bytes()
        require(len(body) <= 4*1024*1024 and hashlib.sha256(body).hexdigest() == expected,
                'QUALIFICATION_IMPLEMENTATION_CHANGED')
        path = target / relative
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.exists():
            require(path.read_bytes() == body, 'QUALIFICATION_PACKAGE_LAYOUT')
            continue
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            view = memoryview(body)
            while view:
                amount = os.write(fd, view); require(amount > 0); view = view[amount:]
            os.fsync(fd)
        finally: os.close(fd)
    for parent, dirs, _ in os.walk(target, topdown=False):
        for item in dirs: os.chmod(Path(parent) / item, 0o700)
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)
    os.fsync(ledger.bulk_fd)
    return target




class QualificationSupervisor:
    def __init__(self, root, *, create=False):
        require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'QUALIFICATION_PLATFORM_UNSUPPORTED')
        self.ledger = AttemptLedger(root, create=create)
        self._execution = threading.Lock()
        self._owned = {}  # Only live Popen/pidfd handles authorize signals.

    def close(self):
        require(self._execution.acquire(blocking=False),'QUALIFICATION_BUSY')
        try:
            require(not self._owned, 'QUALIFICATION_PROCESS_UNSETTLED')
            self.ledger.close()
        finally:self._execution.release()

    def lookup(self, deployment, evaluator, run):
        return self.ledger.lookup(deployment, evaluator, run)

    def status(self, identifier):
        return self.ledger.get(identifier)['record']

    def _checkpoint(self, phase, row):
        """Private test crash seam. Production caller supplies no callbacks."""

    def execute(self, value, bundle=None):
        request = parse_request(value)
        old = self.lookup(*run_key(request))
        if old is not None:
            require(old['record']['requestDigest'] == request_digest(request), 'KEY_CONFLICT')
            return old
        require(self._execution.acquire(blocking=False), 'QUALIFICATION_BUSY')
        try:
            # Source/config validation precedes admission writes, never replay.
            bundle = snapshot_bundle(bundle)
            request = validate_fresh(request, bundle)
            image_charge=_image_charge(self.ledger,request)
            row, created = self.ledger.admit(request,_image_charge=image_charge)
            if not created: return row
            self._checkpoint('admitted', row)
            return self._launch(row, bundle)
        finally: self._execution.release()

    def _launch(self, row, bundle):
        identifier = row['record']['attemptId']; request = row['request']
        directory = lease = input_fd = None
        process = None
        try:
            image = _image(self.ledger, request)
            directory = _directory(self.ledger.bulk_fd, identifier, create=True)
            retain_bundle(directory, request, bundle)
            write_file(directory, 'input.json', canonical(launch_input(request, identifier)))
            output = _directory(directory, 'output', create=True); os.close(output)
            lease = os.open('writer.lease', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            info = safe_file(lease); fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.fsync(lease); os.fsync(directory)
            row = self.ledger.change(identifier, 'launching', lease={'device': str(info.st_dev), 'inode': str(info.st_ino)})
            self._checkpoint('launching', row)
            input_fd = os.open('input.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            safe_file(input_fd, maximum=65536)
            started = time.monotonic()
            process = subprocess.Popen([sys.executable, '-I', '-B', str(image / 'hms_qualification/supervisor/worker_entry.py'),
                str(directory), str(input_fd), str(lease)], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
                pass_fds=(directory, input_fd, lease), cwd=image,
                env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'})
            self._owned[identifier] = (process, None)
            # Before wait/poll, the child is ours or our unreaped zombie. Its PID
            # cannot be recycled before this pidfd is acquired.
            pidfd = os.pidfd_open(process.pid, 0)
            self._owned[identifier] = (process, pidfd)
            os.close(lease); lease = None
            self._checkpoint('spawned', row)
            row = self.ledger.change(identifier, 'running', pid=process.pid)
            return self._collect(row, directory, started)
        except BaseException:
            current = self.ledger.get(identifier)
            if current['record']['state'] not in ('interrupted', 'archived'):
                self.ledger.change(identifier, 'interrupted', reason='SUPERVISOR_ERROR')
            # Never discard a live handle or claim failed spawn proves no work.
            raise
        finally:
            for fd in (input_fd, lease, directory):
                if fd is not None: os.close(fd)

    def _collect(self, row, directory, started):
        identifier = row['record']['attemptId']; request = row['request']; limits = request['limits']
        process, pidfd = self._owned[identifier]
        selector = selectors.DefaultSelector(); logs = {}; sizes = {'stdout': 0, 'stderr': 0}
        reason = None; stopping = None; killed = False
        try:
            for name, stream in [('stdout', process.stdout), ('stderr', process.stderr)]:
                os.set_blocking(stream.fileno(), False); selector.register(stream, selectors.EVENT_READ, name)
                fd = os.open(name + '.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                safe_file(fd); logs[name] = fd
            deadline = started + request['groupLimits']['maxWallMs'] / 1000
            while True:
                now = time.monotonic()
                if reason is None:
                    if now >= deadline: reason = 'SUPERVISOR_DEADLINE'
                    else:
                        try:
                            tree_usage(self.ledger.bulk_root / identifier, max_files=limits['maxFilesPerAttempt'],
                                       max_bytes=limits['attemptReservationBytes'])
                        except Exception: reason = 'SUPERVISOR_RETENTION_UNKNOWN'
                if reason is not None and stopping is None:
                    self.ledger.change(identifier, 'stopping', reason=reason)
                    stopping = now
                    try: signal.pidfd_send_signal(pidfd, signal.SIGTERM)
                    except ProcessLookupError: pass
                if stopping is not None and not killed and now >= stopping + limits['stopGraceMs']/1000:
                    try: signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    except ProcessLookupError: pass
                    killed = True
                for key, _ in selector.select(.02):
                    name = key.data
                    try: chunk = os.read(key.fileobj.fileno(), 4096)
                    except BlockingIOError: continue
                    if not chunk:
                        selector.unregister(key.fileobj); key.fileobj.close(); continue
                    remaining = limits['maxStreamBytes'] - sizes[name]
                    kept = chunk[:remaining]
                    if kept:
                        require(os.write(logs[name], kept) == len(kept), 'QUALIFICATION_SHORT_WRITE')
                        sizes[name] += len(kept)
                    if len(chunk) > remaining and reason is None: reason = 'SUPERVISOR_STREAM_LIMIT'
                code = process.poll()
                if code is not None and not selector.get_map():
                    if reason is None and time.monotonic()>=deadline:
                        reason='SUPERVISOR_DEADLINE'
                    break
                if stopping is not None and now >= stopping + (limits['stopGraceMs']+limits['settleGraceMs'])/1000:
                    self.ledger.change(identifier, 'interrupted', reason=reason)
                    return self.ledger.get(identifier)
            for fd in logs.values(): os.fsync(fd)
            os.fsync(directory)
            # Process exit and EOF are insufficient if a trusted descendant
            # inherited the writer lease. Recovery still checks that lease.
            self._checkpoint('producer_settled', self.ledger.get(identifier))
            archive = self._archive_if_quiescent(row, exit_code=code, reason=reason, recovered=False)
            os.close(pidfd); del self._owned[identifier]
            return archive
        finally:
            selector.close()
            for fd in logs.values(): os.close(fd)

    def recover(self, identifier):
        require(self._execution.acquire(blocking=False), 'QUALIFICATION_BUSY')
        try:
            row = self.ledger.get(identifier)
            if row['record']['state'] == 'archived': return row
            owned = self._owned.get(identifier)
            if owned is not None:
                process, pidfd = owned
                require(process.poll() is not None, 'QUALIFICATION_PRODUCER_ACTIVE')
                for stream in (process.stdout, process.stderr):
                    if not stream.closed: stream.close()
                result = self._archive_if_quiescent(row, exit_code=process.returncode,
                    reason=row['record']['reason'] or 'SUPERVISOR_INTERRUPTED', recovered=True)
                if pidfd is not None:os.close(pidfd)
                del self._owned[identifier]
                return result
            return self._archive_if_quiescent(row, exit_code=None, reason='OWNER_LOST', recovered=True)
        finally: self._execution.release()

    def stop_owned(self, identifier):
        """Settle only a handle retained after this live owner's exception.

        This method cannot signal after reopening. Its waits are bounded but
        kernel I/O can outlive them; the active attempt then remains unresolved.
        It is not a concurrent cancellation API while execute is collecting.
        """
        require(self._execution.acquire(blocking=False), 'QUALIFICATION_BUSY')
        try:
            require(identifier in self._owned, 'QUALIFICATION_NO_OWNED_PROCESS')
            row = self.ledger.get(identifier); process, pidfd = self._owned[identifier]
            limits = row['request']['limits']
            if row['record']['state'] == 'running':
                self.ledger.change(identifier, 'stopping', reason='SUPERVISOR_STOP')
            if process.poll() is None:
                # This is still our unreaped child, not a PID reconstructed from
                # disk. Failed acquisition retains the Popen and active slot.
                if pidfd is None:
                    pidfd=os.pidfd_open(process.pid,0)
                    self._owned[identifier]=(process,pidfd)
                poll = select.poll(); poll.register(pidfd, select.POLLIN)
                for action, timeout in ((signal.SIGTERM, limits['stopGraceMs']),
                                        (signal.SIGKILL, limits['settleGraceMs'])):
                    try: signal.pidfd_send_signal(pidfd, action)
                    except ProcessLookupError: pass
                    if poll.poll(timeout): break
            if process.poll() is None:
                current = self.ledger.get(identifier)
                if current['record']['state'] != 'interrupted':
                    self.ledger.change(identifier, 'interrupted', reason='SUPERVISOR_STOP')
                return self.ledger.get(identifier)
            for stream in (process.stdout, process.stderr):
                if not stream.closed: stream.close()
            result = self._archive_if_quiescent(row, exit_code=process.returncode,
                reason='SUPERVISOR_STOP', recovered=True)
            if pidfd is not None:os.close(pidfd)
            del self._owned[identifier]
            return result
        finally: self._execution.release()

    def _archive_if_quiescent(self, row, *, exit_code, reason, recovered):
        record = row['record']; identifier = record['attemptId']; lease = None; directory = None
        try:
            if record['lease'] is None:
                # No launch intent committed. This exact input is never rerun.
                require(record['state'] in ('admitted', 'interrupted'), 'QUALIFICATION_OWNERSHIP_UNKNOWN')
                return self._archive(row, None, exit_code, reason or 'NOT_LAUNCHED', recovered, None, None)
            try:
                directory = _directory(self.ledger.bulk_fd, identifier)
                lease = os.open('writer.lease', os.O_RDWR | os.O_NOFOLLOW, dir_fd=directory)
                info = safe_file(lease)
                require(record['lease'] == {'device': str(info.st_dev), 'inode': str(info.st_ino)},
                        'QUALIFICATION_OWNERSHIP_UNKNOWN')
            except OSError as error: raise SupervisorError('QUALIFICATION_OWNERSHIP_UNKNOWN') from error
            try: fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error: raise SupervisorError('QUALIFICATION_PRODUCER_ACTIVE') from error
            body = None; integrity = None; failure = None
            try:
                body = read_file(directory, 'worker-return.json')
                result = document(body)
                integrity = output_integrity(directory, row['request'], result, identifier)
            except Exception as error:
                failure = getattr(error, 'code', 'QUALIFICATION_RETURN_UNAVAILABLE')
            usage = None
            try:
                usage = tree_usage(self.ledger.bulk_root / identifier,
                    max_files=row['request']['limits']['maxFilesPerAttempt'],
                    max_bytes=row['request']['limits']['attemptReservationBytes'])
            except Exception: failure = failure or 'QUALIFICATION_RETENTION_UNKNOWN'
            # Retain bounded malformed/nonpassing bytes independently. Full
            # semantic reduction/import is deliberately a subsequent boundary.
            return self._archive(row, body, exit_code, reason, recovered, integrity, failure, usage)
        finally:
            if lease is not None: os.close(lease)
            if directory is not None: os.close(directory)

    def _archive(self, row, body, code, reason, recovered, integrity, failure, usage=None):
        archive = {'exitCode': code, 'ownerRecovered': recovered, 'supervisorReason': reason,
            'returnValidationFailure': failure, 'evidenceIntegrity': integrity, 'usage': usage,
            'transportComplete': code == 0 and not recovered and reason is None and failure is None and integrity is not None,
            'semanticQualificationVerified': False, 'totalDiskQuotaEnforced': False,
            'unresolvedEffects': None, 'returnDigest': None}
        result = self.ledger.archive(row['record']['attemptId'], archive, body)
        self._checkpoint('archived', result)
        return result
