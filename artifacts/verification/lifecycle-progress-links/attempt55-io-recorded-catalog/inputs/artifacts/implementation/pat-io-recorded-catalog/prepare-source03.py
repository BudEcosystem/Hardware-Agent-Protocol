"""Freeze the recorded profile and exact fresh control/process scopes."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path.cwd()
BASE = ROOT / 'artifacts/implementation/pat-io-recorded-catalog'
STAGE = BASE / 'implementation03'
OLD = ROOT / 'artifacts/implementation/pat-io-content-store/implementation01'
PROCESS = ROOT / 'artifacts/implementation/pat-io-content-store/harness02'
CONTROL = ROOT / 'artifacts/implementation/pat-io-content-store/harness01'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_bytes())

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
            rows.append(dict(path=path.relative_to(ROOT if rooted else folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    return sorted(rows, key=lambda item: item['path'])

baseline = read(STAGE / 'baseline-inputs.json')['inheritedProjectInputs']
assert len(baseline) == 266 and not (STAGE / 'index.json').exists()
for row in baseline:
    source = ROOT / row['path']
    destination = STAGE / 'project' / source.relative_to(OLD / 'project')
    assert sha(source) == row['sha256'] == sha(destination)
assert len(inventory(STAGE / 'project')) == 274
module, clsname = 'test_io_recorded_catalog', 'RecordedIoCatalogTests'
tree = ast.parse((STAGE / 'project/tests' / (module + '.py')).read_bytes())
cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == clsname)
controls = sorted(module + '.' + clsname + '.' + node.name for node in cls.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'))
assert len(controls) == 19
first = module + '.' + clsname + '.test_original_invocation_records_and_promotes_with_static_compatibility'
process_target = 'test_io_recorded_catalog_process.RecordedIoCatalogProcessTests.test_actual_original_matrix_catalog_execution_and_historical_replay'
targets = [first, process_target] + [target for target in controls if target != first]
assert len(targets) == 20
review = [
    'All266 inherited project files remain byte-identical. Six host-only recorded_io modules and two tests are new; producer262-file image and both existing consumer identities remain unchanged.',
    'The actual installed compact consumer authorizes and resolves the original run. Full semantic reinspection runs outside the Journal transaction; preparation publishes only after exact current original association/bytes rechecks.',
    'Preparation state is process-owned, capped at four entries and64MiB conservative encoded charges, and cannot be populated by caller result/path/callback documents. Restart starts cold. Limits may only be lowered.',
    'SELECT-only main-schema projection preflights current control/evidence types, byte lengths and counts. Every selected body is compared byte-for-byte. New control history invalidates the prepared projection; unrelated actual bodies are indexed by bounded actual length, not all semantically reinspected.',
    'The source-applicability record retains original source dependencies including endpoint session. Compiler static environment representation is unchanged. Read-only installed resolver checks current source binding/resource/driver/session provenance under the existing SQL/reentry guard.',
    'Current source descriptor provenance is distinct from live primitive freshness; the existing operation/admission/provider guards remain authoritative for expiry and effect checks. No source/filesystem/external-ledger/full-reducer access occurs in the catalog verifier.',
    'Explicit catalog profile, anchor and exact schema refuse old mounts, missing tables and reinitialization. New receipt profile/domain carries original invocation and applicability; historical recording/replay is distinct from current eligibility.',
    'A relevant active source assignment this principal may use is checked before legacy environment filtering; unavailable context/evidence cannot disappear into novelty or manufactured uniqueness. Inaccessible source assignments remain filtered before protected environment reads.',
    'A same-artifact/configuration reservation lacking imported complete evidence inhibits fresh reuse even after warming old success. No old failure, row or mutation key is replaced to obtain success.',
    'Nineteen controls use explicitly substituted qualification/semantic success and no actual worker. One process scope requires complete actual30-case worker/import/record/promotion plus one bounded simulated application, exact key replay, changed-context refusal and cold historical replay after runtime/session reopen.',
    'Original60-second worker/group,180-second outer,16MiB single-file and aggregate/effect limits remain. Controls retain16MiB total scratch and three parent SQL opens; actual process retains256MiB scratch and six parent opens. The application is one planned simulated invocation, with at most eight scheduler ticks and no physical effects.',
    'Source02 preserves the original import failure and import-only diagnostic. Bootstrap order, a catalog profile/domain collision and a nonexistent process assertion field are corrected explicitly; no original test/worker ran.',
    'Source03 changes only the recorded projection from GLOB functions to BINARY prefix ranges. The existing catalog authorizer is unchanged; the failed source02 scope and SQLite diagnosis remain retained. All runner source literals/prefixes now select implementation03.',
    'Primary-agent review only. No physical port/flashing, MCU/emulator, live model/service, acquired controller/research execution or adjacent Harness mutation. Public mounting, broad physical providers and learning remain unfinished.'
]
write(STAGE / 'source-review.json', dict(reviewed=review, unchangedInheritedProjectFiles=266, newProductionFiles=6,
    newTestMethods=20, independentReview=False, releasedBy='primary-agent', projectExecutionDuringPreparation=False))
(STAGE / 'README.md').write_text('# Recorded original-run catalog candidate\n\n[Design](../DESIGN.md), [review](source-review.json). All266 inherited project inputs remain unchanged. Six host modules add explicit invocation, prepared evidence, current applicability and recorded-profile selection. Nineteen fixture controls and one actual full integration are selected. No result is claimed before their retained receipts.\n')
rows = inventory(STAGE, True)
assert len(rows) == 277
write(STAGE / 'index.json', dict(scope='Explicit recorded finite-I/O catalog profile, prepared byte verification and current source applicability.', files=rows))
pin = sha(STAGE / 'index.json')
for i, target in enumerate(targets, 1):
    process = target == process_target
    prior = PROCESS if process else CONTROL
    harness = BASE / ('harness%02d' % (i + 61))
    harness.mkdir(); (harness / 'references').mkdir()
    borrowed = []
    for name in ('run_attempt.py', 'attempt_child.py', 'references/approved-external-roots.json'):
        source = prior / name
        destination = harness / 'references' / Path(name).name
        shutil.copyfile(source, destination)
        borrowed.append(dict(source=source.relative_to(ROOT).as_posix(), copy=destination.relative_to(harness).as_posix(), bytes=source.stat().st_size, sha256=sha(source)))
    write(harness / 'borrowed-inputs.json', borrowed)
    write(harness / 'targets.json', dict(testCount=1, targets=[target]))
    old_targets = read(prior / 'targets.json')['targets']
    old_method, new_method = old_targets[0].rsplit('.', 1)[1], target.rsplit('.', 1)[1]
    old_pin = read(prior / 'review.json')['sourceIndexSha256']
    for name in ('run_attempt.py', 'attempt_child.py'):
        original = (prior / name).read_text()
        updated = original.replace(old_pin, pin).replace('pat-io-content-store/implementation01', 'pat-io-recorded-catalog/implementation03')
        for before, after in [('len(expected) != 269', 'len(expected) != 277'),
            ("'frozenPreparationInputCount': 269", "'frozenPreparationInputCount': 277"),
            ("'projectInputCount': 266", "'projectInputCount': 274"),
            ('len(selected) != 266', 'len(selected) != 274'), ('exactly 266 files', 'exactly 274 files')]:
            updated = updated.replace(before, after)
        if name == 'run_attempt.py':
            stage_marker = "stage = here.parent / 'implementation01'"
            assert updated.count(stage_marker) == 1
            updated = updated.replace(stage_marker, "stage = here.parent / 'implementation03'")
            assert "stage = here.parent / 'implementation03'" in updated
        occurrences = updated.count(repr(old_targets))
        if name == 'attempt_child.py' and process:
            assert occurrences == 0
        else:
            assert occurrences == 1
            updated = updated.replace(repr(old_targets), repr([target]))
        if process:
            updated = updated.replace(old_method, new_method)
        if name == 'attempt_child.py':
            marker = "name.startswith('evidence_compact.')"
            assert updated.count(marker) == 1
            updated = updated.replace(marker, marker + " or name == 'recorded_io' or name.startswith('recorded_io.')")
            assert "counts['testsRun'] == 1" in updated
            marker = '    loaded_ids = flatten(tests)\n'
            assert updated.count(marker) == 1
            updated = updated.replace(marker, marker + "    write('loader-errors.json', list(unittest.defaultTestLoader.errors))\n    for detail in unittest.defaultTestLoader.errors: print(detail, file=sys.stderr, flush=True)\n")
        ast.parse(updated)
        (harness / name).write_text(updated)
        (harness / (name + '.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True), fromfile=str(prior / name), tofile=str(harness / name))))
    scope = ('Actual full30-case original worker/import/catalog/deterministic simulated application and historical replay.'
             if process else 'One recorded-catalog boundary control; successful qualification/semantics are explicit fixtures.')
    (harness / 'SCOPE.md').write_text('# Exact scope\n\n' + scope + '\n\n[Target](targets.json), [source](../implementation03/README.md). Original180-second outer and16MiB single-file ceilings; ' + ('256MiB' if process else '16MiB') + ' total scratch.\n')
    (harness / 'README.md').write_text('# Recorded-catalog verification\n\n[Scope](SCOPE.md), [source](../implementation03/README.md).\n')
    write(harness / 'review.json', dict(scope=scope, tests=1, sourceIndexSha256=pin, targetSha256=sha(harness / 'targets.json'),
        inheritedHarnessIndexSha256=sha(prior / 'index.json'), reviewed=review, independentReview=False, releasedBy='primary-agent',
        selectionKind='process' if process else 'control', sqliteConnectionsMaximum=6 if process else 3,
        scratchBytesCeiling=(256 if process else 16)*1024*1024, projectInputCount=274, frozenPreparationInputCount=277))
    write(harness / 'index.json', dict(scope=scope, files=inventory(harness)))
print(json.dumps(dict(prepared=True, sourceIndexSha256=pin, inheritedUnchanged=266, projectFiles=274,
    frozenFiles=277, fixtureControls=19, actualScopes=1)))
