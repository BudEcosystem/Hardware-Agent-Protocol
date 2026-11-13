"""The durable store of a BHMS server: one SQLite file in WAL mode (operations, history, events, programs, counters).

``Store`` is the single persistence layer of the runtime; device servers and gateways (Task 5 journals) use it alike.
It knows rows, not protocol rules: :mod:`bhms.runtime.operations` owns the state machine on top of it.

Durability (``durability=``), measured in ``benchmarks/invoke_roundtrip.py``:

* ``"dispatch"`` (default) — WAL with ``synchronous=NORMAL`` for ordinary commits and ``synchronous=FULL`` for every
  *barrier* commit (``transaction(barrier=True)``). The runtime writes the ``dispatching`` record of an operation and
  every fence counter in a barrier commit, so the intent is on stable storage (fsync of the WAL, which also covers every
  earlier frame) before the handler can act (BHMS-OPS-003) and fences never repeat (BHMS-LSE-003). Every commit
  survives a process crash (SIGKILL: the WAL frames are in the OS page cache). After a *power loss* a non-barrier
  commit can be lost: a recorded completion may then reappear as ``dispatching`` and be recovered as ``unknown``
  (BHMS-OPS-080) — the safe direction; an intent is never lost after dispatch.
* ``"full"`` — every commit is ``synchronous=FULL``.
* ``"process"`` — ``synchronous=NORMAL`` everywhere, no barriers: durable against process crashes only (not power
  loss). Not honest for physical devices whose controllers survive a host power loss; offered for simulators and
  benchmarks.

Checkpoints (copying the WAL back into the database file, which fsyncs) run in a background thread on its own
connection (``wal_autocheckpoint`` is off on the serving connection), so the event loop never stalls behind one.

A store file belongs to one process: an exclusive ``flock`` on ``<path>.lock`` is taken at open (:class:`StoreLocked`
otherwise) and released by the kernel even on SIGKILL. ``epoch`` is minted when the file is created and kept while it
exists (BHMS-OPS-034); an in-memory store (``path=None``) is not durable and has a new epoch every time.

Errors: any SQLite failure on a write raises :class:`StoreError`; the transaction is rolled back.

Example::

    store = Store("/var/lib/bhms/bench.sqlite3")
    with store.transaction(barrier=True):
        store.insert_operation(...)

Thread-safety: one thread (the server's event loop) uses a store; it is not shared across threads.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import secrets
import logging
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orjson

DURABILITY_MODES = ("dispatch", "full", "process")
log = logging.getLogger("bhms.store")
_SCHEMA_VERSION = "1"

_DDL = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operations(
  id TEXT PRIMARY KEY, principal TEXT NOT NULL, op_key TEXT NOT NULL, request_digest TEXT NOT NULL,
  kind TEXT NOT NULL, device_id TEXT, parent_id TEXT, state TEXT NOT NULL,
  created_ns INTEGER NOT NULL, updated_ns INTEGER NOT NULL, record BLOB NOT NULL, private BLOB NOT NULL,
  UNIQUE(principal, op_key));
CREATE INDEX IF NOT EXISTS operations_created ON operations(created_ns DESC, id);
CREATE INDEX IF NOT EXISTS operations_state ON operations(state);
CREATE INDEX IF NOT EXISTS operations_parent ON operations(parent_id);
CREATE TABLE IF NOT EXISTS history(op_id TEXT NOT NULL, seq INTEGER NOT NULL, entry BLOB NOT NULL,
  PRIMARY KEY(op_id, seq)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, time_ns INTEGER NOT NULL,
  type TEXT NOT NULL, device_id TEXT, event BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS programs(digest TEXT PRIMARY KEY, program BLOB NOT NULL, info BLOB NOT NULL,
  created_ns INTEGER NOT NULL);
"""


class StoreError(RuntimeError):
    """A write to the store failed (disk full, read-only, I/O error, constraint); nothing was committed."""


class StoreLocked(RuntimeError):
    """Another process holds the store file."""


@dataclass(frozen=True, slots=True)
class StoredOperation:
    """One ``operations`` row: the wire record (without history), its owner and server-private data."""

    id: str
    principal: str
    record: dict[str, Any]
    private: dict[str, Any]
    created_ns: int


def _loads(blob: bytes) -> Any:
    return orjson.loads(blob)


class Store:
    """SQLite-backed durable store; see the module docstring.

    Args:
        path: database file (created with its directory), or ``None`` for a non-durable in-memory store.
        durability: ``"dispatch"`` (default), ``"full"`` or ``"process"``.
    """

    def __init__(self, path: str | os.PathLike[str] | None, *, durability: str = "dispatch") -> None:
        if durability not in DURABILITY_MODES:
            raise ValueError(f"durability must be one of {', '.join(DURABILITY_MODES)}, got {durability!r}")
        self.durability = durability
        self.path = None if path is None or str(path) == ":memory:" else Path(path)
        self.durable = self.path is not None
        self._lock_fd: int | None = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._lock_fd = os.open(f"{self.path}.lock", os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(self._lock_fd)
                self._lock_fd = None
                raise StoreLocked(f"{self.path} is in use by another process; one server owns one store") from None
        self._db = sqlite3.connect(":memory:" if self.path is None else str(self.path), isolation_level=None,
                                   check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._sync = ""
        self._set_sync("FULL" if durability == "full" else "NORMAL")
        self._db.executescript(_DDL)
        self._in_txn = False
        self._promote = False
        self._owner = threading.get_ident()
        self._checkpointer: _Checkpointer | None = None
        if self.path is not None:
            self._db.execute("PRAGMA wal_autocheckpoint=0")
            self._checkpointer = _Checkpointer(self.path)
        existing = self.meta_get("epoch")
        self.created = existing is None
        if existing is None:
            with self.transaction(barrier=True):
                self.meta_set("epoch", secrets.token_hex(8))
                self.meta_set("schemaVersion", _SCHEMA_VERSION)
        self.epoch: str = self.meta_get("epoch") or ""

    # ------------------------------------------------------------------ lifecycle

    def close(self) -> None:
        """Close the database (after a final checkpoint) and release the file lock (idempotent)."""
        if self._checkpointer is not None:
            self._checkpointer.stop()
            self._checkpointer = None
        with contextlib.suppress(sqlite3.Error):
            self._db.close()
        if self._lock_fd is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            self._lock_fd = None

    def _set_sync(self, level: str) -> None:
        if level != self._sync:
            self._db.execute(f"PRAGMA synchronous={level}")
            self._sync = level

    def set_writable(self, writable: bool) -> None:
        """Switch the connection to SQLite's ``query_only`` mode (every write fails) or back.

        Used to model an unwritable journal (BHMS-OPS-003, BHMS-AUTH-025) by the conformance device's fault injection.
        """
        self._db.execute(f"PRAGMA query_only={'OFF' if writable else 'ON'}")

    def probe_writable(self) -> bool:
        """True when a write can be committed now (used to lift a degraded-audit refusal, BHMS-AUTH-025)."""
        try:
            with self.transaction():
                self._db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('probe', '1')")
            return True
        except StoreError:
            return False

    def execute_scalar(self, sql: str, args: Sequence[Any] = ()) -> Any:
        """Run a read-only query and return the first column of the first row (diagnostics)."""
        row = self._db.execute(sql, args).fetchone()
        return row[0] if row else None

    @contextlib.contextmanager
    def transaction(self, *, barrier: bool = False) -> Iterator[None]:
        """One write transaction. ``barrier=True`` commits with fsync unless ``durability="process"``.

        Nested use joins the outer transaction (a barrier inside makes the outer commit a barrier).
        """
        if threading.get_ident() != self._owner:
            # The in-transaction flag is not locked: a second thread could join another thread's transaction and
            # return from a barrier before it is durable (BHMS-OPS-003).
            raise StoreError("the journal may only be written from the thread that opened it (the event loop); "
                             "marshal calls from worker threads with loop.call_soon_threadsafe")
        if self._in_txn:
            if barrier and self.durability != "process" and self._sync != "FULL":
                # SQLite cannot change the safety level inside a transaction: promote after the outer commit.
                self._promote = True
            yield
            return
        if self.durability == "dispatch":
            self._set_sync("FULL" if barrier else "NORMAL")
        try:
            self._db.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise StoreError(f"cannot start a journal write: {exc}") from exc
        self._in_txn = True
        try:
            yield
            self._db.execute("COMMIT")
            if self._checkpointer is not None:
                self._checkpointer.committed()
            if self._promote:
                self._in_txn = False
                self._fsync_barrier()
        except BaseException as exc:
            with contextlib.suppress(sqlite3.Error):
                self._db.execute("ROLLBACK")
            if isinstance(exc, sqlite3.Error):
                raise StoreError(f"journal write failed: {exc}") from exc
            raise
        finally:
            self._in_txn = False
            self._promote = False

    def _fsync_barrier(self) -> None:
        """Force everything committed so far onto stable storage (a nested barrier inside a NORMAL transaction).

        A FULL commit fsyncs the WAL, which covers every earlier frame; the marker row is the write that commit needs.
        """
        self._set_sync("FULL")
        try:
            self._db.execute("BEGIN IMMEDIATE")
            self._db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('barrier', hex(randomblob(4)))")
            self._db.execute("COMMIT")
        except sqlite3.Error as exc:
            with contextlib.suppress(sqlite3.Error):
                self._db.execute("ROLLBACK")
            raise StoreError(f"journal barrier failed: {exc}") from exc

    def _write(self, sql: str, args: Sequence[Any]) -> sqlite3.Cursor:
        try:
            return self._db.execute(sql, args)
        except sqlite3.Error as exc:
            raise StoreError(f"journal write failed: {exc}") from exc

    # ------------------------------------------------------------------ meta and counters

    def meta_get(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def meta_set(self, key: str, value: str) -> None:
        with self.transaction():
            self._write("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, value))

    def next_counter(self, name: str) -> int:
        """Increment and return a server-wide monotonic counter (fences, BHMS-LSE-003); committed as a barrier."""
        with self.transaction(barrier=True):
            value = int(self.meta_get(f"counter:{name}") or "0") + 1
            self._write("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (f"counter:{name}", str(value)))
        return value

    def counter(self, name: str) -> int:
        return int(self.meta_get(f"counter:{name}") or "0")

    # ------------------------------------------------------------------ operations

    def insert_operation(self, *, op_id: str, principal: str, key: str, request_digest: str, kind: str,
                         device_id: str | None, parent_id: str | None, state: str, created_ns: int,
                         record: dict[str, Any], private: dict[str, Any], history: Sequence[dict[str, Any]]) -> None:
        with self.transaction():
            self._write("INSERT INTO operations(id, principal, op_key, request_digest, kind, device_id, parent_id, "
                        "state, created_ns, updated_ns, record, private) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (op_id, principal, key, request_digest, kind, device_id, parent_id, state, created_ns,
                         created_ns, orjson.dumps(record), orjson.dumps(private)))
            for entry in history:
                self._write("INSERT INTO history(op_id, seq, entry) VALUES(?,?,?)",
                            (op_id, entry["seq"], orjson.dumps(entry)))

    def update_operation(self, op_id: str, *, state: str, updated_ns: int, record: dict[str, Any],
                         history: Sequence[dict[str, Any]] = (), private: dict[str, Any] | None = None) -> None:
        with self.transaction():
            if private is None:
                self._write("UPDATE operations SET state=?, updated_ns=?, record=? WHERE id=?",
                            (state, updated_ns, orjson.dumps(record), op_id))
            else:
                self._write("UPDATE operations SET state=?, updated_ns=?, record=?, private=? WHERE id=?",
                            (state, updated_ns, orjson.dumps(record), orjson.dumps(private), op_id))
            for entry in history:
                self._write("INSERT INTO history(op_id, seq, entry) VALUES(?,?,?)",
                            (op_id, entry["seq"], orjson.dumps(entry)))

    _OP_COLUMNS = "id, principal, record, private, created_ns"

    @staticmethod
    def _row(row: Any) -> StoredOperation:
        return StoredOperation(row[0], row[1], _loads(row[2]), _loads(row[3]), row[4])

    def get_operation(self, op_id: str) -> StoredOperation | None:
        row = self._db.execute(f"SELECT {self._OP_COLUMNS} FROM operations WHERE id=?", (op_id,)).fetchone()
        return self._row(row) if row else None

    def find_key(self, principal: str, key: str) -> StoredOperation | None:
        row = self._db.execute(f"SELECT {self._OP_COLUMNS} FROM operations WHERE principal=? AND op_key=?",
                               (principal, key)).fetchone()
        return self._row(row) if row else None

    def history(self, op_id: str) -> list[dict[str, Any]]:
        return [_loads(r[0]) for r in self._db.execute("SELECT entry FROM history WHERE op_id=? ORDER BY seq",
                                                        (op_id,))]

    def operations_in_states(self, states: Sequence[str]) -> list[StoredOperation]:
        marks = ",".join("?" * len(states))
        return [self._row(r) for r in self._db.execute(
            f"SELECT {self._OP_COLUMNS} FROM operations WHERE state IN ({marks}) ORDER BY created_ns, id", states)]

    def children(self, parent_id: str) -> list[StoredOperation]:
        return [self._row(r) for r in self._db.execute(
            f"SELECT {self._OP_COLUMNS} FROM operations WHERE parent_id=? ORDER BY created_ns, id", (parent_id,))]

    def list_operations(self, *, principal: str | None, device_id: str | None = None, state: str | None = None,
                        parent_id: str | None = None, after: tuple[int, str] | None = None,
                        limit: int = 100) -> list[StoredOperation]:
        """Operations newest first (``created_ns`` descending, then ``id`` ascending, BHMS-LIF-062)."""
        where, args = [], []
        for column, value in (("principal", principal), ("device_id", device_id), ("state", state),
                              ("parent_id", parent_id)):
            if value is not None:
                where.append(f"{column}=?")
                args.append(value)
        if after is not None:
            where.append("(created_ns < ? OR (created_ns = ? AND id > ?))")
            args += [after[0], after[0], after[1]]
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._db.execute(f"SELECT {self._OP_COLUMNS} FROM operations {clause} "
                                "ORDER BY created_ns DESC, id ASC LIMIT ?", (*args, limit))
        return [self._row(r) for r in rows]

    def prune_operations(self, settled_states: Sequence[str], before_ns: int) -> int:
        """Delete settled operations last updated before ``before_ns`` (key retention, BHMS-OPS-034)."""
        marks = ",".join("?" * len(settled_states))
        with self.transaction():
            ids = [r[0] for r in self._db.execute(
                f"SELECT id FROM operations WHERE state IN ({marks}) AND updated_ns < ?", (*settled_states, before_ns))]
            for op_id in ids:
                self._write("DELETE FROM history WHERE op_id=?", (op_id,))
                self._write("DELETE FROM operations WHERE id=?", (op_id,))
        return len(ids)

    # ------------------------------------------------------------------ events

    def append_event(self, *, time_ns: int, type: str, device_id: str | None, event: dict[str, Any]) -> int:
        """Append an event body (without its cursor) and return its sequence number."""
        with self.transaction():
            cursor = self._write("INSERT INTO events(time_ns, type, device_id, event) VALUES(?,?,?,?)",
                                 (time_ns, type, device_id, orjson.dumps(event)))
        return int(cursor.lastrowid or 0)

    def read_events(self, *, after: int, limit: int, device_ids: Sequence[str] | None = None,
                    types: Sequence[str] | None = None, upto: int | None = None) -> list[tuple[int, dict[str, Any]]]:
        where, args = ["seq > ?"], [after]
        if upto is not None:
            where.append("seq <= ?")
            args.append(upto)
        if device_ids is not None:
            where.append(f"device_id IN ({','.join('?' * len(device_ids))})")
            args += list(device_ids)
        if types is not None:
            where.append(f"type IN ({','.join('?' * len(types))})")
            args += list(types)
        rows = self._db.execute(f"SELECT seq, event FROM events WHERE {' AND '.join(where)} ORDER BY seq LIMIT ?",
                                (*args, limit))
        return [(r[0], _loads(r[1])) for r in rows]

    def event_bounds(self) -> tuple[int, int]:
        """(lowest retained seq or 0, highest seq ever assigned or 0)."""
        low = self._db.execute("SELECT MIN(seq) FROM events").fetchone()[0] or 0
        row = self._db.execute("SELECT seq FROM sqlite_sequence WHERE name='events'").fetchone()
        return low, (row[0] if row else 0)

    def prune_events(self, before_ns: int) -> int:
        """Delete events recorded before ``before_ns``; records the highest pruned seq for gap detection."""
        with self.transaction():
            top = self._db.execute("SELECT MAX(seq) FROM events WHERE time_ns < ?", (before_ns,)).fetchone()[0]
            if top is None:
                return 0
            cursor = self._write("DELETE FROM events WHERE seq <= ?", (top,))
            pruned = max(int(self.meta_get("eventsPrunedThrough") or "0"), int(top))
            self._write("INSERT OR REPLACE INTO meta(key, value) VALUES('eventsPrunedThrough', ?)", (str(pruned),))
        return cursor.rowcount

    def events_pruned_through(self) -> int:
        return int(self.meta_get("eventsPrunedThrough") or "0")

    # ------------------------------------------------------------------ programs registry

    def put_program(self, digest: str, program: dict[str, Any], info: dict[str, Any], created_ns: int) -> None:
        with self.transaction():
            self._write("INSERT OR IGNORE INTO programs(digest, program, info, created_ns) VALUES(?,?,?,?)",
                        (digest, orjson.dumps(program), orjson.dumps(info), created_ns))

    def get_program(self, digest: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        row = self._db.execute("SELECT program, info FROM programs WHERE digest=?", (digest,)).fetchone()
        return (_loads(row[0]), _loads(row[1])) if row else None

    def list_programs(self, *, after: str | None, limit: int) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT info FROM programs WHERE digest > ? ORDER BY digest LIMIT ?",
                                (after or "", limit))
        return [_loads(r[0]) for r in rows]


class _Checkpointer:
    """Runs ``PRAGMA wal_checkpoint(PASSIVE)`` off the event loop: every ``every`` commits or ``interval_s`` seconds.

    A passive checkpoint never blocks the serving connection's writers; it copies what it can and fsyncs the database
    file in this thread. ``stop`` runs a final ``TRUNCATE`` checkpoint.
    """

    def __init__(self, path: Path, *, every: int = 256, interval_s: float = 1.0) -> None:
        self._path, self._every, self._interval = path, every, interval_s
        self._pending = 0
        self._wake = threading.Event()
        self._stopping = False
        self._thread = threading.Thread(target=self._loop, name="bhms-store-checkpoint", daemon=True)
        self._thread.start()

    def committed(self) -> None:
        if not self._stopping and not self._thread.is_alive():
            # The thread died (it never does on an ordinary error): restart it, or the WAL would grow unbounded.
            log.error("the WAL checkpoint thread died; restarting it")
            self._thread = threading.Thread(target=self._loop, name="bhms-store-checkpoint", daemon=True)
            self._thread.start()
        self._pending += 1
        if self._pending >= self._every:
            self._pending = 0
            self._wake.set()

    def _loop(self) -> None:
        db = sqlite3.connect(str(self._path), isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=5000")
            while not self._stopping:
                self._wake.wait(self._interval)
                self._wake.clear()
                try:
                    db.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchall()
                except sqlite3.Error as exc:
                    log.warning("WAL checkpoint failed: %s", exc)
            with contextlib.suppress(sqlite3.Error):
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        finally:
            db.close()

    def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        self._thread.join(timeout=10)
