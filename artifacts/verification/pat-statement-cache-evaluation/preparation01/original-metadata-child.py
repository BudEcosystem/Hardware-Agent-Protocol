"""Exact method comparison on new memory databases, with a memory evidence sink."""
import ast
from collections import OrderedDict
from decimal import Decimal, DecimalException
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import sqlite3
import _sqlite3
import statistics
import sys
import time
import types
from types import FunctionType

BASE = Path(__file__).resolve().parent
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
pins = {row['path']: row for row in json.loads((BASE / 'inputs.json').read_bytes())['files']}


def verify(name):
    path = BASE / name
    row = pins[name]
    assert not path.is_symlink() and path.stat().st_size == row['bytes'] <= 16777216
    body = path.read_bytes()
    assert hashlib.sha256(body).hexdigest() == row['sha256']
    return body


for name in pins:
    verify(name)
external = json.loads(verify('runtime-inputs.json'))
for row in external['files']:
    path = Path(row['path'])
    assert path.stat().st_size == row['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
assert sqlite3.sqlite_version == external['sqliteVersion']
assert _sqlite3.__file__ == external['sqliteExtensionOrigin']
denied, connections = [], []


def guard(event, args):
    forbidden = event.startswith('socket.') or event in {
        'subprocess.Popen', 'os.system', 'os.exec', 'os.fork', 'os.forkpty', 'os.posix_spawn'}
    if event == 'sqlite3.connect':
        if args != (':memory:',):
            forbidden = True
        else:
            connections.append(':memory:')
    if event == 'import' and (args[0] == 'hms' or args[0].startswith(('hms.', 'hms_qualification'))):
        forbidden = True
    if event == 'open':
        mode, flags = args[1:3]
        forbidden |= ((type(mode) is str and any(c in mode for c in 'wax+')) or
                      (type(flags) is int and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))))
    if forbidden:
        denied.append(event)
        raise RuntimeError('Evaluation forbids persistent/external execution and I/O')


sys.addaudithook(guard)
sys.path.insert(0, str(BASE / 'vendor'))
import eval_rfc8785 as rfc8785
for module in (rfc8785, rfc8785._impl):
    verify(str(Path(module.__file__).relative_to(BASE)))

# Execute the exact previously reviewed parser/encoder definitions and helpers.
contracts = types.ModuleType('evaluation_contracts')
contracts.__dict__.update(MAX_BYTES=65536, MAX_DEPTH=32, MAX_NODES=16384, SAFE_INTEGER=2**53-1,
    math=math, json=json, Decimal=Decimal, DecimalException=DecimalException, rfc8785=rfc8785)
for name in ('reference_functions.py', 'reference_helpers.py'):
    exec(compile(verify(name), str(BASE / name), 'exec'), contracts.__dict__)
canonical, parse_json = contracts.canonical, contracts.parse_json
assert contracts._fast_allowed()


def definitions(name, wanted):
    tree = ast.parse(verify('references/' + name))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in wanted]
    assert {n.name for n in nodes} == set(wanted)
    return ast.Module(body=nodes, type_ignores=[])


errors = {}
exec(compile(definitions('journal.py', ['JournalError']), 'exact-journal-error', 'exec'), errors)
exec(compile(definitions('pat_contracts.py', ['PatError', 'require']), 'exact-pat-errors', 'exec'), errors)
cache = dict(OrderedDict=OrderedDict, json=json, FunctionType=FunctionType,
             contracts=contracts, rfc8785=rfc8785, encoder=rfc8785._impl)
cache_tree = ast.parse(verify('references/pat_io_canonical_blobs.py'))
cache_tree.body = [n for n in cache_tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
exec(compile(cache_tree, 'exact-canonical-blob-checker', 'exec'), cache)
assert cache['_dependencies_unchanged'](canonical, parse_json)
specifications = json.loads(verify('table-specifications.json'))
TABLES, PROFILE = specifications['TABLES'], specifications['PROFILE']
PUBLIC_META = tuple(specifications['PUBLIC_META'])


def load_method(name):
    tree = ast.parse(verify(name))
    assert len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef)
    namespace = dict(require=errors['require'], canonical=canonical, parse_json=parse_json,
                     CanonicalBlobs=cache['CanonicalBlobs'], PUBLIC_META=PUBLIC_META)
    exec(compile(tree, str(BASE / name), 'exec'), namespace)
    return namespace['_configuration_table']


reference, candidate = load_method('reference_method.py'), load_method('candidate_method.py')


class Sink:
    """Declared substitution: page bytes/reference checks, no durability claim."""
    def __init__(self):
        self.pages = []

    def _configuration_write(self, kind, value, *, reuse=False):
        assert kind == 'table_page' and reuse is True
        data = canonical({'profile': PROFILE, 'kind': kind, 'value': value})
        result = {'path': '%06d.json' % len(self.pages), 'bytes': len(data),
                  'sha256': hashlib.sha256(data).hexdigest()}
        self.pages.append(data)
        return result


class InvalidText:
    def __init__(self, body):
        self.body = body


class Database:
    def __init__(self, connection, fixture):
        self.raw, self.fixture, self.calls, self.injected = connection, fixture, [], False

    def execute(self, sql, parameters=()):
        f = self.fixture
        stage = ('schema' if sql.startswith('PRAGMA ') else
                 'count' if sql.startswith('SELECT count(*)') else
                 'metadata' if sql.startswith(('SELECT DISTINCT ', 'SELECT min(')) else
                 'rows' if (' ORDER BY ' + f['spec'][0] + ' LIMIT ?') in sql else
                 'keys' if sql.startswith('SELECT key FROM reg_meta') else 'sizes')
        self.calls.append((stage, sql, tuple(parameters)))
        if not self.injected and stage == f.get('injectAt'):
            self.injected = True
            for statement, args in f['mutations']:
                self.raw.execute(statement, args)
            self.raw.commit()
        return self.raw.execute(sql, parameters)


def build(f):
    db = sqlite3.connect(':memory:')
    db.execute('PRAGMA temp_store=MEMORY')
    db.execute('PRAGMA max_page_count=8192')
    db.execute('PRAGMA cache_size=-8192')
    if not f.get('missing'):
        db.execute('CREATE TABLE ' + f['table'] + '(' + f.get('schema', f['spec'][0]) + ')')
        for row in f['rows']:
            placeholders = ','.join('CAST(? AS TEXT)' if isinstance(v, InvalidText) else '?' for v in row)
            db.execute('INSERT INTO ' + f['table'] + ' VALUES (' + placeholders + ')',
                       tuple(v.body if isinstance(v, InvalidText) else v for v in row))
    db.commit()
    if f.get('rowFactory'):
        db.row_factory = sqlite3.Row
    return db


def exception_value(error):
    if error is None:
        return None
    return (type(error).__name__, getattr(error, 'code', None), error.args, exception_value(error.__cause__))


def run(function, fixture):
    connection = build(fixture)
    db, sink = Database(connection, fixture), Sink()
    before = connection.total_changes
    try:
        try:
            outcome = ('accepted', function(sink, db, fixture['table'], fixture['spec']))
        except Exception as error:
            outcome = ('refused', exception_value(error))
        if fixture.get('injectAt'):
            assert db.injected, fixture['id']
        else:
            assert connection.total_changes == before
        return outcome, tuple(sink.pages), tuple(db.calls)
    finally:
        connection.close()


def serial(value):
    if type(value) is bytes:
        return {'bytesHex': value.hex()}
    if type(value) in (tuple, list):
        return [serial(v) for v in value]
    if type(value) is dict:
        return {k: serial(v) for k, v in value.items()}
    assert value is None or type(value) in (int, float, bool, str), type(value)
    return value


cases, all_fixtures = [], []


def compare(f, expected=None):
    all_fixtures.append(f)
    left, left_pages, left_calls = run(reference, f)
    right, right_pages, right_calls = run(candidate, f)
    assert left == right and left_pages == right_pages, (f['id'], left, right)
    if expected == 'accepted':
        assert left[0] == 'accepted', (f['id'], left)
    elif expected is not None:
        assert left[0] == 'refused' and expected in left[1][:2], (f['id'], expected, left)
    if left[0] == 'accepted':
        assert len(left_calls) == len(right_calls) + 1, (f['id'], left_calls, right_calls)
    if f.get('overLimit'):
        assert [r[0] for r in left_calls] == ['schema', 'count']
        assert [r[0] for r in right_calls] == ['schema', 'count']
    body = json.dumps(serial((left, left_pages)), ensure_ascii=True, separators=(',', ':')).encode()
    cases.append({'id': f['id'], 'status': left[0],
        'refusal': None if left[0] == 'accepted' else left[1][1] or left[1][0],
        'exactOutcomeAndPagesSha256': hashlib.sha256(body).hexdigest(),
        'pageCount': len(left_pages), 'referenceSqlCalls': len(left_calls),
        'candidateSqlCalls': len(right_calls), 'injectedAt': f.get('injectAt')})
    return left, left_pages


def fixture(label, rows, spec=('a,b,c', 'text integer blob', 16), **kwargs):
    return dict(id=label, table='sample', spec=spec, rows=rows, **kwargs)


valid_row = ('value', 1, b'{"a":1}')
for count in (0, 1, 2, 7, 8, 9, 15, 16, 17):
    for row_factory in (False, True):
        compare(fixture('pages-%d-rowfactory-%s' % (count, row_factory), [valid_row] * count,
                        rowFactory=row_factory, overLimit=count > 16),
                'PAT_IO_CONFIGURATION_STORAGE_LIMIT' if count > 16 else 'accepted')
for kind in ('null', 'integer', 'real', 'text', 'blob'):
    value = {'null': None, 'integer': 1, 'real': 1.5, 'text': 'text', 'blob': b'{}'}[kind]
    for index in range(3):
        row = list(valid_row); row[index] = value
        compare(fixture('storage-class-%s-column-%d' % (kind, index), [row]),
                'accepted' if kind == ('text', 'integer', 'blob')[index] else 'PAT_IO_CONFIGURATION_STORAGE_TYPE')
        compare(fixture('mixed-class-%s-column-%d' % (kind, index), [valid_row, row]),
                'accepted' if kind == ('text', 'integer', 'blob')[index] else 'PAT_IO_CONFIGURATION_STORAGE_TYPE')
for size in (65533, 65534, 65535, 65536, 65537):
    compare(fixture('text-bytes-%d' % size, [('x' * size, 1, b'{}')]),
            'PAT_IO_CONFIGURATION_STORAGE_LIMIT' if size > 65536 else 'ContractError')
    compare(fixture('blob-bytes-%d' % size, [('x', 1, b'"' + b'x' * (size - 2) + b'"')]),
            'PAT_IO_CONFIGURATION_STORAGE_LIMIT' if size > 65536 else 'ContractError')
for i, body in enumerate((b'', b'not json', b'{"a":1,"a":2}', b'{ "a": 1 }', b'\xff',
                           b'NaN', b'1e999', b'-0', b'{"z":1,"a":2}', b'"\\ud800"', b'[' * 33 + b'0' + b']' * 33)):
    compare(fixture('invalid-document-%d' % i, [('a', 1, body)]))
for i, text in enumerate(('', '\x00', 'é', '😀', 'a\x00z', 'é' * 32769)):
    compare(fixture('text-special-%d' % i, [(text, 1, b'{}')]),
            'PAT_IO_CONFIGURATION_STORAGE_LIMIT' if i == 5 else 'accepted')
compare(fixture('invalid-utf8-text', [(InvalidText(b'\xff'), 1, b'{}')]), 'OperationalError')
for value in (-(2**63), -(2**53), -(2**53 - 1), 2**53 - 1, 2**53, 2**63 - 1):
    compare(fixture('integer-bound-%d' % value, [('a', value, b'{}')]),
            'accepted' if abs(value) <= 2**53 - 1 else 'ContractError')
for label, kwargs in [('missing', {'missing': True}), ('extra', {'schema': 'a,b,c,d'}),
                      ('reordered', {'schema': 'b,a,c'}), ('wide', {'schema': ','.join('c%d' % i for i in range(33))})]:
    compare(fixture('schema-' + label, [], **kwargs), 'PAT_IO_CONFIGURATION_STORAGE_SHAPE')
compare(fixture('collation', [('a', 1, b'{}'), ('A', 1, b'{}')], schema='a COLLATE NOCASE,b,c'), 'accepted')
compare(fixture('type-before-size', [(b'x' * 65537, 1, b'{}')]), 'PAT_IO_CONFIGURATION_STORAGE_TYPE')
compare(fixture('count-before-type-size', [(b'x' * 65537, 1, b'{}')] * 17, overLimit=True), 'PAT_IO_CONFIGURATION_STORAGE_LIMIT')
compare(fixture('size-before-document', [('x' * 65537, 1, b'not json')]), 'PAT_IO_CONFIGURATION_STORAGE_LIMIT')
compare(fixture('type-before-document', [('x', 'bad', b'not json')]), 'PAT_IO_CONFIGURATION_STORAGE_TYPE')

base_meta = [('cursor_key', 'PRIVATE-FIXTURE-KEY'), ('deployment', 'd'), ('revision', '1'), ('version', '1')]
for label, rows, expected in [
    ('normal', base_meta, 'accepted'), ('empty', [], 'PAT_IO_CONFIGURATION_STORAGE_SHAPE'),
    ('private-malformed', [(k, b'\xff' * 65537 if k == 'cursor_key' else v) for k, v in base_meta], 'accepted'),
    ('extra', base_meta + [('extra', 'x')], 'PAT_IO_CONFIGURATION_STORAGE_SHAPE'),
    ('missing', base_meta[:-1], 'PAT_IO_CONFIGURATION_STORAGE_SHAPE'),
    ('duplicate', base_meta + [base_meta[1]], 'PAT_IO_CONFIGURATION_STORAGE_SHAPE'),
    ('public-blob', [(k, b'{}' if k == 'revision' else v) for k, v in base_meta], 'PAT_IO_CONFIGURATION_STORAGE_TYPE')]:
    f = dict(id='registry-meta-' + label, table='reg_meta', spec=TABLES['reg_meta'], rows=rows)
    _, pages = compare(f, expected)
    assert all(b'PRIVATE-FIXTURE-KEY' not in page for page in pages)

# Selected boundaries are shared semantic points, independent of statement count.
mutations = [
    ('insert', [('INSERT INTO sample VALUES (?,?,?)', valid_row)]),
    ('delete', [('DELETE FROM sample', ())]),
    ('type', [('UPDATE sample SET b=?', ('bad',))]),
    ('size', [('UPDATE sample SET a=?', ('x' * 65537,))]),
    ('document', [('UPDATE sample SET c=?', (b'not json',))]),
    ('valid', [('UPDATE sample SET a=?', ('changed',))]),
    ('drop', [('DROP TABLE sample', ())]),
]
for stage in ('metadata', 'rows'):
    for label, statements in mutations:
        compare(fixture('boundary-%s-%s' % (stage, label), [valid_row], injectAt=stage, mutations=statements))
compare(fixture('empty-before-rows-insert', [], injectAt='rows', mutations=mutations[0][1]), 'PAT_IO_CONFIGURATION_STORAGE_CHANGED')

# Exact retained JSON pages supply data, never an interrupted database handle.
snapshot = json.loads(verify('documents/snapshot.json'))['value']
retained = []
for table in snapshot['tables']:
    name = table['table']; rows = []; expected_pages = []
    for ref in table['pages']:
        body = verify('documents/' + ref['path'])
        assert len(body) == ref['bytes'] and hashlib.sha256(body).hexdigest() == ref['sha256']
        document = json.loads(body); expected_pages.append(body)
        page = document['value']; assert page['table'] == name and page['first'] == len(rows)
        assert page['columns'] == TABLES[name][0].split(',')
        for row in page['rows']:
            rows.append(tuple(cell['value'].encode() if cell['type'] == 'blob-utf8' else cell['value'] for cell in row))
    assert len(rows) == table['rowCount']
    if name == 'reg_meta':
        rows.append(('cursor_key', 'PRIVATE-FIXTURE-KEY'))
    f = dict(id='retained-' + name, table=name, spec=TABLES[name], rows=rows)
    _, pages = compare(f, 'accepted')
    assert pages == tuple(expected_pages), name
    retained.append(f)
    if name != 'reg_meta':
        compare(dict(f, id='empty-' + name, rows=[]), 'accepted')
        columns, kinds, limit = TABLES[name]
        scalar = {'text': 'x', 'integer': 1, 'blob': b'{}'}
        row = tuple(scalar[k] for k in kinds.split())
        compare(dict(f, id='row-limit-' + name, rows=[row] * limit), 'accepted')
        compare(dict(f, id='over-row-limit-' + name, rows=[row] * (limit + 1), overLimit=True), 'PAT_IO_CONFIGURATION_STORAGE_LIMIT')

generator = random.Random(770091)
values = [None, -1, 0, 1, 2**53, 1.5, '', 'x', 'é', b'{}', b'null', b'{"a":1}', b'bad', b'\xff']
for i in range(240):
    rows = [tuple(generator.choice(values) for _ in range(3)) for _ in range(generator.randrange(4))]
    compare(fixture('generated-%03d' % i, rows))

# The same engine reads newly changed database contents on each call.
freshness = []
for function in (reference, candidate):
    f = fixture('between-captures', [valid_row]); db = build(f); proxy = Database(db, f); sink = Sink()
    try:
        first = function(sink, proxy, f['table'], f['spec']); first_bytes = tuple(sink.pages)
        db.execute('UPDATE sample SET a=?', ('new-context',)); db.commit(); sink.pages = []
        second = function(sink, proxy, f['table'], f['spec']); second_bytes = tuple(sink.pages)
        assert first != second and first_bytes != second_bytes
        freshness.append((first, first_bytes, second, second_bytes))
    finally:
        db.close()
assert freshness[0] == freshness[1]

# Fixed timing work, no fsync, no evidence publication, no whole-worker claim.
timing_sets = []
for function in (reference, candidate):
    group = []
    for f in retained:
        db = build(f); sink = Sink()
        # Direct native connection avoids counting-wrapper overhead in timings.
        group.append((function, db, sink, f))
        for _ in range(2):
            sink.pages.clear(); function(sink, db, f['table'], f['spec'])
    timing_sets.append(group)


def sample(group):
    start_cpu, start_wall = time.process_time_ns(), time.monotonic_ns()
    for _ in range(16):
        for function, db, sink, f in group:
            sink.pages.clear(); function(sink, db, f['table'], f['spec'])
    return {'cpuNs': time.process_time_ns() - start_cpu, 'wallNs': time.monotonic_ns() - start_wall}


pairs = []
try:
    for i in range(9):
        order = (0, 1) if i % 2 == 0 else (1, 0)
        result = {}
        for j in order:
            result['reference' if j == 0 else 'candidate'] = sample(timing_sets[j])
        result['order'] = ['reference' if j == 0 else 'candidate' for j in order]
        result['cpuRatio'] = result['candidate']['cpuNs'] / result['reference']['cpuNs']
        pairs.append(result)
finally:
    for group in timing_sets:
        for _, db, _, _ in group:
            db.close()

reference_median = statistics.median(pair['reference']['cpuNs'] for pair in pairs)
candidate_median = statistics.median(pair['candidate']['cpuNs'] for pair in pairs)
ratio = candidate_median / reference_median
faster = sum(pair['cpuRatio'] < 1 for pair in pairs)
for name in pins:
    verify(name)
print(json.dumps({'status': 'passed', 'differentialCases': len(cases), 'cases': cases,
    'accepted': sum(case['status'] == 'accepted' for case in cases),
    'refused': sum(case['status'] == 'refused' for case in cases),
    'retainedTables': len(retained), 'retainedPageBytesExact': True,
    'rowGuardPreserved': True, 'freshDataBetweenCaptures': True,
    'inMemoryConnectionsOpened': len(connections), 'persistentDatabasesOpened': 0,
    'hmsRuntimeImported': False, 'qualifiedWorkerLaunched': False,
    'evidenceWriterSubstituted': True, 'durableEvidencePublished': False,
    'timingPairs': pairs, 'capturesPerTablePerSample': 16,
    'referenceMedianCpuNs': reference_median, 'candidateMedianCpuNs': candidate_median,
    'candidateToReferenceMedianCpuRatio': ratio, 'fasterPairs': faster,
    'integrationScreenPassed': ratio <= 0.95 and faster >= 8,
    'productionAdopted': False, 'timingQualified': False,
    'prohibitedAttempts': denied, 'inputsUnchanged': True,
    'sqliteVersion': sqlite3.sqlite_version, 'pythonVersion': sys.version}, separators=(',', ':')))
