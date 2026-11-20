"""Freeze complete resource composition and exact pure regression selections."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-resource-semantics';S=B/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-resource-challenge/implementation01/project';C=ROOT/'artifacts/implementation/pat-io-clock-history'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
baseline=read(S/'baseline-inputs.json');changed=[]
for r in baseline['inheritedProjectInputs']:
 p=ROOT/r['path'];assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes'];rel=p.relative_to(OLD);q=S/'project'/rel
 if sha(q)!=r['sha256'] or q.stat().st_size!=r['bytes']:changed.append(rel.as_posix())
assert set(changed)=={'hms/pat_io_board_history.py','hms/pat_io_operation_history.py','hms/pat_io_configuration_history.py'}
write(S/'source-review.json',dict(scope='Primary-agent pure multi-actor history and complete composition review before execution.',
 inheritedInputsUnchanged=7075,changedFiles=sorted(changed),excludedClockFixtures=947,newResourceFixtureFiles=585,
 newFiles=['hms/pat_io_resource_semantics.py','tests/test_pat_io_resource_semantics.py'],
 reviewed=['Closed structural case/request correspondence precedes private shared-model handoff. Unknown actors refuse; default public single-actor profiles unchanged.',
 'Board claims derive per intent; operation events retain exact authority/state/evidence/fence checks. Direct association requires4 original actor keys and empty parent tables.',
 'All four descriptors/registrations, immutable installed state, trusted grants, sessions, presence and sample sequence/value semantics compose.',
 'Fresh admissions/refusals, required eligible dispatch, five exact replay replies and one historical result are derived. All between-call stores are unchanged.',
 'Three RESOURCE_BUSY refusals are derived from pre-call overlapping claims after checking live admission context. The GPIO probe stays unretained; actual4 effects and zero unresolved work are required.',
 '31 original tests include both real captures, coherent receipt/event-reference attacks, forged call results, hidden actors, ownership/floors, sample/binding/permission attacks and purity.',
 'Original runtime/provider/compiler modules and old tests unchanged.73 board/operation and48 configuration regressions preserve their exact old selection.',
 'The explicit closure excludes only947 old clock fixture files, retains them in the old sealed stage, and adds585 resource fixture files. No ceiling widened.'],
 independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Shared-resource semantic composition\n\nSee the [design](../DESIGN.md) and [source review](source-review.json).\nThe new pure composition reconstructs exact multi-actor ownership, effects,\nauthority, samples and returned results. Full candidate qualification remains\nunfinished. The explicit input closure excludes clock-only fixtures and retains\nthe original8192-file ceiling; all original sealed evidence stays intact.\n')
rows=[]
for p in sorted(S.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  if p.suffix=='.py':ast.parse(p.read_bytes())
  rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==7668;write(S/'index.json',dict(scope='Frozen complete resource composition and explicit pure-test closure.',files=rows));pin=sha(S/'index.json')
tree=ast.parse((S/'project/tests/test_pat_io_resource_semantics.py').read_bytes());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='IoResourceSemanticsTests')
new=sorted('test_pat_io_resource_semantics.IoResourceSemanticsTests.'+n.name for n in cls.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'));assert len(new)==31
specs=[('harness09','5247016ccd4f26b233c0d46162b774d65bf1918ba5959575bac1350d0edcd2ec',33,new),
 ('harness10','e3821e99e485fa385eea7da2d0dc650f0ecaaa3155758cd2b0fb2dde678e6a6a',73,None),
 ('harness13','c2cc11b0a27908d4947a1b34e50dee56f6d8542d588203aea9897502a0e12cc5',48,None)]
for number,(name,oldpin,oldcount,targets) in enumerate(specs,1):
 O=C/name;assert sha(O/'index.json')==oldpin
 for r in read(O/'index.json')['files']:
  p=O/r['path'];assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes']
 targets=targets if targets is not None else read(O/'targets.json')['targets'];count=len(targets)
 H=B/('harness%02d'%number);H.mkdir();(H/'references').mkdir();borrowed=[]
 for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
  p=O/item;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=count,targets=targets))
 for item in ['run_attempt.py','attempt_child.py']:
  before=(O/item).read_text();after=before.replace('io-clock-history','io-resource-semantics').replace('implementation03','implementation01').replace('f98de6d5d3c76335cb74032da5641750a21d6de37af8004f2738f0797aba5ff9',pin)
  after=after.replace('8025','7668').replace('8022','7665').replace('ClockHistory'+str(oldcount),'ResourceHistory'+str(count)).replace('clock'+str(oldcount),'resource'+str(count)).replace('Pure clock history','Pure resource history')
  if number==1:
   after=after.replace('!= 33','!= 31').replace('== 33','== 31').replace("'expectedTests': 33","'expectedTests': 31").replace('test_pat_io_clock_semantics.','test_pat_io_resource_semantics.')
  after=after.replace('33 original pure clock semantic tests','31 original pure resource semantic tests')
  ast.parse(after);(H/item).write_text(after)
  (H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
 (H/'README.md').write_text('# Pure resource history selection '+str(count)+'\n\n[Exact methods](targets.json), [frozen source](../implementation01/README.md),\nand [execution boundaries](SCOPE.md). Launcher/child diff review precedes execution.\n')
 (H/'SCOPE.md').write_text('# Fixed pure execution scope\n\n'+str(count)+' exact pure methods; no SQLite, network, child subprocesses, runtime,\nphysical/MCU execution, live inference or services. Original180s,16MiB scratch,\n8192-file,256MiB input,16MiB file,4MiB JSON and8MiB log bounds unchanged.\nThe source closure explicitly excludes947 clock-only fixtures; original sealed\nfiles remain intact. Preserve original raw scratch and all outcomes. Primary-agent\nreview only; helpers remain usage-limited. Full candidate qualification is pending.\n')
 print(json.dumps(dict(harness=H.name,tests=count,targetsSha256=sha(H/'targets.json'))))
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=7665,frozenFiles=7668)))
