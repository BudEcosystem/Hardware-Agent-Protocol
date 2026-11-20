"""Read-only allocation observation of the retained passing authority database."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'artifacts/implementation/pat-io-definition-build'
ATTEMPT = SOURCE / 'harness02/attempts/attempt01-actual'
result = json.loads((ATTEMPT / 'result.json').read_bytes())
assert result['status'] == 'passed' and result['exitCode'] == 0
name = 'test_actual_original_matrix_catalog_execution_and_historical_replay'
original = Path(result['scratchPath']) / name
copied = ATTEMPT / 'scratch' / name
databases = [original / 'runtime/authority.db', copied / 'runtime/authority.db']
assert all(path.stat().st_size == 16199680 for path in databases)
allowed = [path.resolve().as_uri() + '?mode=ro&immutable=1' for path in databases]
connections = []
def hook(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in ('os.system', 'os.fork', 'os.exec', 'os.posix_spawn'):
        raise RuntimeError('external execution/network veto')
    if event == 'sqlite3.connect':
        assert args[0] in allowed and args[0] not in connections
        connections.append(args[0])
sys.addaudithook(hook)

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

source_pin = Path(__file__).resolve().parent / 'index.json'
pin = json.loads(source_pin.read_bytes())
for row in pin['files']:
    assert digest(source_pin.parent / row['path']) == row['sha256']
assert digest(SOURCE / 'implementation01/index.json') == '7a52bf04800bde161cfb778fca0da5cec996468fe03d9944902e73e11c6817cc'
assert digest(SOURCE / 'index.json') == 'c38169d02e04a3fbb72a50ea4ccd285683ed79834da2e9d9cd32fe5b10f1fe02'
root_index = json.loads((SOURCE / 'index.json').read_bytes())
copy_rows = [row for row in root_index['files'] if row['path'].endswith(
    'harness02/attempts/attempt01-actual/scratch/' + name + '/runtime/authority.db')]
assert len(copy_rows) == 1 and copy_rows[0]['bytes'] == 16199680
held = []
locks = []
try:
    paths = sorted(original.rglob('*'))
    assert len(paths) <= 8192
    for path in paths:
        assert not path.is_symlink()
        if path.is_file() and (path.name.endswith('.owner') or path.name in ('supervisor.owner', 'writer.lease')):
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
            held.append(fd)
            info = os.fstat(fd)
            assert stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == 0
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locks.append(dict(path=path.relative_to(original).as_posix(), device=str(info.st_dev), inode=str(info.st_ino)))
    assert locks and any(row['path'] == 'runtime/authority.db.owner' for row in locks)
    for path in databases:
        assert not path.is_symlink()
        assert not any(Path(str(path) + suffix).exists() for suffix in ('-journal', '-wal', '-shm'))
    before = [digest(path) for path in databases]
    assert before[0] == before[1] == copy_rows[0]['sha256']
    observations = []
    for uri in allowed:
        db = sqlite3.connect(uri, uri=True, isolation_level=None)
        try:
            deadline = time.monotonic() + 10
            steps = [0]
            def progress():
                steps[0] += 1000
                return int(steps[0] > 2000000 or time.monotonic() > deadline)
            db.set_progress_handler(progress, 1000)
            db.execute('PRAGMA query_only=ON')
            meta = {key: db.execute('PRAGMA ' + key).fetchone()[0]
                    for key in ('page_size', 'page_count', 'freelist_count', 'auto_vacuum', 'journal_mode')}
            assert meta['page_size'] == 1024 and meta['page_count'] == 15820
            assert meta['auto_vacuum'] == 0 and meta['journal_mode'] == 'delete'
            rows = db.execute("SELECT name,pageno,payload,unused,pgsize FROM dbstat('main',1) LIMIT 257").fetchall()
            assert 0 < len(rows) <= 256
            records = [dict(zip(('name', 'pages', 'payloadBytes', 'unusedBytes', 'allocatedBytes'), row)) for row in rows]
            assert all(row['pages'] * 1024 == row['allocatedBytes'] for row in records)
            allocated = sum(row['allocatedBytes'] for row in records)
            assert allocated + meta['freelist_count'] * 1024 == 16199680
            body_names = {'ioec_bodies', 'sqlite_autoindex_ioec_bodies_1'}
            assert body_names <= {row['name'] for row in records}
            body_bytes = sum(row['allocatedBytes'] for row in records if row['name'] in body_names)
            evidence_bytes = sum(row['allocatedBytes'] for row in records
                                 if row['name'].startswith(('ioec_', 'sqlite_autoindex_ioec_')))
            observations.append(dict(pragmas=meta, objects=records, btreeBytes=allocated,
                exactBodyTableAndIndexBytes=body_bytes, compactEvidenceBtreeBytes=evidence_bytes,
                otherBtreeBytes=allocated - evidence_bytes, freeBytes=meta['freelist_count'] * 1024))
        finally:
            db.close()
    assert observations[0] == observations[1]
    assert [digest(path) for path in databases] == before
    for row in pin['files']:
        assert digest(source_pin.parent / row['path']) == row['sha256']
    report = dict(status='passed', sqliteVersion=sqlite3.sqlite_version, sourceIndexSha256=digest(source_pin),
        originalDatabase=str(databases[0]), retainedCopy=str(databases[1]), databaseSha256=before[0],
        originalAndCopyUnchanged=True, ownerLocksHeld=locks, observation=observations[0],
        databaseBytes=16199680, unchangedSingleFileCeiling=16777216, headroomBytes=577536,
        thisIsNotCapacityReservation=True, runtimeExecution=False, acquiredCodeExecuted=False)
    with (BASE / 'allocation.json').open('x') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ('observation', 'ownerLocksHeld')}
        | {key: value for key, value in observations[0].items() if key != 'objects'}))
finally:
    for fd in reversed(held):
        os.close(fd)
