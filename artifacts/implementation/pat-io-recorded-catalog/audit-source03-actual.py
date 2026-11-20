"""Retain the actual state behind the source03 effect-row assertion failure."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

BASE = Path('artifacts/implementation/pat-io-recorded-catalog')
ATTEMPT = BASE / 'harness63/attempts/attempt01-actual'

def read(path):
    return json.loads(path.read_bytes())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

result = read(ATTEMPT / 'result.json')
assert result['status'] == 'failed' and result['childState'] == 'exited' and result['counts']['failures'] == 1
assert result['counts']['errors'] == 0 and result['errors'] == [] and result['scratchRetained']
assert 'AssertionError: 4 != 1' in (ATTEMPT / 'output.log').read_text()
work = Path(result['scratchPath']) / 'test_actual_original_matrix_catalog_execution_and_historical_replay'
copied = ATTEMPT / 'scratch' / work.name
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
    def database(relative, callback):
        path = work / relative; before = sha(path)
        assert before == sha(copied / relative)
        db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            value = callback(db)
        finally:
            db.close()
        assert before == sha(path) == sha(copied / relative)
        database_hashes.append(dict(path=relative, bytes=path.stat().st_size, sha256=before))
        return value
    def authority(db):
        assert db.execute('SELECT count(*) FROM claims').fetchone()[0] == 0
        assert db.execute('SELECT state FROM operations').fetchall() == [('completed',)]
        assert db.execute('SELECT state FROM pr_procedures').fetchall() == [('completed',)]
        assert db.execute('SELECT revision FROM iosc_versions ORDER BY sequence').fetchall() == [(1,)]
        assert db.execute('SELECT state FROM pc_entries').fetchall() == [('active',)]
        assert db.execute('SELECT count(*) FROM px_instances').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM pc_evaluations').fetchone()[0] == 1
        cat = json.loads(db.execute('SELECT document FROM pc_evaluations').fetchone()[0])
        imported = read(work / 'original-import.json')
        assert cat == read(work / 'recorded-evaluation.json')['receipt']
        assert cat['invocation']['importReceiptDigest'] == imported['receiptDigest']
        assert cat['invocation']['original'] == imported['receipt']['anchor']
        assert imported['evaluation']['inspectedCases'] == 30 and imported['evaluation']['unresolvedEffects'] == 0
        return cat
    catalog = database('runtime/authority.db', authority)
    board_path = next((work / 'runtime').glob('synthetic-io-board-*.db')).relative_to(work).as_posix()
    def board(db):
        assert [row[1] for row in db.execute('PRAGMA table_info(io_effects)')] == ['instance','activations','completed','canceled']
        assert db.execute('SELECT count(*) FROM io_owners').fetchone()[0] == 0
        rows = [list(row) for row in db.execute('SELECT * FROM io_effects')]
        selected = catalog['applicability']['roleInstances']['io']
        assert len(rows) == 4
        assert all(row[1:] == ([1,1,0] if row[0] == selected else [0,0,0]) for row in rows)
        assert sum(row[1] for row in rows) == sum(row[2] for row in rows) == 1
        return rows
    effects = database(board_path, board)
    def ledger(db):
        values = db.execute('SELECT record FROM qs_attempts').fetchall()
        assert len(values) == 1
        record = json.loads(values[0][0])
        assert record['state'] == 'archived' and record['archive']['transportComplete']
        assert record['attemptId'] == catalog['invocation']['original']['attemptId']
        return record['attemptId']
    attempt_id = database('supervisor/attempts.db', ledger)
    assert not (work / 'changed-context-refusal.json').exists() and not (work / 'recorded-integration-checks.json').exists()
    report = dict(originalScopePassed=False, originalFailureRetained=True, originalAttempt=attempt_id,
        completedWorkerCases=30, originalImportAndCatalogJoined=True, applicationInstances=1,
        applicationActivations=1, applicationCompletions=1, applicationCancellations=0,
        currentClaims=0, boardOwners=0, ownedLocksQuiescent=True, effectCounterRows=4, effects=effects,
        cause='io_effects is a pre-created per-instance counter table, not one row per invocation',
        afterConfigurationReplayReached=False, databaseHashesUnchanged=True, databases=database_hashes,
        locks=locks, physicalObjectiveVerified=False, independentReviewer=False)
    with (BASE / 'source03-actual-state-audit.json').open('x') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key:report[key] for key in ('originalScopePassed','applicationActivations','applicationCompletions',
        'currentClaims','boardOwners','ownedLocksQuiescent','afterConfigurationReplayReached')}))
finally:
    for fd in held:
        os.close(fd)
