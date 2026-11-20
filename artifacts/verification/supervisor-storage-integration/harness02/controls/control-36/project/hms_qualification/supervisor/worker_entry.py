"""Fixed isolated original-worker entry; arguments are inherited descriptors only."""
import os
from pathlib import Path
import resource
import stat
import socket
import sys

# -I ignores caller environment/search paths; this protected image is fixed by
# the supervisor. Its package initializers belong to the pinned producer image.
os.umask(0o077)
sys.dont_write_bytecode = True
_IMAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_IMAGE_ROOT / 'dependencies'))
sys.path.insert(0, str(_IMAGE_ROOT))

# Accidental reference retrieval must fail before any dependency import or
# capsule validation. This trusted-code veto is not an OS security sandbox.
def _no_network(*args, **kwargs):
    raise RuntimeError('QUALIFICATION_NETWORK_FORBIDDEN')
class _NoSocket(socket.socket):
    def __new__(cls, *args, **kwargs): return _no_network()
socket.socket = _NoSocket
socket.create_connection = _no_network
socket.getaddrinfo = _no_network

from hms.contracts import canonical
from hms.pat_io_group_worker import run_io_group
from hms_qualification.supervisor.bundle_io import load_bundle, check_bundle
from hms_qualification.supervisor.supervisor_contracts import parse_request, request_digest, digest, exact
from hms import pat_simulation_worker as worker
from hms_qualification.supervisor.supervisor_contracts import require, safe_file, document, validate_fresh, write_file


def main():
    require(len(sys.argv) == 4, 'QUALIFICATION_ENTRY_ARGUMENTS')
    directory, input_fd, lease = (int(value) for value in sys.argv[1:])
    require(sys.flags.isolated == 1 and worker._ROOT == _IMAGE_ROOT,
            'QUALIFICATION_CHILD_IMPORT_MISMATCH')
    info = os.fstat(directory)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700)
    safe_file(lease); source = safe_file(input_fd, maximum=65536)
    os.lseek(input_fd, 0, os.SEEK_SET)
    body = os.read(input_fd, source.st_size + 1)
    require(len(body) == source.st_size)
    launch = document(body)
    exact(launch, {'profile','attemptId','request'})
    require(launch['profile']=='hms.pat.io-supervisor-launch/0.1')
    request = parse_request(launch['request'])
    bundle = load_bundle(directory, request)
    validate_fresh(request, bundle)
    parsed = check_bundle(request, bundle)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    _, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    cap = request['limits']['maxFileBytes']
    if hard != resource.RLIM_INFINITY: cap = min(cap, hard)
    resource.setrlimit(resource.RLIMIT_FSIZE, (cap, cap))
    os.fchdir(directory)
    # The real protected pathname is necessary for SQLite's stock pathname VFS.
    attempt = Path.cwd()
    require(attempt.name == launch['attemptId'], 'QUALIFICATION_INPUT_ASSOCIATION')
    inputs = parsed['expected_inputs']
    result = run_io_group(attempt / 'output', candidate=inputs['candidate'], installation=inputs['installation'],
        descriptor=inputs['descriptor'], challenge_bindings=inputs['bindings'], limits=request['groupLimits'])
    returned = dict(profile='hms.pat.io-supervisor-return/0.1', attemptId=launch['attemptId'],
        requestDigest=request_digest(request), bundleDigest=request['bundleDigest'],
        groupResultDigest=digest(canonical(result)), status=result['status'])
    write_file(directory, 'worker-return.json', canonical(returned))
    # Do not explicitly unlock/close the inherited writer lease before exit.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
