"""Freeze reviewed source, repin identities, retain exact inherited oracle."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
SOURCE=BASE/'implementation01';PROJECT=SOURCE/'project'
OLD=BASE.parent/'pat-statement-cache'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as stream:stream.write(value if type(value) is bytes else (value if type(value) is str else json.dumps(value,indent=2)+'\n').encode())
def rows(root,prefix):
    return [dict(path=p.relative_to(prefix).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(root.rglob('*')) if p.is_file()]
assert not (SOURCE/'index.json').exists()
pins=read(BASE/'inspection02.json');assert pins['importEffects'] is False and pins['producerImageFiles']==268
old_pins=read(OLD/'implementation01/identity-pins.json')
replacements={old_pins[k]:pins[k] for k in ('consumer','host','vault','legacy') if old_pins[k]!=pins[k]}
updated=[]
for p in sorted((PROJECT/'tests').glob('*.py')):
    before=p.read_text();after=before
    for old,new in replacements.items():after=after.replace(old,new)
    if after!=before:
        reverted=after
        for old,new in replacements.items():reverted=reverted.replace(new,old)
        assert reverted==before
        p.write_text(after);updated.append(p.relative_to(PROJECT).as_posix())
assert set(updated)=={'tests/test_vault_catalog_process.py','tests/test_vault_recorded_catalog.py'}
original=read(BASE/'original-inputs.json')['files'];changed=[];patch=[]
for row in original:
    old=ROOT/row['source'];new=PROJECT/row['path']
    assert sha(old)==row['sha256']
    if old.read_bytes()!=new.read_bytes():
        changed.append(row['path'])
        patch.extend(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),fromfile='original/'+row['path'],tofile='candidate/'+row['path']))
production={'hms_qualification/supervisor/attempt_ledger.py','hms_qualification/supervisor/qualification_supervisor.py',
    'hms_qualification/supervisor/io_service_execution.py','hms_qualification/supervisor/supervisor_contracts.py','hms_qualification/evidence/archive.py'}
assert set(changed)==production|set(updated)
original_names={r['path'] for r in original}
new_files={p.relative_to(PROJECT).as_posix() for p in PROJECT.rglob('*') if p.is_file()}-original_names
assert new_files=={'hms_qualification/supervisor/storage_binding.py','tests/test_storage_bindings.py','tests/test_storage_actual.py'}
for name in sorted(new_files):
    patch.extend(difflib.unified_diff([], (PROJECT/name).read_text().splitlines(True),fromfile='/dev/null',tofile='candidate/'+name))
for p in PROJECT.rglob('*.py'):ast.parse(p.read_bytes())
# Path plumbing is the sole difference to these original control/evidence methods.
for name in ('hms_qualification/supervisor/qualification_supervisor.py','hms_qualification/evidence/archive.py'):
    row=next(r for r in original if r['path']==name)
    before=(ROOT/row['source']).read_text()
    assert (PROJECT/name).read_text()==before.replace('ledger.root','ledger.bulk_root').replace('ledger.fd','ledger.bulk_fd')
write(SOURCE/'final.patch',''.join(patch))
write(SOURCE/'identity-pins.json',pins)
write(SOURCE/'source-review.json',dict(reviewer='primary-agent',independentReview=False,originalFiles=len(original),
    changedExistingProductionFiles=sorted(production),addedProductionFiles=['hms_qualification/supervisor/storage_binding.py'],
    updatedIdentityExpectations=updated,additionalFixtures=sorted(new_files-{'hms_qualification/supervisor/storage_binding.py'}),
    pathPlumbingExact=True,fullActualOracleChangedOnlyInIdentityLiterals=True,publicRuntimeChanged=False,
    originalWorkerMs=60000,parentSeconds=180,quotaClaim=False,backedCapacityClaim=False,hotJournalRecoveryQualified=False))
frozen=rows(SOURCE,ROOT);write(SOURCE/'index.json',dict(files=frozen));pin=sha(SOURCE/'index.json')
def methods(module,cls):
    value=ast.parse((PROJECT/'tests'/f'{module}.py').read_bytes())
    node=next(n for n in value.body if isinstance(n,ast.ClassDef) and n.name==cls)
    return [f'{module}.{cls}.{n.name}' for n in node.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
scopes=[]
for label,module,cls,group in [('legacy-authority','test_supervisor_authority','SupervisorAuthorityTests',14),
    ('legacy-recovery','test_io_supervisor_recovery','IoControlRecoveryTests',10),
    ('legacy-handoff','test_io_service_execution','IoServiceExecutionTests',4),
    ('split-binding','test_storage_bindings','StorageBindingTests',5)]:
    targets=methods(module,cls)
    for start in range(0,len(targets),group):scopes.append(dict(name=f'{label}-{start//group+1:02d}',targets=targets[start:start+group]))
write(BASE/'control-selection.json',dict(sourceIndexSha256=pin,projectFiles=len(rows(PROJECT,PROJECT)),scopes=scopes,
    tests=sum(len(r['targets']) for r in scopes)))
write(BASE/'external-inputs.json',(OLD/'harness17/references/external-inputs.json').read_bytes())
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=len(rows(PROJECT,PROJECT)),frozenFiles=len(frozen),scopes=len(scopes),tests=sum(len(r['targets']) for r in scopes))))
