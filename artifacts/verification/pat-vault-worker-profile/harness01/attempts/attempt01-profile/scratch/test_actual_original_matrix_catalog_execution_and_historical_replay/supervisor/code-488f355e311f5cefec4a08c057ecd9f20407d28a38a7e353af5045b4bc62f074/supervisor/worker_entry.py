"""Fixed isolated original-worker entry; arguments are inherited descriptors only."""
import os
from pathlib import Path
import resource
import stat
import socket
import sys

# -I ignores caller environment/search paths; this protected image is fixed by
# the supervisor. The entry is outside hms so the worker source closure is exact.
os.umask(0o077)
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dependencies'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

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
from bundle_io import load_bundle, check_bundle
from supervisor_contracts import parse_request, request_digest, digest, exact
from hms import pat_simulation_worker as worker
from supervisor_contracts import (require, safe_file, document, validate_fresh, write_file)


def _profile_group(directory, call):
    """Diagnostic only: bounded profile; SIGTERM is re-raised to this process."""
    import cProfile
    import signal
    import time
    profiler = cProfile.Profile()
    wall, cpu = time.monotonic(), time.process_time()
    finishing = False
    previous = signal.getsignal(signal.SIGTERM)
    require(previous == signal.SIG_DFL, 'QUALIFICATION_PROFILE_SIGNAL_STATE')
    def finish(reason):
        nonlocal finishing
        if finishing: return
        finishing = True
        profiler.disable()
        wall_elapsed, cpu_elapsed = time.monotonic()-wall, time.process_time()-cpu
        entries = profiler.getstats()
        require(len(entries)<=8192, 'QUALIFICATION_PROFILE_LIMIT')
        rows = []
        for entry in entries:
            code = entry.code
            if isinstance(code,str): label = code
            else:
                path = Path(code.co_filename)
                name = str(path.relative_to(worker._ROOT)) if path.is_relative_to(worker._ROOT) else str(path)
                label = name+':'+str(code.co_firstlineno)+':'+code.co_name
            require(len(label)<=512, 'QUALIFICATION_PROFILE_LIMIT')
            rows.append(dict(label=label,calls=entry.callcount,recursiveCalls=entry.reccallcount,
                cumulativeMicroseconds=int(entry.totaltime*1000000),selfMicroseconds=int(entry.inlinetime*1000000)))
        rows.sort(key=lambda r:(-r['cumulativeMicroseconds'],r['label']))
        value = dict(profile='hms.diagnostic.io-worker-profile/0.1',reason=reason,
            scope='Instrumented original run_io_group only; profiler overhead and interrupted data do not qualify performance or effects.',
            wallMicroseconds=int(wall_elapsed*1000000),cpuMicroseconds=int(cpu_elapsed*1000000),
            totalFunctions=len(rows),top40=rows[:40],top40Self=sorted(rows,key=lambda r:(-r['selfMicroseconds'],r['label']))[:40])
        write_file(directory,'worker-profile.json',canonical(value))
    def terminated(signum, frame):
        try: finish('SIGTERM')
        finally:
            signal.signal(signal.SIGTERM,signal.SIG_DFL)
            signal.raise_signal(signal.SIGTERM)
    signal.signal(signal.SIGTERM,terminated)
    profiler.enable()
    try: return call()
    finally:
        try: finish('returned-or-exception')
        finally: signal.signal(signal.SIGTERM,previous)

def main():
    require(len(sys.argv) == 4, 'QUALIFICATION_ENTRY_ARGUMENTS')
    directory, input_fd, lease = (int(value) for value in sys.argv[1:])
    require(sys.flags.isolated == 1 and worker._ROOT == Path(__file__).resolve().parents[1],
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
    result = _profile_group(directory, lambda: run_io_group(attempt / 'output', candidate=inputs['candidate'], installation=inputs['installation'],
        descriptor=inputs['descriptor'], challenge_bindings=inputs['bindings'], limits=request['groupLimits']))
    returned = dict(profile='hms.pat.io-supervisor-return/0.1', attemptId=launch['attemptId'],
        requestDigest=request_digest(request), bundleDigest=request['bundleDigest'],
        groupResultDigest=digest(canonical(result)), status=result['status'])
    write_file(directory, 'worker-return.json', canonical(returned))
    # Do not explicitly unlock/close the inherited writer lease before exit.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
