"""Freeze unchanged production, new integration/control tests and exact scopes."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd(); BASE=ROOT/'artifacts/implementation/pat-io-bound-import'; STAGE=BASE/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-evidence-import/implementation01'
PROCESS=ROOT/'artifacts/implementation/pat-io-execution-handoff/harness25'
CONTROL=ROOT/'artifacts/implementation/pat-io-evidence-import/harness01'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_bytes())
def write(path,value):
    with path.open('x') as stream:stream.write(json.dumps(value,indent=2)+'\n')
def inventory(folder,rooted=False):
    rows=[]
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            if path.suffix=='.py':ast.parse(path.read_bytes())
            rows.append(dict(path=path.relative_to(ROOT if rooted else folder).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    return sorted(rows,key=lambda row:row['path'])
baseline=read(STAGE/'baseline-inputs.json')['inheritedProjectInputs'];assert len(baseline)==259
for row in baseline:
    source=ROOT/row['path'];target=STAGE/'project'/source.relative_to(OLD/'project')
    assert sha(source)==row['sha256']==sha(target)
assert len(inventory(STAGE/'project'))==261
modules=[('test_io_evidence_bound_process','IoEvidenceBoundProcessTests'),('test_io_evidence_import_history','IoEvidenceImportHistoryTests')]
targets=[]
for module,clsname in modules:
    tree=ast.parse((STAGE/'project/tests'/(module+'.py')).read_bytes())
    cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name==clsname)
    targets += sorted(module+'.'+clsname+'.'+node.name for node in cls.body if isinstance(node,ast.FunctionDef) and node.name.startswith('test_'))
assert len(targets)==6
review=[
    'All259 prior project files remain byte-identical; only two test modules are added. Producer262-file image and five-module consumer source identities remain unchanged.',
    'The actual integration method substitutes neither launch nor inspection. It requires the original30-case worker, original-run import and receipt replay after configuration/session drift. Failed transport/import publishes zero evaluations; the complete-run assertion still fails.',
    'The actual source authority, configuration, run reservation, version2 supervisor and handoff are used. There is no caller-supplied path/result/callback and no physical provider or live service.',
    'Five separate fixture controls cover replacement supervisor authority, two import histories, rehashed cross-run control substitution, forged receipt chain and32769 retained rows exceeding the32768-document ceiling before body fetch. Their worker/semantic success remains explicitly substituted.',
    'Exactly one method is selected per fresh harness, including every final count predicate. The previous three-test wrapper failure is not rerun or relabeled.',
    'Original60-second worker/group and180-second outer bounds, full matrix, effect/record/byte/file ceilings and retention ceilings remain. Actual-process retention256MiB, control retention16MiB and single-file16MiB are unchanged. Large authority evidence storage can still fail retention; no aggregate quota or protected capacity is claimed.',
    'The actual integration permits only the fixed original worker executable and at most six declared parent SQLite opens for reopen. Each fixture permits three connections, except the replacement-authority control which declares one extra private ledger and exactly four possible connections.',
    'No physical ports/flashing, MCU/emulator, live inference/service, acquired controller/research execution or adjacent Harness mutation. Primary-agent review only. Full prompt learning, catalog/public integration, persistent Arduino and actual device/driver/hub providers remain open.'
]
write(STAGE/'source-review.json',dict(reviewed=review,unchangedInheritedProjectFiles=259,newProductionFiles=0,newTestMethods=6,
    independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(STAGE/'README.md').write_text('# Actual bound-worker import and importer history\n\n[Design](../DESIGN.md), [source review](source-review.json). All259 inherited files remain unchanged. One actual worker/import method and five explicit fixture controls are new. No prior failure is rerun or repaired.\n')
rows=inventory(STAGE,True);assert len(rows)==264
write(STAGE/'index.json',dict(scope='Unchanged production through actual bound import and missing importer controls.',files=rows));pin=sha(STAGE/'index.json')
for i,target in enumerate(targets,1):
    process=i==1; prior=PROCESS if process else CONTROL
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
        s=s.replace('len(expected) != '+str(frozen),'len(expected) != 264')
        s=s.replace("'frozenPreparationInputCount': "+str(frozen),"'frozenPreparationInputCount': 264")
        s=s.replace("'projectInputCount': "+str(count),"'projectInputCount': 261")
        s=s.replace('len(selected) != '+str(count),'len(selected) != 261').replace('exactly '+str(count)+' files','exactly 261 files')
        assert s.count(repr(old_targets))==1;s=s.replace(repr(old_targets),repr([target]))
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
        scratchBytesCeiling=(256 if process else 16)*1024*1024,projectInputCount=261,frozenPreparationInputCount=264))
    write(h/'index.json',dict(scope=scope,files=inventory(h)))
print(json.dumps(dict(sourceIndexSha256=pin,unchangedInheritedProjectFiles=259,projectFiles=261,frozenFiles=264,newMethods=6)))
