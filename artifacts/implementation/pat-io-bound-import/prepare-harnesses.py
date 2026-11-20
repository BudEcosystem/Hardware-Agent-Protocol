"""Fresh complete harnesses after retained pre-launch preparation failure."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd(); BASE=ROOT/'artifacts/implementation/pat-io-bound-import'; STAGE=BASE/'implementation01'
PROCESS=ROOT/'artifacts/implementation/pat-io-execution-handoff/harness25'
CONTROL=ROOT/'artifacts/implementation/pat-io-evidence-import/harness01'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_bytes())
def write(path,value):
    with path.open('x') as stream:stream.write(json.dumps(value,indent=2)+'\n')
def inventory(folder):
    rows=[]
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            if path.suffix=='.py':ast.parse(path.read_bytes())
            rows.append(dict(path=path.relative_to(folder).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    return sorted(rows,key=lambda row:row['path'])
pin=sha(STAGE/'index.json');rows=read(STAGE/'index.json')['files'];assert len(rows)==264
for row in rows:
    path=ROOT/row['path'];assert sha(path)==row['sha256'] and path.stat().st_size==row['bytes']
failed=read(BASE/'harness01/attempts/attempt01-real-import/result.json')
assert failed['childState']=='not_started' and failed['counts'] is None and failed['status']=='failed'
write(BASE/'preparation-failure.json',dict(originalPreparation='prepare.py',
    originalPreparationSha256=sha(BASE/'prepare.py'),originalHarness='harness01',
    originalAttempt='harness01/attempts/attempt01-real-import/result.json',
    childStarted=False,supervisorAdmitted=False,workerLaunched=False,
    cause='The process-child template has no literal target list; the generator incorrectly required one. The launch was invoked before this failed preparation had been inspected and refused a missing child file.',
    action='Retain original generator and partial harness/attempt unchanged. Build complete fresh harnesses and inspect preparation success before execution.',
    originalErrors=failed['errors'],sourceIndexSha256=pin))
targets=[]
for module,clsname in [('test_io_evidence_bound_process','IoEvidenceBoundProcessTests'),('test_io_evidence_import_history','IoEvidenceImportHistoryTests')]:
    tree=ast.parse((STAGE/'project/tests'/(module+'.py')).read_bytes())
    cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name==clsname)
    targets+=sorted(module+'.'+clsname+'.'+node.name for node in cls.body if isinstance(node,ast.FunctionDef) and node.name.startswith('test_'))
assert len(targets)==6
review=read(STAGE/'source-review.json')['reviewed']
for i,target in enumerate(targets,2):
    process=i==2;prior=PROCESS if process else CONTROL
    h=BASE/('harness%02d'%i);h.mkdir();(h/'references').mkdir();borrowed=[]
    for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
        source=prior/name;dest=h/'references'/Path(name).name;shutil.copyfile(source,dest)
        borrowed.append(dict(source=source.relative_to(ROOT).as_posix(),copy=dest.relative_to(h).as_posix(),bytes=source.stat().st_size,sha256=sha(source)))
    write(h/'borrowed-inputs.json',borrowed);write(h/'targets.json',dict(testCount=1,targets=[target]))
    old_targets=read(prior/'targets.json')['targets'];old_method=old_targets[0].rsplit('.',1)[1];new_method=target.rsplit('.',1)[1]
    old_pin=read(prior/'review.json')['sourceIndexSha256'];count=252 if process else 259;frozen=255 if process else 262
    cap=6 if process else (4 if 'replaced_supervisor' in target else 3)
    for name in ('run_attempt.py','attempt_child.py'):
        original=(prior/name).read_text();s=original.replace(old_pin,pin)
        s=s.replace('pat-io-execution-handoff/implementation01','pat-io-bound-import/implementation01') if process else s.replace('pat-io-evidence-import/implementation01','pat-io-bound-import/implementation01')
        for before,after in [('len(expected) != '+str(frozen),'len(expected) != 264'),
            ("'frozenPreparationInputCount': "+str(frozen),"'frozenPreparationInputCount': 264"),
            ("'projectInputCount': "+str(count),"'projectInputCount': 261"),
            ('len(selected) != '+str(count),'len(selected) != 261'),('exactly '+str(count)+' files','exactly 261 files')]:s=s.replace(before,after)
        occurrences=s.count(repr(old_targets))
        if name=='attempt_child.py' and process:assert occurrences==0
        else:
            assert occurrences==1;s=s.replace(repr(old_targets),repr([target]))
        if process:s=s.replace(old_method,new_method)
        if name=='attempt_child.py':
            if process:s=s.replace("name.startswith('test_')", "name.startswith('test_') or name == 'evidence' or name.startswith('evidence.')")
            else:
                s=s.replace('len(sqlite_connections)>=3','len(sqlite_connections)>='+str(cap))
                s=s.replace("sum(c['testId']==current_test for c in sqlite_connections)>=3", "sum(c['testId']==current_test for c in sqlite_connections)>="+str(cap))
                if cap==4:s=s.replace("path.parent.name in {'supervisor'}", "path.parent.name in {'supervisor','replacement'}")
        ast.parse(s);(h/name).write_text(s)
        (h/(name+'.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile=str(prior/name),tofile=str(h/name))))
    scope=('One actual complete30-case reserved/handoff worker through original-run import and historical replay.' if process else 'One explicit importer authority/history/storage fixture control; no worker or semantic success claimed.')
    (h/'SCOPE.md').write_text('# Exact scope\n\n'+scope+'\n\n[Target](targets.json), [source](../implementation01/README.md). Original180-second outer limit; '+('256MiB' if process else '16MiB')+' scratch and16MiB single-file ceilings.\n')
    (h/'README.md').write_text('# Bound import verification\n\n[Scope](SCOPE.md), [source](../implementation01/README.md).\n')
    write(h/'review.json',dict(scope=scope,tests=1,sourceIndexSha256=pin,targetSha256=sha(h/'targets.json'),
        inheritedHarnessIndexSha256=sha(prior/'index.json'),reviewed=review,independentReview=False,releasedBy='primary-agent',
        selectionKind='process' if process else 'control',sqliteConnectionsMaximum=cap,
        scratchBytesCeiling=(256 if process else 16)*1024*1024,projectInputCount=261,frozenPreparationInputCount=264,
        priorPreparationFailureRetained=True))
    write(h/'index.json',dict(scope=scope,files=inventory(h)))
print(json.dumps(dict(sourceIndexSha256=pin,sourceFiles=264,harnesses=list(range(2,8)),methods=6,prepared=True)))
