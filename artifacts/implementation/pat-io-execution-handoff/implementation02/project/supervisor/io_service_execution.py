"""Journal-owned durable admission association for a pinned supervisor authority.

Only the invocation that creates and associates an attempt may launch it.
Historical association and recovery never authorize another producer.
"""
from contextlib import contextmanager
from functools import wraps
import os
import re
import signal
import sqlite3
import threading

from hms.contracts import SAFE_INTEGER, canonical
from hms.journal import JournalError
from hms.registry import _resource_stored_row
from authority_ledger import AuthorityAttemptLedger, authority_id
import io_services as services
import io_service_runs as runs_module
import qualification_supervisor as supervision
import supervisor_contracts as contracts

PROFILE = 'hms.pat.io-service-execution/0.1'
RECEIPT_PROFILE = 'hms.pat.io-service-handoff/0.1'
ANCHOR = 'io_service_execution'
MAX_HANDOFFS = 32
MAX_DATA_BYTES = 256 * 1024
RECEIPT_LIMIT = 4096
DOMAIN = b'HMS-PAT-IO-SERVICE-HANDOFF-v0.1'
META_DOMAIN = b'HMS-PAT-IO-SERVICE-EXECUTION-v0.1'
_DDL = {
    'iose_meta': 'CREATE TABLE iose_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), record BLOB NOT NULL)',
    'iose_handoffs': 'CREATE TABLE iose_handoffs (sequence INTEGER PRIMARY KEY, evaluator TEXT NOT NULL, run TEXT NOT NULL, receipt BLOB NOT NULL, UNIQUE(evaluator,run))',
}


class IoServiceExecutionError(JournalError):
    def __init__(self, suffix): super().__init__('PAT_IO_SERVICE_EXECUTION_' + suffix)


def require(condition, code):
    if not condition: raise IoServiceExecutionError(code)


def errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try: return function(*args, **kwargs)
        except JournalError: raise
        except sqlite3.Error as error: raise IoServiceExecutionError('STORAGE') from error
        except (TypeError, ValueError, KeyError, IndexError, RecursionError) as error:
            raise IoServiceExecutionError('INVALID_INPUT') from error
    return checked


def _number(value, low, high):
    require(type(value) is int and low <= value <= high, 'INVALID_RETAINED')


def _document(body):
    require(type(body) is bytes and 0 < len(body) <= RECEIPT_LIMIT, 'INVALID_RETAINED')
    value = services.snapshot(body)
    require(canonical(value) == body, 'INVALID_RETAINED')
    return value


class BoundQualificationSupervisor(supervision.QualificationSupervisor):
    def __init__(self, root, *, create=False, expected_authority=None):
        contracts.require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'),
                          'QUALIFICATION_PLATFORM_UNSUPPORTED')
        self.ledger = AuthorityAttemptLedger(root, create=create, expected_authority=expected_authority)
        self._execution = threading.Lock()
        self._owned = {}

    def execute(self, value, bundle=None):
        raise IoServiceExecutionError('BOUND_SERVICE_REQUIRED')


class IoServiceExecutionStore:
    @errors
    def __init__(self, runs, supervisor, *, create=False, owner=None):
        require(type(runs) is runs_module.IoServiceRunStore and type(supervisor) is BoundQualificationSupervisor,
                'AUTHORITY_MISMATCH')
        require(type(create) is bool and (create or owner is None), 'REOPEN_OPTIONS')
        self.runs, self.supervisor = runs, supervisor
        self.configurations, self.journal, self._db = runs.configurations, runs.journal, runs._db
        self.authority_id, self.deployment = runs.authority_id, runs.deployment
        with self._execution():
            with self.journal._transaction():
                run_state = runs._load()
                present, anchor = self._schema(allow_absent=True), self._anchor()
                if create:
                    self.configurations._authorize(owner)
                    if present or anchor is not None:
                        self._load(); raise IoServiceExecutionError('ALREADY_EXISTS')
                    meta = dict(profile=PROFILE, authorityId=self.authority_id, deployment=self.deployment,
                        supervisorAuthorityId=supervisor.ledger.authority_id,
                        maxHandoffs=min(MAX_HANDOFFS, run_state['meta']['maxRuns']),
                        maxDataBytes=MAX_DATA_BYTES, createdAtUnixMs=self.journal._now())
                    for sql in _DDL.values(): self._db.execute(sql)
                    self._db.execute('INSERT INTO iose_meta VALUES(1,?)', (canonical(meta),))
                    self._db.execute('INSERT INTO reg_meta VALUES(?,?)', (ANCHOR, self._anchor_value(meta)))
                self._load()

    @contextmanager
    def _execution(self):
        require(not self._db.in_transaction, 'TRANSACTION_REENTRY')
        require(self.supervisor._execution.acquire(blocking=False), 'BUSY')
        try: yield
        finally: self.supervisor._execution.release()

    def _anchor(self):
        row = _resource_stored_row(self._db, 'reg_meta', {'key': ANCHOR}, {'value': ('text', 128)})
        return None if row is None else row['value']

    @staticmethod
    def _anchor_value(meta):
        return PROFILE + '|' + services._hash(META_DOMAIN, meta)

    def _schema(self, *, allow_absent=False):
        require(self._db.execute("SELECT 1 FROM sqlite_temp_master WHERE name GLOB 'iose_*' OR tbl_name GLOB 'iose_*' LIMIT 1").fetchone() is None, 'SCHEMA')
        suffix = " FROM sqlite_master WHERE name GLOB 'iose_*' OR tbl_name GLOB 'iose_*' LIMIT 5"
        rows = self._db.execute('SELECT typeof(name),length(CAST(name AS BLOB)),typeof(type),length(CAST(type AS BLOB)),typeof(tbl_name),length(CAST(tbl_name AS BLOB)),typeof(sql),length(CAST(sql AS BLOB))' + suffix).fetchall()
        if not rows and allow_absent: return False
        require(len(rows) == 3, 'SCHEMA')
        for row in rows:
            require(all(row[i] == 'text' and type(row[i+1]) is int and 1 <= row[i+1] <= 128 for i in (0, 2, 4)), 'SCHEMA')
            require((row[6] == 'null' and row[7] is None) or (row[6] == 'text' and type(row[7]) is int and 1 <= row[7] <= 4096), 'SCHEMA')
        expected = {(name, 'table', name, sql) for name, sql in _DDL.items()} | {
            ('sqlite_autoindex_iose_handoffs_1', 'index', 'iose_handoffs', None)}
        require({tuple(row) for row in self._db.execute('SELECT name,type,tbl_name,sql' + suffix)} == expected, 'SCHEMA')
        return True

    def _receipt(self, reservation, identifier, sequence, principal, now, previous, meta):
        value = reservation['reservation']
        return dict(profile=RECEIPT_PROFILE, authorityId=self.authority_id, deployment=self.deployment,
            supervisorAuthorityId=meta['supervisorAuthorityId'], evaluatorId=value['evaluatorId'], runId=value['runId'],
            reservationDigest=reservation['reservationDigest'], requestDigest=value['requestDigest'],
            attemptId=identifier, sequence=sequence, principal=principal, committedAtUnixMs=now,
            previousHandoffDigest=previous)

    def _load(self):
        try: return self._load_validated()
        except IoServiceExecutionError: raise
        except (JournalError, TypeError, ValueError, KeyError, IndexError, RecursionError) as error:
            raise IoServiceExecutionError('INVALID_RETAINED') from error

    def _load_validated(self):
        require(self._db.in_transaction, 'TRANSACTION_REQUIRED')
        state = self.runs._load(); self._schema()
        values = self.configurations._scan('iose_meta', {'singleton': ('integer', 1), 'record': ('blob', RECEIPT_LIMIT)}, 1)
        require(len(values) == 1, 'INVALID_RETAINED'); meta = _document(values[0]['record'])
        services.exact(meta, {'profile', 'authorityId', 'deployment', 'supervisorAuthorityId', 'maxHandoffs', 'maxDataBytes', 'createdAtUnixMs'})
        require(meta['profile'] == PROFILE and meta['authorityId'] == self.authority_id and
                meta['deployment'] == self.deployment and self._anchor() == self._anchor_value(meta), 'INVALID_RETAINED')
        authority_id(meta['supervisorAuthorityId'])
        require(meta['supervisorAuthorityId'] == self.supervisor.ledger.authority_id, 'SUPERVISOR_MISMATCH')
        _number(meta['maxHandoffs'], 1, min(MAX_HANDOFFS, state['meta']['maxRuns']))
        _number(meta['maxDataBytes'], 1, MAX_DATA_BYTES); _number(meta['createdAtUnixMs'], 0, SAFE_INTEGER)
        rows = self.configurations._scan('iose_handoffs', {'sequence': ('integer', MAX_HANDOFFS),
            'evaluator': ('text', 128), 'run': ('text', 128), 'receipt': ('blob', RECEIPT_LIMIT)}, meta['maxHandoffs'])
        ordered = sorted(rows, key=lambda row: row['sequence'])
        require([row['sequence'] for row in ordered] == list(range(1, len(ordered)+1)), 'INVALID_RETAINED')
        keys, attempts = {}, set(); previous = None; now = meta['createdAtUnixMs']; charge = len(values[0]['record']) + 1024
        for row in ordered:
            key = row['evaluator'], row['run']; reservation = state['keys'].get(key)
            require(reservation is not None and key not in keys, 'INVALID_RETAINED')
            receipt = _document(row['receipt']); require(type(receipt) is dict, 'INVALID_RETAINED')
            identifier = receipt.get('attemptId')
            require(type(identifier) is str and re.fullmatch(r'[0-9a-f]{32}', identifier) is not None and identifier not in attempts, 'INVALID_RETAINED')
            principal = receipt.get('principal'); services.name(principal)
            stamp = receipt.get('committedAtUnixMs'); _number(stamp, now, SAFE_INTEGER); now = stamp
            expected = self._receipt(reservation, identifier, row['sequence'], principal, now, previous, meta)
            require(services.same(receipt, expected), 'INVALID_RETAINED')
            previous = services._hash(DOMAIN, receipt); attempts.add(identifier)
            keys[key] = dict(receipt=receipt, receiptDigest=previous)
            charge += len(row['receipt']) + 512
        require(charge <= meta['maxDataBytes'], 'INVALID_RETAINED')
        return dict(meta=meta, runs=state, keys=keys, charge=charge, lastDigest=previous, lastTime=now)

    def _row(self, reservation, association=None):
        request = reservation['preparedRun']['request']
        row = self.supervisor.lookup(*contracts.run_key(request))
        if row is None:
            require(association is None, 'ATTEMPT_MISSING')
            return None
        require(row['record']['requestDigest'] == reservation['reservation']['requestDigest'] and
                services.same(row['request'], request), 'REQUEST_CONFLICT')
        if association is not None:
            require(row['record']['attemptId'] == association['receipt']['attemptId'], 'ATTEMPT_MISMATCH')
        return row

    def _read(self, context, evaluator, run):
        services.name(evaluator); services.name(run)
        with self.journal._transaction():
            self.configurations._authorize(context); state = self._load()
            reservation = state['runs']['keys'].get((evaluator, run))
            require(reservation is not None, 'RESERVATION_MISSING')
            association = state['keys'].get((evaluator, run))
            row = self._row(reservation, association)
            return reservation, association, row

    @staticmethod
    def _result(association, row):
        return dict(association=services.snapshot(association) if association is not None else None,
                    attempt=None if row is None else dict(request=services.snapshot(row['request']),
                        record=services.snapshot(row['record']), returnBytes=row['returnBytes']))

    @errors
    def lookup(self, context, evaluator, run):
        require(not self._db.in_transaction, 'TRANSACTION_REENTRY')
        _, association, row = self._read(context, evaluator, run)
        return self._result(association, row)

    def _checkpoint(self, phase, value):
        """Private crash/test seam, not an operation-supplied callback."""

    def _fresh(self, context, reservation, runtime, installed_configuration):
        saved = reservation['preparedRun']; value = reservation['reservation']
        candidate = services.snapshot(saved['bundle']['documents']['inputs/candidate.json'])
        built = self.configurations.prepare_run(context, value['evaluatorId'], candidate, value['runId'],
            runtime=runtime, installed_configuration=installed_configuration)
        require(built['configurationReceipt']['receiptDigest'] == value['configurationReceiptDigest'], 'CONFIGURATION_CHANGED')
        current = built['preparedRun']
        require(current['requestDigest'] == value['requestDigest'] and services.same(current['request'], saved['request']) and
                current['bundle']['documents'] == saved['bundle']['documents'], 'INPUT_CHANGED')
        config = services.parse_configuration(saved['configuration']); pin = services.parse_service_pin(saved['servicePin'])
        return config, pin, self.configurations._resolver(runtime, config, pin)

    def _eligibility(self, context, state, reservation, resolver):
        value = reservation['reservation']
        current = state['runs']['configurations']['latest'].get(value['evaluatorId'])
        require(current is not None and current['receiptDigest'] == value['configurationReceiptDigest'], 'CONFIGURATION_CHANGED')
        descriptors = resolver.configured_snapshot(context)
        documents = reservation['preparedRun']['bundle']['documents']
        selected = [services.snapshot(documents['inputs/descriptor.json'])]
        selected += [actor['descriptor'] for actor in services.snapshot(documents['inputs/bindings.json']).values()]
        require(all(services.same(descriptors.get(item['binding']['instanceId']), item) for item in selected), 'AUTHORITY_CHANGED')

    def _associate(self, context, reservation, row, resolver=None):
        value = reservation['reservation']; key = value['evaluatorId'], value['runId']
        with self.journal._transaction():
            self.configurations._authorize(context); state = self._load()
            current = state['runs']['keys'].get(key)
            require(current is not None and current['reservationDigest'] == reservation['reservationDigest'], 'RESERVATION_CHANGED')
            old = state['keys'].get(key); actual = self._row(current, old)
            require(actual is not None and actual['record']['attemptId'] == row['record']['attemptId'], 'ATTEMPT_MISMATCH')
            if old is not None: return old, actual
            if resolver is not None:
                require(actual['record']['state'] == 'admitted' and actual['record']['history'] == ['admitted'], 'ATTEMPT_CHANGED')
                self._eligibility(context, state, current, resolver)
            sequence = len(state['keys']) + 1
            require(sequence <= state['meta']['maxHandoffs'], 'CAPACITY')
            receipt = self._receipt(current, actual['record']['attemptId'], sequence, context.principal,
                                    self.journal._now(), state['lastDigest'], state['meta'])
            wire = canonical(receipt)
            require(len(wire) <= RECEIPT_LIMIT and state['charge'] + len(wire) + 512 <= state['meta']['maxDataBytes'], 'CAPACITY')
            self._db.execute('INSERT INTO iose_handoffs VALUES(?,?,?,?)', (sequence, *key, wire))
            association = self._load()['keys'][key]
            self._checkpoint('before_association_commit', self._result(association, actual))
        self._checkpoint('after_association_commit', self._result(association, actual))
        return association, actual

    @errors
    def execute(self, context, evaluator, run, *, runtime=None, installed_configuration=None):
        require(not self._db.in_transaction, 'TRANSACTION_REENTRY')
        reservation, association, row = self._read(context, evaluator, run)
        if association is not None: return self._result(association, row)
        with self._execution():
            reservation, association, row = self._read(context, evaluator, run)
            if association is not None: return self._result(association, row)
            if row is not None:
                association, row = self._associate(context, reservation, row)
                return self._result(association, row)
            config, pin, resolver = self._fresh(context, reservation, runtime, installed_configuration)
            saved = reservation['preparedRun']
            bundle = contracts.snapshot_bundle(saved['bundle'])
            request = contracts.validate_fresh(saved['request'], bundle)
            image_charge = supervision._image_charge(self.supervisor.ledger, request)
            with self.journal._transaction():
                self.configurations._authorize(context); state = self._load()
                self._eligibility(context, state, reservation, resolver)
            self._checkpoint('before_admission', None)
            row, created = self.supervisor.ledger.admit(request, _image_charge=image_charge)
            if created: self.supervisor._checkpoint('admitted', row)
            self._checkpoint('after_admission', self._result(None, row))
            if not created:
                association, row = self._associate(context, reservation, row)
                return self._result(association, row)
            require(services.same(services.prepare_service_pin(config, runtime.catalog.document,
                authority_id=self.authority_id), pin), 'SOURCE_CHANGED')
            association, row = self._associate(context, reservation, row, resolver)
            self._checkpoint('before_launch', self._result(association, row))
            row = self.supervisor._launch(row, bundle)
            return self._result(association, row)

    @errors
    def recover(self, context, evaluator, run):
        value = self.lookup(context, evaluator, run)
        require(value['association'] is not None and value['attempt'] is not None, 'HANDOFF_MISSING')
        self.supervisor.recover(value['attempt']['record']['attemptId'])
        return self.lookup(context, evaluator, run)
