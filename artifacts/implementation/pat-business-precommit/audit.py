"""Read-only verification of source, final receipts and retained host databases."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
SOURCE=BASE/'implementation03';HARNESS=BASE/'harness03';ATTEMPT=HARNESS/'attempts/attempt01'
def read(path):return json.loads(path.read_bytes())
def sha(path):
    info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_size<=16*1024*1024
    return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(prefix,row):
    path=prefix/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
assert not (BASE/'RESULTS.json').exists()
assert sha(SOURCE/'index.json')=='2f1d6c5aeaf63e960058f9b838b5ecd1080fc17d78f207f0d0b14c248da2dad4'
assert sha(HARNESS/'index.json')=='dfd638911f42cd5f25d02ac21b2a0b59699c946c328eaeb0af040fc85c2a0689'
for row in read(SOURCE/'index.json')['files']:verify(ROOT,row)
for row in read(HARNESS/'index.json')['files']:verify(HARNESS,row)
result=read(ATTEMPT/'result.json');child=read(ATTEMPT/'child-result.json')
assert result['status']=='passed' and result['exitCode']==0 and result['childState']=='exited' and not result['timedOut']
assert result['inputsUnchanged'] and child['inputsUnchanged'] and child['status']=='passed'
assert child['testsRun']==51 and all(child[key]==0 for key in ('failures','errors','skips','expectedFailures','unexpectedSuccesses'))
assert child['deniedEvents']==[] and child['failureDetails']==child['errorDetails']==[]
assert result['childResultSha256']==sha(ATTEMPT/'child-result.json')
assert child['childSha256']==sha(HARNESS/'child.py') and child['log']==(ATTEMPT/'tests.log').read_text()
selection=read(SOURCE/'test-selection.json')
assert child['ids']==['test_business_precommit.'+name for name in selection['newTests']]+['test_journal.'+name for name in selection['legacyTests']]
external_path=ROOT/'artifacts/verification/pat-native-worker-accounting/harness01/attempts/attempt01-accounting/external-before.json'
assert sha(external_path)==child['externalReceiptSha256']
for row in read(external_path)['files']:
    assert sha(Path(row['resolvedPath']))==row['sha256']
for row in child['selectedModuleOrigins']:assert sha(Path(row['path']))==row['sha256']
pins=read(SOURCE/'identity-pins.json')
assert child['runtimeLegacyIdentity']==pins['legacy'] and child['runtimeVaultIdentity']==pins['vault']
rows=read(ATTEMPT/'scratch-index.json');assert len(rows)==result['retainedFiles']==142
scratch=ATTEMPT/'scratch'
assert sum(row['bytes'] for row in rows)==result['retainedBytes']==3948725
assert {row['path'] for row in rows}=={str(p.relative_to(scratch)) for p in scratch.rglob('*') if p.is_file()}
locks=[];databases=[];observations=[];vaults=[]
try:
    for path in sorted(scratch.rglob('*.owner')):
        assert path.lstat().st_size==0 and not path.is_symlink()
        fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK)
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append((path,fd))
    for row in rows:verify(scratch,row)
    for path in sorted(scratch.rglob('*.db')):
        assert any(owned==Path(str(path)+'.owner') for owned,_ in locks)
        assert all(not os.path.lexists(str(path)+suffix) for suffix in ('-journal','-wal','-shm'))
        before=sha(path);db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True,isolation_level=None)
        try:
            db.execute('PRAGMA query_only=ON')
            assert db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
            if path.name=='evidence.db':
                meta=json.loads(db.execute('SELECT record FROM ev_meta').fetchone()[0])
                manifest=json.loads(db.execute('SELECT record FROM ev_manifests').fetchone()[0])
                refs=db.execute('SELECT sequence,path,digest FROM ev_documents').fetchall()
                bodies=db.execute('SELECT digest,body FROM ev_bodies').fetchall()
                body=b'identity only; not qualification';digest='sha256:'+hashlib.sha256(body).hexdigest()
                assert bodies==[(digest,body)] and refs==[(1,'fixture/bytes',digest)]
                assert meta['implementationDigest']==pins['vault'] and manifest['scope']=='immutable-bytes-only'
                assert manifest['authorityId']==meta['authorityId'] and manifest['storeId']==meta['storeId']
                assert manifest['sequence']==1 and manifest['previousManifestDigest'] is None
                assert manifest['intentDigest']=='sha256:'+hashlib.sha256(b'byte retention fixture').hexdigest()
                assert manifest['bindingDigest']=='sha256:'+hashlib.sha256(b'original fixture association').hexdigest()
                encoded=json.dumps(dict(path='fixture/bytes',bytes=len(body),sha256=digest),sort_keys=True,separators=(',',':')).encode()
                closure_digest='sha256:'+hashlib.sha256(b'HMS-PAT-IO-IMPORTED-CLOSURE-v0.1\0'+encoded+b'\n').hexdigest()
                assert manifest['closure']==dict(documents=1,bytes=len(body),digest=closure_digest)
                vaults.append(dict(path=str(path.relative_to(scratch)),authority=meta['authorityId'],manifestScope=manifest['scope']))
            else:
                assert db.execute("SELECT value FROM meta WHERE key='version'").fetchone()==('hms-ledger/0.1',)
                counts={table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in
                    ('operations','replay_keys','resource_floors','claims','events')}
                observation=path.parent/'observations.json'
                if observation.exists():
                    value=read(observation)
                    assert value['counts']==counts and value['checkStateCleared'] and not value['inTransaction']
                    assert value['floor']==db.execute("SELECT value FROM meta WHERE key='last_clock'").fetchone()[0]
                    assert value['authority']==db.execute("SELECT value FROM meta WHERE key='authority'").fetchone()[0]
                    observations.append(dict(path=str(observation.relative_to(scratch)),counts=counts))
        finally:db.close()
        assert sha(path)==before
        databases.append(dict(path=str(path.relative_to(scratch)),sha256=before,mode='ro&immutable=1'))
    for row in rows:verify(scratch,row)
    assert len(locks)==57 and len(databases)==56 and len(observations)==29 and len(vaults)==5
    for item in vaults:
        parent=(scratch/item['path']).parent.parent
        assert read(parent/'observations.json')['authority']==item['authority']
    for name in ('test_valid_early_but_invalid_at_commit_rolls_back_every_business_row',
                 'test_vault_expiry_between_initial_validation_and_commit_rolls_back',
                 'test_replaced_vault_lease_cannot_authorize_commit','test_released_vault_lease_cannot_authorize_commit',
                 'test_nested_catalog_verifier_cannot_replace_commit_authorizer'):
        assert all(value==0 for value in read(scratch/'new'/name/'observations.json')['counts'].values())
    late=read(scratch/'new/test_lost_reply_after_commit_replays_original_without_rechecking/observations.json')
    assert late['calls']==['checked'] and all(value==1 for value in late['counts'].values())
    report=dict(status='verified-progress',testsRun=51,newTests=29,inheritedJournalTests=22,
        sourceIndexSha256=sha(SOURCE/'index.json'),harnessIndexSha256=sha(HARNESS/'index.json'),
        resultSha256=sha(ATTEMPT/'result.json'),childResultSha256=sha(ATTEMPT/'child-result.json'),
        retainedFiles=142,retainedBytes=3948725,ownerLocks=57,readonlyDatabases=databases,
        observations=observations,vaultFixtures=vaults,inputsUnchanged=True,deniedEvents=[],
        publicRuntimeChanged=False,fullWorkerExecuted=False,catalogIntegrated=False,
        physicalObjectiveVerified=False,goalStatus='active',
        limitations=['Installed trusted callbacks, not an arbitrary Python sandbox',
            'No hard deadline guarantee across a blocking COMMIT',
            'Two historical subprocess crash/recovery test methods not rerun',
            'Vault fixture manifests prove byte identity only; no new qualification or catalog mount'])
    with (BASE/'RESULTS.json').open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
finally:
    for _,fd in reversed(locks):os.close(fd)
print(json.dumps({key:report[key] for key in ('status','testsRun','newTests','inheritedJournalTests','retainedFiles','ownerLocks','goalStatus')}))
