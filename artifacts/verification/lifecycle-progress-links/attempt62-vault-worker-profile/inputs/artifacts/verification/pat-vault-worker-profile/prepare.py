"""Prepare a diagnostic of the current worker; no project code runs here."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
SOURCE=ROOT/'artifacts/implementation/pat-vault-original-run/implementation02'
PROFILE=ROOT/'artifacts/implementation/pat-io-catalog-worker-profile/implementation01'
TEMPLATE=ROOT/'artifacts/implementation/pat-io-definition-build/harness02'
STAGE=BASE/'implementation01'; HARNESS=BASE/'harness01'
SOURCE_PIN='4a1f5b97cb29e897fc865ca5dcf46397bfdec6c4154a302dfdac1b546e66c4f4'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream: stream.write(body if type(body)is bytes else body.encode())
def dump(path,value): write(path,json.dumps(value,indent=2)+'\n')
assert sha(SOURCE/'index.json')==SOURCE_PIN
assert sha(PROFILE/'index.json')=='edc5f4dd343334eb46f78e640036e8d922e1a577b28aef20373f144619982535'
STAGE.mkdir(); baseline=[]
for row in read(SOURCE/'index.json')['files']:
    source=ROOT/row['path']; assert source.stat().st_size==row['bytes'] and sha(source)==row['sha256']
    if source.is_relative_to(SOURCE/'project'):
        relative=source.relative_to(SOURCE/'project'); write(STAGE/'project'/relative,source.read_bytes())
        baseline.append(dict(path=relative.as_posix(),bytes=row['bytes'],sha256=row['sha256']))
assert len(baseline)==286
profile_path=PROFILE/'project/supervisor/worker_entry.py'
profile_row=next(row for row in read(PROFILE/'index.json')['files'] if row['path']==profile_path.relative_to(ROOT).as_posix())
assert sha(profile_path)==profile_row['sha256']
profile_text=profile_path.read_text()
node=next(node for node in ast.parse(profile_text).body if isinstance(node,ast.FunctionDef) and node.name=='_profile_group')
function=ast.get_source_segment(profile_text,node)
entry=STAGE/'project/supervisor/worker_entry.py'; original=entry.read_text()
assert original.count('\ndef main():\n')==1
updated=original.replace('\ndef main():\n','\n'+function+'\n\ndef main():\n')
old="    result = run_io_group(attempt / 'output', candidate=inputs['candidate'], installation=inputs['installation'],\n        descriptor=inputs['descriptor'], challenge_bindings=inputs['bindings'], limits=request['groupLimits'])"
new="    result = _profile_group(directory, lambda: run_io_group(attempt / 'output', candidate=inputs['candidate'], installation=inputs['installation'],\n        descriptor=inputs['descriptor'], challenge_bindings=inputs['bindings'], limits=request['groupLimits']))"
assert updated.count(old)==1; updated=updated.replace(old,new); ast.parse(updated); entry.write_text(updated)
changes=[row['path'] for row in baseline if sha(STAGE/'project'/row['path'])!=row['sha256']]
assert changes==['supervisor/worker_entry.py']
for path in (STAGE/'project').rglob('*.py'): ast.parse(path.read_bytes(),filename=str(path))
write(BASE/'worker-instrumentation.patch',''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),fromfile='current/worker_entry.py',tofile='diagnostic/worker_entry.py')))
dump(STAGE/'baseline-inputs.json',dict(sourceIndexSha256=SOURCE_PIN,files=baseline,changedFiles=changes,
    unchangedProjectFiles=285,profileFunctionSource=profile_row))
dump(STAGE/'source-review.json',dict(diagnosticOnly=True,reviewer='primary-agent',independentReview=False,
    projectExecutionDuringPreparation=False,changedFiles=changes,unchangedProjectFiles=285,
    profileScope='Original run_io_group after original launch/bundle checks',
    signalBehavior='Require default SIGTERM; bounded report; restore default and raise SIGTERM to self; original supervisor escalation unchanged',
    maximumProfileEntries=8192,maximumLabelCharacters=512,retainedCumulativeRows=40,retainedSelfRows=40,
    workerMaxWallMs=60000,outerMaxSeconds=180,sqliteConnectionsMaximum=6,
    maxSingleFileBytes=16777216,maxScratchBytes=268435456,
    selectedTest='Unchanged actual compact-catalog process test; one complete 30-case worker and at most its one simulated application',
    previousActualVaultFailureRetained=True,productionAdoptionPermitted=False,
    inferencePhysicalServiceOrMcuExecution=False,timeoutRootCauseClaimed=False))
write(STAGE/'README.md','# Current worker diagnostic source\n\nAll 285 other project files remain exact. Only the worker entry gains the previously reviewed bounded profiler. The original 30-case actual compact-catalog test remains unchanged; the separate authority-vault fixture is not selected. The diagnostic handler must not enter production, and timing does not qualify physical behavior.\n')
rows=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(STAGE.rglob('*')) if p.is_file()]
assert len(rows)==289
dump(STAGE/'index.json',dict(scope='Diagnostic current-worker profile; original failure and limits preserved',files=rows))
pin=sha(STAGE/'index.json')
prior_root=TEMPLATE.parent
assert sha(prior_root/'index.json')=='c38169d02e04a3fbb72a50ea4ccd285683ed79834da2e9d9cd32fe5b10f1fe02'
prior_index=next(row for row in read(prior_root/'index.json')['files'] if row['path']=='harness02/index.json')
assert sha(TEMPLATE/'index.json')==prior_index['sha256']
for row in read(TEMPLATE/'index.json')['files']:
    path=TEMPLATE/row['path']; assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
HARNESS.mkdir(); borrowed=[]
for name in ('run_attempt.py','attempt_child.py'):
    path=TEMPLATE/name; original=path.read_text(); updated=original
    if name=='run_attempt.py':
        updated=updated.replace('7a52bf04800bde161cfb778fca0da5cec996468fe03d9944902e73e11c6817cc',pin)
        updated=updated.replace('artifacts/implementation/pat-io-definition-build/implementation01/','artifacts/verification/pat-vault-worker-profile/implementation01/')
        updated=re.sub(r'\b275\b','286',updated); updated=re.sub(r'\b278\b','289',updated)
        updated=updated.replace("prefix='hms-io-definition-build-'","prefix='hms-vault-worker-profile-'")
    ast.parse(updated); write(HARNESS/name,updated); write(HARNESS/'references'/name,original)
    write(HARNESS/(name+'.patch'),''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),fromfile='prior-actual/'+name,tofile='current-diagnostic/'+name)))
    borrowed.append(dict(source=path.relative_to(ROOT).as_posix(),copy='references/'+name,bytes=path.stat().st_size,sha256=sha(path)))
path=TEMPLATE/'references/approved-external-roots.json'; write(HARNESS/'references/approved-external-roots.json',path.read_bytes())
borrowed.append(dict(source=path.relative_to(ROOT).as_posix(),copy='references/approved-external-roots.json',bytes=path.stat().st_size,sha256=sha(path)))
dump(HARNESS/'borrowed-inputs.json',borrowed); write(HARNESS/'targets.json',(TEMPLATE/'targets.json').read_bytes())
write(HARNESS/'README.md','# Current worker diagnostic\n\n[Source](../implementation01/README.md), [scope](SCOPE.md), [selection](targets.json). No original failed logical run is restarted.\n')
write(HARNESS/'SCOPE.md','# Diagnostic scope\n\nOne unchanged actual compact-catalog process test on the current source plus bounded worker instrumentation. All 30 requested cases remain. If the original test reaches application execution, its existing one simulated application and eight ticks remain the ceiling. This is not an authority-vault import proof.\n\nOriginal limits remain: 60-second worker, 180-second parent wait, six parent SQLite opens, 16 MiB single file, 256 MiB scratch, 8,192 files, 8 MiB log. The profile covers run_io_group, saves at most 40 cumulative and 40 self-time rows, and re-raises SIGTERM after bounded collection. Supervisor ownership and escalation are unchanged. Original raw state and exact copies remain retained; no physical, network, model, MCU or live service execution.\n')
rows=[dict(path=p.relative_to(HARNESS).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(HARNESS.rglob('*')) if p.is_file()]
dump(HARNESS/'index.json',dict(scope='Current-worker bounded diagnostic only',files=rows))
print(json.dumps(dict(projectFiles=286,changedFiles=changes,sourceIndexSha256=pin,harnessIndexSha256=sha(HARNESS/'index.json'))))
