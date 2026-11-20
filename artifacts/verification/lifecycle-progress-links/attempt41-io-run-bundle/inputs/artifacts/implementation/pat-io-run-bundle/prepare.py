"""Freeze an additive input-bundle component and exact pure selection."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-run-bundle'
OLD = ROOT / 'artifacts/implementation/pat-io-snapshot-reuse'
S = B / 'implementation01'; O = OLD / 'implementation02'; PRIOR = OLD / 'harness05'
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
assert sha(O / 'index.json') == baseline['sourceIndexSha256'] == '994feaf97781c64c8bc4b236bf426a7b29ff051eac798616d07bc0128d6ea306'
assert len(baseline['inheritedProjectInputs']) == 228
for row in read(O / 'index.json')['files']:
    p = ROOT / row['path']; assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
for row in baseline['inheritedProjectInputs']:
    p = ROOT / row['path']; q = S / 'project' / p.relative_to(O / 'project')
    assert q.stat().st_size == row['bytes'] and sha(q) == row['sha256']
new_files = ['hms/pat_io_run_bundle.py', 'tests/test_pat_io_run_bundle.py']
actual = {r['path'] for r in inventory(S / 'project')}
inherited = {(ROOT/r['path']).relative_to(O/'project').as_posix() for r in baseline['inheritedProjectInputs']}
assert actual - inherited == set(new_files) and len(actual) == 230
reviewed = [
    'All228 inherited project files are byte-identical. Only the bounded carrier builder/parser/fresh verifier and19tests are added.',
    'The structural parser validates bounded exact builtin bytes, canonical form, strict numeric types, closed external context and original authority, fixed ordered path/size/hash manifest, input-set/header digests, exact closure and matrix/case associations. It uses separately supplied trust anchors and does not replan or consult effects, SQL, files or clocks during parsing.',
    'Fresh verification invokes existing prepare_io_group and compares the complete reconstructed header and document mapping, with current source identity checks. Fully rehashed false setup remains structurally distinguishable from current semantic reconstruction. Neither function attests trusted service configuration or execution.',
    'Seven fixed inputs plus at most32cases, at most65536bytes each, total2555904 plus bounded header. This is an input collection, not a widened carrier or group bound, and must be included in the unchanged supervisor attempt reservation before admission.',
    'The header carries logical deployment/evaluator/run/configuration metadata only. It carries no caller executable/path/PID and authorizes no signal, hardware access or worker launch. A digest from an untrusted archive is not the required independently retained anchor.',
    'Review covers all new source and tests. Existing129pure methods plus19new checks are selected. New GPIO/PWM builders, exact reconstruction and adversaries execute no runtime, SQL, physical endpoint, MCU, inference, acquired controller or live service. The retained example contains original pre-run inputs, never physical or qualification evidence.',
    'Original180s parent and all acquisition/file/JSON/log/scratch limits remain. No group deadline, effect, protocol, storage or case bound changes. Adjacent Harness and live HMS sources remain untouched. Helpers unavailable; no independent review claim.',
]
write(S / 'source-review.json', dict(scope='Primary-agent complete additive carrier and test review before execution.',
    changedInheritedFiles=[], newFiles=new_files, unchangedInheritedFiles=228, reviewed=reviewed,
    independentReview=False, releasedBy='primary-agent', projectExecutionDuringPreparation=False))
(S / 'README.md').write_text('# Pre-run I/O carriers\n\n[Design](../DESIGN.md), [source review](source-review.json).\nAdditive isolated source; no supervisor integration or qualification claim.\n')
rows = inventory(S, True); assert len(rows) == 233
write(S / 'index.json', dict(scope='Frozen bounded pre-run I/O bundle and focused pure tests.', files=rows)); pin = sha(S / 'index.json')
assert sha(PRIOR/'index.json') == 'd7d61d76be5a17270760ba21fec078fb2e9d9a46e75d66a4a150bb567c15352e'
for row in read(PRIOR/'index.json')['files']:
    p = PRIOR/row['path']; assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
tree = ast.parse((S/'project/tests/test_pat_io_run_bundle.py').read_bytes())
body = next(n.body for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='IoRunBundleTests')
new = sorted('test_pat_io_run_bundle.IoRunBundleTests.'+n.name for n in body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
assert len(new) == 19
prior = read(PRIOR/'targets.json'); targets = prior['targets'] + new
assert len(prior['targets']) == 129 and len(targets) == len(set(targets)) == 148
H = B/'harness01'; H.mkdir(); (H/'references').mkdir(); borrowed=[]
for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
    p=PRIOR/name; q=H/'references'/p.name; shutil.copyfile(p,q)
    borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
write(H/'borrowed-inputs.json',borrowed); write(H/'targets.json',dict(testCount=len(targets),targets=targets))
for name in ('run_attempt.py','attempt_child.py'):
    before=(PRIOR/name).read_text()
    after=before.replace(baseline['sourceIndexSha256'],pin).replace(OLD.name,B.name).replace('implementation02','implementation01')
    after=after.replace('IoSnapshotReuse129','IoRunBundle148').replace('snapshot129','bundle148')
    after=re.sub(r'\b231\b','233',after); after=re.sub(r'\b228\b','230',after); after=re.sub(r'\b129\b','148',after)
    if name=='run_attempt.py':
        assert after.count(repr(prior['targets']))==1
        after=after.replace(repr(prior['targets']),repr(targets))
    ast.parse(after); (H/name).write_text(after)
    (H/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
        fromfile=(PRIOR/name).relative_to(ROOT).as_posix(),tofile=(H/name).relative_to(ROOT).as_posix())))
(H/'SCOPE.md').write_text('# Exact pure bundle and regression scope\n\nOnly the148named methods in targets.json:129unchanged pure checks plus19bundle methods.\nNo SQLite connection, network, subprocess, physical/MCU, inference or live-service execution.\nOriginal180s parent,16MiB scratch,8192files,256MiB inputs,16MiB file,4MiB JSON and8MiB logs remain.\nPreserve all failures, input originals and raw output. Parser operation is pure; fresh setup reads installed source identities.\n')
(H/'README.md').write_text('# Isolated I/O bundle checks\n\n[Targets](targets.json), [scope](SCOPE.md), [source](../implementation01/README.md).\n')
write(H/'review.json',dict(scope='Primary-agent exact additive source/selection/count harness review before execution.',
    tests=len(targets),sourceIndexSha256=pin,targetSha256=sha(H/'targets.json'),reviewed=reviewed,
    independentReview=False,releasedBy='primary-agent'))
parsed=ast.parse((H/'run_attempt.py').read_bytes())
lists=[ast.literal_eval(n) for n in ast.walk(parsed) if isinstance(n,ast.List) and n.elts and all(isinstance(e,ast.Constant) and isinstance(e.value,str) for e in n.elts)]
assert targets in lists
write(H/'index.json',dict(scope='Frozen original bounded harness with exact pure148 selection.',files=inventory(H)))
before=(OLD/'acquire.py').read_text(); after=before.replace(OLD.name,B.name)
after=after.replace("A/'project',228", "A/'project',230").replace('ROOT,231','ROOT,233')
after=after.replace('sourceFilesVerified=228,frozenFilesVerified=231','sourceFilesVerified=230,frozenFilesVerified=233')
after=after.replace("connections=read(A/'sqlite-connections.json')", "connections=read(A/'sqlite-connections.json'); assert connections==[]")
after=after.replace('Complete terminated current-group capture/budget attempt; synthetic private SQLite only.',
    'Complete terminated pure input-bundle and regression attempt; no SQLite connection or device execution.')
ast.parse(after); (B/'acquire.py').write_text(after)
(B/'acquire.py.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
    fromfile=(OLD/'acquire.py').relative_to(ROOT).as_posix(),tofile=(B/'acquire.py').relative_to(ROOT).as_posix())))
print(json.dumps(dict(projectFiles=230,frozenFiles=233,newTests=19,totalTests=148,
    sourceIndexSha256=pin,harnessIndexSha256=sha(H/'index.json'),targetSha256=sha(H/'targets.json'))))
