"""Reject unsupported mapping key types before any set hashing/equality hook."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT=Path.cwd(); B=ROOT/'artifacts/implementation/pat-io-run-bundle'
O=B/'implementation02'; S=B/'implementation03'; OLD=B/'harness02'; H=B/'harness03'
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
assert sha(O/'index.json')=='d4923234e678a2acf389178d396128e85a1a2da7d83f78bab29d4a0d8be09452'
proof=read(B/'results/attempt02-passed148/proof.json'); assert proof['counts']['testsRun']==148 and proof['status']=='passed'
(S/'project').mkdir(parents=True); inherited=[]
for row in read(O/'index.json')['files']:
    p=ROOT/row['path']; assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes']
    if p.is_relative_to(O/'project'):
        q=S/'project'/p.relative_to(O/'project'); q.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,q); inherited.append(row)
assert len(inherited)==230
write(S/'baseline-inputs.json',dict(sourceIndexSha256=sha(O/'index.json'),inheritedProjectInputs=inherited))
changes={}
p=S/'project/hms/pat_io_run_bundle.py'; before=p.read_text()
anchor="    _require(type(documents) is dict and len(documents) == len(paths) and set(documents) == set(paths), 'CLOSURE')\n"
replacement="    _require(type(documents) is dict and len(documents) == len(paths), 'CLOSURE')\n"
assert before.count(anchor)==1; after=before.replace(anchor,replacement)
anchor="        for k, v in documents.items()), 'DOCUMENT')\n"
assert after.count(anchor)==1; after=after.replace(anchor,anchor+"    _require(set(documents) == set(paths), 'CLOSURE')\n")
ast.parse(after); p.write_text(after); changes['hms/pat_io_run_bundle.py']=(before,after)
p=S/'project/tests/test_pat_io_run_bundle.py'; before=p.read_text()
anchor='    def test_changed_content_cannot_reuse_retained_manifest_or_digest(self):\n'
addition='''    def test_mapping_key_subclasses_refuse_before_hash_or_equality_callbacks(self):
        class PathKey(str): pass
        changed = copy.deepcopy(self.original); path = 'inputs/authority.json'
        raw = changed['documents'].pop(path); changed['documents'][PathKey(path)] = raw
        with patch.object(PathKey, '__hash__', side_effect=AssertionError('caller hash')), \\
             patch.object(PathKey, '__eq__', side_effect=AssertionError('caller equality')):
            with self.assertRaisesRegex(bundle.IoRunBundleError, 'DOCUMENT'): self.parse(changed)

'''
assert before.count(anchor)==1; after=before.replace(anchor,addition+anchor); ast.parse(after); p.write_text(after)
changes['tests/test_pat_io_run_bundle.py']=(before,after)
patches=[]
for rel,(before,after) in changes.items():
    patches.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
        fromfile=(O/'project'/rel).relative_to(ROOT).as_posix(),tofile=(S/'project'/rel).relative_to(ROOT).as_posix()))
(B/'key-guard.patch').write_text(''.join(patches))
changed=[]
for row in inherited:
    p=ROOT/row['path']; rel=p.relative_to(O/'project')
    if sha(S/'project'/rel)!=row['sha256']: changed.append(rel.as_posix())
assert set(changed)==set(changes)
reviewed=[
    'Static final review found exact document key types were checked after set(documents), which could invoke a rejected subclass hashing/equality hook. Original source02passed148 remains preserved; no production execution failure is inferred.',
    'Retain exact mapping type/count check first, then all exact key/value types and byte bounds, then compare path sets. Only this validation order changes. Unsupported Python object hooks are never needed for the permitted builtin wire mapping.',
    'New regression constructs a str-subclass key before installing raising hash/equality hooks, then requires DOCUMENT refusal without either hook. All228original baseline project files and all prior148methods remain unchanged. New total149.',
    'Primary-agent complete source/test delta and exact harness count/list changes reviewed; no independent helper review. No source, effect, record, byte, case, storage or timeout limits widened.',
]
write(S/'source-review.json',dict(scope='Primary-agent early builtin-key guard reviewed before execution.',changedFiles=changed,
    unchangedInheritedFiles=228,reviewed=reviewed,independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Reject custom key hooks before path comparison\n\n[Guard correction](../KEY-GUARD.md), [review](source-review.json).\nOnly validation ordering and one regression change from source02.\n')
rows=inventory(S,True); assert len(rows)==233
write(S/'index.json',dict(scope='Exact builtin document key types checked before set comparison;149pure methods.',files=rows)); pin=sha(S/'index.json')
assert sha(OLD/'index.json')=='7004abcb03abdcbc779bd738a89e357b6a4d0dfb57afe7cea682ddf24386a595'
for row in read(OLD/'index.json')['files']:
    p=OLD/row['path']; assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes']
prior=read(OLD/'targets.json'); targets=prior['targets']+['test_pat_io_run_bundle.IoRunBundleTests.test_mapping_key_subclasses_refuse_before_hash_or_equality_callbacks']
assert len(targets)==len(set(targets))==149
H.mkdir(); (H/'references').mkdir(); borrowed=[]
for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
    p=OLD/name; q=H/'references'/p.name; shutil.copyfile(p,q)
    borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
write(H/'borrowed-inputs.json',borrowed); write(H/'targets.json',dict(testCount=149,targets=targets))
for name in ('run_attempt.py','attempt_child.py'):
    before=(OLD/name).read_text(); after=before.replace(sha(O/'index.json'),pin).replace('implementation02','implementation03')
    after=after.replace('IoRunBundle148','IoRunBundle149').replace('bundle148','bundle149'); after=re.sub(r'\b148\b','149',after)
    if name=='run_attempt.py':
        assert after.count(repr(prior['targets']))==1; after=after.replace(repr(prior['targets']),repr(targets))
    ast.parse(after); (H/name).write_text(after)
    (H/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
        fromfile=(OLD/name).relative_to(ROOT).as_posix(),tofile=(H/name).relative_to(ROOT).as_posix())))
(H/'README.md').write_text((OLD/'README.md').read_text().replace('implementation02','implementation03'))
(H/'SCOPE.md').write_text((OLD/'SCOPE.md').read_text().replace('148named','149named').replace('19bundle','20bundle'))
review=read(OLD/'review.json'); review.update(tests=149,sourceIndexSha256=pin,targetSha256=sha(H/'targets.json'),scope='Source03exact149selection; early key guard plus original checks.')
review['reviewed']+=reviewed; write(H/'review.json',review)
write(H/'index.json',dict(scope='Original bounded pipeline on source03with149pure methods.',files=inventory(H)))
print(json.dumps(dict(sourceIndexSha256=pin,harnessIndexSha256=sha(H/'index.json'),targetSha256=sha(H/'targets.json'),tests=149)))
