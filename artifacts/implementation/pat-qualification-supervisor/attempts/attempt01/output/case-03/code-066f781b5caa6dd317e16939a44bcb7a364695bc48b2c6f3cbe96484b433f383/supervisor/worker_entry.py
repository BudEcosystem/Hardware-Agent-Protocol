"""Fixed isolated original-worker entry; arguments are inherited descriptors only."""
import os
from pathlib import Path
import resource
import stat
import sys

# -I ignores caller environment/search paths; this protected image is fixed by
# the supervisor. The entry is outside hms so the worker source closure is exact.
os.umask(0o077)
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hms.contracts import canonical
from hms.pat_simulation_worker import run_worker
from supervisor_contracts import (require, safe_file, document, validate_fresh, write_file)


def main():
    require(len(sys.argv) == 4, 'QUALIFICATION_ENTRY_ARGUMENTS')
    directory, input_fd, lease = (int(value) for value in sys.argv[1:])
    info = os.fstat(directory)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700)
    safe_file(lease); source = safe_file(input_fd, maximum=65536)
    os.lseek(input_fd, 0, os.SEEK_SET)
    body = os.read(input_fd, source.st_size + 1)
    require(len(body) == source.st_size)
    request = validate_fresh(document(body))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    _, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    cap = request['limits']['maxFileBytes']
    if hard != resource.RLIM_INFINITY: cap = min(cap, hard)
    resource.setrlimit(resource.RLIMIT_FSIZE, (cap, cap))
    os.fchdir(directory)
    # The real protected pathname is necessary for SQLite's stock pathname VFS.
    attempt = Path.cwd()
    result = run_worker(request['trust']['input'], attempt / 'output')
    write_file(directory, 'worker-return.json', canonical(result))
    # Do not explicitly unlock/close the inherited writer lease before exit.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
