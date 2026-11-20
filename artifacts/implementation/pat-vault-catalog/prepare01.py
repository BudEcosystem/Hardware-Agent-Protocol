"""Freeze the first catalog candidate and a bounded no-worker control harness.

Only stdlib source inspection/copying runs here; no candidate module is imported.
"""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
SOURCE = BASE / 'implementation01'
PROJECT = SOURCE / 'project'
PRIOR = ROOT / 'artifacts/implementation/pat-vault-batch/implementation01'
OLD_HARNESS = ROOT / 'artifacts/verification/pat-vault-authority-controls/harness13'
HARNESS = BASE / 'harness01'

def digest(body):
    return hashlib.sha256(body).hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def write(path, value):
    body = value.encode() if isinstance(value, str) else (json.dumps(value, indent=2) + '\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream: stream.write(body)

def row(path, base):
    body = path.read_bytes()
    return dict(path=path.relative_to(base).as_posix(), bytes=len(body), sha256=digest(body))

def verify(index, base):
    for item in index['files']:
        path = base / item['path']
        assert row(path, base) == item, path

assert not (SOURCE / 'index.json').exists() and not HARNESS.exists()
verify(read(PRIOR / 'index.json'), ROOT)
verify(read(OLD_HARNESS / 'index.json'), OLD_HARNESS)
baseline = read(SOURCE / 'baseline-inputs.json')
assert len(baseline['files']) == 293
verify(baseline, PROJECT)
new = sorted(p.relative_to(PROJECT).as_posix() for p in PROJECT.rglob('*') if p.is_file()
    and p.relative_to(PROJECT).as_posix() not in {x['path'] for x in baseline['files']})
assert len(new) == 7
for name in new: ast.parse((PROJECT / name).read_bytes())
tree = ast.parse((PROJECT / 'tests/test_vault_recorded_catalog.py').read_bytes())
target_class = next(x for x in tree.body if isinstance(x, ast.ClassDef))
targets = ['test_vault_recorded_catalog.VaultRecordedCatalogTests.' + node.name
    for node in target_class.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')]
assert len(targets) == len(set(targets)) == 14
write(SOURCE / 'test-selection.json', targets)
pins = read(PRIOR / 'identity-pins.json')
names = ('__init__.py','contracts.py','projection.py','bridge.py','catalog.py','execution.py')
host_rows = [row(PROJECT / 'vault_recorded_io' / name, PROJECT / 'vault_recorded_io') for name in names]
for item in host_rows: item['sha256'] = 'sha256:' + item['sha256']
payload = dict(consumerIdentity=pins['consumer'], sources=host_rows)
wire = json.dumps(payload, sort_keys=True, separators=(',',':')).encode('ascii')
pins.update(host='sha256:' + digest(b'HMS-PAT-IO-VAULT-RECORDED-HOST-v0.1\0' + wire),
    hostSources=host_rows, hostIdentityComputedWithoutCandidateExecution=True)
write(SOURCE / 'identity-pins.json', pins)
write(SOURCE / 'source-review.json', dict(reviewer='primary-agent', independentReview=False,
    changedInheritedFiles=[], unchangedInheritedFiles=293, newFiles=new,
    journalSourceUnchanged=True, vaultSourceUnchanged=True, authorityConsumerSourceUnchanged=True,
    originalWorkerBoundsUnchanged=True, publicRuntimeChanged=False, actualWorkerExecuted=False,
    controlsPending=True, physicalObjectiveVerified=False,
    review=['Evidence preparation and complete vault snapshot acquisition precede admission transactions.',
        'Held view and complete relevant catalog inventory are rechecked immediately before business COMMIT.',
        'Commit callbacks perform bounded main-database reads and held-state checks only.',
        'Historical original-key retrieval bypasses fresh preparation and vault access.',
        'New catalog and execution mount versions cannot reuse old profile identities.',
        'Locks acquire execution before Journal, and cache mutex is never held across yield.',
        'Controls substitute only the semantic inspection oracle; they launch no worker.']))
write(SOURCE / 'README.md', '# Isolated authority-vault catalog candidate\n\n'
    'Adds a separate recorded catalog, bridge and execution profile. All 293 inherited files remain exact. '
    '[Review](source-review.json), [identity pins](identity-pins.json), [14 selected controls](test-selection.json). '
    'This is a candidate pending execution, not a public runtime or physical qualification claim.\n')
write(SOURCE / 'index.json', dict(profile='hms.source-inputs/1',
    files=[row(p, ROOT) for p in sorted(SOURCE.rglob('*')) if p.is_file()]))
HARNESS.mkdir()
references = HARNESS / 'references'; references.mkdir()
write(references / 'external-inputs.json', (OLD_HARNESS / 'references/external-inputs.json').read_text())
write(HARNESS / 'targets.json', targets)
for name in ('run_attempt.py', 'attempt_child.py'):
    original = (OLD_HARNESS / name).read_text()
    write(references / ('original-' + name), original)
    updated = original
    if name == 'run_attempt.py':
        updated = updated.replace('assert len(inputs) == 285', 'assert len(inputs) == 300')
        updated = updated.replace('sourceInputs=285', 'sourceInputs=300')
        updated = updated.replace("prefix='hms-vault-controls-'", "prefix='hms-vault-catalog-'")
        updated = updated.replace("targets=targets)", "targets=targets, expectedHost=read(SOURCE / 'identity-pins.json')['host'])")
        updated = updated.replace("assert read(attempt / 'driver-before.json') == read(attempt / 'driver-after.json')",
            "assert read(attempt / 'driver-before.json') == read(attempt / 'driver-after.json')\n"
            "    assert read(attempt / 'host-before.json') == read(attempt / 'host-after.json') == {'host': config['expectedHost']}")
        updated = updated.replace('== 2', '== 14')
    else:
        old_targets = next(line for line in updated.splitlines() if line.startswith('CONTROL_TARGETS = '))
        updated = updated.replace(old_targets, 'CONTROL_TARGETS = ' + repr(targets))
        updated = updated.replace("'driver-before.json', 'driver-after.json',", "'driver-before.json', 'driver-after.json', 'host-before.json', 'host-after.json',")
        updated = updated.replace("or name == 'evidence_vault'", "or name == 'vault_recorded_io' or name.startswith('vault_recorded_io.') or name == 'evidence_authority' or name.startswith('evidence_authority.') or name == 'evidence_vault'")
        updated = updated.replace('!= 2', '!= 14').replace('== 2', '== 14')
        updated = updated.replace("    import unittest\n    from hms.pat_compiler", "    import unittest\n    from vault_recorded_io.contracts import identity as host_identity\n    assert host_identity() == config['expectedHost']\n    write('host-before.json', {'host': host_identity()})\n    from hms.pat_compiler")
        updated = updated.replace("    write('driver-after.json', {'digest': implementation_digest()})", "    write('driver-after.json', {'digest': implementation_digest()})\n    write('host-after.json', {'host': host_identity()})")
    ast.parse(updated)
    write(HARNESS / name, updated)
    write(HARNESS / (name + '.patch'), ''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),fromfile='prior/'+name,tofile=name)))
write(HARNESS / 'SCOPE.md', '# Fourteen no-worker catalog controls\n\n'
    'Exact methods are listed in [targets](targets.json). Parent 180 seconds; child 120 CPU seconds, '
    '512 MiB address space, 64 declared SQLite connections. Original 16 MiB/file, 256 MiB scratch, '
    '8,192 files and 4 MiB output limits remain. Vault snapshot lifetime remains five seconds. '
    'Only the selected fixture oracle is substituted. No worker, network, physical I/O or live service is allowed. '
    'The reviewed native retention scanner may run on fixture files. Raw private scratch and exact copies remain. '
    'Source audit hooks are cooperative checks, not OS isolation or an aggregate disk reservation.\n')
write(HARNESS / 'README.md', '# Bounded first catalog control attempt\n\n'
    '[Bounds](SCOPE.md), [candidate](../implementation01/README.md), [targets](targets.json). '
    'Adapted from the retained authority-controls harness13 with dir-fd-aware open auditing. '
    'Only source count, exact test selection, receipt checks and new package identity tracking change. '
    'No automatic retry or repair of retained failure state.\n')
write(HARNESS / 'index.json', dict(profile='hms.harness-inputs/1',
    files=[row(p, HARNESS) for p in sorted(HARNESS.rglob('*')) if p.is_file()]))
print(json.dumps(dict(sourceFiles=len(read(SOURCE/'index.json')['files']), projectFiles=300,
    sourceIndex=digest((SOURCE/'index.json').read_bytes()), harnessIndex=digest((HARNESS/'index.json').read_bytes()),
    host=pins['host'], tests=len(targets))))
