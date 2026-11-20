"""Pin unchanged production plus five controls and the sealed-native auditor."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
OLD=BASE/'implementation01';SOURCE=BASE/'implementation02';PROJECT=SOURCE/'project'
TEMPLATE=BASE/'harness01'
NATIVE=ROOT/'artifacts/implementation/pat-integer-canonical/harness01'
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:stream.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')
def row(path,root):return dict(path=str(path.relative_to(root)),bytes=path.stat().st_size,sha256=sha(path))
def verify(index,root):
    for item in index['files']:assert row(root/item['path'],root)==item
assert not (SOURCE/'index.json').exists()
verify(read(OLD/'index.json'),ROOT);verify(read(TEMPLATE/'index.json'),TEMPLATE)
verify(read(SOURCE/'baseline-inputs.json'),PROJECT)
assert len(read(SOURCE/'baseline-inputs.json')['files'])==300
pin=next(x for x in read(NATIVE/'index.json')['files'] if x['path']=='attempt_child.py')
assert row(NATIVE/'attempt_child.py',NATIVE)==pin
native_source=(NATIVE/'attempt_child.py').read_text()
guard=native_source[native_source.index('native_load = None'):native_source.index('\ndef audit(event, args):')]
guard=guard.replace("if current_test != config['targets'][0]:", "if current_test not in config['targets']:")
guard=guard.replace('Native retention is only authorized inside the exact actual test','Native retention is only authorized inside an exact selected control')
guard=guard.replace("expected = scratch / 'test_actual_original_matrix_import_and_cold_vault_history' / 'supervisor'", "expected = scratch / current_test.split('.')[-1] / 'supervisor'")
origin_start=native_source.index("        if label == 'module:_hms_retention_native_v1':")
origin_end=native_source.index('        path = Path(origin).resolve()',origin_start)
origin_block=native_source[origin_start:origin_end]
old_targets=read(OLD/'test-selection.json')
test_path=PROJECT/'tests/test_vault_catalog_inventory.py';tree=ast.parse(test_path.read_bytes())
cls=next(x for x in tree.body if isinstance(x,ast.ClassDef))
new_targets=['test_vault_catalog_inventory.VaultCatalogInventoryTests.'+x.name for x in cls.body
    if isinstance(x,ast.FunctionDef) and x.name.startswith('test_')]
assert len(new_targets)==5
selection=old_targets+new_targets
write(SOURCE/'test-selection.json',selection)
write(SOURCE/'identity-pins.json',(OLD/'identity-pins.json').read_text())
write(SOURCE/'source-review.json',dict(reviewer='primary-agent',independentReview=False,
    productionUnchanged=True,unchangedInheritedFiles=300,newFiles=['tests/test_vault_catalog_inventory.py'],
    hostIdentityUnchanged=True,publicRuntimeChanged=False,actualWorkerExecuted=False,
    physicalObjectiveVerified=False,controlsPending=True,
    review=['Two original GPIO/PWM fixture runs import separate intents, manifests and publications.',
        'Both active PATs match the same request; both must enter one held view before ambiguity is reported.',
        'Removing one prepared entry or one unique second-run body cannot authorize the other PAT.',
        'Caller authorization excludes an unrelated source before requiring its cache entry.',
        'A failure after actual COMMIT must reconcile the original run key without fresh evidence.']))
write(SOURCE/'README.md','# Catalog candidate with complete-inventory controls\n\n'
    'Production and host identities are byte-for-byte unchanged from implementation01. '
    'One new test file adds five controls; the complete selection now has 19 methods. '
    '[Review](source-review.json), [identity pins](identity-pins.json), [selection](test-selection.json). '
    'The original qualification oracle remains explicitly substituted. No actual worker or physical device runs.\n')
write(SOURCE/'index.json',dict(files=[row(p,ROOT) for p in sorted(SOURCE.rglob('*')) if p.is_file()]))
groups=[old_targets[i:i+3] for i in range(0,len(old_targets),3)]+[[x] for x in new_targets]
scopes=[]
for number,targets in enumerate(groups,7):
    harness=BASE/('harness%02d'%number);harness.mkdir();count=len(targets)
    write(harness/'targets.json',targets)
    write(harness/'references/external-inputs.json',(TEMPLATE/'references/external-inputs.json').read_text())
    write(harness/'references/native-guard-origin.json',dict(path=str((NATIVE/'attempt_child.py').relative_to(ROOT)),sha256=pin['sha256']))
    write(harness/'references/native-boundary.py',guard)
    for name in ('run_attempt.py','attempt_child.py'):
        before=(TEMPLATE/name).read_text();after=before
        after=after.replace('== 14','== '+str(count)).replace('!= 14','!= '+str(count))
        if name=='run_attempt.py':
            after=after.replace("SOURCE = BASE / 'implementation01'","SOURCE = BASE / 'implementation02'")
            after=after.replace('assert len(inputs) == 300','assert len(inputs) == 301').replace('sourceInputs=300','sourceInputs=301')
        else:
            line=next(x for x in after.splitlines() if x.startswith('CONTROL_TARGETS = '))
            after=after.replace(line,'CONTROL_TARGETS = '+repr(targets))
            after=after.replace('import hashlib\n','import hashlib\nimport fcntl\n',1)
            after=after.replace('\ndef audit(event, args):','\n'+guard+'\ndef audit(event, args):',1)
            after=after.replace('def audit(event, args):\n', "def audit(event, args):\n    if event.startswith('hms.retention.'):\n        native_boundary(event, args)\n        return\n",1)
            marker='        path = Path(origin).resolve()\n        key = (label, str(path))'
            assert marker in after
            after=after.replace(marker,origin_block+marker,1)
            after=after.replace("            'deniedBytecodeReads': sorted(denied_bytecode),",
                "            'nativeRetention': dict(load=native_load, image=native_image, scans=list(native_scans.values())),\n            'deniedBytecodeReads': sorted(denied_bytecode),",1)
        ast.parse(after);write(harness/name,after)
        write(harness/(name+'.patch'),''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='harness01/'+name,tofile=harness.name+'/'+name)))
    write(harness/'SCOPE.md','# '+str(count)+' exact no-worker controls\n\n'
        '[Targets](targets.json) use implementation02 with unchanged production. The native guard is derived '
        'from the full-worker harness: exact source digest, loaded descriptor bytes, ownership, seals and bounded '
        'scan roots are verified. Only the selected fixture name determines its private supervisor root. '
        'No unrecognized native image is accepted. Parent 180 seconds; child 120 CPU seconds, 512 MiB address '
        'space and 64 SQLite opens; 16 MiB/file, 256 MiB retained scratch, 8,192 files, 4 MiB output and five-second '
        'vault lifetime remain unchanged. No qualification worker, network, physical I/O or live service. '
        'The semantic oracle remains a fixture. Separate scopes do not imply an aggregate timing pass.\n')
    write(harness/'README.md','# Bounded catalog controls with exact native image audit\n\n'
        '[Candidate](../implementation02/README.md), [targets](targets.json), [limits](SCOPE.md). '
        'The first run was killed; two smaller scopes passed their tests but failed the older origin auditor. '
        'Those results remain unchanged. This harness verifies the memory image instead of treating its resolved '
        'memfd label as a missing filesystem path.\n')
    write(harness/'index.json',dict(files=[row(p,harness) for p in sorted(harness.rglob('*')) if p.is_file()]))
    scopes.append(dict(harness=harness.name,indexSha256=sha(harness/'index.json'),targets=targets))
write(BASE/'corrected-scopes.json',dict(sourceIndexSha256=sha(SOURCE/'index.json'),scopes=scopes,
    unusedKnownIncompleteAuditors=['harness04','harness05','harness06'],aggregateTimingPass=False))
print(json.dumps(dict(sourceFiles=len(read(SOURCE/'index.json')['files']),projectFiles=301,
    sourceIndex=sha(SOURCE/'index.json'),host=read(SOURCE/'identity-pins.json')['host'],scopes=scopes)))
