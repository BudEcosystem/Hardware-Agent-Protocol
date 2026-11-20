"""Bounded single-owner append-only planning history; no device/model callbacks."""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import threading

from hms.contracts import ContractError, canonical, parse_json
from hms.pat_contracts import pat_digest

from . import integrity
from .contracts import (HandoffError, MAX_RECORD, QUALIFICATION, checked_request,
                        closed, detached, identity, integer, name, require)

DDL = (
    'CREATE TABLE ih_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), body BLOB NOT NULL)',
    'CREATE TABLE ih_records (sequence INTEGER PRIMARY KEY, body BLOB NOT NULL)',
)
PROFILE = 'hms.application-intent-store/0.1'
MAX_RECORDS = 129
MAX_BYTES = 8 * 1024 * 1024
ROW_OVERHEAD = 40  # Logical sequence/record framing charge, not SQLite physical bytes.


def limits(value):
    closed(value, {'maxRecords', 'maxBytes'})
    integer(value['maxRecords'], 1, MAX_RECORDS)
    integer(value['maxBytes'], 512, MAX_BYTES)
    return detached(value)


class IntentStore:
    """Trusted constructor anchors identity/owner/caps on both create and reopen.

    The embedding ingress authenticates principal; request JSON cannot set it.
    File content is not a cryptographic proof against the owner rewriting a
    completely coherent history. No external effect can be admitted here.
    """
    def __init__(self, path, *, owner, store_id, capacity, create=False):
        self._db = None
        self._lock = threading.RLock()
        try:
            name(owner); name(store_id)
            require(type(create) is bool)
            capacity = limits(capacity)
            parser = integrity.verify(loaded=True)
            self._meta = dict(profile=PROFILE, owner=owner, storeId=store_id,
                              capacity=capacity, parserIdentity=parser)
            self._meta_wire = canonical(self._meta)
            require(len(self._meta_wire) + ROW_OVERHEAD <= capacity['maxBytes'], 'CAPACITY')
            self.path = Path(path).absolute()
            require(not self.path.is_symlink(), 'STORAGE_UNAVAILABLE')
            if create:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(fd)
            self._db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True,
                isolation_level=None, timeout=5, check_same_thread=False)
            self._db.execute('PRAGMA trusted_schema=OFF')
            self._db.execute('PRAGMA synchronous=FULL')
            if create:
                self._db.execute('PRAGMA journal_mode=DELETE')
                with self._transaction():
                    for statement in DDL:
                        self._db.execute(statement)
                    self._db.execute('INSERT INTO ih_meta VALUES (1,?)', (self._meta_wire,))
            with self._transaction():
                self._load()
        except HandoffError:
            self.close(); raise
        except (OSError, sqlite3.Error, ContractError, ValueError, TypeError) as error:
            self.close()
            raise HandoffError('STORAGE_UNAVAILABLE') from error

    def close(self):
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None

    @contextmanager
    def _transaction(self):
        with self._lock:
            require(self._db is not None, 'CLOSED')
            self._db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self._db.execute('COMMIT')
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute('ROLLBACK')
                raise

    def _schema(self):
        checks = self._db.execute('SELECT typeof(name),length(CAST(name AS BLOB)),typeof(type),'
            'length(CAST(type AS BLOB)),typeof(tbl_name),length(CAST(tbl_name AS BLOB)),'
            'typeof(sql),length(CAST(sql AS BLOB)) FROM sqlite_master LIMIT 4').fetchall()
        require(len(checks) == 2 and all(row[::2] == ('text', 'text', 'text', 'text') and
                all(type(size) is int and 1 <= size <= 1024 for size in row[1::2]) for row in checks), 'CORRUPT')
        rows = self._db.execute('SELECT name,type,tbl_name,sql FROM sqlite_master LIMIT 4').fetchall()
        expected = {(name, 'table', name, statement)
                    for name, statement in zip(('ih_meta', 'ih_records'), DDL)}
        require(len(rows) == 2 and set(rows) == expected, 'CORRUPT')
        require(not self._db.execute('SELECT 1 FROM sqlite_temp_master LIMIT 1').fetchall(), 'CORRUPT')

    def _load(self):
        """Bound types/lengths before fetching blobs; replay the complete history."""
        self._schema()
        checks = self._db.execute('SELECT typeof(singleton),singleton,typeof(body),length(body) FROM ih_meta LIMIT 2').fetchall()
        require(len(checks) == 1 and checks[0][:3] == ('integer', 1, 'blob') and
                0 < checks[0][3] <= 2048, 'CORRUPT')
        raw = self._db.execute('SELECT body FROM ih_meta WHERE singleton=1').fetchone()[0]
        require(raw == self._meta_wire, 'METADATA_CHANGED')
        capacity = self._meta['capacity']
        rows = self._db.execute('SELECT typeof(sequence),sequence,typeof(body),length(body) '
            'FROM ih_records ORDER BY sequence LIMIT ?', (capacity['maxRecords'] + 1,)).fetchall()
        require(len(rows) + 1 <= capacity['maxRecords'], 'CORRUPT')
        used = len(raw) + ROW_OVERHEAD
        for index, row in enumerate(rows, 1):
            require(row[:3] == ('integer', index, 'blob') and 0 < row[3] <= MAX_RECORD, 'CORRUPT')
            used += row[3] + ROW_OVERHEAD
        require(used <= capacity['maxBytes'], 'CORRUPT')
        state = dict(heads={}, intents={}, proposals={}, keys={}, count=len(rows) + 1, used=used)
        for sequence, body in self._db.execute('SELECT sequence,body FROM ih_records ORDER BY sequence'):
            try:
                record = parse_json(body)
                closed(record, {'method', 'request', 'result'})
                require(canonical(record) == body, 'CORRUPT')
                method = record['method']
                require(method in ('intent_put', 'proposal_put'), 'CORRUPT')
                request = checked_request(method, record['request'])
                key = request['operationKey']
                require(key not in state['keys'], 'CORRUPT')
                result = self._apply(state, method, request)
                require(canonical(result) == canonical(record['result']), 'CORRUPT')
                state['keys'][key] = (method, canonical(request), result)
            except (HandoffError, ContractError, TypeError, ValueError, KeyError, RecursionError) as error:
                raise HandoffError('CORRUPT') from error
        return state

    def _apply(self, state, method, request):
        app = request['applicationId']
        current = state['heads'].get(app, 0)
        if method == 'intent_put':
            require(request['expectedRevision'] == current, 'REVISION_CONFLICT')
            integer(current + 1, 1)
            revision = current + 1
            intent_id = identity('HMS-APPLICATION-INTENT-v0.1', dict(storeId=self._meta['storeId'],
                applicationId=app, revision=revision, prompt=request['prompt']))
            handoff = identity('HMS-APPLICATION-HANDOFF-v0.1', dict(storeId=self._meta['storeId'],
                applicationId=app, revision=revision, intentDigest=intent_id))
            result = dict(profile='hms.application-intent-receipt/0.1', storeId=self._meta['storeId'],
                applicationId=app, revision=revision, intentDigest=intent_id,
                handoffDigest=handoff, state='awaiting_proposal', qualification=QUALIFICATION)
            state['heads'][app] = revision
            state['intents'][app, revision] = (request, result)
        else:
            revision = request['intentRevision']
            require(current == revision, 'STALE_PROPOSAL')
            key = app, revision
            require(key in state['intents'], 'INTENT_NOT_FOUND')
            require(key not in state['proposals'], 'PROPOSAL_ALREADY_COMMITTED')
            original = state['intents'][key][1]
            require(request['expectedHandoffDigest'] == original['handoffDigest'], 'HANDOFF_CONFLICT')
            proposal_id = identity('HMS-APPLICATION-PROPOSAL-v0.1',
                dict(storeId=self._meta['storeId'], request=request))
            supported = request['proposal']['kind'] == 'supported_candidate'
            result = dict(profile='hms.application-proposal-receipt/0.1', storeId=self._meta['storeId'],
                applicationId=app, revision=revision, handoffDigest=original['handoffDigest'],
                proposalDigest=proposal_id, state='proposed' if supported else 'unresolved',
                artifactDigest=pat_digest(request['proposal']['artifact']) if supported else None,
                attributionVerification='unverified', qualification=QUALIFICATION)
            state['proposals'][key] = (request, result)
        return detached(result)

    def _get(self, state, request):
        app = request['applicationId']
        current = state['heads'].get(app, 0)
        revision = request.get('revision', current)
        require((app, revision) in state['intents'], 'INTENT_NOT_FOUND')
        intent, receipt = state['intents'][app, revision]
        proposal = state['proposals'].get((app, revision))
        return detached(dict(profile='hms.application-intent-status/0.1', intent=intent,
            receipt=receipt, currentRevision=current, superseded=revision != current,
            state=proposal[1]['state'] if proposal else 'awaiting_proposal',
            proposal=None if proposal is None else dict(request=proposal[0], receipt=proposal[1]),
            qualification=QUALIFICATION,
            usage=dict(records=state['count'], logicalBytes=state['used'], capacity=self._meta['capacity'])))

    def request(self, principal, method, value):
        """Principal is supplied by trusted ingress, never by any JSON field."""
        try:
            require(type(principal) is str and principal == self._meta['owner'], 'ACCESS_DENIED')
            integrity.verify(loaded=True)
            request = checked_request(method, value)
            integrity.verify(loaded=True)
            with self._transaction():
                state = self._load()
                if method == 'intent_get':
                    return self._get(state, request)
                prior = state['keys'].get(request['operationKey'])
                if prior is not None:
                    require(prior[:2] == (method, canonical(request)), 'KEY_CONFLICT')
                    return detached(prior[2])
                result = self._apply(state, method, request)
                body = canonical(dict(method=method, request=request, result=result))
                require(len(body) <= MAX_RECORD, 'CAPACITY')
                capacity = self._meta['capacity']
                require(state['count'] + 1 <= capacity['maxRecords'] and
                        state['used'] + len(body) + ROW_OVERHEAD <= capacity['maxBytes'], 'CAPACITY')
                self._db.execute('INSERT INTO ih_records VALUES (?,?)', (state['count'], body))
                return detached(result)
        except HandoffError:
            raise
        except (sqlite3.Error, OSError) as error:
            raise HandoffError('STORAGE_UNAVAILABLE') from error
        except (ContractError, TypeError, ValueError, KeyError, RecursionError) as error:
            raise HandoffError('INVALID_INPUT_OR_DEPENDENCY') from error
