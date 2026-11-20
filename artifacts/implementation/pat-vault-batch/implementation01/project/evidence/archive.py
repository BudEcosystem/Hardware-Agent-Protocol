"""Copy one quiescent original attempt through its installed directory fd."""
import fcntl
import hashlib
import os
import re
import stat

from hms.contracts import canonical
from attempt_ledger import _validate_record
from bundle_io import directory, launch_input
import supervisor_contracts as supervisor
from .contracts import require, document, sha


def terminal(row):
    supervisor.parse_request(row['request'])
    _validate_record(row['record'], row['request'], row['returnBytes'])
    record = row['record']; archive = record['archive']
    require(record['requestDigest'] == supervisor.request_digest(row['request']), 'REQUEST')
    require(record['state'] == 'archived' and archive['transportComplete'] is True, 'TRANSPORT_INCOMPLETE')
    returned = document(row['returnBytes'])
    require(returned == dict(profile='hms.pat.io-supervisor-return/0.1', attemptId=record['attemptId'],
        requestDigest=record['requestDigest'], bundleDigest=row['request']['bundleDigest'],
        groupResultDigest=returned.get('groupResultDigest'), status='captured'), 'RETURN')
    return returned


def output_closure(files):
    """Match the supervisor's sorted directory walk, including path boundaries."""
    chain = hashlib.sha256(b'HMS-PAT-IO-OUTPUT-CLOSURE-v0.1\0')
    for name in sorted(files, key=lambda value: tuple(value.split('/'))):
        body = files[name]
        chain.update(canonical(dict(path=name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest())) + b'\n')
    return dict(fileCount=len(files), bytes=sum(map(len, files.values())), orderedDigest='sha256:' + chain.hexdigest())


def _names(fd, maximum):
    names = []
    with os.scandir(fd) as entries:
        for entry in entries:
            require(len(names) < maximum, 'FILE_LIMIT'); names.append(entry.name)
    return sorted(names)


def _file(parent, name, maximum=65536):
    handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        before = supervisor.safe_file(handle, maximum=maximum)
        parts = []; remaining = before.st_size + 1
        while remaining:
            part = os.read(handle, min(65536, remaining))
            if not part: break
            parts.append(part); remaining -= len(part)
        body = b''.join(parts); after = os.fstat(handle)
        require(len(body) == before.st_size and
            (before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'FILE_CHANGED')
        return body
    finally: os.close(handle)


def _bundle(parent, expected):
    root = directory(parent, 'bundle')
    try:
        require(_names(root, 4) == ['cases', 'header.json', 'inputs'], 'INPUT_CHANGED')
        require(_file(root, 'header.json') == expected['header'], 'INPUT_CHANGED')
        for part in ('inputs', 'cases'):
            child = directory(root, part)
            try:
                names = sorted(name.split('/')[1] for name in expected['documents'] if name.startswith(part + '/'))
                require(_names(child, 40) == names, 'INPUT_CHANGED')
                for name in names:
                    require(_file(child, name) == expected['documents'][part + '/' + name], 'INPUT_CHANGED')
            finally: os.close(child)
    finally: os.close(root)


def read_original(supervisor_service, row, expected_bundle):
    """No path/callback supplied by import callers; no process is signalled."""
    terminal(row); request = row['request']; record = row['record']
    attempt = directory(supervisor_service.ledger.fd, record['attemptId'])
    lease = None
    try:
        lease = os.open('writer.lease', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=attempt)
        info = supervisor.safe_file(lease, maximum=0)
        require(record['lease'] == dict(device=str(info.st_dev), inode=str(info.st_ino)), 'LEASE_CHANGED')
        try: fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            from .contracts import EvidenceError
            raise EvidenceError('PRODUCER_ACTIVE') from error
        _bundle(attempt, expected_bundle)
        require(_file(attempt, 'worker-return.json') == row['returnBytes'], 'RETURN_CHANGED')
        require(_file(attempt, 'input.json') == canonical(launch_input(request, record['attemptId'])), 'LAUNCH_CHANGED')
        output = directory(attempt, 'output'); files = {}; count = total = 0
        try:
            def walk(fd, prefix, depth):
                nonlocal count, total
                require(depth <= 10, 'DEPTH')
                for name in _names(fd, request['limits']['maxFilesPerAttempt']):
                    count += 1; require(count <= request['limits']['maxFilesPerAttempt'], 'FILE_LIMIT')
                    require(re.fullmatch(r'[A-Za-z0-9_.-]+', name) and name not in ('.', '..'), 'PATH')
                    target = prefix + name; require(len(target) <= 256, 'PATH')
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        child = directory(fd, name)
                        try: walk(child, target + '/', depth + 1)
                        finally: os.close(child)
                    else:
                        # Refuse FIFOs/devices before open as well as on the fd.
                        require(stat.S_ISREG(info.st_mode), 'UNSAFE_FILE')
                        maximum = min(16 * 1024 * 1024, request['groupLimits']['maxDerivedBytes'] - total,
                                      65536 if name.endswith('.json') else 16 * 1024 * 1024)
                        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                        try:
                            before = supervisor.safe_file(handle, maximum=maximum)
                            require((before.st_dev, before.st_ino) == (info.st_dev, info.st_ino), 'FILE_CHANGED')
                            parts = []; remaining = before.st_size + 1
                            while remaining:
                                part = os.read(handle, min(65536, remaining))
                                if not part: break
                                parts.append(part); remaining -= len(part)
                            body = b''.join(parts); after = os.fstat(handle)
                            require(len(body) == before.st_size and
                                (before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                                (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'FILE_CHANGED')
                        finally: os.close(handle)
                        total += len(body); files[target] = body
            walk(output, '', 0)
        finally: os.close(output)
        require(output_closure(files) == record['archive']['evidenceIntegrity'], 'OUTPUT_CHANGED')
        require(sha(files.get('result.json', b'')) == document(row['returnBytes'])['groupResultDigest'], 'RESULT_CHANGED')
        return files
    finally:
        if lease is not None: os.close(lease)
        os.close(attempt)
