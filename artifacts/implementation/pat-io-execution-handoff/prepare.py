"""Freeze the reviewed handoff candidate and exact original/new test scopes."""
import ast
import copy
import difflib
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path.cwd()
B = ROOT/'artifacts/implementation/pat-io-execution-handoff'
O = ROOT/'artifacts/implementation/pat-io-document-validation'
S, P = B/'implementation01', O/'implementation01'
OLD_PIN = '31118f7405fcce5f4828bf4d256faea21e61b6d5bae470632376d9c8c484c4c0'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path, value):
    with path.open('x') as stream: stream.write(json.dumps(value, indent=2)+'\n')
def inventory(folder, rooted=False):
    rows = []
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            if path.suffix == '.py': ast.parse(path.read_bytes())
            rows.append(dict(path=path.relative_to(ROOT if rooted else folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    return sorted(rows, key=lambda row:row['path'])

assert sha(P/'index.json') == OLD_PIN
for row in read(P/'index.json')['files']:
    assert (ROOT/row['path']).stat().st_size == row['bytes'] and sha(ROOT/row['path']) == row['sha256']
baseline = read(S/'baseline-inputs.json')['inheritedProjectInputs']
changed = [(ROOT/row['path']).relative_to(P/'project').as_posix() for row in baseline
           if sha(S/'project'/(ROOT/row['path']).relative_to(P/'project')) != row['sha256']]
assert len(baseline) == 248 and changed == ['supervisor/attempt_ledger.py', 'supervisor/supervisor_contracts.py']

# Expand the two metadata hooks and lifted SQL literals to compare the entire
# original legacy ledger AST. The new subclass opts into different metadata.
old_tree = ast.parse((P/'project/supervisor/attempt_ledger.py').read_bytes())
new_tree = ast.parse((S/'project/supervisor/attempt_ledger.py').read_bytes())
constants = {node.targets[0].id:node.value for node in new_tree.body if isinstance(node, ast.Assign)
             and isinstance(node.targets[0], ast.Name) and node.targets[0].id in {'ATTEMPT_SQL', 'INDEX_SQL'}}
cls = next(node for node in new_tree.body if isinstance(node, ast.ClassDef) and node.name == 'AttemptLedger')
hooks = {node.name:node.body for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in {'_create_metadata', '_check_metadata'}}
class Expand(ast.NodeTransformer):
    def visit_Expr(self, node):
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and node.value.func.attr in hooks:
            return copy.deepcopy(hooks[node.value.func.attr])
        return self.generic_visit(node)
    def visit_Name(self, node):
        return copy.deepcopy(constants[node.id]) if node.id in constants and isinstance(node.ctx, ast.Load) else node
new_tree.body = [node for node in new_tree.body if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in constants)]
cls.body = [node for node in cls.body if not (isinstance(node, ast.FunctionDef) and node.name in hooks)]
new_tree = Expand().visit(new_tree)
assert ast.dump(old_tree, include_attributes=False) == ast.dump(new_tree, include_attributes=False)
for name in changed:
    before, after = (P/'project'/name).read_text(), (S/'project'/name).read_text()
    (B/(Path(name).stem+'-change.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=str(P/'project'/name), tofile=str(S/'project'/name))))
trees = []
for project in (P/'project', S/'project'):
    tree = ast.parse((project/'supervisor/supervisor_contracts.py').read_bytes())
    tree.body = [node for node in tree.body if not (isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SOURCE_FILES' for t in node.targets))]
    trees.append(ast.dump(tree, include_attributes=False))
assert trees[0] == trees[1]

def targets(name, clsname):
    tree = ast.parse((S/'project/tests'/(name+'.py')).read_bytes())
    cls = next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name == clsname)
    return sorted(name+'.'+clsname+'.'+node.name for node in cls.body if isinstance(node,ast.FunctionDef) and node.name.startswith('test_'))
authority = targets('test_supervisor_authority', 'SupervisorAuthorityTests')
handoff = targets('test_io_service_execution', 'IoServiceExecutionTests')
process = targets('test_io_service_execution', 'IoServiceExecutionProcessTests')
assert (len(authority), len(handoff), len(process)) == (13, 32, 1)
assert len(inventory(S/'project')) == 252
reviewed = [
    '246 inherited project files and every inherited test remain unchanged. Legacy ledger AST is identical after expansion of the two metadata hooks and SQL constants. Supervisor contract change only adds two source-identity entries.',
    'Explicit version-2 authority ledger generates its identity at creation, requires a pin on reopen, validates exact bounded schema/metadata and refuses legacy, missing, replaced or corrupt state. Legacy reader refuses version2; no migration/reset.',
    'Journal-owned immutable mount and bounded receipt chain join reservation digest, actual supervisor authority, exact request and attempt ID. Shared Journal transaction/connection; no worker or physical state is hidden in the Journal.',
    'Only the invocation that creates a supervisor row and commits its association calls the original launch path. Existing rows reconcile without launch; missing rows after association refuse. Current admin authorization remains mandatory on historical lookup/replay.',
    'New admission checks current configuration, actual descriptors, source and runtime before admission and association. The durable association is an admission decision for an isolated qualification job, not an effect-time lease on source devices.',
    'No cross-database atomicity or coordinated-rollback guarantee. Nonblocking execution lock; no ledger transaction enters Journal; no calls from an existing Journal transaction. Original pidfd/writer lease/reopen/interrupt/archive behavior remains.',
    '13 authority controls plus32 handoff controls have no producer/network/physical access. Handoff tests substitute only the launch boundary and claim no actual worker completion. Separate process method retains full30-case independent inspection and replay after configuration/session drift.',
    'All298 inherited methods remain selected. Original60s worker/group and180s harness ceilings, source/effect/storage bounds and complete30-case matrix remain. New worker image262files including10supervisor sources and157runtime dependencies.',
    'Fixed new encoded handoff accounting256KiB/32rows is not an aggregate filesystem quota. Deadline/retention failures, public mounting, evidence import/promotion, learning, persistent Arduino and physical I/O/driver/hub providers remain open.',
    'No physical endpoint, acquired controller code, MCU/emulator, live inference/service or adjacent Harness checkout. Primary-agent review only; all prior retained failures remain immutable.'
]
write(S/'source-review.json', dict(scope='Durable supervisor authority and two-store execution handoff',
    changedInheritedFiles=changed, unchangedInheritedFiles=246, newProjectFiles=4, reviewed=reviewed,
    independentReview=False, releasedBy='primary-agent', projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Durable supervisor handoff candidate\n\n[Design](../DESIGN.md), [source review](source-review.json). Original execution and recovery limits remain. Acceptance requires separately retained test evidence.\n')
rows = inventory(S, True); assert len(rows) == 255
write(S/'index.json', dict(scope='Frozen supervisor-authority and durable handoff candidate with46new methods.', files=rows))
pin = sha(S/'index.json')

selections = [(n, n, read(O/('harness%02d'%n)/'targets.json')['targets'], 'inherited') for n in range(1,18)]
selections.append((18, 1, authority, 'authority'))
for offset in range(0, len(handoff), 6): selections.append((19+offset//6, 14, handoff[offset:offset+6], 'handoff'))
selections.append((25, 16, process, 'process'))
all_targets = set()
for number, prior_number, selection, kind in selections:
    prior = O/('harness%02d'%prior_number)
    for row in read(prior/'index.json')['files']: assert sha(prior/row['path']) == row['sha256']
    old_targets = read(prior/'targets.json')['targets']; count = len(selection)
    assert not all_targets.intersection(selection); all_targets.update(selection)
    harness = B/('harness%02d'%number); harness.mkdir(); (harness/'references').mkdir()
    borrowed = []
    for name in ('run_attempt.py', 'attempt_child.py', 'references/approved-external-roots.json'):
        source, destination = prior/name, harness/'references'/Path(name).name
        shutil.copyfile(source, destination)
        borrowed.append(dict(source=source.relative_to(ROOT).as_posix(), copy=destination.relative_to(harness).as_posix(), bytes=source.stat().st_size, sha256=sha(source)))
    write(harness/'borrowed-inputs.json', borrowed)
    write(harness/'targets.json', dict(testCount=count, targets=selection))
    for name in ('run_attempt.py', 'attempt_child.py'):
        original = (prior/name).read_text()
        updated = original.replace(OLD_PIN, pin).replace(O.name, B.name)
        updated = re.sub(r'\b248\b', '252', updated); updated = re.sub(r'\b251\b', '255', updated)
        if kind != 'inherited':
            if name == 'run_attempt.py':
                assert updated.count(repr(old_targets)) == 1
                updated = updated.replace(repr(old_targets), repr(selection))
            if kind in ('authority', 'handoff'):
                updated = re.sub(r'\b'+str(len(old_targets))+r'\b', str(count), updated)
                if name == 'attempt_child.py':
                    start = updated.index('CONTROL_TARGETS = '); end = updated.index('\ndef audit(', start)
                    updated = updated[:start]+'CONTROL_TARGETS = '+repr(selection)+'\n'+updated[end:]
                    start = updated.index("    if event == 'sqlite3.connect':"); end = updated.index("    if event == 'exec':", start)
                    validity = "path.parent.name in {'supervisor','other','legacy'} and path.name=='attempts.db'" if kind == 'authority' else "((path.parent.name in {'supervisor','replacement'} and path.name=='attempts.db') or (path.parent.name=='runtime' and (path.name=='authority.db' or re.fullmatch(r'synthetic-io-board-[0-9a-f]{64}\\.db',path.name))))"
                    guard = """    if event == 'sqlite3.connect':
        path=Path(os.fsdecode(os.fspath(args[0])))
        method=current_test.rsplit('.',1)[1] if current_test in CONTROL_TARGETS else 'invalid'
        valid=VALIDITY
        if current_test not in CONTROL_TARGETS or path.parent.parent!=scratch/method or not valid:
            prohibited.append(event); raise RuntimeError('Only exact declared authority/handoff fixture databases may open')
        if len(sqlite_connections)>=TOTAL or sum(c['testId']==current_test for c in sqlite_connections)>=PER_TEST:
            raise RuntimeError('Declared database inventory bound')
        sqlite_connections.append({'testId':current_test,'database':str(path)})
""".replace('VALIDITY', validity).replace('TOTAL', str(32 if kind == 'authority' else 36)).replace('PER_TEST', str(4 if kind == 'authority' else 6))
                    updated = updated[:start]+guard+updated[end:]
            else:
                old_method, new_method = old_targets[0].rsplit('.',1)[1], selection[0].rsplit('.',1)[1]
                updated = updated.replace(old_method, new_method)
                if name == 'attempt_child.py':
                    updated = updated.replace('len(sqlite_connections)>=9', 'len(sqlite_connections)>=6').replace('Declared nine parent', 'Declared six parent')
        ast.parse(updated)
        (harness/name).write_text(updated)
        (harness/(name+'.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True), fromfile=str(prior/name), tofile=str(harness/name))))
    scope = {'inherited':'Unchanged inherited selection with expanded source identity.',
             'authority':'Thirteen supervisor-authority controls; no producer launch.',
             'handoff':'Exact handoff controls; launch boundary substituted, no producer execution.',
             'process':'One actual bound reserved worker with original full30-case inspection and historical replay.'}[kind]
    (harness/'SCOPE.md').write_text('# Exact scope\n\n'+scope+'\n\n[Design](../DESIGN.md), [targets](targets.json). Original execution/effect/storage ceilings remain.\n')
    (harness/'README.md').write_text('# Supervisor authority and handoff checks\n\n[Scope](SCOPE.md), [targets](targets.json), [source](../implementation01/README.md).\n')
    review = read(prior/'review.json'); review.pop('correction', None)
    review.update(scope=scope, tests=count, sourceIndexSha256=pin, targetSha256=sha(harness/'targets.json'),
                  reviewed=reviewed, inheritedHarnessIndexSha256=sha(prior/'index.json'), selectionKind=kind)
    if kind != 'inherited':
        review.update(controlTargets=selection if kind != 'process' else [],
            controlLabels=['supervisor','other','legacy'] if kind == 'authority' else ['runtime','supervisor','replacement'],
            sqliteConnectionsMaximum=32 if kind == 'authority' else 36 if kind == 'handoff' else 6,
            sqliteConnectionsPerMethod=4 if kind == 'authority' else 6)
    write(harness/'review.json', review)
    write(harness/'index.json', dict(scope=scope, files=inventory(harness)))
assert len(all_targets) == 344
print(json.dumps(dict(sourceIndexSha256=pin, projectFiles=252, frozenFiles=255,
                     harnesses=len(selections), distinctSelectedMethods=len(all_targets), newMethods=46)))
