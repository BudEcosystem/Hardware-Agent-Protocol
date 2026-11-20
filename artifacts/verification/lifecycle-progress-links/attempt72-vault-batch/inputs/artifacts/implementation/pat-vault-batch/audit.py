"""Audit retained batch controls without importing project code or writing DBs."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
SOURCE=BASE/'implementation01';HARNESS=BASE/'harness01';ATTEMPT=HARNESS/'attempts/attempt01';SCRATCH=ATTEMPT/'scratch'
def read(path):return json.loads(path.read_bytes())
def sha(path):
    info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_size<=16*1024*1024
    return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(prefix,row):
    path=prefix/row['path'];assert path.lstat().st_size==row['bytes'] and sha(path)==row['sha256']
assert not (BASE/'RESULTS.json').exists()
assert sha(SOURCE/'index.json')=='71595be27f62d50424ec996a2fdd4b4cad1732f7315026d4009c5213cd657171'
assert sha(HARNESS/'index.json')=='00451d06df2d9fd39a5c9868eec6df7d571e72f74de46df6e31c33fa42133107'
for row in read(SOURCE/'index.json')['files']:verify(ROOT,row)
for row in read(HARNESS/'index.json')['files']:verify(HARNESS,row)
result=read(ATTEMPT/'result.json');child=read(ATTEMPT/'child-result.json');selection=read(SOURCE/'test-selection.json')
assert result['status']==child['status']=='passed' and result['exitCode']==0 and result['childState']=='exited' and not result['timedOut']
assert result['inputsUnchanged'] and child['inputsUnchanged'] and child['testsRun']==60
assert all(child[key]==0 for key in ('failures','errors','skips','expectedFailures','unexpectedSuccesses'))
assert child['deniedEvents']==[] and child['failureDetails']==child['errorDetails']==[]
assert child['ids']==selection['ids'] and child['childSha256']==sha(HARNESS/'child.py')
assert result['childResultSha256']==sha(ATTEMPT/'child-result.json') and child['log']==(ATTEMPT/'tests.log').read_text()
external=ROOT/'artifacts/verification/pat-native-worker-accounting/harness01/attempts/attempt01-accounting/external-before.json'
assert sha(external)==child['externalReceiptSha256']
for row in read(external)['files']:assert sha(Path(row['resolvedPath']))==row['sha256']
for row in child['selectedModuleOrigins']:assert sha(Path(row['path']))==row['sha256']
pins=read(SOURCE/'identity-pins.json')
assert child['runtimeLegacyIdentity']==pins['legacy'] and child['runtimeVaultIdentity']==pins['vault']
rows=read(ATTEMPT/'scratch-index.json');assert len(rows)==result['retainedFiles']==194
assert sum(row['bytes'] for row in rows)==result['retainedBytes']==2976200
assert {row['path'] for row in rows}=={str(path.relative_to(SCRATCH)) for path in SCRATCH.rglob('*') if path.is_file()}
locks=[];databases=[];vaults=[];observations=[];corrupt_bodies=[];corrupt_scopes=[];joint={}
try:
    for path in sorted(SCRATCH.rglob('*.owner')):
        assert path.lstat().st_size==0 and not path.is_symlink()
        fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK)
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append((path,fd))
    for row in rows:verify(SCRATCH,row)
    for path in sorted(SCRATCH.rglob('*.db')):
        relative=str(path.relative_to(SCRATCH))
        assert any(owned==Path(str(path)+'.owner') for owned,_ in locks)
        assert all(not os.path.lexists(str(path)+suffix) for suffix in ('-journal','-wal','-shm'))
        before=sha(path);db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True,isolation_level=None)
        try:
            db.execute('PRAGMA query_only=ON')
            assert db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'ev_meta' in tables:
                meta=json.loads(db.execute('SELECT record FROM ev_meta').fetchone()[0])
                assert meta['implementationDigest']==pins['vault']
                bodies=dict(db.execute('SELECT digest,body FROM ev_bodies'))
                refs=db.execute('SELECT sequence,path,digest FROM ev_documents ORDER BY sequence,path').fetchall()
                manifests=db.execute('SELECT sequence,intent,binding,record FROM ev_manifests ORDER BY sequence').fetchall()
                assert all(digest in bodies for _,_,digest in refs) and {digest for _,_,digest in refs}==set(bodies)
                for digest,body in bodies.items():
                    if 'sha256:'+hashlib.sha256(body).hexdigest()!=digest:corrupt_bodies.append(relative)
                for sequence,intent,binding,wire in manifests:
                    record=json.loads(wire)
                    assert record['sequence']==sequence and record['intentDigest']==intent and record['bindingDigest']==binding
                    assert record['authorityId']==meta['authorityId'] and record['storeId']==meta['storeId']
                    if record['scope']!='immutable-bytes-only':corrupt_scopes.append(relative)
                    chosen=[(name,digest) for seq,name,digest in refs if seq==sequence]
                    chain=hashlib.sha256(b'HMS-PAT-IO-IMPORTED-CLOSURE-v0.1\0')
                    for name,digest in chosen:
                        chain.update(json.dumps(dict(path=name,bytes=len(bodies[digest]),sha256=digest),sort_keys=True,separators=(',',':')).encode()+b'\n')
                    assert record['closure']==dict(documents=len(chosen),bytes=sum(len(bodies[d]) for _,d in chosen),digest='sha256:'+chain.hexdigest())
                vaults.append(dict(path=relative,manifests=len(manifests),documents=len(refs),bodies=len(bodies)))
            else:
                assert db.execute("SELECT value FROM meta WHERE key='version'").fetchone()==('hms-ledger/0.1',)
                counts={table:db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                    for table in ('operations','claims','resource_floors','replay_keys','events')}
                observation=path.parent/'observations.json'
                if relative.startswith('new/'):
                    value=read(observation);assert value['counts']==counts and value['checkStateCleared'] and not value['inTransaction']
                    assert value['floor']==db.execute("SELECT value FROM meta WHERE key='last_clock'").fetchone()[0]
                    assert value['authority']==db.execute("SELECT value FROM meta WHERE key='authority'").fetchone()[0]
                if relative.startswith('batch/test_joint_'):
                    joint[path.parent.name]=counts
                    if counts['operations']:
                        operation=db.execute('SELECT id FROM operations').fetchone()[0]
                        assert db.execute('SELECT operation_id FROM replay_keys').fetchone()==(operation,)
                        if 'cleanup_failure' in relative:
                            assert read(observation)['notes']==[dict(originalId=operation,originalReplay=True)]
        finally:db.close()
        assert sha(path)==before
        databases.append(dict(path=relative,sha256=before,mode='ro&immutable=1'))
    for path in sorted(SCRATCH.rglob('observations.json')):
        value=read(path)
        if str(path.relative_to(SCRATCH)).startswith('batch/'):assert value['handlesClosed']
        observations.append(str(path.relative_to(SCRATCH)))
    assert len(locks)==len(databases)==70 and len(observations)==54
    assert sorted(corrupt_bodies)==[
        'batch/test_selected_body_corruption_never_yields_partial_inventory/bulk/evidence.db',
        'single/test_body_corruption_refuses_snapshot_and_reuse_without_repair/bulk/evidence.db']
    assert corrupt_scopes==['batch/test_manifest_corruption_is_retained_and_refused/bulk/evidence.db']
    assert len(joint)==4
    for name,counts in joint.items():
        expected=0 if 'missing_member' in name or 'expiry_at_commit' in name else 1
        assert all(value==expected for value in counts.values())
    maximum=read(SCRATCH/'batch/test_maximum_manifest_set_retained_completely/observations.json')['notes'][0]
    assert maximum['manifests']==maximum['documents']==32 and maximum['uniqueBodies']==1
    assert next(item for item in vaults if item['path'].startswith('batch/test_maximum_manifest_set_'))['manifests']==32
    for row in rows:verify(SCRATCH,row)
    report=dict(status='verified-progress',testsRun=60,batchTests=25,singleSnapshotTests=6,businessCommitTests=29,
        jointBatchAdmissionScenarios=4,sourceIndexSha256=sha(SOURCE/'index.json'),harnessIndexSha256=sha(HARNESS/'index.json'),
        resultSha256=sha(ATTEMPT/'result.json'),childResultSha256=sha(ATTEMPT/'child-result.json'),
        retainedFiles=194,retainedBytes=2976200,ownerLocks=70,readonlyDatabases=databases,
        observationFiles=observations,vaults=vaults,intentionallyCorruptBodies=corrupt_bodies,
        intentionallyCorruptManifestScopes=corrupt_scopes,jointAdmissionRows=joint,maximumBatch=maximum,
        inputsUnchanged=True,deniedEvents=[],publicRuntimeChanged=False,fullWorkerExecuted=False,
        catalogIntegrated=False,physicalObjectiveVerified=False,goalStatus='active',
        limitations=['Immutable bytes and a held view do not qualify a PAT',
            'Logical charge bounds are not heap measurements or backed capacity reservations',
            'No hard real-time guarantee across preparation or SQLite COMMIT',
            'Complete relevant catalog inventory and publication/applicability association remain to be integrated'])
    with (BASE/'RESULTS.json').open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
finally:
    for _,fd in reversed(locks):os.close(fd)
print(json.dumps({key:report[key] for key in ('status','testsRun','batchTests','retainedFiles','ownerLocks','jointBatchAdmissionScenarios','goalStatus')}))
