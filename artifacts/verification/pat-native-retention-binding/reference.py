import os
import stat

class JournalError(RuntimeError):

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)

class SupervisorError(JournalError):
    pass

def require(ok, code='QUALIFICATION_INVALID'):
    if not ok:
        raise SupervisorError(code)

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
                    require(stat.S_IMODE(info.st_mode) == 448, 'QUALIFICATION_UNSAFE_FILE')
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        walk(child, depth + 1)
                    finally:
                        os.close(child)
                else:
                    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and (stat.S_IMODE(info.st_mode) == 384), 'QUALIFICATION_UNSAFE_FILE')
                    size += info.st_size
                    require(size <= max_bytes, 'QUALIFICATION_RETENTION_UNKNOWN')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        walk(fd, 0)
    finally:
        os.close(fd)
    return {'files': count, 'logicalBytes': size, 'totalDiskQuotaEnforced': False}
