"""Freeze original pure lifecycle composition and one bounded exact selection."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-lifecycle-semantics';S=B/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-lifecycle-challenges/implementation01/project'
O=ROOT/'artifacts/implementation/pat-io-authority-semantics/harness01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
base=read(S/'baseline-inputs.json')
for r in base['inheritedProjectInputs']:
 p=ROOT/r['path'];q=S/'project'/p.relative_to(OLD)
 assert sha(p)==sha(q)==r['sha256'] and p.stat().st_size==q.stat().st_size==r['bytes']
for r in base['excludedFixtureInputs']:
 p=ROOT/r['path'];assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes'] and not (S/'project'/p.relative_to(OLD)).exists()
fixture=S/'project/tests/data/io-lifecycle'
for r in read(fixture/'index.json')['files']:
 p=ROOT/r['source'];q=fixture/r['path'];assert sha(p)==sha(q)==r['sha256'] and p.stat().st_size==q.stat().st_size==r['bytes']
write(S/'source-review.json',dict(scope='Primary-agent complete pure lifecycle composition, acquired fixture closure and new tests reviewed before execution.',
 inheritedInputsUnchanged=5088,changedFiles=[],excludedFixtureFiles=3013,newLifecycleFixtureFiles=2665,
 newFiles=['hms/pat_io_lifecycle_semantics.py','tests/test_pat_io_lifecycle_semantics.py'],
 reviewed=['All20 real fixed captures use unchanged partial exact artifact/schedule/lowering/grant checks and all original semantic folds; no caller-supplied fold verdicts.',
 'Fault list is independently closed per named case, with one exact trusted phase/point/code/occurrence. Unknown events must arise at the single declared cut or pending new-owner reopen.',
 'Before-call, before-reopen and final execution snapshots cannot mutate state. Completed receipt retention and held claims survive authority loss and restart until exact reconciliation.',
 'Pending begin loss uses original independently derived reconciliation-stop context. New-owner stop and accepted no-handoff recovery use original epoch/receipt and operation semantics.',
 'Configuration decisions, full static timing, every receipt/effect/fence, operation/parent event, sample and reply are joined. Exact final inventory/effects/state and no suffix are required.',
 'Completion of one historical child does not satisfy a canceled two-step parent; only the single-step after-completion withdrawal case satisfies its completion objective.',
 '57 methods:20 primitive/case positives and37 adversarial/compatibility/purity methods. Rehashed altered receipts, events, claims/floors, sample clocks, bindings, reports and trusted fault plans refuse.',
 'All5088 inherited files unchanged. Explicit3013 obsolete fixture exclusions and2665 lifecycle fixture additions preserve8192 ceiling and original immutable archives.',
 'Pure checker imports only original independent history components. Every SQL/network/subprocess/device/runtime execution is prohibited in the selected child; all original harness bounds remain.',
 'Current candidate matrix, attestation, aggregate quotas, public qualification and physical/driver/hub controls remain false or unfinished.'],
 independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Complete fixed lifecycle histories\n\nSee [design](../DESIGN.md) and [source review](source-review.json).\nThe pure composition validates20 retained GPIO/PWM histories against separately\ntrusted setup and fault/authority schedules. Full qualification remains unfinished.\nThe explicit closure excludes3013 obsolete fixture files and adds2665 lifecycle\nfixture files without changing original evidence or the8192-file ceiling.\n')
rows=[]
for p in sorted(S.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  if p.suffix=='.py':ast.parse(p.read_bytes())
  rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==7758
write(S/'index.json',dict(scope='Frozen pure complete fixed lifecycle composition and explicit original fixture closure.',files=rows));pin=sha(S/'index.json')
assert sha(O/'index.json')=='6d1be4d34dbae08a867712bfd736a50a012bbf17360edcf3d796f910a15f73c1'
for r in read(O/'index.json')['files']:
 p=O/r['path'];assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes']
module='test_pat_io_lifecycle_semantics';cls='IoLifecycleSemanticsTests'
tree=ast.parse((S/'project/tests'/(module+'.py')).read_bytes());node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
targets=sorted(module+'.'+cls+'.'+n.name for n in node.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'));assert len(targets)==57
H=B/'harness01';H.mkdir();(H/'references').mkdir();borrowed=[]
for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
 p=O/item;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=57,targets=targets))
for item in ['run_attempt.py','attempt_child.py']:
 before=(O/item).read_text();after=before.replace('io-authority-semantics','io-lifecycle-semantics').replace('56f5beaad09b6fd4233f07c403c9d3716fa6c664ae3899e905347cd9005a95f7',pin)
 after=after.replace('8101','7758').replace('8098','7755').replace('AuthorityHistory34','LifecycleHistory57').replace('authority34','lifecycle57')
 after=after.replace('test_pat_io_authority_semantics.','test_pat_io_lifecycle_semantics.').replace('!= 34','!= 57').replace('== 34','== 57').replace("'expectedTests': 34","'expectedTests': 57")
 after=after.replace('34 exact pure authority/regression tests','57 exact pure lifecycle semantic tests').replace('Pure authority history','Pure lifecycle history')
 ast.parse(after);(H/item).write_text(after)
 (H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
(H/'README.md').write_text('# Pure lifecycle57 selection\n\n[Exact methods](targets.json), [frozen source](../implementation01/README.md),\nand [scope](SCOPE.md). Complete launcher/child diff review precedes execution.\n')
(H/'SCOPE.md').write_text('# Original pure execution boundaries\n\n57 exact methods; no SQL, network, subprocess, runtime, physical/MCU, inference\nor live-service execution. Preserve original180s,16MiB scratch,8192 inventory\nfiles,256MiB inputs,16MiB file,4MiB JSON and8MiB log bounds. The explicit\nfixture closure excludes3013 obsolete files and adds2665 lifecycle files.\nOriginal sealed evidence remains. Retain raw scratch and every attempt.\nPrimary-agent review only. Full candidate qualification remains unfinished.\n')
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=7755,frozenFiles=7758,tests=57,targetSha256=sha(H/'targets.json'))))
