"""Adapt the original byte/SQL audit to split storage; never runs the audit."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
OLD=ROOT/'artifacts/implementation/pat-statement-cache/audit_actual.py'
SOURCE=ROOT/'artifacts/implementation/supervisor-storage-bindings/implementation01'
before=OLD.read_text();after=before
after=after.replace("STAGE=BASE/'implementation01'","STAGE=ROOT/'artifacts/implementation/supervisor-storage-bindings/implementation01'")
after=after.replace('7ecd42fec5cef9374573ae8b3d0747060bdc8c4cd8ca552e9c3de4d64a2ec23e','ffcace54bb02211d47e2f69febfb2f7f1566d6ee6dcb8264a3f10ecef5a8534f')
after=after.replace('74204ea2477aa497bfce9a6c667455b4ec5fb622f49c07663a7c87b3c583d933','b53a90f96fbe5e15b4531c3b3474eb212d98a3d0fcb14f06111e82f1434e5873')
after=after.replace("result['projectInputCount']==304 and result['frozenPreparationInputCount']==313", "result['projectInputCount']==309 and result['frozenPreparationInputCount']==312")
after=after.replace("len(native['scans'])==2","len(native['scans'])==3")
after=after.replace('len(locks)==57','len(locks)==58')
after=after.replace("work/'supervisor/attempts.db'","work/'supervisor-control/attempts.db'")
after=after.replace("work/'supervisor'","work/'supervisor-bulk'")
after=after.replace("'supervisor/'+record['attemptId']","'supervisor-bulk/'+record['attemptId']")
after=after.replace('len(paths)==267','len(paths)==268').replace('producerImageFiles=267','producerImageFiles=268')
old="    assert scan_rows[str(work/'supervisor-bulk')]==dict(path=str(work/'supervisor-bulk'),calls=1,maxFiles=262144,maxBytes=268435456)"
new="""    assert scan_rows[str(work/'supervisor-control')]==dict(path=str(work/'supervisor-control'),calls=1,maxFiles=262144,maxBytes=268435456)
    bulk_scan=scan_rows[str(work/'supervisor-bulk')]
    assert bulk_scan['calls']==1 and bulk_scan['maxFiles']==262142
    assert 0<268435456-bulk_scan['maxBytes']<=(work/'supervisor-control/attempts.db').stat().st_size
    assert set(scan_rows)=={str(work/'supervisor-control'),str(work/'supervisor-bulk'),str(worker)}"""
assert after.count(old)==1;after=after.replace(old,new)
old='    authority,vault,supervisor,board_db=dbs'
new=old+'''
    stored_binding=supervisor.execute('SELECT version,binding FROM qs_meta LIMIT 2').fetchall()
    assert len(stored_binding)==1 and stored_binding[0][0]==3
    storage_binding=json.loads(stored_binding[0][1])
    assert canonical(storage_binding)==stored_binding[0][1] and storage_binding==read(work/'storage-binding.json')
    for name in ('control','bulk'):
        path=work/('supervisor-'+name);info=path.lstat()
        assert storage_binding[name]==dict(path=str(path),uid=os.getuid(),device=str(info.st_dev),inode=str(info.st_ino))
        assert stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode)==0o700
    for name,key in (('bulk.owner','bulkOwner'),('storage.json','bulkManifest')):
        path=work/'supervisor-bulk'/name;info=path.lstat()
        assert storage_binding[key]==dict(device=str(info.st_dev),inode=str(info.st_ino))
        assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o600
    marker=(work/'supervisor-bulk/storage.json').read_bytes()
    assert marker==canonical({k:storage_binding[k] for k in ('profile','bindingId','control','bulk')})
    assert hashlib.sha256(marker).hexdigest()==storage_binding['manifestSha256']
    assert storage_binding['profile']=='hms.supervisor.storage-split/0.1'
    assert len([r for r in locks if r['path']=='supervisor-bulk/bulk.owner'])==1
'''
assert after.count(old)==1;after=after.replace(old,new)
pins=json.loads((SOURCE/'identity-pins.json').read_bytes())
after=after.replace('sha256:f4479f6d5b40c38e1c0645515633be63faaed2c8b1e913a1c16c522152fc6738',pins['consumer'])
after=after.replace('catalogControls=19,previousNativeControlsReferenced=True,productionCandidateChanged=True',
    'controlChecks=71,previousNativeControlsReferenced=True,productionCandidateChanged=False,storageBinding=storage_binding,diagnosticBatchingChanged=True,originalBatchedControlProfilePassed=False')
after=after.replace("assert read(BASE/'CONTROL_RESULTS.json')['testsRun']==19","assert read(BASE/'CONTROL_AUDIT.json')['tests']==71")
after=after.replace("BASE/'RESULTS.json'","BASE/'ACTUAL_RESULTS.json'").replace("'catalogControls'","'controlChecks'")
ast.parse(after)
with (BASE/'audit_actual.py').open('x') as stream:stream.write(after)
with (BASE/'actual-audit-adaptation.patch').open('x') as stream:stream.write(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='original/audit_actual.py',tofile='split/audit_actual.py')))
review=dict(originalPath=str(OLD.relative_to(ROOT)),originalSha256=hashlib.sha256(OLD.read_bytes()).hexdigest(),
    auditSha256=hashlib.sha256(after.encode()).hexdigest(),originalAssertions=len([n for n in ast.walk(ast.parse(before)) if isinstance(n,ast.Assert)]),
    currentAssertions=len([n for n in ast.walk(ast.parse(after)) if isinstance(n,ast.Assert)]),
    scope='Owned four-parent-database immutable audit, full byte/identity/import/catalog/effect joins; no worker case DB open',
    newBindingChecks=True,reviewer='primary-agent',independentReview=False)
with (BASE/'actual-audit-review.json').open('x') as stream:json.dump(review,stream,indent=2);stream.write('\n')
print(json.dumps(review))
