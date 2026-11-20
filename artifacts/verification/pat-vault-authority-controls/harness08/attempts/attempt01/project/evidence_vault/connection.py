"""One private owner, independent SQLite connection, and current read leases."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import sqlite3
import stat
import threading
import time

from hms.contracts import canonical
from . import contracts as c


class _Connection:
    def __init__(self, path, expected, create):
        c.require(type(create) is bool, 'OPTIONS')
        c.validate_descriptor(expected)
        c.require(expected['implementationDigest'] == c.identity(), 'IMPLEMENTATION_CHANGED')
        self._descriptor_wire = canonical(expected)
        self._expected = c.document(self._descriptor_wire, c.RECORD_BYTES)
        self._mutex = threading.RLock()
        self._db = None
        self._fds = []
        self._closed = False
        self._poisoned = False
        self._lease = None
        self._path = Path(os.path.abspath(os.fspath(path)))
        c.require(self._path.name not in ('', '.', '..') and len(self._path.name.encode()) <= 128, 'PATH')
        try:
            for component in (self._path.parent, *self._path.parent.parents):
                c.require(not component.is_symlink(), 'PATH')
            self._dir_fd = os.open(self._path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self._fds.append(self._dir_fd)
            info = os.fstat(self._dir_fd)
            c.require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and
                      stat.S_IMODE(info.st_mode) & 0o077 == 0, 'PRIVATE_DIRECTORY_REQUIRED')
            self._dir_identity = (info.st_dev, info.st_ino)
            self._owner_path = Path(str(self._path) + '.owner')
            flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
            self._owner_fd = os.open(self._owner_path, flags | (os.O_CREAT | os.O_EXCL if create else 0), 0o600)
            self._fds.append(self._owner_fd)
            self._owner_identity = self._regular(self._owner_fd, self._owner_path, zero=True)
            try:
                fcntl.flock(self._owner_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise c.VaultError('OWNER_BUSY') from error
            self._file_fd = os.open(self._path, flags | (os.O_CREAT | os.O_EXCL if create else 0), 0o600)
            self._fds.append(self._file_fd)
            self._file_identity = self._regular(self._file_fd, self._path)
            size = os.fstat(self._file_fd).st_size
            c.require(size <= expected['maxPages'] * c.PAGE_SIZE and (create or size >= c.PAGE_SIZE), 'FILE_CAPACITY')
            # This first component does not automatically recover a hot or
            # foreign journal before checking its persisted storage identity.
            c.require(not any(os.path.lexists(str(self._path) + suffix)
                              for suffix in ('-journal', '-wal', '-shm')), 'RECOVERY_REQUIRED')
            uri = self._path.as_uri() + '?mode=rw'
            self._db = sqlite3.connect(uri, uri=True, isolation_level=None,
                                       timeout=0.2, check_same_thread=False)
            if create:
                self._db.execute('PRAGMA page_size=1024')
            c.require(self._scalar('PRAGMA page_size') == c.PAGE_SIZE, 'PAGE_SIZE')
            c.require(self._scalar('PRAGMA journal_mode') == 'delete', 'DURABILITY')
            self._db.execute('PRAGMA synchronous=EXTRA')
            self._db.execute('PRAGMA temp_store=MEMORY')
            self._db.execute('PRAGMA foreign_keys=ON')
            c.require(self._scalar('PRAGMA synchronous') == 3 and self._scalar('PRAGMA foreign_keys') == 1, 'DURABILITY')
            c.require(self._scalar('PRAGMA max_page_count=' + str(expected['maxPages'])) == expected['maxPages'], 'FILE_CAPACITY')
            self._identities()
        except BaseException:
            self.close()
            raise

    def _scalar(self, sql):
        rows = self._db.execute(sql).fetchall()
        c.require(len(rows) == 1 and len(rows[0]) == 1, 'DATABASE')
        return rows[0][0]

    @staticmethod
    def _regular(fd, path, *, zero=False):
        info = os.fstat(fd)
        actual = path.stat(follow_symlinks=False)
        c.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid() and
                  stat.S_IMODE(info.st_mode) & 0o077 == 0 and
                  (actual.st_dev, actual.st_ino) == (info.st_dev, info.st_ino) and
                  stat.S_ISREG(actual.st_mode) and (not zero or info.st_size == 0), 'FILE_IDENTITY')
        return info.st_dev, info.st_ino

    def _identities(self):
        c.require(not self._closed and not self._poisoned, 'UNAVAILABLE')
        info = self._path.parent.stat(follow_symlinks=False)
        c.require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and
                  stat.S_IMODE(info.st_mode) & 0o077 == 0 and
                  (info.st_dev, info.st_ino) == self._dir_identity, 'FILE_IDENTITY')
        c.require(self._regular(self._owner_fd, self._owner_path, zero=True) == self._owner_identity and
                  self._regular(self._file_fd, self._path) == self._file_identity, 'FILE_IDENTITY')
        c.require(os.fstat(self._file_fd).st_size <= self._expected['maxPages'] * c.PAGE_SIZE, 'FILE_CAPACITY')

    def _ready(self):
        self._identities()
        c.require(c.identity() == self._expected['implementationDigest'], 'IMPLEMENTATION_CHANGED')
        c.require(not self._db.in_transaction and self._lease is None, 'TRANSACTION_REENTRY')
        c.require(self._scalar('PRAGMA page_size') == c.PAGE_SIZE and
                  self._scalar('PRAGMA max_page_count') == self._expected['maxPages'], 'FILE_CAPACITY')
        c.require(self._scalar('PRAGMA journal_mode') == 'delete' and
                  self._scalar('PRAGMA synchronous') == 3 and self._scalar('PRAGMA query_only') == 0, 'DURABILITY')

    @contextmanager
    def _transaction(self):
        with self._mutex:
            self._ready()
            self._db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self._identities()
                self._db.execute('COMMIT')
            except BaseException:
                try:
                    if self._db.in_transaction:
                        self._db.execute('ROLLBACK')
                except BaseException:
                    self._poisoned = True
                    raise
                raise

    def close(self):
        with self._mutex:
            c.require(self._lease is None, 'LEASE_ACTIVE')
            if self._closed:
                return
            try:
                if self._db is not None:
                    self._db.close()
            finally:
                for fd in reversed(self._fds):
                    os.close(fd)
                self._fds.clear()
                self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class _Snapshot:
    """Opaque owner-held read transaction; checking it does not perform file I/O."""
    def __init__(self, owner, manifest_wire, files, lifetime_ms):
        self._owner = owner
        self._thread = threading.get_ident()
        self._wire = manifest_wire
        self._files = tuple(sorted(files.items()))
        self._deadline = time.monotonic_ns() + lifetime_ms * 1000000
        self._active = True

    def check(self, owner):
        c.require(owner is self._owner and owner._lease is self and self._active and
                  self._thread == threading.get_ident() and owner._db.in_transaction and
                  time.monotonic_ns() < self._deadline, 'SNAPSHOT_UNAVAILABLE')

    def manifest(self):
        self.check(self._owner)
        return c.document(self._wire, c.RECORD_BYTES)

    def documents(self):
        self.check(self._owner)
        return dict(self._files)
