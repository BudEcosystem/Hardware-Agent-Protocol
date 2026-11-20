"""Freeze the pure definition-build refactor and its exact test scopes."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path.cwd()
BASE = ROOT / 'artifacts/implementation/pat-io-definition-build'
STAGE = BASE / 'implementation01'
PRIOR = ROOT / 'artifacts/implementation/pat-io-recorded-catalog'
SOURCE = PRIOR / 'implementation04'
OLD_PIN = 'daa1013a169c99db81196efa1e0ba1cd3b3a2a1216f1094ff1e79d4ee4b37abc'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path, value):
    with path.open('x') as stream: stream.write(json.dumps(value, indent=2) + '\n')
def inventory(folder, rooted=False):
    rows = []
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            if path.suffix == '.py': ast.parse(path.read_bytes())
            rows.append(dict(path=path.relative_to(ROOT if rooted else folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    return sorted(rows, key=lambda row:row['path'])
def methods(module, name):
    tree = ast.parse((STAGE / 'project/tests' / (module + '.py')).read_bytes())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)
    return sorted(module + '.' + name + '.' + node.name for node in cls.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'))

assert not (STAGE / 'index.json').exists() and sha(SOURCE / 'index.json') == OLD_PIN
baseline = read(STAGE / 'baseline-inputs.json')['inheritedProjectInputs']
assert len(baseline) == 274
changes = []
for row in baseline:
    source = ROOT / row['path']; assert sha(source) == row['sha256']
    relative = source.relative_to(SOURCE / 'project')
    if sha(STAGE / 'project' / relative) != row['sha256']: changes.append(relative.as_posix())
assert changes == ['hms/synthetic_io_installation.py'] and len(inventory(STAGE / 'project')) == 275
old_tree = ast.parse((SOURCE / 'project/hms/synthetic_io_installation.py').read_bytes())
new_tree = ast.parse((STAGE / 'project/tests/test_pat_io_definition_build.py').read_bytes())
old_function = next(node for node in old_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'definitions')
reference = next(node for node in new_tree.body if isinstance(node, ast.FunctionDef) and node.name == '_legacy_definitions')
old_function.name = reference.name
assert ast.dump(old_function, include_attributes=False) == ast.dump(reference, include_attributes=False)
fresh = methods('test_pat_io_definition_build', 'DefinitionBuildTests')
inherited = methods('test_pat_io_installation_reuse', 'InstallationReuseTests')
assert len(fresh) == 7 and len(inherited) == 14
targets = [fresh + inherited, read(PRIOR / 'harness83/targets.json')['targets']]
review = [
    'Baseline is the uninstrumented recorded-catalog source04. Only synthetic_io_installation.py changes in production; all 273 other inherited files remain exact. One new test module retains the original definition builder AST verbatim except its function name.',
    'Each definition build derives a complete static resource proof once per instance, at the original first-action point, and uses it for that instance only. Proofs include every instance action. Handler/consumer/property lookup, expanded-claim indexing and complete type-bundle validation remain for each applicable action/instance.',
    'The detail, argument-schema, type-bundle and validation helpers are pure and do not mutate the supplied installation. No proof or other input survives a call; concurrent mutation of trusted input during a call remains unsupported. The public handler_details function still derives a fresh proof on each invocation.',
    'The proof function and all topology/generation validation are unchanged. No current authority, database, binding/session freshness, source scan or effect check is cached or bypassed. There is no diagnostic signal handler in this candidate.',
    'Seven new tests compare exact canonical legacy outputs, count actual derivations without replacing validation, cover multiple actions, generations changed between calls, detached results, invalid input refusals, public freshness and loaded pure execution. Fourteen inherited normalization controls cover the affected module/dependency guards.',
    'The actual process test is byte-identical to source04 and requests the complete 30-case worker, original import, catalog promotion, one application with at most eight ticks, exact original-key replay, changed-context refusal and cold historical replay. No scope count or effect limit is reduced.',
    'All original 60-second worker, 180-second parent, single-file/evidence ceilings remain. Pure tests deny all SQLite opens and subprocess/network creation. Process retains six parent opens and 256 MiB scratch; neither profile promises OS quota or deployment timing.',
    'The changed HMS source intentionally changes driver, producer and dependent consumer identities. Fresh fixtures generate and bind current identities; no old receipt, logical key or failed state is migrated or retried. Primary-agent review only.',
]
write(STAGE / 'source-review.json', dict(reviewed=review, changedProductionFiles=changes, unchangedInheritedProjectFiles=273,
    newTestMethods=7, inheritedPureMethods=14, originalReferenceAstVerified=True, independentReview=False, releasedBy='primary-agent', projectExecutionDuringPreparation=False))
(STAGE / 'README.md').write_text('# One-call static proof reuse\n\n[Design](../DESIGN.md), [source review](source-review.json). One production module changes; 273 inherited files remain exact. Seven new differential controls and 14 inherited normalization controls precede the unchanged complete process test. No result is claimed before retained execution.\n')
rows = inventory(STAGE, True); assert len(rows) == 278
write(STAGE / 'index.json', dict(scope='One static proof per instance within a pure definition-build call; no cross-call or authority cache.', files=rows))
pin = sha(STAGE / 'index.json')
for number, selected in enumerate(targets, 1):
    pure = number == 1
    prior = PRIOR / ('harness84' if pure else 'harness83')
    harness = BASE / ('harness%02d' % number); harness.mkdir(); (harness / 'references').mkdir()
    borrowed = []
    for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
        source = prior / name; destination = harness / 'references' / Path(name).name
        shutil.copyfile(source, destination)
        borrowed.append(dict(source=source.relative_to(ROOT).as_posix(),copy=destination.relative_to(harness).as_posix(),bytes=source.stat().st_size,sha256=sha(source)))
    write(harness / 'borrowed-inputs.json', borrowed)
    write(harness / 'targets.json', dict(testCount=len(selected), targets=selected))
    for name in ('run_attempt.py','attempt_child.py'):
        original = (prior / name).read_text()
        updated = original.replace(OLD_PIN, pin).replace('pat-io-recorded-catalog/implementation04','pat-io-definition-build/implementation01')
        for before, after in [('len(expected) != 277','len(expected) != 278'),
            ("'frozenPreparationInputCount': 277", "'frozenPreparationInputCount': 278"),
            ("'projectInputCount': 274", "'projectInputCount': 275"), ('len(selected) != 274','len(selected) != 275'),
            ('exactly 274 files','exactly 275 files')]: updated = updated.replace(before, after)
        if name == 'run_attempt.py':
            assert updated.count("stage = here.parent / 'implementation04'") == 1
            updated = updated.replace("stage = here.parent / 'implementation04'", "stage = here.parent / 'implementation01'")
            updated = updated.replace('hms-io-snapshot-reuse-service1-', 'hms-io-definition-build-')
        if pure:
            old_targets = read(prior / 'targets.json')['targets']; assert updated.count(repr(old_targets)) == 1
            updated = updated.replace(repr(old_targets), repr(selected))
            updated = updated.replace("['testsRun'] == 1", "['testsRun'] == 21")
            updated = updated.replace("'expectedTests': 1", "'expectedTests': 21")
            updated = updated.replace("targets['testCount'] != 1", "targets['testCount'] != 21")
            if name == 'attempt_child.py':
                begin = updated.index("    if event == 'sqlite3.connect':\n")
                end = updated.index("    if event == 'exec':\n", begin)
                updated = updated[:begin] + "    if event == 'sqlite3.connect':\n        prohibited.append(event); raise RuntimeError('Pure definition/normalization tests forbid all SQLite opens')\n" + updated[end:]
        ast.parse(updated)
        (harness / name).write_text(updated)
        (harness / (name + '.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),fromfile=str(prior/name),tofile=str(harness/name))))
    scope = ('Seven pure differential definition-build controls plus 14 inherited normalization controls; no Runtime or worker.' if pure
             else 'Unchanged complete original worker/import/catalog/application/replay process test with the local proof-build refactor.')
    (harness / 'SCOPE.md').write_text('# Exact scope\n\n' + scope + '\n\n[Targets](targets.json), [source](../implementation01/README.md). Original 180-second parent and 16 MiB single-file limits; ' + ('16 MiB scratch, no SQLite/subprocess/network.' if pure else '256 MiB scratch, six parent SQLite opens, one complete 60-second worker and the original one simulated application.') + '\n')
    (harness / 'README.md').write_text('# Definition-build verification\n\n[Scope](SCOPE.md), [source](../implementation01/README.md).\n')
    write(harness / 'review.json', dict(scope=scope, tests=len(selected), sourceIndexSha256=pin,targetSha256=sha(harness/'targets.json'),
        inheritedHarnessIndexSha256=sha(prior/'index.json'),reviewed=review,independentReview=False,releasedBy='primary-agent',
        selectionKind='pure' if pure else 'process',sqliteConnectionsMaximum=0 if pure else 6,
        scratchBytesCeiling=(16 if pure else 256)*1024*1024,projectInputCount=275,frozenPreparationInputCount=278))
    write(harness / 'index.json', dict(scope=scope, files=inventory(harness)))
print(json.dumps(dict(prepared=True, sourceIndexSha256=pin, changedProductionFiles=changes,
    inheritedUnchanged=273, newPureTests=7, totalPureTests=21, actualScopes=1)))
