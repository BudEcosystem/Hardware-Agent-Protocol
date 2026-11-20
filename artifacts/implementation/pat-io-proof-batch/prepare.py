"""Freeze the reviewed candidate and one exact pure regression scope."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
STAGE=BASE/'implementation01';PROJECT=STAGE/'project';HARNESS=BASE/'harness01'
SOURCE=ROOT/'artifacts/implementation/pat-vault-original-run/implementation02'
TEMPLATE=ROOT/'artifacts/implementation/pat-io-definition-build/harness04'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_bytes())
def write(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(body if type(body)is bytes else body.encode())
def dump(path,value):write(path,json.dumps(value,indent=2)+'\n')
def inventory(folder,prefix):
    rows=[]
    for path in sorted(folder.rglob('*')):
        assert not path.is_symlink()
        if path.is_file():
            if path.suffix=='.py':ast.parse(path.read_bytes())
            rows.append(dict(path=path.relative_to(prefix).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    return rows
def function(path,name):return next(n for n in ast.parse(path.read_bytes()).body if isinstance(n,ast.FunctionDef) and n.name==name)
def methods(module,cls):
    node=next(n for n in ast.parse((PROJECT/'tests'/(module+'.py')).read_bytes()).body if isinstance(n,ast.ClassDef) and n.name==cls)
    return sorted(module+'.'+cls+'.'+n.name for n in node.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
assert not (STAGE/'index.json').exists() and not HARNESS.exists()
assert sha(SOURCE/'index.json')=='4a1f5b97cb29e897fc865ca5dcf46397bfdec6c4154a302dfdac1b546e66c4f4'
baseline=read(STAGE/'baseline-inputs.json')['files'];assert len(baseline)==286
changed=[]
for row in baseline:
    assert sha(SOURCE/'project'/row['path'])==row['sha256']
    if sha(PROJECT/row['path'])!=row['sha256']:changed.append(row['path'])
assert set(changed)=={'hms/resource_topology.py','hms/synthetic_io_installation.py','tests/test_pat_io_definition_build.py','tests/test_vault_original_run.py'}
assert len(inventory(PROJECT,PROJECT))==288
for name,path,reference in (('definitions','hms/synthetic_io_installation.py','reference_definitions'),('binding_proof','hms/resource_topology.py','reference_binding_proof')):
    old=function(SOURCE/'project'/path,name);old.name=reference
    assert ast.dump(old)==ast.dump(function(PROJECT/'tests/_reference_definition_build.py',reference))
# The entire original derivation tail is factored, not rewritten.
old=function(SOURCE/'project/hms/resource_topology.py','binding_proof')
tail=next(i for i,n in enumerate(old.body) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='details')
new=function(PROJECT/'hms/resource_topology.py','_binding_proof_from_validated')
assert [ast.dump(n) for n in old.body[tail:]]==[ast.dump(n) for n in new.body]
targets=[]
for module,cls in (('test_pat_io_definition_build','DefinitionBuildTests'),('test_pat_io_installation_reuse','InstallationReuseTests'),
    ('test_resource_topology','ResourceTopologyTests'),('test_resource_schema_memo','ResourceSchemaMemoTests'),('test_pat_io_proof_batch','ProofBatchTests')):
    targets+=methods(module,cls)
assert len(targets)==63 and len(set(targets))==63
review=dict(reviewer='primary-agent',independentReview=False,projectExecutedDuringPreparation=False,
    changedProductionFiles=['hms/resource_topology.py','hms/synthetic_io_installation.py'],
    changedTestFiles=['tests/test_pat_io_definition_build.py','tests/test_vault_original_run.py'],unchangedInheritedProjectFiles=282,
    newTestFiles=['tests/_reference_definition_build.py','tests/test_pat_io_proof_batch.py'],
    baselineReferenceAstVerified=True,proofDerivationTailAstUnchanged=True,pureTests=63,
    localLifetime='One definitions call only; immutable input and pure helpers throughout the call',
    firstHandlerLookupPrecedesValidation=True,publicProofCallsFresh=True,perInstanceProofSchemaAndBoundsRetained=True,
    authoritySourceOrEffectChecksCached=False,originalWorkerCases=30,workerMaxWallMs=60000,parentMaxSeconds=180,
    pureSqliteConnections=0,pureSubprocesses=0,pureNetwork=False,physicalMcuInferenceOrServiceExecution=False,
    actualIntegrationNotYetRun=True,consumerPin=read(STAGE/'identity-pins.json')['consumer'])
dump(STAGE/'source-review.json',review)
write(STAGE/'README.md','# One-call resource-proof build candidate\n\n[Design](../DESIGN.md), [source review](source-review.json), [identity pins](identity-pins.json). Two production modules change; 282 inherited project files remain exact. Two baseline test files change only instrumentation targets and the current original-run consumer pin. Two new test/reference modules support exact differential comparison. No actual worker or physical qualification is claimed before execution.\n')
rows=inventory(STAGE,ROOT);assert len(rows)==292
dump(STAGE/'index.json',dict(scope='One validated static topology/generation snapshot within a pure definition build',files=rows))
pin=sha(STAGE/'index.json')
prior=TEMPLATE.parent;assert sha(prior/'index.json')=='c38169d02e04a3fbb72a50ea4ccd285683ed79834da2e9d9cd32fe5b10f1fe02'
entry=next(r for r in read(prior/'index.json')['files'] if r['path']=='harness04/index.json')
assert sha(TEMPLATE/'index.json')==entry['sha256']
for row in read(TEMPLATE/'index.json')['files']:
    path=TEMPLATE/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
borrowed=[];old_targets=read(TEMPLATE/'targets.json')['targets']
for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
    path=TEMPLATE/name;copy='references/'+Path(name).name
    write(HARNESS/copy,path.read_bytes())
    borrowed.append(dict(source=path.relative_to(ROOT).as_posix(),copy=copy,bytes=path.stat().st_size,sha256=sha(path)))
    if not name.endswith('.py'):continue
    original=path.read_text();updated=original
    if name=='run_attempt.py':
        updated=updated.replace('7a52bf04800bde161cfb778fca0da5cec996468fe03d9944902e73e11c6817cc',pin)
        updated=updated.replace('artifacts/implementation/pat-io-definition-build/implementation01/','artifacts/implementation/pat-io-proof-batch/implementation01/')
        updated=re.sub(r'\b275\b','288',updated);updated=re.sub(r'\b278\b','292',updated)
        updated=updated.replace("prefix='hms-io-snapshot-reuse-runs15-'","prefix='hms-io-proof-batch-pure-'")
    assert updated.count(repr(old_targets))==1
    updated=updated.replace(repr(old_targets),repr(targets));updated=re.sub(r'\b21\b','63',updated)
    ast.parse(updated);write(HARNESS/name,updated)
    write(HARNESS/(name+'.patch'),''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),fromfile='reviewed-pure/'+name,tofile='proof-batch/'+name)))
dump(HARNESS/'borrowed-inputs.json',borrowed)
dump(HARNESS/'targets.json',dict(testCount=63,targets=targets))
write(HARNESS/'README.md','# Pure proof-build controls\n\n[Scope](SCOPE.md), [source](../implementation01/README.md), [targets](targets.json).\n')
write(HARNESS/'SCOPE.md','# Exact pure scope\n\n63 methods: 21 inherited definition/normalization controls, 21 topology controls, 11 schema-memo controls, and ten new proof-build controls. One fixed seven-pair timing observation runs eight pure builds per sample. No authority, database, subprocess, worker, network, model, MCU or physical device runs.\n\nOriginal bounds remain: 180-second parent wait, 16 MiB single-file/scratch, 8,192 inventory files, 8 MiB log. Selected project/dependency origins and before/after bytes remain checked. Startup standard library and dynamic system libraries are not a full pinned closure, and audit hooks are cooperative guardrails rather than an OS sandbox.\n')
dump(HARNESS/'review.json',review|dict(sourceIndexSha256=pin,templateIndexSha256=sha(TEMPLATE/'index.json')))
dump(HARNESS/'index.json',dict(scope='63 exact pure controls; no worker or physical execution',files=inventory(HARNESS,HARNESS)))
print(json.dumps(dict(projectFiles=288,frozenFiles=292,sourceIndexSha256=pin,harnessIndexSha256=sha(HARNESS/'index.json'),pureTests=63)))
