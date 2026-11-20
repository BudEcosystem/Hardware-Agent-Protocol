"""Original single-owner research adapter; not a POSIX filesystem or SQLite VFS."""
from __future__ import annotations
import ctypes as C
import base64
from functools import wraps
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import threading

PROFILE = 'hms.chunk-store/0.1'
CHUNK = 4096
MAX_FILE = 16 * 1024 * 1024
MAX_INODES = 16
MAX_HANDLES = 64
MAX_TRANSFER = 65536
INTERNAL_MAX = 16384
MAP_BYTES = MAX_FILE//CHUNK//8


class Reject(ValueError):
    """Invalid request refused before filesystem mutation."""


class StorageError(RuntimeError):
    pass


class NativeError(StorageError):
    def __init__(self, code):
        self.code = code
        super().__init__(f'LITTLEFS_{code}')


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def _name(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}', value) is None:
        raise Reject('INVALID_NAME')
    return value


def _integer(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise Reject('INVALID_RANGE')
    return value


def _guard(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        if os.getpid() != self.pid:
            raise StorageError('FORKED_OWNER')
        with self.lock:
            self._check()
            try:
                return method(self, *args, **kwargs)
            except Reject:
                raise
            except BaseException:
                self.poisoned = True
                raise
    return call


def _block_module(path, expected):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise StorageError('BLOCK_SOURCE_CHANGED')
    spec = importlib.util.spec_from_file_location('hms_chunk_fixed_block', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Native:
    class Entry(C.Structure):
        _fields_ = [('name', C.c_char*64), ('type', C.c_uint32), ('size', C.c_uint32)]

    READ = C.CFUNCTYPE(C.c_int, C.c_uint32, C.c_uint32, C.c_void_p, C.c_uint32)
    PROG = C.CFUNCTYPE(C.c_int, C.c_uint32, C.c_uint32, C.c_void_p, C.c_uint32)
    ERASE = C.CFUNCTYPE(C.c_int, C.c_uint32)
    SYNC = C.CFUNCTYPE(C.c_int)

    def __init__(self, image, library, expected_hash):
        if C.sizeof(self.Entry) != 72:
            raise StorageError('UNSUPPORTED_ENTRY_ABI')
        if hashlib.sha256(Path(library).read_bytes()).hexdigest() != expected_hash:
            raise StorageError('NATIVE_IDENTITY_CHANGED')
        self.image = image
        self.counts = dict(readCalls=0, readBytes=0, programCalls=0, programBytes=0, erases=0, syncs=0)
        self.fault = None
        self.inject = None
        self.lib = C.CDLL(str(Path(library).resolve()))
        signatures = {
            'hm_new': ([self.READ, self.PROG, self.ERASE, self.SYNC, C.c_uint32], C.c_void_p),
            'hm_free': ([C.c_void_p], None),
            'hm_format': ([C.c_void_p], C.c_int), 'hm_mount': ([C.c_void_p], C.c_int),
            'hm_stat': ([C.c_void_p, C.c_char_p, C.POINTER(C.c_uint32), C.POINTER(C.c_uint32)], C.c_int),
            'hm_list': ([C.c_void_p, C.c_char_p, C.c_void_p, C.c_uint32], C.c_int),
            'hm_entries': ([C.c_void_p, C.c_char_p, C.c_void_p, C.c_uint32], C.c_int),
            'hm_read': ([C.c_void_p, C.c_char_p, C.c_void_p, C.c_uint32], C.c_int),
            'hm_write': ([C.c_void_p, C.c_char_p, C.c_void_p, C.c_uint32], C.c_int),
            'hm_mkdir': ([C.c_void_p, C.c_char_p], C.c_int),
            'hm_remove': ([C.c_void_p, C.c_char_p], C.c_int),
            'hm_rename': ([C.c_void_p, C.c_char_p, C.c_char_p], C.c_int),
            'hm_sync': ([C.c_void_p], C.c_int), 'hm_used': ([C.c_void_p], C.c_int)}
        for name, (args, result) in signatures.items():
            func = getattr(self.lib, name)
            func.argtypes, func.restype = args, result

        def wrap(kind, action):
            def callback(*args):
                try:
                    if self.fault is not None:
                        return -5
                    if self.inject is not None:
                        self.inject(kind)
                    action(*args)
                    return 0
                except BaseException as exc:
                    self.fault = f'{type(exc).__name__}: {exc}'
                    return -5
            return callback

        def read(block, off, buf, size):
            data = image.read(block, off, size)
            C.memmove(buf, data, size)
            self.counts['readCalls'] += 1
            self.counts['readBytes'] += size

        def prog(block, off, buf, size):
            image.write(block, off, C.string_at(buf, size))
            self.counts['programCalls'] += 1
            self.counts['programBytes'] += size

        def erase(block):
            image.erase(block)
            self.counts['erases'] += 1

        def sync():
            image.sync()
            self.counts['syncs'] += 1

        self.callbacks = (self.READ(wrap('read', read)), self.PROG(wrap('program', prog)),
                          self.ERASE(wrap('erase', erase)), self.SYNC(wrap('sync', sync)))
        self.ptr = self.lib.hm_new(*self.callbacks, image.block_count)
        if not self.ptr:
            raise StorageError('NATIVE_ALLOCATION')

    def call(self, name, *args, missing=False):
        value = getattr(self.lib, name)(self.ptr, *args)
        if value == -2 and missing:
            return None
        if value < 0:
            raise NativeError(value)
        return value

    def stat(self, path):
        kind, size = C.c_uint32(), C.c_uint32()
        if self.call('hm_stat', path.encode(), C.byref(kind), C.byref(size), missing=True) is None:
            return None
        return kind.value, size.value

    def list(self, path, capacity):
        output = C.create_string_buffer(capacity * 64)
        count = self.call('hm_list', path.encode(), output, capacity)
        return [output.raw[i*64:(i+1)*64].split(b'\0', 1)[0].decode('ascii') for i in range(count)]

    def read(self, path, missing=False):
        output = C.create_string_buffer(INTERNAL_MAX)
        size = self.call('hm_read', path.encode(), output, INTERNAL_MAX, missing=missing)
        return None if size is None else output.raw[:size]

    def entries(self, path, capacity):
        _integer(capacity, MAX_FILE//CHUNK)
        output = (self.Entry*capacity)()
        count = self.call('hm_entries', path.encode(), output, capacity)
        return [(output[i].name.decode('ascii'), output[i].type, output[i].size) for i in range(count)]

    def write(self, path, data):
        if type(data) is not bytes or len(data) > INTERNAL_MAX:
            raise StorageError('INTERNAL_FILE_BOUND')
        self.call('hm_write', path.encode(), data, len(data))

    def remove(self, path):
        self.call('hm_remove', path.encode())

    def dispose(self):
        if self.ptr:
            self.lib.hm_free(self.ptr)
            self.ptr = None


class ChunkStore:
    BLOCK_HASH = 'b5173152c5505934275b89a4c1c2e54f4bd4fa75b9a60b8e7f149bd3456b42db'

    @classmethod
    def create(cls, path, identity, *, block_source, library, library_hash):
        module = _block_module(Path(block_source), cls.BLOCK_HASH)
        anchor = module.create_image(path, identity, 1)
        return cls(path, anchor, module, library, library_hash, fresh=True)

    @classmethod
    def reopen(cls, path, anchor, *, block_source, library, library_hash):
        module = _block_module(Path(block_source), cls.BLOCK_HASH)
        return cls(path, anchor, module, library, library_hash, fresh=False)

    def __init__(self, path, anchor, module, library, library_hash, *, fresh):
        self.pid = os.getpid()
        self.lock = threading.RLock()
        self.closed = self.poisoned = False
        self.handles = {}
        self.session = secrets.token_hex(16)
        self.next_handle = 1
        self.anchor = anchor
        self.image = module.FixedBlockImage(path, anchor['identity'], 1, expected_objects=anchor['objects'])
        self.native = None
        try:
            self.native = Native(self.image, library, library_hash)
            if fresh:
                self.native.call('hm_format')
            self.native.call('hm_mount')
            if fresh:
                self.body = {'profile': PROFILE, 'identity': anchor['identity'], 'next': 1, 'inodes': []}
                self._save()
            else:
                self._load()
                self._recover()
        except BaseException:
            self.dispose()
            raise

    def _check(self):
        if self.closed or self.poisoned:
            raise StorageError('CLOSED' if self.closed else 'POISONED')

    def _encoded(self):
        return _canonical({'body': self.body, 'sha256': hashlib.sha256(_canonical(self.body)).hexdigest()})

    def _save(self):
        data = self._encoded()
        if len(data) > INTERNAL_MAX:
            raise StorageError('NAMESPACE_BOUND')
        self.native.write('state.tmp', data)
        self.native.call('hm_rename', b'state.tmp', b'state')

    def _load(self):
        raw = self.native.read('state')
        try:
            document = json.loads(raw)
            self.body = document['body']
            body = self.body
            if raw != self._encoded() or set(document) != {'body', 'sha256'}:
                raise ValueError('noncanonical or checksum mismatch')
            if set(body) != {'profile', 'identity', 'next', 'inodes'} or body['profile'] != PROFILE or body['identity'] != self.anchor['identity']:
                raise ValueError('profile or identity')
            if type(body['next']) is not int or not 1 <= body['next'] < 2**64:
                raise ValueError('next identity')
            records = body['inodes']
            if type(records) is not list or len(records) > MAX_INODES:
                raise ValueError('inode bounds')
            ids, names = set(), set()
            for inode in records:
                if type(inode) is not dict or set(inode) != {'id', 'name', 'size', 'chunks'}:
                    raise ValueError('inode shape')
                if type(inode['id']) is not int or not 1 <= inode['id'] < body['next'] or inode['id'] in ids:
                    raise ValueError('inode identity')
                ids.add(inode['id'])
                _integer(inode['size'], MAX_FILE)
                bitmap = self._bitmap(inode)
                if any(n*CHUNK >= inode['size'] for n in range(MAX_FILE//CHUNK) if bitmap[n//8] & (1 << (n%8))):
                    raise ValueError('chunk outside file')
                if inode['name'] is not None:
                    _name(inode['name'])
                    if inode['name'] in names:
                        raise ValueError('duplicate name')
                    names.add(inode['name'])
        except (ValueError, TypeError, KeyError) as exc:
            raise StorageError('INVALID_NAMESPACE') from exc

    @staticmethod
    def _directory(inode_id):
        return f'i{inode_id:016x}'

    def _path(self, inode, number):
        return f'{self._directory(inode["id"])}/c{number:08x}'

    @staticmethod
    def _bitmap(inode):
        value = inode['chunks']
        if type(value) is not str:
            raise StorageError('INVALID_CHUNK_MAP')
        try:
            raw = base64.b64decode(value, validate=True)
        except ValueError as exc:
            raise StorageError('INVALID_CHUNK_MAP') from exc
        if len(raw) != MAP_BYTES or base64.b64encode(raw).decode('ascii') != value:
            raise StorageError('INVALID_CHUNK_MAP')
        return raw

    def _present(self, inode):
        bitmap = self._bitmap(inode)
        return {n for n in range(MAX_FILE//CHUNK) if bitmap[n//8] & (1 << (n%8))}

    def _inventory(self):
        root_entries = self.native.entries('/', MAX_INODES+2)
        entries = [name for name, unused_type, unused_size in root_entries]
        if 'state' not in entries:
            raise StorageError('MISSING_NAMESPACE')
        known = {r['id']: r for r in self.body['inodes']}
        present = {identity: self._present(inode) for identity, inode in known.items()}
        directories = {}
        for entry, kind, size in root_entries:
            info = (kind, size)
            if entry in {'state', 'state.tmp'}:
                if info is None or info[0] != 1 or info[1] > INTERNAL_MAX:
                    raise StorageError('INVALID_METADATA_OBJECT')
                continue
            if re.fullmatch('i[0-9a-f]{16}', entry) is None or info != (2, 0):
                raise StorageError('UNKNOWN_ROOT_OBJECT')
            identity = int(entry[1:], 16)
            if not identity or identity > self.body['next']:
                raise StorageError('INVALID_INODE_DIRECTORY')
            chunks = self.native.entries(entry, MAX_FILE//CHUNK)
            numbers = []
            for chunk, kind, size in chunks:
                if re.fullmatch('c[0-9a-f]{8}', chunk) is None:
                    raise StorageError('UNKNOWN_CHUNK')
                number = int(chunk[1:], 16)
                stat = (kind, size)
                if number >= MAX_FILE//CHUNK or stat is None or stat[0] != 1 or not 0 <= stat[1] <= CHUNK:
                    raise StorageError('INVALID_CHUNK')
                inode = known.get(identity)
                if inode is not None and number in present[identity] and stat[1] != CHUNK:
                    raise StorageError('INCOMPLETE_LIVE_CHUNK')
                numbers.append(number)
            directories[identity] = numbers
            if identity in known and not present[identity] <= set(numbers):
                raise StorageError('MISSING_REFERENCED_CHUNK')
        if not set(known) <= set(directories):
            raise StorageError('MISSING_INODE_DIRECTORY')
        return entries, directories

    def _recover(self):
        # Full validation precedes the first recovery write.
        entries, directories = self._inventory()
        if 'state.tmp' in entries:
            self.native.remove('state.tmp')
        if any(r['name'] is None for r in self.body['inodes']):
            self.body['inodes'] = [r for r in self.body['inodes'] if r['name'] is not None]
            self._save()
        live = {r['id']: r for r in self.body['inodes']}
        for identity, numbers in directories.items():
            inode = live.get(identity)
            present = self._present(inode) if inode is not None else set()
            for number in numbers:
                if number not in present:
                    self.native.remove(f'{self._directory(identity)}/c{number:08x}')
            if inode is None:
                self.native.remove(self._directory(identity))

    def _lookup(self, name):
        for inode in self.body['inodes']:
            if inode['name'] == name:
                return inode
        raise Reject('NOT_FOUND')

    def _fd(self, handle, writable=False):
        if (type(handle) is not tuple or len(handle) != 2 or type(handle[0]) is not str
                or type(handle[1]) is not int or handle not in self.handles):
            raise Reject('BAD_HANDLE')
        identity, can_write = self.handles[handle]
        if writable and not can_write:
            raise Reject('READ_ONLY')
        return next(r for r in self.body['inodes'] if r['id'] == identity)

    def _referenced(self, inode):
        return any(identity == inode['id'] for identity, unused in self.handles.values())

    def _drop(self, inode):
        self.body['inodes'].remove(inode)
        self._save()
        directory = self._directory(inode['id'])
        for chunk in self.native.list(directory, MAX_FILE//CHUNK):
            self.native.remove(f'{directory}/{chunk}')
        self.native.remove(directory)

    def _chunk(self, inode, number):
        bitmap = self._bitmap(inode)
        if not bitmap[number//8] & (1 << (number%8)):
            return b'\0'*CHUNK
        raw = self.native.read(self._path(inode, number))
        if len(raw) != CHUNK:
            raise StorageError('INCOMPLETE_CHUNK')
        valid = max(0, min(CHUNK, inode['size']-number*CHUNK))
        return raw[:valid] + b'\0'*(CHUNK-valid)

    def _zero_tail(self, inode):
        size = inode['size']
        if size % CHUNK and size//CHUNK in self._present(inode):
            path = self._path(inode, size//CHUNK)
            raw = self.native.read(path)
            if raw is not None:
                if len(raw) != CHUNK:
                    raise StorageError('INCOMPLETE_CHUNK')
                clean = raw[:size % CHUNK] + b'\0'*(CHUNK-size % CHUNK)
                if raw != clean:
                    self.native.write(path, clean)

    @_guard
    def open(self, name, *, create=False, exclusive=False, writable=True):
        name = _name(name)
        if any(type(x) is not bool for x in [create, exclusive, writable]):
            raise Reject('INVALID_FLAGS')
        if len(self.handles) >= MAX_HANDLES or self.next_handle >= 2**64:
            raise Reject('HANDLE_LIMIT')
        inode = next((r for r in self.body['inodes'] if r['name'] == name), None)
        if inode is not None and create and exclusive:
            raise Reject('EXISTS')
        if inode is None:
            if not create:
                raise Reject('NOT_FOUND')
            if len(self.body['inodes']) >= MAX_INODES or self.body['next'] >= 2**64-1:
                raise Reject('INODE_LIMIT')
            inode = {'id': self.body['next'], 'name': name, 'size': 0,
                     'chunks': base64.b64encode(b'\0'*MAP_BYTES).decode('ascii')}
            self.native.call('hm_mkdir', self._directory(inode['id']).encode())
            self.body['next'] += 1
            self.body['inodes'].append(inode)
            self._save()
        handle = (self.session, self.next_handle)
        self.next_handle += 1
        self.handles[handle] = (inode['id'], writable)
        return handle

    @_guard
    def info(self, handle):
        return dict(self._fd(handle))

    @_guard
    def pread(self, handle, size, offset):
        inode = self._fd(handle)
        _integer(size, MAX_TRANSFER)
        _integer(offset, MAX_FILE)
        stop = min(inode['size'], offset+size)
        out = bytearray()
        while offset < stop:
            number, within = divmod(offset, CHUNK)
            amount = min(stop-offset, CHUNK-within)
            out += self._chunk(inode, number)[within:within+amount]
            offset += amount
        return bytes(out)

    @_guard
    def pwrite(self, handle, data, offset):
        inode = self._fd(handle, True)
        if type(data) is not bytes or len(data) > MAX_TRANSFER:
            raise Reject('INVALID_DATA')
        _integer(offset, MAX_FILE)
        if offset+len(data) > MAX_FILE:
            raise Reject('FILE_LIMIT')
        if not data:
            return 0
        stop = offset+len(data)
        if stop > inode['size']:
            self._zero_tail(inode)
        done = 0
        bitmap = bytearray(self._bitmap(inode))
        prior_map = bytes(bitmap)
        while done < len(data):
            number, within = divmod(offset+done, CHUNK)
            amount = min(len(data)-done, CHUNK-within)
            chunk = bytearray(self._chunk(inode, number))
            chunk[within:within+amount] = data[done:done+amount]
            self.native.write(self._path(inode, number), bytes(chunk))
            bitmap[number//8] |= 1 << (number%8)
            done += amount
        if stop > inode['size'] or bytes(bitmap) != prior_map:
            inode['size'] = max(inode['size'], stop)
            inode['chunks'] = base64.b64encode(bitmap).decode('ascii')
            self._save()
        return len(data)

    @_guard
    def truncate(self, handle, size):
        inode = self._fd(handle, True)
        _integer(size, MAX_FILE)
        old = inode['size']
        if old == size:
            return
        if size > old:
            self._zero_tail(inode)
        inode['size'] = size
        if size < old:
            bitmap = bytearray(self._bitmap(inode))
            for number in range((size+CHUNK-1)//CHUNK, MAX_FILE//CHUNK):
                bitmap[number//8] &= ~(1 << (number%8))
            inode['chunks'] = base64.b64encode(bitmap).decode('ascii')
        self._save()
        if size < old:
            directory = self._directory(inode['id'])
            for name in self.native.list(directory, MAX_FILE//CHUNK):
                if int(name[1:], 16)*CHUNK >= size:
                    self.native.remove(f'{directory}/{name}')

    @_guard
    def unlink(self, name):
        inode = self._lookup(_name(name))
        inode['name'] = None
        self._save()
        if not self._referenced(inode):
            self._drop(inode)

    @_guard
    def rename(self, source, target):
        inode = self._lookup(_name(source))
        target = _name(target)
        if source == target:
            return
        prior = next((r for r in self.body['inodes'] if r['name'] == target), None)
        if prior is not None:
            prior['name'] = None
        inode['name'] = target
        self._save()
        if prior is not None and not self._referenced(prior):
            self._drop(prior)

    @_guard
    def close_handle(self, handle):
        inode = self._fd(handle)
        del self.handles[handle]
        if inode['name'] is None and not self._referenced(inode):
            self._drop(inode)

    @_guard
    def sync(self):
        self.native.call('hm_sync')

    @_guard
    def accounting(self):
        return {'uniqueReachableBlocks': self.native.call('hm_used'),
                'blockBytes': CHUNK, 'backingBytes': self.image.block_count*CHUNK,
                'logicalBytes': sum(r['size'] for r in self.body['inodes']),
                'inodes': len(self.body['inodes']), 'handles': len(self.handles),
                'reservedContinuationBytes': 0}

    @_guard
    def close(self):
        if self.handles:
            raise Reject('OPEN_HANDLES')
        self.native.call('hm_sync')
        self.dispose()

    def dispose(self):
        """Release resources without a clean-shutdown receipt; preserve orphan state."""
        if os.getpid() != self.pid:
            raise StorageError('FORKED_OWNER')
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.handles.clear()
            try:
                if self.native is not None:
                    self.native.dispose()
            finally:
                self.image.close()
