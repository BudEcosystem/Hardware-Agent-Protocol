"""Exercise only the new test helper's bounded read-only SQLite contention path."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sqlite3
import sys
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent
SOURCE = Path('/home/bud/Desktop/bud/hms-harness-a1626788/packages/experimental/tool-hardware/tests/compact-launcher.py')
original = sys.argv
sys.argv = [str(SOURCE), str(HERE / 'runtime-fixture'), str(HERE / 'runtime-fixture/bin/endpoint-scenarios-pipe'), '/tmp/unused-observer-path']
spec = importlib.util.spec_from_file_location('compact_observer_test', SOURCE)
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
finally:
    sys.argv = original

results = []
with tempfile.TemporaryDirectory(prefix='hms-observer-read-test-') as temporary:
    state = Path(temporary)
    writer = sqlite3.connect(state / 'authority.db', check_same_thread=False)
    writer.execute('CREATE TABLE evidence(value INTEGER)')
    writer.execute('INSERT INTO evidence VALUES (7)')
    writer.commit()
    reader = module.Launcher.__new__(module.Launcher)
    reader.state = state
    writer.execute('BEGIN EXCLUSIVE')
    release = threading.Timer(0.3, writer.rollback)
    start = time.monotonic()
    release.start()
    try:
        assert reader.database('SELECT value FROM evidence') == [(7,)]
    finally:
        release.join(2)
        assert not release.is_alive()
    elapsed = time.monotonic() - start
    assert 0.2 <= elapsed < 2
    results.append({'case': 'read_waits_for_busy_then_reads', 'elapsed_seconds': elapsed})
    writer.execute('BEGIN EXCLUSIVE')
    start = time.monotonic()
    try:
        try:
            reader.database('SELECT value FROM evidence', deadline=start + 0.15)
        except (sqlite3.OperationalError, AssertionError):
            pass
        else:
            raise AssertionError('Locked read ignored its absolute deadline')
    finally:
        writer.rollback()
    elapsed = time.monotonic() - start
    assert elapsed < 1
    results.append({'case': 'busy_read_deadline_fails', 'elapsed_seconds': elapsed})
    start = time.monotonic()
    try:
        reader.database('SELECT value FROM absent_table')
    except sqlite3.OperationalError as error:
        assert error.sqlite_errorcode == sqlite3.SQLITE_ERROR
    else:
        raise AssertionError('Non-lock SQL error was hidden')
    assert time.monotonic() - start < 0.5
    results.append({'case': 'non_lock_error_propagates'})
    try:
        reader.database('UPDATE evidence SET value=8')
    except AssertionError:
        pass
    else:
        raise AssertionError('Observer accepted a mutation')
    assert writer.execute('SELECT value FROM evidence').fetchall() == [(7,)]
    results.append({'case': 'mutation_refused'})
    writer.close()
record = {'passed': True, 'cases': results, 'helper_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
          'scope': 'Test helper only; no HMS invocation, native C process or production changes. Genuine SQLite EXCLUSIVE lock and read-only connections.'}
(HERE / 'verification/observer-check.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
