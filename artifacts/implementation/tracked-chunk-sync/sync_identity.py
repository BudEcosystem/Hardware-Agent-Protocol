"""Private wait/error helper; full fsync remains in the block provider."""
import ctypes
import hashlib
import os
from pathlib import Path
import re


class SyncError(RuntimeError):
    pass


class Probe:
    def __init__(self, library, wanted):
        library = Path(library)
        if (type(wanted) is not str or re.fullmatch('[0-9a-f]{64}', wanted) is None or
                hashlib.sha256(library.read_bytes()).hexdigest() != wanted):
            raise SyncError('SYNC_LIBRARY_IDENTITY')
        self.lib = ctypes.CDLL(str(library))
        self.lib.hm_sync_abi.argtypes = []
        self.lib.hm_sync_abi.restype = ctypes.c_uint
        if self.lib.hm_sync_abi() != 1:
            raise SyncError('SYNC_LIBRARY_ABI')
        self.lib.hm_sync_wait.argtypes = [ctypes.c_int]
        self.lib.hm_sync_wait.restype = ctypes.c_int

    def wait(self, fd):
        if type(fd) is not int or not 0 <= fd < 2**31:
            raise SyncError('INVALID_SYNC_DESCRIPTOR')
        rc = self.lib.hm_sync_wait(fd)
        if rc != 0:
            raise SyncError('SYNC_WAIT_ERRNO_' + str(-rc))


_probe = None


def wait(fd):
    global _probe
    if _probe is None:
        _probe = Probe(os.environ['HMS_SYNC_LIBRARY'], os.environ['HMS_SYNC_LIBRARY_SHA256'])
    _probe.wait(fd)
