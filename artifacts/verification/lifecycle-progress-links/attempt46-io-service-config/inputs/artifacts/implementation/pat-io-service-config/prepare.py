"""Freeze trusted service configuration and exact inherited/new execution scopes."""
import ast,difflib,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-service-config';O=ROOT/'artifacts/implementation/pat-io-installation-reuse';S=B/'implementation01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,value):
 with p.open('x')as f:f.write(json.dumps(value,indent=2)+'\n')
def inventory(folder,rooted=False):
 rows=[]
 for p in folder.rglob('*'):
  assert not p.is_symlink()
  if p.is_file():
   if p.suffix=='.py':ast.parse(p.read_bytes())
   rows.append(dict(path=p.relative_to(ROOT if rooted else folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 return sorted(rows,key=lambda r:r['path'])
base=read(S/'baseline-inputs.json');assert sha(O/'implementation01/index.json')==base['sourceIndexSha256']=='0d4f87812d08c1ee4494cfa3e9ee117c0aca7b69827761e2a5053523c77622f8'
for r in read(O/'implementation01/index.json')['files']:assert sha(ROOT/r['path'])==r['sha256']
changed=[]
for r in base['inheritedProjectInputs']:
 rel=(ROOT/r['path']).relative_to(O/'implementation01/project')
 if sha(S/'project'/rel)!=r['sha256']:changed.append(rel.as_posix())
assert len(base['inheritedProjectInputs'])==240 and changed==['supervisor/supervisor_contracts.py']
before=(O/'implementation01/project'/changed[0]).read_text();after=(S/'project'/changed[0]).read_text()
def without_closure(text):
 return [ast.dump(n)for n in ast.parse(text).body if not(isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='SOURCE_FILES'for t in n.targets))]
assert without_closure(before)==without_closure(after)
(B/'source-closure.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='previous/'+changed[0],tofile='configured/'+changed[0])))
module='test_io_service_configuration';tree=ast.parse((S/'project/tests'/ (module+'.py')).read_bytes())
def methods(cls):
 node=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name==cls)
 return sorted(module+'.'+cls+'.'+n.name for n in node.body if isinstance(n,ast.FunctionDef)and n.name.startswith('test_'))
controls=methods('IoServiceConfigurationTests');process=methods('IoConfiguredProcessTests');assert len(controls)==21 and len(process)==1
assert len(inventory(S/'project'))==242
reviewed=[
 '239 inherited project files unchanged. Only existing production delta adds io_services.py to SOURCE_FILES; all other AST nodes in supervisor_contracts remain identical. New original service module and test module. Every Python source AST parsed without project execution.',
 'Closed64KiB configuration, exact integer/type checks before JCS can erase distinctions, explicit registrations/artifact assignments/challenge mappings and original lowered-only limits. No command/import/callback/URL/result/claimed code attestation.',
 'Current installation/source-derived pin includes service module in supervisor identity/image. Expected external pin required on reconstruction. Fresh complete descriptor snapshot required per run; no cached current authority or source identity.',
 'Historical reader requires external pin, run ID and request digest; canonical configuration and pin, exact original bundle/request association, no source reads/replanning. Rehashed replacements conflict with retained digest.',
 'No service SQL, worker launch, authority installation or promotion is implemented by preparation. Actual configured test durably retains configuration/pin/digest before supervisor construction, then uses unchanged owned worker, full independent group reader and replay/conflict checks.',
 'Exact206 controls: inherited185 plus21 pure configuration controls. Original nine process scopes unchanged; one configured process added under the same fixed-worker/SQL paths and180s outer deadline. Group/owned deadline60s and all existing limits unchanged.',
 'Primary-agent review only. No physical/MCU/emulator/acquired-controller/live-inference/service/adjacent-Harness execution. Raw failures preserved, no corrupt reset, no new key for old mutations, no quota or public qualification claim.'
]
write(S/'source-review.json',dict(scope='Trusted finite I/O service preparation and anchored replay',changedInheritedFiles=changed,unchangedInheritedFiles=239,newProjectFiles=2,reviewed=reviewed,independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Trusted I/O service configuration\n\n[Design](../DESIGN.md), [source review](source-review.json). Authority persistence and public mounting remain unfinished.\n')
rows=inventory(S,True);assert len(rows)==245;write(S/'index.json',dict(scope='Frozen service preparation, closure addition and22 new tests.',files=rows));pin=sha(S/'index.json')
for i in range(1,12):
 prior=O/('harness%02d'%(i if i<=10 else 2))
 for r in read(prior/'index.json')['files']:assert sha(prior/r['path'])==r['sha256']
 oldtargets=read(prior/'targets.json')['targets'];targets=oldtargets+controls if i==1 else process if i==11 else oldtargets
 count=len(targets);assert count==(206 if i==1 else 1)
 H=B/('harness%02d'%i);H.mkdir();(H/'references').mkdir();borrowed=[]
 for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
  p=prior/name;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=count,targets=targets))
 for name in ('run_attempt.py','attempt_child.py'):
  original=(prior/name).read_text();updated=original.replace(base['sourceIndexSha256'],pin).replace(O.name,B.name)
  updated=re.sub(r'\b243\b','245',updated);updated=re.sub(r'\b240\b','242',updated)
  if i==1:updated=re.sub(r'\b185\b','206',updated)
  if name=='run_attempt.py':
   assert updated.count(repr(oldtargets))==1;updated=updated.replace(repr(oldtargets),repr(targets))
  if i==11:updated=updated.replace(oldtargets[0].rsplit('.',1)[1],targets[0].rsplit('.',1)[1])
  updated=updated.replace('installation185','service206').replace('Installation185','Service206').replace('installation1','service1').replace('Installation1','Service1')
  ast.parse(updated);(H/name).write_text(updated)
  (H/(name+'.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),fromfile=str((prior/name).relative_to(ROOT)),tofile=str((H/name).relative_to(ROOT)))))
 scope='Control206: unchanged185 plus21 pure service-configuration tests.'if i==1 else'Configured original owned worker1.'if i==11 else'Unchanged original process recovery1.'
 (H/'SCOPE.md').write_text('# Exact execution scope\n\n'+scope+'\n\n[Design](../DESIGN.md), [targets](targets.json). Original SQL/launch/retention/deadline bounds.\n')
 (H/'README.md').write_text('# Configured I/O checks\n\n[Scope](SCOPE.md), [targets](targets.json), [source](../implementation01/README.md).\n')
 review=read(prior/'review.json');review.update(scope=scope,tests=count,sourceIndexSha256=pin,targetSha256=sha(H/'targets.json'),reviewed=reviewed,inheritedHarnessIndexSha256=sha(prior/'index.json'))
 write(H/'review.json',review);write(H/'index.json',dict(scope=scope,files=inventory(H)))
 print(json.dumps(dict(harness=H.name,tests=count,indexSha256=sha(H/'index.json'))))
print(json.dumps(dict(projectFiles=242,frozenFiles=245,sourceIndexSha256=pin)))
