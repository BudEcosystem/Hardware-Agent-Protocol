"""Freeze exact four-actor environment handling and unchanged retained subject."""
import ast,difflib,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-group-history';S=B/'implementation04';OLD=B/'implementation03'
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
baseline=read(S/'baseline-inputs.json');assert sha(OLD/'index.json')==baseline['sourceIndexSha256'];assert len(baseline['inheritedProjectInputs'])==4198
changed=[];patches=[]
for row in baseline['inheritedProjectInputs']:
 p=ROOT/row['path'];q=S/'project'/p.relative_to(OLD/'project');assert sha(p)==row['sha256']and p.stat().st_size==row['bytes']
 if sha(p)!=sha(q):
  changed.append(q.relative_to(S/'project').as_posix());patches.extend(difflib.unified_diff(p.read_text().splitlines(True),q.read_text().splitlines(True),fromfile=p.relative_to(ROOT).as_posix(),tofile=q.relative_to(ROOT).as_posix()))
assert changed==['hms/pat_io_group_history.py','tests/test_pat_io_group_history.py','tests/test_pat_io_group_retained.py']
(B/'actor-correction.patch').write_text(''.join(patches))
reviewed=['Only the resource opening branch changes production behavior. It requires initial creation, exact gpio/pwm/alias/independent maps in both original/current environments and a matching compiler identity for every actor. Existing full resource semantics still validates complete per-actor correspondence.',
 'One new pure method checks every original/current actor for absence, null, missing compiler, changed compiler, extra actor and forbidden reopen. Retained-test output names the exact source04 evaluator. All 3972 historical fixture files remain byte-identical.',
 'The unavailable-authority correction and all original semantic/accounting logic remain. No producer, runtime, case, budget, SQL scope, deadline or effect changes. Source01/source03 inspection failures, pre-start refusal and source02 incomplete fresh groups remain retained.',
 '107 selected pure checks and the exact one-method retained complete-history test. Passing retained inspection cannot qualify a current capture or attest run/physical/quota properties. All original harness acquisition and output ceilings unchanged.']
write(S/'source-review.json',dict(scope='Primary-agent complete actor correction and tests reviewed before execution.',changedFiles=changed,unchangedInheritedFiles=4195,reviewed=reviewed,independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Exact actor environments in complete group inspection\n\n[Design](../DESIGN.md), [corrections](../CORRECTION.md), [review](source-review.json).\nOriginal retained subject/setup bytes remain unchanged. Current qualification is incomplete.\n')
rows=inventory(S,True);assert len(rows)==4201;write(S/'index.json',dict(scope='Exact four-actor environment correction over unchanged complete retained subject.',files=rows));pin=sha(S/'index.json')
new='test_pat_io_group_history.IoGroupSetupTests.test_resource_environment_checks_all_four_original_and_current_actors'
for number,origin in ((11,7),(12,10)):
 old=B/('harness%02d'%origin);h=B/('harness%02d'%number);h.mkdir();(h/'references').mkdir()
 for row in read(old/'index.json')['files']:assert sha(old/row['path'])==row['sha256']
 prior=read(old/'targets.json');targets=prior['targets']+([new]if number==11 else [])
 write(h/'targets.json',dict(testCount=len(targets),targets=targets));borrow=[]
 for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
  p=old/name;q=h/'references'/p.name;shutil.copyfile(p,q);borrow.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(h).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(h/'borrowed-inputs.json',borrow)
 for name in ('run_attempt.py','attempt_child.py'):
  before=(old/name).read_text();after=before.replace(read(old/'review.json')['sourceIndexSha256'],pin)
  after=after.replace('implementation02','implementation04').replace('implementation03','implementation04')
  if number==11:
   after=re.sub(r'\b228\b','4201',after);after=re.sub(r'\b225\b','4198',after);after=re.sub(r'\b106\b','107',after)
   after=after.replace('IoGroupHistory106','IoGroupHistory107').replace('history106','history107')
   if name=='run_attempt.py':assert after.count(repr(prior['targets']))==1;after=after.replace(repr(prior['targets']),repr(targets))
  ast.parse(after);(h/name).write_text(after);(h/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(old/name).relative_to(ROOT).as_posix(),tofile=(h/name).relative_to(ROOT).as_posix())))
 shutil.copyfile(B/'harness10/SCOPE.md',h/'SCOPE.md');(h/'README.md').write_text('# Corrected actor environment validation\n\n[Targets](targets.json), [scope](SCOPE.md), [review](review.json).\n')
 write(h/'review.json',dict(scope='Exact source04 selectors, targets, acquisition counts and original bounds reviewed.',tests=len(targets),sourceIndexSha256=pin,targetSha256=sha(h/'targets.json'),reviewed=reviewed,independentReview=False,releasedBy='primary-agent'))
 write(h/'index.json',dict(scope='Frozen original bounded corrected-reader harness.',files=inventory(h)))
 print(json.dumps(dict(harness=h.name,tests=len(targets),indexSha256=sha(h/'index.json'))))
print(json.dumps(dict(projectFiles=4198,frozenFiles=4201,sourceIndexSha256=pin)))
