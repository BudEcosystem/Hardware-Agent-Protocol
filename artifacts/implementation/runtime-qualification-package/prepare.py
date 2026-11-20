"""Acquire and install the exact verified library slice and five semantic checks."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = BASE.parent / 'pat-statement-cache/implementation01'
PROJECT = SOURCE / 'project'
PIN = '7ecd42fec5cef9374573ae8b3d0747060bdc8c4cd8ca552e9c3de4d64a2ec23e'
RECEIPT = ROOT / 'artifacts/verification/runtime-attempts/20261109T011608.358669Z-115386951c7c/receipt.json'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, body):
    p.parent.mkdir(parents=True, exist_ok=True)
    if type(body) is not bytes:
        body = (body if type(body) is str else json.dumps(body, indent=2) + '\n').encode()
    with p.open('xb') as out: out.write(body)
def row(p): return dict(path=str(p.relative_to(ROOT)), bytes=p.stat().st_size, sha256=sha(p))

assert not (BASE / 'selected-source.json').exists()
assert sha(SOURCE / 'index.json') == PIN
for item in read(SOURCE / 'index.json')['files']:
    p = ROOT / item['path']
    assert not p.is_symlink() and p.stat().st_size == item['bytes'] and sha(p) == item['sha256']
assert sha(RECEIPT) == '68c1d8ec28038cc30167b11898c8484b60c94a0fd17b669534eb5a268e8d56c7'
receipt = read(RECEIPT)
assert receipt['passed'] and receipt['tests'] == 861 and len(receipt['files_after']) == 161
for item in receipt['files_after']:
    p = ROOT / item['path']
    assert p.stat().st_size == item['bytes'] and sha(p) == item['sha256']
    write(BASE / 'baseline' / item['path'], p.read_bytes())
write(BASE / 'baseline/receipt.json', RECEIPT.read_bytes())

installed, unchanged = [], []
for group in ('hms', 'hms_qualification', 'schemas'):
    for p in sorted((PROJECT / group).rglob('*')):
        if not p.is_file(): continue
        name = p.relative_to(PROJECT); destination = ROOT / name
        if destination.exists():
            assert destination.read_bytes() == p.read_bytes(), str(name)
            unchanged.append(str(name))
        else:
            assert group in ('hms', 'hms_qualification')
            write(BASE / 'selected-source' / name, p.read_bytes())
            write(destination, p.read_bytes())
            installed.append(dict(path=str(name), originalPath=str(p.relative_to(ROOT)),
                bytes=p.stat().st_size, sha256=sha(p)))
assert len(installed) == 82 and len(unchanged) == 50
assert sum(r['path'].startswith('hms/') for r in installed) == 40
assert sum(r['path'].startswith('hms_qualification/') for r in installed) == 42

original_test = PROJECT / 'tests/test_business_precommit.py'
test_source = original_test.read_text()
tree = ast.parse(test_source)
original_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'VaultCommitTests')
class_text = ast.get_source_segment(test_source, original_class)
methods = [n.name for n in original_class.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
assert len(methods) == 5
header = ('"""Held-vault evidence must remain valid through the Journal business commit."""\n'
          'import unittest\nfrom unittest.mock import patch\n'
          'from test_business_precommit import BusinessCommitTests, TABLES\n\n\n')
selection = '\n\n\ndef load_tests(loader, tests, pattern):\n'
selection += '    """Run exactly the five vault methods; inherited checks already run separately."""\n'
selection += '    names = ' + repr(tuple(methods)) + '\n'
selection += '    return unittest.TestSuite(VaultCommitTests(name) for name in names)\n'
test = header + class_text + selection
new_class = next(n for n in ast.parse(test).body if isinstance(n, ast.ClassDef))
assert ast.dump(new_class) == ast.dump(original_class)
name = 'tests/test_qualification_vault_commit.py'
write(BASE / 'selected-source' / name, test)
write(ROOT / name, test)
write(BASE / 'references/test_business_precommit.py', original_test.read_bytes())
write(BASE / 'references/namespace-map.json', (SOURCE / 'namespace-map.json').read_bytes())
write(BASE / 'references/identity-pins.json', (SOURCE / 'identity-pins.json').read_bytes())

script = ROOT / 'scripts/check_runtime.py'
before = script.read_text()
needle = '    paths = set([*root.glob("hms/**/*.py"), *root.glob("tests/**/*.py"),'
assert before.count(needle) == 1
after = before.replace(needle, needle + '\n'
    '                 *root.glob("hms_qualification/**/*.py"),\n'
    '                 *root.glob("hms_qualification/**/*.c"),\n'
    '                 *root.glob("hms_qualification/**/*.so"),')
ast.parse(after)
write(BASE / 'selected-source/scripts/check_runtime.py', after)
write(BASE / 'runtime-runner.patch', ''.join(difflib.unified_diff(before.splitlines(True),
    after.splitlines(True), fromfile='baseline/scripts/check_runtime.py', tofile='installed/scripts/check_runtime.py')))
script.write_text(after)

inspector_path = SOURCE.parent / 'inspect_package.py'
inspector = inspector_path.read_text()
inspector = inspector.replace("PROJECT = BASE / 'implementation01/project'", 'PROJECT = BASE.parents[2]')
inspector = inspector.replace("BASE / 'implementation01/namespace-map.json'", "BASE / 'references/namespace-map.json'")
inspector = inspector.replace("if event.startswith('socket.') or event in {", "if event.startswith(('socket.', 'hms.retention.')) or event in {")
needle = 'report = dict(passed=True, importEffects=False,'
assert inspector.count(needle) == 1
inspector = inspector.replace(needle,
    "from hms_qualification.supervisor import retention_native\n"
    "assert not retention_native._ATTEMPTED and retention_native._IMAGE_FD is None\n"
    "assert retention_native.MODULE_NAME not in sys.modules\n" + needle)
write(BASE / 'inspect_installed.py', inspector)
write(BASE / 'inspection.patch', ''.join(difflib.unified_diff(inspector_path.read_text().splitlines(True),
    inspector.splitlines(True), fromfile='candidate/inspect_package.py', tofile='installed/inspect_installed.py')))
write(BASE / 'selected-source.json', dict(sourceIndexSha256=PIN, sourceProjectFiles=304,
    installedLibraryFiles=installed, existingProductionFilesUnchanged=unchanged,
    nativeProfile='hms.retention.linux-cpython312-x86_64/1',
    nativeBinarySha256='ce475ab2a70fb94e84d5d2f2f4c22cb8858d3305005bd154ebda996aae0774ff',
    newTests=[name + ':' + method for method in methods],
    testClassAstUnchanged=True, publicQualificationMounted=False, originalWorkerRepeated=False))
write(BASE / 'preparation-review.json', dict(reviewer='primary-agent', independentReview=False,
    sourceIndexSha256=PIN, previousRuntimeReceiptSha256=sha(RECEIPT), baselineInputs=161,
    installedLibraryFiles=82, existingProductionFilesUnchanged=50, newVaultCommitTests=5,
    originalTestClassSha256=hashlib.sha256(class_text.encode()).hexdigest(),
    testSourceSha256=sha(original_test), changedExistingFiles=['scripts/check_runtime.py'],
    existingTestsUnchanged=True, runtimeChecksPending=True, noPublicMethodsAdded=True,
    noNativeProfileBroadened=True, noPhysicalExecution=True))
print(json.dumps(dict(installedLibraryFiles=82, existingProductionFilesUnchanged=50,
    newVaultCommitTests=5, changedExistingFiles=['scripts/check_runtime.py'])))
