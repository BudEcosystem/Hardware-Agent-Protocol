"""Immutable logical I/O qualification runs in the owning Journal authority.

A reservation retains exact prepared inputs, not an execution outcome. The
separate supervisor ledger still owns worker admission, recovery and status.
No source/runtime lookup is needed to read or exactly replay a committed run.
"""
from functools import wraps
import hashlib
import sqlite3

from hms.contracts import SAFE_INTEGER, canonical
from hms.journal import JournalError
from hms.pat_contracts import parse_pat, pat_digest
from hms.registry import _resource_stored_row
import hms_qualification.supervisor.io_services as services
import hms_qualification.supervisor.io_service_store as configuration_store
import hms_qualification.supervisor.supervisor_contracts as contracts

PROFILE = 'hms.pat.io-service-runs/0.1'
INTENT_PROFILE = 'hms.pat.io-service-run-intent/0.1'
RECEIPT_PROFILE = 'hms.pat.io-service-run-reservation/0.1'
ANCHOR = 'hms_qualification.supervisor.io_service_runs'
MAX_RUNS = 32
MAX_DATA_BYTES = 8 * 1024 * 1024
MAX_DOCUMENTS = 39
DOCUMENT_LIMIT = REQUEST_LIMIT = 65536
INTENT_LIMIT, RECEIPT_LIMIT = 2048, 4096
INTENT_DOMAIN = b'HMS-PAT-IO-SERVICE-RUN-INTENT-v0.1'
RECEIPT_DOMAIN = b'HMS-PAT-IO-SERVICE-RUN-RESERVATION-v0.1'
_DDL = {
    'iosr_meta': 'CREATE TABLE iosr_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), record BLOB NOT NULL)',
    'iosr_runs': 'CREATE TABLE iosr_runs (sequence INTEGER PRIMARY KEY, evaluator TEXT NOT NULL, run TEXT NOT NULL, intent BLOB NOT NULL, configuration_sequence INTEGER NOT NULL, request BLOB NOT NULL, receipt BLOB NOT NULL, UNIQUE(evaluator,run))',
    'iosr_documents': 'CREATE TABLE iosr_documents (sequence INTEGER NOT NULL, path TEXT NOT NULL, body BLOB NOT NULL, PRIMARY KEY(sequence,path))',
}
_INDEXES = {('sqlite_autoindex_' + name + '_1', name) for name in ('iosr_runs', 'iosr_documents')}


class IoServiceRunError(JournalError):
    def __init__(self, suffix): super().__init__('PAT_IO_SERVICE_RUN_' + suffix)


def require(condition, code):
    if not condition: raise IoServiceRunError(code)


def errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try: return function(*args, **kwargs)
        except JournalError: raise
        except sqlite3.Error as error: raise IoServiceRunError('STORAGE') from error
        except (TypeError, ValueError, KeyError, IndexError, RecursionError) as error:
            raise IoServiceRunError('INVALID_INPUT') from error
    return checked


def _number(value, low, high):
    require(type(value) is int and low <= value <= high, 'INTEGER')


def _document(body, limit):
    require(type(body) is bytes and 0 < len(body) <= limit, 'INVALID_RETAINED')
    value = services.snapshot(body)
    require(canonical(value) == body, 'INVALID_RETAINED')
    return value


class IoServiceRunStore:
    @errors
    def __init__(self, configurations, *, create=False, owner=None, max_runs=None, max_data_bytes=None):
        require(type(configurations) is configuration_store.IoServiceConfigurationStore, 'AUTHORITY_MISMATCH')
        self.configurations = configurations
        self.journal, self.registry, self._db = configurations.journal, configurations.registry, configurations._db
        self.authority_id, self.deployment = configurations.authority_id, configurations.deployment
        require(type(create) is bool, 'INVALID_INPUT')
        if not create: require(owner is None and max_runs is None and max_data_bytes is None, 'REOPEN_OPTIONS')
        with self.journal._transaction():
            configurations._load()
            present, anchor = self._schema(allow_absent=True), self._anchor()
            if create:
                configurations._authorize(owner)
                if present or anchor is not None:
                    self._load(); raise IoServiceRunError('ALREADY_EXISTS')
                maximum = MAX_RUNS if max_runs is None else max_runs
                capacity = MAX_DATA_BYTES if max_data_bytes is None else max_data_bytes
                _number(maximum, 1, MAX_RUNS); _number(capacity, 1, MAX_DATA_BYTES)
                now = self.journal._now()
                meta = dict(profile=PROFILE, authorityId=self.authority_id, deployment=self.deployment,
                            maxRuns=maximum, maxDataBytes=capacity, createdAtUnixMs=now)
                wire = canonical(meta); require(len(wire) + 1024 <= capacity, 'CAPACITY')
                for statement in _DDL.values(): self._db.execute(statement)
                self._db.execute('INSERT INTO reg_meta VALUES (?,?)', (ANCHOR, self._anchor_value(meta)))
                self._db.execute('INSERT INTO iosr_meta VALUES (1,?)', (wire,))
            self._load()

    def _anchor(self):
        row = _resource_stored_row(self._db, 'reg_meta', {'key': ANCHOR}, {'value': ('text', 128)})
        return None if row is None else row['value']

    @staticmethod
    def _anchor_value(meta):
        return PROFILE + '|' + services._hash(b'HMS-PAT-IO-SERVICE-RUNS-META-v0.1', meta)

    def _schema(self, *, allow_absent=False):
        require(self._db.execute("SELECT 1 FROM sqlite_temp_master WHERE name GLOB 'iosr_*' OR tbl_name GLOB 'iosr_*' LIMIT 1").fetchone() is None, 'SCHEMA')
        suffix = " FROM sqlite_master WHERE name GLOB 'iosr_*' OR tbl_name GLOB 'iosr_*' LIMIT 7"
        rows = self._db.execute('SELECT typeof(name),length(CAST(name AS BLOB)),typeof(type),length(CAST(type AS BLOB)),typeof(tbl_name),length(CAST(tbl_name AS BLOB)),typeof(sql),length(CAST(sql AS BLOB))' + suffix).fetchall()
        if not rows and allow_absent: return False
        require(len(rows) == 5, 'SCHEMA')
        for row in rows:
            require(all(row[i] == 'text' and type(row[i+1]) is int and 1 <= row[i+1] <= 128 for i in (0, 2, 4)), 'SCHEMA')
            require((row[6] == 'null' and row[7] is None) or (row[6] == 'text' and type(row[7]) is int and 1 <= row[7] <= 4096), 'SCHEMA')
        actual = {tuple(row) for row in self._db.execute('SELECT name,type,tbl_name,sql' + suffix)}
        expected = {(name, 'table', name, sql) for name, sql in _DDL.items()} | {(name, 'index', table, None) for name, table in _INDEXES}
        require(actual == expected, 'SCHEMA'); return True

    def _documents(self, meta):
        # Preflight the aggregate body size before fetching any document BLOB.
        limit = meta['maxRuns'] * MAX_DOCUMENTS
        rows = self._db.execute("SELECT typeof(sequence),CASE WHEN typeof(sequence)='integer' THEN sequence ELSE NULL END,typeof(path),length(CAST(path AS BLOB)),typeof(body),length(body) FROM iosr_documents LIMIT ?", (limit + 1,)).fetchall()
        require(len(rows) <= limit, 'INVALID_RETAINED')
        for row in rows:
            require(row[0] == 'integer' and type(row[1]) is int and 1 <= row[1] <= meta['maxRuns'] and
                    row[2] == 'text' and type(row[3]) is int and 1 <= row[3] <= 128 and
                    row[4] == 'blob' and type(row[5]) is int and 1 <= row[5] <= DOCUMENT_LIMIT, 'INVALID_RETAINED')
        require(sum(row[5] for row in rows) <= meta['maxDataBytes'], 'INVALID_RETAINED')
        values = self._db.execute('SELECT sequence,path,body FROM iosr_documents LIMIT ?', (limit + 1,)).fetchall()
        require(len(values) == len(rows), 'INVALID_RETAINED')
        documents = {}
        for sequence, path, body in values:
            group = documents.setdefault(sequence, {})
            require(path not in group and len(group) < MAX_DOCUMENTS, 'INVALID_RETAINED'); group[path] = body
        return documents

    def _intent(self, evaluator, run, candidate_digest, configuration_receipt_digest):
        return dict(profile=INTENT_PROFILE, authorityId=self.authority_id, deployment=self.deployment,
            evaluatorId=evaluator, runId=run, artifactDigest=candidate_digest,
            configurationReceiptDigest=configuration_receipt_digest)

    def _receipt(self, intent, request, sequence, config_sequence, principal, previous, now):
        return dict(profile=RECEIPT_PROFILE, authorityId=self.authority_id, deployment=self.deployment,
            evaluatorId=intent['evaluatorId'], runId=intent['runId'], sequence=sequence,
            artifactDigest=intent['artifactDigest'], intentDigest=services._hash(INTENT_DOMAIN, intent),
            configurationSequence=config_sequence, configurationReceiptDigest=intent['configurationReceiptDigest'],
            requestDigest=contracts.request_digest(request), bundleDigest=request['bundleDigest'],
            principal=principal, previousReservationDigest=previous, committedAtUnixMs=now)

    def _load(self):
        try: return self._load_validated()
        except IoServiceRunError: raise
        except (JournalError, TypeError, ValueError, KeyError, IndexError, RecursionError) as error:
            raise IoServiceRunError('INVALID_RETAINED') from error

    def _load_validated(self):
        require(self._db.in_transaction, 'TRANSACTION_REQUIRED')
        configurations = self.configurations._load(); self._schema()
        rows = self.configurations._scan('iosr_meta', {'singleton': ('integer', 1), 'record': ('blob', 4096)}, 1)
        require(len(rows) == 1, 'INVALID_RETAINED'); meta = _document(rows[0]['record'], 4096)
        services.exact(meta, {'profile', 'authorityId', 'deployment', 'maxRuns', 'maxDataBytes', 'createdAtUnixMs'})
        require(self._anchor() == self._anchor_value(meta) and meta['profile'] == PROFILE and
                meta['authorityId'] == self.authority_id and meta['deployment'] == self.deployment, 'INVALID_RETAINED')
        _number(meta['maxRuns'], 1, MAX_RUNS); _number(meta['maxDataBytes'], 1, MAX_DATA_BYTES)
        _number(meta['createdAtUnixMs'], 0, SAFE_INTEGER)
        runs = self.configurations._scan('iosr_runs', {'sequence': ('integer', MAX_RUNS),
            'evaluator': ('text', 128), 'run': ('text', 128), 'intent': ('blob', INTENT_LIMIT),
            'configuration_sequence': ('integer', configuration_store.MAX_REVISIONS),
            'request': ('blob', REQUEST_LIMIT), 'receipt': ('blob', RECEIPT_LIMIT)}, meta['maxRuns'])
        documents = self._documents(meta); ordered = sorted(runs, key=lambda row: row['sequence'])
        require([row['sequence'] for row in ordered] == list(range(1, len(ordered) + 1)) and
                set(documents) == {row['sequence'] for row in ordered}, 'INVALID_RETAINED')
        records, keys = {}, {}; previous = None; previous_time = meta['createdAtUnixMs']; charge = len(rows[0]['record']) + 1024
        for row in ordered:
            sequence = row['sequence']; config = configurations['records'].get(row['configuration_sequence'])
            require(config is not None and config['configuration']['evaluatorId'] == row['evaluator'], 'INVALID_RETAINED')
            services.name(row['evaluator']); services.name(row['run'])
            request = contracts.parse_request(_document(row['request'], REQUEST_LIMIT))
            receipt = _document(row['receipt'], RECEIPT_LIMIT); require(type(receipt) is dict, 'INVALID_RETAINED')
            candidate = _document(documents[sequence].get('inputs/candidate.json'), DOCUMENT_LIMIT)
            intent = self._intent(row['evaluator'], row['run'], pat_digest(parse_pat(candidate)), config['receiptDigest'])
            require(services.same(_document(row['intent'], INTENT_LIMIT), intent), 'INVALID_RETAINED')
            principal = receipt.get('principal'); services.name(principal)
            now = receipt.get('committedAtUnixMs'); _number(now, previous_time, SAFE_INTEGER); previous_time = now
            expected = self._receipt(intent, request, sequence, row['configuration_sequence'], principal, previous, now)
            require(services.same(receipt, expected), 'INVALID_RETAINED')
            prepared = services.parse_prepared_run(dict(configuration=config['configurationBytes'], servicePin=config['pinBytes'],
                request=request, requestDigest=receipt['requestDigest'], bundle=dict(header=canonical(request['bundleHeader']),
                    bundleDigest=request['bundleDigest'], documents=documents[sequence])), expected_pin=config['pin'],
                expected_run_id=row['run'], expected_request_digest=receipt['requestDigest'])
            previous = services._hash(RECEIPT_DOMAIN, receipt)
            record = dict(reservation=receipt, reservationDigest=previous, preparedRun=prepared, intentBytes=row['intent'])
            key = row['evaluator'], row['run']; require(key not in keys, 'INVALID_RETAINED')
            records[sequence] = record; keys[key] = record
            charge += len(row['intent']) + len(row['request']) + len(row['receipt']) + 512
            charge += sum(len(body) + 128 for body in documents[sequence].values())
        require(charge <= meta['maxDataBytes'], 'INVALID_RETAINED')
        return dict(meta=meta, configurations=configurations, records=records, keys=keys, charge=charge)

    @staticmethod
    def _result(record):
        value = record['preparedRun']
        # Reconstruct only detached builtins; bytes are immutable.
        return dict(reservation=services.snapshot(record['reservation']), reservationDigest=record['reservationDigest'],
            preparedRun=dict(configuration=value['configuration'], servicePin=value['servicePin'],
                request=services.snapshot(value['request']), requestDigest=value['requestDigest'],
                bundle=contracts.snapshot_bundle(value['bundle'])))

    def _checkpoint(self, phase, value):
        pass

    def _admit(self, state, intent, wire):
        existing = state['keys'].get((intent['evaluatorId'], intent['runId']))
        if existing is not None:
            require(existing['intentBytes'] == wire, 'KEY_CONFLICT'); return existing
        require(len(state['records']) < state['meta']['maxRuns'], 'CAPACITY')
        current = state['configurations']['latest'].get(intent['evaluatorId'])
        require(current is not None and current['receiptDigest'] == intent['configurationReceiptDigest'], 'CONFIGURATION_CHANGED')
        return None

    @errors
    def lookup(self, context, evaluator_id, run_id):
        services.name(evaluator_id); services.name(run_id)
        with self.journal._transaction():
            self.configurations._authorize(context); record = self._load()['keys'].get((evaluator_id, run_id))
            return None if record is None else self._result(record)

    @errors
    def reserve(self, context, evaluator_id, run_id, candidate, *, expected_configuration_receipt_digest,
                runtime=None, installed_configuration=None):
        services.name(evaluator_id); services.name(run_id); services.digest(expected_configuration_receipt_digest)
        artifact = parse_pat(services.snapshot(candidate))
        intent = self._intent(evaluator_id, run_id, pat_digest(artifact), expected_configuration_receipt_digest)
        wire = canonical(intent); require(len(wire) <= INTENT_LIMIT, 'CAPACITY')
        with self.journal._transaction():
            self.configurations._authorize(context); state = self._load()
            existing = self._admit(state, intent, wire)
            if existing is not None: return self._result(existing)
        built = self.configurations.prepare_run(context, evaluator_id, artifact, run_id, runtime=runtime,
                                               installed_configuration=installed_configuration)
        require(built['configurationReceipt']['receiptDigest'] == expected_configuration_receipt_digest, 'CONFIGURATION_CHANGED')
        prepared = built['preparedRun']; pin = services.parse_service_pin(prepared['servicePin'])
        config = services.parse_configuration(prepared['configuration'])
        prepared = services.parse_prepared_run(prepared, expected_pin=pin, expected_run_id=run_id,
                                               expected_request_digest=prepared['requestDigest'])
        require(pat_digest(_document(prepared['bundle']['documents']['inputs/candidate.json'], DOCUMENT_LIMIT)) == intent['artifactDigest'], 'INPUT_CHANGED')
        resolver = self.configurations._resolver(runtime, config, pin)
        request_wire = canonical(prepared['request']); require(len(request_wire) <= REQUEST_LIMIT, 'CAPACITY')
        self._checkpoint('prepared', prepared)
        require(services.same(services.prepare_service_pin(config, runtime.catalog.document, authority_id=self.authority_id), pin), 'SOURCE_CHANGED')
        with self.journal._transaction():
            self.configurations._authorize(context); state = self._load()
            existing = self._admit(state, intent, wire)
            if existing is not None: return self._result(existing)
            descriptors = resolver.configured_snapshot(context)
            documents = prepared['bundle']['documents']
            actors = _document(documents['inputs/bindings.json'], DOCUMENT_LIMIT)
            selected = [_document(documents['inputs/descriptor.json'], DOCUMENT_LIMIT)] + [row['descriptor'] for row in actors.values()]
            require(all(services.same(descriptors.get(value['binding']['instanceId']), value) for value in selected), 'AUTHORITY_CHANGED')
            current = state['configurations']['latest'][evaluator_id]; sequence = len(state['records']) + 1
            now = self.journal._now()
            previous = state['records'][sequence-1]['reservationDigest'] if sequence > 1 else None
            receipt = self._receipt(intent, prepared['request'], sequence, current['receipt']['sequence'], context.principal, previous, now)
            receipt_wire = canonical(receipt); require(len(receipt_wire) <= RECEIPT_LIMIT, 'CAPACITY')
            charge = len(wire) + len(request_wire) + len(receipt_wire) + 512 + sum(len(body) + 128 for body in documents.values())
            require(state['charge'] + charge <= state['meta']['maxDataBytes'], 'CAPACITY')
            self._db.execute('INSERT INTO iosr_runs VALUES (?,?,?,?,?,?,?)', (sequence, evaluator_id, run_id, wire,
                current['receipt']['sequence'], request_wire, receipt_wire))
            self._db.executemany('INSERT INTO iosr_documents VALUES (?,?,?)', ((sequence, path, body) for path, body in documents.items()))
            result = self._result(self._load()['records'][sequence]); self._checkpoint('before_commit', result)
        self._checkpoint('after_commit', result)
        return result
