"""Freeze the original identity correction and adapt the retained pure harness."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path.cwd().resolve()
B = ROOT/'artifacts/implementation/pat-compiler-identity'
S = B/'implementation01'
OLD = ROOT/'artifacts/implementation/pat-io-lifecycle-semantics/implementation02/project'
O = ROOT/'artifacts/implementation/pat-io-lifecycle-semantics/harness02'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2)+'\n')

base = read(S/'baseline-inputs.json')
changed = {'hms/pat_compiler.py', 'hms/pat_simulation_worker.py', 'tests/test_pat_compiler.py'}
assert len(base['inheritedProjectInputs']) == 213 and len(base['excludedFixtureInputs']) == 7542
for row in base['inheritedProjectInputs']:
    p = ROOT/row['path']; rel = p.relative_to(OLD); q = S/'project'/rel
    assert sha(p) == row['sha256'] and p.stat().st_size == row['bytes']
    assert (sha(q) != sha(p)) is (rel.as_posix() in changed)
for row in base['excludedFixtureInputs']:
    p = ROOT/row['path']; assert sha(p) == row['sha256'] and p.stat().st_size == row['bytes']
    assert not (S/'project'/p.relative_to(OLD)).exists()
write(S/'source-review.json', dict(
    scope='Primary-agent full changed source and all 18 new pure tests reviewed before execution.',
    changedFiles=sorted(changed), newFiles=['tests/test_pat_compiler_identity.py'],
    inheritedFiles=213, unchangedInheritedFiles=210, excludedHistoricalFixtures=7542,
    reviewed=[
        'Seven selected mandatory validation packages; explicit version 0.2 manifest and domain separate current identity from historical evidence.',
        'Acquisition caps selected files/bytes and per-distribution inventory, requires regular files and exact observed size, rejects duplicate/escaping/cache selected paths.',
        'Missing selected packages and filesystem failures become structured identity refusals; no missing-file recovery or replacement.',
        'Trusted setup rechecks all selected bytes against the imported manifest without refreshing it. Worker setup calls the check; pure compilation remains unchanged.',
        'Actual-origin and dependency acquisition remain the separate retained harness responsibility. No claim of complete OS, import-path or dynamic-library attestation.',
        '20 existing compiler,14 unit,31 I/O contract and18 new identity methods; no runtime/SQLite/network/subprocess/device/service execution.',
        'All unchanged runtime, provider, recorder and semantic components retain their original bytes; full qualification and aggregate storage remain unfinished.'
    ], independentReview=False, releasedBy='primary-agent', projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Selected compiler identity version 0.2\n\nSee [design](../DESIGN.md) and [source review](source-review.json).\nThe candidate adds both known omitted dependencies and trusted setup rechecks.\nPure compilation remains unchanged. This is not full deployment attestation or\na qualified application. The original historical fixture archives are retained.\n')
rows=[]
for p in sorted(S.rglob('*')):
    assert not p.is_symlink()
    if p.is_file():
        if p.suffix == '.py': ast.parse(p.read_bytes())
        rows.append(dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p)))
assert len(rows) == 217
write(S/'index.json', dict(scope='Frozen isolated compiler identity version 0.2 candidate.', files=rows))
pin = sha(S/'index.json')
assert sha(O/'index.json') == '81a17bd222ab56c09f66fa45b37a4bfae8e89b579597e09bdb3118be9c471941'
for row in read(O/'index.json')['files']:
    assert sha(O/row['path']) == row['sha256'] and (O/row['path']).stat().st_size == row['bytes']
targets=[]
for module, cls, expected in [('test_pat_compiler','PatCompilerTests',20),
                             ('test_pat_fixed_schema_units','FixedSchemaUnitTests',14),
                             ('test_pat_io_contracts','IoContractTests',31),
                             ('test_pat_compiler_identity','CompilerIdentityTests',18)]:
    tree=ast.parse((S/'project/tests'/(module+'.py')).read_bytes())
    node=next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    names=sorted(n.name for n in node.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_') and
                 n.name != 'test_all_three_families_compile_and_execute_across_two_local_aliases')
    assert len(names) == expected
    targets.extend(module+'.'+cls+'.'+name for name in names)
assert len(targets)==83
H=B/'harness01'; H.mkdir(); (H/'references').mkdir(); borrowed=[]
for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
    p=O/item; q=H/'references'/p.name; shutil.copyfile(p,q)
    borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
write(H/'borrowed-inputs.json',borrowed)
write(H/'targets.json',dict(testCount=83,targets=targets))
for item in ['run_attempt.py','attempt_child.py']:
    before=(O/item).read_text()
    after=before.replace('9171613b64444be9d79b10576852cda6411a0a46c7adcd1138e8e983948ee1d4',pin)
    after=after.replace('pat-io-lifecycle-semantics','pat-compiler-identity').replace('io-lifecycle-semantics','pat-compiler-identity')
    after=after.replace('implementation02','implementation01').replace('7758','217').replace('7755','214')
    after=after.replace('LifecycleHistory58','CompilerIdentity83').replace('lifecycle58','identity83')
    after=after.replace('!= 58','!= 83').replace('== 58','== 83').replace("'expectedTests': 58","'expectedTests': 83")
    after=after.replace("name.startswith('test_pat_io_lifecycle_semantics.')", "name.startswith(('test_pat_compiler.', 'test_pat_fixed_schema_units.', 'test_pat_io_contracts.', 'test_pat_compiler_identity.'))")
    after=after.replace("compiler's five-package identity", "compiler's seven-package identity")
    after=after.replace('pure semantic/history methods','pure compiler/contract methods').replace('Pure lifecycle history','Pure compiler identity')
    ast.parse(after); (H/item).write_text(after)
    (H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
        fromfile=(O/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
(H/'README.md').write_text('# Pure compiler identity selection\n\n[83 exact methods](targets.json), [frozen candidate](../implementation01/README.md),\nand [scope](SCOPE.md). Source and complete harness deltas are reviewed before\nexecution. Seven selected external inventories and actual origins are checked.\n')
(H/'SCOPE.md').write_text('# Original pure execution boundaries\n\n83 exact methods:20 compiler,14 fixed-unit,31 I/O contract and18 identity.\nEvery SQLite connection, network and child subprocess is forbidden. No runtime,\nphysical device, MCU, inference or live service execution. Original180s,16MiB\nscratch,8192 inventory files,256MiB inputs,16MiB file,4MiB JSON and8MiB logs\nremain unchanged. Retain all attempts and original private scratch.\nSelected compiler closure is not complete deployment or OS attestation.\n')
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=214,frozenFiles=217,tests=83,targetSha256=sha(H/'targets.json'))))
