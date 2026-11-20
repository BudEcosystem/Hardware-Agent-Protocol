"""Freeze test-only rehash correction after retaining the complete failed57 attempt."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-lifecycle-semantics';S=B/'implementation02';O=B/'harness01';OLD=B/'implementation01/project'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
proof=read(B/'results/attempt01-failed57/proof.json');assert proof['counts']==dict(testsRun=57,failures=0,errors=7,skips=0,expectedFailures=0,unexpectedSuccesses=0)
changed=[]
for r in read(S/'baseline-inputs.json')['inheritedProjectInputs']:
 p=ROOT/r['path'];q=S/'project'/p.relative_to(OLD)
 assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes']
 if sha(q)!=r['sha256'] or q.stat().st_size!=r['bytes']:changed.append(p.relative_to(OLD).as_posix())
assert changed==['tests/test_pat_io_lifecycle_semantics.py']
a=OLD/changed[0];z=S/'project'/changed[0]
(B/'test-only-correction.patch').write_text(''.join(difflib.unified_diff(a.read_text().splitlines(True),z.read_text().splitlines(True),fromfile=a.relative_to(ROOT).as_posix(),tofile=z.relative_to(ROOT).as_posix())))
write(B/'DIAGNOSIS.json',dict(scope='Seven test-construction errors in failed57; all20 actual-history positives pass.',
 attempt='results/attempt01-failed57',proofSha256=sha(B/'results/attempt01-failed57/proof.json'),counts=proof['counts'],
 causes={'PAT_IO_TRANSCRIPT_DUPLICATE_PAGE':['active_board_owners_cannot_disappear','resource_floor_cannot_disappear','terminal_authority_receipt_cannot_be_missing','unknown_cannot_release_all_claims'],
 'PAT_IO_CORRESPONDENCE_LOWERING_EFFECT':['hidden_independent_effect_cannot_be_added'],
 'PAT_IO_CORRESPONDENCE_LOWERING_ADMITTED_WORK':['declined_parent_cannot_allocate_resource_floor'],
 'PAT_IO_TRANSCRIPT_CELL':['second_step_cannot_alias_the_first_child']},
 correction='New test-only checkpoint rewriter regenerates/deduplicates typed pages, all references and paired sidecar accounting. Seven edits target post-lowering states. Original structural-success precondition and semantic-refusal assertion retained. One new six-case byte-exact no-op rewriter test.',
 productionChanged=False,oldMalformedRecordsAccepted=False,limitsChanged=False,testCountAfter=58))
write(S/'source-review.json',dict(scope='Primary-agent test-only correction reviewed against exact retained failures before execution.',
 inheritedInputsUnchanged=7754,changedFiles=changed,newProjectFiles=[],
 reviewed=['Production lifecycle composition and every original dependency/fixture are byte-identical to source01. All20 real histories passed in failed57.',
 'Seven adversaries failed their preliminary structural/correspondence success assertion. Four collapsed unique pages, two changed lower-stage state, one retained a null cell tag after inserting text.',
 'Test-only checkpoint writer uses original schema types, canonical row ordering, page deduplication, sequential names, exact reference rehashing, updated observations and configuration sidecar joins.',
 'Claim/owner/floor/receipt removals and suffix aliases now target specific post-lowering states; hidden effects are introduced only after activation. Lowering stays unchanged.',
 'All seven methods still require the partial exact transcript reader to pass before full semantic refusal. One new six-case no-op byte equality method checks the rewriter itself.',
 '58 methods, unchanged original180s/16MiB/8192-file and all other bounds; no runtime, SQL, network, subprocess, physical/MCU/inference/live-service execution.'],
 independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Test-only lifecycle correction\n\nSee [diagnosis](../DIAGNOSIS.json), [exact correction](../test-only-correction.patch)\nand [source review](source-review.json). The production checker and all7754\nother project files are unchanged. Seven adversarial constructions now preserve\nstructural validity; one new byte-exact no-op rewriter method brings the total\nto58. Original source01 and failed57 remain retained. Full qualification pending.\n')
rows=[]
for p in sorted(S.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  if p.suffix=='.py':ast.parse(p.read_bytes())
  rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==7758
write(S/'index.json',dict(scope='Test-only lifecycle adversary construction correction; production and all existing fixtures unchanged.',files=rows));pin=sha(S/'index.json')
assert sha(O/'index.json')=='153ababfe7ee1fb2aace6589022e7fe28c074b85b872777b91964184cbf02696'
for r in read(O/'index.json')['files']:
 p=O/r['path'];assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
tree=ast.parse(z.read_bytes());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef));targets=sorted('test_pat_io_lifecycle_semantics.IoLifecycleSemanticsTests.'+n.name for n in cls.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'));assert len(targets)==58
H=B/'harness02';H.mkdir();(H/'references').mkdir();borrowed=[]
for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
 p=O/item;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=58,targets=targets))
for item in ['run_attempt.py','attempt_child.py']:
 before=(O/item).read_text();after=before.replace('14e731f9e5fa81ce78d663049e9d54326e5511411dc42ceee7930672c388067e',pin).replace('implementation01','implementation02')
 after=after.replace('LifecycleHistory57','LifecycleHistory58').replace('lifecycle57','lifecycle58').replace('!= 57','!= 58').replace('== 57','== 58').replace("'expectedTests': 57","'expectedTests': 58")
 ast.parse(after);(H/item).write_text(after)
 (H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
(H/'README.md').write_text('# Pure lifecycle58 selection\n\n[Exact methods](targets.json), [corrected source](../implementation02/README.md),\nand [scope](SCOPE.md). Complete launcher/child diff review precedes execution.\n')
(H/'SCOPE.md').write_text('# Original pure execution boundaries\n\n58 exact methods after test-only correction. Every SQL/network/subprocess and\nphysical/MCU/inference/live-service operation is forbidden. Original180s,16MiB\nscratch,8192 input files,256MiB inputs,16MiB file,4MiB JSON and8MiB log\nbounds unchanged. Preserve every original source/attempt/raw scratch tree.\nPrimary-agent review only. Full current-candidate qualification remains pending.\n')
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=7755,frozenFiles=7758,tests=58,targetSha256=sha(H/'targets.json'))))
