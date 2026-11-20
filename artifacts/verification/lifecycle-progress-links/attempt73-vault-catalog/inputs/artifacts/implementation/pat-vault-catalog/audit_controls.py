"""Independently inspect completed controls under original owner/writer locks.

No project import and no failed/interrupted database is opened or recovered.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
SOURCE=BASE/'implementation03'
SCOPES=[BASE/('harness%02d'%n) for n in (7,8,9,10,11,17,18,19,20,21)]
ADMITTED={'test_admission_and_commit_do_no_external_reads',
    'test_cold_history_works_with_closed_vault_and_fresh_admission_refuses',
    'test_unauthorized_source_does_not_require_its_preparation',
    'test_lost_reply_after_commit_reconciles_original_instance_without_view'}
MISSING={'test_missing_evidence_is_not_novelty_or_automatic_requalification',
    'test_missing_second_manifest_body_cannot_manufacture_unique_selection'}
def read(path):return json.loads(path.read_bytes())
def sha(path):
    info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_size<=16*1024*1024
    return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(root,row):
    path=root/row['path'];assert path.lstat().st_size==row['bytes'] and sha(path)==row['sha256'],str(path)
def wire(value):
    # These retained control receipts have ASCII strings and integral numbers.
    def check(x):
        if x is None or type(x) in (bool,int):return
        if type(x) is str:assert x.isascii();return
        if type(x) is list:
            for item in x:check(item)
            return
        assert type(x) is dict
        for key,item in x.items():check(key);check(item)
    check(value)
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def hash_value(domain,value):return 'sha256:'+hashlib.sha256(domain+b'\0'+wire(value)).hexdigest()
assert not (BASE/'CONTROL_RESULTS.json').exists()
assert sha(SOURCE/'index.json')=='5ffd155119c12c73d6090a6684973f7f14474ebbfdb0fce228f880476df4e3a9'
for row in read(SOURCE/'index.json')['files']:verify(ROOT,row)
pins=read(SOURCE/'identity-pins.json');selected=read(SOURCE/'test-selection.json')['controls']
observed=[];reports=[];databases=[];missing=[];lock_count=0;files_count=0;bytes_count=0;admissions=[]
for harness in SCOPES:
    for row in read(harness/'index.json')['files']:verify(harness,row)
    attempt=harness/'attempts/attempt01';result=read(attempt/'result.json');targets=read(harness/'targets.json')
    assert result['status']=='passed' and result['exitCode']==0 and result['childState']=='exited'
    assert not result['errors'] and result['inputAndExternalVerificationPassed']
    counts=read(attempt/'test-return.json')
    assert counts==result['counts'] and counts['testsRun']==len(targets)
    assert all(counts[k]==0 for k in counts if k!='testsRun')
    assert read(attempt/'actual-tests.json')==dict(loaded=targets,executed=targets,exactSelection=True)
    assert read(attempt/'child-errors.json')==[]
    assert read(attempt/'host-before.json')==read(attempt/'host-after.json')==dict(host=pins['host'])
    for kind in ('compiler','driver'):assert read(attempt/(kind+'-before.json'))==read(attempt/(kind+'-after.json'))
    origins=read(attempt/'imports.json')
    assert origins['summary']['allOriginsMatched'] and not origins['violations'] and not origins['prohibitedAttempts']
    native=origins['nativeRetention']
    assert native['load']['sha256']==native['image']['sha256']=='ce475ab2a70fb94e84d5d2f2f4c22cb8858d3305005bd154ebda996aae0774ff'
    assert native['image']['requestedSeals']==15 and len(native['scans'])==len(targets)
    assert all(item['calls']>=1 for item in native['scans'])
    # The earlier 14-method file and every production file are unchanged in
    # implementation03; only the separate inventory receipt test was corrected.
    for item in read(attempt/'inputs-before.json'):
        verify(attempt/'project',item)
        if item['path']!='tests/test_vault_catalog_inventory.py':verify(SOURCE/'project',item)
    if harness.name in {'harness17','harness18','harness19','harness20','harness21'}:
        assert sha(attempt/'project/tests/test_vault_catalog_inventory.py')==sha(SOURCE/'project/tests/test_vault_catalog_inventory.py')
    for item in read(harness/'references/external-inputs.json')['files']:
        path=Path(item['resolvedPath']);assert path.stat().st_size==item['bytes'] and sha(path)==item['sha256']
    inventory=read(attempt/'scratch-index.json');raw=Path(inventory['rawPath']);copy=attempt/'scratch'
    assert inventory['retained'] and inventory['originalRetained']
    assert len(inventory['files'])==result['scratchEntries'] and inventory['bytes']==result['scratchBytes']
    assert sum(item['bytes'] for item in inventory['files'])==inventory['bytes']
    assert {item['path'] for item in inventory['files']}=={str(p.relative_to(raw)) for p in raw.rglob('*') if p.is_file()}
    leases=[];authority_imports={}
    try:
        locks=sorted(p for p in raw.rglob('*') if p.name.endswith('.owner') or p.name=='writer.lease')
        for path in locks:
            assert stat.S_ISREG(path.lstat().st_mode)
            fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK)
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);leases.append(fd)
        lock_count+=len(leases)
        for item in inventory['files']:verify(raw,item);verify(copy,item)
        for path in sorted(raw.rglob('*.db')):
            relative=path.relative_to(raw);method=relative.parts[0]
            expected_owner=path.parent/'supervisor.owner' if path.name=='attempts.db' else Path(str(path)+'.owner')
            assert expected_owner in locks
            assert all(not os.path.lexists(str(path)+suffix) for suffix in ('-journal','-wal','-shm'))
            before=sha(path);db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True,isolation_level=None)
            summary=dict(scope=harness.name,path=str(relative),sha256=before)
            try:
                db.execute('PRAGMA query_only=ON')
                assert db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
                tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if path.name=='authority.db':
                    intents={}
                    for digest,body in db.execute('SELECT intent,record FROM evi_intents'):
                        value=json.loads(body);assert wire(value)==body
                        assert hash_value(b'HMS-PAT-VAULT-IMPORT-INTENT-v0.1',value)==digest
                        intents[digest]=value
                    publications={}
                    for digest,body in db.execute('SELECT intent,record FROM evi_publications'):
                        value=json.loads(body);assert wire(value)==body and value['intentDigest']==digest
                        assert digest in intents
                        publications[digest]=value
                    authority_imports[method]=dict(intents=intents,publications=publications)
                    expected=1 if method in ADMITTED else 0
                    counts={name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] if name in tables else 0
                        for name in ('px_instances','px_triggers','pr_procedures','pr_keys','operations','claims','events','replay_keys')}
                    assert counts['px_instances']==counts['px_triggers']==counts['pr_procedures']==expected,(method,counts)
                    assert all(counts[name]==0 for name in ('operations','claims','events','replay_keys')),(method,counts)
                    if not expected:assert counts['pr_keys']==0,(method,counts)
                    else:
                        assert counts['pr_keys']==2
                        instance,procedure,digest=db.execute('SELECT id,procedure_id,artifact_digest FROM px_instances').fetchone()
                        assert db.execute('SELECT instance_id FROM px_triggers').fetchone()==(instance,)
                        assert db.execute('SELECT id FROM pr_procedures').fetchone()==(procedure,)
                        admissions.append(dict(test=method,instanceId=instance,procedureId=procedure,artifactDigest=digest))
                    for digest,body in db.execute('SELECT digest,document FROM pc_evaluations'):
                        receipt=json.loads(body);assert wire(receipt)==body
                        assert hash_value(b'HMS-PAT-IO-VAULT-CATALOG-EVALUATION-v0.1',receipt)==digest
                        assert receipt['invocation']['hostImplementationDigest']==pins['host']
                        assert receipt['invocation']['consumerIdentity']==pins['consumer']
                        assert receipt['physicalObjectiveVerified'] is False
                        inv=receipt['invocation'];intent=intents[inv['importIntentDigest']]
                        publication=publications[inv['importIntentDigest']]
                        assert inv['original']==intent['anchor'] and inv['vaultStoreId']==intent['storeId']
                        assert inv['vaultBindingDigest']==intent['bindingDigest']
                        assert inv['publicationDigest']==hash_value(b'HMS-PAT-VAULT-PUBLICATION-v0.1',publication)
                        assert inv['manifestDigest']==publication['manifestDigest']
                        assert inv['evaluationDigest']==publication['evaluationDigest']
                    summary['admissionRows']=counts
                elif path.name=='evidence.db':
                    meta=json.loads(db.execute('SELECT record FROM ev_meta').fetchone()[0])
                    assert meta['implementationDigest']==pins['vault']
                    bodies=dict(db.execute('SELECT digest,body FROM ev_bodies'))
                    assert all('sha256:'+hashlib.sha256(body).hexdigest()==digest for digest,body in bodies.items())
                    refs=db.execute('SELECT sequence,path,digest FROM ev_documents ORDER BY sequence,path').fetchall()
                    absent=[dict(sequence=seq,path=name,digest=digest) for seq,name,digest in refs if digest not in bodies]
                    assert bool(absent)==(method in MISSING),(method,absent)
                    if absent:missing.append(dict(test=method,references=absent))
                    for seq,intent,binding,body in db.execute('SELECT sequence,intent,binding,record FROM ev_manifests'):
                        manifest=json.loads(body);assert wire(manifest)==body
                        assert manifest['intentDigest']==intent and manifest['bindingDigest']==binding
                        publication=authority_imports[method]['publications'][intent]
                        assert publication['manifestDigest']==hash_value(b'HMS-PAT-EVIDENCE-VAULT-MANIFEST-v0.1',manifest)
                        assert publication['closure']==manifest['closure']
                        group=[(name,digest) for number,name,digest in refs if number==seq]
                        if all(digest in bodies for name,digest in group):
                            chain=hashlib.sha256(b'HMS-PAT-IO-IMPORTED-CLOSURE-v0.1\0')
                            for name,digest in group:chain.update(wire(dict(path=name,bytes=len(bodies[digest]),sha256=digest))+b'\n')
                            assert manifest['closure']==dict(documents=len(group),bytes=sum(len(bodies[d]) for _,d in group),digest='sha256:'+chain.hexdigest())
                    summary.update(manifests=db.execute('SELECT count(*) FROM ev_manifests').fetchone()[0],references=len(refs),bodies=len(bodies))
                elif path.name.startswith('synthetic-io-board-'):
                    effects=[list(row) for row in db.execute('SELECT * FROM io_effects')]
                    assert all(all(value==0 for value in row[1:]) for row in effects)
                    assert db.execute('SELECT count(*) FROM io_receipts').fetchone()[0]==0
            finally:db.close()
            assert sha(path)==before
            databases.append(summary)
        for item in inventory['files']:verify(raw,item);verify(copy,item)
    finally:
        for fd in leases:os.close(fd)
    files_count+=len(inventory['files']);bytes_count+=inventory['bytes'];observed+=targets
    reports.append(dict(harness=harness.name,tests=len(targets),elapsedSeconds=result['elapsedSeconds'],
        resultSha256=sha(attempt/'result.json'),sourceIndexSha256=result['sourceIndexSha256'],
        harnessIndexSha256=sha(harness/'index.json'),files=len(inventory['files']),bytes=inventory['bytes']))
assert observed==selected and len(observed)==19 and len(databases)==76 and len(admissions)==4 and len(missing)==2
# Failed scopes remain byte-retained and failed. Do not open their databases.
failures=[]
for name in ('harness01','harness02','harness03','harness12'):
    attempt=BASE/name/'attempts/attempt01';result=read(attempt/'result.json')
    assert result['status']=='failed' and result['childState']=='exited'
    for item in read(attempt/'scratch-index.json')['files']:verify(attempt/'scratch',item)
    failures.append(dict(harness=name,result=result,databasesOpened=False))
report=dict(status='verified-controls',testsRun=19,scopes=reports,retainedFiles=files_count,retainedBytes=bytes_count,
    originalOwnerAndWriterLocks=lock_count,readonlyDatabases=databases,admissions=admissions,intentionallyMissingBodies=missing,
    sourceIndexSha256=sha(SOURCE/'index.json'),hostIdentity=pins['host'],failedScopesRetained=failures,
    fullWorkerExecuted=False,semanticQualificationSubstituted=True,physicalObjectiveVerified=False,
    publicRuntimeChanged=False,aggregateTimingPass=False,goalStatus='active')
with (BASE/'CONTROL_RESULTS.json').open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
print(json.dumps({k:v for k,v in report.items() if k in ('status','testsRun','retainedFiles','retainedBytes','originalOwnerAndWriterLocks','sourceIndexSha256')}))
