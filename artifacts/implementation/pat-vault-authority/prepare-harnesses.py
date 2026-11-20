"""Freeze reviewed source and two disjoint, bounded control-test selections."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = BASE / 'implementation01'
OLD = ROOT / 'artifacts/implementation/pat-evidence-vault/harness03'
assert hashlib.sha256((OLD / 'index.json').read_bytes()).hexdigest() == '85b87454013a41189edd60bbf3e2c84b4b81a1b0b8b81fdbd7e13f7a0393c5aa'

def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(body if type(body) is bytes else body.encode())

def dump(path, value):
    write(path, json.dumps(value, indent=2) + '\n')

for row in json.loads((OLD / 'index.json').read_bytes())['files']:
    path = OLD / row['path']; body = path.read_bytes()
    assert len(body) == row['bytes'] and hashlib.sha256(body).hexdigest() == row['sha256']
for row in json.loads((SOURCE / 'baseline-inputs.json').read_bytes())['files']:
    body = (SOURCE / 'project' / row['path']).read_bytes()
    assert len(body) == row['bytes'] and hashlib.sha256(body).hexdigest() == row['sha256']
project = sorted(path for path in (SOURCE / 'project').rglob('*') if path.is_file())
assert len(project) == 284
for path in project:
    assert not path.is_symlink()
    if path.suffix == '.py': ast.parse(path.read_bytes(), filename=str(path))
test = ast.parse((SOURCE / 'project/tests/test_vault_authority.py').read_bytes())
cls = next(node for node in test.body if isinstance(node, ast.ClassDef))
targets = ['test_vault_authority.VaultAuthorityTests.' + node.name for node in cls.body
           if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')]
assert len(targets) == len(set(targets)) == 19
write(SOURCE / 'README.md', '# Authority-bound vault publication candidate\n\n'
    'All 280 inherited project files remain exact. Three new production modules and one new test module add explicit installation, durable original import intents and held-snapshot publication.\n\n'
    'The 19 controls substitute a declared semantic oracle and launch no worker. They do not establish actual-matrix or physical qualification. The distinct profile is not mounted in the compact catalog or public service.\n')
dump(SOURCE / 'source-review.json', dict(review='Primary-agent source and failure-boundary review; helpers unavailable until recorded usage reset',
    inheritedFilesUnchanged=280, productionModulesAdded=3, methods=targets,
    reviewed=['Actual execution/Journal/vault objects and administrator installation',
        'Vault descriptor persisted in authority anchor; no attached database',
        'Original evaluator/run intent recorded before archive read',
        'Original archive and semantic reducer retained; no worker start API',
        'Execution -> vault read ownership -> short Journal transaction lock order',
        'Source/supervisor/archive reads outside control transaction',
        'Recheck authorization, configuration, original association and snapshot before publication',
        'Interrupted intent/seal/publication boundaries preserve original key and evidence',
        'Logical charges only; no physical reserve or aggregate quota claim'],
    remaining=['Actual-data original-run import through this profile', 'Held-snapshot catalog profile',
        'Pre-recovery Journal cap and backed capacity', 'Hot-journal recovery', 'Public tools and physical providers']))
source_files = []
for path in sorted(SOURCE.rglob('*')):
    if path.is_file():
        body = path.read_bytes()
        source_files.append(dict(path=path.relative_to(ROOT).as_posix(), bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
dump(SOURCE / 'index.json', dict(scope='New authority-owned independent-vault import component; no production files replaced', files=source_files))

for number, selection in enumerate((targets[:10], targets[10:]), 1):
    folder = BASE / ('harness%02d' % number)
    folder.mkdir()
    child_original = (OLD / 'attempt_child.py').read_text()
    parent_original = (OLD / 'run_attempt.py').read_text()
    child = child_original.replace('Vault child: exact source origins, one corrected control/quiescence method.',
        'Authority-vault controls: exact sources, no worker or physical effect.')
    old_targets = "CONTROL_TARGETS = ['test_evidence_vault.VaultTests.test_page_capacity_rolls_back_and_control_still_completes']"
    assert old_targets in child
    child = child.replace(old_targets, 'CONTROL_TARGETS = ' + repr(selection))
    start = child.index("        fixture = Path(config['originalDatabase']).resolve()")
    end = child.index('        sqlite_connections.append', start)
    board = 'runtime/synthetic-io-board-' + hashlib.sha256(b'board').hexdigest() + '.db'
    allowed = ['runtime/authority.db', board, 'supervisor/attempts.db', 'vault/evidence.db', 'wrong-vault/evidence.db']
    child = child[:start] + "        if current_test is None:\n            raise RuntimeError('SQLite before selected method')\n        parent = scratch / current_test.split('.')[-1]\n        allowed = " + repr(allowed) + "\n        if path not in {parent / name for name in allowed}:\n            raise RuntimeError('SQLite outside declared current control fixture')\n" + child[end:]
    child = child.replace("len(config['targets']) != 1 or len(set(config['targets'])) != 1", "len(config['targets']) != %d or len(set(config['targets'])) != %d" % (len(selection), len(selection)))
    child = child.replace("    os.environ['HMS_VAULT_TEST_ROOT'] = str(scratch)\n    os.environ['HMS_VAULT_ORIGINAL_DATABASE'] = config['originalDatabase']\n", '')
    child = child.replace("counts['testsRun'] == 1 and", "counts['testsRun'] == %d and" % len(selection))
    parent = parent_original.replace("SOURCE = BASE / 'implementation02'", "SOURCE = BASE / 'implementation01'")
    parent = parent.replace('len(inputs) == 280', 'len(inputs) == 284').replace('sourceInputs=280', 'sourceInputs=284')
    start = parent.index("original = ROOT / 'artifacts/implementation/pat-io-definition-build/")
    end = parent.index("child_path = attempt / 'attempt_child.py'", start)
    parent = parent[:start] + parent[end:]
    parent = parent.replace('len(targets) == len(set(targets)) == 1', 'len(targets) == len(set(targets)) == %d' % len(selection))
    parent = parent.replace('originalDatabase=str(fixture), externalRoots=', 'externalRoots=')
    parent = parent.replace("    assert sha(fixture) == sha(original) == 'f106c3312d0c05b69be52b5fae65edd19892b9c019bd62d6691ec3555cc93099'\n", '')
    parent = parent.replace("counts['testsRun'] == 1 and", "counts['testsRun'] == %d and" % len(selection))
    parent = parent.replace('    originalDataFileUnchanged=sha(fixture) == sha(original),\n', '')
    assert 'originalDatabase' not in child and 'fixture' not in parent
    ast.parse(child); ast.parse(parent)
    for name, original, body in [('attempt_child.py', child_original, child), ('run_attempt.py', parent_original, parent)]:
        write(folder / name, body)
        write(folder / 'references' / ('original-' + name), original)
        write(folder / (name + '.patch'), ''.join(difflib.unified_diff(original.splitlines(True), body.splitlines(True),
            fromfile='sealed-harness03/' + name, tofile='new-authority-controls/' + name)))
    write(folder / 'references/external-inputs.json', (OLD / 'references/external-inputs.json').read_bytes())
    dump(folder / 'targets.json', selection)
    write(folder / 'README.md', '# Authority-vault controls, scope %d\n\n[Selection](targets.json), [bounds](SCOPE.md), [source](../implementation01/README.md).\n' % number)
    write(folder / 'SCOPE.md', '# Reviewed bounded control scope\n\n'
        '%d explicit methods; this scope is disjoint from the other scope. Every method uses fresh retained state.\n\n' % len(selection) +
        'Parent: 180 seconds, 16 MiB/file, 256 MiB scratch, 4 MiB output, 8,192 retained entries. Child: 120 CPU seconds, 512 MiB address space, 16 MiB/file, at most 64 declared SQLite connections. These bounds are unchanged.\n\n'
        'Only synthetic runtime authority/board, original-request supervisor ledger and independent vault fixtures may open SQLite. No network, child process, actual qualification worker or device access. Semantic success uses an explicitly substituted oracle. Exact project and dependency origins are checked; audit hooks are cooperative guardrails, not an OS sandbox.\n\n'
        'Only the two parent test launchers are executable entry points for this selection. No acquired controller code executes. Failures are retained without reset or widened limits.\n')
    files = []
    for path in sorted(folder.rglob('*')):
        if path.is_file():
            body = path.read_bytes(); files.append(dict(path=path.relative_to(folder).as_posix(), bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
    dump(folder / 'index.json', dict(scope='Disjoint authority publication controls with declared substituted semantic oracle', files=files))
print(json.dumps(dict(projectFiles=284, inheritedUnchanged=280, methods=19,
    scopes=[10, 9], sourceIndexSha256=hashlib.sha256((SOURCE / 'index.json').read_bytes()).hexdigest())))
