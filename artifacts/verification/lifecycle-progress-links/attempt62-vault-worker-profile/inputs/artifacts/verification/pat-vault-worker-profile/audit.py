"""Verify diagnostic bytes and source databases; never open worker case databases."""
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = BASE / 'implementation01'
HARNESS = BASE / 'harness01'
ATTEMPT = HARNESS / 'attempts/attempt01-profile'
METHOD = 'test_actual_original_matrix_catalog_execution_and_historical_replay'
SOURCE_PIN = '2e5170b6f0b34bd5490b15b71285d9d85fdf0709eddf00a40cc6a8670a0b55d9'
HARNESS_PIN = '798ce5a871cb18f2b7c40a21075a0a90b300d7843402346730df6aede4791139'

def read(path): return json.loads(path.read_bytes())
def sha(path):
    assert path.is_file() and not path.is_symlink() and path.stat().st_size <= 16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(path, row):
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], str(path)
def inventory(folder):
    rows = []
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            rows.append(dict(path=path.relative_to(folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    return sorted(rows, key=lambda row: row['path'])
def canonical(value):
    # This audit hashes only this independently checked ASCII-key receipt subset.
    def check(item):
        if type(item) is dict:
            assert all(type(key) is str and key.isascii() for key in item)
            for child in item.values(): check(child)
        elif type(item) is list:
            for child in item: check(child)
        else:
            assert type(item) in (str, int, bool, type(None))
            assert type(item) is not int or abs(item) <= 2**53 - 1
    check(value)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
def digest(domain, value): return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()

assert sha(SOURCE / 'index.json') == SOURCE_PIN
assert sha(HARNESS / 'index.json') == HARNESS_PIN
for row in read(SOURCE / 'index.json')['files']: verify(ROOT / row['path'], row)
for row in read(HARNESS / 'index.json')['files']: verify(HARNESS / row['path'], row)
baseline = read(SOURCE / 'baseline-inputs.json')
assert len(baseline['files']) == 286
changes = [row['path'] for row in baseline['files'] if sha(SOURCE / 'project' / row['path']) != row['sha256']]
assert changes == ['supervisor/worker_entry.py']
borrowed = baseline['profileFunctionSource']; verify(ROOT / borrowed['path'], borrowed)
def profile_ast(path):
    return ast.dump(next(n for n in ast.parse(path.read_bytes()).body if isinstance(n, ast.FunctionDef) and n.name == '_profile_group'))
assert profile_ast(SOURCE / 'project/supervisor/worker_entry.py') == profile_ast(ROOT / borrowed['path'])
for row in read(HARNESS / 'borrowed-inputs.json'):
    verify(ROOT / row['source'], row); verify(HARNESS / row['copy'], row)
assert (HARNESS / 'attempt_child.py').read_bytes() == (HARNESS / 'references/attempt_child.py').read_bytes()

result = read(ATTEMPT / 'result.json')
assert result['status'] == 'failed' and result['currentPass'] is False and result['childState'] == 'exited' and result['exitCode'] == 1
assert result['counts'] == dict(testsRun=1, failures=1, errors=0, skips=0, expectedFailures=0, unexpectedSuccesses=0)
assert result['errors'] == result['childErrors'] == [] and result['rawScratchInventoryTerminal']
assert result['timeoutSeconds'] == 180 and result['projectInputCount'] == 286 and result['externalInputCount'] == 159
assert result['limits']['singleAcquiredFileBytes'] == 16777216 and result['limits']['scratchRetentionBytes'] == 268435456
targets = read(HARNESS / 'targets.json')['targets']
assert result['actualTests'] == dict(loaded=targets, executed=targets, exactSelection=True)
for label, folder in (('inputs', ATTEMPT / 'project'), ('frozen', ROOT), ('harness', ATTEMPT / 'harness')):
    before = read(ATTEMPT / (label + '-before.json'))
    assert before == read(ATTEMPT / (label + '-after.json'))
    for row in before: verify(folder / row['path'], row)
external = read(ATTEMPT / 'external-before.json')
assert external == read(ATTEMPT / 'external-after.json')
for row in external['files']: verify(Path(row['resolvedPath']), row)
for label in ('compiler', 'driver'):
    assert read(ATTEMPT / (label + '-before.json')) == read(ATTEMPT / (label + '-after.json'))
origins = read(ATTEMPT / 'imports.json')
assert origins['violations'] == origins['prohibitedAttempts'] == []
for row in origins['records']:
    if 'sha256' in row: assert sha(Path(row['origin'])) == row['sha256']
assert len(read(ATTEMPT / 'sqlite-connections.json')) == 3

raw = Path(result['scratchPath']); work = raw / METHOD
for path, identity in ((raw, read(ATTEMPT / 'raw-scratch-before.json')['identity']),
                       (raw.parent, read(ATTEMPT / 'raw-scratch-after.json')['parentBefore'])):
    info = path.lstat(); assert stat.S_ISDIR(info.st_mode)
    assert (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == tuple(identity[k] for k in ('device','inode','uid','gid','mode'))
held, locks, dbs, hashes = [], [], [], {}
try:
    for path in sorted(work.rglob('*')):
        assert not path.is_symlink()
        if path.is_file() and (path.name.endswith('.owner') or path.name == 'writer.lease'):
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK); held.append(fd)
            info = os.fstat(fd)
            assert stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == 0
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locks.append(dict(path=path.relative_to(work).as_posix(), device=str(info.st_dev), inode=str(info.st_ino)))
    rows = inventory(raw)
    assert rows == inventory(ATTEMPT / 'scratch') == read(ATTEMPT / 'scratch-index.json')
    assert len(rows) <= 8192 and sum(row['bytes'] for row in rows) == result['scratchRetainedBytes'] <= 268435456
    board = next((work / 'runtime').glob('synthetic-io-board-*.db'))
    for path in (work / 'runtime/authority.db', work / 'supervisor/attempts.db', board):
        assert not any(os.path.lexists(str(path) + suffix) for suffix in ('-journal', '-wal', '-shm'))
        hashes[path.relative_to(work).as_posix()] = sha(path)
        db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True, isolation_level=None)
        dbs.append(db); db.execute('PRAGMA query_only=ON')
    authority, supervisor, board_db = dbs
    saved = supervisor.execute('SELECT request,record,return_bytes FROM qs_attempts LIMIT 2').fetchall()
    assert len(saved) == 1 and saved[0][2] is None
    request, record = map(json.loads, saved[0][:2])
    archive = read(work / 'worker-archive.json'); assert archive['record'] == record
    report = record['archive']
    assert record['state'] == 'archived' and record['reason'] == report['supervisorReason'] == 'SUPERVISOR_DEADLINE'
    assert report['exitCode'] == -15 and report['transportComplete'] is False and report['unresolvedEffects'] is None
    assert report['semanticQualificationVerified'] is False and report['returnDigest'] is report['evidenceIntegrity'] is None
    assert request['groupLimits']['maxWallMs'] == 60000 and len(request['bundleHeader']['caseIds']) == 30
    writer = next(row for row in locks if row['path'] == 'supervisor/' + record['attemptId'] + '/writer.lease')
    assert record['lease'] == {key: writer[key] for key in ('device','inode')}
    assert authority.execute('SELECT count(*) FROM iose_handoffs').fetchone()[0] == authority.execute('SELECT count(*) FROM iosr_runs').fetchone()[0] == 1
    handoff = json.loads(authority.execute('SELECT receipt FROM iose_handoffs').fetchone()[0])
    reservation = json.loads(authority.execute('SELECT receipt FROM iosr_runs').fetchone()[0])
    assert handoff == archive['association']['receipt'] and handoff['attemptId'] == record['attemptId'] and handoff['requestDigest'] == record['requestDigest']
    assert handoff['reservationDigest'] == digest(b'HMS-PAT-IO-SERVICE-RUN-RESERVATION-v0.1', reservation)
    assert handoff['supervisorAuthorityId'] == supervisor.execute('SELECT authority FROM qs_meta').fetchone()[0]
    tables = {row[0] for row in authority.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'pc_evaluations' not in tables
    counts = {name: authority.execute('SELECT count(*) FROM ' + name).fetchone()[0] for name in ('ioec_runs','operations','claims')}
    assert set(counts.values()) == {0}
    assert all(row[1:] == (0, 0, 0) for row in board_db.execute('SELECT instance,activations,completed,canceled FROM io_effects'))
    assert board_db.execute('SELECT count(*) FROM io_owners').fetchone()[0] == 0
    worker = work / 'supervisor' / record['attemptId']; output = worker / 'output'
    matrix = read(output / 'matrix.json')
    assert [case['caseId'] for case in matrix['cases']] == request['bundleHeader']['caseIds']
    cases = sorted(output.glob('case-*')); manifests = sorted(output.glob('case-*/manifest.json'))
    assert len(cases) == 10 and len(manifests) == 9
    for i, path in enumerate(manifests): assert read(path)['caseId'] == matrix['cases'][i]['caseId']
    assert not (output / 'result.json').exists() and not (worker / 'worker-return.json').exists()
    profile_path = worker / 'worker-profile.json'; profile = read(profile_path)
    assert profile['profile'] == 'hms.diagnostic.io-worker-profile/0.1' and profile['reason'] == 'SIGTERM'
    assert 0 < profile['totalFunctions'] <= 8192 and len(profile['top40']) <= 40 and len(profile['top40Self']) <= 40
    assert 0 < profile['cpuMicroseconds'] <= profile['wallMicroseconds'] and profile_path.stat().st_size <= 65536
    for row in profile['top40'] + profile['top40Self']:
        assert len(row['label']) <= 512
        assert all(type(row[k]) is int and row[k] >= 0 for k in ('calls','recursiveCalls','cumulativeMicroseconds','selfMicroseconds'))
    for db in reversed(dbs): db.close()
    dbs = []
    for path, expected in hashes.items(): assert sha(work / path) == expected
    assert inventory(raw) == rows == inventory(ATTEMPT / 'scratch')
finally:
    for db in reversed(dbs): db.close()
    for fd in reversed(held): os.close(fd)

summary = dict(stageStatus='verified-diagnostic-actual-scope-failed', sourceIndexSha256=SOURCE_PIN,
    harnessIndexSha256=HARNESS_PIN, resultSha256=sha(ATTEMPT / 'result.json'), productionChanged=False,
    actualScopePassed=False, diagnosticProfileCaptured=True, requestedCases=30,
    caseDirectories=len(cases), caseManifests=len(manifests), originalMaxWallMs=60000,
    originalAttemptId=record['attemptId'], supervisorReason='SUPERVISOR_DEADLINE',
    workerUnresolvedEffects=None, importReached=False, catalogEvaluations=0, sourceApplicationInvocations=0,
    wallMicroseconds=profile['wallMicroseconds'], cpuMicroseconds=profile['cpuMicroseconds'],
    totalProfileFunctions=profile['totalFunctions'], profilePath=profile_path.relative_to(raw).as_posix(),
    profileSha256=sha(profile_path), topCumulative=profile['top40'], topSelf=profile['top40Self'],
    rawPath=str(raw), rawFiles=len(rows), rawBytes=result['scratchRetainedBytes'],
    ownerAndWriterLocks=locks, readonlySourceDatabases=hashes, workerCaseDatabasesOpened=0,
    allOriginalAndCopiedBytesVerified=True, originalDatabasesUnchanged=True,
    previousTimeoutCauseEstablished=False, deploymentPerformanceQualified=False,
    physicalObjectiveVerified=False, aggregateDiskQuotaEnforced=False,
    independentReview=False, goalStatus='active')
with (BASE / 'RESULTS.json').open('x') as stream:
    json.dump(summary, stream, indent=2); stream.write('\n')
print(json.dumps({key: summary[key] for key in ('stageStatus','requestedCases','caseManifests','rawFiles','workerCaseDatabasesOpened','goalStatus')}))
