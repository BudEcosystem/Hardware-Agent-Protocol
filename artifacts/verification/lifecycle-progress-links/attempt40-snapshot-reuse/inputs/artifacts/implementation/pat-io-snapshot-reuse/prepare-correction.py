"""Correct the new graph-check assertion; preserve all production and failure bytes."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-snapshot-reuse'
O = B / 'implementation01'; S = B / 'implementation02'
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
assert sha(O / 'index.json') == '121d71b66df982c9c0a530a56f5cea200b67339284fadd152e2e399e5aae58e3'
proof = read(B / 'results/attempt01-failed129/proof.json')
assert proof['counts']['testsRun'] == 129 and proof['counts']['failures'] == 1 and proof['counts']['errors'] == 0
assert proof['sqliteConnections'] == 0 and read(B / 'results/attempt01-failed129/attempt/result.json')['childState'] == 'exited'
(S / 'project').mkdir(parents=True)
baseline = []
for row in read(O / 'index.json')['files']:
    p = ROOT / row['path']; assert sha(p) == row['sha256'] and p.stat().st_size == row['bytes']
    if p.is_relative_to(O / 'project'):
        q = S / 'project' / p.relative_to(O / 'project'); q.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, q); baseline.append(row)
assert len(baseline) == 228
write(S / 'baseline-inputs.json', dict(sourceIndexSha256=sha(O / 'index.json'), inheritedProjectInputs=baseline))
p = S / 'project/tests/test_pat_io_snapshot_reuse.py'; before = p.read_text()
anchor = '            self.assertEqual(dag.call_count, 2)\n'
replacement = '''            self.assertEqual([call.args[1] for call in dag.call_args_list],
                ['RESOURCE_CONTAINMENT_CYCLE', 'RESOURCE_DEPENDENCY_CYCLE', 'RESOURCE_ALIAS_CYCLE'])
'''
assert before.count(anchor) == 1; after = before.replace(anchor, replacement); ast.parse(after); p.write_text(after)
(B / 'test-correction.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
    fromfile=(O / 'project/tests/test_pat_io_snapshot_reuse.py').relative_to(ROOT).as_posix(), tofile=p.relative_to(ROOT).as_posix())))
changed = []
for row in baseline:
    old = ROOT / row['path']; rel = old.relative_to(O / 'project')
    if sha(S / 'project' / rel) != row['sha256']: changed.append(rel.as_posix())
assert changed == ['tests/test_pat_io_snapshot_reuse.py']
reviewed = [
    'The failed pure129 run has128passes and one assertion failure: the new test expected two _dag calls, but unchanged _alias_closures also checks RESOURCE_ALIAS_CYCLE. Original source has exactly three call sites; no production defect is inferred from that mismatch.',
    'Replace only the new count assertion with the exact ordered containment/dependency/alias refusal-code inventory. Warm-parser veto and output equality stay, and the subsequent repeated dependency-cycle refusal assertions are now reachable.',
    'Every production file and227of228 inherited project files remain unchanged. Preserve the complete failed attempt and original scratch. Fresh pure129 and original cutoff/GPIO/PWM pipelines remain required; no limit or mutation rule changes.',
]
write(S / 'source-review.json', dict(scope='Primary-agent test-only correction reviewed before execution.', changedFiles=changed,
    unchangedInheritedFiles=227, productionUnchanged=True, reviewed=reviewed, independentReview=False, releasedBy='primary-agent', projectExecutionDuringPreparation=False))
(S / 'README.md').write_text('# Require all three unchanged graph checks\n\nProduction matches source01. [Correction](../CORRECTION.md), [review](source-review.json).\n')
rows = inventory(S, True); assert len(rows) == 231
write(S / 'index.json', dict(scope='Only corrected graph-check expectation; production unchanged from source01.', files=rows)); pin = sha(S / 'index.json')
for i, origin in enumerate(range(1, 5), 5):
    old = B / ('harness%02d' % origin); h = B / ('harness%02d' % i); h.mkdir(); (h / 'references').mkdir()
    for row in read(old / 'index.json')['files']: assert sha(old / row['path']) == row['sha256']
    borrowed = []
    for name in ('run_attempt.py', 'attempt_child.py', 'references/approved-external-roots.json'):
        a = old / name; q = h / 'references' / a.name; shutil.copyfile(a, q)
        borrowed.append(dict(source=a.relative_to(ROOT).as_posix(), copy=q.relative_to(h).as_posix(), bytes=a.stat().st_size, sha256=sha(a)))
    write(h / 'borrowed-inputs.json', borrowed)
    for name in ('attempt_child.py', 'targets.json', 'SCOPE.md', 'README.md'): shutil.copyfile(old / name, h / name)
    before = (old / 'run_attempt.py').read_text(); after = before.replace(sha(O / 'index.json'), pin).replace('implementation01', 'implementation02')
    ast.parse(after); assert "stage = here.parent / 'implementation02'" in after
    (h / 'run_attempt.py').write_text(after)
    (h / 'run_attempt.py.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile=(old / 'run_attempt.py').relative_to(ROOT).as_posix(), tofile=(h / 'run_attempt.py').relative_to(ROOT).as_posix())))
    # This descriptive link also points to the exact corrected source.
    (h / 'README.md').write_text((h / 'README.md').read_text().replace('implementation01', 'implementation02'))
    review = read(old / 'review.json'); review.update(sourceIndexSha256=pin, scope='Source02 test-only correction with exact original selection and limits.')
    review['reviewed'] += reviewed; write(h / 'review.json', review)
    write(h / 'index.json', dict(scope='Original bounded pipeline on test-corrected source02.', files=inventory(h)))
    print(json.dumps(dict(harness=h.name, indexSha256=sha(h / 'index.json'))))
print(json.dumps(dict(sourceIndexSha256=pin, projectFiles=228, frozenFiles=231)))
