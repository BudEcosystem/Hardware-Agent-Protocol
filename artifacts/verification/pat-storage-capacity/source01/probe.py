"""Original, finite SQLite allocation experiments. No HMS/project imports."""
import hashlib
import json
import os
from pathlib import Path
import resource
import sqlite3
import sys

ROOT = Path(sys.argv[1]).resolve(strict=True)
assert ROOT.is_dir() and not list(ROOT.iterdir())
os.umask(0o077)
resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
NAMES = ('full.db', 'freelist.db', 'reopen.db', 'journal.db', 'split.db', 'bulk.db')
PATHS = {name: ROOT / name for name in NAMES}
open_counts = {str(path): 0 for path in PATHS.values()}
attach_count = 0


def audit(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in (
            'os.system', 'os.fork', 'os.forkpty', 'os.exec', 'os.posix_spawn'):
        raise RuntimeError('external execution/network veto')
    if event == 'sqlite3.connect':
        key = str(args[0])
        assert key in open_counts and key != str(PATHS['bulk.db'])
        open_counts[key] += 1
        assert open_counts[key] <= (2 if key == str(PATHS['reopen.db']) else 1)
    if event == 'open':
        path, mode, flags = args
        if isinstance(path, (str, bytes)) and (flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)):
            assert Path(os.fsdecode(path)).resolve().parent == ROOT


sys.addaudithook(audit)


def scalar(db, sql):
    rows = db.execute(sql).fetchall()
    assert len(rows) == 1 and len(rows[0]) == 1
    return rows[0][0]


def authorizer(action, arg1, arg2, schema, trigger):
    global attach_count
    if action == sqlite3.SQLITE_ATTACH:
        assert arg1 == str(PATHS['bulk.db']) and attach_count == 0
        attach_count += 1
    if action == sqlite3.SQLITE_DETACH:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and arg2 == 'load_extension':
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def connect(name, cap, fresh=True):
    path = PATHS[name]
    if fresh:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    else:
        assert path.is_file() and not path.is_symlink()
    db = sqlite3.connect(str(path), isolation_level=None, timeout=0.2)
    db.set_authorizer(authorizer)
    if fresh:
        db.execute('PRAGMA page_size=1024')
    assert scalar(db, 'PRAGMA page_size') == 1024
    assert scalar(db, 'PRAGMA journal_mode=DELETE') == 'delete'
    db.execute('PRAGMA synchronous=EXTRA')
    assert scalar(db, 'PRAGMA synchronous') == 3
    db.execute('PRAGMA temp_store=MEMORY')
    previous_cap = scalar(db, 'PRAGMA max_page_count')
    assert scalar(db, 'PRAGMA max_page_count=' + str(cap)) == cap
    return db, previous_cap


def state(db, schema='main'):
    assert schema in ('main', 'bulk')
    return {key: scalar(db, 'PRAGMA ' + schema + '.' + key)
            for key in ('page_size', 'page_count', 'freelist_count', 'max_page_count')}


def failure(db, work):
    try:
        work()
    except sqlite3.OperationalError as exc:
        record = dict(code=exc.sqlite_errorcode, name=exc.sqlite_errorname,
                      message=str(exc), transactionActiveOnError=db.in_transaction)
        assert exc.sqlite_errorcode == sqlite3.SQLITE_FULL
        if db.in_transaction:
            db.execute('ROLLBACK')
        assert not db.in_transaction
        return record
    raise AssertionError('Expected a bounded SQLITE_FULL failure')


results = {}
db, _ = connect('full.db', 32)
try:
    db.execute('CREATE TABLE control(id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
    db.execute('CREATE TABLE evidence(id INTEGER PRIMARY KEY, body BLOB NOT NULL)')
    db.execute("INSERT INTO control VALUES(1,'original')")
    initial = state(db)
    db.execute('BEGIN IMMEDIATE')
    db.execute("INSERT INTO control VALUES(2,'must rollback')")
    def fill_transaction():
        for number in range(64):
            db.execute('INSERT INTO evidence VALUES(?,?)', (number, bytes(2000)))
    error = failure(db, fill_transaction)
    assert scalar(db, 'SELECT count(*) FROM control') == 1
    assert scalar(db, 'SELECT count(*) FROM evidence') == 0
    db.execute("INSERT INTO control VALUES(3,'control after rollback')")
    results['fullRollback'] = dict(initial=initial, error=error, final=state(db),
                                   originalRetained=True, failedWritesAbsent=True,
                                   laterControlWriteSucceeded=True)
finally:
    db.close()

db, _ = connect('freelist.db', 64)
try:
    db.execute('CREATE TABLE evidence(id INTEGER PRIMARY KEY, body BLOB NOT NULL)')
    db.execute('BEGIN IMMEDIATE')
    for number in range(16):
        db.execute('INSERT INTO evidence VALUES(?,?)', (number, bytes(2000)))
    db.execute('COMMIT')
    seeded = state(db)
    # Delete only this experiment's explicitly disposable synthetic rows.
    db.execute('DELETE FROM evidence WHERE id < 8')
    deleted = state(db)
    assert deleted['page_count'] == seeded['page_count'] and deleted['freelist_count'] > 0
    requested = deleted['page_count'] - 1
    readback = scalar(db, 'PRAGMA max_page_count=' + str(requested))
    assert readback == deleted['page_count'] > requested
    db.execute('INSERT INTO evidence VALUES(100,?)', (bytes(2000),))
    reused = state(db)
    assert reused['page_count'] == deleted['page_count']
    assert reused['freelist_count'] < deleted['freelist_count']
    results['freelist'] = dict(seeded=seeded, deleted=deleted, requestedCap=requested,
                               actualCap=readback, afterEvidenceInsert=reused)
finally:
    db.close()

db, default_cap = connect('reopen.db', 16)
try:
    db.execute('CREATE TABLE control(id INTEGER PRIMARY KEY)')
    db.execute('INSERT INTO control VALUES(1)')
    before_close = state(db)
finally:
    db.close()
db, reopened_cap = connect('reopen.db', 16, fresh=False)
try:
    assert scalar(db, 'SELECT count(*) FROM control') == 1
    results['reopen'] = dict(initialDefaultCap=default_cap, beforeClose=before_close,
                             observedCapBeforeReapplication=reopened_cap,
                             capPersisted=(reopened_cap == 16), final=state(db),
                             noDataMutationBeforeReapplication=True)
finally:
    db.close()

db, _ = connect('journal.db', 64)
try:
    assert scalar(db, 'PRAGMA journal_size_limit=0') == 0
    db.execute('CREATE TABLE evidence(id INTEGER PRIMARY KEY, body BLOB NOT NULL)')
    db.execute('BEGIN IMMEDIATE')
    for number in range(8):
        db.execute('INSERT INTO evidence VALUES(?,?)', (number, bytes(2000)))
    db.execute('COMMIT')
    db.execute('BEGIN IMMEDIATE')
    db.execute('UPDATE evidence SET body=?', (b'x' * 2000,))
    live = Path(str(PATHS['journal.db']) + '-journal')
    live_bytes = live.stat().st_size
    assert 0 < live_bytes < 1024 * 1024
    db.execute('COMMIT')
    assert not live.exists()
    results['liveJournal'] = dict(configuredRetainedLimit=0, liveJournalBytes=live_bytes,
                                  journalAbsentAfterCommit=True, final=state(db))
finally:
    db.close()

db, _ = connect('split.db', 32)
try:
    fd = os.open(PATHS['bulk.db'], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    db.execute('ATTACH DATABASE ? AS bulk', (str(PATHS['bulk.db']),))
    db.execute('PRAGMA bulk.page_size=1024')
    assert scalar(db, 'PRAGMA bulk.journal_mode=DELETE') == 'delete'
    db.execute('PRAGMA bulk.synchronous=EXTRA')
    assert scalar(db, 'PRAGMA bulk.synchronous') == 3
    assert scalar(db, 'PRAGMA bulk.max_page_count=16') == 16
    db.execute('CREATE TABLE main.control(id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
    db.execute('CREATE TABLE bulk.evidence(id INTEGER PRIMARY KEY, body BLOB NOT NULL)')
    db.execute("INSERT INTO main.control VALUES(1,'original')")
    committed = 0
    def fill_committed():
        global committed
        for number in range(32):
            db.execute('INSERT INTO bulk.evidence VALUES(?,?)', (number, bytes(2000)))
            committed += 1
    first_error = failure(db, fill_committed)
    assert 0 < committed < 32
    bulk_before = state(db, 'bulk')
    db.execute('BEGIN IMMEDIATE')
    db.execute("INSERT INTO main.control VALUES(2,'must rollback')")
    second_error = failure(db, lambda: db.execute('INSERT INTO bulk.evidence VALUES(100,?)', (bytes(2000),)))
    assert scalar(db, 'SELECT count(*) FROM main.control') == 1
    assert scalar(db, 'SELECT count(*) FROM bulk.evidence') == committed
    db.execute("INSERT INTO main.control VALUES(3,'independent control')")
    assert scalar(db, 'SELECT count(*) FROM main.control') == 2
    assert state(db, 'bulk') == bulk_before
    results['separateFiles'] = dict(firstError=first_error, crossDatabaseError=second_error,
        committedEvidenceRows=committed, bulk=bulk_before, control=state(db),
        failedCrossDatabaseMarkerAbsent=True, originalEvidenceRetained=True,
        independentControlWriteSucceeded=True, physicalSpaceReservationProved=False,
        powerLossTested=False)
finally:
    db.close()

assert sum(open_counts.values()) == 6 and attach_count == 1
files = []
for path in sorted(ROOT.iterdir()):
    assert path.name in NAMES and path.is_file() and not path.is_symlink()
    body = path.read_bytes()
    assert len(body) <= 64 * 1024
    files.append(dict(path=path.name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
assert len(files) == 6 and sum(row['bytes'] for row in files) <= 384 * 1024
report = dict(status='passed', sqliteVersion=sqlite3.sqlite_version, pythonVersion=sys.version,
              cases=results, files=files, sqliteConnections=sum(open_counts.values()),
              attachedDatabases=attach_count, acquiredCodeExecuted=False,
              hardwareEffects=False, productionImports=False,
              aggregateFilesystemQuotaEnforced=False)
encoded = json.dumps(report, indent=2).encode() + b'\n'
assert len(encoded) <= 64 * 1024
sys.stdout.buffer.write(encoded)
