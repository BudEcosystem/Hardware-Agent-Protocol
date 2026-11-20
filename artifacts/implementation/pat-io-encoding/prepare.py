"""Freeze reviewed encoding changes and original bounded execution harnesses."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path.cwd()
B = ROOT / 'artifacts/implementation/pat-io-encoding'
OLD = ROOT / 'artifacts/implementation/pat-io-group-efficiency'
S = B / 'implementation01'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, value):
    with p.open('x') as f: f.write(json.dumps(value, indent=2) + '\n')
def inventory(folder, rooted=False):
    rows = []
    for p in sorted(folder.rglob('*')):
        assert not p.is_symlink()
        if p.is_file():
            if p.suffix == '.py': ast.parse(p.read_bytes())
            rows.append(dict(path=p.relative_to(ROOT if rooted else folder).as_posix(), bytes=p.stat().st_size, sha256=sha(p)))
    return rows

baseline = read(S / 'baseline-inputs.json')
assert sha(OLD / 'implementation01/index.json') == baseline['sourceIndexSha256']
assert len(baseline['inheritedProjectInputs']) == 221
changed, patches = [], []
for row in baseline['inheritedProjectInputs']:
    p = ROOT / row['path']
    assert sha(p) == row['sha256'] and p.stat().st_size == row['bytes']
    relative = p.relative_to(OLD / 'implementation01/project')
    q = S / 'project' / relative
    if sha(p) != sha(q):
        changed.append(relative.as_posix())
        patches.extend(difflib.unified_diff(p.read_text().splitlines(True), q.read_text().splitlines(True),
            fromfile=p.relative_to(ROOT).as_posix(), tofile=q.relative_to(ROOT).as_posix()))
assert sorted(changed) == ['hms/pat_io_configuration_capture.py', 'hms/pat_io_trials.py', 'hms/resource_topology.py']
(B / 'implementation.patch').write_text(''.join(patches))
reviewed = [
    'Base and configured writers call the same private byte writer after their original budget check. Configured combined reservation still precedes the wall/group check. Exact envelope profile, hash, reference, reuse, charges, exclusive create, flush and fsync remain unchanged.',
    'Topology bytes carriers still parse, reject unsupported scalar types, then canonicalize. Object carriers retain original canonical bound, strict original tree, detached parse and strict parsed tree; reuse the original canonical bytes. Every schema memo and semantic check remains.',
    'Nine focused tests check byte identity, detached references, inherited profile, both streams, single encoding, budget precedence, group check on cache hit, failed exclusive create, failed fsync and changed input. Original 87 pure tests and three actual cutoff/GPIO/PWM methods unchanged.',
    'No table-page memo, authority cache, schema change, SQL scope expansion, timing/storage/effect ceiling change or durability relaxation. Live source and all prior retained evidence untouched.',
]
write(S / 'source-review.json', dict(scope='Primary-agent complete source and tests reviewed before execution.',
    changedFiles=changed, newFiles=['tests/test_pat_io_encoding.py'], unchangedInheritedFiles=218,
    reviewed=reviewed, independentReview=False, releasedBy='primary-agent', projectExecutionDuringPreparation=False))
(S / 'README.md').write_text('# Single encoding of bounded evidence\n\nSee [design](../DESIGN.md) and [review](source-review.json).\nOriginal group limits and validation remain. Complete capture is not qualification.\n')
rows = inventory(S, rooted=True)
assert len(rows) == 225
write(S / 'index.json', dict(scope='Frozen three-file production encoding change and nine focused tests.', files=rows))
pin = sha(S / 'index.json')
tree = ast.parse((S / 'project/tests/test_pat_io_encoding.py').read_bytes())
body = next(n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'IoEncodingTests')
new_tests = sorted('test_pat_io_encoding.IoEncodingTests.' + n.name for n in body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_'))
assert len(new_tests) == 9
for i, origin in enumerate((1, 3, 4, 5), 1):
    old = OLD / ('harness%02d' % origin)
    h = B / ('harness%02d' % i)
    h.mkdir(); (h / 'references').mkdir()
    for row in read(old / 'index.json')['files']:
        assert sha(old / row['path']) == row['sha256'] and (old / row['path']).stat().st_size == row['bytes']
    borrowed = []
    for name in ('run_attempt.py', 'attempt_child.py', 'references/approved-external-roots.json'):
        p = old / name; q = h / 'references' / p.name
        shutil.copyfile(p, q)
        borrowed.append(dict(source=p.relative_to(ROOT).as_posix(), copy=q.relative_to(h).as_posix(), bytes=p.stat().st_size, sha256=sha(p)))
    write(h / 'borrowed-inputs.json', borrowed)
    prior = read(old / 'targets.json')
    targets = prior['targets'] + (new_tests if i == 1 else [])
    write(h / 'targets.json', dict(testCount=len(targets), targets=targets))
    for name in ('run_attempt.py', 'attempt_child.py'):
        before = (old / name).read_text()
        after = before.replace(baseline['sourceIndexSha256'], pin).replace('pat-io-group-efficiency', 'pat-io-encoding').replace('hms-io-group-efficiency-', 'hms-io-encoding-')
        after = re.sub(r'\b224\b', '225', after)
        after = re.sub(r'\b221\b', '222', after)
        if i == 1:
            after = re.sub(r'\b87\b', '96', after).replace('GroupEfficiency87', 'IoEncoding96').replace('efficiency87', 'encoding96')
        ast.parse(after)
        (h / name).write_text(after)
        (h / (name + '.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
            fromfile=(old / name).relative_to(ROOT).as_posix(), tofile=(h / name).relative_to(ROOT).as_posix())))
    shutil.copyfile(old / 'SCOPE.md', h / 'SCOPE.md')
    (h / 'README.md').write_text('# Bounded encoding validation\n\n[Targets](targets.json), [scope](SCOPE.md), [source](../implementation01/README.md).\n')
    write(h / 'review.json', dict(scope='Complete source and launcher deltas reviewed before execution.', tests=len(targets),
        sourceIndexSha256=pin, targetSha256=sha(h / 'targets.json'), reviewed=reviewed + [
            'Harness changes only source/count/prefix pins and pure selection from 87 to 96. Original three actual SQL paths and 180s/16MiB scratch limits unchanged.'],
        independentReview=False, releasedBy='primary-agent'))
    write(h / 'index.json', dict(scope='Frozen reviewed original bounded harness.', files=inventory(h)))
    print(json.dumps(dict(harness=h.name, tests=len(targets), indexSha256=sha(h / 'index.json'))))
for name in ('acquire.py', 'audit-states.py', 'audit-storage.py'):
    before = (OLD / name).read_text()
    after = before.replace('pat-io-group-efficiency', 'pat-io-encoding')
    if name == 'acquire.py':
        after = after.replace("A/'project',221", "A/'project',222").replace('ROOT,224', 'ROOT,225')
        after = after.replace('sourceFilesVerified=221,frozenFilesVerified=224', 'sourceFilesVerified=222,frozenFilesVerified=225')
    ast.parse(after); (B / name).write_text(after)
    (B / (name + '.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile=(OLD / name).relative_to(ROOT).as_posix(), tofile=(B / name).relative_to(ROOT).as_posix())))
print(json.dumps(dict(projectFiles=222, frozenFiles=225, sourceIndexSha256=pin)))
