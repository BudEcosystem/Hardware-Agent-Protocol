"""Freeze installed source and prove that the public receipt covers the package."""
import ast
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]

def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    body = value if type(value) is bytes else (json.dumps(value, indent=2) + '\n').encode()
    with p.open('xb') as out: out.write(body)
def row(p): return dict(path=str(p.relative_to(ROOT)), bytes=p.stat().st_size, sha256=sha(p))

assert not (BASE / 'inputs.json').exists()
selected = read(BASE / 'selected-source.json')
assert read(BASE / 'inspection01.json') == read(BASE / 'references/identity-pins.json')
assert (BASE / 'inspection01.stderr.txt').read_bytes() == b''
for r in selected['installedLibraryFiles']:
    p = ROOT / r['path']
    assert p.stat().st_size == r['bytes'] and sha(p) == r['sha256']
    assert p.read_bytes() == (BASE / 'selected-source' / r['path']).read_bytes()
old_tree = ast.parse((BASE / 'references/test_business_precommit.py').read_bytes())
new_tree = ast.parse((ROOT / 'tests/test_qualification_vault_commit.py').read_bytes())
base_tree = ast.parse((ROOT / 'tests/test_business_precommit.py').read_bytes())
def find_class(tree, name): return next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
assert ast.dump(find_class(old_tree, 'VaultCommitTests')) == ast.dump(find_class(new_tree, 'VaultCommitTests'))
old_base, current_base = [find_class(t, 'BusinessCommitTests') for t in (old_tree, base_tree)]
for tree in (old_base, current_base):
    tree.body = [n for n in tree.body if not isinstance(n, ast.FunctionDef) or n.name != 'setUp']
assert ast.dump(old_base) == ast.dump(current_base)
def tables(tree):
    return ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'TABLES' for t in n.targets)))
assert tables(old_tree) == tables(base_tree)
imports = [n for n in new_tree.body if isinstance(n, ast.ImportFrom) and n.module == 'test_business_precommit']
assert len(imports) == 1 and [n.name for n in imports[0].names] == ['BusinessCommitTests', 'TABLES']
loader = next(n for n in new_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'load_tests')
names = ast.literal_eval(next(n.value for n in loader.body if isinstance(n, ast.Assign)))
assert list(names) == [name.rsplit(':', 1)[1] for name in selected['newTests']]
assert len(names) == len(set(names)) == 5

runner = ROOT / 'scripts/check_runtime.py'
assert runner.read_bytes() == (BASE / 'selected-source/scripts/check_runtime.py').read_bytes()
# Evaluate only the reviewed input inventory function, not the runner or any test.
function = next(n for n in ast.parse(runner.read_bytes()).body if isinstance(n, ast.FunctionDef) and n.name == 'input_paths')
namespace = {'json': json, 'Path': Path}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(runner), 'exec'), namespace)
paths = namespace['input_paths'](ROOT)
assert len(paths) == len(set(paths)) == 244
original = read(BASE / 'baseline/receipt.json')
before = {r['path']: r for r in original['files_after']}
expected_new = {r['path'] for r in selected['installedLibraryFiles']} | {'tests/test_qualification_vault_commit.py'}
assert {str(p.relative_to(ROOT)) for p in paths} == set(before) | expected_new
changed = [name for name, r in before.items() if sha(ROOT / name) != r['sha256']]
assert changed == ['scripts/check_runtime.py']
for p in paths:
    assert p.is_file() and not p.is_symlink()
    write(BASE / 'inputs' / p.relative_to(ROOT), p.read_bytes())
rows = [row(p) for p in paths]
write(BASE / 'inputs.json', dict(files=rows, sourcePackageInstalled=True, publicQualificationMounted=False))
write(BASE / 'source-review.json', dict(reviewer='primary-agent', independentReview=False,
    publicInputs=244, originalInputsPreserved=161, unchangedPreviousInputs=160,
    changedPreviousInputs=changed, addedLibraryFiles=82, addedTestFiles=1,
    qualifiedSourceIdentityUnchanged=True, installedInspectionExactlyMatchesCandidate=True,
    originalVaultClassAstExact=True, baseClassExceptWorkspaceSetupExact=True,
    tableContractAndGlobalBindingExact=True, explicitlySelectedVaultTests=list(names),
    expectedPreviousTests=861, expectedFullTests=866,
    nativeInputAndCSourceCaptured=True, noPublicMethodsAdded=True,
    noWorkerOrNativeCodeLaunchedByInspection=True, fullRegressionPending=True,
    inputIndexSha256=sha(BASE / 'inputs.json')))
print(json.dumps(dict(publicInputs=244, installedLibraryFiles=82, expectedFullTests=866,
    inputIndexSha256=sha(BASE / 'inputs.json'))))
