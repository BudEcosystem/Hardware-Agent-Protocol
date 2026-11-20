"""Independent read-only joins, exact bodies, identities and allocation audit."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

BASE=Path('artifacts/implementation/pat-io-recorded-catalog')
ATTEMPT=BASE/'harness83/attempts/attempt01-actual'
def read(path):return json.loads(path.read_bytes())
def file_hash(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def sha(body):return 'sha256:'+hashlib.sha256(body).hexdigest()
def canonical(value):
    def check(item):
        if type(item) is dict:
            assert all(type(key) is str and key.isascii() for key in item)
            for child in item.values():check(child)
        elif type(item) is list:
            for child in item:check(child)
        else:assert type(item) in (str,int,bool,type(None)) and (type(item) is not int or abs(item)<=2**53-1)
    check(value);return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def hashed(domain,value):return sha(domain+b'\0'+canonical(value))
result=read(ATTEMPT/'result.json')
assert result['status']=='passed' and result['currentPass'] and result['childState']=='exited' and result['exitCode']==0
assert result['errors']==result['childErrors']==[] and result['scratchRetained']
raw=Path(result['scratchPath']);work=raw/'test_actual_original_matrix_catalog_execution_and_historical_replay'
copied=ATTEMPT/'scratch/test_actual_original_matrix_catalog_execution_and_historical_replay'
assert result['timeoutSeconds']==180 and result['limits']['singleAcquiredFileBytes']==16*1024*1024
held=[];locks=[]
try:
    for path in sorted(work.rglob('*')):
        assert not path.is_symlink()
        if path.is_file() and (path.name.endswith('.owner') or path.name in ('supervisor.owner','writer.lease')):
            fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK);held.append(fd);info=os.fstat(fd)
            assert stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1 and info.st_size==0
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            locks.append(dict(path=path.relative_to(work).as_posix(),device=str(info.st_dev),inode=str(info.st_ino)))
    ledger=work/'supervisor/attempts.db';before=file_hash(ledger)
    db=sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        values=db.execute('SELECT request,record,return_bytes FROM qs_attempts LIMIT 2').fetchall();assert len(values)==1
        request=json.loads(values[0][0]);record=json.loads(values[0][1]);returned=values[0][2]
        supervisor_authority=db.execute('SELECT authority FROM qs_meta').fetchone()[0]
    finally:db.close()
    assert file_hash(ledger)==before==file_hash(copied/'supervisor/attempts.db')
    assert record['state']=='archived' and record['archive']['transportComplete'] and record['archive']['unresolvedEffects'] is None
    assert request['groupLimits']['maxWallMs']==60000 and len(request['bundleHeader']['caseIds'])==30
    writer=next(row for row in locks if row['path'].endswith('/'+record['attemptId']+'/writer.lease'))
    assert record['lease']=={key:writer[key] for key in ('device','inode')}
    producer=work/'supervisor'/record['attemptId'];authority=work/'runtime/authority.db';before=file_hash(authority)
    assert authority.stat().st_size<=16*1024*1024
    db=sqlite3.connect(authority.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        metadata=db.execute('SELECT record FROM ioec_meta LIMIT 2').fetchall();assert len(metadata)==1
        meta=json.loads(metadata[0][0]);assert meta['profile']=='hms.pat.io-evidence-compact/0.1'
        assert db.execute("SELECT value FROM reg_meta WHERE key='io_evidence_compact'").fetchone()[0]==meta['profile']+'|'+hashed(b'HMS-PAT-IO-COMPACT-STORE-v0.1',meta)
        receipt_rows=db.execute('SELECT sequence,evaluator,run,receipt FROM ioec_runs LIMIT 2').fetchall();assert len(receipt_rows)==1
        sequence,evaluator,run,wire=receipt_rows[0];assert sequence==1
        receipt=json.loads(wire);external=read(work/'original-import.json')
        assert receipt==external['receipt'] and hashed(b'HMS-PAT-IO-COMPACT-IMPORTED-RECEIPT-v0.1',receipt)==external['receiptDigest']
        checks=db.execute('SELECT typeof(digest),length(CAST(digest AS BLOB)),typeof(body),length(body) FROM ioec_bodies LIMIT 32769').fetchall()
        assert len(checks)<=meta['maxObjects'] and sum(row[3]+256 for row in checks)<=meta['maxDataBytes']
        assert all(t=='text' and d==71 and bt=='blob' and type(n) is int and 0<=n<=16*1024*1024 for t,d,bt,n in checks)
        bodies={}
        for digest,body in db.execute('SELECT digest,body FROM ioec_bodies'):
            assert sha(body)==digest and digest not in bodies;bodies[digest]=body
        checks=db.execute('SELECT typeof(sequence),typeof(path),length(CAST(path AS BLOB)),typeof(digest),length(CAST(digest AS BLOB)) FROM ioec_documents LIMIT 32769').fetchall()
        assert len(checks)<=meta['maxDocuments']
        assert all(a=='integer' and b=='text' and 1<=c<=288 and d=='text' and e==71 for a,b,c,d,e in checks)
        files={};referenced=set()
        for seq,name,digest in db.execute('SELECT sequence,path,digest FROM ioec_documents ORDER BY sequence,path'):
            assert seq==1 and name not in files and digest in bodies and re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',name)
            assert all(part not in ('.','..') for part in name.split('/'))
            files[name]=bodies[digest];referenced.add(digest)
        assert referenced==set(bodies)
        expanded=sum(map(len,files.values()));unique=sum(map(len,bodies.values()))
        assert expanded+512*len(files)<=meta['maxExpandedDataBytes'] and expanded<=24*1024*1024
        chain=hashlib.sha256(b'HMS-PAT-IO-IMPORTED-CLOSURE-v0.1\0')
        for name,body in sorted(files.items()):chain.update(canonical(dict(path=name,bytes=len(body),sha256=sha(body)))+b'\n')
        assert receipt['closure']==dict(documents=len(files),bytes=expanded,digest='sha256:'+chain.hexdigest())
        assert sha(files['evaluation.json'])==receipt['evaluationDigest'] and json.loads(files['evaluation.json'])==external['evaluation']
        evaluation=external['evaluation'];anchor=evaluation['anchor'];assert anchor==receipt['anchor']
        assert anchor['runId']==run and anchor['evaluatorId']==evaluator
        reservation=json.loads(db.execute('SELECT receipt FROM iosr_runs WHERE sequence=1').fetchone()[0])
        handoff=json.loads(db.execute('SELECT receipt FROM iose_handoffs WHERE sequence=1').fetchone()[0])
        assert files['original/control/reservation.json']==canonical(reservation)
        assert files['original/control/handoff.json']==canonical(handoff)
        assert files['original/control/request.json']==canonical(request)
        assert files['original/control/attempt.json']==canonical(record) and files['original/control/return.json']==returned
        assert anchor['reservationDigest']==hashed(b'HMS-PAT-IO-SERVICE-RUN-RESERVATION-v0.1',reservation)
        assert anchor['handoffDigest']==hashed(b'HMS-PAT-IO-SERVICE-HANDOFF-v0.1',handoff)
        assert anchor['supervisorAuthorityId']==supervisor_authority==handoff['supervisorAuthorityId']
        assert anchor['attemptId']==record['attemptId']==handoff['attemptId']
        config_rows=db.execute('SELECT revision,receipt FROM iosc_versions ORDER BY sequence').fetchall()
        assert [row[0] for row in config_rows]==[1,2]
        assert anchor['configurationReceiptDigest']==hashed(b'HMS-PAT-IO-SERVICE-CONFIGURATION-RECEIPT-v0.1',json.loads(config_rows[0][1]))
        assert anchor['configurationReceiptDigest']!=hashed(b'HMS-PAT-IO-SERVICE-CONFIGURATION-RECEIPT-v0.1',json.loads(config_rows[1][1]))
        outputs={name[len('original/output/'):]:body for name,body in files.items() if name.startswith('original/output/')}
        original_outputs={path.relative_to(producer/'output').as_posix():path for path in (producer/'output').rglob('*') if path.is_file()}
        assert set(outputs)==set(original_outputs)
        output_chain=hashlib.sha256(b'HMS-PAT-IO-OUTPUT-CLOSURE-v0.1\0')
        for name in sorted(outputs,key=lambda value:tuple(value.split('/'))):
            body=outputs[name];assert original_outputs[name].read_bytes()==body
            output_chain.update(canonical(dict(path=name,bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))+b'\n')
        assert record['archive']['evidenceIntegrity']==dict(fileCount=len(outputs),bytes=sum(map(len,outputs.values())),orderedDigest='sha256:'+output_chain.hexdigest())
        for name,body in files.items():
            if name.startswith('original/bundle/'):assert (producer/'bundle'/name[len('original/bundle/'):]).read_bytes()==body
        summary=json.loads(files['inspection/summary.json'])
        assert len(summary['cases'])==30 and evaluation['inspectedCases']==30 and evaluation['unresolvedEffects']==0
        assert not evaluation['physicalObjectiveVerified'] and not evaluation['catalogActivated']
        catalog_rows=db.execute('SELECT digest,document FROM pc_evaluations LIMIT 2').fetchall();assert len(catalog_rows)==1
        catalog_digest,catalog_wire=catalog_rows[0];catalog=json.loads(catalog_wire)
        assert canonical(catalog)==catalog_wire and catalog_digest==hashed(b'HMS-PAT-IO-CATALOG-EVALUATION-v0.1',catalog)
        assert catalog['protocol']=='hms.pat.io-catalog-evaluation/0.1' and catalog['outcome']=='passed' and catalog['physicalObjectiveVerified'] is False
        emitted=read(work/'recorded-evaluation.json');assert emitted==dict(evaluationDigest=catalog_digest,receipt=catalog)
        invocation=catalog['invocation'];applicability=catalog['applicability']
        assert invocation['original']==anchor and invocation['importReceiptDigest']==external['receiptDigest']
        assert invocation['consumerIdentity']==meta['consumerIdentity'] and invocation['evidenceClosure']==receipt['closure']
        assert invocation['caseIds']==request['bundleHeader']['caseIds'] and invocation['matrixDigest']==request['bundleHeader']['matrixDigest']
        assert catalog['runId']==run and catalog['artifactDigest']==anchor['artifactDigest']
        matrix=json.loads(files['original/bundle/inputs/matrix.json'])
        candidate=json.loads(files['original/bundle/inputs/candidate.json'])
        descriptor=json.loads(files['original/bundle/inputs/descriptor.json']);binding=descriptor['binding']
        role=matrix['candidateContract']['role'];assert [case['caseId'] for case in matrix['cases']]==invocation['caseIds']
        groups={category:[] for category in ('positive','boundary','negative','fault')}
        for i,case in enumerate(matrix['cases']):
            categories=case['domainCase']['categories'] if case['kind']=='candidate' else ['fault']
            for category in categories:groups[category].append(dict(caseId=case['caseId'],inspectionDigest=sha(files['inspection/case-%02d.json'%i])))
        assert all(groups.values())
        required=[dict(id='complete-matrix:'+category,category=category) for category in groups]
        checks=[item|dict(outcome='passed',evidenceDigest=hashed(b'HMS-PAT-IO-COMPLETE-CATEGORY-v0.1',groups[item['category']])) for item in required]
        assert catalog['evaluator']['requiredChecks']==required and catalog['result']['checks']==checks and catalog['result']['unresolvedEffects']==0
        dependency=dict(role=role,descriptionDigest=binding['typeDigest'],bindingDigest=sha(canonical(binding)),
            instanceId=binding['instanceId'],bindingGeneration=binding['generation'],controlGeneration=binding['controlGeneration'],
            calibrationRevision=binding['calibrationRevision'],endpointSession=descriptor['endpointSession'],driverProfile=descriptor['driverProfile'],
            driverDigest=descriptor['driverDigest'],installationDigest=descriptor['installationDigest'],metadataDigest=sha(canonical(descriptor['argumentMetadata'])))
        assert applicability['dependencies']==[dependency] and applicability['roleInstances']=={role:binding['instanceId']}
        for name in ('authorityId','deployment','configurationReceiptDigest','configurationDigest','configurationRevision'):
            assert applicability[name]==anchor[name]
        expected_role=dict(typeDigest=dependency['descriptionDigest'],bindingDigest=dependency['bindingDigest'],
            installationDigest=dependency['installationDigest'],argumentMetadataDigest=dependency['metadataDigest'],
            driverProfile=dependency['driverProfile'],driverDigest=dependency['driverDigest'])
        assert catalog['environment']['roles']=={role:expected_role} and catalog['environment']['profile']=='hms.pat.environment/0.1'
        assert catalog['environmentDigest']==hashed(b'HMS-PAT-ENVIRONMENT-v0.1',catalog['environment'])
        assert db.execute('SELECT session FROM reg_presence WHERE instance=?',(binding['instanceId'],)).fetchone()[0]!=dependency['endpointSession']
        assert db.execute('SELECT sequence FROM iosc_heads WHERE evaluator=?',(evaluator,)).fetchone()[0]==2
        entries=db.execute('SELECT state,evaluation,decision,evaluation_conflict FROM pc_entries').fetchall();assert len(entries)==1
        assert entries[0][0]=='active' and entries[0][1]==catalog_digest and entries[0][3]==0
        decision_digest=entries[0][2]
        decision_rows=db.execute('SELECT document FROM pc_decisions WHERE digest=?',(decision_digest,)).fetchall();assert len(decision_rows)==1
        decision=json.loads(decision_rows[0][0]);assert hashed(b'HMS-PAT-DECISION-v0.1',decision)==decision_digest
        assert decision['to']=='active' and decision['evaluationDigest']==catalog_digest
        cursor=db.execute('SELECT * FROM px_instances LIMIT 2');columns=[item[0] for item in cursor.description];instances=cursor.fetchall();assert len(instances)==1
        instance=dict(zip(columns,instances[0]));assert instance['evaluation_digest']==catalog_digest and instance['evaluation']==catalog_wire
        assert instance['decision_digest']==decision_digest and json.loads(instance['artifact'])==candidate
        compilation=json.loads(instance['compilation']);assert compilation['requestDigest']==instance['compiled_digest']
        assert canonical(compilation['request'])==instance['compiled_request'] and compilation['evaluationEnvironment']==catalog['environment']
        assert instance['artifact_digest']==anchor['artifactDigest'] and db.execute('SELECT count(*) FROM px_triggers').fetchone()[0]==1
        procedures=db.execute('SELECT id,state,digest,request FROM pr_procedures').fetchall();assert len(procedures)==1
        assert procedures[0]==(instance['procedure_id'],'completed',instance['compiled_digest'],instance['compiled_request'])
        operations=db.execute('SELECT id,state FROM operations').fetchall();assert len(operations)==1 and operations[0][1]=='completed'
        assert db.execute('SELECT count(*) FROM claims').fetchone()[0]==0
        assert db.execute('SELECT operation_id FROM pr_steps').fetchall()==[(operations[0][0],)]
        assert read(work/'application-admission.json')['instanceId']==instance['id']
        statuses=read(work/'application-statuses.json');assert 1<=statuses['ticks']<=8 and statuses['statuses'][-1]['procedure']['executionState']=='completed'
        assert statuses['statuses'][-1]['procedure']['unresolvedOperations']==[]
        assert read(work/'changed-context-refusal.json')['code']=='PAT_EVIDENCE_UNAVAILABLE'
        mount_value=db.execute("SELECT value FROM reg_meta WHERE key='io_recorded_catalog'").fetchone()[0]
        allocated=authority.stat().st_size
        assert allocated==db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]
    finally:db.close()
    assert file_hash(authority)==before==file_hash(copied/'runtime/authority.db')
    image=work/'supervisor'/('code-'+request['supervisorIdentity'][7:])
    image_files=[path for path in image.rglob('*') if path.is_file()];assert len(image_files)==262
    external_inputs=read(ATTEMPT/'external-before.json')['files'];source_rows=[]
    for path in image_files:
        relative=path.relative_to(image).as_posix();digest=file_hash(path)
        if relative.startswith('dependencies/'):
            matches=[row for row in external_inputs if row['resolvedPath'].endswith('/'+relative[len('dependencies/'):])]
            assert len(matches)==1 and matches[0]['sha256']==digest
        else:assert digest==file_hash(ATTEMPT/'project'/relative)
        source_rows.append(dict(path=relative,bytes=path.stat().st_size,sha256=digest))
    for name in ('__init__.py','contracts.py','archive.py','reducer.py','store.py'):
        path=ATTEMPT/'project/evidence'/name
        source_rows.append(dict(path='evidence/'+name,bytes=path.stat().st_size,sha256=file_hash(path)))
    legacy_identity=hashed(b'HMS-PAT-IO-EVIDENCE-CONSUMER-v0.1',sorted(source_rows,key=lambda row:row['path']))
    assert legacy_identity=='sha256:b378f8726e4ab4220233dfaac55389124ab9af5998f0eb374d57d8aebcd98f3a'
    compact_rows=[]
    for name in ('__init__.py','contracts.py','store.py'):
        path=ATTEMPT/'project/evidence_compact'/name
        compact_rows.append(dict(path='evidence_compact/'+name,bytes=path.stat().st_size,sha256=file_hash(path)))
    compact_identity=hashed(b'HMS-PAT-IO-COMPACT-CONSUMER-v0.1',dict(legacyConsumerIdentity=legacy_identity,sources=compact_rows))
    assert compact_identity==meta['consumerIdentity']==receipt['consumerIdentity']==evaluation['consumerIdentity']
    host_rows=[]
    for name in ('__init__.py','contracts.py','projection.py','bridge.py','catalog.py','execution.py'):
        path=ATTEMPT/'project/recorded_io'/name
        host_rows.append(dict(path=name,bytes=path.stat().st_size,sha256='sha256:'+file_hash(path)))
    host_identity=hashed(b'HMS-PAT-IO-RECORDED-HOST-v0.1',dict(consumerIdentity=compact_identity,sources=host_rows))
    assert invocation['hostImplementationDigest']==catalog['evaluator']['implementationDigest']==host_identity
    assert mount_value=='hms.pat.io-recorded-catalog/0.1|'+hashed(b'HMS-PAT-IO-RECORDED-CATALOG-MOUNT-v0.1',dict(
        authorityId=anchor['authorityId'],deployment=anchor['deployment'],hostImplementationDigest=host_identity,evaluators=[catalog['evaluator']]))
    policy=hashed(b'HMS-PAT-IO-RECORDED-CATALOG-POLICY-v0.1',dict(matrixPolicy='hms.pat.eval.sqlite-finite-io-combined/0.3',
        completeOriginalMatrixRequired=True,candidateCategories='all original domainCase.categories',fixedChallengeCategory='fault',
        originalRunRequired=True,currentSourceApplicabilityRequired=True,physicalObjectiveVerified=False))
    assert policy==invocation['evaluationPolicyDigest']==catalog['evaluator']['policyDigest']
    board=next((work/'runtime').glob('synthetic-io-board-*.db'));before_board=file_hash(board)
    db=sqlite3.connect(board.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        assert [row[1] for row in db.execute('PRAGMA table_info(io_effects)')]==['instance','activations','completed','canceled']
        effects=db.execute('SELECT instance,activations,completed,canceled FROM io_effects').fetchall();assert len(effects)==4
        assert all(row[1:]==((1,1,0) if row[0]==binding['instanceId'] else (0,0,0)) for row in effects)
        assert db.execute('SELECT count(*) FROM io_owners').fetchone()[0]==0
    finally:db.close()
    assert file_hash(board)==before_board==file_hash(copied/'runtime'/board.name)
    replay=read(work/'recorded-integration-checks.json')
    assert replay['originalAttemptId']==record['attemptId'] and replay['importReceiptDigest']==external['receiptDigest']
    assert replay['catalogEvaluationDigest']==catalog_digest and replay['applicationInstanceId']==instance['id']
    assert all(replay[name] is True for name in ('oneQualificationWorker','oneApplicationInvocation','exactOriginalKeyReplay','historicalReplayAfterConfigurationAndSessionDrift'))
    assert not replay['unavailableEvidenceIsNovelty'] and not replay['physicalObjectiveVerified']
    report=dict(actualScopePassed=True,completeMatrixCases=30,referenceCount=len(files),uniqueBodies=len(bodies),
        duplicateReferences=len(files)-len(bodies),expandedBytes=expanded,uniqueBodyBytes=unique,
        authorityDatabaseBytes=allocated,originalSingleFileLimit=16*1024*1024,headroomBytes=16*1024*1024-allocated,
        allOriginalAndStoredBytesMatched=True,originalDatabaseUnchanged=True,originalAuthorityHandoffAttemptJoined=True,
        configurationRevisions=[1,2],historicalReplayVerified=True,producerImageFiles=262,
        legacyConsumerIdentity=legacy_identity,compactConsumerIdentity=compact_identity,recordedHostIdentity=host_identity,
        sourceIdentitiesIndependentlyRecomputed=True,receiptDigest=external['receiptDigest'],
        supervisorAuthorityId=supervisor_authority,attemptId=record['attemptId'],locksHeld=locks,
        unresolvedSimulatedEffects=0,physicalObjectiveVerified=False,freshEligibilityUnderChangedContextClaimed=False,
        originalContextPromotionVerified=True,originalConfigurationCatalogJoined=True,catalogEvaluationDigest=catalog_digest,
        applicationInstanceId=instance['id'],applicationActivations=1,applicationCompletions=1,applicationCancellations=0,
        currentClaims=0,boardOwners=0,oneOriginalWorker=True,changedContextRefusedWithoutNovelty=True,
        generalCapacityOrTimingGuarantee=False,independentReviewer=False)
    with (BASE/'actual-catalog-audit.json').open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps({key:report[key] for key in ('actualScopePassed','completeMatrixCases','referenceCount','uniqueBodies','authorityDatabaseBytes','headroomBytes','sourceIdentitiesIndependentlyRecomputed')}))
finally:
    for fd in held:os.close(fd)
