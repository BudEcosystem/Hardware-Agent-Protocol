"""Audit the complete original import without opening worker case databases."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import re

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
STAGE=BASE/'implementation03';HARNESS=BASE/'harness23';ATTEMPT=HARNESS/'attempts/attempt01-actual'
PIN='5ffd155119c12c73d6090a6684973f7f14474ebbfdb0fce228f880476df4e3a9'
HPIN='eb5a17ffdffaaa5ef208fd623f0db8e7c19b7634cf26e370b9fe00880d827437'
METHOD='test_actual_original_matrix_catalog_admission_and_cold_history'
def read(path):return json.loads(path.read_bytes())
def sha(path):
    assert not path.is_symlink() and path.is_file() and path.stat().st_size<=16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(path,row):assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],str(path)
def inventory(folder):
    rows=[]
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():rows.append(dict(path=path.relative_to(folder).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    return sorted(rows,key=lambda row:row['path'])
def canonical(value):
    def check(item):
        if type(item)is dict:
            assert all(type(k)is str and k.isascii() for k in item)
            for v in item.values():check(v)
        elif type(item)is list:
            for v in item:check(v)
        else:
            assert type(item)in(str,int,bool,type(None))
            assert type(item)is not int or abs(item)<=2**53-1
    check(value);return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(domain,value):return 'sha256:'+hashlib.sha256(domain+b'\0'+canonical(value)).hexdigest()
assert sha(STAGE/'index.json')==PIN and sha(HARNESS/'index.json')==HPIN
for folder,prefix in ((STAGE,ROOT),(HARNESS,HARNESS)):
    for row in read(folder/'index.json')['files']:verify(prefix/row['path'],row)
result=read(ATTEMPT/'result.json')
assert result['status']=='passed' and result['currentPass'] is True and result['childState']=='exited' and result['exitCode']==0
assert result['counts']==dict(testsRun=1,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert result['errors']==result['childErrors']==[] and result['rawScratchInventoryTerminal']
assert result['timeoutSeconds']==180 and result['limits']['scratchRetentionBytes']==268435456
assert result['projectInputCount']==302 and result['frozenPreparationInputCount']==308
for label,prefix in (('inputs',ATTEMPT/'project'),('frozen',ROOT),('harness',ATTEMPT/'harness')):
    rows=read(ATTEMPT/(label+'-before.json'));assert rows==read(ATTEMPT/(label+'-after.json'))
    for row in rows:verify(prefix/row['path'],row)
external=read(ATTEMPT/'external-before.json');assert external==read(ATTEMPT/'external-after.json')
for row in external['files']:verify(Path(row['resolvedPath']),row)
assert len(external['files'])==159
origins=read(ATTEMPT/'imports.json');assert origins['violations']==origins['prohibitedAttempts']==[]
native=origins['nativeRetention']
assert native['load']['sha256']=='ce475ab2a70fb94e84d5d2f2f4c22cb8858d3305005bd154ebda996aae0774ff'
assert native['image']['sha256']==native['load']['sha256'] and native['image']['requestedSeals']==15
assert native['image']['origin']=='/proc/self/fd/'+str(native['image']['descriptor'])
native_records=[]
for row in origins['records']:
    if row.get('kind')=='sealed_native_image':
        native_records.append(row)
        assert row['source']=='module:_hms_retention_native_v1' and row['origin']==native['image']['origin']
        assert row['sha256']==native['load']['sha256']==sha(Path(row['artifactOrigin']))
        assert row['device']==native['image']['device'] and row['inode']==native['image']['inode'] and row['matchesBefore']
    elif 'sha256' in row:assert sha(Path(row['origin']))==row['sha256']
assert len(native_records)==1
# The held descriptor was checked in the child; never reopen its numeric path after exit.
assert len(native['scans'])==2 and all(type(v['calls']) is int and v['calls']>0 for v in native['scans'])
for label in ('compiler','driver'):assert read(ATTEMPT/(label+'-before.json'))==read(ATTEMPT/(label+'-after.json'))
assert len(read(ATTEMPT/'sqlite-connections.json'))==5
targets=read(HARNESS/'targets.json')['targets']
assert read(ATTEMPT/'actual-tests.json')==dict(loaded=targets,executed=targets,exactSelection=True)
raw=Path(result['scratchPath']);work=raw/METHOD
for path,identity in ((raw,read(ATTEMPT/'raw-scratch-before.json')['identity']),
                      (raw.parent,read(ATTEMPT/'raw-scratch-after.json')['parentBefore'])):
    info=path.lstat();assert stat.S_ISDIR(info.st_mode)
    assert (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==tuple(identity[k] for k in ('device','inode','uid','gid','mode'))
held=[];locks=[];dbs=[];hashes={}
try:
    for path in sorted(work.rglob('*')):
        assert not path.is_symlink()
        if path.is_file() and (path.name.endswith('.owner') or path.name=='writer.lease'):
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK);held.append(fd);info=os.fstat(fd)
            assert stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1 and info.st_size==0
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            locks.append(dict(path=path.relative_to(work).as_posix(),device=str(info.st_dev),inode=str(info.st_ino)))
    assert len(locks)==57
    rows=inventory(raw);assert rows==inventory(ATTEMPT/'scratch')==read(ATTEMPT/'scratch-index.json')
    assert len(rows)<=8192 and sum(row['bytes'] for row in rows)==result['scratchRetainedBytes']<=268435456
    board=next((work/'runtime').glob('synthetic-io-board-*.db'))
    for path in (work/'runtime/authority.db',work/'vault/evidence.db',work/'supervisor/attempts.db',board):
        assert not any(os.path.lexists(str(path)+suffix) for suffix in ('-journal','-wal','-shm'))
        hashes[path.relative_to(work).as_posix()]=sha(path)
        db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True,isolation_level=None)
        dbs.append(db);db.execute('PRAGMA query_only=ON')
    authority,vault,supervisor,board_db=dbs
    saved=supervisor.execute('SELECT request,record,return_bytes FROM qs_attempts LIMIT 2').fetchall()
    assert len(saved)==1 and type(saved[0][2]) is bytes
    request,record=map(json.loads,saved[0][:2]);archive=read(work/'worker-archive.json')
    assert archive['record']==record and record['state']=='archived' and record['reason'] is None
    report=record['archive'];assert report['supervisorReason'] is None and report['exitCode']==0 and report['returnValidationFailure'] is None
    assert report['transportComplete'] is True and report['unresolvedEffects'] is None and report['semanticQualificationVerified'] is False
    assert type(report['evidenceIntegrity']) is dict and type(report['returnDigest']) is str
    assert request['groupLimits']['maxWallMs']==60000 and len(request['bundleHeader']['caseIds'])==30
    assert record['requestDigest']==digest(b'HMS-PAT-IO-SUPERVISOR-REQUEST-v0.1',request)
    writer=next(row for row in locks if row['path']=='supervisor/'+record['attemptId']+'/writer.lease')
    assert record['lease']=={key:writer[key] for key in ('device','inode')}
    assert authority.execute('SELECT count(*) FROM iose_handoffs').fetchone()[0]==authority.execute('SELECT count(*) FROM iosr_runs').fetchone()[0]==1
    handoff=json.loads(authority.execute('SELECT receipt FROM iose_handoffs').fetchone()[0])
    reservation=json.loads(authority.execute('SELECT receipt FROM iosr_runs').fetchone()[0])
    assert handoff==archive['association']['receipt'] and handoff['attemptId']==record['attemptId'] and handoff['requestDigest']==record['requestDigest']
    assert handoff['reservationDigest']==digest(b'HMS-PAT-IO-SERVICE-RUN-RESERVATION-v0.1',reservation)
    assert handoff['supervisorAuthorityId']==supervisor.execute('SELECT authority FROM qs_meta').fetchone()[0]
    assert [row[0] for row in authority.execute('SELECT revision FROM iosc_versions ORDER BY revision')]==[1,2]
    counts={name:authority.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('evi_intents','evi_publications','operations','claims')}
    assert counts==dict(evi_intents=1,evi_publications=1,operations=1,claims=0)
    assert [vault.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('ev_manifests','ev_documents','ev_bodies')]==[1,4011,2798]
    meta=json.loads(authority.execute('SELECT record FROM evi_meta').fetchone()[0])
    assert json.loads(vault.execute('SELECT record FROM ev_meta').fetchone()[0])==meta['vault']
    assert meta['authorityId']==meta['vault']['authorityId']==authority.execute("SELECT value FROM meta WHERE key='authority'").fetchone()[0]
    assert authority.execute("SELECT value FROM reg_meta WHERE key='vault_evidence_import'").fetchone()[0]=='hms.pat.vault-import/0.1|'+digest(b'HMS-PAT-VAULT-IMPORT-MOUNT-v0.1',meta)
    effects=read(work/'application-effects.json')
    actual_effects=[list(row) for row in board_db.execute('SELECT instance,activations,completed,canceled FROM io_effects')]
    assert actual_effects==effects['effects']
    assert all(row[1:]==([1,1,0] if row[0]==effects['selectedInstance'] else [0,0,0]) for row in actual_effects)
    assert board_db.execute('SELECT count(*) FROM io_owners').fetchone()[0]==0
    worker=work/'supervisor'/record['attemptId'];output=worker/'output';matrix=read(output/'matrix.json')
    scan_rows={value['path']:value for value in native['scans']}
    assert scan_rows[str(work/'supervisor')]==dict(path=str(work/'supervisor'),calls=1,maxFiles=262144,maxBytes=268435456)
    assert scan_rows[str(worker)]==dict(path=str(worker),calls=scan_rows[str(worker)]['calls'],maxFiles=8192,maxBytes=67108864)
    assert [case['caseId'] for case in matrix['cases']]==request['bundleHeader']['caseIds']
    cases=sorted(output.glob('case-*'));manifests=sorted(output.glob('case-*/manifest.json'))
    assert len(cases)==30 and len(manifests)==30
    for i,path in enumerate(manifests):assert read(path)['caseId']==matrix['cases'][i]['caseId']
    assert matrix['cases'][29]['definition']['scenario']=='shared_resources'
    assert (output/'result.json').is_file() and (worker/'worker-return.json').is_file()
    phases=read(work/'phase-times.json');assert {'import_complete','catalog_recorded','catalog_activated','application_completed','cold_history_complete','test_body_complete'}<={row['phase'] for row in phases}
    phase_map={row['phase']:row['elapsedMs'] for row in phases}
    image=work/'supervisor'/('code-'+request['supervisorIdentity'][7:]);paths=sorted(p for p in image.rglob('*') if p.is_file())
    assert len(paths)==265;source_rows=[]
    for path in paths:
        relative=path.relative_to(image).as_posix();value=sha(path)
        if relative.startswith('dependencies/'):
            selected=[row for row in external['files'] if row['resolvedPath'].endswith('/'+relative[len('dependencies/'):])]
            assert len(selected)==1 and selected[0]['sha256']==value
        else:assert sha(ATTEMPT/'project'/relative)==value
        source_rows.append(dict(path=relative,bytes=path.stat().st_size,sha256=value))
    def package(name,names):
        return [dict(path=name+'/'+filename,bytes=(ATTEMPT/'project'/name/filename).stat().st_size,
            sha256=sha(ATTEMPT/'project'/name/filename)) for filename in names]
    source_rows+=package('evidence',('__init__.py','contracts.py','archive.py','reducer.py','store.py'))
    legacy=digest(b'HMS-PAT-IO-EVIDENCE-CONSUMER-v0.1',sorted(source_rows,key=lambda r:r['path']))
    vault_id=digest(b'HMS-PAT-EVIDENCE-VAULT-IMPLEMENTATION-v0.1',dict(legacyIdentity=legacy,sources=package('evidence_vault',('__init__.py','contracts.py','connection.py','store.py'))))
    consumer=digest(b'HMS-PAT-VAULT-IMPORT-IMPLEMENTATION-v0.1',dict(vaultIdentity=vault_id,sources=package('evidence_authority',('__init__.py','contracts.py','store.py'))))
    pins=read(STAGE/'identity-pins.json')
    assert sorted(source_rows,key=lambda r:r['path'])==pins['sourceRows'] and legacy==pins['legacy'] and vault_id==pins['vault']==meta['vault']['implementationDigest']
    assert consumer==pins['consumer']==meta['consumerIdentity']=='sha256:5e9214b37a96f897253ea2f1859090327039f5aaeb9512aa49df880484cf4523'

    # Independently verify publication and every retained vault body/reference.
    def body_sha(body):return 'sha256:'+hashlib.sha256(body).hexdigest()
    imported=read(work/'original-import.json');checks=read(work/'actual-vault-catalog-checks.json')
    intent=imported['intent'];publication=imported['receipt'];evaluation=imported['evaluation']
    intent_digest=digest(b'HMS-PAT-VAULT-IMPORT-INTENT-v0.1',intent)
    publication_digest=digest(b'HMS-PAT-VAULT-PUBLICATION-v0.1',publication)
    assert intent_digest==imported['intentDigest']
    assert publication_digest==imported['receiptDigest']==checks['importReceiptDigest']
    assert intent['sequence']==publication['sequence']==1 and intent['previousIntentDigest'] is None and publication['previousPublicationDigest'] is None
    assert intent['consumerIdentity']==evaluation['consumerIdentity']==consumer
    assert intent['storeId']==meta['vault']['storeId'] and publication['intentDigest']==intent_digest
    assert intent['bindingDigest']==digest(b'HMS-PAT-VAULT-ORIGINAL-BINDING-v0.1',intent['anchor'])
    intent_rows=authority.execute('SELECT sequence,evaluator,run,intent,record FROM evi_intents LIMIT 2').fetchall()
    publication_rows=authority.execute('SELECT sequence,intent,record FROM evi_publications LIMIT 2').fetchall()
    assert intent_rows==[(1,reservation['evaluatorId'],reservation['runId'],intent_digest,canonical(intent))]
    assert publication_rows==[(1,intent_digest,canonical(publication))]
    returned=json.loads(saved[0][2])
    assert saved[0][2]==(worker/'worker-return.json').read_bytes()==canonical(returned)
    assert body_sha(saved[0][2])==report['returnDigest']
    assert returned==dict(profile='hms.pat.io-supervisor-return/0.1',attemptId=record['attemptId'],
        bundleDigest=request['bundleDigest'],requestDigest=record['requestDigest'],
        groupResultDigest=body_sha((output/'result.json').read_bytes()),status='captured')
    expected_anchor=dict(authorityId=reservation['authorityId'],deployment=reservation['deployment'],
        evaluatorId=reservation['evaluatorId'],runId=reservation['runId'],artifactDigest=reservation['artifactDigest'],
        reservationDigest=handoff['reservationDigest'],configurationReceiptDigest=reservation['configurationReceiptDigest'],
        configurationDigest=request['context']['configurationDigest'],configurationRevision=request['context']['configurationRevision'],
        supervisorAuthorityId=handoff['supervisorAuthorityId'],handoffDigest=archive['association']['receiptDigest'],
        requestDigest=record['requestDigest'],attemptId=record['attemptId'],bundleDigest=request['bundleDigest'],
        producerIdentity=request['supervisorIdentity'],producerImplementation=request['implementation'],
        recordDigest=digest(b'HMS-PAT-IO-ORIGINAL-RECORD-v0.1',record),returnDigest=report['returnDigest'],
        groupResultDigest=returned['groupResultDigest'],outputClosure=report['evidenceIntegrity'])
    assert intent['anchor']==evaluation['anchor']==expected_anchor
    assert evaluation['outcome']=='passed' and evaluation['scope']=='complete-finite-synthetic-io-matrix'
    assert evaluation['inspectedCases']==30 and evaluation['unresolvedEffects']==0
    assert all(evaluation[key] is False for key in ('physicalObjectiveVerified','wallDeadlineAttested','aggregateDiskQuotaEnforced','catalogActivated'))
    assert authority.execute('SELECT request FROM iosr_runs').fetchall()==[(canonical(request),)]
    manifest_rows=vault.execute('SELECT sequence,intent,binding,record FROM ev_manifests LIMIT 2').fetchall()
    assert len(manifest_rows)==1
    sequence,stored_intent,binding,manifest_wire=manifest_rows[0]
    manifest=json.loads(manifest_wire)
    assert manifest_wire==canonical(manifest) and (sequence,stored_intent,binding)==(1,intent_digest,intent['bindingDigest'])
    assert manifest['scope']=='immutable-bytes-only' and manifest['previousManifestDigest'] is None
    assert manifest['sequence']==1 and manifest['intentDigest']==intent_digest and manifest['bindingDigest']==binding
    assert manifest['authorityId']==meta['authorityId'] and manifest['storeId']==meta['vault']['storeId']
    assert publication['manifestDigest']==digest(b'HMS-PAT-EVIDENCE-VAULT-MANIFEST-v0.1',manifest)
    assert vault.execute('SELECT count(*),sum(length(body)),max(length(body)) FROM ev_bodies').fetchone()[0]==2798
    assert vault.execute('SELECT sum(length(body)) FROM ev_bodies').fetchone()[0]<=24*1024*1024
    bodies={}
    for name,body in vault.execute('SELECT digest,body FROM ev_bodies LIMIT 2799'):
        assert type(body)is bytes and len(body)<=16777216 and body_sha(body)==name and name not in bodies
        bodies[name]=body
    refs=vault.execute('SELECT sequence,path,digest FROM ev_documents ORDER BY path LIMIT 4012').fetchall()
    assert len(refs)==4011 and len(bodies)==2798 and {row[2] for row in refs}==set(bodies)
    files={};chain=hashlib.sha256(b'HMS-PAT-IO-IMPORTED-CLOSURE-v0.1\0')
    for sequence,name,value in refs:
        assert sequence==1 and name not in files and re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',name)
        assert all(part not in ('.','..') for part in name.split('/')) and len(name)<=288
        body=bodies[value];files[name]=body
        chain.update(canonical(dict(path=name,bytes=len(body),sha256=value))+b'\n')
    closure=dict(documents=len(files),bytes=sum(map(len,files.values())),digest='sha256:'+chain.hexdigest())
    assert closure==manifest['closure']==publication['closure']
    assert files['evaluation.json']==canonical(evaluation) and body_sha(files['evaluation.json'])==publication['evaluationDigest']
    assert body_sha(files['inspection/summary.json'])==evaluation['inspectionDigest']
    inspection=json.loads(files['inspection/summary.json'])
    assert [row['caseId'] for row in inspection['cases']]==[row['caseId'] for row in matrix['cases']]
    assert all(inspection[key] is True for key in ('requiredMatrixCoverageChecked','independentOutcomeChecked',
        'archiveAccountingChecked','trustedSetupMatched','implementationIdentityMatched'))
    for i,case in enumerate(inspection['cases']):
        body=files['inspection/case-%02d.json'%i]
        assert hashlib.sha256(body).hexdigest()==case['inspectionSha256'] and len(body)==case['inspectionBytes']
        assert json.loads(body)['caseId']==case['caseId'] and case['expectedResponseVerified'] is True
    expected_files={}
    for name,value in dict(reservation=reservation,handoff=handoff,request=request,attempt=record).items():
        expected_files['original/control/'+name+'.json']=canonical(value)
    expected_files['original/control/return.json']=saved[0][2]
    source_documents=authority.execute('SELECT sequence,path,body FROM iosr_documents LIMIT 40').fetchall()
    assert len(source_documents)<=39
    for sequence,name,body in source_documents:
        assert sequence==1 and re.fullmatch(r'(inputs|cases)/[A-Za-z0-9_.-]+',name) and len(body)<=65536
        assert body==(worker/'bundle'/name).read_bytes()
        expected_files['original/bundle/'+name]=body
    expected_files['original/bundle/header.json']=canonical(request['bundleHeader'])
    assert (worker/'bundle/header.json').read_bytes()==expected_files['original/bundle/header.json']
    output_rows=inventory(output);output_chain=hashlib.sha256(b'HMS-PAT-IO-OUTPUT-CLOSURE-v0.1\0')
    for row in sorted(output_rows,key=lambda row:tuple(row['path'].split('/'))):
        output_chain.update(canonical(row)+b'\n')
        expected_files['original/output/'+row['path']]=(output/row['path']).read_bytes()
    output_closure=dict(fileCount=len(output_rows),bytes=sum(row['bytes'] for row in output_rows),orderedDigest='sha256:'+output_chain.hexdigest())
    assert output_closure==report['evidenceIntegrity']
    assert all(files.get(name)==body for name,body in expected_files.items())
    inspection_names={'evaluation.json','inspection/summary.json'}|{'inspection/case-%02d.json'%i for i in range(30)}
    assert set(files)==set(expected_files)|inspection_names
    group=read(output/'result.json')
    assert group['status']=='captured' and group['error'] is None and group['allMatrixCasesCaptured']
    assert len(group['cases'])==30 and group['accounting']['charged']==inspection['accounting']
    assert [row['caseId'] for row in group['cases']]==[row['caseId'] for row in matrix['cases']]
    for row in group['cases']:
        ref=row['manifest'];verify(output/ref['path'],dict(bytes=ref['bytes'],sha256=ref['sha256']))
    assert checks['originalAttemptId']==record['attemptId'] and checks['completeCases']==30
    assert checks['oneQualificationWorker'] and checks['realReducerUsed'] and checks['exactOriginalKeyReplay']
    assert checks['coldVaultAndBridgeHistory'] and checks['catalogIntegrated']
    assert checks['freshConfigurationRefusal']!='PAT_NO_MATCH' and checks['freshColdRefusal']!='PAT_NO_MATCH'
    assert all(checks[key] is False for key in ('physicalObjectiveVerified','aggregateDiskQuotaEnforced','physicalCapacityReserved'))
    assert checks['sourceApplicationInvocations']==1
    storage=checks['storage']
    assert storage==dict(authorityBytes=(work/'runtime/authority.db').stat().st_size,
        vaultBytes=(work/'vault/evidence.db').stat().st_size,references=len(refs),bodies=len(bodies))
    assert storage['authorityBytes']<=16777216 and storage['vaultBytes']<=15728640
    import_observation=dict(originalImportAndPublicationAssociated=True,allVaultBodiesAndReferencesVerified=True,
        originalBundleAndOutputBytesEqual=True,originalOutputClosure=output_closure,importedClosure=closure,
        completeCases=30,syntheticUnresolvedEffects=0,publicationDigest=publication_digest,intentDigest=intent_digest,
        manifestDigest=publication['manifestDigest'],inspectionSha256=evaluation['inspectionDigest'],storage=storage,
        vaultUnreservedPageCapHeadroomBytes=15728640-storage['vaultBytes'],catalogIntegrated=True,
        physicalObjectiveVerified=False,semanticReducerExecutedInOriginalScope=True,semanticReducerReexecutedByAudit=False)

    # Verify the separately versioned catalog and exact admitted application.
    host_names=('__init__.py','contracts.py','projection.py','bridge.py','catalog.py','execution.py')
    host_rows=[dict(path=name,bytes=(ATTEMPT/'project/vault_recorded_io'/name).stat().st_size,
        sha256='sha256:'+sha(ATTEMPT/'project/vault_recorded_io'/name)) for name in host_names]
    host=digest(b'HMS-PAT-IO-VAULT-RECORDED-HOST-v0.1',dict(consumerIdentity=consumer,sources=host_rows))
    assert host==pins['host'] and host_rows==pins['hostSources']
    recorded=read(work/'recorded-evaluation.json');receipt=recorded['receipt'];inv=receipt['invocation']
    evaluation_digest=digest(b'HMS-PAT-IO-VAULT-CATALOG-EVALUATION-v0.1',receipt)
    assert evaluation_digest==recorded['evaluationDigest']==checks['evaluationDigest']
    assert inv['original']==intent['anchor'] and inv['publicationDigest']==publication_digest
    assert inv['importIntentDigest']==intent_digest and inv['manifestDigest']==publication['manifestDigest']
    assert inv['evaluationDigest']==publication['evaluationDigest'] and inv['evidenceClosure']==closure
    assert inv['vaultStoreId']==intent['storeId'] and inv['vaultBindingDigest']==binding
    assert inv['hostImplementationDigest']==host and inv['consumerIdentity']==consumer
    assert receipt['physicalObjectiveVerified'] is False and receipt['outcome']=='passed'
    assert authority.execute('SELECT digest,document FROM pc_evaluations').fetchall()==[(evaluation_digest,canonical(receipt))]
    assert authority.execute('SELECT value FROM pc_meta WHERE key="version"').fetchone()==('hms.pat.io-vault-recorded-catalog/0.1',)
    mount='hms.pat.io-vault-recorded-catalog/0.1|'+digest(b'HMS-PAT-IO-VAULT-RECORDED-CATALOG-MOUNT-v0.1',
        dict(authorityId=meta['authorityId'],deployment=receipt['environment']['deployment'],
            hostImplementationDigest=host,evaluators=[receipt['evaluator']]))
    assert authority.execute('SELECT value FROM reg_meta WHERE key="io_vault_recorded_catalog"').fetchone()==(mount,)
    assert authority.execute('SELECT value FROM px_meta WHERE key="version"').fetchone()==('hms.pat.io-vault-execution/0.1',)
    cursor=authority.execute('SELECT * FROM px_instances LIMIT 2');instance_rows=cursor.fetchall()
    assert len(instance_rows)==1;instance=dict(zip([row[0] for row in cursor.description],instance_rows[0]))
    assert instance['id']==checks['instanceId'] and instance['evaluation_digest']==evaluation_digest
    assert instance['evaluation']==canonical(receipt)
    artifact=json.loads(instance['artifact']);assert canonical(artifact)==instance['artifact']
    assert digest(b'HMS-PAT-JCS-SHA256-v0.1',artifact)==instance['artifact_digest']==receipt['artifactDigest']
    decisions=authority.execute('SELECT digest,document FROM pc_decisions').fetchall();assert len(decisions)==1
    decision=json.loads(decisions[0][1]);assert canonical(decision)==decisions[0][1]==instance['decision']
    assert digest(b'HMS-PAT-DECISION-v0.1',decision)==decisions[0][0]==instance['decision_digest']
    assert authority.execute('SELECT state,evaluation,decision FROM pc_entries').fetchall()==[('active',evaluation_digest,instance['decision_digest'])]
    assert authority.execute('SELECT instance_id FROM px_triggers').fetchall()==[(instance['id'],)]
    assert authority.execute('SELECT id,state FROM pr_procedures').fetchall()==[(instance['procedure_id'],'completed')]
    operations=authority.execute('SELECT id,state,intent FROM operations').fetchall();assert len(operations)==1
    operation=operations[0];assert operation[1]=='completed'
    assert authority.execute('SELECT procedure_id,operation_id FROM pr_steps').fetchall()==[(instance['procedure_id'],operation[0])]
    compiled_request=json.loads(instance['compiled_request'])
    assert canonical(compiled_request)==instance['compiled_request']
    assert digest(b'HMS-PROCEDURE-JCS-SHA256-v0.1',compiled_request)==instance['compiled_digest']
    assert canonical(compiled_request['procedure']['steps'][0]['request']['intent'])==operation[2]
    assert authority.execute('SELECT operation_id FROM replay_keys').fetchall()==[(operation[0],)]
    assert authority.execute('SELECT count(*) FROM pr_keys').fetchone()[0]==2
    request_document=json.loads(instance['request'])
    assert digest(b'HMS-PAT-RUN-v0.1',request_document)==instance['request_digest']
    assert request_document['runKey']=='application:1'
    statuses=read(work/'application-statuses.json')['statuses'];assert 1<=len(statuses)<=8
    assert statuses[-1]['instanceId']==instance['id'] and statuses[-1]['procedure']['executionState']=='completed'
    assert statuses[-1]['procedure']['unresolvedOperations']==[]
    catalog_observation=dict(hostIdentity=host,receiptDigest=evaluation_digest,artifactDigest=instance['artifact_digest'],
        decisionDigest=instance['decision_digest'],instanceId=instance['id'],procedureId=instance['procedure_id'],
        operationId=operation[0],oneCompletedApplication=True,activations=1,completions=1,cancellations=0,
        originalKeyReplay=True,coldVaultAndBridgeHistory=True,configurationDriftRefusesFreshAdmission=True,
        exactInvocationPublicationManifestJoin=True,physicalObjectiveVerified=False)

    # Independently derive observations; never import the observer or project code.
    accounting=read(ATTEMPT/'worker-accounting.json')
    launches=read(ATTEMPT/'worker-accounting-launch-audit.json')
    assert len(launches)==1 and launches[0]['testId']==targets[0]==accounting['testId']
    assert accounting['profile']=='hms.worker-resource-observation/1' and accounting['errors']==[]
    observed=accounting['launch'];terminal=observed['terminal']
    assert observed['launchFailure'] is None and observed['pid']==record['pid']
    assert observed['argv']==launches[0]['argv'] and launches[0]['cwd']==str(image)
    assert observed['argv'][:4]==[read(ATTEMPT/'child-runtime.json')['executable'],'-I','-B',str(image/'supervisor/worker_entry.py')]
    assert terminal['observedBy']=='original-poll' and terminal['returnCode']==report['exitCode']==0
    assert observed['before']['afterMonotonicNs']<=observed['launchedMonotonicNs']<=terminal['snapshot']['beforeMonotonicNs']
    for name,position,path in (('attemptDirectory',4,worker),('input',5,worker/'input.json'),('writerLease',6,worker/'writer.lease')):
        info=path.lstat();description=observed['descriptors'][name]
        assert description['available'] and description['descriptor']==int(observed['argv'][position])
        for key,value in dict(device=info.st_dev,inode=info.st_ino,uid=info.st_uid,mode=stat.S_IMODE(info.st_mode),fileType=stat.S_IFMT(info.st_mode)).items():
            assert description[key]==value
        if name!='attemptDirectory':assert description['size']==info.st_size
    assert record['lease']=={key:str(observed['descriptors']['writerLease'][key]) for key in ('device','inode')}
    launch_input=read(worker/'input.json')
    assert launch_input==dict(profile='hms.pat.io-supervisor-launch/0.1',attemptId=record['attemptId'],request=request)
    assert (worker/'input.json').read_bytes()==canonical(launch_input)
    start_snapshot=accounting['testStart'];before_snapshot=observed['before']
    reaped_snapshot=terminal['snapshot'];finish_snapshot=accounting['testFinish']
    start_receipt=read(ATTEMPT/'worker-accounting-start.json')
    launch_receipt=read(ATTEMPT/'worker-accounting-launch.json')
    terminal_receipt=read(ATTEMPT/'worker-accounting-terminal.json')
    assert start_receipt['testStart']==start_snapshot and start_receipt['launch'] is None
    assert launch_receipt['launch']['before']==before_snapshot and launch_receipt['launch']['pid'] is None
    assert launch_receipt['launch']['terminal'] is None and terminal_receipt['launch']==observed
    assert terminal_receipt['testFinish'] is None
    additive=('ru_utime','ru_stime','ru_minflt','ru_majflt','ru_inblock','ru_oublock','ru_nvcsw','ru_nivcsw')
    raw_fields=set(additive)|{'ru_maxrss','ru_ixrss','ru_idrss','ru_isrss','ru_nswap','ru_msgsnd','ru_msgrcv','ru_nsignals'}
    snapshots=(start_snapshot,before_snapshot,reaped_snapshot,finish_snapshot)
    for position,snapshot in enumerate(snapshots):
        assert snapshot['beforeMonotonicNs']<=snapshot['afterMonotonicNs']
        if position:assert snapshots[position-1]['afterMonotonicNs']<=snapshot['beforeMonotonicNs']
        for scope in ('self','children'):
            raw_usage=snapshot['usage'][scope]
            assert raw_usage['available'] and set(raw_usage['raw'])==raw_fields
            assert all(type(value) in (int,float) and 0<=value<float('inf') for value in raw_usage['raw'].values())
        assert set(snapshot['pressure'])=={'cpu','memory','io'}
        for pressure in snapshot['pressure'].values():
            if pressure['available']:assert len(pressure['raw'].encode('ascii'))<=4096
            else:assert 'raw' not in pressure and type(pressure['errorType']) is str
    assert start_snapshot['usage']['children']==before_snapshot['usage']['children']
    assert reaped_snapshot['usage']['children']==finish_snapshot['usage']['children']
    for label,first,last in (('testDelta',start_snapshot,finish_snapshot),('launchToReapDelta',before_snapshot,reaped_snapshot)):
        derived={scope:{'available':True,'additiveCounters':{field:last['usage'][scope]['raw'][field]-first['usage'][scope]['raw'][field]
            for field in additive}} for scope in ('self','children')}
        assert derived==accounting[label]
        assert all(value>=0 for item in derived.values() for value in item['additiveCounters'].values())
    wall_bounds=[(reaped_snapshot['beforeMonotonicNs']-before_snapshot['afterMonotonicNs'])/1e9,
                 (reaped_snapshot['afterMonotonicNs']-before_snapshot['beforeMonotonicNs'])/1e9]
    interval=accounting['launchToReapDelta']
    cpu_seconds={scope:sum(interval[scope]['additiveCounters'][name] for name in ('ru_utime','ru_stime')) for scope in ('self','children')}
    observation=dict(associationVerified=True,directChildLaunches=1,originalAttemptId=record['attemptId'],pid=record['pid'],
        accountingSha256=sha(ATTEMPT/'worker-accounting.json'),launchAuditSha256=sha(ATTEMPT/'worker-accounting-launch-audit.json'),
        ownedObjectAndInheritedDescriptorsAssociated=True,pidBasedSampling=False,launchToReapWallSecondsBounds=wall_bounds,
        launchToReapCpuSeconds=cpu_seconds,launchToReapAdditiveCounters=interval,
        testAdditiveCounters=accounting['testDelta'],rawChildPeakRssKiB=reaped_snapshot['usage']['children']['raw']['ru_maxrss'],
        snapshotDurationsNs=[s['afterMonotonicNs']-s['beforeMonotonicNs'] for s in snapshots],
        globalPressureAvailable={name:all(s['pressure'][name]['available'] for s in snapshots) for name in ('cpu','memory','io')},
        childUsageOutsideObservedIntervalUnchanged=True,schedulingWaitCauseMeasured=False,
        parentFunctionAttributionMeasured=False,observerOverheadEliminated=False,
        deploymentTimingQualified=False)

    for db in reversed(dbs):db.close()
    dbs=[]
    for path,expected in hashes.items():assert sha(work/path)==expected
    assert inventory(raw)==rows==inventory(ATTEMPT/'scratch')
finally:
    for db in reversed(dbs):db.close()
    for fd in reversed(held):os.close(fd)
summary=dict(stageStatus='verified-progress-actual-scope-passed',sourceIndexSha256=PIN,harnessIndexSha256=HPIN,
    resultSha256=sha(ATTEMPT/'result.json'),catalogControls=19,previousNativeControlsReferenced=True,productionCandidateChanged=True,publicRuntimeChanged=False,
    actualScopePassed=True,originalAttemptId=record['attemptId'],supervisorReason=None,
    requestedCases=30,caseDirectories=30,caseManifests=30,incompleteScenario=None,
    originalMaxWallMs=60000,transportComplete=True,workerUnresolvedEffects=None,importReached=True,
    importIntents=1,publications=1,evidenceManifests=1,sourceApplicationInvocations=1,
    readonlySourceDatabases=hashes,workerCaseDatabasesOpened=0,ownerAndWriterLocks=locks,
    sourceAndOriginsAndRetainedBytesVerified=True,producerImageFiles=265,legacyIdentity=legacy,vaultIdentity=vault_id,consumerIdentity=consumer,
    sourceIdentitiesIndependentlyRecomputed=True,rawPath=str(raw),rawFiles=len(rows),rawBytes=result['scratchRetainedBytes'],
    phaseTimes=phases,observedSpawnToSettledMs=phase_map['worker_producer_settled']-phase_map['worker_spawned'],
    nativeImageReceiptVerified=True,nativeOriginReopenedAfterChildExit=False,nativeRetention=native,workerResourceObservation=observation,vaultImportObservation=import_observation,catalogObservation=catalog_observation,
    timeoutRootCauseEstablished=False,wholeWorkerPerformanceQualified=False,catalogIntegrated=True,
    physicalObjectiveVerified=False,aggregateDiskQuotaEnforced=False,independentReview=False,goalStatus='active')
assert read(BASE/'CONTROL_RESULTS.json')['testsRun']==19
with (BASE/'RESULTS.json').open('x') as stream:json.dump(summary,stream,indent=2);stream.write('\n')
print(json.dumps({key:summary[key] for key in ('stageStatus','catalogControls','caseManifests','importReached','rawFiles','catalogObservation','goalStatus')}))
