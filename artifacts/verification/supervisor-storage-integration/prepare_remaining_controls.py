"""Declare new per-control diagnostic scopes after the retained batch termination."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2];NEW=BASE/'harness02'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
    with p.open('xb') as stream:stream.write(v if type(v) is bytes else (v if type(v) is str else json.dumps(v,indent=2)+'\n').encode())
original=read(BASE/'control-selection.json');prior=read(BASE/'CONTROL_RESULTS.json')
assert not prior['passed'] and len(prior['scopes'])==5
failed=read(BASE/'controls/legacy-handoff-02/result.json')
assert failed['exitCode']==-9 and failed['child'] is None and failed['sourceUnchanged']
assert 40<failed['elapsedSeconds']<60
passed=[]
for scope in original['scopes']:
    path=BASE/'controls'/scope['name']/'result.json'
    if not path.exists():continue
    result=read(path)
    if result['passed']:
        assert result['child']['executed']==scope['targets']
        passed+=scope['targets']
all_targets=[t for scope in original['scopes'] for t in scope['targets']]
assert len(all_targets)==len(set(all_targets))==71 and len(passed)==28
remaining=[t for t in all_targets if t not in passed];assert len(remaining)==43
NEW.mkdir(exist_ok=False)
for name in ('control_child.py','external-inputs.json'):write(NEW/name,(BASE/name).read_bytes())
write(NEW/'control-selection.json',dict(sourceIndexSha256=original['sourceIndexSha256'],projectFiles=309,
    tests=43,scopes=[dict(name=f'control-{i:02d}',targets=[target]) for i,target in enumerate(remaining,1)]))
before=(BASE/'run_controls.py').read_text()
after=before.replace('import hashlib','import resource\nimport hashlib',1).replace('ROOT=BASE.parents[2]','ROOT=BASE.parents[3]')
after=after.replace("    started=time.monotonic();error=None", "    usage_before=resource.getrusage(resource.RUSAGE_CHILDREN)\n    started=time.monotonic();error=None")
after=after.replace("    elapsed=time.monotonic()-started", "    elapsed=time.monotonic()-started\n    usage_after=resource.getrusage(resource.RUSAGE_CHILDREN)\n    child_cpu=dict(userSeconds=usage_after.ru_utime-usage_before.ru_utime,systemSeconds=usage_after.ru_stime-usage_before.ru_stime)")
after=after.replace("sourceUnchanged=inputs==after,child=child_result", "sourceUnchanged=inputs==after,childCpu=child_cpu,child=child_result")
assert after!=before;ast.parse(after);write(NEW/'run_controls.py',after)
write(NEW/'adaptation.patch',''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='stage90/batched-controls',tofile='stage90/per-control-diagnostics')))
write(NEW/'RELEASE.json',dict(reviewer='primary-agent',independentReview=False,reason='Retained batched diagnostic terminated with SIGKILL before final receipt',
    precedingBatchExitCode=-9,precedingCauseConfirmed=False,precedingWallSeconds=failed['elapsedSeconds'],
    sourceIndexSha256=original['sourceIndexSha256'],candidateChanged=False,childChanged=False,
    originalDistinctControls=71,completePassingControlsRetained=passed,remainingControls=remaining,
    changedDiagnosticBatching=True,aggregateDiagnosticBudgetIncreased=True,originalFourteenScopeProfilePassed=False,
    wallSecondsPerProcess=60,cpuSecondsPerProcess=40,memoryBytes=512*1024*1024,fdLimit=128,
    fileBytes=16*1024*1024,scratchBytes=256*1024*1024,actualWorkerMsUnchanged=60000,actualParentSecondsUnchanged=180,
    originalFailedBatchRetained=True,physicalExecution=False))
write(NEW/'SCOPE.md','''# Individually bounded remaining diagnostic controls

The first batch experiment remains failed: four scopes passed 28 controls; the
fifth ended with SIGKILL at 41.5 seconds and has no child CPU receipt. Its cause
is not conclusively attributed. No original database is reopened or repaired.

This explicitly revised diagnostic profile runs the remaining 43 test identities
in separate fresh processes and fixtures, retaining all 28 complete passing
receipts. Source, assertions and child guard remain exact. Each process still has
60 seconds wall, 40 CPU, 512 MiB, 128 FDs, 16 MiB per file and 256 MiB scratch.
The total diagnostic budget increases; this is not a passing result for the
original fourteen-scope packing. Parent-observed child CPU deltas are recorded.
No unchanged batch retry occurs. A failing individual control stops this profile.

The required complete thirty-case worker, reducer, vault, catalog and one PAT
application retain their original joint scope, 60-second worker and 180-second
parent limits. They run only if all 71 diagnostic identities have complete
passing receipts. No production timing or physical qualification is inferred
from control batching. All raw and acquired failed evidence remains retained.
''')
files=[dict(path=p.relative_to(NEW).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(NEW.iterdir()) if p.is_file()]
write(NEW/'index.json',dict(files=files));print(json.dumps(dict(indexSha256=sha(NEW/'index.json'),remainingControls=43)))
