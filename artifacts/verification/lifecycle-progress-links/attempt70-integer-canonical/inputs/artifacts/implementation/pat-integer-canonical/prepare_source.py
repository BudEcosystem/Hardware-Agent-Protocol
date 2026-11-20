"""Freeze one-module canonicalization integration with independent identities."""
import ast
import difflib
import hashlib
import importlib.metadata
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PRIOR=BASE.parent/'pat-native-supervisor/implementation02'
PURE=ROOT/'artifacts/verification/pat-integer-canonical-evaluation'
STAGE=BASE/'implementation01';PROJECT=STAGE/'project'
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(body if type(body)is bytes else body.encode())
def dump(path,value):put(path,json.dumps(value,indent=2)+'\n')
def canonical(value):
    # Independently encoded identity envelopes have only ASCII keys and no floats.
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
assert not STAGE.exists()
assert sha(PRIOR/'index.json')=='255b919194d150572c7b7876d941fb2e7d5866e36cdc119e91608da4b85ddc18'
assert sha(PURE/'index.json')=='158a1b49bc13291eaf24a59f2bc47ba6cceff5a0c86b476e95a96c6ce1edd9de'
for folder,prefix in ((PRIOR,ROOT),(PURE,PURE)):
    for row in read(folder/'index.json')['files']:
        path=prefix/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
assert read(PURE/'RESULTS.json')['allNinePairsLower'] and read(PURE/'RESULTS.json')['differentialCases']==1668
baseline=[]
for path in sorted((PRIOR/'project').rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        relative=str(path.relative_to(PRIOR/'project'));put(PROJECT/relative,path.read_bytes())
        baseline.append(dict(path=relative,bytes=path.stat().st_size,sha256=sha(path)))
assert len(baseline)==291
dump(STAGE/'baseline-inputs.json',dict(sourceIndexSha256=sha(PRIOR/'index.json'),files=baseline))
path=PROJECT/'hms/contracts.py';old=path.read_text()
helper=(PURE/'candidate_helpers.py').read_text()
helper_tree=ast.parse(helper)
# Omit only the standalone evaluation file's module docstring; retain every node.
assert isinstance(helper_tree.body[0],ast.Expr) and type(helper_tree.body[0].value.value)is str
helper='\n'.join(helper.splitlines()[helper_tree.body[0].end_lineno:]).lstrip('\n')
assert old.count('result = rfc8785.dumps(value)')==1 and old.count('\n_SCHEMA =')==1
new=old.replace('result = rfc8785.dumps(value)','result = _canonical_bytes(value)')
new=new.replace('\n_SCHEMA =','\n# Integer-only canonical byte path; original validation and float fallback remain.\n'+helper+'\n\n_SCHEMA =')
ast.parse(new);path.write_text(new)
new_nodes={n.name:n for n in ast.parse(new).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
for n in helper_tree.body:
    if isinstance(n,(ast.FunctionDef,ast.ClassDef)):assert ast.dump(n)==ast.dump(new_nodes[n.name])
for n in ast.parse(old).body:
    if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name!='canonical':assert ast.dump(n)==ast.dump(new_nodes[n.name])
put(BASE/'contracts.py.patch',''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='native-source/hms/contracts.py',tofile='canonical-source/hms/contracts.py')))
selected=read(PRIOR.parent/'harness02/references/approved-external-roots.json')
external={}
for pin in selected['selectedMetadata']:
    metadata_path=Path(pin['metadataPath'])
    assert sha(metadata_path)==pin['sha256'] and metadata_path.stat().st_size==pin['bytes']
    distribution=importlib.metadata.PathDistribution(metadata_path.parent)
    assert distribution.version==pin['version']
    for item in distribution.files or []:
        if item.is_absolute() or '..' in item.parts or '__pycache__' in item.parts:continue
        item_path=Path(distribution.locate_file(item))
        if item_path.is_file():external['dependencies/'+str(item)]=item_path
previous=read(PRIOR/'identity-pins.json')
assert digest(b'HMS-PAT-IO-EVIDENCE-CONSUMER-v0.1',previous['sourceRows'])==previous['legacy']
source_rows=[]
for row in previous['sourceRows']:
    name=row['path'];old_path=external[name] if name.startswith('dependencies/') else PRIOR/'project'/name
    assert sha(old_path)==row['sha256'] and old_path.stat().st_size==row['bytes']
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
changed=[row['path'] for row in baseline if sha(PROJECT/row['path'])!=row['sha256']]
assert changed==['hms/contracts.py','tests/test_vault_original_run.py']
dump(STAGE/'source-review.json',dict(reviewer='primary-agent',independentReview=False,changedInheritedFiles=changed,
    unchangedInheritedFiles=289,newFiles=[],pureEvaluationIndexSha256=sha(PURE/'index.json'),pureDifferentialCases=1668,
    helperAstsExact=True,originalValidationAndParserAstsExact=True,originalTestOnlyConsumerPinChanged=True,
    nativeScannerAndSupervisorUnchanged=True,caseMatrix=30,workerMaxWallMs=60000,parentMaxSeconds=180,
    publicRuntimeChanged=False,actualScopeNotYetExecuted=True))
put(STAGE/'README.md','# Isolated canonicalization candidate\n\n[Source review](source-review.json), [identities](identity-pins.json). '
    'One inherited production module selects the guarded integer-only byte path; the original complete test changes only its consumer pin. '
    'The other 289 inherited files remain exact. Full qualification is recorded separately.\n')
files=[]
for path in sorted(STAGE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        if path.suffix=='.py':ast.parse(path.read_bytes())
        files.append(dict(path=str(path.relative_to(ROOT)),bytes=path.stat().st_size,sha256=sha(path)))
assert len(files)==295
dump(STAGE/'index.json',dict(scope='One-module guarded integer canonicalization; complete original test except consumer pin',files=files))
print(json.dumps(dict(projectFiles=291,frozenFiles=295,indexSha256=sha(STAGE/'index.json'),consumerIdentity=consumer)))
