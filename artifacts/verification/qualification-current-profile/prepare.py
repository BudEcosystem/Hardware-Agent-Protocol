"""Prepare the previously reviewed profiler against the exact current package."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = ROOT / 'artifacts/implementation/qualification-package/implementation03'
PRIOR = ROOT / 'artifacts/verification/pat-vault-worker-profile/implementation01'
STAGE = BASE / 'implementation01'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, body):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as out: out.write(body if type(body) is bytes else body.encode())
def dump(p, obj): write(p, json.dumps(obj, indent=2) + '\n')
assert sha(SOURCE / 'index.json') == 'ec6df4066c89f38328030a28e2a5bd71d137abbc67cd51cb161cc246e2e8a268'
assert sha(PRIOR / 'index.json') == '2e5170b6f0b34bd5490b15b71285d9d85fdf0709eddf00a40cc6a8670a0b55d9'
assert not STAGE.exists()
baseline = []
for row in read(SOURCE / 'index.json')['files']:
    p = ROOT / row['path']
    assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
    if p.is_relative_to(SOURCE / 'project'):
        relative = p.relative_to(SOURCE / 'project')
        write(STAGE / 'project' / relative, p.read_bytes())
        baseline.append(dict(path=relative.as_posix(), bytes=row['bytes'], sha256=row['sha256']))
assert len(baseline) == 304
write(STAGE / 'namespace-map.json', (SOURCE / 'namespace-map.json').read_bytes())
profile = PRIOR / 'project/supervisor/worker_entry.py'
profile_pin = next(v for v in read(PRIOR / 'index.json')['files'] if v['path'] == profile.relative_to(ROOT).as_posix())
assert sha(profile) == profile_pin['sha256']
profile_body = profile.read_text()
function = next(n for n in ast.parse(profile_body).body if isinstance(n, ast.FunctionDef) and n.name == '_profile_group')
function_text = ast.get_source_segment(profile_body, function)
entry = STAGE / 'project/hms_qualification/supervisor/worker_entry.py'
before = entry.read_text()
after = before.replace('\ndef main():\n', '\n' + function_text + '\n\ndef main():\n')
old = "    result = run_io_group(attempt / 'output', candidate=inputs['candidate'], installation=inputs['installation'],\n        descriptor=inputs['descriptor'], challenge_bindings=inputs['bindings'], limits=request['groupLimits'])"
new = "    result = _profile_group(directory, lambda: run_io_group(attempt / 'output', candidate=inputs['candidate'], installation=inputs['installation'],\n        descriptor=inputs['descriptor'], challenge_bindings=inputs['bindings'], limits=request['groupLimits']))"
assert after.count(old) == 1
after = after.replace(old, new)
ast.parse(after)
entry.write_text(after)
extracted = next(n for n in ast.parse(after).body if isinstance(n, ast.FunctionDef) and n.name == '_profile_group')
assert ast.dump(extracted) == ast.dump(function)
changed = [v['path'] for v in baseline if sha(STAGE / 'project' / v['path']) != v['sha256']]
assert changed == ['hms_qualification/supervisor/worker_entry.py']
dump(STAGE / 'baseline-inputs.json', dict(sourceIndexSha256=sha(SOURCE / 'index.json'),
    files=baseline, diagnosticFunctionSource=profile_pin, diagnosticFunctionAstUnchanged=True,
    unchangedCoreHmsModules=83, changedBeforeIdentityPins=changed))
write(BASE / 'worker-instrumentation.patch', ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='current/worker_entry.py', tofile='diagnostic/worker_entry.py')))
inspector = (SOURCE.parent / 'inspect_package.py').read_text().replace('implementation03/', 'implementation01/')
ast.parse(inspector)
write(BASE / 'inspect_package.py', inspector)
print(json.dumps(dict(projectFiles=304, changedFiles=changed, profilerAstUnchanged=True)))
