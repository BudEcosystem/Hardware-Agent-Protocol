"""Retain exact source/DDL and baseline JSON; no runtime import or database."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import textwrap

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = ROOT / 'artifacts/implementation/qualification-package/implementation03'
OLD = ROOT / 'artifacts/verification/pat-sql-metadata-evaluation'
PROFILE = ROOT / 'artifacts/verification/qualification-current-profile'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, body):
    path = BASE / name; path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as out:
        out.write(body if type(body) is bytes else body.encode())


def read(path):
    return json.loads(path.read_bytes())


assert sha(SOURCE / 'index.json') == 'ec6df4066c89f38328030a28e2a5bd71d137abbc67cd51cb161cc246e2e8a268'
assert sha(OLD / 'index.json') == 'd0b36c6e2e6988d4237adb0d6cb0a8432559a24c9e5d70d50ea63a3c6dfe0de8'
assert sha(PROFILE / 'index.json') == '0be98141123f0b6d4af41b6efc152edfa2a60fe51293f5720829665434898093'
indices = [{r['path']: r for r in read(p / 'index.json')['files']} for p in (SOURCE, OLD, PROFILE)]
borrowed = []


def copy(path, name, index):
    row = index[str(path.relative_to(ROOT))]
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    write(name, path.read_bytes())
    borrowed.append({'source': str(path.relative_to(ROOT)), 'copy': name,
                     'bytes': row['bytes'], 'sha256': row['sha256']})


files = ['pat_io_trials.py', 'pat_io_configuration_capture.py', 'pat_io_canonical_blobs.py',
         'pat_io_page_encoding.py', 'contracts.py', 'pat_contracts.py', 'journal.py',
         'pat_catalog.py', 'procedures.py', 'registry.py', 'resource_catalog.py',
         'synthetic_io_catalog.py', 'synthetic_io_board.py']
for name in files:
    copy(SOURCE / 'project/hms' / name, 'references/' + name, indices[0])
for name in ('reference_functions.py', 'reference_helpers.py', 'runtime-inputs.json',
             'vendor/eval_rfc8785/__init__.py', 'vendor/eval_rfc8785/_impl.py'):
    copy(OLD / name, name, indices[1])
copy(OLD / 'child.py', 'original-metadata-child.py', indices[1])
copy(OLD / 'run.py', 'run.py', indices[1])


def source_tree(name):
    body = (BASE / 'references' / name).read_text()
    return body, ast.parse(body)


def method(name, cls_name, function_name):
    body, tree = source_tree(name)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == function_name)
    first = min([node.lineno] + [d.lineno for d in node.decorator_list])
    text = textwrap.dedent(''.join(body.splitlines(True)[first - 1:node.end_lineno]))
    assert ast.dump(ast.parse(text).body[0], include_attributes=False) == ast.dump(node, include_attributes=False)
    return text


def literal(name, wanted):
    _, tree = source_tree(name)
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1 and
                isinstance(n.targets[0], ast.Name) and n.targets[0].id == wanted)
    return ast.literal_eval(node.value)


write('legacy_method.py', method('pat_io_trials.py', 'IoTrialEngine', '_table'))
write('configuration_method.py', method('pat_io_configuration_capture.py', 'ConfiguredIoTrialEngine', '_configuration_table'))
assert (BASE / 'configuration_method.py').read_bytes() == (OLD / 'reference_method.py').read_bytes()
specs = {key: literal('pat_io_configuration_capture.py', key) for key in ('PROFILE', 'PUBLIC_META', 'TABLES')}
specs.update({key: literal('pat_io_trials.py', key) for key in ('RECORD_PROFILE', '_AUTHORITY', '_BOARD')})
write('table-specifications.json', json.dumps(specs, indent=2) + '\n')

journal_methods = ['_transaction', '_reject_commit_reentry', '_require_at_commit',
                   '_check_business_commit', '_meta', '_set_meta']
write('journal_methods.py', '\n\n'.join(method('journal.py', 'Journal', name) for name in journal_methods))
write('catalog_method.py', method('pat_catalog.py', 'PatCatalog', '_verify_evidence'))
body, tree = source_tree('journal.py')
node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == '_CommitChecks')
first = min([node.lineno] + [d.lineno for d in node.decorator_list])
write('commit_state.py', ''.join(body.splitlines(True)[first - 1:node.end_lineno]))

authority = [{'source': 'journal.py', 'script': literal('journal.py', '_DDL')}]
for name in ('registry.py', 'procedures.py', 'resource_catalog.py'):
    authority.extend({'source': name, 'statement': s} for s in literal(name, '_DDL'))
_, tree = source_tree('synthetic_io_catalog.py')
catalog_ddl = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and
               type(n.value) is str and n.value.startswith('CREATE TABLE ')]
assert len(catalog_ddl) == 5
authority.extend({'source': 'synthetic_io_catalog.py', 'statement': s} for s in catalog_ddl)
body, tree = source_tree('synthetic_io_board.py')
node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_create')
assignment = next(n for n in ast.walk(node) if isinstance(n, ast.Assign) and len(n.targets) == 1 and
                  isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'statements')
board_ddl = ast.literal_eval(assignment.value)
assert len(board_ddl) == 7
write('ddl.json', json.dumps({'authority': authority,
    'board': [{'source': 'synthetic_io_board.py', 'statement': s} for s in board_ddl]}, indent=2) + '\n')

case = PROFILE / 'harness02/attempts/attempt02-profile/scratch/test_actual_original_matrix_catalog_admission_and_cold_history/supervisor/1fa51266feef43e8bf8d435d5ed6585a/output/case-00'
for kind, summary in [('records', '000036.json'), ('configuration', '000017.json')]:
    path = case / kind / summary
    copy(path, 'documents/' + kind + '/summary.json', indices[2])
    document = read(path)
    for table in document['value']['tables']:
        for reference in table['pages']:
            page = case / kind / reference['path']
            assert page.stat().st_size == reference['bytes'] and sha(page) == reference['sha256']
            copy(page, 'documents/' + kind + '/' + reference['path'], indices[2])

old_child = (OLD / 'child.py').read_text()
bootstrap = old_child[:old_child.index('reference, candidate = load_method(')]
bootstrap = bootstrap.replace('"""Exact method comparison on new memory databases, with a memory evidence sink."""',
    '"""Pinned standard-library and exact validation-code bootstrap."""')
bootstrap = bootstrap.replace("'subprocess.Popen', 'os.system', 'os.exec', 'os.fork', 'os.forkpty', 'os.posix_spawn'",
    "'subprocess.Popen', 'os.system', 'os.exec', 'os.fork', 'os.forkpty', 'os.posix_spawn',\n        'sqlite3.enable_load_extension', 'sqlite3.load_extension'")
write('bootstrap.py', bootstrap)
write('bootstrap.patch', ''.join(difflib.unified_diff(
    old_child[:old_child.index('reference, candidate = load_method(')].splitlines(True), bootstrap.splitlines(True),
    fromfile='preceding/bootstrap-prefix', tofile='bootstrap.py')))
write('borrowed-inputs.json', json.dumps(borrowed, indent=2) + '\n')
write('PREPARATION.json', json.dumps({'sourceIndexSha256': sha(SOURCE / 'index.json'),
    'borrowedInputs': len(borrowed), 'coreModulesCopied': len(files),
    'legacyTables': 29, 'configurationTables': 15, 'retainedBaselinePages': 46,
    'captureMethodsUnchanged': True, 'journalMethodsExact': journal_methods,
    'catalogEvidenceMethodExact': True, 'authorityStatementCacheSizes': [0, 128, 256],
    'boardStatementCacheSize': 128, 'databaseConnectionsOpened': 0,
    'productionRuntimeChanged': False}, indent=2) + '\n')
print(json.dumps({'borrowedInputs': len(borrowed), 'baselinePages': 46,
                  'databaseConnectionsOpened': 0, 'runtimeImported': False}))
