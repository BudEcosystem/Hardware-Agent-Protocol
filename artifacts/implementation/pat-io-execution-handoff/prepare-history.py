"""Freeze a test-only multi-run extension without changing prior project bytes."""
import ast
import difflib
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path.cwd(); B = ROOT/'artifacts/implementation/pat-io-execution-handoff'
P, S = B/'implementation01', B/'implementation02'
PIN = 'f53286e08e528fd764893afc6f6765128c388a349ef536c2f22b17bc521f6035'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, value):
    with p.open('x') as f: f.write(json.dumps(value,indent=2)+'\n')
def inventory(folder, rooted=False):
    rows = []
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            if path.suffix == '.py': ast.parse(path.read_bytes())
            rows.append(dict(path=path.relative_to(ROOT if rooted else folder).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    return sorted(rows,key=lambda r:r['path'])
assert sha(P/'index.json') == PIN
baseline = read(S/'baseline-inputs.json')['inheritedProjectInputs']; assert len(baseline) == 252
for row in baseline:
    old = ROOT/row['path']; new = S/'project'/old.relative_to(P/'project')
    assert sha(old) == row['sha256'] == sha(new) and old.stat().st_size == new.stat().st_size == row['bytes']
module = 'test_io_service_execution_history'; clsname = 'IoServiceExecutionHistoryTests'
tree = ast.parse((S/'project/tests'/(module+'.py')).read_bytes())
cls = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==clsname)
targets = sorted(module+'.'+clsname+'.'+n.name for n in cls.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
assert len(targets) == 5 and len(inventory(S/'project')) == 253
reviewed = [
    'All252 prior project files remain byte-identical. Only a new test module is added; production code, worker image262/10supervisors, public interfaces, bounds and original tests are unchanged.',
    'Two distinct logical runs must get distinct attempts and an exact receipt chain. The first is explicitly recovered without launch before the second admission; the second is interrupted on reopen and is never resumed.',
    'Well-formed canonical second receipts with a forged previous link, borrowed attempt ID or regressed timestamp refuse. Swapped committed row order also refuses. All altered fixtures are retained without repair.',
    'Both launch boundaries are substituted in these controls; no producer subprocess or physical effect is claimed. A separate actual owned-worker failure is retained under implementation01.',
    'Each method has its own original180-second/16MiB scope. Parent SQL opens are exactly three, or six for the explicit two-store/runtime reopen. No network, physical endpoint or extra executable is allowed.',
    'Primary-agent review only. Earlier immutable source/harnesses/results remain separate; this extension is not a rerun or repair of the failed owned worker. Full goal remains active.'
]
write(S/'source-review.json',dict(scope='Test-only multiple-run handoff history coverage', inheritedSourceIndexSha256=PIN,
    unchangedInheritedProjectFiles=252, productionFilesChanged=[], newTestMethods=5,
    reviewed=reviewed, independentReview=False, releasedBy='primary-agent', projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Multiple-run handoff history controls\n\n[Test-only source review](source-review.json), [design](../DESIGN.md). All252 preceding project files remain unchanged; this copy adds five history controls. No worker execution is claimed by these controls.\n')
rows = inventory(S,True); assert len(rows)==256
write(S/'index.json',dict(scope='Unchanged production and five added multiple-run handoff controls.',files=rows))
pin=sha(S/'index.json'); prior=B/'harness19'; old_targets=read(prior/'targets.json')['targets']
for i,target in enumerate(targets,26):
    harness=B/('harness%02d'%i);harness.mkdir();(harness/'references').mkdir();borrowed=[]
    for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
        source,dest=prior/name,harness/'references'/Path(name).name;shutil.copyfile(source,dest)
        borrowed.append(dict(source=source.relative_to(ROOT).as_posix(),copy=dest.relative_to(harness).as_posix(),bytes=source.stat().st_size,sha256=sha(source)))
    write(harness/'borrowed-inputs.json',borrowed);write(harness/'targets.json',dict(testCount=1,targets=[target]))
    cap=6 if target.endswith('test_two_logical_runs_keep_distinct_attempts_and_chain_on_reopen') else 3
    for name in ('run_attempt.py','attempt_child.py'):
        original=(prior/name).read_text();s=original.replace(PIN,pin).replace('implementation01','implementation02')
        s=re.sub(r'\b252\b','253',s);s=re.sub(r'\b255\b','256',s);s=re.sub(r'\b6\b','1',s)
        assert s.count(repr(old_targets))==1;s=s.replace(repr(old_targets),repr([target]))
        if name=='attempt_child.py':
            s=s.replace("{'supervisor','replacement'}","{'supervisor'}")
            s=s.replace('len(sqlite_connections)>=36','len(sqlite_connections)>='+str(cap))
            s=s.replace("sum(c['testId']==current_test for c in sqlite_connections)>=1", "sum(c['testId']==current_test for c in sqlite_connections)>="+str(cap))
        ast.parse(s);(harness/name).write_text(s)
        (harness/(name+'.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile=str(prior/name),tofile=str(harness/name))))
    scope='One multiple-run handoff history control; both launch boundaries substituted, no producer execution.'
    (harness/'SCOPE.md').write_text('# Exact history scope\n\n'+scope+'\n\n[Targets](targets.json), [source](../implementation02/README.md). Original180-second and16MiB ceilings; exact reviewed SQL fixtures.\n')
    (harness/'README.md').write_text('# Handoff history control\n\n[Scope](SCOPE.md), [source](../implementation02/README.md).\n')
    review=read(prior/'review.json');review.update(scope=scope,tests=1,sourceIndexSha256=pin,targetSha256=sha(harness/'targets.json'),
        reviewed=reviewed,inheritedHarnessIndexSha256=sha(prior/'index.json'),selectionKind='history',
        controlTargets=[target],controlLabels=['runtime','supervisor'],sqliteConnectionsMaximum=cap,
        sqliteConnectionsPerMethod=cap,projectInputCount=253,frozenPreparationInputCount=256)
    write(harness/'review.json',review);write(harness/'index.json',dict(scope=scope,files=inventory(harness)))
print(json.dumps(dict(sourceIndexSha256=pin,unchangedPriorProjectFiles=252,projectFiles=253,frozenFiles=256,newMethods=5,harnesses=[26,27,28,29,30])))
