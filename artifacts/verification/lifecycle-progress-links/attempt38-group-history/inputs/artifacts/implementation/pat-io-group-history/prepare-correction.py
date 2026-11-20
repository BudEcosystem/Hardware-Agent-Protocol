"""Freeze narrow unavailable-resolution correction without replacing failures."""
import ast,difflib,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-group-history';S=B/'implementation02';OLD=B/'implementation01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
def inventory(folder,rooted=False):
 rows=[]
 for p in sorted(folder.rglob('*')):
  assert not p.is_symlink()
  if p.is_file():
   if p.suffix=='.py':ast.parse(p.read_bytes())
   rows.append(dict(path=p.relative_to(ROOT if rooted else folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 return rows
baseline=read(S/'baseline-inputs.json');assert sha(OLD/'index.json')==baseline['sourceIndexSha256'];assert len(baseline['inheritedProjectInputs'])==225
changed=[];patches=[]
for row in baseline['inheritedProjectInputs']:
 p=ROOT/row['path'];q=S/'project'/p.relative_to(OLD/'project');assert sha(p)==row['sha256']and p.stat().st_size==row['bytes']
 if sha(q)!=sha(p):
  changed.append(q.relative_to(S/'project').as_posix());patches.extend(difflib.unified_diff(p.read_text().splitlines(True),q.read_text().splitlines(True),fromfile=p.relative_to(ROOT).as_posix(),tofile=q.relative_to(ROOT).as_posix()))
assert changed==['hms/pat_io_group_history.py','tests/test_pat_io_group_history.py']
(B/'correction.patch').write_text(''.join(patches))
review=read(OLD/'source-review.json');review.update(scope='Primary-agent complete narrow correction reviewed before execution.',
 changedFiles=changed,unchangedInheritedFiles=223,newFiles=[],projectExecutionDuringPreparation=False)
review['reviewed'] += ['Retained GPIO capture completed but source01 inspector failed on null current environment after authority loss. Source02 always checks original compiler identity and permits null current resolution only for the exact two authority reopen scenarios, create false and the original unavailable-resolution marker. Existing full authority semantics still proves cause; no guard/case/bound changes.',
 'One new pure method covers both legitimate absences, wrong scenario/create/marker/original compiler, null original environment, ordinary current compiler and changed current compiler. Full fresh GPIO and PWM are still required.']
write(S/'source-review.json',review)
(S/'README.md').write_text('# Group history with explicit unavailable current resolution\n\n[Design](../DESIGN.md), [correction](../CORRECTION.md), [review](source-review.json).\n')
rows=inventory(S,True);assert len(rows)==228;write(S/'index.json',dict(scope='Narrow authority reopen resolution correction; failed source01 retained.',files=rows));pin=sha(S/'index.json')
new_test='test_pat_io_group_history.IoGroupSetupTests.test_absent_current_environment_requires_exact_authority_reopen_context'
for origin in (1,2,3):
 old=B/('harness%02d'%origin);h=B/('harness%02d'%(origin+3));h.mkdir();(h/'references').mkdir()
 for row in read(old/'index.json')['files']:assert sha(old/row['path'])==row['sha256']
 prior=read(old/'targets.json');targets=prior['targets']+([new_test]if origin==1 else [])
 write(h/'targets.json',dict(testCount=len(targets),targets=targets));borrow=[]
 for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
  p=old/name;q=h/'references'/p.name;shutil.copyfile(p,q);borrow.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(h).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(h/'borrowed-inputs.json',borrow)
 for name in ('run_attempt.py','attempt_child.py'):
  before=(old/name).read_text();after=before.replace(baseline['sourceIndexSha256'],pin).replace('pat-io-group-history/implementation01/','pat-io-group-history/implementation02/')
  if origin==1:
   after=re.sub(r'\b105\b','106',after).replace('IoGroupHistory105','IoGroupHistory106').replace('history105','history106')
   if name=='run_attempt.py':assert after.count(repr(prior['targets']))==1;after=after.replace(repr(prior['targets']),repr(targets))
  ast.parse(after);(h/name).write_text(after);(h/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(old/name).relative_to(ROOT).as_posix(),tofile=(h/name).relative_to(ROOT).as_posix())))
 shutil.copyfile(old/'SCOPE.md',h/'SCOPE.md');shutil.copyfile(old/'README.md',h/'README.md')
 write(h/'review.json',dict(scope='Exact source02 pin, unchanged SQL/bounds, 106 pure or original full-history selection reviewed.',tests=len(targets),sourceIndexSha256=pin,targetSha256=sha(h/'targets.json'),reviewed=review['reviewed'],independentReview=False,releasedBy='primary-agent'))
 write(h/'index.json',dict(scope='Frozen narrow corrected group-history harness.',files=inventory(h)))
 print(json.dumps(dict(harness=h.name,tests=len(targets),indexSha256=sha(h/'index.json'))))
print(json.dumps(dict(projectFiles=225,frozenFiles=228,sourceIndexSha256=pin)))
