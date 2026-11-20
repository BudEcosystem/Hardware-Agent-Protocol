"""Freeze exact page encoding and original bounded pure/cutoff/group harnesses."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path.cwd()
B = ROOT / 'artifacts/implementation/pat-io-page-encoding'
OLD = ROOT / 'artifacts/implementation/pat-io-group-history'
S = B / 'implementation01'

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
assert sha(OLD / 'implementation04/index.json') == baseline['sourceIndexSha256'] == 'ad22248967c7a163ccd108d13210331399e15ffb9e166541a80694dce649547c'
assert len(baseline['inheritedProjectInputs']) == 225 and len(baseline['excludedRetainedOnlyInputs']) == 3973
changed, patches = [], []
for row in baseline['inheritedProjectInputs'] + baseline['excludedRetainedOnlyInputs']:
    p = ROOT / row['path']
    assert sha(p) == row['sha256'] and p.stat().st_size == row['bytes']
    rel = p.relative_to(OLD / 'implementation04/project'); q = S / 'project' / rel
    if row in baseline['excludedRetainedOnlyInputs']:
        assert not q.exists()
        continue
    if sha(q) != row['sha256']:
        changed.append(rel.as_posix())
        patches.extend(difflib.unified_diff(p.read_text().splitlines(True), q.read_text().splitlines(True),
            fromfile=p.relative_to(ROOT).as_posix(), tofile=q.relative_to(ROOT).as_posix()))
assert sorted(changed) == ['hms/pat_io_configuration_capture.py', 'hms/pat_io_trials.py']
(B / 'implementation.patch').write_text(''.join(patches))
reviewed = [
    'All current production inputs and current-group tests preserved. Historical data-only fixture and its dedicated retrospective test excluded explicitly; their immutable source pins remain. No claim that those files caused earlier deadline failures.',
    'Two writer modules select an exact table-page encoding memo only for reusable table_page records. Every SQL query, lock, shape/count/size/type/canonical-blob check and page construction is unchanged.',
    'Memo keys include every page field, record profile, cell tag and exact scalar type/value. Immutable tuple keys retain no caller containers. Unsupported shapes retain original canonicalization and errors. Bounded 128 entries/1MiB encoded bytes; eviction only recomputes.',
    'Base check-before-encoding, configured combined-reserve-before-check, sidecar check-before-encoding, original record caches, charge, exclusive creation, flush/fsync and reference publication order unchanged. Encoded-cache success does not claim write success.',
    'Ten focused methods exercise exact bytes/digests, mutation, metadata/type distinctions, invalid inputs, entry/byte eviction, both evidence streams, original budget precedence and failed writes. Fake closed query fixtures prove repeated live-read and cell-validation paths; full original GPIO/PWM tests remain the actual SQLite validation.',
    'All 107 prior selected pure methods remain, plus ten new methods. The original actual record-cutoff and complete GPIO/PWM history methods retain their bodies and limits. No physical/MCU, inference, acquired-controller, live-service or adjacent-Harness execution.',
]
write(S / 'source-review.json', dict(scope='Primary-agent complete production delta and tests reviewed before execution.',
    changedFiles=changed, newFiles=['hms/pat_io_page_encoding.py', 'tests/test_pat_io_page_encoding.py'],
    unchangedInheritedFiles=223, excludedRetainedOnlyFiles=3973, reviewed=reviewed,
    independentReview=False, releasedBy='primary-agent', projectExecutionDuringPreparation=False))
(S / 'README.md').write_text('# Bounded exact table-page encoding\n\n[Design](../DESIGN.md), [source review](source-review.json).\nCurrent SQL checks and all execution/evidence ceilings remain unchanged.\n')
rows = inventory(S, True); assert len(rows) == 230
write(S / 'index.json', dict(scope='Frozen exact page encoding candidate with lean current-worker inputs.', files=rows))
pin = sha(S / 'index.json')
tree = ast.parse((S / 'project/tests/test_pat_io_page_encoding.py').read_bytes())
body = next(n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PageEncodingTests')
new = sorted('test_pat_io_page_encoding.PageEncodingTests.' + n.name for n in body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_'))
assert len(new) == 10
origins = [OLD / 'harness11', ROOT / 'artifacts/implementation/pat-io-encoding/harness02', OLD / 'harness13', OLD / 'harness14']
for i, old in enumerate(origins, 1):
    for row in read(old / 'index.json')['files']:
        assert sha(old / row['path']) == row['sha256'] and (old / row['path']).stat().st_size == row['bytes']
    prior = read(old / 'targets.json'); targets = prior['targets'] + (new if i == 1 else [])
    h = B / ('harness%02d' % i); h.mkdir(); (h / 'references').mkdir()
    borrowed = []
    for name in ('run_attempt.py', 'attempt_child.py', 'references/approved-external-roots.json'):
        p = old / name; q = h / 'references' / p.name; shutil.copyfile(p, q)
        borrowed.append(dict(source=p.relative_to(ROOT).as_posix(), copy=q.relative_to(h).as_posix(), bytes=p.stat().st_size, sha256=sha(p)))
    write(h / 'borrowed-inputs.json', borrowed)
    write(h / 'targets.json', dict(testCount=len(targets), targets=targets))
    for name in ('run_attempt.py', 'attempt_child.py'):
        before = (old / name).read_text()
        after = before.replace(read(old / 'review.json')['sourceIndexSha256'], pin)
        after = after.replace(old.parent.name, B.name).replace('hms-io-group-history-', 'hms-io-page-encoding-').replace('hms-io-encoding-', 'hms-io-page-encoding-')
        after = after.replace('implementation04', 'implementation01')
        source_count, frozen_count = (222, 225) if i == 2 else (4198, 4201)
        after = re.sub(r'\b' + str(frozen_count) + r'\b', '230', after)
        after = re.sub(r'\b' + str(source_count) + r'\b', '227', after)
        if i == 1:
            if name == 'run_attempt.py':
                assert after.count(repr(prior['targets'])) == 1
                after = after.replace(repr(prior['targets']), repr(targets))
            after = re.sub(r'\b107\b', '117', after).replace('IoGroupHistory107', 'IoPageEncoding117').replace('history107', 'page117')
        ast.parse(after)
        if name == 'run_attempt.py': assert "stage = here.parent / 'implementation01'" in after
        (h / name).write_text(after)
        (h / (name + '.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
            fromfile=(old / name).relative_to(ROOT).as_posix(), tofile=(h / name).relative_to(ROOT).as_posix())))
    shutil.copyfile(old / 'SCOPE.md', h / 'SCOPE.md')
    (h / 'README.md').write_text('# Original bounded page-encoding validation\n\n[Targets](targets.json), [scope](SCOPE.md), [source](../implementation01/README.md).\n')
    write(h / 'review.json', dict(scope='Exact source/count/selection harness changes reviewed before execution.', tests=len(targets),
        sourceIndexSha256=pin, targetSha256=sha(h / 'targets.json'), reviewed=reviewed + [
            'Launcher/child retain original 180s parent, 60s capture, 16MiB scratch, 8192-file, input/document/log bounds and exact target SQL path scopes. Pure methods create no SQLite connections.'],
        independentReview=False, releasedBy='primary-agent'))
    parsed = ast.parse((h / 'run_attempt.py').read_bytes())
    lists = [ast.literal_eval(n) for n in ast.walk(parsed) if isinstance(n, ast.List) and n.elts and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in n.elts)]
    assert targets in lists
    write(h / 'index.json', dict(scope='Frozen original bounded page encoding validation harness.', files=inventory(h)))
    print(json.dumps(dict(harness=h.name, tests=len(targets), indexSha256=sha(h / 'index.json'))))
for name in ('acquire.py', 'audit-states.py', 'audit-storage.py'):
    before = (OLD / name).read_text(); after = before.replace(OLD.name, B.name)
    if name == 'acquire.py':
        after = after.replace("A/'project',225", "A/'project',227").replace('ROOT,228', 'ROOT,230')
        after = after.replace('sourceFilesVerified=225,frozenFilesVerified=228', 'sourceFilesVerified=227,frozenFilesVerified=230')
        targets = read(B / 'harness02/targets.json')['targets']
        anchor = "'test_pat_io_group_history.IoGroupHistoryTests.test_complete_pwm_history']"
        assert after.count(anchor) == 1
        after = after.replace(anchor, anchor[:-1] + ', ' + repr(targets[0]) + ']')
    ast.parse(after); (B / name).write_text(after)
    (B / (name + '.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile=(OLD / name).relative_to(ROOT).as_posix(), tofile=(B / name).relative_to(ROOT).as_posix())))
print(json.dumps(dict(projectFiles=227, frozenFiles=230, sourceIndexSha256=pin)))
