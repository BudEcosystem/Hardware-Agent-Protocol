"""Freeze current-source diagnostic and the original bounded actual harness."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = BASE / 'implementation01'
OLD = ROOT / 'artifacts/implementation/qualification-package/implementation03'
TEMPLATE = OLD.parent / 'harness01'
HARNESS = BASE / 'harness01'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    body = value if type(value) is str else json.dumps(value, indent=2) + '\n'
    with p.open('x') as out: out.write(body)
def row(p, root=ROOT): return dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
assert not (SOURCE / 'index.json').exists() and not HARNESS.exists()
pins = read(BASE / 'inspection01.json')
assert pins['passed'] and not pins['importEffects'] and pins['producerImageFiles'] == 267
old_pins = read(OLD / 'identity-pins.json')
changed_tests = []
for p in sorted((SOURCE / 'project/tests').glob('*.py')):
    before = p.read_text(); after = before
    for kind in ('host', 'consumer', 'vault', 'legacy'): after = after.replace(old_pins[kind], pins[kind])
    if after != before: p.write_text(after); changed_tests.append(p.relative_to(SOURCE / 'project').as_posix())
baseline = read(SOURCE / 'baseline-inputs.json')['files']
changed = [v['path'] for v in baseline if sha(SOURCE / 'project' / v['path']) != v['sha256']]
assert set(changed) == {'hms_qualification/supervisor/worker_entry.py'} | set(changed_tests)
assert all((SOURCE / 'project' / v['path']).read_bytes() == (OLD / 'project' / v['path']).read_bytes()
           for v in baseline if v['path'].startswith('hms/'))
for p in (SOURCE / 'project').rglob('*.py'): ast.parse(p.read_bytes())
write(SOURCE / 'identity-pins.json', pins)
write(SOURCE / 'test-selection.json', read(TEMPLATE / 'targets.json'))
write(SOURCE / 'source-review.json', dict(diagnosticOnly=True, productionAdoptionPermitted=False,
    reviewer='primary-agent', independentReview=False, changedProductionFiles=['hms_qualification/supervisor/worker_entry.py'],
    changedTestIdentityLiterals=changed_tests, unchangedCoreHmsFiles=83, profilerFunctionAstUnchanged=True,
    originalActualTestSemanticsPreserved=True, originalCaseCount=30, workerMaxWallMs=60000,
    parentMaxSeconds=180, maxParentSqliteOpens=6, maxSingleFileBytes=16777216,
    maxScratchBytes=268435456, maxFiles=8192, maxLogBytes=8388608, maxVaultBytes=15728640,
    snapshotMaxMs=5000, maxApplicationInvocations=1, semanticOracleSubstituted=False,
    precedingFailedAttemptRetained=True, physicalDeviceExecuted=False,
    signalBehavior='Default SIGTERM required; bounded report then default re-raised; escalation unchanged',
    profileLimits=dict(entries=8192,labelCharacters=512,cumulativeRows=40,selfRows=40)))
write(SOURCE / 'README.md', '# Current qualification diagnostic source\n\nOnly the fixed worker entry adds the previously reviewed profiler. All 83 core modules remain exact. Test changes update expected identity literals for that diagnostic source. [Review](source-review.json), [selection](test-selection.json). This diagnostic cannot enter the production runtime.\n')
frozen = [row(p) for p in sorted(SOURCE.rglob('*')) if p.is_file()]
assert len(baseline) == 304
write(SOURCE / 'index.json', dict(files=frozen, diagnosticOnly=True))
assert sha(TEMPLATE / 'index.json') == 'ce31a90947d5ec9a2c426ca64f879c071964823bf9b5da68c8c9d745476f5820'
for item in read(TEMPLATE / 'index.json')['files']:
    p = TEMPLATE / item['path']
    assert p.stat().st_size == item['bytes'] and sha(p) == item['sha256']
HARNESS.mkdir()
for name in ('targets.json', 'borrowed-inputs.json', 'attempt_child.py'):
    write(HARNESS / name, (TEMPLATE / name).read_text())
for p in (TEMPLATE / 'references').rglob('*'):
    if p.is_file():
        destination = HARNESS / 'references' / p.relative_to(TEMPLATE / 'references')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as out: out.write(p.read_bytes())
before = (TEMPLATE / 'run_attempt.py').read_text()
after = before.replace('ec6df4066c89f38328030a28e2a5bd71d137abbc67cd51cb161cc246e2e8a268', sha(SOURCE / 'index.json'))
after = after.replace('artifacts/implementation/qualification-package/implementation03/', SOURCE.relative_to(ROOT).as_posix() + '/')
after = after.replace('!= 312', '!= ' + str(len(frozen))).replace("'frozenPreparationInputCount': 312", "'frozenPreparationInputCount': " + str(len(frozen)))
ast.parse(after)
write(HARNESS / 'run_attempt.py', after)
write(HARNESS / 'run_attempt.py.patch', ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='package/run_attempt.py', tofile='diagnostic/run_attempt.py')))
write(HARNESS / 'SCOPE.md', '# Original full flow with current diagnostic instrumentation\n\nOne complete original thirty-case worker is requested, followed by the real reducer, vault/catalog and at most one simulated application if reached. No substituted oracle. The exact [diagnostic plan](../PLAN.md) applies. Original 60/180-second, 6 parent SQLite, 16 MiB/file, 256 MiB scratch, 8192-file, 8 MiB-log, 5-second lease and 15 MiB-vault bounds remain. Native retention image and owned-process accounting guards remain exact. No physical, network, MCU, inference or live service execution. An interrupted worker remains incomplete and its case databases are not opened or repaired.\n')
write(HARNESS / 'README.md', '# Current worker diagnostic harness\n\n[Source](../implementation01/README.md), [scope](SCOPE.md), [selection](targets.json). This is a distinct diagnostic scope; earlier failed logical work is not restarted.\n')
write(HARNESS / 'index.json', dict(files=[row(p, HARNESS) for p in sorted(HARNESS.rglob('*')) if p.is_file()]))
write(BASE / 'release.json', dict(reviewer='primary-agent', independentReview=False, diagnosticOnly=True,
    sourceIndexSha256=sha(SOURCE / 'index.json'), harnessIndexSha256=sha(HARNESS / 'index.json'),
    projectFiles=304, frozenFiles=len(frozen), unchangedCoreHmsModules=83, actualWorkerCeiling=1,
    actualApplicationCeiling=1, originalLimitsPreserved=True, profilerAstUnchanged=True,
    semanticOracleSubstituted=False, publicRuntimeChanged=False, physicalExecutionAllowed=False))
print(json.dumps(read(BASE / 'release.json')))
