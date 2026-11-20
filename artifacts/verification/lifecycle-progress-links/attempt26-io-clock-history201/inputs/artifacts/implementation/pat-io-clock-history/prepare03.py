"""Preserve both failures; derive the atomic claim release of start exclusion."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-clock-history';OLD=BASE/'implementation02';NEW=BASE/'implementation03'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
assert sha(OLD/'index.json')=='c33c4ce245f95cf087201ffa7eedd5290a554f69aa5c2ad8301b5998d591a01e';NEW.mkdir();inherited=[]
for row in read(OLD/'index.json')['files']:
 p=ROOT/row['path'];assert p.stat().st_size==row['bytes']and sha(p)==row['sha256']
 if p.is_relative_to(OLD/'project'):
  q=NEW/'project'/p.relative_to(OLD/'project');q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);inherited.append(row)
assert len(inherited)==8022
write(NEW/'baseline-inputs.json',dict(sourceIndex=(OLD/'index.json').relative_to(ROOT).as_posix(),sourceIndexSha256=sha(OLD/'index.json'),inheritedProjectInputs=inherited))
p=NEW/'project/hms/pat_io_operation_history.py';before=p.read_text();old="consumed_no_starts.add(op_id); st['may_have_acted'] = 0";new="consumed_no_starts.add(op_id); st.update(may_have_acted=0, held=False)"
assert before.count(old)==1;after=before.replace(old,new);p.write_text(after);ast.parse(after)
(BASE/'start-exclusion-release-correction.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='implementation02/project/hms/pat_io_operation_history.py',tofile='implementation03/project/hms/pat_io_operation_history.py')))
write(NEW/'source-review.json',dict(scope='Primary-agent atomic start-exclusion claim-release correction review.',
 inheritedInputsUnchanged=8021,changedFiles=['hms/pat_io_operation_history.py'],testsAndFixturesUnchanged=True,
 diagnosis='After the board-key fix, the same two delayed-start cases reached the operation fold and failed CLAIMS: it cleared may_have_acted but incorrectly retained modeled claims.',
 evidence='journal.py _execution lines615-619 resets may_have_acted and deletes claims atomically before the execution_evidence event when start_excluded is validated. Captured guard phases have exactly accepted,dispatch_claimed,execution_evidence; no separate resource-release event.',
 correction='Set held=False only within the independently derived rejected_before_start transition after exact receipt evidence passes. Existing resource/fence equality then requires actual claims absent and floors retained.',
 reviewed=['One model-state update, no weakened comparisons or event/evidence changes. All33 original tests unchanged.',
 'Runtime/provider/compiler and all fixtures remain unchanged. Previous source snapshots, complete failures and empty original scratch roots retained.',
 'Four exact pure regression selections retain original180s/16MiB/8192-file bounds and forbid SQLite.'],
 independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(NEW/'README.md').write_text('# Clock-history candidate with atomic start exclusion\n\nSee the [design](../DESIGN.md) and [source review](source-review.json).\nSource01 and02 and both failing runs are retained. This revision derives the\natomic claim release already performed by the original runtime when exact\nevidence proves no start. All tests, fixtures and runtime/provider/compiler bytes\nare unchanged. Full matrix qualification and the end-to-end goal remain incomplete.\n')
rows=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p))for p in sorted(NEW.rglob('*'))if p.is_file()]
assert len(rows)==8025;write(NEW/'index.json',dict(scope='Clock semantic source with atomic claim-release derivation; prior failures retained.',files=rows));pin=sha(NEW/'index.json')
for a,b in [('05','09'),('06','10'),('07','11'),('08','12')]:
 O=BASE/('harness'+a);H=BASE/('harness'+b);H.mkdir();(H/'references').mkdir();borrowed=[]
 for row in read(O/'index.json')['files']:
  p=O/row['path'];assert p.stat().st_size==row['bytes']and sha(p)==row['sha256']
 for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
  p=O/item;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed);shutil.copyfile(O/'targets.json',H/'targets.json')
 for item in ['run_attempt.py','attempt_child.py']:
  before=(O/item).read_text();after=before.replace('implementation02','implementation03').replace('c33c4ce245f95cf087201ffa7eedd5290a554f69aa5c2ad8301b5998d591a01e',pin)
  ast.parse(after);(H/item).write_text(after);(H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
 for item in ['README.md','SCOPE.md']:(H/item).write_text((O/item).read_text().replace('implementation02','implementation03'))
 review=read(O/'review.json');review.update(sourceIndexSha256=pin,reviewed=review['reviewed']+['Atomic-release correction harness changes only source folder/pin;33 tests and all original regressions unchanged.'])
 write(H/'review.json',review)
 rows=[dict(path=p.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p))for p in sorted(H.rglob('*'))if p.is_file()]
 write(H/'index.json',dict(scope='Frozen original exact selections against atomic-release correction.',files=rows));print(H.name,sha(H/'index.json'))
print('source03',pin)
