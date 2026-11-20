"""Freeze exact validation reuse and inherited/new scopes without importing it."""
import ast
import copy
import difflib
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path.cwd()
B = ROOT/'artifacts/implementation/pat-io-document-validation'
O = ROOT/'artifacts/implementation/pat-io-service-runs'
S, P = B/'implementation01', O/'implementation01'
OLD_PIN = '8086023d524443fb617b654ad7573f1ef25a7388e12f991d28457457a720ba8d'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def write(path,value):
    with path.open('x') as stream:
        stream.write(json.dumps(value,indent=2)+'\n')

def inventory(folder, rooted=False):
    rows = []
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes())
            rows.append(dict(path=path.relative_to(ROOT if rooted else folder).as_posix(),
                             bytes=path.stat().st_size,sha256=sha(path)))
    return sorted(rows,key=lambda row:row['path'])

assert sha(P/'index.json') == OLD_PIN
baseline = read(S/'baseline-inputs.json')
assert baseline['sourceIndexSha256'] == OLD_PIN
for row in read(P/'index.json')['files']:
    assert sha(ROOT/row['path']) == row['sha256']
changed = []
for row in baseline['inheritedProjectInputs']:
    relative = (ROOT/row['path']).relative_to(P/'project')
    if sha(S/'project'/relative) != row['sha256']:
        changed.append(relative.as_posix())
assert len(baseline['inheritedProjectInputs']) == 246
assert changed == ['hms/pat_io_configuration_capture.py']
relative = changed[0]
before, after = (P/'project'/relative).read_text(), (S/'project'/relative).read_text()
old, new = ast.parse(before), ast.parse(after)
old_class = next(node for node in old.body if isinstance(node,ast.ClassDef))
new_class = next(node for node in new.body if isinstance(node,ast.ClassDef))
old_method = next(node for node in old_class.body if isinstance(node,ast.FunctionDef) and node.name == '_configuration_table')
new_method = next(node for node in new_class.body if isinstance(node,ast.FunctionDef) and node.name == '_configuration_table')
old_cell = next(node for node in old_method.body if isinstance(node,ast.FunctionDef) and node.name == 'cell')
new_method.body = [copy.deepcopy(old_cell) if isinstance(node,ast.FunctionDef) and node.name == 'cell' else node for node in new_method.body]
new.body = [node for node in new.body if not (isinstance(node,ast.ImportFrom) and node.module == 'pat_io_canonical_blobs')]
assert ast.dump(old,include_attributes=False) == ast.dump(new,include_attributes=False)
with (B/'capture-change.patch').open('x') as stream:
    stream.write(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str(P/'project'/relative),tofile=str(S/'project'/relative))))
tree = ast.parse((S/'project/tests/test_pat_io_canonical_blobs.py').read_bytes())
targets = sorted('test_pat_io_canonical_blobs.CanonicalBlobTests.'+node.name
    for cls in tree.body if isinstance(cls,ast.ClassDef) and cls.name == 'CanonicalBlobTests'
    for node in cls.body if isinstance(node,ast.FunctionDef) and node.name.startswith('test_'))
assert len(targets) == 19 and len(inventory(S/'project')) == 248
reviewed = [
    '245 inherited project files, including every inherited test, unchanged. Only the configuration-capture import and BLOB-cell branch change; the rest of its AST is identical. New pure memo and19 focused methods.',
    'All original SQL schema/count/type/size reads, payload fetches, locks, transaction checks, budgets, source/image identities, record bytes and durable write paths remain. The memo stores only immutable exact successful document bytes; no current authority or database value is cached.',
    'Per-engine64-entry/128KiB fixed byte-key bounds;65536-byte document maximum. Invalid values and exceptions never publish. Selected parser/encoder function/code/default/constant/object/escape changes clear reuse and retain original fallback behavior; post-validation dependency check precedes publication. Not Python-process attestation or an RSS quota.',
    'Focused19 controls have no SQL, subprocess, network, MCU or physical access. Scratch16MiB and outer180s unchanged. Existing caller-parser spy test keeps original two-call behavior through uncached fallback.',
    'All279 inherited methods remain selected separately, including reserved worker and two owner-loss failures. New image260 files/eight supervisor sources. Original60s group/owned-worker bounds, complete30-case matrix and all effect/storage ceilings remain.',
    'Fresh fixtures only; prior four failed attempts, three partial claims and all archived state remain unchanged. Primary-agent review only. No public mounting, promotion, acquired-controller/live-inference/service or adjacent-Harness execution.'
]
write(S/'source-review.json',dict(scope='Exact immutable canonical BLOB validation reuse',changedInheritedFiles=changed,
    unchangedInheritedFiles=245,newProjectFiles=2,reviewed=reviewed,independentReview=False,
    releasedBy='primary-agent',projectExecutionDuringPreparation=False))
with (S/'README.md').open('x') as stream:
    stream.write('# Canonical document validation reuse\n\n[Design](../DESIGN.md), [source review](source-review.json). Exact-byte validation only; no cached database or authority state. Execution acceptance remains separate.\n')
rows = inventory(S,True)
assert len(rows) == 251
write(S/'index.json',dict(scope='Frozen exact-byte canonical validation reuse and19 new controls.',files=rows))
pin = sha(S/'index.json')
for number in range(1,18):
    prior = O/('harness%02d'%(number if number <= 16 else 1))
    for row in read(prior/'index.json')['files']:
        assert sha(prior/row['path']) == row['sha256']
    old_targets = read(prior/'targets.json')['targets']
    selection = targets if number == 17 else old_targets
    harness = B/('harness%02d'%number)
    harness.mkdir(); (harness/'references').mkdir()
    borrowed = []
    for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
        source, destination = prior/name, harness/'references'/Path(name).name
        shutil.copyfile(source,destination)
        borrowed.append(dict(source=source.relative_to(ROOT).as_posix(),copy=destination.relative_to(harness).as_posix(),bytes=source.stat().st_size,sha256=sha(source)))
    write(harness/'borrowed-inputs.json',borrowed)
    write(harness/'targets.json',dict(testCount=len(selection),targets=selection))
    for name in ('run_attempt.py','attempt_child.py'):
        original = (prior/name).read_text()
        updated = original.replace(OLD_PIN,pin).replace(O.name,B.name)
        updated = re.sub(r'\b249\b','251',updated)
        updated = re.sub(r'\b246\b','248',updated)
        if number == 17:
            updated = re.sub(r'\b206\b','19',updated)
            if name == 'run_attempt.py':
                assert updated.count(repr(old_targets)) == 1
                updated = updated.replace(repr(old_targets),repr(selection))
            else:
                start = updated.index('CONTROL_TARGETS = ')
                end = updated.index('\nCONTROL_LABELS = ',start)
                updated = updated[:start]+'CONTROL_TARGETS = []'+updated[end:]
        ast.parse(updated)
        (harness/name).write_text(updated)
        (harness/(name+'.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),fromfile=str(prior/name),tofile=str(harness/name))))
    scope = 'Nineteen pure validation/storage-fixture controls; no SQLite or child process.' if number == 17 else 'Unchanged inherited '+str(len(selection))+' methods with expanded source identity.'
    (harness/'SCOPE.md').write_text('# Exact scope\n\n'+scope+'\n\n[Design](../DESIGN.md), [targets](targets.json). Original execution, SQL, retention and effect ceilings remain.\n')
    (harness/'README.md').write_text('# Document validation checks\n\n[Scope](SCOPE.md), [targets](targets.json), [source](../implementation01/README.md).\n')
    review = read(prior/'review.json')
    review.update(scope=scope,tests=len(selection),sourceIndexSha256=pin,targetSha256=sha(harness/'targets.json'),reviewed=reviewed,inheritedHarnessIndexSha256=sha(prior/'index.json'))
    if number == 17:
        review.update(controlTargets=[],sqliteConnectionsMaximum=0)
    write(harness/'review.json',review)
    write(harness/'index.json',dict(scope=scope,files=inventory(harness)))
    print(json.dumps(dict(harness=harness.name,tests=len(selection),indexSha256=sha(harness/'index.json'))))
print(json.dumps(dict(projectFiles=248,frozenFiles=251,sourceIndexSha256=pin)))
