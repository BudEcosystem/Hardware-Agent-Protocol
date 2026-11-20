"""Freeze a harness-only diagnostic after the pure observer controls pass."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ORIGINAL = ROOT / 'artifacts/implementation/pat-io-proof-batch'
SOURCE = ORIGINAL / 'implementation01'
TEMPLATE = ORIGINAL / 'harness02'
HARNESS = BASE / 'harness01'
SOURCE_PIN = 'a7e03e59584b61e09efe40fbd093c423acfdc4c037c6d5d24273019bdda3f2b5'
TEMPLATE_PIN = '094098cab10de007e509f99895997915f6956634cb045f0d241ae333a01b08dc'
RESEARCH_PIN = '9a7a88ac0535e1bb22a6f496f2d6579b414a616a8d3aea5810fb3ed67647ce45'

def sha(path):
    assert not path.is_symlink() and path.is_file() and path.stat().st_size <= 16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path): return json.loads(path.read_bytes())
def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream: stream.write(body if type(body) is bytes else body.encode())
def dump(path, value): write(path, json.dumps(value, indent=2) + '\n')
def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)
def inventory(folder):
    return [dict(path=path.relative_to(folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path))
            for path in sorted(folder.rglob('*')) if path.is_file()]

assert not HARNESS.exists()
for folder, pin, prefix in ((SOURCE, SOURCE_PIN, ROOT), (TEMPLATE, TEMPLATE_PIN, TEMPLATE),
        (ROOT/'research/host-contract/worker-accounting', RESEARCH_PIN, ROOT/'research/host-contract/worker-accounting')):
    assert sha(folder/'index.json') == pin
    for row in read(folder/'index.json')['files']:
        path = prefix/row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
controls = read(BASE/'controls.json')
assert controls['status'] == 'passed' and controls['testsRun'] == 15
assert all(controls[name] == 0 for name in ('failures', 'errors', 'skips', 'expectedFailures', 'unexpectedSuccesses'))
assert controls['sourceUnchanged'] and controls['deniedEvents'] == []
for row in controls['before']:
    assert (BASE/row['path']).stat().st_size == row['bytes'] and sha(BASE/row['path']) == row['sha256']
observer = (BASE/'observer.py').read_text()
borrowed = []
for name in ('run_attempt.py', 'attempt_child.py', 'targets.json', 'references/approved-external-roots.json'):
    path = TEMPLATE/name
    copied = 'references/original-' + path.name
    write(HARNESS/copied, path.read_bytes())
    borrowed.append(dict(source=path.relative_to(ROOT).as_posix(), copy=copied,
        bytes=path.stat().st_size, sha256=sha(path)))
    original = path.read_text()
    updated = original
    if name == 'run_attempt.py':
        updated = replace_once(updated, "stage = here.parent / 'implementation01'",
            "stage = here.parents[3] / 'artifacts/implementation/pat-io-proof-batch/implementation01'")
        updated = replace_once(updated, "prefix='hms-io-proof-batch-actual-'", "prefix='hms-worker-accounting-'")
    elif name == 'attempt_child.py':
        updated = replace_once(updated, 'current_test = None\nsqlite_connections = []',
            'current_test = None\naccounting_launch_audit = []\nsqlite_connections = []')
        needle = "        if not valid: prohibited.append(event); raise RuntimeError('Only exact owned I/O entry may launch')"
        updated = replace_once(updated, needle, needle + "\n        if accounting_launch_audit:\n            prohibited.append(event); raise RuntimeError('Diagnostic permits exactly one original worker launch')\n        accounting_launch_audit.append({'argv': list(argv), 'cwd': str(cwd), 'testId': current_test})")
        needle = '\ndef actual_origins():'
        insertion = ('\n# BEGIN FROZEN HARNESS OBSERVER\n' + observer +
            "\nimport subprocess\nworker_accounting = _WorkerAccounting(persist=write)\nsubprocess.Popen = _observed_popen(subprocess.Popen, worker_accounting)\n# END FROZEN HARNESS OBSERVER\n")
        updated = replace_once(updated, needle, insertion + needle)
        updated = replace_once(updated, '            executed_ids.append(test.id())\n            super().startTest(test)',
            '            executed_ids.append(test.id())\n            worker_accounting.start_test(test.id())\n            super().startTest(test)')
        updated = replace_once(updated, '            super().stopTest(test)\n            current_test = None',
            '            super().stopTest(test)\n            worker_accounting.stop_test()\n            current_test = None')
        needle = "    finalize('sqlite-connections', lambda: write('sqlite-connections.json', sqlite_connections))"
        updated = replace_once(updated, needle, needle + "\n    finalize('accounting-launch-audit', lambda: write('worker-accounting-launch-audit.json', accounting_launch_audit))")
    if name.endswith('.py'):
        ast.parse(updated)
        write(HARNESS/(name+'.patch'), ''.join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True),
            fromfile='original/'+name, tofile='accounting/'+name)))
    write(HARNESS/name, updated)
dump(HARNESS/'borrowed-inputs.json', borrowed)
write(HARNESS/'SCOPE.md', (BASE/'DESIGN.md').read_bytes())
write(HARNESS/'README.md', '# Whole-worker accounting harness\n\n[Scope](SCOPE.md). The original frozen project is used byte-for-byte; only this harness adds observations.\n')
# Compare every embedded helper's AST with the already tested standalone helper.
child = ast.parse((HARNESS/'attempt_child.py').read_text())
embedded = {node.name: ast.dump(node, include_attributes=False) for node in child.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
helper = ast.parse(observer)
for node in helper.body:
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        assert embedded[node.name] == ast.dump(node, include_attributes=False)
dump(HARNESS/'review.json', dict(reviewer='primary-agent', independentReview=False,
    sourceIndexSha256=SOURCE_PIN, templateIndexSha256=TEMPLATE_PIN, researchIndexSha256=RESEARCH_PIN,
    observerSha256=sha(BASE/'observer.py'), controlsSha256=sha(BASE/'controls.json'), pureControls=15,
    embeddedObserverAstEqual=True, projectFilesChanged=0, projectFiles=288, originalCases=30,
    workerMaxWallMs=60000, parentMaxSeconds=180, parentSqliteOpens=6, scratchBytes=268435456,
    vaultBytes=15728640, singleFileBytes=16777216, heldSnapshotMaxSeconds=5,
    addedWaits=0, addedSignals=0, pidBasedCounterReads=0, sourcePatApplications=0,
    diagnosticOnly=True, actualScopeNotYetExecuted=True))
dump(HARNESS/'index.json', dict(scope='Harness-only whole-worker accounting; source and all original bounds unchanged', files=inventory(HARNESS)))
print(json.dumps(dict(sourceIndexSha256=SOURCE_PIN, harnessIndexSha256=sha(HARNESS/'index.json'), pureControls=15, changedProjectFiles=0)))
