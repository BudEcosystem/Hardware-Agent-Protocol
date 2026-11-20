"""Freeze original authority semantic composition and four bounded pure selections."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-authority-semantics';S=B/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-authority-challenges/implementation01/project'
O=ROOT/'artifacts/implementation/pat-io-resource-semantics/harness01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
changed=[]
for r in read(S/'baseline-inputs.json')['inheritedProjectInputs']:
 p=ROOT/r['path'];assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes'];q=S/'project'/p.relative_to(OLD)
 if sha(q)!=r['sha256'] or q.stat().st_size!=r['bytes']:changed.append(p.relative_to(OLD).as_posix())
assert set(changed)=={'hms/pat_io_configuration_history.py','hms/pat_io_observation_history.py','hms/pat_io_operation_history.py','hms/pat_io_procedure_history.py'}
write(S/'source-review.json',dict(scope='Primary-agent pure authority/binding composition and all four shared private-fold diffs reviewed before execution.',
 inheritedInputsUnchanged=7079,changedFiles=sorted(changed),excludedResourceFixtures=585,newAuthorityFixtureFiles=1013,
 newFiles=['hms/pat_io_authority_semantics.py','tests/test_pat_io_authority_semantics.py'],
 reviewed=['Closed structural/request inspection precedes independent trusted authority-change validation and exact revision, grant or binding transitions.',
 'The inactive set is derived only from the authorized declared invalidation. Static binding documents/history remain exact, target presence disappears and endpoint/session/sample history stays cached through reopen.',
 'Initial and later admissions/dispatches require current permissions and active bindings; the original inactive probe is unreserved, distinct and budgeted. Public read/replay/namespace refusals require empty grants.',
 'Before-call and final snapshots cannot introduce changes. Administrative change calls mutate only the declared configuration tables and no execution table.',
 'Unchanged board fold and extended private operation/procedure folds derive effects, unknown/held ownership, historical stop, reconciliation, exact cancellation replies, final privileged status and no suffix.',
 'Default readers retain old behavior and unsupported-case refusal. New private contexts are consumed exactly; full grant withdrawal does not fabricate public read authority.',
 '34 new tests include six real retained cases, coherent false grants/presence/receipts, changed samples/epochs/revisions, operation/parent/report forgeries, old-profile refusal and purity.',
 '72 operation/procedure,48 configuration and27 observation regressions selected. All original tests and old retained fixtures except585 resource-only input exclusions are unchanged.',
 'No runtime/provider/compiler/producer changes, no SQL/device execution. Current attestation, aggregate quotas and complete candidate qualification remain false.'],
 independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Independent authority/binding composition\n\nSee [design](../DESIGN.md) and [source review](source-review.json).\nThe pure checker derives complete fixed histories from trusted setup/change\ninputs and acquired records. Full candidate qualification remains unfinished.\nThe explicit closure excludes585 resource-only fixtures and adds1013 authority\nfixture files while preserving the original8192-file ceiling.\n')
rows=[]
for p in sorted(S.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  if p.suffix=='.py':ast.parse(p.read_bytes())
  rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==8101
write(S/'index.json',dict(scope='Frozen pure authority/binding composition and explicit original fixture closure.',files=rows));pin=sha(S/'index.json')
assert sha(O/'index.json')=='9db0613dd63c4afefdcc9a431e50b43424e96032a60b4a7635b0c17bd0a0d9a1'
for r in read(O/'index.json')['files']:
 p=O/r['path'];assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes']
def methods(module,cls):
 tree=ast.parse((S/'project/tests'/(module+'.py')).read_bytes());c=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
 return sorted(module+'.'+cls+'.'+n.name for n in c.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
specs=[ [('test_pat_io_authority_semantics','IoAuthoritySemanticsTests',34)],
 [('test_pat_io_operation_history','IoOperationHistoryTests',38),('test_pat_io_procedure_history','IoProcedureHistoryTests',34)],
 [('test_pat_io_configuration_history','IoConfigurationHistoryTests',48)],
 [('test_pat_io_observation_history','IoObservationHistoryTests',27)] ]
for number,spec in enumerate(specs,1):
 targets=[]
 for module,cls,n in spec:
  chosen=methods(module,cls);assert len(chosen)==n;targets+=chosen
 targets.sort();count=len(targets);H=B/('harness%02d'%number);H.mkdir();(H/'references').mkdir();borrowed=[]
 for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
  p=O/item;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=count,targets=targets))
 for item in ['run_attempt.py','attempt_child.py']:
  before=(O/item).read_text();after=before.replace('io-resource-semantics','io-authority-semantics').replace('045897b786682b0e676a376e1292bd86309f22bd9a73744fd86e9df841e7c639',pin)
  after=after.replace('7668','8101').replace('7665','8098').replace('ResourceHistory31','AuthorityHistory'+str(count)).replace('resource31','authority'+str(count)).replace('Pure resource history','Pure authority history')
  selector="sum(name.startswith('test_pat_io_resource_semantics.') for name in targets['targets']) != 31"
  replacement=' or\n                '.join("sum(name.startswith('"+module+".') for name in targets['targets']) != "+str(n)for module,cls,n in spec)
  after=after.replace(selector,replacement)
  after=after.replace('!= 31','!= '+str(count)).replace('== 31','== '+str(count)).replace("'expectedTests': 31","'expectedTests': "+str(count))
  after=after.replace('31 original pure resource semantic tests',str(count)+' exact pure authority/regression tests')
  ast.parse(after);(H/item).write_text(after)
  (H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
 (H/'README.md').write_text('# Pure authority selection '+str(count)+'\n\n[Exact methods](targets.json), [frozen source](../implementation01/README.md),\nand [scope](SCOPE.md). Complete launcher/child diff review precedes execution.\n')
 (H/'SCOPE.md').write_text('# Original pure execution boundaries\n\n'+str(count)+' exact methods; no SQL, network, subprocess, runtime, physical/MCU,\ninference or live-service execution. Preserve original180s,16MiB scratch,8192\ninventory files,256MiB inputs,16MiB file,4MiB JSON and8MiB log bounds.\nThe explicit fixture closure excludes585 resource files and adds1013 authority\nfiles. Original sealed evidence remains. Retain raw scratch and every attempt.\nPrimary-agent review only. Full candidate qualification remains unfinished.\n')
 print(json.dumps(dict(harness=H.name,tests=count,targetSha256=sha(H/'targets.json'))))
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=8098,frozenFiles=8101)))
