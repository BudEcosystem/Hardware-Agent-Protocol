"""Freeze bounded pure snapshot reuse and original complete-group harnesses."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-snapshot-reuse'
OLD = ROOT / 'artifacts/implementation/pat-io-page-encoding'; S = B / 'implementation01'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, v):
    with p.open('x') as f: f.write(json.dumps(v, indent=2) + '\n')
def inventory(folder, rooted=False):
    rows = []
    for p in sorted(folder.rglob('*')):
        assert not p.is_symlink()
        if p.is_file():
            if p.suffix == '.py': ast.parse(p.read_bytes())
            rows.append(dict(path=p.relative_to(ROOT if rooted else folder).as_posix(), bytes=p.stat().st_size, sha256=sha(p)))
    return rows
baseline = read(S / 'baseline-inputs.json')
assert sha(OLD / 'implementation01/index.json') == baseline['sourceIndexSha256'] == 'ac3e2b660efa78ca9db68b3d0d7ff0cf90a8a38fe8693c982c9d0a077b9301b0'
assert len(baseline['inheritedProjectInputs']) == 227
changed, patches = [], []
for row in baseline['inheritedProjectInputs']:
    p = ROOT / row['path']; assert sha(p) == row['sha256'] and p.stat().st_size == row['bytes']
    rel = p.relative_to(OLD / 'implementation01/project'); q = S / 'project' / rel
    if sha(q) != row['sha256']:
        changed.append(rel.as_posix())
        patches.extend(difflib.unified_diff(p.read_text().splitlines(True), q.read_text().splitlines(True),
            fromfile=p.relative_to(ROOT).as_posix(), tofile=q.relative_to(ROOT).as_posix()))
assert sorted(changed) == ['hms/resource_topology.py', 'hms/synthetic_io_installation.py', 'tests/test_pat_io_encoding.py']
(B / 'implementation.patch').write_text(''.join(patches))
invariants = []
for name, methods in [('resource_topology.py', ['_strict_tree', 'parse_topology', 'parse_generations', '_generations', 'binding_proof', 'topology_digest']),
        ('synthetic_io_installation.py', ['implementation_digest', 'definitions', 'handler_details'])]:
    a = ast.parse((OLD / 'implementation01/project/hms' / name).read_bytes())
    b = ast.parse((S / 'project/hms' / name).read_bytes())
    for method in methods:
        x = next(n for n in ast.walk(a) if isinstance(n, ast.FunctionDef) and n.name == method)
        y = next(n for n in ast.walk(b) if isinstance(n, ast.FunctionDef) and n.name == method)
        encoded = ast.dump(x, include_attributes=False); assert encoded == ast.dump(y, include_attributes=False)
        invariants.append(dict(file=name, method=method, unchanged=True, astSha256=hashlib.sha256(encoded.encode()).hexdigest()))
reviewed = [
    'Only resource snapshot handling and duplicate installation encoding change in production. All current SQL/authority, capture, writer, budget, effect and full independent-reader modules remain byte-identical.',
    'The existing eight-entry schema cache retains immutable frozen built-in trees with exact canonical byte keys and validator identity. Canonical byte hits bypass repeated parse/encode only for a previously accepted carrier; oversized/noncanonical/changed inputs retain original bounded validation. Object inputs canonicalize and reject original unsupported scalar types before lookup.',
    'Every hit reconstructs detached built-in dictionaries/lists without deepcopy or caller hooks. Cache keys retain at most512KiB of document bytes plus bounded frozen trees; no total-RSS quota claim. Eviction recomputes; changed validator identities cannot inherit success, and a validator replaced during validation cannot publish the snapshot.',
    'All graph, footprint, generation and binding semantic functions are unchanged and run after snapshot retrieval. No mutable authority or generation outcome is cached. Installation normalization preserves the first encoded bytes after its original float scan and still checks current implementation_digest on each call.',
    'Twelve focused tests cover warm bytes, object guards, noncanonical input, oversized lookup refusal, validator replacement/race, immutable bounded entries, repeated graph/generation checks, exact detached normalization and changed source/float refusals.',
    'All 117 prior pure checks are selected; one topology encoding test is renamed and its warm canonical-byte encoding count changes from1to0, with exact output/detachment assertions unchanged. Twelve new methods bring selection to129. Original actual record-cutoff and full GPIO/PWM history methods remain unchanged.',
    'No capture/parent deadline, required challenge, protocol, effect, record, byte or other ceiling is widened. No physical/MCU, inference, acquired-controller, live HMS or adjacent Harness execution.',
]
write(S / 'source-review.json', dict(scope='Primary-agent complete snapshot/normalization/test delta reviewed before execution.',
    changedFiles=changed, newFiles=['tests/test_pat_io_snapshot_reuse.py'], unchangedInheritedFiles=224,
    reviewed=reviewed, independentReview=False, releasedBy='primary-agent', projectExecutionDuringPreparation=False))
(S / 'README.md').write_text('# Reuse exact validated pure snapshots\n\n[Design](../DESIGN.md), [source review](source-review.json).\nGraph/generation/source checks remain; no current qualification claim.\n')
rows = inventory(S, True); assert len(rows) == 231
write(S / 'index.json', dict(scope='Frozen pure snapshot reuse, duplicate-normalization encoding removal and focused tests.', files=rows))
pin = sha(S / 'index.json')
write(B / 'source-invariant-review.json', dict(scope='Exact unchanged graph/generation/binding/source semantic method ASTs.', sourceIndexSha256=pin, methods=invariants))
tree = ast.parse((S / 'project/tests/test_pat_io_snapshot_reuse.py').read_bytes())
body = next(n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SnapshotReuseTests')
new = sorted('test_pat_io_snapshot_reuse.SnapshotReuseTests.' + n.name for n in body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_'))
assert len(new) == 12
old_method = 'test_pat_io_encoding.IoEncodingTests.test_topology_snapshot_encodes_once_for_objects_and_bytes_and_detaches'
new_method = 'test_pat_io_encoding.IoEncodingTests.test_topology_snapshot_encodes_objects_and_reuses_warm_bytes_and_detaches'
for i in range(1, 5):
    old = OLD / ('harness%02d' % i)
    for row in read(old / 'index.json')['files']:
        assert sha(old / row['path']) == row['sha256'] and (old / row['path']).stat().st_size == row['bytes']
    prior = read(old / 'targets.json')
    targets = [(new_method if x == old_method else x) for x in prior['targets']] + (new if i == 1 else [])
    if i == 1: assert prior['targets'].count(old_method) == 1 and len(targets) == 129
    h = B / ('harness%02d' % i); h.mkdir(); (h / 'references').mkdir()
    borrowed = []
    for name in ('run_attempt.py', 'attempt_child.py', 'references/approved-external-roots.json'):
        p = old / name; q = h / 'references' / p.name; shutil.copyfile(p, q)
        borrowed.append(dict(source=p.relative_to(ROOT).as_posix(), copy=q.relative_to(h).as_posix(), bytes=p.stat().st_size, sha256=sha(p)))
    write(h / 'borrowed-inputs.json', borrowed); write(h / 'targets.json', dict(testCount=len(targets), targets=targets))
    for name in ('run_attempt.py', 'attempt_child.py'):
        before = (old / name).read_text()
        after = before.replace(baseline['sourceIndexSha256'], pin).replace(OLD.name, B.name).replace('hms-io-page-encoding-', 'hms-io-snapshot-reuse-')
        after = re.sub(r'\b230\b', '231', after); after = re.sub(r'\b227\b', '228', after)
        if i == 1:
            if name == 'run_attempt.py':
                assert after.count(repr(prior['targets'])) == 1; after = after.replace(repr(prior['targets']), repr(targets))
            after = re.sub(r'\b117\b', '129', after).replace('IoPageEncoding117', 'IoSnapshotReuse129').replace('page117', 'snapshot129')
        ast.parse(after)
        if name == 'run_attempt.py': assert "stage = here.parent / 'implementation01'" in after
        (h / name).write_text(after)
        (h / (name + '.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
            fromfile=(old / name).relative_to(ROOT).as_posix(), tofile=(h / name).relative_to(ROOT).as_posix())))
    shutil.copyfile(old / 'SCOPE.md', h / 'SCOPE.md')
    (h / 'README.md').write_text('# Original bounded snapshot-reuse checks\n\n[Targets](targets.json), [scope](SCOPE.md), [source](../implementation01/README.md).\n')
    write(h / 'review.json', dict(scope='Exact source/count/selection harness changes reviewed before execution.', tests=len(targets), sourceIndexSha256=pin,
        targetSha256=sha(h / 'targets.json'), reviewed=reviewed + ['Original180s parent/60s capture/16MiB scratch and every original input/file/JSON/log ceiling remain. SQL scope remains exact named synthetic group targets and their original paths.'], independentReview=False, releasedBy='primary-agent'))
    parsed = ast.parse((h / 'run_attempt.py').read_bytes())
    lists = [ast.literal_eval(n) for n in ast.walk(parsed) if isinstance(n, ast.List) and n.elts and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in n.elts)]
    assert targets in lists
    write(h / 'index.json', dict(scope='Frozen original bounded snapshot-reuse validation harness.', files=inventory(h)))
    print(json.dumps(dict(harness=h.name, tests=len(targets), indexSha256=sha(h / 'index.json'))))
for name in ('acquire.py', 'audit-states.py', 'audit-storage.py'):
    before = (OLD / name).read_text(); after = before.replace(OLD.name, B.name)
    if name == 'acquire.py':
        after = after.replace("A/'project',227", "A/'project',228").replace('ROOT,230', 'ROOT,231')
        after = after.replace('sourceFilesVerified=227,frozenFilesVerified=230', 'sourceFilesVerified=228,frozenFilesVerified=231')
    ast.parse(after); (B / name).write_text(after)
    (B / (name + '.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile=(OLD / name).relative_to(ROOT).as_posix(), tofile=(B / name).relative_to(ROOT).as_posix())))
print(json.dumps(dict(projectFiles=228, frozenFiles=231, sourceIndexSha256=pin)))
