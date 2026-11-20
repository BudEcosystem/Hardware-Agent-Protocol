"""Freeze the new consumer and exact, original-bound storage-control scopes."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path.cwd()
BASE = ROOT / 'artifacts/implementation/pat-io-evidence-import'
SOURCE = BASE / 'implementation01'
PRIOR = ROOT / 'artifacts/implementation/pat-io-execution-handoff/harness26'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path, value):
    with path.open('x') as stream: stream.write(json.dumps(value, indent=2) + '\n')
def inventory(folder, rooted=False):
    rows = []
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            if path.suffix == '.py': ast.parse(path.read_bytes())
            rows.append(dict(path=path.relative_to(ROOT if rooted else folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    return sorted(rows, key=lambda row: row['path'])

inherited = read(SOURCE / 'baseline-inputs.json')['inheritedProjectInputs']
old = ROOT / 'artifacts/implementation/pat-io-execution-handoff/implementation02/project'
assert len(inherited) == 253
for row in inherited:
    path = ROOT / row['path']; copied = SOURCE / 'project' / path.relative_to(old)
    assert sha(path) == row['sha256'] == sha(copied)
tree = ast.parse((SOURCE / 'project/tests/test_io_evidence_import.py').read_bytes())
cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
targets = sorted('test_io_evidence_import.IoEvidenceImportTests.' + node.name
    for node in cls.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'))
assert len(targets) == 23 and len(inventory(SOURCE / 'project')) == 259
review = [
    'All253 inherited project files remain byte-identical. Five host-only evidence modules and one test module are added. The producer source/image selection is unchanged.',
    'The public import accepts evaluator/run only and resolves the actual execution store, original reservation, handoff, supervisor authority and terminal attempt. No caller-selected path, callback, return or archive is accepted.',
    'The reader uses no-follow/nonblocking file opens, bounded directories and bodies, original flock identity/quiescence, exact input bytes and archived output closure. It never signals a stored PID.',
    'The full semantic reducer runs outside Journal transactions; commit rechecks current admin and exact original binding. The store has explicit count/actual-byte/metadata limits and transactional publication. These limits are not a filesystem quota.',
    'Historical lookup validates current body hashes/closure and authority association. Reinspection independently repeats semantic checks outside Journal transactions. Neither operation provides catalog admission or physical qualification.',
    'Positive storage fixtures substitute launch and semantic inspection, write explicit fixture provenance and execute no producer. They cannot establish a real worker, end-to-end qualification, learning or physical success.',
    'Each of23 exact control scopes has the original180-second/16MiB retention ceilings, exactly three possible SQLite connections and no network/subprocesses in the child. Corruption is retained, never repaired.',
    'Primary-agent review only. Full-matrix retained-data reduction, actual bound worker and catalog integration remain required beyond these controls.'
]
write(SOURCE / 'source-review.json', dict(reviewed=review, unchangedInheritedProjectFiles=253,
    newProductionFiles=5, newTestMethods=23, independentReview=False, releasedBy='primary-agent',
    projectExecutionDuringPreparation=False))
(SOURCE / 'README.md').write_text('# Archived I/O evidence consumer\n\n[Design](../DESIGN.md), [source review](source-review.json). All253 inherited files are unchanged. This candidate adds a separately pinned host consumer and23 storage/reader controls. Positive storage fixtures substitute the semantic oracle; they do not establish complete worker qualification.\n')
rows = inventory(SOURCE, True); assert len(rows) == 262
write(SOURCE / 'index.json', dict(scope='Host-only original-run evidence import and bounded controls.', files=rows))
pin = sha(SOURCE / 'index.json')
old_targets = read(PRIOR / 'targets.json')['targets']
for i, target in enumerate(targets, 1):
    harness = BASE / ('harness%02d' % i); harness.mkdir(); (harness / 'references').mkdir()
    borrowed = []
    for name in ('run_attempt.py', 'attempt_child.py', 'references/approved-external-roots.json'):
        source = PRIOR / name; dest = harness / 'references' / Path(name).name
        shutil.copyfile(source, dest)
        borrowed.append(dict(source=source.relative_to(ROOT).as_posix(), copy=dest.relative_to(harness).as_posix(), bytes=source.stat().st_size, sha256=sha(source)))
    write(harness / 'borrowed-inputs.json', borrowed)
    write(harness / 'targets.json', dict(testCount=1, targets=[target]))
    for name in ('run_attempt.py', 'attempt_child.py'):
        original = (PRIOR / name).read_text()
        text = original.replace('52590e9723805e43f76ad50c94d306d4d6a45c031e00b5fff2b6572c38ee4b90', pin)
        text = text.replace('pat-io-execution-handoff/implementation02', 'pat-io-evidence-import/implementation01')
        text = text.replace("here.parent / 'implementation02'", "here.parent / 'implementation01'")
        text = text.replace('len(expected) != 256', 'len(expected) != 262')
        text = text.replace("'frozenPreparationInputCount': 256", "'frozenPreparationInputCount': 262")
        text = text.replace("'projectInputCount': 253", "'projectInputCount': 259")
        text = text.replace('len(selected) != 253', 'len(selected) != 259')
        text = text.replace('exactly 253 files', 'exactly 259 files')
        assert text.count(repr(old_targets)) == 1
        text = text.replace(repr(old_targets), repr([target]))
        if name == 'attempt_child.py':
            text = text.replace("name.startswith('test_')", "name.startswith('test_') or name == 'evidence' or name.startswith('evidence.')")
        ast.parse(text); (harness / name).write_text(text)
        (harness / (name + '.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True), text.splitlines(True), fromfile=str(PRIOR / name), tofile=str(harness / name))))
    scope = 'One authority/reader/storage evidence-import control. Launch and successful semantic inspection are explicit fixtures; no worker is executed.'
    (harness / 'SCOPE.md').write_text('# Exact control scope\n\n' + scope + '\n\n[Targets](targets.json), [source](../implementation01/README.md). Original180-second/16MiB ceilings and three SQLite connections.\n')
    (harness / 'README.md').write_text('# Evidence import control\n\n[Scope](SCOPE.md), [source](../implementation01/README.md).\n')
    write(harness / 'review.json', dict(scope=scope, tests=1, sourceIndexSha256=pin, targetSha256=sha(harness / 'targets.json'),
        inheritedHarnessIndexSha256=sha(PRIOR / 'index.json'), reviewed=review, independentReview=False,
        releasedBy='primary-agent', controlTargets=[target], sqliteConnectionsMaximum=3,
        projectInputCount=259, frozenPreparationInputCount=262))
    write(harness / 'index.json', dict(scope=scope, files=inventory(harness)))
print(json.dumps(dict(sourceIndexSha256=pin, unchangedInheritedProjectFiles=253, newMethods=23, harnesses=23)))
