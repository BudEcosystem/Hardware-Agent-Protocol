"""Freeze additive vault batch source, identities and the exact control list."""
import ast
import difflib
import hashlib
import importlib.metadata
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PRIOR=BASE.parent/'pat-business-precommit/implementation03';STAGE=BASE/'implementation01';PROJECT=STAGE/'project'
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(body if type(body)is bytes else body.encode())
def dump(path,value):put(path,json.dumps(value,indent=2)+'\n')
def canonical(value):
    def check(item):
        if type(item)is dict:
            assert all(type(key)is str and key.isascii() for key in item)
            for child in item.values():check(child)
        elif type(item)is list:
            for child in item:check(child)
        else:assert type(item)in(str,int,bool,type(None))
    check(value);return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
def digest(domain,value):return 'sha256:'+hashlib.sha256(domain+b'\0'+canonical(value)).hexdigest()
assert not (STAGE/'index.json').exists()
assert sha(PRIOR/'index.json')=='2f1d6c5aeaf63e960058f9b838b5ecd1080fc17d78f207f0d0b14c248da2dad4'
for row in read(PRIOR/'index.json')['files']:
    path=ROOT/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
baseline=read(STAGE/'baseline-inputs.json')['files'];assert len(baseline)==292
assert [r['path'] for r in baseline if sha(PROJECT/r['path'])!=r['sha256']]==['evidence_vault/connection.py','evidence_vault/store.py']
for name in ('connection.py','store.py'):
    old=(PRIOR/'project/evidence_vault'/name).read_text();new=(PROJECT/'evidence_vault'/name).read_text()
    before={n.name:n for n in ast.parse(old).body if isinstance(n,(ast.ClassDef,ast.FunctionDef))}
    after={n.name:n for n in ast.parse(new).body if isinstance(n,(ast.ClassDef,ast.FunctionDef))}
    if name=='connection.py':
        assert set(after)-set(before)=={'_BatchSnapshot'}
        for key,node in before.items():assert ast.dump(node)==ast.dump(after[key])
    else:
        assert set(before)==set(after)=={'EvidenceVault'}
        methods={n.name:n for n in after['EvidenceVault'].body if isinstance(n,ast.FunctionDef)}
        original={n.name:n for n in before['EvidenceVault'].body if isinstance(n,ast.FunctionDef)}
        assert set(methods)-set(original)=={'snapshot_many'}
        for key,node in original.items():assert ast.dump(node)==ast.dump(methods[key])
    put(BASE/(name+'.patch'),''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='prior/evidence_vault/'+name,tofile='batch/evidence_vault/'+name)))
selected=read(ROOT/'artifacts/implementation/pat-native-supervisor/harness02/references/approved-external-roots.json')
external={}
for pin in selected['selectedMetadata']:
    path=Path(pin['metadataPath']);assert sha(path)==pin['sha256'] and path.stat().st_size==pin['bytes']
    distribution=importlib.metadata.PathDistribution(path.parent);assert distribution.version==pin['version']
    for item in distribution.files or []:
        if item.is_absolute() or '..' in item.parts or '__pycache__' in item.parts:continue
        path=Path(distribution.locate_file(item))
        if path.is_file():external['dependencies/'+str(item)]=path
previous=read(PRIOR/'identity-pins.json');source_rows=[]
assert digest(b'HMS-PAT-IO-EVIDENCE-CONSUMER-v0.1',previous['sourceRows'])==previous['legacy']
for row in previous['sourceRows']:
    name=row['path'];path=external[name] if name.startswith('dependencies/') else PROJECT/name
    assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
    source_rows.append(row)
legacy=digest(b'HMS-PAT-IO-EVIDENCE-CONSUMER-v0.1',source_rows);assert legacy==previous['legacy']
def package(folder,names):
    return [dict(path=folder+'/'+name,bytes=(PROJECT/folder/name).stat().st_size,sha256=sha(PROJECT/folder/name)) for name in names]
vault=digest(b'HMS-PAT-EVIDENCE-VAULT-IMPLEMENTATION-v0.1',dict(legacyIdentity=legacy,sources=package('evidence_vault',('__init__.py','contracts.py','connection.py','store.py'))))
consumer=digest(b'HMS-PAT-VAULT-IMPORT-IMPLEMENTATION-v0.1',dict(vaultIdentity=vault,sources=package('evidence_authority',('__init__.py','contracts.py','store.py'))))
test=PROJECT/'tests/test_vault_original_run.py';body=test.read_text();assert body.count(previous['consumer'])==1
test.write_text(body.replace(previous['consumer'],consumer))
dump(STAGE/'identity-pins.json',dict(legacy=legacy,vault=vault,consumer=consumer,producerImageFiles=265,sourceRows=source_rows,actualRuntimeEqualityStillRequiresExecution=True))
tree=ast.parse((PROJECT/'tests/test_vault_batch.py').read_bytes())
batch=['test_vault_batch.'+cls.name+'.'+method.name for cls in tree.body if isinstance(cls,ast.ClassDef) for method in cls.body
    if isinstance(method,ast.FunctionDef) and method.name.startswith('test_')]
assert len(batch)>=20 and len(batch)==len(set(batch))
commit=['test_business_precommit.'+name for name in read(PRIOR/'test-selection.json')['newTests']]
single=['test_evidence_vault.VaultTests.'+name for name in (
    'test_snapshot_is_read_only_detached_and_expires_on_release',
    'test_snapshot_time_bound_invalidates_handle_and_cleans_transaction',
    'test_snapshot_owner_and_sqlite_reader_lock',
    'test_body_corruption_refuses_snapshot_and_reuse_without_repair',
    'test_before_commit_failure_retains_no_partial_manifest',
    'test_after_commit_reply_failure_reopens_original_manifest')]
assert len(commit)==29 and len(single)==6
dump(STAGE/'test-selection.json',dict(ids=batch+single+commit,batchTests=len(batch),singleSnapshotTests=len(single),businessCommitTests=len(commit),
    scope='New batch controls, existing relevant vault methods and all 29 business-commit controls; no worker, legacy crash suite or physical providers'))
dump(STAGE/'source-review.json',dict(reviewer='primary-agent',independentReview=False,
    changedInheritedFiles=['evidence_vault/connection.py','evidence_vault/store.py','tests/test_vault_original_run.py'],
    unchangedInheritedFiles=289,newFiles=['tests/test_vault_batch.py'],priorClassAndMethodAstsExact=True,
    journalSourceUnchanged=True,originalTestOnlyConsumerPinChanged=True,actualWorkerExecuted=False,
    publicRuntimeChanged=False,catalogIntegrated=False,physicalObjectiveVerified=False))
put(STAGE/'README.md','# Isolated vault batch candidate\n\n[Source review](source-review.json), [identities](identity-pins.json), [selected controls](test-selection.json). '
    'One new batch handle class and one vault method preserve the prior single-snapshot and Journal implementations. '
    'The retained full-worker test receives only a new consumer pin and is not run here.\n')
files=[]
for path in sorted(STAGE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        if path.suffix=='.py':ast.parse(path.read_bytes())
        files.append(dict(path=str(path.relative_to(ROOT)),bytes=path.stat().st_size,sha256=sha(path)))
dump(STAGE/'index.json',dict(scope='Additive bounded multi-manifest snapshot; catalog profile remains separate',files=files))
print(json.dumps(dict(frozenFiles=len(files),indexSha256=sha(STAGE/'index.json'),batchTests=len(batch),totalTests=len(batch+single+commit),vaultIdentity=vault,consumerIdentity=consumer)))
