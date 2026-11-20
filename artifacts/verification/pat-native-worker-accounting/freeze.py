"""Release only the reviewed observer composition under the original scope."""
import ast
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
HARNESS = BASE / 'harness01'
SOURCE = ROOT / 'artifacts/implementation/pat-native-supervisor/implementation02'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    return json.loads(path.read_bytes())
def put(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2);stream.write('\n')
assert not (HARNESS / 'index.json').exists()
assert sha(SOURCE / 'index.json') == '255b919194d150572c7b7876d941fb2e7d5866e36cdc119e91608da4b85ddc18'
for row in read(SOURCE / 'index.json')['files']:
    assert sha(ROOT / row['path']) == row['sha256']
controls = read(BASE / 'controls.json')
assert controls['status'] == 'passed' and controls['testsRun'] == 21 and controls['sourceUnchanged']
assert controls['deniedEvents'] == []
assert all(controls[key] == 0 for key in ('failures', 'errors', 'skips', 'expectedFailures', 'unexpectedSuccesses'))
for row in controls['before']:
    assert (BASE / row['path']).stat().st_size == row['bytes'] and sha(BASE / row['path']) == row['sha256']
child = ast.parse((HARNESS / 'attempt_child.py').read_bytes())
embedded = {node.name: ast.dump(node) for node in child.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
for node in ast.parse((BASE / 'observer.py').read_bytes()).body:
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        assert embedded[node.name] == ast.dump(node)
put(HARNESS / 'review.json', dict(reviewer='primary-agent', independentReview=False,
    sourceIndexSha256=sha(SOURCE / 'index.json'), pureControls=21, observerControls=15, compositionControls=6,
    observerSha256=sha(BASE / 'observer.py'), controlsSha256=sha(BASE / 'controls.json'),
    embeddedObserverAstEqual=True, nativeGuardAndOriginAstsEqual=True,
    projectFilesChanged=0, projectFiles=291, originalCases=30,
    workerMaxWallMs=60000, parentMaxSeconds=180, parentSqliteOpens=6,
    scratchBytes=268435456, vaultBytes=15728640, singleFileBytes=16777216, heldSnapshotMaxSeconds=5,
    addedWaits=0, addedSignals=0, pidBasedCounterReads=0, sourcePatApplications=0,
    diagnosticOnly=True, actualScopeNotYetExecuted=True))
rows = []
for path in sorted(HARNESS.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        rows.append(dict(path=str(path.relative_to(HARNESS)), bytes=path.stat().st_size, sha256=sha(path)))
put(HARNESS / 'index.json', dict(scope='Exact native candidate plus harness-only original-process accounting', files=rows))
print(json.dumps(dict(harnessIndexSha256=sha(HARNESS / 'index.json'), pureControls=21, projectChanges=0)))
