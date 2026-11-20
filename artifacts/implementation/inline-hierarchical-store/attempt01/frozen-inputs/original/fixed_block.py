"""Original fixed block-image prototype; no filesystem or public HMS service."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading

import mount_identity

PROFILE = 'hms.block-image.linux-ext4.statx-mount/0.1'
CHUNK_BYTES = 16 * 1024 * 1024
BLOCK_BYTES = 4096
PROGRAM_BYTES = 16
MAX_CHUNKS = 8
_FLAGS = os.O_CLOEXEC | os.O_NOFOLLOW


class ImageError(RuntimeError):
    pass


def _identity(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{32}', value) is None:
        raise ImageError('INVALID_IDENTITY')
    return value


def _geometry(count):
    if type(count) is not int or not 1 <= count <= MAX_CHUNKS:
        raise ImageError('INVALID_GEOMETRY')


def _manifest(identity, count):
    _identity(identity)
    _geometry(count)
    return (json.dumps({'profile': PROFILE, 'identity': identity,
        'chunks': count, 'chunkBytes': CHUNK_BYTES, 'blockBytes': BLOCK_BYTES,
        'programBytes': PROGRAM_BYTES}, sort_keys=True, separators=(',', ':')) + '\n').encode()


def _path(path):
    value = Path(path).absolute()
    if value != value.resolve(strict=True):
        raise ImageError('ALIASED_PATH')
    return value


def _private(info, directory=False):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    mode = 0o700 if directory else 0o600
    if (not kind(info.st_mode) or info.st_uid != os.getuid() or
            stat.S_IMODE(info.st_mode) != mode or
            (not directory and info.st_nlink != 1)):
        raise ImageError('UNSUPPORTED_OWNERSHIP')


def _host(path, fd):
    try:
        return mount_identity.admit(path, fd)
    except mount_identity.MountError as error:
        raise ImageError(str(error)) from error


def _host_current(path, fd, pin):
    try:
        mount_identity.verify(path, fd, pin)
    except mount_identity.MountError as error:
        raise ImageError(str(error)) from error


def _write_all(fd, data, offset):
    view = memoryview(data)
    done = 0
    while done < len(view):
        amount = os.pwrite(fd, view[done:], offset + done)
        if not 0 < amount <= len(view) - done:
            raise ImageError('WRITE_NO_PROGRESS')
        done += amount


def _read_all(fd, size, offset):
    output = bytearray()
    while len(output) < size:
        part = os.pread(fd, size - len(output), offset + len(output))
        if not part or len(part) > size - len(output):
            raise ImageError('SHORT_READ')
        output.extend(part)
    return bytes(output)


def create_image(path, identity, chunks):
    """Explicit fresh creation. Any failure retains the partial directory."""
    document = _manifest(identity, chunks)
    path = Path(path).absolute()
    parent = _path(path.parent)
    parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | _FLAGS)
    root_fd = owner_fd = None
    try:
        _host(parent, parent_fd)
        os.mkdir(path.name, 0o700, dir_fd=parent_fd)
        root_fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | _FLAGS, dir_fd=parent_fd)
        _private(os.fstat(root_fd), True)
        owner_fd = os.open('owner', os.O_RDWR | os.O_CREAT | os.O_EXCL | _FLAGS, 0o600, dir_fd=root_fd)
        _private(os.fstat(owner_fd))
        fcntl.flock(owner_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _write_all(owner_fd, (identity + '\n').encode(), 0)
        os.fsync(owner_fd)
        fill = b'\xff' * (1024 * 1024)
        files = []
        for number in range(chunks):
            name = f'chunk-{number:02d}'
            fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | _FLAGS, 0o600, dir_fd=root_fd)
            try:
                os.posix_fallocate(fd, 0, CHUNK_BYTES)
                for offset in range(0, CHUNK_BYTES, len(fill)):
                    _write_all(fd, fill, offset)
                os.fsync(fd)
                info = os.fstat(fd)
                _private(info)
                if info.st_size != CHUNK_BYTES or info.st_blocks * 512 < CHUNK_BYTES:
                    raise ImageError('INCOMPLETE_ALLOCATION')
                files.append({'name': name, 'bytes': info.st_size,
                              'allocatedBytes': info.st_blocks * 512})
            finally:
                os.close(fd)
        fd = os.open('manifest', os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FLAGS, 0o600, dir_fd=root_fd)
        try:
            _private(os.fstat(fd))
            _write_all(fd, document, 0)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(root_fd)
        os.fsync(parent_fd)
        objects = {}
        for name in ['.', 'owner', 'manifest'] + [f'chunk-{i:02d}' for i in range(chunks)]:
            info = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            objects[name] = [info.st_dev, info.st_ino]
        return {'identity': identity, 'capacityBytes': chunks * CHUNK_BYTES,
                'files': files, 'manifestSha256': hashlib.sha256(document).hexdigest(),
                'objects': objects}
    finally:
        for fd in [owner_fd, root_fd, parent_fd]:
            if fd is not None:
                os.close(fd)


class FixedBlockImage:
    """Exclusive trusted-host access; ranges are bounded before positional I/O.

    This layer has no transaction, deletion, truncation or implicit formatting.
    Raw payload integrity belongs to the filesystem using the block interface.
    """
    def __init__(self, path, identity, chunks, *, expected_objects):
        self._document = _manifest(identity, chunks)
        names = ['owner', 'manifest'] + [f'chunk-{i:02d}' for i in range(chunks)]
        if (type(expected_objects) is not dict or set(expected_objects) != {'.', *names} or
                any(type(v) not in (list, tuple) or len(v) != 2 or
                    any(type(x) is not int or not 0 <= x < 2**64 for x in v)
                    for v in expected_objects.values())):
            raise ImageError('INVALID_OBJECT_ANCHOR')
        self._objects = {name: tuple(value) for name, value in expected_objects.items()}
        self._identity = identity
        self._count = chunks
        self._capacity = chunks * CHUNK_BYTES
        self._path = _path(path)
        self._mutex = threading.RLock()
        self._root = None
        self._fds = {}
        self._pins = {}
        self._closed = False
        self._poisoned = False
        self._pid = os.getpid()
        try:
            self._root = os.open(self._path, os.O_RDONLY | os.O_DIRECTORY | _FLAGS)
            _private(os.fstat(self._root), True)
            self._root_pin = (os.fstat(self._root).st_dev, os.fstat(self._root).st_ino)
            if self._root_pin != self._objects['.']:
                raise ImageError('DIRECTORY_REPLACED')
            self._host_pin = _host(self._path, self._root)
            for name in names:
                prior = os.stat(name, dir_fd=self._root, follow_symlinks=False)
                _private(prior)
                fd = os.open(name, (os.O_RDONLY if name == 'manifest' else os.O_RDWR) | _FLAGS | os.O_NONBLOCK,
                             dir_fd=self._root)
                self._fds[name] = fd
                info = os.fstat(fd)
                _private(info)
                if self._pin(prior) != self._pin(info):
                    raise ImageError('FILE_CHANGED_DURING_OPEN')
                if (info.st_dev, info.st_ino) != self._objects[name]:
                    raise ImageError('OBJECT_REPLACED')
                expected_size = (33 if name == 'owner' else len(self._document) if name == 'manifest' else CHUNK_BYTES)
                if info.st_size != expected_size or info.st_blocks * 512 < expected_size:
                    raise ImageError('INVALID_FILE_ALLOCATION')
                self._pins[name] = self._pin(info)
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if _read_all(self._fds['owner'], 33, 0) != (identity + '\n').encode():
                raise ImageError('IDENTITY_MISMATCH')
            if _read_all(self._fds['manifest'], len(self._document), 0) != self._document:
                raise ImageError('MANIFEST_MISMATCH')
            self._verify()
        except BaseException:
            self.close()
            raise

    @property
    def block_count(self):
        return self._capacity // BLOCK_BYTES

    @staticmethod
    def _pin(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_blocks,
                info.st_uid, info.st_gid, info.st_mode, info.st_nlink)

    def _verify(self):
        if self._closed:
            raise ImageError('CLOSED')
        if self._poisoned:
            raise ImageError('POISONED')
        if os.getpid() != self._pid:
            raise ImageError('FORKED_HANDLE')
        _private(os.fstat(self._root), True)
        named = os.stat(self._path, follow_symlinks=False)
        _private(named, True)
        if (named.st_dev, named.st_ino) != self._root_pin:
            raise ImageError('DIRECTORY_REPLACED')
        _host_current(self._path, self._root, self._host_pin)
        if set(os.listdir(self._root)) != set(self._fds):
            raise ImageError('INVENTORY_CHANGED')
        for name, fd in self._fds.items():
            if (self._pin(os.fstat(fd)) != self._pins[name] or
                    self._pin(os.stat(name, dir_fd=self._root, follow_symlinks=False)) != self._pins[name]):
                raise ImageError('FILE_CHANGED')
        if (_read_all(self._fds['manifest'], len(self._document), 0) != self._document or
                _read_all(self._fds['owner'], 33, 0) != (self._identity + '\n').encode()):
            raise ImageError('METADATA_CHANGED')

    def _range(self, block, offset, size):
        if (any(type(x) is not int for x in [block, offset, size]) or
                not 0 <= block < self.block_count or not 0 <= offset <= BLOCK_BYTES or
                not 0 <= size <= BLOCK_BYTES - offset or
                offset % PROGRAM_BYTES or size % PROGRAM_BYTES):
            raise ImageError('INVALID_RANGE')
        absolute = block * BLOCK_BYTES + offset
        return absolute // CHUNK_BYTES, absolute % CHUNK_BYTES

    def _perform(self, action):
        if os.getpid() != self._pid:
            raise ImageError('FORKED_HANDLE')
        with self._mutex:
            try:
                self._verify()
                return action()
            except BaseException:
                self._poisoned = True
                raise

    def read(self, block, offset, size):
        number, position = self._range(block, offset, size)
        return self._perform(lambda: _read_all(self._fds[f'chunk-{number:02d}'], size, position) if size else b'')

    def write(self, block, offset, data):
        if type(data) is not bytes:
            raise ImageError('INVALID_DATA')
        number, position = self._range(block, offset, len(data))
        return self._perform(lambda: _write_all(self._fds[f'chunk-{number:02d}'], data, position) if data else None)

    def erase(self, block):
        return self.write(block, 0, b'\xff' * BLOCK_BYTES)

    def sync(self):
        def flush():
            for number in range(self._count):
                os.fsync(self._fds[f'chunk-{number:02d}'])
        return self._perform(flush)

    def close(self):
        if os.getpid() != self._pid:
            raise ImageError('FORKED_HANDLE')
        with self._mutex:
            if self._closed:
                return
            self._closed = True
            errors = []
            for fd in [*reversed(self._fds.values()), self._root]:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError as error:
                        errors.append(error)
            self._fds.clear()
            self._root = None
            if errors:
                raise errors[0]

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()
