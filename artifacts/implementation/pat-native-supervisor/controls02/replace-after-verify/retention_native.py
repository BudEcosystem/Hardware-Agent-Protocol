"""Pinned Linux/CPython retention profile; no caller-selected native code."""
import fcntl
import hashlib
import importlib.machinery
import importlib.util
import os
from pathlib import Path, PosixPath, PurePosixPath
import stat
import sys
import sysconfig
import threading

PROFILE = 'hms.retention.linux-cpython312-x86_64/1'
BINARY = Path(__file__).with_name('retention_scan.so')
BINARY_SHA256 = 'ce475ab2a70fb94e84d5d2f2f4c22cb8858d3305005bd154ebda996aae0774ff'
MAX_BINARY_BYTES = 65536
MODULE_NAME = '_hms_retention_native_v1'
MFD_EXEC = 0x0010  # Linux UAPI; explicit executable image, never override kernel policy.
_LOCK = threading.RLock()
_ATTEMPTED = False
_NATIVE = None
_IMAGE_FD = None
_IMAGE_RECORD = None

class NativeRetentionError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

def _require(value, code='QUALIFICATION_NATIVE_UNAVAILABLE'):
    if not value:
        raise NativeRetentionError(code)

def _read_binary():
    fd = os.open(BINARY, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 < info.st_size <= MAX_BINARY_BYTES)
        body = bytearray()
        while len(body) <= info.st_size:
            chunk = os.read(fd, min(65536, info.st_size + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
        after = os.fstat(fd)
        _require(len(body) == info.st_size and all(getattr(info, key) == getattr(after, key)
            for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')))
        _require(hashlib.sha256(body).hexdigest() == BINARY_SHA256, 'QUALIFICATION_IMPLEMENTATION_CHANGED')
        return bytes(body)
    finally:
        os.close(fd)

def _load():
    global _ATTEMPTED, _NATIVE, _IMAGE_FD, _IMAGE_RECORD
    with _LOCK:
        if _NATIVE is not None:
            return _NATIVE
        _require(not _ATTEMPTED)
        _ATTEMPTED = True  # A failed load is unavailable until a fresh process.
        _require(sys.platform == 'linux' and sys.implementation.name == 'cpython'
            and sys.version_info[:2] == (3, 12) and os.uname().machine == 'x86_64'
            and sysconfig.get_config_var('SOABI') == 'cpython-312-x86_64-linux-gnu')
        _require(MODULE_NAME not in sys.modules)
        sys.audit('hms.retention.load.v1', str(BINARY), BINARY_SHA256, PROFILE)
        body = _read_binary()
        fd = None
        try:
            fd = os.memfd_create('hms-retention-' + BINARY_SHA256,
                                 os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING | MFD_EXEC)
            view = memoryview(body)
            while view:
                amount = os.write(fd, view)
                _require(amount > 0)
                view = view[amount:]
            seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SEAL
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
            _require(fcntl.fcntl(fd, fcntl.F_GET_SEALS) & seals == seals)
            info = os.fstat(fd)
            _require(info.st_size == len(body) and info.st_nlink == 0 and not os.get_inheritable(fd))
            # Verify the sealed bytes, not just the disk input or write count.
            sealed = os.pread(fd, len(body) + 1, 0)
            _require(len(sealed) == len(body) and hashlib.sha256(sealed).hexdigest() == BINARY_SHA256)
            origin = '/proc/self/fd/' + str(fd)
            sys.audit('hms.retention.image.v1', origin, BINARY_SHA256, info.st_dev, info.st_ino, seals)
            # Keep the descriptor for process lifetime, even if dynamic loading fails.
            # This bounded one-image ownership prevents reuse of the loader cache path.
            _IMAGE_FD = fd
            fd = None
            _IMAGE_RECORD = dict(origin=origin, sha256=BINARY_SHA256, device=info.st_dev,
                                 inode=info.st_ino, bytes=len(body), seals=seals, profile=PROFILE)
            loader = importlib.machinery.ExtensionFileLoader(MODULE_NAME, origin)
            spec = importlib.util.spec_from_file_location(MODULE_NAME, origin, loader=loader)
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)
            _require(module.ABI_VERSION == 1 and module.__spec__.origin == origin
                     and callable(module.scan))
            sys.modules[MODULE_NAME] = module
            _NATIVE = module
            return module
        finally:
            if fd is not None:
                os.close(fd)

def scan_usage(path, *, max_files, max_bytes):
    """Strict supervisor profile. No weak fallback; OS failures name the scan root."""
    if type(path) not in (str, bytes, PosixPath, PurePosixPath):
        raise TypeError('retention path must be str, bytes or an exact POSIX Path')
    encoded = os.fsencode(path)
    if not 1 <= len(encoded) <= 4095 or b'\0' in encoded:
        raise ValueError('invalid retention path')
    for value, maximum in ((max_files, 262144), (max_bytes, 268435456)):
        if type(value) is not int:
            raise TypeError('retention limits must be exact integers')
        if not 0 <= value <= maximum:
            raise ValueError('retention limit outside native profile')
    result = _load().scan(encoded, max_files, max_bytes)
    if result['reason'] == 'OS_ERROR':
        error = OSError(result['errno'], os.strerror(result['errno']), os.fspath(path))
        if result['cleanupErrno']:
            error.add_note('retention cleanup errno: ' + str(result['cleanupErrno']))
        raise error
    if result['reason'] != 'OK':
        error = NativeRetentionError(result['reason'])
        if result['cleanupErrno']:
            error.add_note('retention cleanup errno: ' + str(result['cleanupErrno']))
        raise error
    return dict(files=result['files'], logicalBytes=result['logicalBytes'], totalDiskQuotaEnforced=False)
