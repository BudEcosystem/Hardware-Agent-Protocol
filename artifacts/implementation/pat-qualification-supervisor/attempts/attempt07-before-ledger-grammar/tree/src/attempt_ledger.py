"""Separate private attempt authority. It never receives a Journal connection."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import sqlite3
import stat
import threading
import uuid

from hms.contracts import canonical
from hms.state_path import private_state_directory
from supervisor_contracts import (SupervisorError, require, digest, document,
    parse_request, request_digest, run_key, safe_file, read_file)

ACTIVE = ('admitted', 'launching', 'running', 'stopping', 'interrupted')
TRANSITIONS = {'admitted': {'launching', 'interrupted', 'archived'},
    'launching': {'running', 'interrupted', 'archived'},
    'running': {'stopping', 'interrupted', 'archived'},
    'stopping': {'interrupted', 'archived'}, 'interrupted': {'archived'}, 'archived': set()}


def tree_usage(path, *, max_files, max_bytes):
    """Bounded no-follow logical size scan, not allocated space or a quota."""
    count = size = 0
    def walk(fd, depth):
        nonlocal count, size
        require(depth <= 10, 'QUALIFICATION_RETENTION_UNKNOWN')
        with os.scandir(fd) as entries:
            for entry in entries:
                count += 1
                require(count <= max_files, 'QUALIFICATION_RETENTION_UNKNOWN')
                info = entry.stat(follow_symlinks=False)
                require(info.st_uid == os.getuid(), 'QUALIFICATION_UNSAFE_FILE')
                if stat.S_ISDIR(info.st_mode):
                    require(stat.S_IMODE(info.st_mode) == 0o700, 'QUALIFICATION_UNSAFE_FILE')
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try: walk(child, depth + 1)
                    finally: os.close(child)
                else:
                    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                        stat.S_IMODE(info.st_mode) == 0o600, 'QUALIFICATION_UNSAFE_FILE')
                    size += info.st_size
                    require(size <= max_bytes, 'QUALIFICATION_RETENTION_UNKNOWN')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: walk(fd, 0)
    finally: os.close(fd)
    return {'files': count, 'logicalBytes': size, 'totalDiskQuotaEnforced': False}


class AttemptLedger:
    def __init__(self, root, *, create=False):
        self.root = private_state_directory(root, create=create)
        self.lock = threading.RLock()
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.owner = None
        self.db = None
        try:
            self.owner = os.open('supervisor.owner', os.O_RDWR | os.O_NOFOLLOW |
                (os.O_CREAT if create else 0), 0o600, dir_fd=self.fd)
            safe_file(self.owner)
            try: fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error: raise SupervisorError('QUALIFICATION_OWNER_BUSY') from error
            for name in ('attempts.db', 'attempts.db-journal', 'attempts.db-wal', 'attempts.db-shm'):
                try: fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
                except FileNotFoundError: continue
                try: safe_file(fd)
                finally: os.close(fd)
            exists = (self.root / 'attempts.db').exists()
            require(exists or create, 'QUALIFICATION_LEDGER_MISSING')
            if not exists:
                fd = os.open('attempts.db', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600, dir_fd=self.fd)
                os.fsync(fd); os.close(fd); os.fsync(self.fd)
            self.db = sqlite3.connect(self.root / 'attempts.db', isolation_level=None, timeout=.2,
                                     check_same_thread=False)
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('PRAGMA journal_mode=DELETE')
            with self.transaction():
                names = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                require(names in (set(), {'qs_meta', 'qs_attempts'}), 'QUALIFICATION_SCHEMA_INVALID')
                if not names:
                    require(not exists, 'QUALIFICATION_SCHEMA_INVALID')
                    self.db.execute('CREATE TABLE qs_meta(version INTEGER NOT NULL CHECK(version=1))')
                    self.db.execute('INSERT INTO qs_meta VALUES(1)')
                    self.db.execute('''CREATE TABLE qs_attempts(
                        id TEXT PRIMARY KEY, deployment TEXT NOT NULL, evaluator TEXT NOT NULL, run TEXT NOT NULL,
                        request BLOB NOT NULL CHECK(typeof(request)='blob' AND length(request) BETWEEN 1 AND 65536),
                        digest TEXT NOT NULL, record BLOB NOT NULL CHECK(typeof(record)='blob' AND length(record) BETWEEN 1 AND 65536),
                        return_bytes BLOB CHECK(return_bytes IS NULL OR (typeof(return_bytes)='blob' AND length(return_bytes) BETWEEN 0 AND 65536)),
                        active INTEGER NOT NULL CHECK(active IN (0,1)), UNIQUE(deployment,evaluator,run))''')
                    self.db.execute('CREATE UNIQUE INDEX qs_singleflight ON qs_attempts(active) WHERE active=1')
                require(self.db.execute('SELECT version FROM qs_meta').fetchall() == [(1,)], 'QUALIFICATION_SCHEMA_INVALID')
                # Reopening never silently resumes or relaunches an old producer.
                for (identifier,) in self.db.execute('SELECT id FROM qs_attempts WHERE active=1').fetchall():
                    row = self._row(identifier)
                    if row['record']['state'] != 'interrupted':
                        self._change(row, 'interrupted', reason='OWNER_LOST')
        except BaseException:
            self.close()
            raise

    @contextmanager
    def transaction(self):
        with self.lock:
            require(self.db is not None and not self.db.in_transaction, 'QUALIFICATION_REENTRY')
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self.db.execute('COMMIT')
            except BaseException:
                if self.db.in_transaction: self.db.execute('ROLLBACK')
                raise

    def close(self):
        if self.db is not None: self.db.close(); self.db = None
        if self.owner is not None: os.close(self.owner); self.owner = None
        if getattr(self, 'fd', None) is not None: os.close(self.fd); self.fd = None

    def _row(self, identifier):
        require(type(identifier) is str and len(identifier) == 32 and all(c in '0123456789abcdef' for c in identifier))
        meta = self.db.execute('''SELECT typeof(request),length(request),typeof(record),length(record),
            typeof(return_bytes),length(return_bytes) FROM qs_attempts WHERE id=?''', (identifier,)).fetchone()
        require(meta is not None, 'QUALIFICATION_NOT_FOUND')
        require(meta[0] == meta[2] == 'blob' and 0 < meta[1] <= 65536 and 0 < meta[3] <= 65536 and
                ((meta[4] == 'null' and meta[5] is None) or (meta[4] == 'blob' and 0 <= meta[5] <= 65536)),
                'QUALIFICATION_LEDGER_INVALID')
        request, record, result = self.db.execute('SELECT request,record,return_bytes FROM qs_attempts WHERE id=?',
                                                 (identifier,)).fetchone()
        request = parse_request(document(request)); record = document(record)
        require(record['attemptId'] == identifier and record['requestDigest'] == request_digest(request),
                'QUALIFICATION_LEDGER_INVALID')
        require(self.db.execute('''SELECT 1 FROM qs_attempts WHERE id=? AND deployment=? AND evaluator=?
            AND run=? AND digest=? AND active=?''', (identifier, *run_key(request), request_digest(request),
                0 if record['state'] == 'archived' else 1)).fetchone() == (1,), 'QUALIFICATION_LEDGER_INVALID')
        if record['archive'] is not None:
            require(record['archive']['returnDigest'] == (digest(result) if result is not None else None),
                    'QUALIFICATION_LEDGER_INVALID')
        return {'request': request, 'record': record, 'returnBytes': result}

    def lookup(self, deployment, evaluator, run):
        with self.lock:
            row = self.db.execute('SELECT id FROM qs_attempts WHERE deployment=? AND evaluator=? AND run=?',
                                  (deployment, evaluator, run)).fetchone()
            return None if row is None else self._row(row[0])

    def get(self, identifier):
        with self.lock: return self._row(identifier)

    def admit(self, request, *, _image_charge=None):
        request = parse_request(request)
        image = {'logicalBytes':0,'files':0} if _image_charge is None else _image_charge
        require(type(image) is dict and set(image)=={'logicalBytes','files'} and
            type(image['logicalBytes']) is int and 0<=image['logicalBytes']<=64*1024*1024 and
            type(image['files']) is int and 0<=image['files']<=16384)
        with self.transaction():
            old = self.lookup(*run_key(request))
            if old is not None:
                require(old['record']['requestDigest'] == request_digest(request), 'KEY_CONFLICT')
                return old, False
            require(self.db.execute('SELECT 1 FROM qs_attempts WHERE active=1').fetchone() is None,
                    'QUALIFICATION_BUSY')
            limits = request['limits']
            require(self.db.execute('SELECT count(*) FROM qs_attempts').fetchone()[0] < limits['maxArchives'],
                    'QUALIFICATION_RETENTION_FULL')
            use = tree_usage(self.root, max_files=limits['maxFilesPerAttempt'] * limits['maxArchives'],
                             max_bytes=limits['maxRetainedBytes'])
            require(use['logicalBytes'] + image['logicalBytes'] + limits['attemptReservationBytes'] <= limits['maxRetainedBytes'] and
                    use['files'] + image['files'] <= limits['maxFilesPerAttempt'] * limits['maxArchives'],
                    'QUALIFICATION_RETENTION_FULL')
            identifier = uuid.uuid4().hex
            record = {'attemptId': identifier, 'state': 'admitted', 'requestDigest': request_digest(request),
                'lease': None, 'pid': None, 'reason': None, 'archive': None, 'history': ['admitted']}
            self.db.execute('INSERT INTO qs_attempts VALUES(?,?,?,?,?,?,?,NULL,1)',
                (identifier, *run_key(request), canonical(request), request_digest(request), canonical(record)))
            return self._row(identifier), True

    def _change(self, row, state, **changes):
        record = row['record']
        require(state in TRANSITIONS[record['state']], 'QUALIFICATION_PHASE_CONFLICT')
        record.update(changes); record['state'] = state; record['history'].append(state)
        self.db.execute('UPDATE qs_attempts SET record=?,active=? WHERE id=?',
            (canonical(record), 0 if state == 'archived' else 1, record['attemptId']))
        return self._row(record['attemptId'])

    def change(self, identifier, state, **changes):
        with self.transaction(): return self._change(self._row(identifier), state, **changes)

    def archive(self, identifier, archive, result):
        require(result is None or type(result) is bytes and len(result) <= 65536)
        with self.transaction():
            row = self._row(identifier)
            require(row['record']['state'] != 'archived', 'QUALIFICATION_PHASE_CONFLICT')
            archive = document(canonical(archive)); archive['returnDigest'] = digest(result) if result is not None else None
            self.db.execute('UPDATE qs_attempts SET return_bytes=? WHERE id=?', (result, identifier))
            return self._change(row, 'archived', archive=archive)
