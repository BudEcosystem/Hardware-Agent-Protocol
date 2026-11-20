"""Freeze compact storage and exact reviewed integration/control scopes."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd(); BASE=ROOT/'artifacts/implementation/pat-io-content-store'; STAGE=BASE/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-bound-import/implementation01'
PROCESS=ROOT/'artifacts/implementation/pat-io-bound-import/harness02'
CONTROL=ROOT/'artifacts/implementation/pat-io-bound-import/harness03'
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
baseline=read(STAGE/'baseline-inputs.json')['inheritedProjectInputs'];assert len(baseline)==261
for row in baseline:
    source=ROOT/row['path'];dest=STAGE/'project'/source.relative_to(OLD/'project')
    assert sha(source)==row['sha256']==sha(dest)
assert len(inventory(STAGE/'project'))==266
controls=[]
for module,clsname in [('test_io_evidence_compact','CompactIoEvidenceTests')]:
    tree=ast.parse((STAGE/'project/tests'/(module+'.py')).read_bytes())
    cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name==clsname)
    controls=sorted(module+'.'+clsname+'.'+node.name for node in cls.body if isinstance(node,ast.FunctionDef) and node.name.startswith('test_'))
assert len(controls)==18
first='test_io_evidence_compact.CompactIoEvidenceTests.test_exact_reconstruction_deduplicates_without_dropping_references'
process_target='test_io_evidence_compact_process.CompactIoEvidenceProcessTests.test_compact_bound_worker_import_and_historical_replay'
assert first in controls
targets=[first,process_target]+[target for target in controls if target!=first]
review=[
    'All261 inherited files remain byte-identical. New evidence_compact package has three modules; two new test modules add18 controls and one actual integration. Producer262-file image and legacy267-input consumer identity remain unchanged.',
    'Explicit compact profile/anchor and four owned tables retain one exact body per digest and every original run/path reference. All legacy tables/readers remain separate; no migration or reset occurs.',
    'Actual body/reference types, sizes, counts, missing references and orphan objects are checked before payload reads. Per-run expanded closure and aggregate expanded/unique encoded work plus conservative metadata charges remain bounded by the original ceilings. Installed creation options only lower bounds.',
    'Objects, references, receipt and association publish in one Journal transaction. Existing objects are compared by actual bytes/digest/length before reuse, not trusted digest columns. Rollback/lost reply preserve atomicity and exact replay.',
    'Independent full-group inspection still runs outside Journal transactions. Current auth and original authority/request/attempt binding are checked at commit. Historical reads/reinspection do not provide fresh catalog eligibility.',
    'Controls cover exact reconstruction, multi-run sharing, legacy coexistence, corruption/missing/orphan bodies, rehashed cross-run substitution, rollback/lost replies, object/expanded quotas, preflight, schema shadows/extras, creation limits, auth recheck and reinspection. Successful worker/semantic results in these controls are explicitly substituted fixtures.',
    'The actual integration substitutes neither worker launch nor semantics and preserves full30-case matrix,60-second worker/group and180-second outer deadline. It verifies import/replay after configuration/session drift and distinct reference/body counts.',
    'All original effect/record/byte/file limits remain. Controls retain16MiB and actual process256MiB total scratch; both retain the16MiB single-file ceiling. Deduplication is not an allocated-storage guarantee or protected control capacity.',
    'Each fresh scope selects exactly one method and every final count predicate expects one. Only the actual scope permits the fixed original worker command and six declared parent SQLite opens. Controls permit no worker/network and exactly three parent SQLite connections.',
    'Primary-agent review only. No physical ports/flashing, MCU/emulator, live inference/service, acquired controller/research execution or adjacent Harness mutation. All previous failures remain retained; no original logical run is retried or relabeled.'
]
write(STAGE/'source-review.json',dict(reviewed=review,unchangedInheritedProjectFiles=261,newProductionFiles=3,newTestMethods=19,
    independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(STAGE/'README.md').write_text('# Compact exact-body evidence storage\n\n[Design](../DESIGN.md), [review](source-review.json). All261 inherited files remain unchanged. A separate versioned host package stores exact shared bodies with bounded expansion and atomic references.18 fixture controls and one full actual worker/import scope are new.\n')
rows=inventory(STAGE,True);assert len(rows)==269
write(STAGE/'index.json',dict(scope='Versioned exact shared-body store, unchanged legacy/producer and full integration scope.',files=rows));pin=sha(STAGE/'index.json')
for i,target in enumerate(targets,1):
    process=target==process_target;prior=PROCESS if process else CONTROL
    h=BASE/('harness%02d'%i);h.mkdir();(h/'references').mkdir();borrowed=[]
    for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
        source=prior/name;dest=h/'references'/Path(name).name;shutil.copyfile(source,dest)
        borrowed.append(dict(source=source.relative_to(ROOT).as_posix(),copy=dest.relative_to(h).as_posix(),bytes=source.stat().st_size,sha256=sha(source)))
    write(h/'borrowed-inputs.json',borrowed);write(h/'targets.json',dict(testCount=1,targets=[target]))
    old_targets=read(prior/'targets.json')['targets'];old_method=old_targets[0].rsplit('.',1)[1];new_method=target.rsplit('.',1)[1]
    old_pin=read(prior/'review.json')['sourceIndexSha256']
    for name in ('run_attempt.py','attempt_child.py'):
        original=(prior/name).read_text();s=original.replace(old_pin,pin)
        s=s.replace('pat-io-bound-import/implementation01','pat-io-content-store/implementation01')
        for before,after in [('len(expected) != 264','len(expected) != 269'),("'frozenPreparationInputCount': 264","'frozenPreparationInputCount': 269"),
            ("'projectInputCount': 261","'projectInputCount': 266"),('len(selected) != 261','len(selected) != 266'),('exactly 261 files','exactly 266 files')]:s=s.replace(before,after)
        occurrences=s.count(repr(old_targets))
        if name=='attempt_child.py' and process:assert occurrences==0
        else:
            assert occurrences==1;s=s.replace(repr(old_targets),repr([target]))
        if process:s=s.replace(old_method,new_method)
        if name=='attempt_child.py':
            s=s.replace("name.startswith('evidence.')", "name.startswith('evidence.') or name == 'evidence_compact' or name.startswith('evidence_compact.')")
            assert "counts['testsRun'] == 1" in s
        ast.parse(s);(h/name).write_text(s)
        (h/(name+'.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile=str(prior/name),tofile=str(h/name))))
    scope=('One full30-case actual worker through compact import and historical replay; original limits.' if process else 'One exact shared-body control; successful worker/semantics are explicit fixtures.')
    (h/'SCOPE.md').write_text('# Exact scope\n\n'+scope+'\n\n[Target](targets.json), [source](../implementation01/README.md). Original180-second outer limit; '+('256MiB' if process else '16MiB')+' scratch and16MiB single-file ceilings.\n')
    (h/'README.md').write_text('# Compact evidence verification\n\n[Scope](SCOPE.md), [source](../implementation01/README.md).\n')
    write(h/'review.json',dict(scope=scope,tests=1,sourceIndexSha256=pin,targetSha256=sha(h/'targets.json'),
        inheritedHarnessIndexSha256=sha(prior/'index.json'),reviewed=review,independentReview=False,releasedBy='primary-agent',
        selectionKind='process' if process else 'control',sqliteConnectionsMaximum=6 if process else 3,
        scratchBytesCeiling=(256 if process else 16)*1024*1024,projectInputCount=266,frozenPreparationInputCount=269))
    write(h/'index.json',dict(scope=scope,files=inventory(h)))
print(json.dumps(dict(sourceIndexSha256=pin,unchangedInheritedProjectFiles=261,projectFiles=266,frozenFiles=269,controls=18,actualScopes=1,prepared=True)))
