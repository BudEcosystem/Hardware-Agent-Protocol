"""Bounded UTF-8 directory-entry transport; block callbacks remain exact."""
import ctypes as C
import hashlib
from pathlib import Path
from chunk_store_base import StorageError, NativeError, _integer, INTERNAL_MAX

class Native:
    class Entry(C.Structure):
        _fields_ = [('name', C.c_char*256), ('type', C.c_uint32), ('size', C.c_uint32)]

    READ = C.CFUNCTYPE(C.c_int, C.c_uint32, C.c_uint32, C.c_void_p, C.c_uint32)
    PROG = C.CFUNCTYPE(C.c_int, C.c_uint32, C.c_uint32, C.c_void_p, C.c_uint32)
    ERASE = C.CFUNCTYPE(C.c_int, C.c_uint32)
    SYNC = C.CFUNCTYPE(C.c_int)

    def __init__(self, image, library, expected_hash):
        if C.sizeof(self.Entry) != 264:
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
        output = C.create_string_buffer(capacity * 256)
        count = self.call('hm_list', path.encode(), output, capacity)
        return [output.raw[i*256:(i+1)*256].split(b'\0', 1)[0].decode('utf-8') for i in range(count)]

    def read(self, path, missing=False):
        output = C.create_string_buffer(INTERNAL_MAX)
        size = self.call('hm_read', path.encode(), output, INTERNAL_MAX, missing=missing)
        return None if size is None else output.raw[:size]

    def entries(self, path, capacity):
        _integer(capacity, 8192)
        output = (self.Entry*capacity)()
        count = self.call('hm_entries', path.encode(), output, capacity)
        return [(output[i].name.decode('utf-8'), output[i].type, output[i].size) for i in range(count)]

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
