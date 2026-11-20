"""Freeze run reservations and exact inherited/new scopes without project execution."""
import ast,difflib,hashlib,json,re,shutil
from pathlib import Path
R=Path.cwd();B=R/'artifacts/implementation/pat-io-service-runs';O=R/'artifacts/implementation/pat-io-service-authority';S=B/'implementation01';P=O/'implementation02'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
def inventory(folder,rooted=False):
 rows=[]
 for p in folder.rglob('*'):
  assert not p.is_symlink()
  if p.is_file():
   if p.suffix=='.py':ast.parse(p.read_bytes())
   rows.append(dict(path=p.relative_to(R if rooted else folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 return sorted(rows,key=lambda x:x['path'])
base=read(S/'baseline-inputs.json');assert sha(P/'index.json')==base['sourceIndexSha256']=='6215ff9c5fe621a704c1996af86fc6ad80da994ffb6d92e97f7bad71afb75470'
for row in read(P/'index.json')['files']:assert sha(R/row['path'])==row['sha256']
changed=[]
for row in base['inheritedProjectInputs']:
 rel=(R/row['path']).relative_to(P/'project')
 if sha(S/'project'/rel)!=row['sha256']:changed.append(rel.as_posix())
assert len(base['inheritedProjectInputs'])==244 and changed==['supervisor/supervisor_contracts.py']
rel=changed[0];before=(P/'project'/rel).read_text();after=(S/'project'/rel).read_text()
def without_closure(text):return [ast.dump(n)for n in ast.parse(text).body if not(isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='SOURCE_FILES'for t in n.targets))]
assert without_closure(before)==without_closure(after)
(B/'source-closure.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='authority/'+rel,tofile='runs/'+rel)))
module='test_io_service_runs';tree=ast.parse((S/'project/tests'/(module+'.py')).read_bytes())
def methods(cls):
 node=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name==cls)
 return sorted(module+'.'+cls+'.'+n.name for n in node.body if isinstance(n,ast.FunctionDef)and n.name.startswith('test_'))
controls=methods('IoServiceRunTests');process=methods('IoReservedProcessTests');assert len(controls)==29 and len(process)==1 and len(inventory(S/'project'))==246
reviewed=[
 '243 inherited project files unchanged, including every inherited test and all supervisor behavior except the SOURCE_FILES addition. Other supervisor_contracts AST nodes unchanged. New io_service_runs and test module. Every Python AST parsed without project execution.',
 'Explicit authority-owned creation with existing configuration store and Journal lock/connection. Exact schema, metadata anchor, typed/size preflight and total document-byte preflight, immutable configuration reference, contiguous sequence, intent/request/bundle/receipt chain joins, no repair or pruning.',
 'Logical key matches original supervisor deployment/evaluator/run. Current admin required; creator retained. Exact replay precedes source/runtime/current-configuration/capacity checks, but not authorization or retained-state validation. Changed candidate/config receipt conflicts. No implicit latest-configuration selection.',
 'Fresh preparation is outside the transaction. Final commit rechecks current configuration, complete installed registry availability and selected descriptor equality; atomic request plus all original inputs. Lost reply and rollback seams; no provider/worker effect or execution-success claim. No source IO added inside final authority validation.',
 '32 runs/8MiB encoded accounting maxima may only be lowered;39 original64KiB documents,64KiB request,2KiB intent,4KiB receipt. Accounting is not an enforced disk/SQLite/time quota. Public pinned supervisor mounting and interrupted-handoff reconciliation remain required.',
 'New29 controls split15/14 under original16MiB scratch ceilings; exact runtime-only SQL scopes36/30 opens, at most4 per method. Actual reserved worker permits9 parent DB opens and unchanged fixed worker. Inherited249 controls/process methods rerun; original60s group/owned and180s outer deadlines unchanged.',
 'Actual worker retains original reservation, config/pin and digest before supervisor construction; full30-case reader; then configuration/session change and source-free reservation/supervisor replay. No second worker, no source authority device effects. Expanded code image259 files/eight supervisor sources.',
 'Primary-agent review only. Raw failures retained, no altered mutation key retry or reset. No physical/MCU/emulator/acquired-controller/live-inference/service/adjacent-Harness execution. Full goal active; no public, semantic or physical qualification claim.'
]
write(S/'source-review.json',dict(scope='Durable I/O run reservations and replay of original inputs',changedInheritedFiles=changed,unchangedInheritedFiles=243,newProjectFiles=2,reviewed=reviewed,independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Durable logical I/O runs\n\n[Design](../DESIGN.md), [source review](source-review.json). Reservation is distinct from execution; public mounting and evidence import remain unfinished.\n')
rows=inventory(S,True);assert len(rows)==249;write(S/'index.json',dict(scope='Frozen logical run reservation and30 new test methods.',files=rows));pin=sha(S/'index.json')
extras={'test_before_commit_failure_rolls_back_run_and_all_input_documents','test_cross_authority_runtime_cannot_supply_fresh_run','test_lost_reply_after_commit_replays_exact_reservation_on_reopen','test_reopen_replay_retains_complete_original_inputs_without_source_io'}
for n in range(1,17):
 prior=O/('harness%02d'%(n+13 if n<=13 else 25 if n<=15 else 26))
 for row in read(prior/'index.json')['files']:assert sha(prior/row['path'])==row['sha256']
 oldtargets=read(prior/'targets.json')['targets'];targets=controls[:15]if n==14 else controls[15:]if n==15 else process if n==16 else oldtargets
 count=len(targets);H=B/('harness%02d'%n);H.mkdir();(H/'references').mkdir();borrowed=[]
 for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
  p=prior/name;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(R).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=count,targets=targets))
 sql_max=2*count+2*sum(t.rsplit('.',1)[1]in extras for t in targets)if n in(14,15)else 9 if n==16 else None
 if n in(14,15):assert sql_max==(36 if n==14 else 30)
 for name in ('run_attempt.py','attempt_child.py'):
  original=(prior/name).read_text();updated=original.replace(base['sourceIndexSha256'],pin).replace(O.name,B.name).replace('implementation02','implementation01')
  updated=re.sub(r'\b247\b','249',updated);updated=re.sub(r'\b244\b','246',updated)
  if name=='run_attempt.py':assert updated.count(repr(oldtargets))==1;updated=updated.replace(repr(oldtargets),repr(targets))
  if n in(14,15):
   updated=re.sub(r'\b32\b',str(count),updated).replace('authority32','runs'+str(count)).replace('Authority32','Runs'+str(count))
   if name=='attempt_child.py':
    start=updated.index('CONTROL_TARGETS = ');end=updated.index('\ndef audit(',start)
    updated=updated[:start]+'CONTROL_TARGETS = '+repr(targets)+'\n'+updated[end:]
    updated=updated.replace('len(sqlite_connections)>=74','len(sqlite_connections)>='+str(sql_max))
  if n==16:
   updated=updated.replace(oldtargets[0].rsplit('.',1)[1],targets[0].rsplit('.',1)[1])
   if name=='attempt_child.py':updated=updated.replace('len(sqlite_connections)>=6','len(sqlite_connections)>=9').replace('six parent','nine parent')
  ast.parse(updated);(H/name).write_text(updated)
  (H/(name+'.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),fromfile=str((prior/name).relative_to(R)),tofile=str((H/name).relative_to(R)))))
 scope='Run reservation controls'+str(count)+': private compact runtime fixtures only.'if n in(14,15)else 'Reserved original worker1 and replay after configuration/session change.'if n==16 else 'Unchanged inherited '+str(count)+' methods with expanded source identity.'
 (H/'SCOPE.md').write_text('# Exact execution scope\n\n'+scope+'\n\n[Design](../DESIGN.md), [targets](targets.json). Fixed SQL/worker allowances in retained child; original deadlines and retention bounds.\n')
 (H/'README.md').write_text('# Durable-run checks\n\n[Scope](SCOPE.md), [targets](targets.json), [source](../implementation01/README.md).\n')
 review=read(prior/'review.json');review.update(scope=scope,tests=count,sourceIndexSha256=pin,targetSha256=sha(H/'targets.json'),reviewed=reviewed,inheritedHarnessIndexSha256=sha(prior/'index.json'))
 if n in(14,15):review.update(controlTargets=targets,sqliteConnectionsMaximum=sql_max)
 if n==16:review.update(sqliteConnectionsMaximum=9)
 write(H/'review.json',review);write(H/'index.json',dict(scope=scope,files=inventory(H)))
 print(json.dumps(dict(harness=H.name,tests=count,indexSha256=sha(H/'index.json'))))
print(json.dumps(dict(projectFiles=246,frozenFiles=249,sourceIndexSha256=pin)))
