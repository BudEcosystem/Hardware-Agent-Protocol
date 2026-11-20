"""Static exact-source and fixture review before the one bounded evaluation."""
import ast
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def dump(node):
    return ast.dump(node, include_attributes=False)


def write(name, value):
    with (BASE / name).open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


def original_method(filename, class_name, name):
    tree = ast.parse((BASE / 'references' / filename).read_bytes())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)


reviewed = []
for extracted, filename, class_name, wanted in [
    ('legacy_method.py', 'pat_io_trials.py', 'IoTrialEngine', ['_table']),
    ('configuration_method.py', 'pat_io_configuration_capture.py', 'ConfiguredIoTrialEngine', ['_configuration_table']),
    ('journal_methods.py', 'journal.py', 'Journal', ['_transaction', '_reject_commit_reentry',
       '_require_at_commit', '_check_business_commit', '_meta', '_set_meta']),
    ('catalog_method.py', 'pat_catalog.py', 'PatCatalog', ['_verify_evidence']),
]:
    nodes = ast.parse((BASE / extracted).read_bytes()).body
    assert [n.name for n in nodes] == wanted
    for node in nodes:
        assert dump(node) == dump(original_method(filename, class_name, node.name))
        reviewed.append(class_name + '.' + node.name)
source_tree = ast.parse((BASE / 'references/journal.py').read_bytes())
state = next(n for n in source_tree.body if isinstance(n, ast.ClassDef) and n.name == '_CommitChecks')
assert dump(ast.parse((BASE / 'commit_state.py').read_bytes()).body[0]) == dump(state)
source_tree = ast.parse((BASE / 'references/contracts.py').read_bytes())
definitions = {n.name: n for n in source_tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
functions = ast.parse((BASE / 'reference_functions.py').read_bytes()).body
assert len(functions) == 7
for node in functions:
    assert dump(node) == dump(definitions[node.name])
body = (BASE / 'references/contracts.py').read_text()
helpers = body[body.index('from types import FunctionType as _FunctionType'):body.index('_SCHEMA =')].rstrip() + '\n'
assert helpers == (BASE / 'reference_helpers.py').read_text()

borrowed = read(BASE / 'borrowed-inputs.json')
assert len(borrowed) == 69
for row in borrowed:
    original, copied = ROOT / row['source'], BASE / row['copy']
    assert original.stat().st_size == copied.stat().st_size == row['bytes']
    assert sha(original) == sha(copied) == row['sha256']
research = ROOT / 'research/host-contract/sqlite-cache-binding'
assert sha(research / 'index.json') == 'c1a9eca2686e7d0d3ee0a27321e859845732cc400ac3f3427e38d3b9c77ad2d9'
for row in read(research / 'index.json')['files']:
    assert sha(ROOT / row['path']) == row['sha256']
assert read(research / 'reading.json')['coveredLfLines'] == 4025
failure = BASE.parent / 'preparation01'
assert sha(failure / 'index.json') == '6e0f37f952ba64d996c929f5e8a1bdcc5f07afc2dc23a0d8f2eef4150024528c'
for row in read(failure / 'index.json')['files']:
    assert sha(failure / row['path']) == row['sha256']
for path in BASE.rglob('*.py'):
    ast.parse(path.read_bytes(), str(path))
specs = read(BASE / 'table-specifications.json')
assert len(specs['_AUTHORITY']) == 22 and len(specs['_BOARD']) == 7 and len(specs['TABLES']) == 15
assert len(read(BASE / 'documents/records/summary.json')['value']['tables']) == 29
assert len(read(BASE / 'documents/configuration/summary.json')['value']['tables']) == 15
ddl = read(BASE / 'ddl.json')
for area in ('authority', 'board'):
    for item in ddl[area]:
        text = item.get('statement', item.get('script'))
        assert text.lstrip().startswith(('CREATE TABLE ', 'CREATE INDEX '))
        assert all(word not in text.upper() for word in ('ATTACH ', 'DETACH ', 'LOAD_EXTENSION', 'VIRTUAL TABLE', 'CREATE TRIGGER'))
        assert text in (BASE / 'references' / item['source']).read_text(), item['source']

profile = read(BASE / 'fixture-profile.json')
assert profile['legacyProfile'] == 'hms.pat.io-trial-record/0.2'
profile_source = BASE / 'references/pat_io_conflict_capture.py'
assert sha(profile_source) == profile['sourceSha256']
values = [ast.literal_eval(n.value) for n in ast.walk(ast.parse(profile_source.read_bytes()))
          if isinstance(n, ast.Assign) and len(n.targets) == 1 and
          isinstance(n.targets[0], ast.Name) and n.targets[0].id == '_record_profile']
assert values == [profile['legacyProfile']]
for path in (BASE / 'documents/records').glob('*.json'):
    assert read(path)['profile'] == profile['legacyProfile']

write('SOURCE_REVIEW.json', {
    'reviewer': 'primary-agent', 'independentReview': False,
    'astExactMethods': reviewed, 'commitStateClassAstExact': True,
    'parserEncoderDefinitionsAstExact': 7, 'canonicalizerHelpersExact': True,
    'captureSqlChanged': False, 'legacyFixtureProfile': profile['legacyProfile'],
    'fixtureProfileMatchesRetainedSubclass': True, 'borrowedInputsVerified': 69,
    'authorityCacheSizes': [0, 128, 256], 'boardCacheSize': 128,
    'originalDdlLiteralsVerified': True, 'ddlTriggersAndExternalSourcesAbsent': True,
    'matchingBindingSourceReadLfLines': 4025,
    'researchIndexSha256': sha(research / 'index.json'),
    'failedPreparationIndexSha256': sha(failure / 'index.json'),
    'failedPreparationStartedChild': False,
    'fixtureSubstitutions': ['Memory-only connections replace file ownership and startup recovery.',
        'Memory writer replaces durability, reservations and publication; exact page encoding remains.',
        'Private reg_meta cursor_key is a fixture value, excluded from captured bytes.',
        'Memory Journal/catalog objects supply original method state without constructing a live runtime.',
        'The fixture caller aborts its write when evidence verification reports unavailable.'],
    'productionRuntimeChanged': False, 'fullWorkerQualificationStillRequired': True})

files = []
for path in sorted(BASE.rglob('*')):
    if path.is_file() and failure not in path.parents:
        assert not path.is_symlink()
        files.append({'path': str(path.relative_to(BASE)), 'bytes': path.stat().st_size, 'sha256': sha(path)})
write('inputs.json', {'files': files, 'allowedDatabase': ':memory:', 'qualifiedWorkerPermitted': False,
                     'failedPreparationIndexSha256': sha(failure / 'index.json')})
print(json.dumps({'frozenInputs': len(files), 'inputIndexSha256': sha(BASE / 'inputs.json'),
                  'astExactMethods': len(reviewed), 'databaseConnectionsOpened': 0}))
