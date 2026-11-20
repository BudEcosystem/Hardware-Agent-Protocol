"""Static review and freeze; no project imports or execution."""
import ast,difflib,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path.cwd(); B=ROOT/'artifacts/implementation/pat-io-service-authority'; O=ROOT/'artifacts/implementation/pat-io-service-config'; S=B/'implementation01'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x') as f: f.write(json.dumps(v,indent=2)+'\n')
def inventory(folder,rooted=False):
 rows=[]
 for p in folder.rglob('*'):
  assert not p.is_symlink()
  if p.is_file():
   if p.suffix=='.py': ast.parse(p.read_bytes())
   rows.append(dict(path=p.relative_to(ROOT if rooted else folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 return sorted(rows,key=lambda r:r['path'])
base=read(S/'baseline-inputs.json'); assert sha(O/'implementation01/index.json')==base['sourceIndexSha256']=='a242d84d16919fe15da783397642d1ae7ed9b07cc14a4a5ce1de78ebabae3f65'
for r in read(O/'implementation01/index.json')['files']: assert sha(ROOT/r['path'])==r['sha256']
changed=[]
for r in base['inheritedProjectInputs']:
 rel=(ROOT/r['path']).relative_to(O/'implementation01/project')
 if sha(S/'project'/rel)!=r['sha256']: changed.append(rel.as_posix())
assert len(base['inheritedProjectInputs'])==242 and changed==['hms/pat_io_bindings.py','supervisor/io_services.py','supervisor/supervisor_contracts.py']
patches=[]
for rel in changed:
 before=(O/'implementation01/project'/rel).read_text();after=(S/'project'/rel).read_text()
 patches.append(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='previous/'+rel,tofile='authority/'+rel)))
(B/'source.patch').write_text(''.join(patches))
def nodes_without(text,field):
 return [ast.dump(n) for n in ast.parse(text).body if not(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==field for t in n.targets))]
rel='supervisor/supervisor_contracts.py'
assert nodes_without((O/'implementation01/project'/rel).read_text(),'SOURCE_FILES')==nodes_without((S/'project'/rel).read_text(),'SOURCE_FILES')
rel='hms/pat_io_bindings.py'
old=ast.parse((O/'implementation01/project'/rel).read_bytes());new=ast.parse((S/'project'/rel).read_bytes())
for node in new.body:
 if isinstance(node,ast.ClassDef) and node.name=='IoRegistryPatBindings': node.body=[n for n in node.body if not(isinstance(n,ast.FunctionDef) and n.name=='configured_snapshot')]
assert ast.dump(old)==ast.dump(new)
module='test_io_service_authority';tree=ast.parse((S/'project/tests'/(module+'.py')).read_bytes())
def methods(cls):
 node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
 return sorted(module+'.'+cls+'.'+n.name for n in node.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
controls=methods('IoServiceAuthorityTests');process=methods('IoAuthorityProcessTests');assert len(controls)==32 and len(process)==1
assert len(inventory(S/'project'))==244
reviewed=[
 '239 inherited files unchanged, including every old test. Existing production deltas: one read-only resolver method (other AST identical), optional authority-bound service pin with legacy profile unchanged, and store source added to supervisor closure (other AST identical). New store and test module. All Python AST parsed without project execution.',
 'Explicit admin creation, shared Journal database/owner/transaction, metadata digest anchor, exact owned schema including no temp shadows, typed and bounded retained payloads, contiguous global/per-evaluator histories, mutation/receipt/hash/head association, no repair or pruning.',
 'Exact replay before fresh source/runtime/capacity/current-revision checks, current authorization still required. Same key changed request conflicts. Fresh revision compare-and-swap repeated after preparation. Checkpoint fault seams cover rollback and lost reply; original independent clock floor semantics retained.',
 'Bound pin profile0.2 includes actual authority ID in configuration digest and history; pure legacy profile0.1 unchanged. Not standalone attestation or a defense against whole-database trusted-state rewrite.',
 'Complete installed resolver snapshot requires transaction, all permissions/actions, bindings/history/resource proof/readiness/session provenance. No source IO under snapshot, no fake candidate, no omission, no writes. Presence is not freshness.',
 'Fresh run requires installed config match, reconstructs source pin, actual descriptors, original matrix and final authority consistency recheck. No lease after return, run reservation, provider effects, promotion or public mount introduced.',
 '32 new authority controls have separate16MiB scratch and74 private runtime SQL opens maximum/four per method; no launches/network. New actual authority process permits six parent SQL opens and original exact worker. Inherited206 controls/ten process scopes unchanged. Existing deadlines/effect/storage ceilings unchanged.',
 'Raw corrupt fixtures and all failed attempts retained. Original code image now258 files, seven supervisor source files. Primary-agent review only; no physical/MCU/emulator/acquired-controller/live-inference/service/adjacent-Harness execution. Logical data accounting is not enforced aggregate disk quota.'
]
write(S/'source-review.json',dict(scope='Authority-owned service configuration and fresh installed descriptor preparation',changedInheritedFiles=changed,unchangedInheritedFiles=239,newProjectFiles=2,reviewed=reviewed,independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Authority-owned I/O service configuration\n\n[Design](../DESIGN.md), [source review](source-review.json). Public mounting, promotion and physical qualification remain unfinished.\n')
rows=inventory(S,True); assert len(rows)==247;write(S/'index.json',dict(scope='Frozen authority configuration and33 new methods.',files=rows));pin=sha(S/'index.json')
for i in range(1,14):
 prior=O/('harness%02d'%(i if i<=11 else 1 if i==12 else 11))
 for r in read(prior/'index.json')['files']: assert sha(prior/r['path'])==r['sha256']
 oldtargets=read(prior/'targets.json')['targets'];targets=controls if i==12 else process if i==13 else oldtargets;count=len(targets)
 H=B/('harness%02d'%i);H.mkdir();(H/'references').mkdir();borrowed=[]
 for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
  p=prior/name;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=count,targets=targets))
 for name in ('run_attempt.py','attempt_child.py'):
  original=(prior/name).read_text();updated=original.replace(base['sourceIndexSha256'],pin).replace(O.name,B.name)
  updated=re.sub(r'\b245\b','247',updated);updated=re.sub(r'\b242\b','244',updated)
  if name=='run_attempt.py':
   assert updated.count(repr(oldtargets))==1; updated=updated.replace(repr(oldtargets),repr(targets))
  if i==12:
   updated=re.sub(r'\b206\b','32',updated).replace('service206','authority32').replace('Service206','Authority32')
   if name=='attempt_child.py':
    start=updated.index('CONTROL_TARGETS = ');end=updated.index('\ndef audit(',start)
    updated=updated[:start]+'CONTROL_TARGETS = '+repr(controls)+'\n'+updated[end:]
    start=updated.index("        allowed=current_test in CONTROL_TARGETS");end=updated.index("    if event == 'exec':",start)
    updated=updated[:start]+'''        method=current_test.rsplit('.',1)[1] if current_test in CONTROL_TARGETS else 'invalid'
        if (current_test not in CONTROL_TARGETS or path.parent.parent!=scratch/method or
                path.parent.name not in {'runtime','runtime-other'} or
                not(path.name=='authority.db' or re.fullmatch(r'synthetic-io-board-[0-9a-f]{64}\\.db',path.name))):
            prohibited.append(event); raise RuntimeError('Only declared authority fixture databases may open')
        if len(sqlite_connections)>=74 or sum(c['testId']==current_test for c in sqlite_connections)>=4:
            raise RuntimeError('Declared authority database inventory bound')
        sqlite_connections.append({'testId':current_test,'database':str(path)})
'''+updated[end:]
  if i==13:
   updated=updated.replace(oldtargets[0].rsplit('.',1)[1],targets[0].rsplit('.',1)[1])
   if name=='attempt_child.py':
    start=updated.index("        expected = scratch /",updated.index("    if event == 'sqlite3.connect':"));end=updated.index("    if event == 'exec':",start)
    updated=updated[:start]+'''        work=scratch/'test_authority_configured_owned_group_reopens_and_replays'
        valid=(path==work/'supervisor'/'attempts.db' or (path.parent==work/'runtime' and
            (path.name=='authority.db' or re.fullmatch(r'synthetic-io-board-[0-9a-f]{64}\\.db',path.name))))
        if current_test!=config['targets'][0] or not valid:
            prohibited.append(event); raise RuntimeError('Only exact authority/runtime/supervisor databases may open')
        if len(sqlite_connections)>=6: raise RuntimeError('Declared six parent database opens exceeded')
        sqlite_connections.append({'testId':current_test,'database':str(path)})
'''+updated[end:]
  ast.parse(updated);(H/name).write_text(updated)
  (H/(name+'.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),fromfile=str((prior/name).relative_to(ROOT)),tofile=str((H/name).relative_to(ROOT)))))
 scope='Authority32: exact32 new controls, private runtime SQL only.' if i==12 else 'Authority-owned original worker1: durable configuration plus original supervisor.' if i==13 else 'Unchanged inherited '+str(count)+' method selection with new source identity.'
 (H/'SCOPE.md').write_text('# Exact execution scope\n\n'+scope+'\n\n[Design](../DESIGN.md), [targets](targets.json). Existing deadlines and retention bounds; explicit SQL/launch allowances are frozen in the child.\n')
 (H/'README.md').write_text('# Authority I/O checks\n\n[Scope](SCOPE.md), [targets](targets.json), [source](../implementation01/README.md).\n')
 review=read(prior/'review.json');review.update(scope=scope,tests=count,sourceIndexSha256=pin,targetSha256=sha(H/'targets.json'),reviewed=reviewed,inheritedHarnessIndexSha256=sha(prior/'index.json'))
 if i==12: review.update(controlTargets=controls,controlLabels=['runtime','runtime-other'],sqliteConnectionsMaximum=74,sqliteConnectionsPerMethodMaximum=4)
 if i==13: review.update(sqliteConnectionsMaximum=6)
 write(H/'review.json',review);write(H/'index.json',dict(scope=scope,files=inventory(H)))
 print(json.dumps(dict(harness=H.name,tests=count,indexSha256=sha(H/'index.json'))))
print(json.dumps(dict(projectFiles=244,frozenFiles=247,sourceIndexSha256=pin)))
