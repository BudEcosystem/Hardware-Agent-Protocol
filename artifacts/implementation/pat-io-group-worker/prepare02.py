"""Freeze the exact negative-result correction and fresh selections."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-group-worker';S=B/'implementation02';O=B/'implementation01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
changed={'hms/pat_io_group_worker.py','tests/test_pat_io_group_worker.py'};patches=[]
for r in read(S/'baseline-inputs.json')['inheritedProjectInputs']:
 p=ROOT/r['path'];rel=p.relative_to(O/'project');q=S/'project'/rel
 assert sha(p)==r['sha256']and p.stat().st_size==r['bytes'];assert(sha(p)!=sha(q))is(rel.as_posix()in changed)
 if rel.as_posix()in changed:patches.extend(difflib.unified_diff(p.read_text().splitlines(True),q.read_text().splitlines(True),fromfile=p.relative_to(ROOT).as_posix(),tofile=q.relative_to(ROOT).as_posix()))
(B/'negative-result-correction.patch').write_text(''.join(patches))
write(S/'source-review.json',dict(scope='Primary-agent complete two-file delta reviewed before execution; actual failed GPIO and acquisition error retained.',changedFiles=sorted(changed),unchangedFiles=215,
 reviewed=['Map only validated not_applicable outcomes to the existing compiler PAT_NOT_APPLICABLE code. Refused outcomes retain exact declared errors. No planner, compiler, runtime, budget or fault behavior changed.',
 'Negative capture now records staticOutcome and actual compiler code separately. One pure regression covers all four constant-candidate negatives and forbids runtime construction.',
 'Full group test checks this distinction; original30cases/44children/1676ticks and all evidence/time ceilings remain. Previous failed source and raw state unchanged.',
 'Fresh12pure,GPIO,PWM,partial selections; old unexecuted source01 PWM/partial harnesses are retained without execution.'],independentReview=False,releasedBy='primary-agent'))
(S/'README.md').write_text('# Group capture with exact negative result mapping\n\nSee [design](../DESIGN.md), [diagnosis](../DIAGNOSIS.json), and\n[source review](source-review.json). This corrects the compiler/planner distinction\nfor not-applicable cases while preserving all original limits and required cases.\nQualification and hard filesystem quotas remain unfinished.\n')
rows=[]
for p in sorted(S.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  if p.suffix=='.py':ast.parse(p.read_bytes())
  rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==220;write(S/'index.json',dict(scope='Exact negative applicability/refusal distinction; all original group bounds unchanged.',files=rows));pin=sha(S/'index.json')
for i in range(1,5):
 old=B/('harness%02d'%i);h=B/('harness%02d'%(i+4));h.mkdir();(h/'references').mkdir();borrowed=[]
 for r in read(old/'index.json')['files']:assert sha(old/r['path'])==r['sha256']
 for n in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
  p=old/n;q=h/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(h).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(h/'borrowed-inputs.json',borrowed);t=read(old/'targets.json');before_targets=t['targets'][:]
 if i==1:
  t['targets'].insert(0,'test_pat_io_group_worker.IoGroupBudgetTests.test_negative_preflight_distinguishes_refused_and_not_applicable');t['testCount']=12
 write(h/'targets.json',t)
 for n in ['run_attempt.py','attempt_child.py']:
  before=(old/n).read_text();after=before.replace('84d21cc5515a9be0d8c8112b1c1c49a747e3088a243ca82eead659009c3e1408',pin).replace('implementation01','implementation02')
  if i==1:
   after=after.replace('IoGroup11','IoGroup12').replace('group11','group12').replace('!= 11','!= 12').replace('== 11','== 12').replace("'expectedTests': 11","'expectedTests': 12").replace(repr(before_targets),repr(t['targets']))
  ast.parse(after);(h/n).write_text(after)
  (h/(n+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(old/n).relative_to(ROOT).as_posix(),tofile=(h/n).relative_to(ROOT).as_posix())))
 (h/'README.md').write_text('# Corrected group selection\n\n[Exact targets](targets.json), [source02](../implementation02/README.md),\n[scope](SCOPE.md). Complete source/harness deltas reviewed before execution.\n')
 shutil.copyfile(old/'SCOPE.md',h/'SCOPE.md')
 print(json.dumps(dict(harness=h.name,tests=t['testCount'],targetSha256=sha(h/'targets.json'))))
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=217,frozenFiles=220)))
