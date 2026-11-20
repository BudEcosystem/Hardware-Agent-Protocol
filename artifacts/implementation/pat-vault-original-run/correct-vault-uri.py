"""Recognize the already-declared vault's exact production URI; keep all bounds."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
OLD=BASE/'harness02'; NEW=BASE/'harness03'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream: stream.write(body if type(body) is bytes else body.encode())
def dump(path,value): write(path,json.dumps(value,indent=2)+'\n')
assert sha(OLD/'index.json')=='fb7c98f67057baaec11152acff67d6eaac71eacb99e56b0df69579be837f83cf'
attempt=OLD/'attempts/attempt01-actual'; result=read(attempt/'result.json')
assert result['status']=='failed' and result['childState']=='exited' and result['counts']['errors']==1
assert read(attempt/'writer-quiescence.json')['records']==[]
assert len(read(attempt/'sqlite-connections.json'))==3
assert 'Only exact authority/runtime/supervisor/vault databases may open' in (attempt/'output.log').read_text()
NEW.mkdir()
for row in read(OLD/'index.json')['files']:
    path=OLD/row['path']; assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
    if row['path'] in ('attempt_child.py','attempt_child.py.patch','README.md','SCOPE.md'): continue
    write(NEW/row['path'],path.read_bytes())
before=(OLD/'attempt_child.py').read_text()
old="        path = Path(os.fsdecode(os.fspath(args[0])))\n        work=scratch/'test_actual_original_matrix_import_and_cold_vault_history'\n"
new="        supplied = os.fsdecode(os.fspath(args[0]))\n        work=scratch/'test_actual_original_matrix_import_and_cold_vault_history'\n        vault = work/'vault'/'evidence.db'\n        path = vault if supplied == vault.as_uri() + '?mode=rw' else Path(supplied)\n"
assert before.count(old)==1
after=before.replace(old,new).replace("'database':str(path)}", "'database':str(path),'supplied':supplied}")
ast.parse(after)
write(NEW/'attempt_child.py',after)
write(NEW/'attempt_child.py.patch',''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='harness02/attempt_child.py',tofile='harness03/attempt_child.py')))
write(NEW/'README.md','# Actual original-run scope with exact vault URI\n\n[Source](../implementation02/README.md), [bounds](SCOPE.md), [target](targets.json). Both prior failures remain retained.\n')
write(NEW/'SCOPE.md',(OLD/'SCOPE.md').read_text()+'\nThe harness recognizes only the declared vault path in its exact production `file:` URI spelling with `mode=rw`. It does not parse or admit arbitrary URI authorities, queries, fragments or alternate paths. The six-open limit, source, method and all other bounds are unchanged.\n')
files=[dict(path=p.relative_to(NEW).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(NEW.rglob('*')) if p.is_file()]
dump(NEW/'index.json',dict(scope='Exact declared vault URI mapping; unchanged source and limits',files=files))
dump(BASE/'vault-uri-failure.json',dict(attempt='harness02/attempts/attempt01-actual',
    status='failed',resultSha256=sha(attempt/'result.json'),logSha256=sha(attempt/'output.log'),
    testsRun=1,errors=1,sqliteOpens=3,workerExecuted=False,originalStateRetained=True,
    sourceUnchanged=True,pathSetUnchanged=True,sqliteOpenLimit=6,otherBoundsUnchanged=True,
    freshScope='harness03',originalAttemptRetried=False))
print(json.dumps(dict(harnessIndexSha256=sha(NEW/'index.json'),sourceChanged=False,pathSetChanged=False,boundsChanged=False)))
