"""Private Linux/ext4 admission and current mount identity predicate."""
import ctypes
import hashlib
import os
from pathlib import Path
import re
import sys

BOUND = 1024 * 1024


class MountError(RuntimeError):
    pass


class Mount(ctypes.Structure):
    _fields_ = [('mount', ctypes.c_uint64), ('inode', ctypes.c_uint64),
                ('major', ctypes.c_uint32), ('minor', ctypes.c_uint32)]


def path_bytes(path):
    value = os.fsencode(path)
    if not value.startswith(b'/') or b'\0' in value or len(value) > 4095:
        raise MountError('INVALID_MOUNT_PATH')
    return value


class Probe:
    def __init__(self, library, wanted):
        library = Path(library)
        if sys.platform != 'linux':
            raise MountError('UNSUPPORTED_HOST')
        if (type(wanted) is not str or re.fullmatch('[0-9a-f]{64}', wanted) is None or
                hashlib.sha256(library.read_bytes()).hexdigest() != wanted):
            raise MountError('MOUNT_LIBRARY_IDENTITY')
        self.lib = ctypes.CDLL(str(library))
        self.lib.hm_mount_abi.argtypes = []
        self.lib.hm_mount_abi.restype = ctypes.c_uint
        if self.lib.hm_mount_abi() != 1 or ctypes.sizeof(Mount) != 24:
            raise MountError('MOUNT_LIBRARY_ABI')
        self.lib.hm_mount_query.argtypes = [ctypes.c_int, ctypes.c_char_p,
                                            ctypes.c_int, ctypes.POINTER(Mount)]
        self.lib.hm_mount_query.restype = ctypes.c_int

    def query(self, path, fd, unique=True):
        if type(fd) is not int or not 0 <= fd < 2**31 or type(unique) is not bool:
            raise MountError('INVALID_MOUNT_QUERY')
        out = Mount()
        rc = self.lib.hm_mount_query(fd, path_bytes(path), int(unique), ctypes.byref(out))
        if rc != 0:
            raise MountError('MOUNT_QUERY_ERRNO_' + str(-rc))
        return out.mount, out.inode, out.major, out.minor


_probe = None


def query(path, fd, unique=True):
    global _probe
    if _probe is None:
        _probe = Probe(os.environ['HMS_MOUNT_LIBRARY'], os.environ['HMS_MOUNT_LIBRARY_SHA256'])
    return _probe.query(path, fd, unique)


def _number(token, zero=False):
    if re.fullmatch(rb'0|[1-9][0-9]{0,19}', token) is None:
        raise MountError('MOUNT_INVENTORY_NUMBER')
    value = int(token)
    if value >= 2**64 or (not zero and value == 0):
        raise MountError('MOUNT_INVENTORY_NUMBER')
    return value


def _unescape(token):
    # proc(5) escapes exactly space, tab, newline and backslash.
    if re.search(rb'\\(?!040|011|012|134)', token):
        raise MountError('MOUNT_INVENTORY_ESCAPE')
    return re.sub(rb'\\(040|011|012|134)', lambda m: bytes([int(m[1], 8)]), token)


def select_mount(body, path, legacy):
    """Select the exact kernel-reported ID, never sort mountpoint candidates."""
    if type(body) is not bytes or not body or len(body) > BOUND or not body.endswith(b'\n') or b'\0' in body:
        raise MountError('MOUNT_INVENTORY_BOUND_OR_FORMAT')
    expected, inode, major, minor = legacy
    selected = None
    seen = set()
    for line in body[:-1].split(b'\n'):
        fields = line.split(b' ')
        if len(fields) < 10 or any(not part for part in fields) or b'-' not in fields[6:]:
            raise MountError('MOUNT_INVENTORY_FORMAT')
        separator = fields.index(b'-', 6)
        if separator < 6 or len(fields) != separator + 4:
            raise MountError('MOUNT_INVENTORY_FORMAT')
        identity = _number(fields[0])
        _number(fields[1], zero=True)
        if identity in seen:
            raise MountError('MOUNT_INVENTORY_DUPLICATE')
        seen.add(identity)
        if identity != expected:
            continue
        device = fields[2].split(b':')
        if len(device) != 2 or tuple(_number(n, zero=True) for n in device) != (major, minor):
            raise MountError('MOUNT_DEVICE_MISMATCH')
        mountpoint = _unescape(fields[4])
        root = _unescape(fields[3])
        if not mountpoint.startswith(b'/') or not root.startswith(b'/'):
            raise MountError('MOUNT_INVENTORY_PATH')
        if path != mountpoint and not path.startswith(mountpoint.rstrip(b'/') + b'/'):
            raise MountError('MOUNT_PATH_MISMATCH')
        if fields[separator + 1] != b'ext4':
            raise MountError('UNSUPPORTED_FILESYSTEM')
        selected = mountpoint
    if selected is None:
        raise MountError('MOUNT_ID_MISSING')
    return selected


def inventory():
    with open('/proc/self/mountinfo', 'rb') as stream:
        return stream.read(BOUND + 1)


def admit(path, fd):
    encoded = path_bytes(path)
    before = query(path, fd)
    legacy = query(path, fd, False)
    if before[1:] != legacy[1:]:
        raise MountError('MOUNT_CHANGED_DURING_ADMISSION')
    mountpoint = select_mount(inventory(), encoded, legacy)
    if query(path, fd) != before:
        raise MountError('MOUNT_CHANGED_DURING_ADMISSION')
    return before + (legacy[0], mountpoint)


def verify(path, fd, pin):
    if query(path, fd) != pin[:4]:
        raise MountError('MOUNT_CHANGED')
