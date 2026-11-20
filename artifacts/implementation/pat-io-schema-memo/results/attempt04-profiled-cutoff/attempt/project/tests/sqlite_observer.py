"""Bounded read-only SQLite observations used by live transport tests."""
import contextlib
from pathlib import Path
import sqlite3
import time


def readonly_rows(path, query, params=(), *, timeout=3.0, report=None):
    """Bounded test-observer reads; never retry commands or change their timing.

    Only SQLite BUSY can retry. Every attempt opens mode=ro and closes on both
    success and failure. The three-second budget belongs to this observer,
    independently of all operation, lease and freshness deadlines.
    """
    if type(timeout) not in {int, float} or not 0 < timeout <= 3.0:
        raise ValueError('invalid observer read budget')
    entry = report if report is not None else {}
    entry.update(query=query, parameters=list(params), readBudgetSeconds=timeout,
                 attempts=0, busyRetries=0, succeeded=False)
    started = time.monotonic()
    deadline = started + timeout
    busy = None
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 and busy is not None:
                raise busy
            entry['attempts'] += 1
            try:
                with contextlib.closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro',
                        uri=True, timeout=max(0, min(.1, remaining)))) as database:
                    rows = database.execute(query, params).fetchall()
                entry.update(succeeded=True, rowCount=len(rows))
                return rows
            except sqlite3.OperationalError as error:
                code = getattr(error, 'sqlite_errorcode', None)
                if code is None or code & 0xff != sqlite3.SQLITE_BUSY:
                    raise
                busy = error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                entry['busyRetries'] += 1
                time.sleep(min(.01, remaining))
    except sqlite3.Error as error:
        entry['error'] = {'message': str(error), 'code': getattr(error, 'sqlite_errorcode', None),
                          'name': getattr(error, 'sqlite_errorname', None)}
        raise
    finally:
        entry['elapsedSeconds'] = time.monotonic() - started


def admission_snapshot(path, namespace, key, *, procedures=False, report=None):
    """Read counts and replay-key presence from one SQLite statement snapshot.

    The closed table list is test instrumentation, not caller-supplied SQL.
    Read-only BUSY retries repeat this whole observation, never an admission.
    """
    tables = ('operations', 'claims', 'ep_commands')
    if procedures:
        tables += ('pr_procedures', 'pr_keys')
    query = 'SELECT ' + ', '.join('(SELECT count(*) FROM ' + table + ')' for table in tables)
    query += ', EXISTS(SELECT 1 FROM replay_keys WHERE namespace=? AND caller_key=?)'
    row, = readonly_rows(path, query, (namespace, key), report=report)
    return tuple(row[:-1]), bool(row[-1])
