"""Full memory-capture and real guard-method comparison at fixed cache sizes."""
import copy
import gc
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import threading
from types import SimpleNamespace

BASE = Path(__file__).resolve().parent
exec(compile((BASE / 'bootstrap.py').read_bytes(), str(BASE / 'bootstrap.py'), 'exec'), globals())
LEGACY = specifications['RECORD_PROFILE']
AUTHORITY, BOARD = specifications['_AUTHORITY'], specifications['_BOARD']


def load_functions(name, extra=None):
    namespace = dict(require=errors['require'], JournalError=errors['JournalError'],
        canonical=canonical, parse_json=parse_json, CanonicalBlobs=cache['CanonicalBlobs'],
        PUBLIC_META=PUBLIC_META, sqlite3=sqlite3, copy=copy, threading=threading,
        contextmanager=contextmanager, dataclass=dataclass, __name__=__name__)
    if extra:
        namespace.update(extra)
    exec(compile(verify(name), str(BASE / name), 'exec'), namespace)
    return namespace


legacy = load_functions('legacy_method.py')['_table']
configuration = load_functions('configuration_method.py')['_configuration_table']
state_ns = load_functions('commit_state.py')
journal_ns = load_functions('journal_methods.py', {'_CommitChecks': state_ns['_CommitChecks']})
MemoryJournal = type('MemoryJournal', (), {name: journal_ns[name] for name in (
    '_transaction', '_reject_commit_reentry', '_require_at_commit', '_check_business_commit', '_meta', '_set_meta')})
MemoryCatalog = type('MemoryCatalog', (), {'_verify_evidence': load_functions('catalog_method.py')['_verify_evidence']})
page_tree = ast.parse(verify('references/pat_io_page_encoding.py'))
page_tree.body = [n for n in page_tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
page_ns = dict(OrderedDict=OrderedDict, hashlib=hashlib, canonical=canonical)
exec(compile(page_tree, 'exact-page-encoding', 'exec'), page_ns)
PageEncodings = page_ns['PageEncodings']

active, peak_connections = set(), 0


def open_memory(capacity):
    global peak_connections
    db = sqlite3.connect(':memory:', cached_statements=capacity, isolation_level=None,
                         check_same_thread=False, timeout=0.2)
    active.add(db); peak_connections = max(peak_connections, len(active))
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA page_size=1024')
        db.execute('PRAGMA temp_store=MEMORY')
        db.execute('PRAGMA max_page_count=32768')
        return db
    except BaseException:
        close(db); raise


def close(db):
    try:
        db.close()
    finally:
        active.remove(db)


class MemoryWriter:
    def __init__(self):
        self.encoder = PageEncodings()
        self.pages = {'records': {}, 'configuration': {}}
        self.refs = {'records': {}, 'configuration': {}}
        self.next = {'records': 5, 'configuration': 2}

    def write(self, area, profile, kind, value, reuse):
        assert kind == 'table_page' and reuse is True
        body, digest = self.encoder.encode(profile, value)
        if digest not in self.refs[area]:
            name = '%06d.json' % self.next[area]; self.next[area] += 1
            self.pages[area][name] = body
            self.refs[area][digest] = {'path': name, 'bytes': len(body), 'sha256': digest}
        return copy.deepcopy(self.refs[area][digest])

    def _write(self, kind, value, *, reuse=False):
        return self.write('records', LEGACY, kind, value, reuse)

    def _configuration_write(self, kind, value, *, reuse=False):
        return self.write('configuration', PROFILE, kind, value, reuse)


expected, expected_pages, data = {}, {}, {'authority': {}, 'board': {}}
for area in ('records', 'configuration'):
    summary = json.loads(verify('documents/' + area + '/summary.json'))['value']
    expected[area] = summary['tables']; expected_pages[area] = {}
    for table in summary['tables']:
        rows = []; columns = None
        for ref in table['pages']:
            body = verify('documents/' + area + '/' + ref['path'])
            assert len(body) == ref['bytes'] and hashlib.sha256(body).hexdigest() == ref['sha256']
            expected_pages[area][ref['path']] = body
            page = json.loads(body)['value']
            assert page['first'] == len(rows) and page['totalRows'] == table['rowCount']
            columns = page['columns']
            for row in page['rows']:
                rows.append(tuple(cell['value'].encode('utf-8') if cell['type'] == 'blob-utf8' else cell['value'] for cell in row))
        assert len(rows) == table['rowCount']
        store = table.get('store', 'authority'); name = table['table']
        assert name not in data[store]
        if name == 'reg_meta':
            rows.append(('cursor_key', 'PRIVATE-FIXTURE-KEY'))
        data[store][name] = (columns, rows)
assert len(data['authority']) == 37 and len(data['board']) == 7
assert sum(len(v) for v in expected_pages.values()) == 46
ddl = json.loads(verify('ddl.json'))


def build_group(capacity):
    group = {}
    try:
        for store in ('authority', 'board'):
            db = open_memory(capacity if store == 'authority' else 128)
            group[store] = db
            for item in ddl[store]:
                if 'script' in item:
                    db.executescript(item['script'])
                else:
                    db.execute(item['statement'])
            names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert names == set(data[store]), (store, names)
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            for table, (columns, rows) in data[store].items():
                db.executemany('INSERT INTO ' + table + '(' + ','.join(columns) + ') VALUES (' +
                               ','.join('?' for _ in columns) + ')', rows)
            db.execute('COMMIT')
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        return group, MemoryWriter()
    except BaseException:
        for db in group.values():
            close(db)
        raise


def close_group(group):
    for db in group.values():
        close(db)


def capture(group, writer):
    legacy_tables = [legacy(writer, group[store], store, name, spec)
        for store, inventory in [('authority', AUTHORITY), ('board', BOARD)]
        for name, spec in inventory.items()]
    configuration_tables = [configuration(writer, group['authority'], name, spec)
                            for name, spec in TABLES.items()]
    return {'records': legacy_tables, 'configuration': configuration_tables}


def error_value(error):
    if error is None:
        return None
    return (type(error).__name__, getattr(error, 'code', None), error.args, error_value(error.__cause__))


def outcome(function):
    try:
        return ('accepted', function())
    except Exception as error:
        return ('refused', error_value(error))


def serial(value):
    if type(value) is bytes:
        return {'bytesHex': value.hex()}
    if type(value) in (tuple, list):
        return [serial(v) for v in value]
    if type(value) is dict:
        return {k: serial(v) for k, v in value.items()}
    assert value is None or type(value) in (int, float, bool, str), type(value)
    return value


cases = []


def compare(label, function):
    left, right = function(128), function(256)
    assert left == right, (label, left, right)
    body = json.dumps(serial(left), sort_keys=True, separators=(',', ':')).encode()
    cases.append({'id': label, 'exactOutcomeSha256': hashlib.sha256(body).hexdigest(), 'matched': True})
    return left


class Observer:
    """Declared compile/reprepare observation; absent from paired timing."""
    def __init__(self, db):
        self.db, self.current, self.calls = db, None, []
        db.set_authorizer(self.authorize)

    def authorize(self, action, first, second, database, source):
        assert self.current is not None
        counts = self.current['events']
        counts[str(action)] = counts.get(str(action), 0) + 1
        return sqlite3.SQLITE_OK

    def execute(self, sql, parameters=()):
        row = {'sql': sql, 'events': {}}
        self.calls.append(row); self.current = row
        return self.db.execute(sql, parameters)


diagnostics = []
for capacity in (0, 128, 256):
    group, writer = build_group(capacity)
    observers = {store: Observer(db) for store, db in group.items()}
    cycles = []
    try:
        for cycle in range(4):
            for observer in observers.values():
                observer.calls = []
            assert capture(observers, writer) == expected
            assert writer.pages == expected_pages
            row = {'cycle': cycle, 'connections': {}}
            for store, observer in observers.items():
                count = 164 if store == 'authority' else 28
                assert len(observer.calls) == len({r['sql'] for r in observer.calls}) == count
                row['connections'][store] = {
                    'executeCalls': count,
                    'statementsWithAuthorizerEvents': sum(bool(r['events']) for r in observer.calls),
                    'authorizerEvents': sum(sum(r['events'].values()) for r in observer.calls),
                    'statements': observer.calls}
            cycles.append(row)
    finally:
        for db in group.values():
            db.set_authorizer(None)
        close_group(group)
    diagnostics.append({'authorityCacheCapacity': capacity, 'cycles': cycles})


def fresh_capture(capacity, mutation):
    group, writer = build_group(capacity)
    try:
        initial = capture(group, writer)
        assert initial == capture(group, writer) == expected and writer.pages == expected_pages
        if mutation is not None:
            mutation(group)
        before = {k: db.total_changes for k, db in group.items()}
        value = outcome(lambda: capture(group, writer))
        assert before == {k: db.total_changes for k, db in group.items()}
        assert all(not db.in_transaction for db in group.values())
        return value, writer.pages
    finally:
        close_group(group)


compare('baseline-cold-warm-exact-46-pages', lambda capacity: fresh_capture(capacity, None))


def mutate_overflow(group):
    group['authority'].executemany('INSERT INTO rt_adapters VALUES (?,?,?,?)',
        [('extra:%02d' % i, b'{}', 'fixture-digest', 0) for i in range(15)])


mutations = [
    ('board-output', lambda g: g['board'].execute('UPDATE io_effects SET activations=activations+1'), None),
    ('configuration-context', lambda g: g['authority'].execute('UPDATE reg_instances SET retired=1'), None),
    ('new-type', lambda g: g['authority'].execute('UPDATE reg_instances SET retired=1.5'), 'PAT_IO_CONFIGURATION_STORAGE_TYPE'),
    ('new-document', lambda g: g['authority'].execute('UPDATE reg_observations SET document=?', (b'{ "new": 1 }',)), 'PAT_IO_CONFIGURATION_STORAGE_DOCUMENT'),
    ('deleted-grant', lambda g: g['authority'].execute('DELETE FROM reg_grants'), None),
    ('extra-authority-column', lambda g: g['authority'].execute('ALTER TABLE meta ADD COLUMN added TEXT'), 'PAT_IO_TRIAL_STORAGE_SHAPE'),
    ('extra-config-column', lambda g: g['authority'].execute('ALTER TABLE reg_grants ADD COLUMN added TEXT'), 'PAT_IO_CONFIGURATION_STORAGE_SHAPE'),
    ('missing-board-table', lambda g: g['board'].execute('DROP TABLE io_effects'), 'PAT_IO_TRIAL_STORAGE_SHAPE'),
    ('row-overflow', mutate_overflow, 'PAT_IO_TRIAL_STORAGE_LIMIT'),
]
for label, mutate, refusal in mutations:
    value, pages = compare('warm-capture-' + label, lambda capacity, m=mutate: fresh_capture(capacity, m))
    if refusal:
        assert value[0] == 'refused' and value[1][1] == refusal, (label, value)
    else:
        assert value[0] == 'accepted' and value[1] != expected


def make_journal(capacity):
    journal = MemoryJournal()
    journal._db = open_memory(capacity)
    journal._db.executescript("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);"
        "INSERT INTO meta VALUES('last_clock','0');"
        "CREATE TABLE guarded(id INTEGER PRIMARY KEY,value INTEGER NOT NULL);"
        "INSERT INTO guarded VALUES(1,0),(2,0),(3,0);")
    journal._mutex = threading.RLock()
    journal._closed = journal._poisoned = False
    journal._observed_clock = 0
    journal._commit_checks = None
    return journal


prohibited = [
    ('update', 'UPDATE guarded SET value=? WHERE id=?', (7, 2)),
    ('delete', 'DELETE FROM guarded WHERE id=?', (3,)),
    ('insert', 'INSERT INTO guarded VALUES (?,?)', (4, 0)),
    ('replace', 'INSERT OR REPLACE INTO guarded VALUES (?,?)', (2, 7)),
    ('pragma', 'PRAGMA user_version', ()),
    ('count-function', 'SELECT count(*) FROM guarded', ()),
    ('abs-function', 'SELECT abs(value) FROM guarded', ()),
    ('savepoint', 'SAVEPOINT cache_guard', ()),
    ('commit', 'COMMIT', ()),
    ('rollback', 'ROLLBACK', ()),
]


def warm(db, label, sql, parameters):
    if label in ('commit', 'rollback'):
        db.execute('BEGIN IMMEDIATE'); db.execute(sql).fetchall()
    elif label == 'savepoint':
        db.execute(sql).fetchall(); db.execute('RELEASE cache_guard')
    else:
        db.execute('BEGIN IMMEDIATE'); db.execute(sql, parameters).fetchall(); db.execute('ROLLBACK')


def guard_case(capacity, domain, operation, swallow=False, behavior='sql'):
    journal = make_journal(capacity); db = journal._db
    catalog = MemoryCatalog(); catalog.journal = journal; catalog._db = db
    label, sql, parameters = operation
    warm(db, label, sql, parameters)
    before = [tuple(r) for r in db.execute('SELECT * FROM guarded ORDER BY id')]

    def callback(*args):
        if behavior == 'raise':
            raise ValueError('declared fixture error')
        if behavior == 'reenter':
            journal._require_at_commit(lambda: None)
        elif behavior == 'nested-evidence':
            catalog._verify_evidence(SimpleNamespace(verify_evidence=lambda *_: True), None, {})
        else:
            try:
                db.execute(sql, parameters).fetchall()
            except sqlite3.DatabaseError:
                if not swallow:
                    raise
        return None if domain == 'commit' else True

    def operation_body():
        with journal._transaction():
            db.execute('UPDATE guarded SET value=10 WHERE id=1')
            if domain == 'commit':
                journal._require_at_commit(callback)
            else:
                result = catalog._verify_evidence(SimpleNamespace(verify_evidence=callback), None, {})
                # Declared fixture caller: unavailable evidence aborts its write.
                # Full catalog selection/admission remains a separate gate.
                if result[0] is not True:
                    raise errors['JournalError'](result[1])
                return result

    try:
        result = outcome(operation_body)
        after = [tuple(r) for r in db.execute('SELECT * FROM guarded ORDER BY id')]
        assert not db.in_transaction and journal._commit_checks is None
        assert getattr(journal, '_pat_evidence_guard', None) is None and not journal._poisoned
        if behavior == 'sql' and label != 'permitted-read':
            code = 'COMMIT_CHECK_IMPURE' if domain == 'commit' else 'PAT_EVIDENCE_PROVIDER_IMPURE'
            assert result[0] == 'refused' and result[1][1] == code and after == before, result
        elif behavior in ('reenter', 'nested-evidence'):
            assert result[0] == 'refused' and result[1][1] == 'COMMIT_CHECK_IMPURE' and after == before
        elif behavior == 'raise' and domain == 'commit':
            assert result[0] == 'refused' and result[1][0] == 'ValueError' and after == before
        elif behavior == 'raise':
            assert result[0] == 'refused' and result[1][1] == 'PAT_EVIDENCE_UNAVAILABLE' and after == before
        else:
            assert result[0] == 'accepted' and after[0] == (1, 10)
        # Fresh legitimate mutation proves hook restoration after every path.
        db.execute('UPDATE guarded SET value=11 WHERE id=1')
        assert db.execute('SELECT value FROM guarded WHERE id=1').fetchone()[0] == 11
        return result, before, after, True
    finally:
        close(db)


for domain in ('commit', 'evidence'):
    for operation in prohibited:
        for swallow in (False, True):
            compare('%s-warmed-%s-swallow-%s' % (domain, operation[0], swallow),
                    lambda capacity, d=domain, o=operation, s=swallow: guard_case(capacity, d, o, s))
    permitted = ('permitted-read', 'SELECT typeof(value),length(value) FROM guarded WHERE id=?', (1,))
    compare(domain + '-permitted-read', lambda capacity, d=domain: guard_case(capacity, d, permitted))
    compare(domain + '-exception-restoration', lambda capacity, d=domain: guard_case(capacity, d, permitted, behavior='raise'))
for behavior in ('reenter', 'nested-evidence'):
    compare('commit-' + behavior, lambda capacity, b=behavior: guard_case(capacity, 'commit', permitted, behavior=b))


def native_case(capacity, name):
    journal = make_journal(capacity); db = journal._db; cursors = []
    try:
        if name == 'parameters-data':
            sql = 'SELECT value FROM guarded WHERE id=?'
            assert db.execute(sql, (1,)).fetchone()[0] == 0
            db.execute('UPDATE guarded SET value=12 WHERE id=2')
            result = db.execute(sql, (2,)).fetchone()[0]
            assert result == 12
            bad = outcome(lambda: db.execute(sql, ()).fetchall())
            assert bad[0] == 'refused' and bad[1][0] == 'ProgrammingError'
            return result, bad
        if name == 'schema-refresh':
            sql = 'SELECT * FROM guarded WHERE id=?'
            assert len(db.execute(sql, (1,)).fetchone()) == 2
            db.execute('ALTER TABLE guarded ADD COLUMN note TEXT')
            result = tuple(db.execute(sql, (1,)).fetchone())
            assert result == (1, 0, None)
            return result
        if name == 'busy-cursors':
            sql = 'SELECT id FROM guarded ORDER BY id'
            first = db.execute(sql); cursors.append(first)
            assert tuple(first.fetchone()) == (1,)
            second = db.execute(sql); cursors.append(second)
            whole, remaining = [tuple(r) for r in second.fetchall()], [tuple(r) for r in first.fetchall()]
            assert whole == [(1,), (2,), (3,)] and remaining == [(2,), (3,)]
            return whole, remaining
        if name in ('authorizer-replacement', 'authorizer-exception'):
            sql = 'SELECT value FROM guarded WHERE id=?'
            assert db.execute(sql, (1,)).fetchone()[0] == 0
            def reject(*args):
                if name == 'authorizer-exception':
                    raise ValueError('declared authorizer failure')
                return sqlite3.SQLITE_DENY
            db.set_authorizer(reject)
            refusal = outcome(lambda: db.execute(sql, (1,)).fetchall())
            assert refusal[0] == 'refused' and refusal[1][0] == 'DatabaseError'
            db.set_authorizer(lambda *_: sqlite3.SQLITE_OK)
            assert db.execute(sql, (1,)).fetchone()[0] == 0
            db.set_authorizer(None)
            assert db.execute(sql, (1,)).fetchone()[0] == 0
            return refusal, True
        assert name == 'close-pending'
        cursor = db.execute('SELECT id FROM guarded ORDER BY id')
        assert cursor.fetchone()[0] == 1
        close(db); db = None
        refusal = outcome(cursor.fetchall)
        assert refusal[0] == 'refused' and refusal[1][0] == 'ProgrammingError'
        del cursor; gc.collect()
        return refusal
    finally:
        for cursor in cursors:
            cursor.close()
        if db is not None:
            db.set_authorizer(None); close(db)


for name in ('parameters-data', 'schema-refresh', 'busy-cursors', 'authorizer-replacement',
             'authorizer-exception', 'close-pending'):
    compare('native-' + name, lambda capacity, n=name: native_case(capacity, n))

timing_groups = [build_group(capacity) for capacity in (128, 256)]
for group, writer in timing_groups:
    for _ in range(2):
        assert capture(group, writer) == expected and writer.pages == expected_pages


def sample(group, writer):
    cpu, wall = time.process_time_ns(), time.monotonic_ns()
    for _ in range(16):
        result = capture(group, writer)
    elapsed = {'cpuNs': time.process_time_ns() - cpu, 'wallNs': time.monotonic_ns() - wall}
    assert result == expected and writer.pages == expected_pages
    return elapsed


pairs = []
try:
    for i in range(9):
        order = (0, 1) if i % 2 == 0 else (1, 0)
        pair = {}
        for j in order:
            pair['reference' if j == 0 else 'candidate'] = sample(*timing_groups[j])
        pair['order'] = ['reference' if j == 0 else 'candidate' for j in order]
        pair['cpuRatio'] = pair['candidate']['cpuNs'] / pair['reference']['cpuNs']
        pairs.append(pair)
finally:
    for group, _ in timing_groups:
        close_group(group)
assert not active
gc.collect()
reference_cpu = statistics.median(p['reference']['cpuNs'] for p in pairs)
candidate_cpu = statistics.median(p['candidate']['cpuNs'] for p in pairs)
ratio = candidate_cpu / reference_cpu
faster = sum(p['cpuRatio'] < 1 for p in pairs)
warm_observations = {d['authorityCacheCapacity']: sum(c['connections']['authority']['statementsWithAuthorizerEvents']
    for c in d['cycles'][1:]) for d in diagnostics}
preparation_reduced = warm_observations[256] < warm_observations[128]
for name in pins:
    verify(name)
print(json.dumps({'status': 'passed', 'differentialCases': len(cases), 'cases': cases,
    'diagnostics': diagnostics, 'warmAuthorityStatementsWithAuthorizerEvents': warm_observations,
    'warmPreparationObservationsReduced': preparation_reduced,
    'authorityCacheSizes': [0, 128, 256], 'boardCacheSize': 128,
    'legacyTables': 29, 'configurationTables': 15, 'baselinePagesExact': 46,
    'captureMethodsChanged': False, 'guardMethodsChanged': False,
    'ddlConstraintsAndIndexesRetained': True, 'memoryFixtureSubstitutionsDeclared': True,
    'timingPairs': pairs, 'fullCapturesPerSample': 16,
    'referenceMedianCpuNs': reference_cpu, 'candidateMedianCpuNs': candidate_cpu,
    'candidateToReferenceMedianCpuRatio': ratio, 'fasterPairs': faster,
    'integrationScreenPassed': preparation_reduced and ratio <= 0.95 and faster >= 8,
    'inMemoryConnectionsOpened': len(connections), 'peakLiveConnections': peak_connections,
    'liveConnectionsAtEnd': len(active), 'peakProcessRssKiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    'nativeStatementByteReservationProven': False,
    'persistentDatabasesOpened': 0, 'qualifiedWorkerLaunched': False, 'productionAdopted': False,
    'prohibitedAttempts': denied, 'inputsUnchanged': True, 'timingQualified': False,
    'sqliteVersion': sqlite3.sqlite_version, 'pythonVersion': sys.version}, separators=(',', ':')))
