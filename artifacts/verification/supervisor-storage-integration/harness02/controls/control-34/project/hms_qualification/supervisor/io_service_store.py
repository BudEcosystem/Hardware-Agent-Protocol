"""Authority-owned configuration history and fresh trusted I/O preparation.

The store shares the Journal transaction/owner, never opens its own database,
launches a worker or promotes a PAT. Exact mutation replay precedes source reads.
Every history read is bounded and validated; missing/partial/corrupt state is not
reinitialized. Data accounting is not a filesystem quota or SQLite memory bound.
"""
from functools import wraps
import sqlite3

from hms.contracts import SAFE_INTEGER, canonical
from hms.journal import Context, JournalError
from hms.pat_io_bindings import IoRegistryPatBindings
from hms.registry import _resource_stored_row
import hms_qualification.supervisor.io_services as services

PROFILE = 'hms.pat.io-service-store/0.1'
REQUEST_PROFILE = 'hms.pat.io-service-configuration-mutation/0.1'
RECEIPT_PROFILE = 'hms.pat.io-service-configuration-receipt/0.1'
ANCHOR = 'io_service_configuration'
MAX_REVISIONS = 128
MAX_DATA_BYTES = 8 * 1024 * 1024
MAX_SERVICES = 16
CONFIG_LIMIT, PIN_LIMIT, RECEIPT_LIMIT, REQUEST_LIMIT = 65536, 4096, 4096, 2048
CONFIG_REQUEST_DOMAIN = b'HMS-PAT-IO-SERVICE-CONFIGURATION-MUTATION-v0.1'
RECEIPT_DOMAIN = b'HMS-PAT-IO-SERVICE-CONFIGURATION-RECEIPT-v0.1'
PIN_DOMAIN = b'HMS-PAT-IO-SERVICE-PIN-v0.1'
_DDL = {
    'iosc_meta': 'CREATE TABLE iosc_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), record BLOB NOT NULL)',
    'iosc_versions': 'CREATE TABLE iosc_versions (sequence INTEGER PRIMARY KEY, evaluator TEXT NOT NULL, revision INTEGER NOT NULL, configuration BLOB NOT NULL, pin BLOB NOT NULL, receipt BLOB NOT NULL, UNIQUE(evaluator,revision))',
    'iosc_heads': 'CREATE TABLE iosc_heads (evaluator TEXT PRIMARY KEY, sequence INTEGER NOT NULL)',
    'iosc_mutations': 'CREATE TABLE iosc_mutations (principal TEXT NOT NULL, operation_key TEXT NOT NULL, request BLOB NOT NULL, sequence INTEGER NOT NULL, PRIMARY KEY(principal,operation_key))',
}
_INDEXES = {('sqlite_autoindex_' + name + '_1', name) for name in ('iosc_versions', 'iosc_heads', 'iosc_mutations')}


class IoServiceStoreError(JournalError):
    def __init__(self, suffix): super().__init__('PAT_IO_SERVICE_STORE_' + suffix)


def require(condition, code):
    if not condition: raise IoServiceStoreError(code)


def errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try: return function(*args, **kwargs)
        except JournalError: raise
        except sqlite3.Error as error: raise IoServiceStoreError('STORAGE') from error
        except (TypeError, ValueError, KeyError, IndexError, RecursionError) as error:
            raise IoServiceStoreError('INVALID_INPUT') from error
    return checked


def _number(value, low, high):
    require(type(value) is int and low <= value <= high, 'INTEGER')


def _document(body, limit):
    require(type(body) is bytes and 0 < len(body) <= limit, 'INVALID_RETAINED')
    value = services.snapshot(body)
    require(canonical(value) == body, 'INVALID_RETAINED')
    return value


class IoServiceConfigurationStore:
    @errors
    def __init__(self, journal, registry, *, create=False, owner=None, max_revisions=None, max_data_bytes=None):
        require(registry.journal is journal and registry._db is journal._db, 'AUTHORITY_MISMATCH')
        self.journal, self.registry, self._db = journal, registry, journal._db
        self.authority_id, self.deployment = journal.authority_id, registry.deployment
        services._authority_id(self.authority_id)
        require(type(create) is bool, 'INVALID_INPUT')
        if not create: require(owner is None and max_revisions is None and max_data_bytes is None, 'REOPEN_OPTIONS')
        with journal._transaction():
            self._authority_profile()
            present = self._schema(allow_absent=True)
            anchor = self._anchor()
            if create:
                self._authorize(owner)
                if present or anchor is not None:
                    self._load(); raise IoServiceStoreError('ALREADY_EXISTS')
                revisions = MAX_REVISIONS if max_revisions is None else max_revisions
                capacity = MAX_DATA_BYTES if max_data_bytes is None else max_data_bytes
                _number(revisions, 1, MAX_REVISIONS); _number(capacity, 1, MAX_DATA_BYTES)
                now = journal._now()
                meta = dict(profile=PROFILE, authorityId=self.authority_id, deployment=self.deployment,
                            maxRevisions=revisions, maxDataBytes=capacity, createdAtUnixMs=now)
                wire = canonical(meta); require(len(wire) + 1024 <= capacity, 'CAPACITY')
                for statement in _DDL.values(): self._db.execute(statement)
                self._db.execute('INSERT INTO reg_meta(key,value) VALUES (?,?)', (ANCHOR, self._anchor_value(meta)))
                self._db.execute('INSERT INTO iosc_meta VALUES (1,?)', (wire,))
            self._load()

    def _authorize(self, context):
        require(type(context) is Context and context.deployment == self.deployment, 'AUTHORITY_MISMATCH')
        services.name(context.principal)
        self.registry.authorize(context, 'admin', '*')

    def _anchor(self):
        row = _resource_stored_row(self._db, 'reg_meta', {'key': ANCHOR}, {'value': ('text', 128)})
        return None if row is None else dict(row)

    @staticmethod
    def _anchor_value(meta):
        return PROFILE + '|' + services._hash(b'HMS-PAT-IO-SERVICE-STORE-META-v0.1', meta)

    def _authority_profile(self):
        for table, expected in [('meta', 'hms-ledger/0.1'), ('reg_meta', 'hms.registry/resource-roots/0.1')]:
            row = _resource_stored_row(self._db, table, {'key': 'version'}, {'value': ('text', 128)})
            require(row is not None and row['value'] == expected, 'AUTHORITY_MISMATCH')

    def _schema(self, *, allow_absent=False):
        require(self._db.execute("SELECT 1 FROM sqlite_temp_master WHERE name GLOB 'iosc_*' OR tbl_name GLOB 'iosc_*' LIMIT 1").fetchone() is None, 'SCHEMA')
        clause = " FROM sqlite_master WHERE name GLOB 'iosc_*' OR tbl_name GLOB 'iosc_*' LIMIT 9"
        meta = self._db.execute("SELECT typeof(name),length(CAST(name AS BLOB)),typeof(type),length(CAST(type AS BLOB)),typeof(tbl_name),length(CAST(tbl_name AS BLOB)),typeof(sql),length(CAST(sql AS BLOB))" + clause).fetchall()
        if not meta and allow_absent: return False
        require(len(meta) == 7, 'SCHEMA')
        for row in meta:
            require(all(row[i] == 'text' and type(row[i+1]) is int and 1 <= row[i+1] <= 128 for i in (0, 2, 4)), 'SCHEMA')
            require((row[6] == 'null' and row[7] is None) or (row[6] == 'text' and type(row[7]) is int and 1 <= row[7] <= 4096), 'SCHEMA')
        actual = {tuple(row) for row in self._db.execute('SELECT name,type,tbl_name,sql' + clause)}
        expected = {(name, 'table', name, sql) for name, sql in _DDL.items()} | {(name, 'index', table, None) for name, table in _INDEXES}
        require(actual == expected, 'SCHEMA')
        return True

    def _scan(self, table, fields, limit):
        # All table/column names and limits are installed source constants.
        checks = []
        for column, (kind, _) in fields.items():
            checks.extend(['typeof(' + column + ')', "CASE WHEN typeof(" + column + ")='integer' THEN " + column + ' ELSE NULL END' if kind == 'integer' else 'length(CAST(' + column + ' AS BLOB))'])
        suffix = ' FROM ' + table + ' LIMIT ?'
        rows = self._db.execute('SELECT ' + ','.join(checks) + suffix, (limit + 1,)).fetchall()
        require(len(rows) <= limit, 'INVALID_RETAINED')
        for row in rows:
            for i, (kind, bound) in enumerate(fields.values()):
                require(row[2*i] == kind and type(row[2*i+1]) is int and 1 <= row[2*i+1] <= bound, 'INVALID_RETAINED')
        values = self._db.execute('SELECT ' + ','.join(fields) + suffix, (limit + 1,)).fetchall()
        require(len(values) == len(rows), 'INVALID_RETAINED')
        return [dict(zip(fields, row)) for row in values]

    def _request(self, config, principal, key, expected_revision):
        return dict(profile=REQUEST_PROFILE, authorityId=self.authority_id, deployment=self.deployment,
            principal=principal, operationKey=key, evaluatorId=config['evaluatorId'], expectedRevision=expected_revision,
            configurationDigest=services._pin_context(config, self.authority_id)['configurationDigest'])

    def _receipt(self, config, pin, request, sequence, previous, now):
        return dict(profile=RECEIPT_PROFILE, authorityId=self.authority_id, deployment=self.deployment,
            evaluatorId=config['evaluatorId'], configurationRevision=config['revision'], sequence=sequence,
            configurationDigest=pin['configurationDigest'], servicePinDigest=services._hash(PIN_DOMAIN, pin),
            previousReceiptDigest=previous, principal=request['principal'], operationKey=request['operationKey'],
            requestDigest=services._hash(CONFIG_REQUEST_DOMAIN, request), committedAtUnixMs=now)

    def _load(self):
        try: return self._load_validated()
        except IoServiceStoreError: raise
        except (JournalError, TypeError, ValueError, KeyError, IndexError, RecursionError) as error:
            raise IoServiceStoreError('INVALID_RETAINED') from error

    def _load_validated(self):
        require(self._db.in_transaction, 'TRANSACTION_REQUIRED')
        self._authority_profile()
        self._schema()
        anchor = self._anchor(); require(anchor is not None, 'INVALID_RETAINED')
        authority = _resource_stored_row(self._db, 'meta', {'key': 'authority'}, {'value': ('text', 32)})
        deployment = _resource_stored_row(self._db, 'reg_meta', {'key': 'deployment'}, {'value': ('text', 128)})
        require(authority is not None and authority['value'] == self.authority_id and
                deployment is not None and deployment['value'] == self.deployment, 'AUTHORITY_MISMATCH')
        rows = self._scan('iosc_meta', {'singleton': ('integer', 1), 'record': ('blob', 4096)}, 1)
        require(len(rows) == 1, 'INVALID_RETAINED'); meta = _document(rows[0]['record'], 4096)
        services.exact(meta, {'profile', 'authorityId', 'deployment', 'maxRevisions', 'maxDataBytes', 'createdAtUnixMs'})
        require(anchor == {'value': self._anchor_value(meta)}, 'INVALID_RETAINED')
        require(meta['profile'] == PROFILE and meta['authorityId'] == self.authority_id and meta['deployment'] == self.deployment, 'AUTHORITY_MISMATCH')
        _number(meta['maxRevisions'], 1, MAX_REVISIONS); _number(meta['maxDataBytes'], 1, MAX_DATA_BYTES)
        _number(meta['createdAtUnixMs'], 0, SAFE_INTEGER)
        versions = self._scan('iosc_versions', {'sequence': ('integer', MAX_REVISIONS), 'evaluator': ('text', 128),
            'revision': ('integer', MAX_REVISIONS), 'configuration': ('blob', CONFIG_LIMIT), 'pin': ('blob', PIN_LIMIT), 'receipt': ('blob', RECEIPT_LIMIT)}, meta['maxRevisions'])
        mutations = self._scan('iosc_mutations', {'principal': ('text', 128), 'operation_key': ('text', 128),
            'request': ('blob', REQUEST_LIMIT), 'sequence': ('integer', MAX_REVISIONS)}, meta['maxRevisions'])
        heads = self._scan('iosc_heads', {'evaluator': ('text', 128), 'sequence': ('integer', MAX_REVISIONS)}, MAX_SERVICES)
        require(len(versions) == len(mutations) and len({row['sequence'] for row in mutations}) == len(mutations), 'INVALID_RETAINED')
        by_mutation = {row['sequence']: row for row in mutations}; ordered = sorted(versions, key=lambda row: row['sequence'])
        require([row['sequence'] for row in ordered] == list(range(1, len(ordered) + 1)), 'INVALID_RETAINED')
        latest, records, keys = {}, {}, {}; previous_time = meta['createdAtUnixMs']
        charge = len(rows[0]['record']) + 1024 + 256 * len(heads)
        for row in ordered:
            sequence = row['sequence']; mutation = by_mutation[sequence]
            config = services.parse_configuration(_document(row['configuration'], CONFIG_LIMIT))
            pin = services.parse_service_pin(_document(row['pin'], PIN_LIMIT))
            receipt = _document(row['receipt'], RECEIPT_LIMIT); request = _document(mutation['request'], REQUEST_LIMIT)
            require(canonical(config) == row['configuration'] and canonical(pin) == row['pin'], 'INVALID_RETAINED')
            require(pin['profile'] == services.AUTHORITY_PIN_PROFILE and pin['authorityId'] == self.authority_id, 'AUTHORITY_MISMATCH')
            require(all(services.same(pin[key], value) for key, value in services._pin_context(config, self.authority_id).items()), 'INVALID_RETAINED')
            require(config['deployment'] == self.deployment and row['evaluator'] == config['evaluatorId'], 'INVALID_RETAINED')
            prior = latest.get(row['evaluator']); expected_revision = prior['configuration']['revision'] + 1 if prior else 1
            require(row['revision'] == config['revision'] == expected_revision, 'INVALID_RETAINED')
            services.name(mutation['principal']); services.name(mutation['operation_key'])
            expected_request = self._request(config, mutation['principal'], mutation['operation_key'], expected_revision - 1)
            require(services.same(request, expected_request), 'INVALID_RETAINED')
            require(type(receipt) is dict, 'INVALID_RETAINED')
            now = receipt.get('committedAtUnixMs'); _number(now, previous_time, SAFE_INTEGER); previous_time = now
            expected_receipt = self._receipt(config, pin, request, sequence, prior['receiptDigest'] if prior else None, now)
            require(services.same(receipt, expected_receipt), 'INVALID_RETAINED')
            record = dict(configuration=config, pin=pin, receipt=receipt, receiptDigest=services._hash(RECEIPT_DOMAIN, receipt),
                          configurationBytes=row['configuration'], pinBytes=row['pin'], requestBytes=mutation['request'])
            records[sequence] = record; latest[row['evaluator']] = record
            key = mutation['principal'], mutation['operation_key']; require(key not in keys, 'INVALID_RETAINED'); keys[key] = record
            charge += sum(len(row[field]) for field in ('configuration', 'pin', 'receipt')) + len(mutation['request']) + 512
        expected_heads = {key: row['receipt']['sequence'] for key, row in latest.items()}
        require(len(heads) == len(expected_heads) and {row['evaluator']: row['sequence'] for row in heads} == expected_heads, 'INVALID_RETAINED')
        require(charge <= meta['maxDataBytes'], 'INVALID_RETAINED')
        return dict(meta=meta, records=records, latest=latest, mutations=keys, charge=charge)

    @staticmethod
    def _result(record):
        return dict(receipt=services.snapshot(record['receipt']), receiptDigest=record['receiptDigest'])

    def _checkpoint(self, phase, value):
        pass

    def _runtime(self, runtime):
        require(runtime is not None and runtime.journal is self.journal and runtime.registry is self.registry and
                runtime.catalog.journal is self.journal and runtime.catalog.resources.registry is self.registry, 'AUTHORITY_MISMATCH')

    def _resolver(self, runtime, config, pin):
        self._runtime(runtime)
        registrations = [row | dict(driverDigest=pin['implementation']['driverDigest'], installationDigest=config['installationDigest'])
                         for row in config['registrations']]
        return IoRegistryPatBindings(runtime, registrations)

    def _admit(self, state, context, key, request_bytes, config, expected_revision):
        existing = state['mutations'].get((context.principal, key))
        if existing is not None:
            require(existing['requestBytes'] == request_bytes, 'KEY_CONFLICT')
            return existing
        previous = state['latest'].get(config['evaluatorId'])
        current = previous['configuration']['revision'] if previous else 0
        require(current == expected_revision and config['revision'] == current + 1, 'REVISION_CONFLICT')
        require(len(state['records']) < state['meta']['maxRevisions'], 'CAPACITY')
        require(previous is not None or len(state['latest']) < MAX_SERVICES, 'CAPACITY')
        return None

    @errors
    def configure(self, context, operation_key, configuration, *, expected_revision, runtime=None):
        config = services.parse_configuration(configuration); services.name(operation_key)
        _number(expected_revision, 0, SAFE_INTEGER)
        require(type(context) is Context and config['deployment'] == self.deployment, 'AUTHORITY_MISMATCH')
        services.name(context.principal)
        request = self._request(config, context.principal, operation_key, expected_revision); request_bytes = canonical(request)
        require(len(request_bytes) <= REQUEST_LIMIT, 'CAPACITY')
        with self.journal._transaction():
            self._authorize(context); state = self._load()
            existing = self._admit(state, context, operation_key, request_bytes, config, expected_revision)
            if existing is not None: return self._result(existing)
        self._runtime(runtime)
        pin = services.prepare_service_pin(config, runtime.catalog.document, authority_id=self.authority_id)
        resolver = self._resolver(runtime, config, pin)
        config_bytes, pin_bytes = canonical(config), canonical(pin)
        require(len(config_bytes) <= CONFIG_LIMIT and len(pin_bytes) <= PIN_LIMIT, 'CAPACITY')
        with self.journal._transaction():
            self._authorize(context); state = self._load()
            existing = self._admit(state, context, operation_key, request_bytes, config, expected_revision)
            if existing is not None: return self._result(existing)
            resolver.configured_snapshot(context)
            previous = state['latest'].get(config['evaluatorId']); sequence = len(state['records']) + 1
            now = self.journal._now()
            receipt = self._receipt(config, pin, request, sequence, previous['receiptDigest'] if previous else None, now)
            receipt_bytes = canonical(receipt); require(len(receipt_bytes) <= RECEIPT_LIMIT, 'CAPACITY')
            charge = sum(map(len, (config_bytes, pin_bytes, request_bytes, receipt_bytes))) + 512 + (256 if previous is None else 0)
            require(state['charge'] + charge <= state['meta']['maxDataBytes'], 'CAPACITY')
            self._db.execute('INSERT INTO iosc_versions VALUES (?,?,?,?,?,?)', (sequence, config['evaluatorId'], config['revision'], config_bytes, pin_bytes, receipt_bytes))
            self._db.execute('INSERT INTO iosc_mutations VALUES (?,?,?,?)', (context.principal, operation_key, request_bytes, sequence))
            if previous is None: self._db.execute('INSERT INTO iosc_heads VALUES (?,?)', (config['evaluatorId'], sequence))
            else: self._db.execute('UPDATE iosc_heads SET sequence=? WHERE evaluator=?', (sequence, config['evaluatorId']))
            retained = self._load()['records'][sequence]; result = self._result(retained)
            self._checkpoint('before_commit', result)
        self._checkpoint('after_commit', result)
        return result

    @errors
    def lookup_mutation(self, context, operation_key):
        services.name(operation_key)
        with self.journal._transaction():
            self._authorize(context); record = self._load()['mutations'].get((context.principal, operation_key))
            return self._result(record) if record else None

    @errors
    def read(self, context, evaluator_id, *, revision=None):
        services.name(evaluator_id)
        if revision is not None: _number(revision, 1, MAX_REVISIONS)
        with self.journal._transaction():
            self._authorize(context); state = self._load()
            record = state['latest'].get(evaluator_id) if revision is None else next((row for row in state['records'].values()
                if row['configuration']['evaluatorId'] == evaluator_id and row['configuration']['revision'] == revision), None)
            require(record is not None, 'NOT_FOUND')
            return self._result(record) | dict(configuration=record['configurationBytes'], servicePin=record['pinBytes'])

    @errors
    def prepare_run(self, context, evaluator_id, candidate, run_id, *, runtime, installed_configuration):
        self._runtime(runtime)
        supplied = canonical(services.parse_configuration(installed_configuration))
        retained = self.read(context, evaluator_id)
        require(retained['configuration'] == supplied, 'CONFIGURATION_CHANGED')
        config = services.parse_configuration(retained['configuration']); pin = services.parse_service_pin(retained['servicePin'])
        configured = services.ConfiguredIoService(config, runtime.catalog.document, expected_pin=pin)
        resolver = self._resolver(runtime, config, pin)
        def snapshot_current():
            self._authorize(context); current = self._load()['latest'].get(evaluator_id)
            require(current is not None and current['receiptDigest'] == retained['receiptDigest'], 'CONFIGURATION_CHANGED')
            return resolver.configured_snapshot(context)
        with self.journal._transaction(): descriptors = snapshot_current()
        prepared = configured.prepare_run(candidate, run_id, trusted_descriptors=descriptors)
        self._checkpoint('prepared', prepared)
        with self.journal._transaction():
            require(services.same(snapshot_current(), descriptors), 'AUTHORITY_CHANGED')
        return dict(configurationReceipt={key: retained[key] for key in ('receipt', 'receiptDigest')}, preparedRun=prepared)
