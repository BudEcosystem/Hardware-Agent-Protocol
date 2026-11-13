"""Static query inventory and installed API signature; no database connection."""
import ast
import hashlib
import json
from pathlib import Path
import sqlite3
import _sqlite3
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = ROOT / 'artifacts/implementation/qualification-package/implementation03'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert sha(SOURCE / 'index.json') == 'ec6df4066c89f38328030a28e2a5bd71d137abbc67cd51cb161cc246e2e8a268'
pins = {r['path']: r for r in json.loads((SOURCE / 'index.json').read_bytes())['files']}
sources, definitions = [], {}
for filename in ('pat_io_trials.py', 'pat_io_configuration_capture.py', 'journal.py',
                 'synthetic_io_board.py', 'pat_catalog.py'):
    path = SOURCE / 'project/hms' / filename
    row = pins[str(path.relative_to(ROOT))]
    assert sha(path) == row['sha256'] and path.stat().st_size == row['bytes']
    sources.append(row)
    tree = ast.parse(path.read_bytes())
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ('_BOARD', '_AUTHORITY', 'TABLES'):
                definitions[node.targets[0].id] = ast.literal_eval(node.value)
    if filename in ('journal.py', 'synthetic_io_board.py'):
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and
                 isinstance(n.func, ast.Attribute) and n.func.attr == 'connect' and
                 isinstance(n.func.value, ast.Name) and n.func.value.id == 'sqlite3']
        assert len(calls) == 1 and all(k.arg != 'cached_statements' for k in calls[0].keywords)

queries = []
for store, inventory in [('authority', definitions['_AUTHORITY']), ('board', definitions['_BOARD'])]:
    for table, (fields, limit) in inventory.items():
        columns = fields.split(',')
        statements = [
            'PRAGMA table_info(' + table + ')',
            'SELECT count(*) FROM ' + table,
            'SELECT ' + ','.join('max(length(CAST(' + c + ' AS BLOB)))' for c in columns) + ' FROM ' + table,
            'SELECT ' + fields + ' FROM ' + table + ' ORDER BY ' + fields + ' LIMIT ?',
        ]
        queries.extend({'store': store, 'table': table, 'sql': sql} for sql in statements)
for table, (fields, kinds, limit) in definitions['TABLES'].items():
    columns = fields.split(','); where = ' WHERE key IN (?,?,?)' if table == 'reg_meta' else ''
    statements = ['PRAGMA table_info(' + table + ')']
    if table == 'reg_meta':
        statements.append('SELECT key FROM reg_meta ORDER BY key LIMIT 5')
    statements.extend([
        'SELECT count(*) FROM ' + table + where,
        'SELECT DISTINCT ' + ','.join('typeof(' + c + ')' for c in columns) + ' FROM ' + table + where + ' LIMIT 2',
        'SELECT ' + ','.join('max(length(CAST(' + c + ' AS BLOB)))' for c in columns) + ' FROM ' + table + where,
        'SELECT ' + fields + ' FROM ' + table + where + ' ORDER BY ' + fields + ' LIMIT ?',
    ])
    queries.extend({'store': 'authority', 'table': table, 'sql': sql} for sql in statements)
counts = {store: len({r['sql'] for r in queries if r['store'] == store}) for store in ('authority', 'board')}
assert counts == {'authority': 164, 'board': 28}
assert 'cached_statements=128' in sqlite3.connect.__text_signature__
result = {'pythonVersion': sys.version, 'sqliteVersion': sqlite3.sqlite_version,
    'connectTextSignature': sqlite3.connect.__text_signature__,
    'sqliteExtensionOrigin': _sqlite3.__file__, 'sqliteExtensionSha256': sha(Path(_sqlite3.__file__)),
    'pythonExecutableSha256': sha(Path(sys.executable).resolve()),
    'sourceIndexSha256': sha(SOURCE / 'index.json'), 'sourceInputs': sources,
    'staticDistinctSqlByConnection': counts, 'queries': queries,
    'runtimeCacheMissesMeasured': False, 'hypothesisOnly': True,
    'authorizerReplacementPresent': ['Journal._check_business_commit', 'PatCatalog._verify_evidence'],
    'databaseConnectionsOpened': 0, 'productionRuntimeChanged': False,
    'scope': 'Static capture-only query set; startup, runtime and other queries may add statements.'}
with (BASE / 'OBSERVATION.json').open('x') as stream:
    json.dump(result, stream, indent=2); stream.write('\n')
print(json.dumps({'staticDistinctSqlByConnection': counts,
                  'defaultCachedStatements': 128, 'runtimeCacheMissesMeasured': False}))
