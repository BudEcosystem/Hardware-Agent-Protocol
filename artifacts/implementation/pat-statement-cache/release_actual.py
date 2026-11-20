"""Review gate for one complete changed-source worker; does not launch it."""
import ast
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = BASE / 'implementation01'
HARNESS = BASE / 'harness01'
PIN = '7ecd42fec5cef9374573ae8b3d0747060bdc8c4cd8ca552e9c3de4d64a2ec23e'
HPIN = '74204ea2477aa497bfce9a6c667455b4ec5fb622f49c07663a7c87b3c583d933'

def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(index, prefix, pin):
    assert sha(index) == pin
    for row in read(index)['files']:
        p = prefix / row['path']
        assert not p.is_symlink() and p.stat().st_size == row['bytes'] and sha(p) == row['sha256']

assert not (HARNESS / 'attempts').exists()
assert not (BASE / 'actual-release01.json').exists()
local = ROOT / 'artifacts/verification/pat-statement-cache-evaluation'
verify(local / 'index.json', ROOT,
       '9c52c01d1bce2203620dbffdc71eea00dc061de0707cd119a0d86232359fe021')
screen = read(local / 'RESULTS.json')
assert screen['retentionAuditPassed'] and screen['integrationScreenPassed']
assert screen['differentialCases'] == 62 and screen['timingRunsPerformed'] == 1
verify(SOURCE / 'index.json', ROOT, PIN)
verify(HARNESS / 'index.json', HARNESS, HPIN)
controls = read(BASE / 'CONTROL_RESULTS.json')
assert controls['status'] == 'verified-controls' and controls['testsRun'] == 19
assert controls['sourceIndexSha256'] == PIN and len(controls['scopes']) == 10
assert len(controls['readonlyDatabases']) == 76
for scope in read(BASE / 'control-selection.json')['scopes']:
    p = BASE / scope['harness']
    verify(p / 'index.json', p, scope['indexSha256'])
    result = read(p / 'attempts/attempt01/result.json')
    assert result['status'] == 'passed' and result['childState'] == 'exited'
    assert result['counts']['testsRun'] == len(scope['targets'])
old = BASE.parent / 'qualification-package/implementation03/project'
current = SOURCE / 'project'
before = ast.parse((old / 'hms/journal.py').read_bytes())
after = ast.parse((current / 'hms/journal.py').read_bytes())
calls = [n for n in ast.walk(after) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
         and isinstance(n.func.value, ast.Name) and n.func.value.id == 'sqlite3' and n.func.attr == 'connect']
assert len(calls) == 1 and calls[0].keywords[-1].arg == 'cached_statements'
assert ast.literal_eval(calls[0].keywords.pop().value) == 256
assert ast.dump(before) == ast.dump(after)
assert (HARNESS / 'attempt_child.py').read_bytes() == (BASE.parent / 'qualification-package/harness01/attempt_child.py').read_bytes()
report = dict(reviewer='primary-agent', independentReview=False, sourceIndexSha256=PIN,
    harnessIndexSha256=HPIN, sourceAndHarnessVerified=True, soleProductionChangeReviewed=True,
    unchangedAttemptChildVerified=True, localDifferentialCases=62, catalogControls=19,
    originalCases=30, originalWorkerWallMs=60000, parentSeconds=180, parentSqliteOpens=6,
    exactOneQualificationWorker=True, plannedApplicationInvocations=1, oracleSubstitution=False,
    physicalProviderExecution=False, publicServiceEnabled=False, unchangedRetryPermitted=False)
with (BASE / 'actual-release01.json').open('x') as stream:
    json.dump(report, stream, indent=2); stream.write('\n')
print(json.dumps(report))
