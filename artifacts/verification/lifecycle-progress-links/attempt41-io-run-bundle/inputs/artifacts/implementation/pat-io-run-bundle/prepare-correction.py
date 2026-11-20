"""Correct the identity mock lookup; keep production and original failures."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd(); B=ROOT/'artifacts/implementation/pat-io-run-bundle'
O=B/'implementation01'; S=B/'implementation02'; OLD=B/'harness01'; H=B/'harness02'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p,v):
    with p.open('x') as f: f.write(json.dumps(v,indent=2)+'\n')
def inventory(folder,rooted=False):
    rows=[]
    for p in sorted(folder.rglob('*')):
        assert not p.is_symlink()
        if p.is_file():
            if p.suffix=='.py': ast.parse(p.read_bytes())
            rows.append(dict(path=p.relative_to(ROOT if rooted else folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    return rows
assert sha(O/'index.json')=='05ac1edd337b0a37d63a96adca30e60bd67cc7551b522de4115e47d40827e0d8'
proof=read(B/'results/attempt01-failed148/proof.json')
assert proof['counts']['testsRun']==148 and proof['counts']['failures']==1 and proof['counts']['errors']==0
assert proof['sqliteConnections']==0 and read(B/'results/attempt01-failed148/attempt/result.json')['childState']=='exited'
(S/'project').mkdir(parents=True); inherited=[]
for row in read(O/'index.json')['files']:
    p=ROOT/row['path']; assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes']
    if p.is_relative_to(O/'project'):
        q=S/'project'/p.relative_to(O/'project'); q.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,q); inherited.append(row)
assert len(inherited)==230
write(S/'baseline-inputs.json',dict(sourceIndexSha256=sha(O/'index.json'),inheritedProjectInputs=inherited))
p=S/'project/tests/test_pat_io_run_bundle.py'; before=p.read_text()
anchor="""        with patch('hms.pat_io_group_worker._identities', return_value=identity):
            with self.assertRaisesRegex(bundle.IoRunBundleError, 'FRESH_MISMATCH'): self.fresh()
"""
replacement="""        with patch('hms.pat_io_group_setup._identities', return_value=identity) as changed:
            with self.assertRaisesRegex(bundle.IoRunBundleError, 'FRESH_MISMATCH'): self.fresh()
        changed.assert_called_once()
"""
assert before.count(anchor)==1; after=before.replace(anchor,replacement); ast.parse(after); p.write_text(after)
(B/'test-correction.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
    fromfile=(O/'project/tests/test_pat_io_run_bundle.py').relative_to(ROOT).as_posix(),tofile=p.relative_to(ROOT).as_posix())))
changed=[]
for row in inherited:
    p=ROOT/row['path']; rel=p.relative_to(O/'project')
    if sha(S/'project'/rel)!=row['sha256']: changed.append(rel.as_posix())
assert changed==['tests/test_pat_io_run_bundle.py']
reviewed=[
    'First attempt147passes/onefailure preserved. The failing second assertion patched the defining module after setup imported the function; it did not inject a changed identity. The actual-source-change assertion before it passed.',
    'Patch the setup module function reference that is actually called and require one call. Keep exact FRESH_MISMATCH expectation and all other assertions. Complete delta reviewed by primary agent; no independent helper review.',
    'All production and229of230 inherited project files are unchanged. Use exact148method selection and original limits. No state reset, physical execution, SQLite connection, live-service or adjacent Harness mutation.',
]
write(S/'source-review.json',dict(scope='Primary-agent test-only lookup correction reviewed before execution.',
    changedFiles=changed,unchangedInheritedFiles=229,productionUnchanged=True,reviewed=reviewed,
    independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Correct the changed-identity injection\n\nProduction matches source01. [Correction](../CORRECTION.md), [review](source-review.json).\n')
rows=inventory(S,True); assert len(rows)==233
write(S/'index.json',dict(scope='Only test lookup correction; production unchanged from source01.',files=rows)); pin=sha(S/'index.json')
assert sha(OLD/'index.json')=='b07982ea8c150c4e56f264c3d5429057dc0b3a32a27e3a7c7cc8b8749c38b9f4'
for row in read(OLD/'index.json')['files']:
    p=OLD/row['path']; assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes']
H.mkdir(); (H/'references').mkdir(); borrowed=[]
for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
    p=OLD/name; q=H/'references'/p.name; shutil.copyfile(p,q)
    borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
write(H/'borrowed-inputs.json',borrowed)
for name in ('attempt_child.py','targets.json','SCOPE.md'): shutil.copyfile(OLD/name,H/name)
before=(OLD/'run_attempt.py').read_text(); after=before.replace(sha(O/'index.json'),pin).replace('implementation01','implementation02')
ast.parse(after); (H/'run_attempt.py').write_text(after)
(H/'run_attempt.py.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
    fromfile=(OLD/'run_attempt.py').relative_to(ROOT).as_posix(),tofile=(H/'run_attempt.py').relative_to(ROOT).as_posix())))
(H/'README.md').write_text((OLD/'README.md').read_text().replace('implementation01','implementation02'))
review=read(OLD/'review.json'); review.update(sourceIndexSha256=pin,scope='Source02 test-only correction; exact148selection and unchanged limits.')
review['reviewed']+=reviewed; write(H/'review.json',review)
write(H/'index.json',dict(scope='Original bounded pure148 pipeline on corrected test lookup source02.',files=inventory(H)))
print(json.dumps(dict(sourceIndexSha256=pin,harnessIndexSha256=sha(H/'index.json'),projectFiles=230,frozenFiles=233,tests=148)))
