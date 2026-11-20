"""Freeze reviewed fixed lifecycle worker/reader/tests and four exact selections."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-lifecycle-challenges';S=B/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-authority-semantics/implementation01/project'
O=ROOT/'artifacts/implementation/pat-io-authority-challenges/harness01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
for r in read(S/'baseline-inputs.json')['inheritedProjectInputs']:
 p=ROOT/r['path'];q=S/'project'/p.relative_to(OLD)
 assert sha(p)==sha(q)==r['sha256'] and p.stat().st_size==q.stat().st_size==r['bytes']
write(S/'source-review.json',dict(scope='Primary-agent original lifecycle/runtime paths and all three new modules reviewed before execution.',
 inheritedInputsUnchanged=8098,changedFiles=[],newFiles=['hms/pat_io_lifecycle_capture.py','hms/pat_io_lifecycle_history.py','tests/test_pat_io_lifecycle_challenges.py'],
 reviewed=['Original matrix0.3 is validated before runtime construction; only ten fixed cases, no new policy/input/operation/time ceilings.',
 'Exact original lower request and keys are retained across reopen; accepted work/stale suffix resume refuse without replacement mutation keys.',
 'Loss injection wraps original board.begin after commit or original journal.record_execution before authority settlement; the original bound method is restored in finally. One occurrence is required and retained.',
 'Invocation withdrawal grants read then removes wildcard admin at exact before-call boundary; no rescue grants or invocations.',
 'New pure reader independently reconstructs the complete fixed artifact/case, exact calls/clocks/reopen/failure schedule, original lowering, trusted grant snapshots and no-change public refusals.',
 'Reader explicitly does not claim full semantic history, independent outcome, attestation, aggregate quotas or qualification; fault causes need subsequent independent composition.',
 'Twenty actual primitive/case trials assert exact receipts/effects, terminal and unknown states, retained claims, idle release, new session, immutable requests and absent suffix.',
 'Ten GPIO cases each include three coherent/rehash refusals and an I/O/clock purity check. One additional pre-runtime refusal method. All inherited files unchanged.',
 'Four disjoint5-case selections, first with extra pure refusal; original180s/16MiB/8192 file and all other harness/trial bounds unchanged. No physical/MCU/inference/live-service execution.'],
 independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Fixed lifecycle capture candidate\n\nSee [design](../DESIGN.md) and [source review](source-review.json).\nTwenty original synthetic cases and a pure exact-request/schedule reader.\nComplete independent outcome composition and full qualification remain pending.\n')
rows=[]
for p in sorted(S.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  if p.suffix=='.py':ast.parse(p.read_bytes())
  rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==8104
write(S/'index.json',dict(scope='Frozen fixed lifecycle captures and pure partial reader; original inherited closure unchanged.',files=rows));pin=sha(S/'index.json')
assert sha(O/'index.json')=='74e95d69cbfbc56e1145f6e1ffe1f1c6c162f9774e0fb9b57ba80add1843e3eb'
for r in read(O/'index.json')['files']:
 p=O/r['path'];assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes']
prefix='test_pat_io_lifecycle_challenges.IoLifecycleChallengeTests.'
first=['cancel_accepted','cancel_pending','reopen_accepted','reopen_pending','completion_reply_lost']
second=['pending_reply_lost','permission_before_parent','permission_before_dispatch','permission_pending','permission_after_completion']
specs=[('gpio',first,True),('pwm',first,False),('gpio',second,False),('pwm',second,False)]
allchosen=[]
for number,(primitive,names,extra) in enumerate(specs,1):
 targets=[prefix+'test_'+primitive+'_'+name for name in names]
 if extra:targets.append(prefix+'test_invalid_matrix_or_unsupported_case_refuses_before_runtime')
 targets.sort();allchosen+=targets;count=len(targets);H=B/('harness%02d'%number);H.mkdir();(H/'references').mkdir();borrowed=[]
 for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
  p=O/item;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=count,targets=targets))
 for item in ['run_attempt.py','attempt_child.py']:
  before=(O/item).read_text();after=before.replace('io-authority-challenges','io-lifecycle-challenges').replace('709cbe3024ba8b08dacc601b24b06e1e9a105c1fc2d94958ff29c9c0dd0d0d79',pin)
  after=after.replace('7671','8104').replace('7668','8101').replace('AuthorityChallenge76','LifecycleChallenge'+str(count)).replace('authority76','lifecycle'+str(count))
  after=after.replace('test_pat_io_authority_challenges.IoAuthorityChallengeTests.','test_pat_io_lifecycle_challenges.IoLifecycleChallengeTests.')
  selector="sum(name.startswith('test_pat_io_lifecycle_challenges.IoLifecycleChallengeTests.') for name in targets['targets']) != 7 or\n                sum(name.startswith('test_pat_io_combined_matrix.IoCombinedMatrixTests.') for name in targets['targets']) != 30 or\n                sum(name.startswith('test_pat_io_transcript.') for name in targets['targets']) != 39"
  replacement="targets['targets'] != "+repr(targets)
  if item=='run_attempt.py':assert selector in after;after=after.replace(selector,replacement)
  after=after.replace('!= 76','!= '+str(count)).replace('== 76','== '+str(count)).replace("'expectedTests': 76","'expectedTests': "+str(count))
  after=after.replace('Six original authority/binding cases, one pre-runtime refusal,30 revised matrix and39 unchanged transcript methods','Five original fixed lifecycle cases'+(', one pre-runtime refusal' if extra else ''))
  ast.parse(after);(H/item).write_text(after)
  (H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
 (H/'README.md').write_text('# Bounded lifecycle selection '+str(number)+'\n\n[Exact methods](targets.json), [frozen source](../implementation01/README.md),\nand [scope](SCOPE.md). Full launcher/child diff review precedes execution.\n')
 (H/'SCOPE.md').write_text('# Original execution boundaries\n\nFive actual synthetic lifecycle cases'+(' and one pre-runtime refusal' if extra else '')+'.\nOriginal180s,16MiB scratch,8192 inventory files,256MiB inputs,16MiB file,4MiB\nJSON and8MiB log bounds. SQL only for selected lifecycle methods under exact\ntrial-0/state authority and board paths. No network/subprocesses, physical/MCU,\ninference or live services. Preserve original raw state and every attempt.\nPrimary-agent review only. Full independent semantic composition and qualification pending.\n')
 print(json.dumps(dict(harness=H.name,tests=count,targetSha256=sha(H/'targets.json'))))
tree=ast.parse((S/'project/tests/test_pat_io_lifecycle_challenges.py').read_bytes());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
assert sorted(allchosen)==sorted(prefix+n.name for n in cls.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')) and len(set(allchosen))==21
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=8101,frozenFiles=8104)))
