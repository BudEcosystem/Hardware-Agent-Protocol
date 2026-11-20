"""Verify exact source scope, then freeze the single local experiment."""
import ast
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(node):
    return ast.dump(node, include_attributes=False)


def write(name, body):
    with (BASE / name).open('x') as stream:
        json.dump(body, stream, indent=2); stream.write('\n')


original = ast.parse((BASE / 'references/pat_io_configuration_capture.py').read_bytes())
candidate = ast.parse((BASE / 'candidate-pat_io_configuration_capture.py').read_bytes())
methods = []
for tree in (original, candidate):
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ConfiguredIoTrialEngine')
    methods.append(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_configuration_table'))
for node, name in zip(methods, ('reference_method.py', 'candidate_method.py')):
    assert dump(node) == dump(ast.parse((BASE / name).read_bytes()).body[0])
left, right = methods


def assignment_index(nodes, name):
    return next(i for i, n in enumerate(nodes) if isinstance(n, ast.Assign) and
                len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == name)


old_start = assignment_index(left.body, 'actual_types')
new_start = assignment_index(right.body, 'type_check')
assert old_start == new_start
assert [dump(n) for n in left.body[:old_start]] == [dump(n) for n in right.body[:new_start]]
old_end = assignment_index(left.body, 'sizes') + 1
new_end = assignment_index(right.body, 'sizes') + 1
assert [dump(n) for n in left.body[old_end:]] == [dump(n) for n in right.body[new_end:]]
assert len(left.body[old_start:old_end]) == 3
assert len(right.body[new_start:new_end]) == 5
right.body = left.body
assert dump(original) == dump(candidate)

contract_source = ast.parse((BASE / 'references/contracts.py').read_bytes())
extracted = ast.parse((BASE / 'reference_functions.py').read_bytes())
source_names = {n.name: n for n in contract_source.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
assert len(extracted.body) == 7
for node in extracted.body:
    assert dump(node) == dump(source_names[node.name])
contracts_text = (BASE / 'references/contracts.py').read_text()
helpers = contracts_text[contracts_text.index('from types import FunctionType as _FunctionType'):contracts_text.index('_SCHEMA =')].rstrip() + '\n'
assert helpers == (BASE / 'reference_helpers.py').read_text()

borrowed = json.loads((BASE / 'borrowed-inputs.json').read_bytes())
for row in borrowed:
    original_path, copied = ROOT / row['source'], BASE / row['copy']
    assert original_path.stat().st_size == copied.stat().st_size == row['bytes']
    assert sha(original_path) == sha(copied) == row['sha256']

for path in BASE.rglob('*.py'):
    ast.parse(path.read_bytes(), str(path))
write('SOURCE_REVIEW.json', {
    'reviewer': 'primary-agent', 'independentReview': False,
    'configurationCaptureOnly': True, 'changedMethods': ['ConfiguredIoTrialEngine._configuration_table'],
    'schemaKeysAndRowCountPrefixAstExact': True, 'sizeGuardRowsCellValidationPagesSuffixAstExact': True,
    'allOtherModuleAstExact': True, 'legacyTableUnchanged': True,
    'publicParserEncoderDefinitionsExact': 7, 'canonicalizerHelpersExact': True,
    'borrowedInputsVerified': len(borrowed), 'typeSizeQueryCountBefore': 2, 'typeSizeQueryCountAfter': 1,
    'rowCountGuardStillBeforeMetadata': True, 'freshMetadataEveryCall': True,
    'typeRefusalBeforeSizeRefusal': True, 'durabilityCodeChanged': False,
    'productionAdopted': False, 'wholeWorkerGateStillRequired': True,
    'limits': ['The memory evidence sink substitutes durable writes and reservations.',
               'Selected mutation boundaries do not prove arbitrary concurrent-writer equivalence.',
               'Combined aggregation does more work before refusing invalid types; the preceding row bound remains.',
               'Local timings do not prove complete-worker deadline compliance or physical behavior.']})

old_runner = ROOT / 'artifacts/verification/pat-ascii-canonical-evaluation/run.py'
with (BASE / 'run.py').open('xb') as stream:
    stream.write(old_runner.read_bytes().replace(
        b'One owned isolated pure-evaluation child; preserve every original result.',
        b'One isolated memory-SQLite evaluation child; preserve every original result.'))
files = []
for path in sorted(BASE.rglob('*')):
    if path.is_file():
        assert not path.is_symlink()
        files.append({'path': str(path.relative_to(BASE)), 'bytes': path.stat().st_size, 'sha256': sha(path)})
write('inputs.json', {'files': files, 'productionAdopted': False,
                      'allowedDatabases': [':memory:'], 'qualifiedWorkerPermitted': False})
print(json.dumps({'frozenInputs': len(files), 'inputIndexSha256': sha(BASE / 'inputs.json'),
                  'sourceScopeVerified': True, 'databaseConnectionsOpened': 0}))
