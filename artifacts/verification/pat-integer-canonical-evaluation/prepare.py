"""Copy pinned pure functions, reviewed JCS, and fixed retained data; no imports."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = ROOT / 'artifacts/implementation/pat-native-supervisor/implementation02'
PRIOR = ROOT / 'artifacts/verification/pat-native-worker-accounting'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    return json.loads(path.read_bytes())
def put(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(body if type(body) is bytes else body.encode())
assert sha(SOURCE / 'index.json') == '255b919194d150572c7b7876d941fb2e7d5866e36cdc119e91608da4b85ddc18'
assert sha(PRIOR / 'index.json') == '3deeb84b5a3187a5b4c482483e673961525b88c5b690dc58945f3f685c316721'
rows = {row['path']: row for row in read(SOURCE / 'index.json')['files']}
borrowed = []
def copy(path, target, row=None):
    if row is not None:
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    put(BASE / target, path.read_bytes())
    borrowed.append(dict(source=str(path), copy=target, bytes=path.stat().st_size, sha256=sha(path)))
contracts = SOURCE / 'project/hms/contracts.py'
copy(contracts, 'references/contracts.py', rows[str(contracts.relative_to(ROOT))])
tree = ast.parse(contracts.read_bytes())
names = {'ContractError', '_number', '_object', '_bad_constant', 'check_tree', 'parse_json', 'canonical'}
selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
assert {node.name for node in selected} == names
body = contracts.read_text()
reference = '\n\n'.join(ast.get_source_segment(body, node) for node in selected) + '\n'
assert reference.count('result = rfc8785.dumps(value)') == 1
candidate = reference.replace('result = rfc8785.dumps(value)', 'result = _canonical_bytes(value)')
put(BASE / 'reference_functions.py', reference)
put(BASE / 'candidate_functions.py', candidate)
put(BASE / 'candidate.patch', ''.join(difflib.unified_diff(reference.splitlines(True), candidate.splitlines(True),
    fromfile='reference_functions.py', tofile='candidate_functions.py')))
for name in ('__init__.py', '_impl.py'):
    path = SOURCE / 'project/hms/_vendor/rfc8785' / name
    copy(path, 'vendor/eval_rfc8785/' + name, rows[str(path.relative_to(ROOT))])
prior_rows = {row['path']: row for row in read(PRIOR / 'index.json')['files']}
output = PRIOR / 'harness01/attempts/attempt01-accounting/scratch/test_actual_original_matrix_import_and_cold_vault_history/supervisor/ab34180777314fbfbc14b840709fcd90/output'
for name in ('candidate.json', 'installation.json', 'descriptor.json', 'bindings.json', 'matrix.json',
             'case-28/records/000000.json', 'case-28/records/000060.json', 'case-28/records/000119.json'):
    path = output / name
    assert path.stat().st_size <= 65536
    copy(path, 'documents/' + name.replace('/', '-'), prior_rows[str(path.relative_to(PRIOR))])
assets = ROOT / 'research/host-contract/repos/rfc8785.py/test/assets'
for group in ('input', 'output'):
    for path in sorted((assets / group).glob('*.json')):
        copy(path, 'vectors/' + group + '/' + path.name)
for name in ('__init__.py', 'encoder.py'):
    copy(Path('/usr/lib/python3.12/json') / name, 'references/installed-json-' + name)
put(BASE / 'borrowed-inputs.json', json.dumps(borrowed, indent=2) + '\n')
print(json.dumps(dict(borrowedInputs=len(borrowed), extractedFunctions=len(selected), projectImported=False)))
