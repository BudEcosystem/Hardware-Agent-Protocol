"""Original one-shot client; invoked only after the owned mount is identified."""
import errno
import json
import os
from pathlib import Path
import resource
import stat
import sys

resource.setrlimit(resource.RLIMIT_AS, (64 * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_CPU, (3,) * 2)
resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)
root = Path(sys.argv[1])
checks = []


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)


check('directory', sorted(os.listdir(root)) == ['probe.json'])
target = root / 'probe.json'
body = target.read_bytes()
check('content', json.loads(body) == {
    'profile': 'hms.fuse-mechanism-probe/1', 'readOnly': True,
    'durableStorage': False, 'totalDiskQuotaEnforced': False,
    'backedControlCapacity': False})
observed = target.stat()
check('file-ownership-mode-size', observed.st_uid == os.getuid() and
      observed.st_gid == os.getgid() and stat.S_IMODE(observed.st_mode) == 0o400
      and observed.st_size == len(body) and stat.S_ISREG(observed.st_mode))
observed = root.stat()
check('directory-ownership-mode', observed.st_uid == os.getuid() and
      observed.st_gid == os.getgid() and stat.S_IMODE(observed.st_mode) == 0o500
      and stat.S_ISDIR(observed.st_mode))
fd = os.open(target, os.O_RDONLY)
try:
    check('offset-read', os.pread(fd, 17, 5) == body[5:22])
    check('eof-read', os.pread(fd, 10, len(body)) == b'')
finally:
    os.close(fd)


def refused(name, operation, expected):
    try:
        result = operation()
    except OSError as error:
        check(name, error.errno in expected)
    else:
        if isinstance(result, int):
            os.close(result)
        raise AssertionError(name + ' unexpectedly succeeded')


refused('missing-path', lambda: os.stat(root / 'missing'), {errno.ENOENT})
refused('create-refused', lambda: os.open(root / 'new', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), {errno.EROFS, errno.EACCES})
refused('write-refused', lambda: os.open(target, os.O_WRONLY), {errno.EROFS, errno.EACCES})
refused('unlink-refused', lambda: os.unlink(target), {errno.EROFS, errno.EACCES})
check('unchanged-content', target.read_bytes() == body)
print(json.dumps({'status': 'passed', 'checks': checks}, sort_keys=True))
