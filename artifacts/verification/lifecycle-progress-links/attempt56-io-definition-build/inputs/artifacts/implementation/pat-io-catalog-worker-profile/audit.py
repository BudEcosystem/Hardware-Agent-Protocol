"""Read only original/copy bytes and quiescent databases; preserve failure."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

ROOT = Path.cwd()
BASE = ROOT / 'artifacts/implementation/pat-io-catalog-worker-profile'
STAGE = BASE / 'implementation01'
HARNESS = BASE / 'harness01'
ATTEMPT = HARNESS / 'attempts/attempt01-current-profile'
PIN = 'edc5f4dd343334eb46f78e640036e8d922e1a577b28aef20373f144619982535'

def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(path, row):
    assert not path.is_symlink() and path.is_file() and path.stat().st_size == row['bytes']
    assert sha(path) == row['sha256'], str(path)

assert sha(STAGE / 'index.json') == PIN
for row in read(STAGE / 'index.json')['files']: verify(ROOT / row['path'], row)
for row in read(HARNESS / 'index.json')['files']: verify(HARNESS / row['path'], row)
result = read(ATTEMPT / 'result.json')
assert result['status'] == 'failed' and not result['currentPass'] and result['childState'] == 'exited'
assert result['counts'] == dict(testsRun=1, failures=1, errors=0, skips=0, expectedFailures=0, unexpectedSuccesses=0)
assert result['errors'] == result['childErrors'] == [] and result['rawScratchInventoryTerminal']
targets = read(HARNESS / 'targets.json')['targets']
assert result['actualTests'] == dict(loaded=targets, executed=targets, exactSelection=True)
for label, folder in [('inputs', ATTEMPT / 'project'), ('frozen', ROOT), ('harness', ATTEMPT / 'harness')]:
    rows = read(ATTEMPT / (label + '-before.json'))
    assert rows == read(ATTEMPT / (label + '-after.json'))
    for row in rows: verify(folder / row['path'], row)
assert read(ATTEMPT / 'external-before.json') == read(ATTEMPT / 'external-after.json')
for row in read(ATTEMPT / 'external-before.json')['files']: verify(Path(row['resolvedPath']), row)
for label in ('compiler', 'driver'):
    assert read(ATTEMPT / (label + '-before.json')) == read(ATTEMPT / (label + '-after.json'))
origins = read(ATTEMPT / 'imports.json')
assert origins['violations'] == origins['prohibitedAttempts'] == []
for row in origins['records']:
    if 'sha256' in row: assert sha(Path(row['origin'])) == row['sha256']

raw = Path(result['scratchPath'])
work = raw / 'test_actual_original_matrix_catalog_execution_and_historical_replay'
identity = read(ATTEMPT / 'raw-scratch-before.json')['identity']; info = raw.lstat()
assert stat.S_ISDIR(info.st_mode)
assert (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)) == (
    identity['device'], identity['inode'], identity['uid'], identity['mode'])
held, locks, databases = [], [], []
try:
    for path in sorted(work.rglob('*')):
        assert not path.is_symlink()
        if path.is_file() and (path.name.endswith('.owner') or path.name == 'writer.lease'):
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
            held.append(fd); info = os.fstat(fd)
            assert stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == 0
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locks.append(dict(path=path.relative_to(work).as_posix(), device=str(info.st_dev), inode=str(info.st_ino)))
    rows = read(ATTEMPT / 'scratch-index.json')
    assert len(rows) <= 8192 and sum(row['bytes'] for row in rows) == result['scratchRetainedBytes'] <= 256*1024*1024
    assert {row['path'] for row in rows} == {path.relative_to(raw).as_posix() for path in raw.rglob('*') if path.is_file()}
    for row in rows:
        assert row['bytes'] <= 16*1024*1024
        verify(raw / row['path'], row); verify(ATTEMPT / 'scratch' / row['path'], row)
    archive = read(work / 'worker-archive.json')
    record = archive['record']; report = record['archive']
    assert record['state'] == 'archived' and report['supervisorReason'] == 'SUPERVISOR_DEADLINE'
    assert report['exitCode'] == -15 and not report['transportComplete'] and report['unresolvedEffects'] is None
    attempt_id = record['attemptId']
    worker = work / 'supervisor' / attempt_id
    writer = next(row for row in locks if row['path'] == 'supervisor/' + attempt_id + '/writer.lease')
    assert record['lease'] == {key: writer[key] for key in ('device', 'inode')}
    profile_path = worker / 'worker-profile.json'
    profile = read(profile_path)
    assert profile['profile'] == 'hms.diagnostic.io-worker-profile/0.1' and profile['reason'] == 'SIGTERM'
    assert 0 < profile['totalFunctions'] <= 8192 and len(profile['top40']) <= 40 and len(profile['top40Self']) <= 40
    assert 0 < profile['cpuMicroseconds'] <= profile['wallMicroseconds'] and profile_path.stat().st_size <= 65536
    for row in profile['top40'] + profile['top40Self']:
        assert len(row['label']) <= 512 and all(type(row[key]) is int and row[key] >= 0 for key in ('calls','recursiveCalls','cumulativeMicroseconds','selfMicroseconds'))
    def database(path):
        before = sha(path)
        db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            observed = dict(path=path.relative_to(work).as_posix(), bytes=path.stat().st_size, sha256=before)
            for table in ('ioec_runs','pc_evaluations','px_instances','operations','claims','io_owners'):
                if table in tables: observed[table] = db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
            if 'operations' in tables:
                observed['operationStates'] = [list(row) for row in db.execute('SELECT state,count(*) FROM operations GROUP BY state ORDER BY state')]
            if 'io_effects' in tables:
                observed['effectCounters'] = [list(row) for row in db.execute('SELECT * FROM io_effects ORDER BY instance')]
            if 'qs_attempts' in tables:
                values = db.execute('SELECT request,record,return_bytes FROM qs_attempts').fetchall()
                assert len(values) == 1 and values[0][2] is None
                request = json.loads(values[0][0]); assert json.loads(values[0][1]) == record
                assert request['groupLimits']['maxWallMs'] == 60000 and len(request['bundleHeader']['caseIds']) == 30
                observed['originalRequestMaxWallMs'] = 60000
                observed['originalRequestedCases'] = 30
        finally:
            db.close()
        assert sha(path) == before
        databases.append(observed)
        return observed
    for path in sorted(work.glob('runtime/*.db')): database(path)
    database(work / 'supervisor/attempts.db')
    cases = sorted(path for path in (worker / 'output').glob('case-*') if path.is_dir())
    assert len(cases) <= 30
    for case in cases:
        paths = sorted((case / 'state').glob('*.db'))
        assert len(paths) <= 2
        for path in paths: database(path)
    source = next(row for row in databases if row['path'] == 'runtime/authority.db')
    assert source['ioec_runs'] == source['operations'] == source['claims'] == 0
    assert 'pc_evaluations' not in source
    emitted = dict(stageStatus='diagnostic-complete-original-scope-failed', sourceIndexSha256=PIN,
        actualScopePassed=False, diagnosticProfileCaptured=True, originalFailureRetained=True,
        originalAttemptId=attempt_id, supervisorReason='SUPERVISOR_DEADLINE', originalMaxWallMs=60000,
        originalRequestedCases=30, caseDirectories=len(cases), caseManifests=sum((case/'manifest.json').is_file() for case in cases),
        workerUnresolvedEffects=None, sourceApplications=0, catalogEvaluations=0,
        wallMicroseconds=profile['wallMicroseconds'], cpuMicroseconds=profile['cpuMicroseconds'], totalProfileFunctions=profile['totalFunctions'],
        profilePath=profile_path.relative_to(raw).as_posix(), profileSha256=sha(profile_path),
        topCumulative=profile['top40'], topSelf=profile['top40Self'], phases=archive['phases'],
        rawFiles=len(rows), rawBytes=result['scratchRetainedBytes'], locks=locks, databases=databases,
        writerQuiescenceEstablished=True, originalHarnessUnsettledFlag=result['rawScratchMayContainUnsettledFixtureWork'],
        allOriginalAndCopiedBytesVerified=True, originalDatabasesUnchanged=True,
        previousTimeoutCauseEstablished=False, deploymentPerformanceQualified=False, physicalObjectiveVerified=False,
        independentReview=False, goalStatus='active')
    with (BASE / 'RESULTS.json').open('x') as stream:
        stream.write(json.dumps(emitted, indent=2) + '\n')
    print(json.dumps({key: emitted[key] for key in ('actualScopePassed','diagnosticProfileCaptured','caseDirectories','caseManifests',
        'wallMicroseconds','cpuMicroseconds','writerQuiescenceEstablished','rawFiles')}))
finally:
    for fd in held: os.close(fd)
