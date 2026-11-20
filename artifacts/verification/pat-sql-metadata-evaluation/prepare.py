"""Freeze exact method sources and retained JSON data; never open a database."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import sqlite3
import _sqlite3
import sys
import textwrap

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = ROOT / 'artifacts/implementation/qualification-package/implementation03'
PURE = ROOT / 'artifacts/verification/pat-ascii-canonical-evaluation'
PROFILE = ROOT / 'artifacts/verification/qualification-current-profile'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, body):
    path = BASE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(body if type(body) is bytes else body.encode())


assert sha(SOURCE / 'index.json') == 'ec6df4066c89f38328030a28e2a5bd71d137abbc67cd51cb161cc246e2e8a268'
assert sha(PURE / 'index.json') == 'a41ccd9339c176800cc4dbe0b3d21d97f69b4e9d49c7ff7bc55cfd0553bb903e'
assert sha(PROFILE / 'index.json') == '0be98141123f0b6d4af41b6efc152edfa2a60fe51293f5720829665434898093'
source_rows = {r['path']: r for r in json.loads((SOURCE / 'index.json').read_bytes())['files']}
pure_rows = {r['path']: r for r in json.loads((PURE / 'index.json').read_bytes())['files']}
profile_rows = {r['path']: r for r in json.loads((PROFILE / 'index.json').read_bytes())['files']}
borrowed = []


def copy(path, name, inventory):
    row = inventory[str(path.relative_to(ROOT))]
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    write(name, path.read_bytes())
    borrowed.append({'source': str(path.relative_to(ROOT)), 'copy': name,
                     'bytes': row['bytes'], 'sha256': row['sha256']})


for name in ('pat_io_trials.py', 'pat_io_configuration_capture.py', 'pat_io_canonical_blobs.py',
             'contracts.py', 'pat_contracts.py', 'journal.py'):
    copy(SOURCE / 'project/hms' / name, 'references/' + name, source_rows)
for name in ('reference_functions.py', 'reference_helpers.py'):
    copy(PURE / name, name, pure_rows)
for name in ('__init__.py', '_impl.py'):
    copy(PURE / 'vendor/eval_rfc8785' / name, 'vendor/eval_rfc8785/' + name, pure_rows)

source = (BASE / 'references/pat_io_configuration_capture.py').read_text()
tree = ast.parse(source)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ConfiguredIoTrialEngine')
method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_configuration_table')
original = textwrap.dedent(''.join(source.splitlines(True)[method.lineno - 1:method.end_lineno]))
assert ast.dump(ast.parse(original).body[0], include_attributes=False) == ast.dump(method, include_attributes=False)
start = original.index('    actual_types = ')
end = original.index('    require(all(v is None', start)
replacement = '''    type_check = ' AND '.join('typeof(' + c + ') = ?' for c in columns)
    sizes_sql = ','.join('max(length(CAST(' + c + ' AS BLOB)))' for c in columns)
    metadata = db.execute('SELECT min(' + type_check + '),' + sizes_sql + ' FROM ' + table + where,
                          (*kinds, *params)).fetchone()
    require(not count or metadata[0] == 1, 'PAT_IO_CONFIGURATION_STORAGE_TYPE')
    sizes = metadata[1:]
'''
candidate = original[:start] + replacement + original[end:]
ast.parse(candidate)
write('reference_method.py', original)
write('candidate_method.py', candidate)
write('candidate.patch', ''.join(difflib.unified_diff(original.splitlines(True), candidate.splitlines(True),
    fromfile='reference_method.py', tofile='candidate_method.py')))
candidate_module = source
old_block = textwrap.indent(original[start:end], '    ')
new_block = textwrap.indent(replacement, '    ')
assert candidate_module.count(old_block) == 1
candidate_module = candidate_module.replace(old_block, new_block)
ast.parse(candidate_module)
write('candidate-pat_io_configuration_capture.py', candidate_module)

definitions = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id in ('PROFILE', 'PUBLIC_META', 'TABLES'):
            definitions[node.targets[0].id] = ast.literal_eval(node.value)
assert len(definitions['TABLES']) == 15
write('table-specifications.json', json.dumps(definitions, indent=2) + '\n')

case = PROFILE / 'harness02/attempts/attempt02-profile/scratch/test_actual_original_matrix_catalog_admission_and_cold_history/supervisor/1fa51266feef43e8bf8d435d5ed6585a/output/case-00/configuration'
snapshot_path = case / '000017.json'
copy(snapshot_path, 'documents/snapshot.json', profile_rows)
snapshot = json.loads(snapshot_path.read_bytes())
assert snapshot['kind'] == 'snapshot' and snapshot['value']['label'] == 'baseline'
for table in snapshot['value']['tables']:
    for reference in table['pages']:
        path = case / reference['path']
        assert path.stat().st_size == reference['bytes'] and sha(path) == reference['sha256']
        copy(path, 'documents/' + reference['path'], profile_rows)
write('borrowed-inputs.json', json.dumps(borrowed, indent=2) + '\n')

paths = {Path(sys.executable).resolve(), Path(_sqlite3.__file__), Path(sqlite3.__file__),
         Path(sqlite3.dbapi2.__file__), Path(json.__file__), Path(json.encoder.__file__),
         Path(json.decoder.__file__), Path(json.scanner.__file__)}
for line in Path('/proc/self/maps').read_text().splitlines():
    fields = line.split()
    if len(fields) == 6 and fields[5].startswith('/') and 'libsqlite3.so' in fields[5]:
        paths.add(Path(fields[5]))
assert any('libsqlite3.so' in str(p) for p in paths)
write('runtime-inputs.json', json.dumps({'pythonVersion': sys.version,
    'sqliteVersion': sqlite3.sqlite_version, 'sqliteExtensionOrigin': _sqlite3.__file__,
    'files': [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in sorted(paths)],
    'systemLibraryClosureAttested': False}, indent=2) + '\n')
print(json.dumps({'borrowedInputs': len(borrowed), 'tableSpecifications': 15,
                  'databaseConnectionsOpened': 0, 'packageImported': False}))
