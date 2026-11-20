"""Retain exact original scan/audit source and completed-scope association."""
import ast
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PRIOR=ROOT/'artifacts/verification/pat-worker-accounting'
SOURCE=ROOT/'artifacts/implementation/pat-io-proof-batch/implementation01'
ATTEMPT=PRIOR/'harness02/attempts/attempt01-accounting'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_bytes())
def write(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(body if type(body)is bytes else body.encode())
def dump(path,value):write(path,json.dumps(value,indent=2)+'\n')
assert not (BASE/'inputs.json').exists()
assert sha(PRIOR/'index.json')=='4dd93fabdeb7d0f5e118777b417fea6221fe90399443358225b4cfb84e713e19'
assert sha(SOURCE/'index.json')=='a7e03e59584b61e09efe40fbd093c423acfdc4c037c6d5d24273019bdda3f2b5'
source_pins={row['path']:row for row in read(SOURCE/'index.json')['files']}
prior_pins={row['path']:row for row in read(PRIOR/'index.json')['files']}
selected={
    'journal.py':(SOURCE/'project/hms/journal.py',('JournalError',)),
    'supervisor_contracts.py':(SOURCE/'project/supervisor/supervisor_contracts.py',('SupervisorError','require')),
    'attempt_ledger.py':(SOURCE/'project/supervisor/attempt_ledger.py',('tree_usage',)),
    'attempt_child.py':(PRIOR/'harness02/attempt_child.py',('sha','remember','is_stdlib','audit')),
}
extracted=[];borrowed=[]
for name,(path,names) in selected.items():
    lookup=source_pins.get(path.relative_to(ROOT).as_posix()) if path.is_relative_to(SOURCE) else prior_pins[path.relative_to(PRIOR).as_posix()]
    assert lookup['sha256']==sha(path) and lookup['bytes']==path.stat().st_size
    body=path.read_bytes();write(BASE/'references'/name,body)
    nodes={node.name:node for node in ast.parse(body).body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
    for function in names:
        node=nodes[function];extracted.append(dict(source=name,name=function,astSha256=hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()))
    borrowed.append(dict(source=path.relative_to(ROOT).as_posix(),copy='references/'+name,sha256=sha(path),bytes=len(body)))
for name,path in (
    ('original-result.json',PRIOR/'RESULTS.json'),('original-accounting.json',ATTEMPT/'worker-accounting.json'),
    ('original-child-config.json',ATTEMPT/'child-config.json'),('original-raw-identity.json',ATTEMPT/'raw-scratch-before.json'),
    ('original-worker-archive.json',ATTEMPT/'scratch/test_actual_original_matrix_import_and_cold_vault_history/worker-archive.json'),
    ('original-input.json',ATTEMPT/'scratch/test_actual_original_matrix_import_and_cold_vault_history/supervisor/c00ffb566da8416aa10f99a8be4033c4/input.json')):
    row=prior_pins[path.relative_to(PRIOR).as_posix()]
    assert sha(path)==row['sha256'] and path.stat().st_size==row['bytes']
    write(BASE/'references'/name,path.read_bytes());borrowed.append(dict(source=path.relative_to(ROOT).as_posix(),copy='references/'+name,sha256=sha(path),bytes=path.stat().st_size))
dump(BASE/'preparation.json',dict(scope='Exact-source read-only scan and audit-callback comparison',
    reviewer='primary-agent',independentReview=False,priorStageSha256=sha(PRIOR/'index.json'),
    sourceIndexSha256=sha(SOURCE/'index.json'),borrowed=borrowed,extracted=extracted,
    originalWorkerRerun=False,caseDatabaseReads=0))
for name in ('evaluate.py','prepare.py'):ast.parse((BASE/name).read_text())
rows=[]
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():rows.append(dict(path=path.relative_to(BASE).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
dump(BASE/'inputs.json',dict(scope='Frozen preparation before the single bounded evaluation',files=rows))
print(json.dumps(dict(files=len(rows),functions=len(extracted),inputsSha256=sha(BASE/'inputs.json'))))
