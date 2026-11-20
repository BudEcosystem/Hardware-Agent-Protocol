"""Freeze the reviewed pure normalization delta and unchanged recovery scopes."""
import ast
import difflib
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path.cwd()
B = ROOT / 'artifacts/implementation/pat-io-installation-reuse'
O = ROOT / 'artifacts/implementation/pat-io-supervision-recovery'
S = B / 'implementation01'
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

base = read(S / 'baseline-inputs.json')
assert sha(O / 'implementation01/index.json') == base['sourceIndexSha256'] == 'd1c5ac0d86c77bd195ffebfcf75dc6e1c95ecf7a0814416073cfba691fb5685c'
for row in read(O / 'implementation01/index.json')['files']:
    assert sha(ROOT / row['path']) == row['sha256']
assert len(base['inheritedProjectInputs']) == 239
changed = []
for row in base['inheritedProjectInputs']:
    relative = (ROOT / row['path']).relative_to(O / 'implementation01/project')
    if sha(S / 'project' / relative) != row['sha256']: changed.append(relative.as_posix())
assert changed == ['hms/synthetic_io_installation.py']
before = (O / 'implementation01/project' / changed[0]).read_text()
after = (S / 'project' / changed[0]).read_text()
old = next(node for node in ast.parse(before).body if isinstance(node, ast.FunctionDef) and node.name == 'normalize_installation')
new = next(node for node in ast.parse(after).body if isinstance(node, ast.FunctionDef) and node.name == '_normalize_validated')
start = next(i for i, node in enumerate(old.body) if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'document')
assert [ast.dump(node) for node in old.body[start:]] == [ast.dump(node) for node in new.body]
(B / 'normalization-reuse.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='recovery/' + changed[0], tofile='reuse/' + changed[0])))
test_module = 'test_pat_io_installation_reuse'
tree = ast.parse((S / 'project/tests' / (test_module + '.py')).read_bytes())
cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'InstallationReuseTests')
added = sorted(test_module + '.' + cls.name + '.' + node.name for node in cls.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'))
assert len(added) == 14 and len(inventory(S / 'project')) == 240
reviewed = [
    'One production file changes; 238 inherited files, all supervisor/worker and original test bytes remain unchanged. One new module adds14 pure tests. All Python AST parsed without project execution; original semantic body AST identical.',
    'Original bounded input/type/float/closed-profile/source checks run before lookup. Driver digest recomputed each call. Eight exact byte keys at most512KiB, bounded immutable normalized trees, fresh detached result per hit. No durable state or live authority cached.',
    'Selected trusted helper/code/default/closure, constants, validator object/schema/type/format/iteration/keyword guards checked before lookup and publication. Private in-place mutation retains original fallback semantics; no full process attestation claim.',
    'Pure memo invalidation never resets durable evidence. No semantic, effect, protocol, source scan, tree scan, durability, deadline or storage ceiling changed. No new launch/SQL allowance; test-only profiling observes original functions.',
    'Control185 is exact inherited171 plus14 pure tests. Nine process selections unchanged, each180s outer and original60s owned deadline. Existing SQL path/count, code-image launch, owner/writer lease and raw retention checks unchanged.',
    'Primary-agent review only. No diagnostic signal interception, physical/MCU/emulator/acquired-controller/inference/live-service/adjacent-Harness execution. Raw failures and logical keys remain immutable.'
]
write(S / 'source-review.json', dict(scope='Pure installation normalization memo', changedFiles=changed, unchangedInheritedFiles=238, newProjectFiles=1, reviewed=reviewed, independentReview=False, releasedBy='primary-agent', projectExecutionDuringPreparation=False))
(S / 'README.md').write_text('# Installation normalization reuse\n\n[Design](../DESIGN.md), [source review](source-review.json). One production delta; unchanged uninstrumented supervisor.\n')
rows = inventory(S, True); assert len(rows) == 243
write(S / 'index.json', dict(scope='Frozen bounded pure installation reuse and14 new tests.', files=rows))
pin = sha(S / 'index.json')
for number in range(1, 11):
    prior = O / ('harness%02d' % number)
    for row in read(prior / 'index.json')['files']:
        assert sha(prior / row['path']) == row['sha256']
    H = B / prior.name; H.mkdir(); (H / 'references').mkdir()
    old_targets = read(prior / 'targets.json')['targets']
    targets = old_targets + added if number == 1 else old_targets
    count = len(targets); assert count == (185 if number == 1 else 1)
    borrowed = []
    for name in ('run_attempt.py', 'attempt_child.py', 'references/approved-external-roots.json'):
        source = prior / name; dest = H / 'references' / source.name
        shutil.copyfile(source, dest)
        borrowed.append(dict(source=source.relative_to(ROOT).as_posix(), copy=dest.relative_to(H).as_posix(), bytes=source.stat().st_size, sha256=sha(source)))
    write(H / 'borrowed-inputs.json', borrowed)
    write(H / 'targets.json', dict(testCount=count, targets=targets))
    for name in ('run_attempt.py', 'attempt_child.py'):
        original = (prior / name).read_text()
        updated = original.replace(base['sourceIndexSha256'], pin).replace(O.name, B.name)
        updated = re.sub(r'\b242\b', '243', updated)
        updated = re.sub(r'\b239\b', '240', updated)
        if number == 1:
            updated = re.sub(r'\b171\b', '185', updated)
            if name == 'run_attempt.py':
                assert updated.count(repr(old_targets)) == 1
                updated = updated.replace(repr(old_targets), repr(targets))
        updated = updated.replace('recovery171', 'installation185').replace('Recovery171', 'Installation185').replace('recovery1', 'installation1').replace('Recovery1', 'Installation1')
        ast.parse(updated); (H / name).write_text(updated)
        (H / (name + '.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True), fromfile=str((prior / name).relative_to(ROOT)), tofile=str((H / name).relative_to(ROOT)))))
    scope = 'Control185: unchanged171 plus14 pure normalization tests.' if number == 1 else 'Unchanged original single process recovery selection.'
    (H / 'SCOPE.md').write_text('# Exact execution scope\n\n' + scope + '\n\n[Design](../DESIGN.md), [exact targets](targets.json). Original SQL/launch/retention/deadline bounds.\n')
    (H / 'README.md').write_text('# Installation reuse checks\n\n[Scope](SCOPE.md), [targets](targets.json), [source](../implementation01/README.md).\n')
    review = read(prior / 'review.json')
    review.update(scope=scope, tests=count, sourceIndexSha256=pin, targetSha256=sha(H / 'targets.json'), reviewed=reviewed, inheritedHarnessIndexSha256=sha(prior / 'index.json'))
    write(H / 'review.json', review)
    write(H / 'index.json', dict(scope=scope, files=inventory(H)))
    print(json.dumps(dict(harness=H.name, tests=count, indexSha256=sha(H / 'index.json'))))
print(json.dumps(dict(projectFiles=240, frozenFiles=243, sourceIndexSha256=pin)))
