"""Prepare one current-worker diagnostic; do not run project code here."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path.cwd()
BASE = ROOT / 'artifacts/implementation/pat-io-catalog-worker-profile'
STAGE = BASE / 'implementation01'
PRIOR = ROOT / 'artifacts/implementation/pat-io-recorded-catalog'
SOURCE = PRIOR / 'implementation04'
OLD_HARNESS = PRIOR / 'harness83'
HARNESS = BASE / 'harness01'
OLD_PROFILE = ROOT / 'artifacts/implementation/pat-io-supervision-profile/implementation01'
SOURCE_PIN = 'daa1013a169c99db81196efa1e0ba1cd3b3a2a1216f1094ff1e79d4ee4b37abc'

def read(path):
    return json.loads(path.read_bytes())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')

def inventory(folder, rooted=False):
    rows = []
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes())
            rows.append(dict(path=path.relative_to(ROOT if rooted else folder).as_posix(),
                             bytes=path.stat().st_size, sha256=sha(path)))
    return sorted(rows, key=lambda row: row['path'])

assert not STAGE.exists() and not HARNESS.exists()
assert sha(SOURCE / 'index.json') == SOURCE_PIN
source_rows = read(SOURCE / 'index.json')['files']
for row in source_rows:
    path = ROOT / row['path']
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
project_rows = [row for row in source_rows if '/implementation04/project/' in row['path']]
assert len(project_rows) == 274
shutil.copytree(SOURCE / 'project', STAGE / 'project')

profile_path = OLD_PROFILE / 'project/supervisor/worker_entry.py'
profile_row = next(row for row in read(OLD_PROFILE / 'index.json')['files'] if row['path'] == profile_path.relative_to(ROOT).as_posix())
assert profile_row['sha256'] == 'c9a92b0b2ee7f547c4e603d72d11d29ad2d80f2b484b3b446512c6768105cb80' == sha(profile_path)
text = profile_path.read_text()
node = next(node for node in ast.parse(text).body if isinstance(node, ast.FunctionDef) and node.name == '_profile_group')
function = ast.get_source_segment(text, node)
entry = STAGE / 'project/supervisor/worker_entry.py'
original = entry.read_text()
marker = '\ndef main():\n'
assert original.count(marker) == 1
updated = original.replace(marker, '\n' + function + '\n\n' + marker)
before_call = "    result = run_io_group(attempt / 'output', candidate=inputs['candidate'], installation=inputs['installation'],\n        descriptor=inputs['descriptor'], challenge_bindings=inputs['bindings'], limits=request['groupLimits'])"
after_call = "    result = _profile_group(directory, lambda: run_io_group(attempt / 'output', candidate=inputs['candidate'], installation=inputs['installation'],\n        descriptor=inputs['descriptor'], challenge_bindings=inputs['bindings'], limits=request['groupLimits']))"
assert updated.count(before_call) == 1
updated = updated.replace(before_call, after_call)
ast.parse(updated)
entry.write_text(updated)
(BASE / 'worker-instrumentation.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True), fromfile=str(SOURCE / 'project/supervisor/worker_entry.py'), tofile=str(entry))))
changes = []
for row in project_rows:
    relative = (ROOT / row['path']).relative_to(SOURCE / 'project')
    if sha(STAGE / 'project' / relative) != row['sha256']:
        changes.append(relative.as_posix())
assert changes == ['supervisor/worker_entry.py']
review = [
    'Current recorded-catalog source04 is the baseline. All 273 other project files, all test methods, matrix generation, oracle, consumer and catalog logic are unchanged.',
    'Only the fixed worker entry receives the previously reviewed bounded cProfile wrapper. Profiling starts after launch/bundle checks and covers run_io_group. It records wall and process CPU plus at most 40 cumulative and 40 self-time rows; total function entries <=8192 and labels <=512 characters. The normal canonical document bound still applies.',
    'The diagnostic requires the existing default SIGTERM disposition, disables profiling, writes one exclusive private fsynced document through the existing directory descriptor, restores the default disposition and raises SIGTERM to itself. The supervisor original grace and pidfd SIGKILL path are unchanged. Interrupted transactions and partial states remain retained.',
    'This is a fresh diagnostic fixture with a new actual source/producer identity. No old logical run, ledger, failed state or mutation key is retried or repaired. A profile is neither a causal proof of the previous timeout nor a qualification/performance pass.',
    'The exact existing process test still requests all 30 cases and complete original-run semantics. If it reaches application code it permits only the existing one simulated invocation and at most eight scheduler ticks. No extra selected cases or effect budget are added.',
    'Original 60-second worker/group, 180-second parent, 16 MiB single-file, 256 MiB scratch and six parent SQLite-open ceilings remain. Producer/evidence limits and all writes, flush/fsync, purity and authorization checks remain.',
    'No physical I/O, MCU/emulator, live model/service, acquired controller code or adjacent Harness changes. Primary-agent review only; production must not adopt this diagnostic SIGTERM handler.',
]
write(STAGE / 'baseline-inputs.json', dict(sourceIndexSha256=SOURCE_PIN, inheritedProjectInputs=project_rows,
    changedFiles=changes, profileFunctionOrigin=profile_row, unchangedProjectFiles=273))
write(STAGE / 'source-review.json', dict(reviewed=review, independentReview=False, releasedBy='primary-agent',
    projectExecutionDuringPreparation=False, diagnosticOnly=True))
(STAGE / 'README.md').write_text('# Current worker diagnostic source\n\n[Design](../DESIGN.md), [review](source-review.json). Only the fixed worker entry changes from the sealed recorded-catalog source04. The bounded profile is diagnostic; no timing, qualification or production-readiness claim follows.\n')
rows = inventory(STAGE, True)
assert len(rows) == 277
write(STAGE / 'index.json', dict(scope='Bounded profile of the current complete I/O worker; diagnostic only.', files=rows))
pin = sha(STAGE / 'index.json')
HARNESS.mkdir(); (HARNESS / 'references').mkdir()
borrowed = []
for name in ('run_attempt.py', 'attempt_child.py', 'references/approved-external-roots.json'):
    source = OLD_HARNESS / name
    destination = HARNESS / 'references' / Path(name).name
    shutil.copyfile(source, destination)
    borrowed.append(dict(source=source.relative_to(ROOT).as_posix(), copy=destination.relative_to(HARNESS).as_posix(),
                         bytes=source.stat().st_size, sha256=sha(source)))
write(HARNESS / 'borrowed-inputs.json', borrowed)
write(HARNESS / 'targets.json', read(OLD_HARNESS / 'targets.json'))
for name in ('run_attempt.py', 'attempt_child.py'):
    original = (OLD_HARNESS / name).read_text()
    updated = original.replace(SOURCE_PIN, pin).replace('pat-io-recorded-catalog/implementation04', 'pat-io-catalog-worker-profile/implementation01')
    if name == 'run_attempt.py':
        assert updated.count("stage = here.parent / 'implementation04'") == 1
        updated = updated.replace("stage = here.parent / 'implementation04'", "stage = here.parent / 'implementation01'")
        updated = updated.replace('hms-io-snapshot-reuse-service1-', 'hms-io-current-worker-profile-')
    ast.parse(updated)
    (HARNESS / name).write_text(updated)
    (HARNESS / (name + '.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True), fromfile=str(OLD_HARNESS / name), tofile=str(HARNESS / name))))
scope = 'One current-source worker diagnostic using the unchanged actual recorded-catalog process test; full matrix and original limits.'
(HARNESS / 'SCOPE.md').write_text('# Exact diagnostic scope\n\n' + scope + '\n\n[Target](targets.json), [source](../implementation01/README.md). One original 60-second worker, 180-second outer limit, 16 MiB single-file and 256 MiB retained scratch ceilings. No failed logical run is restarted.\n')
(HARNESS / 'README.md').write_text('# Current worker profile\n\n[Scope](SCOPE.md), [source](../implementation01/README.md). Timing is instrumented and cannot establish deployment performance.\n')
write(HARNESS / 'review.json', dict(scope=scope, tests=1, sourceIndexSha256=pin,
    targetSha256=sha(HARNESS / 'targets.json'), inheritedHarnessIndexSha256=sha(OLD_HARNESS / 'index.json'),
    reviewed=review, independentReview=False, releasedBy='primary-agent', selectionKind='diagnostic-process',
    sqliteConnectionsMaximum=6, scratchBytesCeiling=256*1024*1024, projectInputCount=274, frozenPreparationInputCount=277))
write(HARNESS / 'index.json', dict(scope=scope, files=inventory(HARNESS)))
print(json.dumps(dict(prepared=True, sourceIndexSha256=pin, projectFiles=274, changedFiles=changes,
                      frozenFiles=277, diagnosticScopes=1, priorFailuresUntouched=True)))
