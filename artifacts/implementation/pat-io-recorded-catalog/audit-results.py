"""Read-only audit of retained scopes; failures remain failures."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

ROOT = Path.cwd()
BASE = ROOT / 'artifacts/implementation/pat-io-recorded-catalog'
PINS = {
    1: '490595e7d5a5f5c2877cc81a810997f34b2070ea54948b7dd070dbed6d51a16d',
    2: '55e12b130d5c87ad8c5eef53d890692db2e1121a4622e75287d6d8ba2dea8b89',
    3: 'd3124e146df9627bc22f8275c0f79c9eff34bb1fde06a0777c2fa6f53b290fdf',
    4: 'daa1013a169c99db81196efa1e0ba1cd3b3a2a1216f1094ff1e79d4ee4b37abc',
}

def read(path):
    return json.loads(path.read_bytes())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify(path, row):
    assert path.is_file() and not path.is_symlink(), str(path)
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], str(path)

def inventory(folder):
    rows = []
    for path in folder.rglob('*'):
        assert not path.is_symlink(), str(path)
        if path.is_file():
            rows.append(dict(path=path.relative_to(folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    return sorted(rows, key=lambda row: row['path'])

baseline_root = ROOT / 'artifacts/implementation/pat-io-content-store/implementation01/project'
for number, pin in PINS.items():
    source = BASE / ('implementation%02d' % number)
    assert sha(source / 'index.json') == pin
    frozen = read(source / 'index.json')['files']
    assert len(frozen) == 277
    for row in frozen:
        verify(ROOT / row['path'], row)
    baseline = read(source / 'baseline-inputs.json')['inheritedProjectInputs']
    assert len(baseline) == 266
    for row in baseline:
        origin = ROOT / row['path']
        verify(origin, row)
        verify(source / 'project' / origin.relative_to(baseline_root), row)

source3 = BASE / 'implementation03/project'
source4 = BASE / 'implementation04/project'
changes = [row['path'] for row in inventory(source3) if sha(source4 / row['path']) != row['sha256']]
assert changes == ['tests/test_io_recorded_catalog_process.py']
assert len(list((source4 / 'recorded_io').glob('*.py'))) == 6

harnesses = sorted(BASE.glob('harness*'))
harnesses = [path for path in harnesses if path.is_dir()]
assert len(harnesses) == 101
for harness in harnesses:
    assert read(harness / 'review.json')['sourceIndexSha256'] in PINS.values()
    for row in read(harness / 'index.json')['files']:
        verify(harness / row['path'], row)

launches = read(BASE / 'source04-control-launch-results.json')
assert [row['harness'] for row in launches] == list(range(84, 102))
assert all(row['exitCode'] == 0 and row['status'] == 'passed' for row in launches)
scopes = [(1, 'attempt01'), (21, 'attempt01'), (22, 'attempt01'), (42, 'attempt01'),
          (62, 'attempt01'), (63, 'attempt01-actual'), (83, 'attempt01-actual')]
scopes += [(number, 'attempt01') for number in range(84, 102)]
passes = {62, *range(84, 102)}
attempts, databases, methods, lock_count = [], [], [], 0
for number, name in scopes:
    harness = BASE / ('harness21-import-diagnostic' if number == 21 else 'harness%02d' % number)
    attempt = harness / 'attempts' / name
    review = read(harness / 'review.json')
    result = read(attempt / 'result.json')
    targets = read(harness / 'targets.json')['targets']
    assert result['status'] == ('passed' if number in passes else 'failed')
    assert result['currentPass'] == (number in passes)
    assert result['timeoutSeconds'] == 180
    assert result['limits']['singleAcquiredFileBytes'] == 16 * 1024 * 1024
    if number == 22:
        assert result['childState'] == 'not_started' and result['counts'] is None
        assert not (attempt / 'sqlite-connections.json').exists()
        assert any(item['message'] == 'Frozen source-preparation index changed' for item in result['errors'])
    else:
        assert result['childState'] == 'exited'
        for label, folder in [('inputs', attempt / 'project'), ('frozen', ROOT), ('harness', attempt / 'harness')]:
            rows = read(attempt / (label + '-before.json'))
            assert rows == read(attempt / (label + '-after.json'))
            for row in rows:
                verify(folder / row['path'], row)
        assert read(attempt / 'external-before.json') == read(attempt / 'external-after.json')
        for row in read(attempt / 'external-before.json')['files']:
            verify(Path(row['resolvedPath']), row)
        if number not in (1, 21):
            for label in ('compiler', 'driver'):
                assert read(attempt / (label + '-before.json')) == read(attempt / (label + '-after.json'))
            assert result['actualTests'] == dict(loaded=targets, executed=targets, exactSelection=True)
            assert result['counts']['testsRun'] == 1 and result['errors'] == result['childErrors'] == []
            methods += targets
        else:
            assert result['counts'] is None and read(attempt / 'sqlite-connections.json') == []
        if number in passes:
            assert result['exitCode'] == 0
            assert result['counts'] == dict(testsRun=1, failures=0, errors=0, skips=0, expectedFailures=0, unexpectedSuccesses=0)
        origins = read(attempt / 'imports.json')
        assert origins['violations'] == origins['prohibitedAttempts'] == []
        for row in origins['records']:
            if 'sha256' in row:
                assert sha(Path(row['origin'])) == row['sha256']
        scratch = Path(result['scratchPath'])
        identity = read(attempt / 'raw-scratch-before.json')['identity']
        info = scratch.lstat()
        assert stat.S_ISDIR(info.st_mode)
        assert (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)) == (
            identity['device'], identity['inode'], identity['uid'], identity['mode'])
        held = []
        try:
            for path in sorted(scratch.rglob('*')):
                if path.is_file() and (path.name.endswith('.owner') or path.name == 'writer.lease'):
                    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
                    held.append(fd)
                    info = os.fstat(fd)
                    assert stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == 0
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_count += len(held)
            rows = inventory(scratch)
            assert rows == inventory(attempt / 'scratch') == read(attempt / 'scratch-index.json')
            assert sum(row['bytes'] for row in rows) == result['scratchRetainedBytes'] <= review['scratchBytesCeiling']
            assert all(row['bytes'] <= 16 * 1024 * 1024 for row in rows)
            sql = read(attempt / 'sqlite-connections.json')
            assert len(sql) <= review['sqliteConnectionsMaximum']
            seen = set()
            for entry in sql:
                original = Path(entry['database'])
                relative = original.relative_to(scratch)
                if relative in seen:
                    continue
                seen.add(relative)
                copied = attempt / 'scratch' / relative
                before = sha(original)
                assert sha(copied) == before
                db = sqlite3.connect(copied.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
                try:
                    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    audit = dict(harness=number, database=relative.as_posix(), bytes=copied.stat().st_size, sha256=before)
                    for table in ('ioec_runs', 'pc_evaluations', 'px_instances', 'operations', 'claims'):
                        if table in tables:
                            audit[table] = db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                    if number not in (63, 83):
                        if 'operations' in tables:
                            assert audit['operations'] == audit['claims'] == 0
                        if 'io_effects' in tables:
                            assert all(tuple(row) == (0, 0, 0) for row in db.execute('SELECT activations,completed,canceled FROM io_effects'))
                        if 'ioec_runs' in tables:
                            bodies = db.execute("SELECT b.body FROM ioec_documents d JOIN ioec_bodies b ON b.digest=d.digest WHERE d.path='original/output/result.json'").fetchall()
                            assert bodies
                            assert all(json.loads(row[0]) == dict(fixture=True, workerExecuted=False, semanticsVerified=False) for row in bodies)
                            audit['explicitQualificationFixture'] = True
                    databases.append(audit)
                finally:
                    db.close()
                assert sha(original) == before == sha(copied)
        finally:
            for fd in held:
                os.close(fd)
    attempts.append(dict(harness=harness.name, attempt=attempt.relative_to(BASE).as_posix(),
        status=result['status'], childState=result['childState'], counts=result['counts'], targets=targets,
        elapsedSeconds=result['elapsedSeconds'], rawBytes=result.get('scratchRetainedBytes'),
        sourceIndexSha256=review['sourceIndexSha256'], harnessIndexSha256=sha(harness / 'index.json')))

actual = read(BASE / 'source03-actual-state-audit.json')
deadline = read(BASE / 'source04-deadline-audit.json')
assert actual['completedWorkerCases'] == 30 and actual['applicationCompletions'] == 1
assert not actual['originalScopePassed'] and not actual['afterConfigurationReplayReached']
assert deadline['writerQuiescenceEstablished'] and not deadline['originalScopePassed']
assert deadline['supervisorReason'] == 'SUPERVISOR_DEADLINE' and deadline['workerUnresolvedEffects'] is None
assert deadline['importedEvaluations'] == deadline['sourceApplications'] == 0
report = dict(goalStatus='active', stageStatus='controls-passed-integration-incomplete', attemptedScopes=25,
    passingScopes=19, failedScopes=6, importOnlyDiagnosticScopes=1, preChildRefusals=1,
    completeMethodReceipts=22, newFixtureControlsPassed=19, actualIntegrationScopesPassed=0,
    actualIntegrationScopesFailed=2, originalSource03WorkerCases=30, originalSource03CompletedApplications=1,
    currentActualFailure='SUPERVISOR_DEADLINE', currentWorkerUnresolvedEffects=None,
    sourceIndexSha256=PINS[4], unchangedInheritedProjectFiles=266, newProductionFiles=6,
    smokePassReusedByExactBytes=True, source03To04ChangedFiles=changes,
    attempts=attempts, databaseAudits=databases, lockFilesReacquired=lock_count,
    allOriginalAndCopiedDatabasesUnchanged=True, allRetainedScratchFilesVerified=True,
    allFrozenInputsVerified=True, historicalFailuresPreserved=True,
    currentConfigurationEligibilityImplemented=True, publicCatalogMounted=False,
    actualCompleteHistoricalReplayVerified=False, physicalObjectiveVerified=False,
    generalCapacityOrTimingGuarantee=False, independentReview=False)
with (BASE / 'RESULTS.json').open('x') as stream:
    stream.write(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: report[key] for key in ('attemptedScopes', 'passingScopes', 'failedScopes',
    'newFixtureControlsPassed', 'actualIntegrationScopesPassed', 'lockFilesReacquired', 'stageStatus')}))
