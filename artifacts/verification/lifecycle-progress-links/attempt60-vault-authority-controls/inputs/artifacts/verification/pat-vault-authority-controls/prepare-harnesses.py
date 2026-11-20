"""Freeze unchanged production and all remaining/additional authority controls."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = BASE / 'implementation01'
PRIOR = ROOT / 'artifacts/implementation/pat-vault-authority'
TEMPLATE = PRIOR / 'harness19'

def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream: stream.write(body if type(body) is bytes else body.encode())
def dump(path, value): write(path, json.dumps(value, indent=2) + '\n')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

assert sha(PRIOR / 'index.json') == '2e70bbbe937208237d56335b1884070df770e611441f6018042154ebdeb24da6'
assert sha(TEMPLATE / 'index.json') == 'c1367ee257c225515094da7265cd3e6e34a319c760957a78b0b8f5c16e48e913'
for row in json.loads((TEMPLATE / 'index.json').read_bytes())['files']:
    path = TEMPLATE / row['path']; assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
baseline = json.loads((SOURCE / 'baseline-inputs.json').read_bytes())['files']
assert len(baseline) == 284
for row in baseline:
    path = SOURCE / 'project' / row['path']; assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
project = sorted(path for path in (SOURCE / 'project').rglob('*') if path.is_file())
assert len(project) == 285
for path in project:
    assert not path.is_symlink()
    if path.suffix == '.py': ast.parse(path.read_bytes(), filename=str(path))
remaining = json.loads((PRIOR / 'pending-methods.json').read_bytes())['methods']; assert len(remaining) == 17
tree = ast.parse((SOURCE / 'project/tests/test_vault_authority_edges.py').read_bytes())
cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
edges = ['test_vault_authority_edges.VaultAuthorityEdgeTests.' + node.name for node in cls.body
         if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')]
assert len(edges) == 5
targets = remaining + edges; assert len(targets) == len(set(targets)) == 22
write(SOURCE / 'README.md', '# Corrected authority importer: remaining controls\n\n'
    'All 284 inherited project files remain exact. One new test module adds five authority-boundary controls; no production code changes. '
    'The selection contains all 17 pending methods plus those five new controls. Three prior focused methods already passed on identical production. '
    'The original aggregate timing failure remains failed. The semantic oracle is explicitly substituted; no worker or physical device executes.\n')
dump(SOURCE / 'source-review.json', dict(review='Primary-agent review of new control fixtures and unchanged production; helper usage reset not reached',
    inheritedFilesUnchanged=284, productionChanged=False, remainingMethods=remaining, additionalMethods=edges,
    coverage=['Original current-source publication and replay controls',
        'Injected changed consumer identity detection before replay',
        'Malformed authority record type refuses before variable-width body fetch without repair',
        'Installation rollback before commit preserves original empty vault',
        'Lost installation reply reconciles original association without a new identity',
        'Published historical evidence after configuration drift is not fresh catalog eligibility'],
    noWorkerExecuted=True, physicalEffects=False, actualOriginalRunQualification=False))
files = []
for path in sorted(SOURCE.rglob('*')):
    if path.is_file(): files.append(dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
dump(SOURCE / 'index.json', dict(scope='Test-only addition on unchanged corrected authority/vault production', files=files))
scopes = []
for offset in range(0, len(targets), 2):
    selection = targets[offset:offset + 2]; number = 1 + offset // 2
    folder = BASE / ('harness%02d' % number); folder.mkdir()
    for filename in ('attempt_child.py', 'run_attempt.py'):
        original = (TEMPLATE / filename).read_text()
        body = original
        if filename == 'attempt_child.py':
            start = body.index('CONTROL_TARGETS = '); end = body.index('\n', start)
            body = body[:start] + 'CONTROL_TARGETS = ' + repr(selection) + body[end:]
            body = body.replace("len(config['targets']) != 1 or len(set(config['targets'])) != 1", "len(config['targets']) != 2 or len(set(config['targets'])) != 2")
        else:
            body = body.replace("SOURCE = BASE / 'implementation02'", "SOURCE = BASE / 'implementation01'")
            body = body.replace('len(inputs) == 284', 'len(inputs) == 285').replace('sourceInputs=284', 'sourceInputs=285')
            body = body.replace('len(targets) == len(set(targets)) == 1', 'len(targets) == len(set(targets)) == 2')
            body = body.replace("prefix='hms-vault-authority-'", "prefix='hms-vault-controls-'")
        body = body.replace("counts['testsRun'] == 1 and", "counts['testsRun'] == 2 and")
        ast.parse(body)
        write(folder / filename, body)
        write(folder / 'references' / ('original-' + filename), original)
        write(folder / (filename + '.patch'), ''.join(difflib.unified_diff(original.splitlines(True), body.splitlines(True),
            fromfile='sealed-harness19/' + filename, tofile=folder.name + '/' + filename)))
    write(folder / 'references/external-inputs.json', (TEMPLATE / 'references/external-inputs.json').read_bytes())
    dump(folder / 'targets.json', selection)
    write(folder / 'README.md', '# Corrected-authority controls, scope %02d\n\n[Targets](targets.json), [bounds](SCOPE.md), [source](../implementation01/README.md).\n' % number)
    write(folder / 'SCOPE.md', '# Two disjoint methods on unchanged production\n\n'
        'The eleven selections contain all 17 remaining current-source controls plus five additional boundary controls. '
        'Together with the three preceding focused controls, they cover the full 25-method current selection only if every required receipt passes. '
        'Original failed scopes remain failed. This does not assert an aggregate timing pass.\n\n'
        'Parent 180 seconds, 4 MiB output, 16 MiB/file, 256 MiB scratch, 8,192 entries; child 120 CPU seconds, 512 MiB address space, 64 declared SQLite connections. '
        'The production snapshot remains five seconds. Raw private /tmp state and exact retained copies remain; no reset, changed key, widened bound or dropped document. '
        'No network, actual qualification worker or physical execution. The semantic oracle is a declared substitute. Source/package audit hooks are cooperative guardrails, not OS isolation.\n')
    files = []
    for path in sorted(folder.rglob('*')):
        if path.is_file(): files.append(dict(path=path.relative_to(folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    dump(folder / 'index.json', dict(scope='Two unchanged/current authority controls; full selection requires every named receipt', files=files))
    scopes.append(dict(harness=folder.name, targets=selection))
dump(BASE / 'selection.json', dict(priorStageIndexSha256=sha(PRIOR / 'index.json'), priorSourceIndexSha256=sha(PRIOR / 'implementation02/index.json'),
    unchangedConsumerIdentity='sha256:0e7ff6440fdb93e941ff4b5b0f2f275558f67f1e63a3c719c66756f81b7971d5',
    priorPassingMethods=json.loads((PRIOR / 'PROGRESS-RESULTS.json').read_bytes())['currentSourcePassingMethods'],
    targets=targets, scopes=scopes, productionUnchanged=True, originalAggregatePassed=False))
print(json.dumps(dict(projectFiles=285, unchangedInherited=284, newMethods=5, selectedMethods=22,
    sourceIndexSha256=sha(SOURCE / 'index.json'), scopes=len(scopes))))
