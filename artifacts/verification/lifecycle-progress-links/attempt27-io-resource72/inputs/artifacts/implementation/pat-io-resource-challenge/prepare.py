"""Freeze shared-resource source and prepare bounded harness; stdlib only."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-resource-challenge';S=BASE/'implementation01'
O=ROOT/'artifacts/implementation/pat-io-clock-challenges/harness01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x') as f:f.write(json.dumps(v,indent=2)+'\n')
baseline=read(S/'baseline-inputs.json')['inheritedProjectInputs'];old=ROOT/'artifacts/implementation/pat-io-clock-history/implementation03/project';changed=[]
for row in baseline:
 p=ROOT/row['path'];assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes']
 r=p.relative_to(old);q=S/'project'/r
 if sha(q)!=row['sha256'] or q.stat().st_size!=row['bytes']:changed.append(r.as_posix())
assert set(changed)=={'hms/pat_io_combined_matrix.py','hms/pat_io_transcript.py','tests/test_pat_io_combined_matrix.py'}
new=['hms/pat_io_resource_capture.py','hms/pat_io_resource_history.py','tests/test_pat_io_resource_challenge.py']
write(S/'source-review.json',dict(scope='Primary-agent direct shared-resource source and original provider path review before execution.',
 inheritedInputsUnchanged=8019,changedFiles=sorted(changed),newFiles=new,
 reviewed=['Matrix0.2 declares an original GPIO probe and reserves possible admission5 without changing the global512 ceiling. Successful actions remain4.',
 'Four fixed PATs compile once with one replay namespace. Direct child invokes do not create parents or claim a general multi-role PAT implementation.',
 'The closed original request inventory is enforced before the unchanged authority guard. Four real admissions cannot mask the fifth probe behind an operation cap.',
 'Initial PWM/alias failures are RESOURCE_BUSY, then exact same-key bytes are resubmitted after release. Completed GPIO replay is separate from the new GPIO probe.',
 'The original29 execution/15 configuration table grammars and row ceilings remain. Four resolver registrations are captured before effects.',
 'Resource transcript0.4 is explicit and mutually exclusive with old modes. Pure reader derives actor requests, historical compiler association, exact schedule, resolver identity and read-only paired phases.',
 'Targeted runtime assertions check independent progress,4 completions, historical idle while alias active, shared fences and zero final unresolved work. These do not substitute for the complete independent multi-actor folds.',
 'Two runtime cases, one pre-runtime refusal test,9 rehashed attacks and reader purity;30 matrix regression methods and39 old transcript methods selected.',
 'Runtime/provider/compiler source, all old fixtures and tests except exact matrix budget assertions unchanged. No physical/MCU/inference/live-service execution.'],
 independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Shared-resource capture candidate\n\nSee the [design](../DESIGN.md) and [source review](source-review.json).\nFour fixed actors and a separately declared GPIO exclusion probe share one\nboard/authority. This implements capture and targeted checks; complete independent\nmulti-actor semantics and full qualification remain unfinished.\n')
rows=[]
for p in sorted(S.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  if p.suffix=='.py':ast.parse(p.read_bytes())
  rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==8028;write(S/'index.json',dict(scope='Frozen shared-resource capture, explicit probe and independent request/schedule reader.',files=rows));pin=sha(S/'index.json')
assert sha(O/'index.json')=='c7de4e6813e4193ae0567ddc70e7a60921aecf820ef6f9ae3aada891a3f71013'
for row in read(O/'index.json')['files']:
 p=O/row['path'];assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes']
def methods(module,cls):
 tree=ast.parse((S/'project/tests'/(module+'.py')).read_bytes());c=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
 return sorted(module+'.'+cls+'.'+n.name for n in c.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
a=methods('test_pat_io_resource_challenge','IoResourceChallengeTests');b=methods('test_pat_io_combined_matrix','IoCombinedMatrixTests')
c=[v for v in read(O/'targets.json')['targets'] if v.startswith('test_pat_io_transcript.')]
assert len(a)==3 and len(b)==30 and len(c)==39
H=BASE/'harness01';H.mkdir();(H/'references').mkdir();borrowed=[]
for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
 p=O/item;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=72,targets=sorted(a+b+c)))
for item in ['run_attempt.py','attempt_child.py']:
 before=(O/item).read_text();after=before.replace('ClockChallenges46','ResourceChallenge72').replace('clock46','resource72').replace('io-clock-challenges','io-resource-challenge')
 after=after.replace('83df5455e2a0ecd21ccc2c9aeb42ffbcc80ba6f7dd2483ff4cb4ba44ad087f40',pin).replace('7076','8028').replace('7073','8025')
 after=after.replace('!= 46','!= 72').replace('== 46','== 72').replace("'expectedTests': 46","'expectedTests': 72")
 after=after.replace('test_pat_io_clock_challenges.IoClockChallengeTests.','test_pat_io_resource_challenge.IoResourceChallengeTests.')
 if item=='run_attempt.py':
  after=after.replace("for name in targets['targets']) != 7 or", "for name in targets['targets']) != 3 or\n                sum(name.startswith('test_pat_io_combined_matrix.IoCombinedMatrixTests.') for name in targets['targets']) != 30 or")
  after=after.replace('Six original clock runtime cases, one pre-runtime refusal and39 unchanged transcript methods','Two original shared-resource cases, one pre-runtime refusal,30 revised matrix and39 unchanged transcript methods')
 ast.parse(after);(H/item).write_text(after)
 (H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
(H/'README.md').write_text('# Isolated shared-resource selection\n\n[Exact72 methods](targets.json) from the [frozen candidate](../implementation01/README.md).\nSee [scope](SCOPE.md). Complete launcher/child diff review precedes execution.\n')
(H/'SCOPE.md').write_text('# Original boundaries\n\nTwo synthetic shared-board cases, one pre-runtime refusal,30 revised matrix and\n39 unchanged transcript methods. Preserve180s,16MiB scratch,8192 inventory files,\n256MiB input,16MiB file,4MiB JSON and8MiB log bounds. Only exact selected\nresource test/trial-0/state authority and board databases may connect.\nRetain original raw scratch and all failures. No network/subprocesses, physical\ndevices, MCU/emulator, inference or live services. Primary-agent review only;\nhelpers remain usage-limited. Full multi-actor semantics and qualification pending.\n')
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=8025,frozenFiles=8028,tests=72,targetSha256=sha(H/'targets.json'))))
