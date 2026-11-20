"""Independent read-only joins, exact bodies, identities and allocation audit."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

BASE=Path('artifacts/implementation/pat-io-content-store')
ATTEMPT=BASE/'harness02/attempts/attempt01-compact-real'
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
raw=Path(result['scratchPath']);work=raw/'test_compact_bound_worker_import_and_historical_replay'
copied=ATTEMPT/'scratch/test_compact_bound_worker_import_and_historical_replay'
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
        receipt=json.loads(wire);external=read(work/'actual-import-receipt.json')
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
    replay=read(work/'bound-import-replay-checks.json');assert replay['exactReplayAfterConfigurationAndSessionDrift'] and replay['sourceEffectsUnchanged']
    assert replay['receiptDigest']==external['receiptDigest'] and not replay['freshEligibilityUnderChangedConfigurationClaimed']
    report=dict(actualScopePassed=True,completeMatrixCases=30,referenceCount=len(files),uniqueBodies=len(bodies),
        duplicateReferences=len(files)-len(bodies),expandedBytes=expanded,uniqueBodyBytes=unique,
        authorityDatabaseBytes=allocated,originalSingleFileLimit=16*1024*1024,headroomBytes=16*1024*1024-allocated,
        allOriginalAndStoredBytesMatched=True,originalDatabaseUnchanged=True,originalAuthorityHandoffAttemptJoined=True,
        configurationRevisions=[1,2],historicalReplayVerified=True,producerImageFiles=262,
        legacyConsumerIdentity=legacy_identity,compactConsumerIdentity=compact_identity,
        sourceIdentitiesIndependentlyRecomputed=True,receiptDigest=external['receiptDigest'],
        supervisorAuthorityId=supervisor_authority,attemptId=record['attemptId'],locksHeld=locks,
        unresolvedSimulatedEffects=0,physicalObjectiveVerified=False,freshEligibilityClaimed=False,
        generalCapacityOrTimingGuarantee=False,independentReviewer=False)
    with (BASE/'actual-import-audit.json').open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps({key:report[key] for key in ('actualScopePassed','completeMatrixCases','referenceCount','uniqueBodies','authorityDatabaseBytes','headroomBytes','sourceIdentitiesIndependentlyRecomputed')}))
finally:
    for fd in held:os.close(fd)
