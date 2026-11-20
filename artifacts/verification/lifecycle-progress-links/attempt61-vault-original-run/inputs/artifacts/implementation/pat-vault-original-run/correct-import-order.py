"""Retain the startup failure; change only the new test's import ordering."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
OLD=BASE/'implementation01'; NEW=BASE/'implementation02'
PRIOR=BASE/'harness01'; HARNESS=BASE/'harness02'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream: stream.write(body if type(body) is bytes else body.encode())
def dump(path,value): write(path,json.dumps(value,indent=2)+'\n')
assert sha(OLD/'index.json')=='14e33c595526a7a7d626d635dcff7327fef65e9a94b28c85b7d43a109b212414'
assert sha(PRIOR/'index.json')=='dcf60daa4c4e39426c51aa3ac2a1679799a37a8f3b0ba91d07f682b9017f2ea3'
attempt=PRIOR/'attempts/attempt01-actual'; result=read(attempt/'result.json')
assert result['status']=='failed' and result['childState']=='exited' and result['counts'] is None
assert result['scratchRetainedBytes']==0 and read(attempt/'sqlite-connections.json')==[]
assert 'ModuleNotFoundError: No module named \'attempt_ledger\'' in (attempt/'output.log').read_text()
NEW.mkdir()
for row in read(OLD/'index.json')['files']:
    source=ROOT/row['path']; assert source.stat().st_size==row['bytes'] and sha(source)==row['sha256']
    relative=source.relative_to(OLD)
    if relative.parts[0]=='project' or relative.as_posix()=='baseline-inputs.json': write(NEW/relative,source.read_bytes())
test=NEW/'project/tests/test_vault_original_run.py'; before=test.read_text()
line='from test_io_service_execution import IoServiceExecutionTests\n'
assert before.count(line)==1
after=before.replace(line,'').replace('from evidence import archive, reducer\n',line+'\nfrom evidence import archive, reducer\n')
old_cls=next(node for node in ast.parse(before).body if isinstance(node,ast.ClassDef))
new_cls=next(node for node in ast.parse(after).body if isinstance(node,ast.ClassDef))
assert ast.dump(old_cls)==ast.dump(new_cls)
test.write_text(after)
old_project={p.relative_to(OLD/'project').as_posix():sha(p) for p in (OLD/'project').rglob('*') if p.is_file()}
new_project={p.relative_to(NEW/'project').as_posix():sha(p) for p in (NEW/'project').rglob('*') if p.is_file()}
assert len(old_project)==len(new_project)==286
assert {name for name in old_project if old_project[name]!=new_project[name]}=={'tests/test_vault_original_run.py'}
write(NEW/'README.md','# Actual original-run source: import-order correction\n\nThe initial scope failed before loading a test, opening SQLite or launching a worker. This fresh copy imports the inherited execution fixture before the evidence package so its existing supervisor path setup is available. Only the new test module changes; its complete class AST is identical. All 285 other project files, including production and all prior actual-run sources, remain unchanged. No scope or bound changes.\n')
write(NEW/'source-review.json',(OLD/'source-review.json').read_bytes())
dump(NEW/'correction.json',dict(priorSourceIndexSha256=sha(OLD/'index.json'),
    failedAttempt='harness01/attempts/attempt01-actual',failure='Missing supervisor module path during test loading',
    changedProjectFiles=['tests/test_vault_original_run.py'],unchangedProjectFiles=285,
    testClassAstIdentical=True,productionChanged=False,workerExecutedInFailedScope=False,
    sqliteOpensInFailedScope=0,scratchBytesInFailedScope=0,boundsChanged=False))
files=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(NEW.rglob('*')) if p.is_file()]
assert len(files)==290
dump(NEW/'index.json',dict(scope='Import-order-only correction; actual-run fixture body and all production unchanged',files=files))
HARNESS.mkdir()
for row in read(PRIOR/'index.json')['files']:
    path=PRIOR/row['path']; assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
    if row['path'] in ('run_attempt.py','run_attempt.py.patch','README.md','SCOPE.md'): continue
    write(HARNESS/row['path'],path.read_bytes())
before=(PRIOR/'run_attempt.py').read_text()
after=before.replace(sha(OLD/'index.json'),sha(NEW/'index.json')).replace('implementation01','implementation02').replace('289','290')
ast.parse(after)
write(HARNESS/'run_attempt.py',after)
write(HARNESS/'run_attempt.py.patch',''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='harness01/run_attempt.py',tofile='harness02/run_attempt.py')))
write(HARNESS/'README.md','# Corrected actual original-run scope\n\n[Source](../implementation02/README.md), [bounds](SCOPE.md), [target](targets.json). Initial loading failure remains retained in harness01.\n')
write(HARNESS/'SCOPE.md',(PRIOR/'SCOPE.md').read_text()+'\nThis fresh scope changes only source selection to the import-order-corrected fixture. All method bodies, production and execution/storage limits remain unchanged.\n')
files=[dict(path=p.relative_to(HARNESS).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(HARNESS.rglob('*')) if p.is_file()]
dump(HARNESS/'index.json',dict(scope='Actual original-run scope after isolated test-loader correction',files=files))
dump(BASE/'startup-failure.json',dict(attempt='harness01/attempts/attempt01-actual',status='failed',
    resultSha256=sha(attempt/'result.json'),logSha256=sha(attempt/'output.log'),
    testsExecuted=0,sqliteOpens=0,workerExecuted=False,rawScratchRetained=True,
    correction='implementation02',freshScope='harness02',originalAttemptRetried=False))
print(json.dumps(dict(sourceIndexSha256=sha(NEW/'index.json'),harnessIndexSha256=sha(HARNESS/'index.json'),productionChanged=False,testBodyChanged=False)))
