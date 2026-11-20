"""Protected pathname policy for the stock SQLite VFS used by the runtime.

SQLite resolves filenames and opens sidecars by pathname. A procfs directory
descriptor alias alone does not make this VFS resilient to directory renames.
This profile instead excludes ancestors an untrusted UID can replace.
"""
import os
from pathlib import Path
import re
import stat

from .journal import JournalError


def private_state_directory(path, *, create=False, database_names=()):
    """Validate root/current-UID ancestry and return a private absolute path.

    Root and the current UID remain trusted. A sticky directory owned by one of
    them is allowed because every child traversed is also trusted-owned. Group
    membership alone never makes a writable ancestor trusted in this profile.
    """
    if (type(database_names) not in (tuple, list) or any(type(name) is not str or
            re.fullmatch(r'simulated-plant-[0-9a-f]{64}\.db', name) is None for name in database_names)):
        raise JournalError("INVALID_STATE_FILE_NAME")
    path = Path(os.path.abspath(path))
    if path == Path("/"):
        raise JournalError("UNSAFE_STATE_DIRECTORY")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open("/", flags)
    uid = os.getuid()
    try:
        parts = path.parts[1:]
        for index, part in enumerate(parts):
            parent = os.fstat(descriptor)
            if (parent.st_uid not in {0, uid} or
                    (stat.S_IMODE(parent.st_mode) & 0o022 and not parent.st_mode & stat.S_ISVTX)):
                raise JournalError("UNSAFE_STATE_ANCESTOR")
            if create and index == len(parts) - 1:
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except OSError as error:
                # Missing state is still a startup error, never initialization.
                raise JournalError("UNSAFE_OR_MISSING_STATE_DIRECTORY") from error
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if info.st_uid not in {0, uid}:
                raise JournalError("UNSAFE_STATE_ANCESTOR")
        leaf = os.fstat(descriptor)
        if leaf.st_uid != uid or stat.S_IMODE(leaf.st_mode) != 0o700:
            raise JournalError("UNSAFE_STATE_DIRECTORY")
        # Existing files cannot redirect a validated pathname to a different
        # storage authority through symlinks or hard links. No hostile UID may
        # alter this directory under the ancestor policy just checked.
        names = [name + suffix for name in ("authority.db", "simulated-plant.db", *database_names)
                 for suffix in ("", ".owner", "-journal", "-wal", "-shm")]
        for name in names:
            try:
                info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or
                    stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise JournalError("UNSAFE_STATE_FILE")
        return path
    finally:
        os.close(descriptor)
