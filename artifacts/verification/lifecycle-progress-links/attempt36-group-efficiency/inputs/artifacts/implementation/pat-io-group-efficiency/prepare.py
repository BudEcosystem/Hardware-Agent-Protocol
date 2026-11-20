"""Freeze exact plan reuse and fresh compact layout with original bound selections."""
import ast,difflib,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-group-efficiency';S=B/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-schema-memo';OS=OLD/'implementation01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
def methods(module,cls):
 tree=ast.parse((S/'project/tests'/(module+'.py')).read_bytes());body=next(n.body for n in tree.body if isinstance(n,ast.ClassDef)and n.name==cls)
 return sorted(module+'.'+cls+'.'+n.name for n in body if isinstance(n,ast.FunctionDef)and n.name.startswith('test_'))
base=read(S/'baseline-inputs.json');assert sha(OS/'index.json')==base['sourceIndexSha256'];assert len(base['inheritedProjectInputs'])==218
changed=[];patches=[]
for row in base['inheritedProjectInputs']:
 p=ROOT/row['path'];rel=p.relative_to(OS/'project');q=S/'project'/rel
 assert sha(p)==row['sha256']and p.stat().st_size==row['bytes']
 if sha(p)!=sha(q):
  changed.append(rel.as_posix());patches.extend(difflib.unified_diff(p.read_text().splitlines(True),q.read_text().splitlines(True),fromfile=p.relative_to(ROOT).as_posix(),tofile=q.relative_to(ROOT).as_posix()))
assert len(changed)==12;(B/'implementation.patch').write_text(''.join(patches))
write(S/'source-review.json',dict(scope='Primary-agent complete11 inherited production changes, one new production module, inherited full-test addition and19 new test methods reviewed before execution.',
 changedFiles=changed,newFiles=['hms/pat_io_validated_matrix.py','tests/test_pat_io_validated_matrix.py','tests/test_io_compact_storage.py'],unchangedInheritedFiles=206,
 reviewed=['Validated matrix bundle performs original full generate/validate before publication. Five exact bounded detached trees, type-sensitive equality and active unbound ticket association prevent reuse after input change. No runtime/authority/semantic guards removed.',
 'All five fixed runners preserve original standalone validation and use exact group association only with the trusted ticket. Budget constructor verifies the plan association; stale/bound/missing/mismatched tickets refuse.',
 'Closed opt-in1024-byte SQLite creation profile in Journal/Board/IoRuntime, used by all three original finite-I/O runtime-open paths. Existing mismatched layouts refuse before conversion. None preserves existing/default behavior. Schemas and DELETE/EXTRA/foreign-key settings unchanged.',
 'Full groups add explicit storage identity and52 actual header checks, retaining all existing cases, expected outcomes, record/operation/tick accounting and every ceiling. No retained raw state changed or deleted.',
 'Twelve new pure matrix tests cover all five runner families and default validation; one pure profile refusal plus six actual layout/rollback/owner/recovery/replay methods.87 pure selection includes existing44 and30 combined-matrix methods.',
 'No live HMS, adjacent Harness, physical ports/MCU, inference or external controllers executed. Primary review only; existing helpers are usage-limited.'],
 independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Exact group input reuse and compact fresh stores\n\nSee [design](../DESIGN.md) and [source review](source-review.json). The candidate\nretains original matrix validation, runtime authority and every existing limit.\nSuccessful capture is not complete independent qualification or physical evidence.\n')
rows=[]
for p in sorted(S.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  if p.suffix=='.py':ast.parse(p.read_bytes())
  rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==224;write(S/'index.json',dict(scope='Frozen exact validated-plan reuse and compact new-store profile; original bounds retained.',files=rows));pin=sha(S/'index.json')
pure=read(OLD/'harness01/targets.json')['targets']+methods('test_pat_io_combined_matrix','IoCombinedMatrixTests')+methods('test_pat_io_validated_matrix','ValidatedIoMatrixTests')+methods('test_io_compact_storage','StorageProfileInputTests')
storage=methods('test_io_compact_storage','CompactStorageTests');assert len(pure)==87 and len(storage)==6
groups=[read(OLD/('harness%02d'%n)/'targets.json')['targets']for n in (4,2,3)]
selections=[(1,pure),(4,storage),(4,groups[0]),(2,groups[1]),(3,groups[2])]
for i,(origin,targets)in enumerate(selections,1):
 old=OLD/('harness%02d'%origin);h=B/('harness%02d'%i);h.mkdir();(h/'references').mkdir();borrowed=[]
 for row in read(old/'index.json')['files']:assert sha(old/row['path'])==row['sha256']and(old/row['path']).stat().st_size==row['bytes']
 for name in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
  p=old/name;q=h/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(h).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(h/'borrowed-inputs.json',borrowed);prior=read(old/'targets.json');write(h/'targets.json',dict(testCount=len(targets),targets=targets))
 for name in ['run_attempt.py','attempt_child.py']:
  before=(old/name).read_text();after=before.replace(base['sourceIndexSha256'],pin).replace('pat-io-schema-memo','pat-io-group-efficiency').replace('hms-io-schema-memo-','hms-io-group-efficiency-')
  after=after.replace("len(expected) != 221","len(expected) != 224").replace("'frozenPreparationInputCount': 221","'frozenPreparationInputCount': 224")
  after=re.sub(r'\b218\b','221',after)
  count=prior['testCount'];new=len(targets)
  if new!=count:
   after=re.sub(r'([=!]= )'+str(count)+r'\b',lambda m:m[1]+str(new),after)
   after=after.replace("'expectedTests': "+str(count),"'expectedTests': "+str(new)).replace(repr(prior['targets']),repr(targets))
  if i==1:after=after.replace('SchemaMemo44','GroupEfficiency87').replace('schema44','efficiency87')
  if i==2:after=after.replace('IoGroup1','CompactStorage6').replace('group1','storage6')
  if i==2 and name=='attempt_child.py':
   start=after.index('        valid = (type(current_test)');end=after.index('        if not valid:',start)
   after=after[:start]+"""        valid = (type(current_test) is str and current_test in config['targets'] and
            current_test in STORAGE_IDS and Path(raw).is_absolute() and
            not raw.startswith('file:') and path.is_relative_to(scratch))
        parts = path.relative_to(scratch).parts if valid else ()
        valid = (valid and len(parts)==4 and parts[0]==current_test.split('.')[-1] and
            parts[1] in ('compact','default') and parts[2]=='state' and
            (parts[3]=='authority.db' or re.fullmatch(r'synthetic-io-board-[0-9a-f]{64}\\.db',parts[3]) is not None))
""".replace('STORAGE_IDS',repr(storage))+after[end:]
  ast.parse(after);(h/name).write_text(after)
  (h/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(old/name).relative_to(ROOT).as_posix(),tofile=(h/name).relative_to(ROOT).as_posix())))
 scope=(old/'SCOPE.md').read_text()
 if i==2:scope='''# Exact original compact-store execution scope

Only the six named original compact-storage methods in targets.json. SQL is
allowed solely at each own compact/default/state authority or synthetic-board
database. Other SQL paths, network, subprocess, physical/MCU, inference and
live-service execution are forbidden. Original180s harness,16MiB scratch,
8192 files,256MiB inputs,16MiB file,4MiB JSON and8MiB log bounds remain.
All original sources, failures and raw scratch must remain retained.
'''
 (h/'SCOPE.md').write_text(scope)
 (h/'README.md').write_text('# Exact group efficiency selection\n\n[Targets](targets.json), [source](../implementation01/README.md), [scope](SCOPE.md).\nComplete source and harness deltas are reviewed before execution.\n')
 print(json.dumps(dict(harness=h.name,tests=len(targets),targetsSha256=sha(h/'targets.json'))))
before=(OLD/'acquire.py').read_text();after=before.replace('pat-io-schema-memo','pat-io-group-efficiency')
after=after.replace("A/'project',218","A/'project',221").replace("ROOT,221","ROOT,224").replace('sourceFilesVerified=218,frozenFilesVerified=221','sourceFilesVerified=221,frozenFilesVerified=224')
start=after.index('for c in connections:');end=after.index("log=(A/'output.log')",start)
after=after[:start]+"""for c in connections:
 assert c['testId']in targets
 p=Path(c['database']);parts=p.relative_to(raw).parts
 assert parts[0]==c['testId'].split('.')[-1]
 if c['testId']in STORAGE_IDS:
  assert len(parts)==4 and parts[1]in{'compact','default'}and parts[2]=='state';filename=parts[3]
 else:
  assert c['testId'].startswith('test_pat_io_group_worker.IoGroupWorkerTests.')
  assert len(parts)==5 and parts[1]=='group'and re.fullmatch(r'case-[0-2][0-9]',parts[2])is not None and parts[3]=='state';filename=parts[4]
 assert filename=='authority.db'or re.fullmatch(r'synthetic-io-board-[0-9a-f]{64}\\.db',filename)
""".replace('STORAGE_IDS',repr(storage))+after[end:]
ast.parse(after);(B/'acquire.py').write_text(after);(B/'acquire.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(OLD/'acquire.py').relative_to(ROOT).as_posix(),tofile=(B/'acquire.py').relative_to(ROOT).as_posix())))
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=221,frozenFiles=224)))
