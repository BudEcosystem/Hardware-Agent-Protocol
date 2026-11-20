"""Read-only retention/association audit of the deadline failure.

Only the four settled parent databases are opened, under their original owner
locks. Worker case databases, including the interrupted case, are never opened.
This audit cannot turn incomplete producer evidence into qualification.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = BASE / 'implementation03'
HARNESS = BASE / 'harness01'
ATTEMPT = HARNESS / 'attempts/attempt01-actual'
PIN = 'ec6df4066c89f38328030a28e2a5bd71d137abbc67cd51cb161cc246e2e8a268'
HPIN = 'ce31a90947d5ec9a2c426ca64f879c071964823bf9b5da68c8c9d745476f5820'
METHOD = 'test_actual_original_matrix_catalog_admission_and_cold_history'

def read(p): return json.loads(p.read_bytes())
def sha(p):
    info = p.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_size <= 16777216
    return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(p, row):
    assert p.lstat().st_size == row['bytes'] and sha(p) == row['sha256'], str(p)
def inventory(folder):
    rows = []
    for p in folder.rglob('*'):
        assert not p.is_symlink()
        if p.is_file(): rows.append(dict(path=p.relative_to(folder).as_posix(), bytes=p.stat().st_size, sha256=sha(p)))
    return sorted(rows, key=lambda v: v['path'])
def canonical(value):
    def check(v):
        if type(v) is dict:
            assert all(type(k) is str and k.isascii() for k in v)
            for x in v.values(): check(x)
        elif type(v) is list:
            for x in v: check(x)
        else:
            assert type(v) in (str, int, bool, type(None))
            assert type(v) is not int or abs(v) <= 2**53 - 1
    check(value)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
def digest(domain, value): return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()

assert not (BASE / 'FAILED_ACTUAL_RESULTS.json').exists()
assert sha(SOURCE / 'index.json') == PIN and sha(HARNESS / 'index.json') == HPIN
for row in read(SOURCE / 'index.json')['files']: verify(ROOT / row['path'], row)
for row in read(HARNESS / 'index.json')['files']: verify(HARNESS / row['path'], row)
result = read(ATTEMPT / 'result.json')
assert result['status'] == 'failed' and result['currentPass'] is False
assert result['childState'] == 'exited' and result['exitCode'] == 1
assert result['counts'] == dict(testsRun=1, failures=1, errors=0, skips=0, expectedFailures=0, unexpectedSuccesses=0)
assert result['errors'] == result['childErrors'] == []
assert result['projectInputCount'] == 304 and result['frozenPreparationInputCount'] == 312
assert result['timeoutSeconds'] == 180 and result['rawScratchInventoryTerminal']
for label, root in (('inputs', ATTEMPT / 'project'), ('frozen', ROOT), ('harness', ATTEMPT / 'harness')):
    rows = read(ATTEMPT / (label + '-before.json'))
    assert rows == read(ATTEMPT / (label + '-after.json'))
    for row in rows: verify(root / row['path'], row)
external = read(ATTEMPT / 'external-before.json')
assert external == read(ATTEMPT / 'external-after.json') and len(external['files']) == 159
for row in external['files']: verify(Path(row['resolvedPath']), row)
origins = read(ATTEMPT / 'imports.json')
assert origins['violations'] == origins['prohibitedAttempts'] == []
native = origins['nativeRetention']
assert native['load']['sha256'] == native['image']['sha256'] == 'ce475ab2a70fb94e84d5d2f2f4c22cb8858d3305005bd154ebda996aae0774ff'
assert native['image']['requestedSeals'] == 15
native_records = 0
for row in origins['records']:
    if row.get('kind') == 'sealed_native_image':
        native_records += 1
        assert row['origin'] == native['image']['origin'] == '/proc/self/fd/' + str(native['image']['descriptor'])
        assert row['sha256'] == native['load']['sha256'] == sha(Path(row['artifactOrigin']))
        assert row['device'] == native['image']['device'] and row['inode'] == native['image']['inode'] and row['matchesBefore']
    elif 'sha256' in row: assert sha(Path(row['origin'])) == row['sha256']
assert native_records == 1
for kind in ('compiler', 'driver'):
    assert read(ATTEMPT / (kind + '-before.json')) == read(ATTEMPT / (kind + '-after.json'))
targets = read(HARNESS / 'targets.json')['targets']
assert read(ATTEMPT / 'actual-tests.json') == dict(loaded=targets, executed=targets, exactSelection=True)
assert len(read(ATTEMPT / 'sqlite-connections.json')) == 4
raw = Path(result['scratchPath'])
work = raw / METHOD
identity = read(ATTEMPT / 'raw-scratch-before.json')['identity']
parent = read(ATTEMPT / 'raw-scratch-after.json')['parentBefore']
for p, expected in ((raw, identity), (raw.parent, parent)):
    info = p.lstat()
    assert stat.S_ISDIR(info.st_mode)
    assert (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == tuple(expected[k] for k in ('device', 'inode', 'uid', 'gid', 'mode'))
held, locks, dbs, hashes = [], [], [], {}
try:
    for p in sorted(work.rglob('*')):
        assert not p.is_symlink()
        if p.is_file() and (p.name.endswith('.owner') or p.name == 'writer.lease'):
            fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            held.append(fd)
            info = os.fstat(fd)
            assert stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == 0
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locks.append(dict(path=p.relative_to(work).as_posix(), device=str(info.st_dev), inode=str(info.st_ino)))
    assert len(locks) == 49
    rows = inventory(raw)
    assert rows == inventory(ATTEMPT / 'scratch') == read(ATTEMPT / 'scratch-index.json')
    assert len(rows) == 3378 and sum(r['bytes'] for r in rows) == result['scratchRetainedBytes'] == 16627891
    board = next((work / 'runtime').glob('synthetic-io-board-*.db'))
    for p in (work / 'runtime/authority.db', work / 'vault/evidence.db', work / 'supervisor/attempts.db', board):
        owner = p.parent / 'supervisor.owner' if p.name == 'attempts.db' else Path(str(p) + '.owner')
        assert owner.relative_to(work).as_posix() in {r['path'] for r in locks}
        assert not any(os.path.lexists(str(p) + suffix) for suffix in ('-journal', '-wal', '-shm'))
        hashes[p.relative_to(work).as_posix()] = sha(p)
        db = sqlite3.connect(p.as_uri() + '?mode=ro&immutable=1', uri=True, isolation_level=None)
        dbs.append(db)
        db.execute('PRAGMA query_only=ON')
    authority, vault, supervisor, board_db = dbs
    saved = supervisor.execute('SELECT request,record,return_bytes FROM qs_attempts LIMIT 2').fetchall()
    assert len(saved) == 1 and saved[0][2] is None
    request, record = map(json.loads, saved[0][:2])
    archive = read(work / 'worker-archive.json')
    assert archive['record'] == record and record['state'] == 'archived' and record['reason'] == 'SUPERVISOR_DEADLINE'
    report = record['archive']
    assert report['exitCode'] == -15 and report['supervisorReason'] == 'SUPERVISOR_DEADLINE'
    assert report['transportComplete'] is False and report['returnValidationFailure'] == 'QUALIFICATION_RETURN_UNAVAILABLE'
    assert report['semanticQualificationVerified'] is False and report['unresolvedEffects'] is None
    assert report['returnDigest'] is None and report['evidenceIntegrity'] is None
    assert request['groupLimits']['maxWallMs'] == 60000 and len(request['bundleHeader']['caseIds']) == 30
    assert record['requestDigest'] == digest(b'HMS-PAT-IO-SUPERVISOR-REQUEST-v0.1', request)
    writer = next(r for r in locks if r['path'] == 'supervisor/' + record['attemptId'] + '/writer.lease')
    assert record['lease'] == {k: writer[k] for k in ('device', 'inode')}
    assert authority.execute('SELECT count(*) FROM iose_handoffs').fetchone()[0] == authority.execute('SELECT count(*) FROM iosr_runs').fetchone()[0] == 1
    handoff = json.loads(authority.execute('SELECT receipt FROM iose_handoffs').fetchone()[0])
    reservation = json.loads(authority.execute('SELECT receipt FROM iosr_runs').fetchone()[0])
    assert handoff == archive['association']['receipt'] and handoff['attemptId'] == record['attemptId']
    assert handoff['requestDigest'] == record['requestDigest']
    assert handoff['reservationDigest'] == digest(b'HMS-PAT-IO-SERVICE-RUN-RESERVATION-v0.1', reservation)
    assert handoff['supervisorAuthorityId'] == supervisor.execute('SELECT authority FROM qs_meta').fetchone()[0]
    assert authority.execute('SELECT request FROM iosr_runs').fetchall() == [(canonical(request),)]
    assert authority.execute('SELECT revision FROM iosc_versions').fetchall() == [(1,)]
    tables = {v[0] for v in authority.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    counts = {n: authority.execute('SELECT count(*) FROM ' + n).fetchone()[0] if n in tables else 0
              for n in ('evi_intents', 'evi_publications', 'operations', 'claims', 'pc_evaluations', 'pc_decisions', 'px_instances', 'px_triggers')}
    assert all(v == 0 for v in counts.values())
    assert [vault.execute('SELECT count(*) FROM ' + n).fetchone()[0] for n in ('ev_manifests', 'ev_documents', 'ev_bodies')] == [0, 0, 0]
    effects = [list(v) for v in board_db.execute('SELECT instance,activations,completed,canceled FROM io_effects')]
    assert effects and all(v[1:] == [0, 0, 0] for v in effects)
    assert board_db.execute('SELECT count(*) FROM io_owners').fetchone()[0] == 0
    worker = work / 'supervisor' / record['attemptId']
    output = worker / 'output'
    matrix = read(output / 'matrix.json')
    assert [v['caseId'] for v in matrix['cases']] == request['bundleHeader']['caseIds']
    manifests = sorted(output.glob('case-*/manifest.json'))
    assert len(manifests) == 25 and len(list(output.glob('case-*'))) == 26
    manifest_summary = []
    for i, p in enumerate(manifests):
        value = read(p)
        assert value['caseId'] == matrix['cases'][i]['caseId'] and value['qualificationPassed'] is False
        if value['executionPerformed']: assert value['closed'] is True
        manifest_summary.append(dict(case=i, caseId=value['caseId'], executionPerformed=value['executionPerformed'], sha256=sha(p)))
    assert (output / 'case-25').is_dir() and not (output / 'case-25/manifest.json').exists()
    assert not (output / 'result.json').exists() and not (worker / 'worker-return.json').exists()
    image = work / 'supervisor' / ('code-' + request['supervisorIdentity'][7:])
    image_rows = inventory(image)
    assert len(image_rows) == 267
    for r in image_rows:
        if r['path'].startswith('dependencies/'):
            matches = [v for v in external['files'] if v['resolvedPath'].endswith('/' + r['path'][len('dependencies/'):])]
            assert len(matches) == 1 and matches[0]['sha256'] == r['sha256'] and matches[0]['bytes'] == r['bytes']
        else: verify(ATTEMPT / 'project' / r['path'], r)
    assert {'hms_qualification/__init__.py', 'hms_qualification/supervisor/__init__.py'} <= {r['path'] for r in image_rows}
    phases = read(work / 'phase-times.json')
    assert phases[-1]['phase'] == 'worker_complete' and not any(v['phase'].startswith('import_') for v in phases)
    accounting = read(ATTEMPT / 'worker-accounting.json')
    launch = accounting['launch']
    assert launch['pid'] == record['pid'] and launch['terminal']['returnCode'] == -15
    assert launch['argv'][3] == str(image / 'hms_qualification/supervisor/worker_entry.py')
    assert not accounting['errors'] and launch['launchFailure'] is None
    for p, expected in hashes.items(): assert sha(work / p) == expected
    assert inventory(raw) == rows
finally:
    for db in reversed(dbs): db.close()
    for fd in reversed(held): os.close(fd)

report = dict(retentionAuditPassed=True, qualificationPassed=False, sourceIndexSha256=PIN,
    harnessIndexSha256=HPIN, attemptId=record['attemptId'], reason=record['reason'],
    sourceFiles=304, frozenFiles=312, producerImageFiles=267, retainedFiles=len(rows),
    retainedBytes=sum(r['bytes'] for r in rows), originalLocks=len(locks), parentDatabaseHashes=hashes,
    parentDatabaseCount=4, workerCaseDatabasesOpened=0, originalRequestAssociated=True,
    requiredCases=30, writtenCaseManifests=25, interruptedCase=25, manifests=manifest_summary,
    independentSemanticReductionPerformed=False, workerEffectsUnresolved=True,
    parentBusinessCounts=counts, parentBoardEffects=effects, vaultManifests=0,
    parentElapsedSeconds=result['elapsedSeconds'],
    workerLaunchToReapSeconds=(launch['terminal']['snapshot']['beforeMonotonicNs']-launch['launchedMonotonicNs'])/1e9,
    workerCpu=accounting['launchToReapDelta']['children']['additiveCounters'],
    waitCauseMeasured=False, limitsUnchanged=True, physicalExecutionPerformed=False,
    sameSourceRetryPerformed=False, namespaceControlResultsSeparate=True,
    limits=['Partial manifests are retained bytes, not independent successful qualification.',
            'Worker case effects remain uninspected and potentially unresolved.',
            'Global pressure and CPU counters do not attribute the deadline cause.',
            'No public service or physical target is qualified by this audit.'])
with (BASE / 'FAILED_ACTUAL_RESULTS.json').open('x') as out: json.dump(report, out, indent=2); out.write('\n')
print(json.dumps({k: report[k] for k in ('retentionAuditPassed', 'qualificationPassed', 'retainedFiles', 'originalLocks', 'writtenCaseManifests', 'interruptedCase')}))
