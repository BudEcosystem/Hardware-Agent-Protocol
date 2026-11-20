"""Read-only deadline-state and writer-quiescence audit; never a pass rewrite."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

BASE = Path('artifacts/implementation/pat-io-recorded-catalog')
ATTEMPT = BASE / 'harness83/attempts/attempt01-actual'

def read(path):
    return json.loads(path.read_bytes())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

result = read(ATTEMPT / 'result.json')
assert result['status'] == 'failed' and result['childState'] == 'exited' and result['counts']['failures'] == 1
assert result['counts']['errors'] == 0 and result['errors'] == [] and result['scratchRetained']
assert 'SUPERVISOR_DEADLINE' in (ATTEMPT / 'output.log').read_text()
raw = Path(result['scratchPath'])
work = raw / 'test_actual_original_matrix_catalog_execution_and_historical_replay'
held, locks, database_hashes = [], [], []
try:
    for path in sorted(work.rglob('*')):
        assert not path.is_symlink()
        if path.is_file() and (path.name.endswith('.owner') or path.name == 'writer.lease'):
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
            held.append(fd); info = os.fstat(fd)
            assert stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == 0
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locks.append(dict(path=path.relative_to(work).as_posix(), device=str(info.st_dev), inode=str(info.st_ino)))
    for row in read(ATTEMPT / 'scratch-index.json'):
        original = raw / row['path']; copied = ATTEMPT / 'scratch' / row['path']
        assert original.stat().st_size == copied.stat().st_size == row['bytes']
        assert sha(original) == sha(copied) == row['sha256']
    def database(relative, callback):
        path = work / relative; before = sha(path)
        db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            value = callback(db)
        finally:
            db.close()
        assert before == sha(path)
        database_hashes.append(dict(path=relative, bytes=path.stat().st_size, sha256=before))
        return value
    def ledger(db):
        values = db.execute('SELECT request,record,return_bytes FROM qs_attempts').fetchall()
        assert len(values) == 1
        request, record = json.loads(values[0][0]), json.loads(values[0][1])
        archive = record['archive']
        assert record['state'] == 'archived' and values[0][2] is None
        assert archive['supervisorReason'] == 'SUPERVISOR_DEADLINE' and archive['exitCode'] == -15
        assert archive['transportComplete'] is False and archive['unresolvedEffects'] is None
        assert request['groupLimits']['maxWallMs'] == 60000 and len(request['bundleHeader']['caseIds']) == 30
        writer = next(row for row in locks if row['path'].endswith('/' + record['attemptId'] + '/writer.lease'))
        assert record['lease'] == {name:writer[name] for name in ('device','inode')}
        return record
    record = database('supervisor/attempts.db', ledger)
    def authority(db):
        counts = {name:db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                  for name in ('ioec_runs','operations','claims')}
        assert counts == dict(ioec_runs=0, operations=0, claims=0)
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='pc_evaluations'").fetchone() is None
        assert db.execute('SELECT revision FROM iosc_versions').fetchall() == [(1,)]
        return counts
    counts = database('runtime/authority.db', authority)
    archive = read(work / 'worker-archive.json')
    assert archive['record'] == record
    report = dict(originalScopePassed=False, originalFailureRetained=True, originalAttempt=record['attemptId'],
        supervisorReason='SUPERVISOR_DEADLINE', originalWorkerMaxWallMs=60000, completeMatrixRequestedCases=30,
        completeMatrixVerified=False, importedEvaluations=0, catalogEvaluations=0, sourceApplications=0,
        sourceClaims=0, writerQuiescenceEstablished=True, workerUnresolvedEffects=None,
        partialWorkerStatesRetained=True, allOriginalAndCopiedFilesUnchanged=True, databases=database_hashes,
        locks=locks, phases=archive['phases'], originalHarnessUnsettledFlag=result['rawScratchMayContainUnsettledFixtureWork'],
        performanceRootCauseEstablished=False, physicalObjectiveVerified=False)
    with (BASE / 'source04-deadline-audit.json').open('x') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key:report[key] for key in ('originalScopePassed','supervisorReason','writerQuiescenceEstablished',
        'completeMatrixVerified','importedEvaluations','sourceApplications','workerUnresolvedEffects')}))
finally:
    for fd in held:
        os.close(fd)
