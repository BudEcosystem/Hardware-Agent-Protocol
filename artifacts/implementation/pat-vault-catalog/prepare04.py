"""Freeze receipt correction and actual catalog integration without executing it."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
SOURCE=BASE/'implementation03';OLD=BASE/'implementation02';PROJECT=SOURCE/'project'
ACTUAL=ROOT/'artifacts/implementation/pat-integer-canonical/harness01'
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:stream.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')
def row(path,root):return dict(path=str(path.relative_to(root)),bytes=path.stat().st_size,sha256=sha(path))
def verify(index,root):
    for item in index['files']:assert row(root/item['path'],root)==item
assert not (SOURCE/'index.json').exists()
verify(read(OLD/'index.json'),ROOT);verify(read(ACTUAL/'index.json'),ACTUAL)
baseline=read(SOURCE/'baseline-inputs.json');changed=[]
for item in baseline['files']:
    if row(PROJECT/item['path'],PROJECT)!=item:changed.append(item['path'])
assert changed==['tests/test_vault_catalog_inventory.py']
for name in changed+['tests/test_vault_catalog_process.py']:ast.parse((PROJECT/name).read_bytes())
before=(OLD/'project'/changed[0]).read_text();after=(PROJECT/changed[0]).read_text()
write(SOURCE/'receipt-correction.patch',''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='implementation02/'+changed[0],tofile='implementation03/'+changed[0])))
write(SOURCE/'identity-pins.json',(OLD/'identity-pins.json').read_text())
method='test_actual_original_matrix_catalog_admission_and_cold_history'
target='test_vault_catalog_process.VaultCatalogProcessTests.'+method
write(SOURCE/'test-selection.json',dict(controls=read(OLD/'test-selection.json'),actual=[target]))
write(SOURCE/'source-review.json',dict(reviewer='primary-agent',independentReview=False,
    unchangedInheritedFiles=300,changedInheritedFiles=changed,newFiles=['tests/test_vault_catalog_process.py'],
    productionUnchanged=True,hostIdentityUnchanged=True,publicRuntimeChanged=False,
    controlsPending=True,actualIntegrationPending=True,physicalObjectiveVerified=False,
    review=['Four test receipt lines now use arrays instead of unsupported tuples; assertions preserve the same key inventory.',
        'One full original 30-case worker, real reducer and authority-vault import precede catalog promotion.',
        'One virtual-clock PAT application must complete one GPIO activation and completion.',
        'Original-key history must survive configuration drift and cold vault/bridge reconstruction.',
        'All worker, parent, snapshot, storage and effect bounds remain unchanged.']))
write(SOURCE/'README.md','# Catalog candidate with actual integration selection\n\n'
    'Production is unchanged. Two control receipt emissions use JSON arrays; one new actual integration test '
    'requires the original thirty-case worker, real evidence import, catalog activation, one completed simulated '
    'PAT and original-key history after configuration drift and cold vault/bridge reconstruction. '
    '[Review](source-review.json), [selection](test-selection.json), [receipt correction](receipt-correction.patch). '
    'Execution results are pending; physical devices and the public runtime are outside this candidate.\n')
write(SOURCE/'index.json',dict(files=[row(p,ROOT) for p in sorted(SOURCE.rglob('*')) if p.is_file()]))
assert len(read(SOURCE/'index.json')['files'])==308
scopes=[]
for number,prior_number in zip(range(17,22),range(12,17)):
    prior=BASE/('harness%02d'%prior_number);verify(read(prior/'index.json'),prior)
    harness=BASE/('harness%02d'%number);harness.mkdir()
    for item in read(prior/'index.json')['files']:
        name=item['path']
        if name.endswith('.patch'):continue
        before=(prior/name).read_text();after=before
        if name=='run_attempt.py':
            after=after.replace("SOURCE = BASE / 'implementation02'", "SOURCE = BASE / 'implementation03'")
            after=after.replace('assert len(inputs) == 301','assert len(inputs) == 302').replace('sourceInputs=301','sourceInputs=302')
        if name=='README.md':after=after.replace('../implementation02/','../implementation03/')
        if name=='SCOPE.md':after=after.replace('implementation02','implementation03')
        write(harness/name,after)
        if name.endswith('.py') and not name.startswith('references/'):
            ast.parse(after)
            write(harness/(name+'.patch'),''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=prior.name+'/'+name,tofile=harness.name+'/'+name)))
    write(harness/'index.json',dict(files=[row(p,harness) for p in sorted(harness.rglob('*')) if p.is_file()]))
    scopes.append(dict(harness=harness.name,indexSha256=sha(harness/'index.json'),targets=read(harness/'targets.json')))
harness=BASE/'harness22';harness.mkdir()
borrowed=[]
for name in ('run_attempt.py','attempt_child.py','targets.json','references/approved-external-roots.json'):
    copy='references/original-'+Path(name).name
    write(harness/copy,(ACTUAL/name).read_text())
    borrowed.append(dict(source=str((ACTUAL/name).relative_to(ROOT)),copy=copy,bytes=(ACTUAL/name).stat().st_size,sha256=sha(ACTUAL/name)))
write(harness/'borrowed-inputs.json',borrowed)
write(harness/'references/approved-external-roots.json',(ACTUAL/'references/approved-external-roots.json').read_text())
write(harness/'targets.json',dict(testCount=1,targets=[target]))
old_method='test_actual_original_matrix_import_and_cold_vault_history'
old_prefix='artifacts/implementation/pat-integer-canonical/implementation01'
new_prefix='artifacts/implementation/pat-vault-catalog/implementation03'
for name in ('run_attempt.py','attempt_child.py'):
    before=(ACTUAL/name).read_text()
    after=before.replace(old_method,method).replace('test_vault_original_run.VaultOriginalRunTests.','test_vault_catalog_process.VaultCatalogProcessTests.')
    if name=='run_attempt.py':
        after=after.replace(old_prefix,new_prefix)
        after=after.replace("FROZEN_INDEX = '387d33e2992d2862b1c21902b8de09195a56b569f52c3c3e04b84ce09b2d8849'", "FROZEN_INDEX = '"+sha(SOURCE/'index.json')+"'")
        after=after.replace('295','308').replace('291','302')
        after=after.replace('hms-integer-canonical-actual-','hms-vault-catalog-actual-')
    else:
        after=after.replace("or name == 'recorded_io'", "or name == 'vault_recorded_io' or name.startswith('vault_recorded_io.') or name == 'recorded_io'")
    ast.parse(after);write(harness/name,after)
    write(harness/(name+'.patch'),''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='integer-canonical/'+name,tofile=harness.name+'/'+name)))
write(harness/'SCOPE.md','# Original complete qualification through catalog and PAT\n\n'
    'One thirty-case original worker, real reducer, authority-vault publication, explicit catalog recording '
    'and promotion, one completed simulated GPIO application, drift refusal and cold vault/bridge original-key '
    'history. Exact current production is inherited unchanged from implementation01. No oracle substitution. '
    'Original bounds remain: 60-second worker, 180-second parent, six parent SQLite opens, 16 MiB/file, '
    '256 MiB retained scratch, 8,192 files, 8 MiB log, five-second vault lease and 15 MiB vault. '
    'Exactly one qualification worker and one application invocation. No physical endpoint, MCU, inference or '
    'live service. Interrupted case databases must not be opened or repaired. Raw and copied state remain. '
    'Native-image and owned-process accounting checks are preserved. Cooperative hooks are not OS isolation.\n')
write(harness/'README.md','# Complete original catalog integration attempt\n\n'
    '[Source](../implementation03/README.md), [targets](targets.json), [bounds](SCOPE.md). '
    'The prior passing actual-worker harness changes only source/count pins and exact method identity. '
    'Review and passing component controls are required before its single original attempt. '
    'No retry, changed key, reduced matrix or widened bound is implicit.\n')
write(harness/'review.json',dict(reviewer='primary-agent',independentReview=False,
    preservedNativeGuard=True,preservedProcessAccounting=True,preservedOriginalBounds=True,
    componentControlsRequiredBeforeActualExecution=True,sourceIndexSha256=sha(SOURCE/'index.json')))
write(harness/'index.json',dict(files=[row(p,harness) for p in sorted(harness.rglob('*')) if p.is_file()]))
write(BASE/'final-scopes.json',dict(sourceIndexSha256=sha(SOURCE/'index.json'),controls=scopes,
    actual=dict(harness=harness.name,indexSha256=sha(harness/'index.json'),target=target),
    unchangedEarlierControls=['harness07','harness08','harness09','harness10','harness11'],
    unusedOlderControlHarnesses=['harness13','harness14','harness15','harness16']))
print(json.dumps(dict(projectFiles=302,sourceFiles=308,sourceIndex=sha(SOURCE/'index.json'),
    controls=[x['harness'] for x in scopes],actualHarnessIndex=sha(harness/'index.json'))))
