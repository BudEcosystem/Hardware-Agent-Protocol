"""Freeze the business commit candidate without importing any project module."""
import ast
import difflib
import hashlib
import importlib.metadata
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PRIOR=BASE.parent/'pat-integer-canonical/implementation01'
STAGE=BASE/'implementation01';PROJECT=STAGE/'project'
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
    check(value)
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
def digest(domain,value):return 'sha256:'+hashlib.sha256(domain+b'\0'+canonical(value)).hexdigest()
assert not (STAGE/'index.json').exists()
assert sha(PRIOR/'index.json')=='387d33e2992d2862b1c21902b8de09195a56b569f52c3c3e04b84ce09b2d8849'
for row in read(PRIOR/'index.json')['files']:
    path=ROOT/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
baseline=read(STAGE/'baseline-inputs.json')['files'];assert len(baseline)==291
changed=[r['path'] for r in baseline if sha(PROJECT/r['path'])!=r['sha256']]
assert changed==['hms/journal.py']
old=(PRIOR/'project/hms/journal.py').read_text();new=(PROJECT/'hms/journal.py').read_text()
before={n.name:n for n in ast.parse(old).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
after={n.name:n for n in ast.parse(new).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
assert set(after)-set(before)=={'_CommitChecks'}
for name,node in before.items():
    if name!='Journal':assert ast.dump(node)==ast.dump(after[name])
prior_methods={n.name:n for n in before['Journal'].body if isinstance(n,ast.FunctionDef)}
new_methods={n.name:n for n in after['Journal'].body if isinstance(n,ast.FunctionDef)}
assert set(new_methods)-set(prior_methods)=={'_reject_commit_reentry','_require_at_commit','_check_business_commit'}
changed_methods=[name for name in prior_methods if ast.dump(prior_methods[name])!=ast.dump(new_methods[name])]
assert changed_methods==['__init__','close','_transaction','_clock']
put(BASE/'journal.py.patch',''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='prior/hms/journal.py',tofile='candidate/hms/journal.py')))
selected=read(ROOT/'artifacts/implementation/pat-native-supervisor/harness02/references/approved-external-roots.json')
external={}
for pin in selected['selectedMetadata']:
    path=Path(pin['metadataPath']);assert sha(path)==pin['sha256'] and path.stat().st_size==pin['bytes']
    distribution=importlib.metadata.PathDistribution(path.parent);assert distribution.version==pin['version']
    for item in distribution.files or []:
        if item.is_absolute() or '..' in item.parts or '__pycache__' in item.parts:continue
        path=Path(distribution.locate_file(item))
        if path.is_file():external['dependencies/'+str(item)]=path
previous=read(PRIOR/'identity-pins.json')
assert digest(b'HMS-PAT-IO-EVIDENCE-CONSUMER-v0.1',previous['sourceRows'])==previous['legacy']
source_rows=[]
for row in previous['sourceRows']:
    name=row['path'];prior=external[name] if name.startswith('dependencies/') else PRIOR/'project'/name
    assert sha(prior)==row['sha256'] and prior.stat().st_size==row['bytes']
    current=external[name] if name.startswith('dependencies/') else PROJECT/name
    source_rows.append(dict(path=name,bytes=current.stat().st_size,sha256=sha(current)))
assert len(source_rows)==270 and source_rows==sorted(source_rows,key=lambda row:row['path'])
def package(folder,names):
    return [dict(path=folder+'/'+name,bytes=(PROJECT/folder/name).stat().st_size,sha256=sha(PROJECT/folder/name)) for name in names]
legacy=digest(b'HMS-PAT-IO-EVIDENCE-CONSUMER-v0.1',source_rows)
vault=digest(b'HMS-PAT-EVIDENCE-VAULT-IMPLEMENTATION-v0.1',dict(legacyIdentity=legacy,sources=package('evidence_vault',('__init__.py','contracts.py','connection.py','store.py'))))
consumer=digest(b'HMS-PAT-VAULT-IMPORT-IMPLEMENTATION-v0.1',dict(vaultIdentity=vault,sources=package('evidence_authority',('__init__.py','contracts.py','store.py'))))
test=PROJECT/'tests/test_vault_original_run.py';body=test.read_text();assert body.count(previous['consumer'])==1
test.write_text(body.replace(previous['consumer'],consumer))
dump(STAGE/'identity-pins.json',dict(legacy=legacy,vault=vault,consumer=consumer,producerImageFiles=265,sourceRows=source_rows,actualRuntimeEqualityStillRequiresExecution=True))
new_tests=ast.parse((PROJECT/'tests/test_business_precommit.py').read_bytes())
ids=[cls.name+'.'+method.name for cls in new_tests.body if isinstance(cls,ast.ClassDef) for method in cls.body
    if isinstance(method,ast.FunctionDef) and method.name.startswith('test_')]
assert len(ids)==29
legacy_tests=ast.parse((PROJECT/'tests/test_journal.py').read_bytes())
excluded=['JournalTests.test_subprocess_crash_windows','JournalTests.test_interrupted_transactions_restore_atomic_state']
legacy_ids=[cls.name+'.'+method.name for cls in legacy_tests.body if isinstance(cls,ast.ClassDef) for method in cls.body
    if isinstance(method,ast.FunctionDef) and method.name.startswith('test_') and cls.name+'.'+method.name not in excluded]
dump(STAGE/'test-selection.json',dict(newTests=ids,legacyTests=legacy_ids,excludedLegacy=excluded,
    exclusionReason='This stage exercises host transaction checks; existing crash/subprocess recovery scopes are not rerun.'))
dump(STAGE/'source-review.json',dict(reviewer='primary-agent',independentReview=False,
    changedInheritedFiles=['hms/journal.py','tests/test_vault_original_run.py'],unchangedInheritedFiles=289,
    changedJournalMethods=changed_methods,newJournalMethods=sorted(set(new_methods)-set(prior_methods)),
    newFiles=['tests/test_business_precommit.py'],newTestMethods=len(ids),legacyTestMethods=len(legacy_ids),
    originalTestOnlyConsumerPinChanged=True,actualWorkerExecuted=False,publicRuntimeChanged=False,
    catalogIntegrated=False,physicalObjectiveVerified=False))
put(STAGE/'README.md','# Isolated business commit candidate\n\n[Source review](source-review.json), [identities](identity-pins.json), [test selection](test-selection.json). '
    'The Journal adds transaction-scoped final checks. All other inherited production source is unchanged; '
    'the retained original-worker test changes only its consumer pin and is not executed in this stage.\n')
files=[]
for path in sorted(STAGE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        if path.suffix=='.py':ast.parse(path.read_bytes())
        files.append(dict(path=str(path.relative_to(ROOT)),bytes=path.stat().st_size,sha256=sha(path)))
dump(STAGE/'index.json',dict(scope='Business precommit checks; bounded host tests, not catalog integration or actual worker',files=files))
print(json.dumps(dict(frozenFiles=len(files),indexSha256=sha(STAGE/'index.json'),newTests=len(ids),legacyTests=len(legacy_ids),consumerIdentity=consumer)))
