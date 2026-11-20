"""Preserve source01; fix only the receipt-key shadow in a fresh snapshot."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-clock-history';OLD=BASE/'implementation01';NEW=BASE/'implementation02'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
assert sha(OLD/'index.json')=='6fddf44b03d4910da1848f594a015f43d0df6b80d5d6cdbc0e7602c69d4d6d6b';NEW.mkdir();inherited=[]
for row in read(OLD/'index.json')['files']:
 p=ROOT/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 if p.is_relative_to(OLD/'project'):
  q=NEW/'project'/p.relative_to(OLD/'project');q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);inherited.append(row)
assert len(inherited)==8022
write(NEW/'baseline-inputs.json',dict(sourceIndex=(OLD/'index.json').relative_to(ROOT).as_posix(),sourceIndexSha256=sha(OLD/'index.json'),inheritedProjectInputs=inherited))
p=NEW/'project/hms/pat_io_board_history.py';before=p.read_text();old="""                        key = (cp['record'], operation_id)
                        require(key in checked_no_starts, 'PAT_IO_HISTORY_NO_START_CAUSE_UNIMPLEMENTED')
                        require(checked_no_starts[key] == result['reason'] == 'duration_budget_excluded',
                                'PAT_IO_HISTORY_NO_START_CAUSE')
                        consumed_no_starts.add(key)"""
new=old.replace('key','cause_key');assert before.count(old)==1;after=before.replace(old,new);p.write_text(after);ast.parse(after)
(BASE/'receipt-key-correction.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='implementation01/project/hms/pat_io_board_history.py',tofile='implementation02/project/hms/pat_io_board_history.py')))
write(NEW/'source-review.json',dict(scope='Primary-agent receipt-history key correction review after retained33-test failure.',
 inheritedInputsUnchanged=8021,changedFiles=['hms/pat_io_board_history.py'],testsAndFixturesUnchanged=True,
 diagnosis='The no-start cause lookup shadowed the outer (operation,sequence) receipt key. It inserted a valid receipt under (checkpoint,operation), then correctly failed inventory comparison.',
 correction='Use cause_key for the private context lookup and retain the original receipt key. No acceptance condition, cause derivation, proof, count or test assertion is relaxed.',
 initialResult='33 tests:1 failure,2 errors. Both delayed-start positive cases and unused-context check exposed the same shadow. Four clock recovery cases passed.',
 reviewed=['Exact four-line variable rename; full predicate logic and all33 tests unchanged.','Original runtime/provider/compiler/producer and all inherited fixtures remain byte-identical.','Fresh harnesses rerun33 new and168 unchanged semantic regressions under original boundaries.'],
 independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(NEW/'README.md').write_text('# Corrected pure clock-history candidate\n\nThe [design](../DESIGN.md) and [source review](source-review.json) describe complete\nclock challenge composition. Source01 and its failing run remain retained. This\nrevision only fixes a temporary cause-key shadow in the board receipt fold.\nAll tests, fixtures, runtime/provider/compiler and acceptance predicates are unchanged.\n')
rows=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p))for p in sorted(NEW.rglob('*'))if p.is_file()]
assert len(rows)==8025;write(NEW/'index.json',dict(scope='Corrected pure clock-history source; prior failures preserved.',files=rows));pin=sha(NEW/'index.json')
for a,b in [('01','05'),('02','06'),('03','07'),('04','08')]:
 O=BASE/('harness'+a);H=BASE/('harness'+b);H.mkdir();(H/'references').mkdir();borrowed=[]
 for row in read(O/'index.json')['files']:
  p=O/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
  p=O/item;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed);shutil.copyfile(O/'targets.json',H/'targets.json')
 for item in ['run_attempt.py','attempt_child.py']:
  before=(O/item).read_text();after=before.replace('implementation01','implementation02').replace('6fddf44b03d4910da1848f594a015f43d0df6b80d5d6cdbc0e7602c69d4d6d6b',pin)
  ast.parse(after);(H/item).write_text(after);(H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
 for item in ['README.md','SCOPE.md']:(H/item).write_text((O/item).read_text().replace('implementation01','implementation02'))
 review=read(O/'review.json');review.update(sourceIndexSha256=pin,reviewed=review['reviewed']+['Correction harness changes only source folder and pin; exact test IDs/counts/limits and SQLite refusal unchanged.'])
 write(H/'review.json',review)
 rows=[dict(path=p.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p))for p in sorted(H.rglob('*'))if p.is_file()]
 write(H/'index.json',dict(scope='Frozen exact original selection against corrected receipt-key source.',files=rows));print(H.name,sha(H/'index.json'))
print('source02',pin)
