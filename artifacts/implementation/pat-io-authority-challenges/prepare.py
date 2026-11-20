"""Freeze reviewed authority capture and prepare original bounded harness."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-authority-challenges';S=B/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-resource-semantics/implementation01/project'
O=ROOT/'artifacts/implementation/pat-io-resource-challenge/harness01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
changed=[]
for r in read(S/'baseline-inputs.json')['inheritedProjectInputs']:
 p=ROOT/r['path'];assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes'];rel=p.relative_to(OLD);q=S/'project'/rel
 if sha(q)!=r['sha256'] or q.stat().st_size!=r['bytes']:changed.append(rel.as_posix())
assert set(changed)=={'hms/pat_io_combined_matrix.py','hms/pat_io_transcript.py','tests/test_pat_io_combined_matrix.py'}
write(S/'source-review.json',dict(scope='Primary-agent original runtime/authority paths, new capture/reader/tests and source delta reviewed before execution.',
 inheritedInputsUnchanged=7662,changedFiles=sorted(changed),newFiles=['hms/pat_io_authority_capture.py','hms/pat_io_authority_history.py','tests/test_pat_io_authority_challenges.py'],
 reviewed=['Registry invalidation retains old binding, deletes presence and bumps revision. Historical catalog recovery does not require current grants.',
 'Original ProcedureStore owner cancellation is allowed without public read and cannot authorize a new effect. Full withdrawal removes the only grant; no rescue grant.',
 'Matrix0.3 declares the separate original binding probe before effects and reserves3 rather than2 possible admissions.44/59 global totals; all ceilings unchanged.',
 'New0.5 grammar is explicitly opt-in and mutually exclusive with all old modes. Real reopen resolver refusal has null current environment and cannot rebind the old request.',
 'Privileged internal final observation is explicitly labeled. Eight actual public read/replay/namespace denials span full withdrawal and recovery.',
 'Pure reader reconstructs fixed case, exact initial lowering, immutable predeclared probe, resolver identity, schedule, reopen phase and read-only denial pairs. It makes no complete semantic/outcome claim.',
 'Six real GPIO/PWM scenarios plus pre-runtime refusal test. Targeted runtime assertions cover exact one-child effects, held claims through unknown, historical stop, unchanged bindings and no suffix.15 rehashed attacks plus purity.',
 'All runtime/provider/compiler source and all inherited fixtures remain unchanged. Three changed files and three new files; no physical/MCU/inference/live-service execution.'],
 independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Authority/binding capture candidate\n\nSee [design](../DESIGN.md) and [source review](source-review.json).\nFixed captures and request/schedule checks precede a complete independent\nauthority/binding semantic fold. Full qualification remains unfinished.\n')
rows=[]
for p in sorted(S.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  if p.suffix=='.py':ast.parse(p.read_bytes())
  rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==7671
write(S/'index.json',dict(scope='Frozen binding/full authority capture candidate with original source closure.',files=rows));pin=sha(S/'index.json')
assert sha(O/'index.json')=='11c107abb92e286e2f07649be5117370cccc61cc7c3b92472ecd4f371698ec8b'
for r in read(O/'index.json')['files']:
 p=O/r['path'];assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes']
def methods(module,cls):
 tree=ast.parse((S/'project/tests'/(module+'.py')).read_bytes());node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
 return sorted(module+'.'+cls+'.'+n.name for n in node.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
a=methods('test_pat_io_authority_challenges','IoAuthorityChallengeTests');b=methods('test_pat_io_combined_matrix','IoCombinedMatrixTests')
c=[v for v in read(O/'targets.json')['targets'] if v.startswith('test_pat_io_transcript.')]
assert len(a)==7 and len(b)==30 and len(c)==39
H=B/'harness01';H.mkdir();(H/'references').mkdir();borrowed=[]
for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
 p=O/item;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=76,targets=sorted(a+b+c)))
for item in ['run_attempt.py','attempt_child.py']:
 before=(O/item).read_text();after=before.replace('ResourceChallenge72','AuthorityChallenge76').replace('resource72','authority76').replace('io-resource-challenge','io-authority-challenges')
 after=after.replace('1f86626a0ea1c298b23065505c6728c0e73679269b4b642536fa4f7669cf1f6c',pin).replace('8028','7671').replace('8025','7668')
 after=after.replace('!= 72','!= 76').replace('== 72','== 76').replace("'expectedTests': 72","'expectedTests': 76")
 after=after.replace('test_pat_io_resource_challenge.IoResourceChallengeTests.','test_pat_io_authority_challenges.IoAuthorityChallengeTests.')
 if item=='run_attempt.py':after=after.replace("for name in targets['targets']) != 3 or","for name in targets['targets']) != 7 or").replace('Two original shared-resource cases, one pre-runtime refusal','Six original authority/binding cases, one pre-runtime refusal')
 ast.parse(after);(H/item).write_text(after)
 (H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
(H/'README.md').write_text('# Bounded authority challenge selection\n\n[Exact76 methods](targets.json), [frozen source](../implementation01/README.md),\nand [scope](SCOPE.md). Full launcher/child diff review precedes execution.\n')
(H/'SCOPE.md').write_text('# Original execution boundaries\n\nSix actual synthetic binding/authority cases, one pre-runtime refusal,30 matrix\nand39 unchanged transcript methods. Original180s,16MiB scratch,8192 inventory\nfiles,256MiB inputs,16MiB file,4MiB JSON and8MiB log bounds. SQL only for\nselected authority tests under exact trial-0/state authority and board paths.\nNo network/subprocesses, physical/MCU execution, inference or live services.\nPreserve original raw state and every attempt. Primary-agent review only.\nComplete independent binding/authority semantics and full qualification pending.\n')
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=7668,frozenFiles=7671,tests=76,targetSha256=sha(H/'targets.json'))))
