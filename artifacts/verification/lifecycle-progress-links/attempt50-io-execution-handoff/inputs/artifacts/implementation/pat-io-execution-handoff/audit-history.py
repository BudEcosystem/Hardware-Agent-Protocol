"""Read-only two-run joins and exact retained history mutations; no project imports."""
import fcntl, hashlib, json, os, sqlite3, sys
from pathlib import Path
B=Path.cwd()/'artifacts/implementation/pat-io-execution-handoff'; F=B/'results'/sys.argv[1]; R=F/'attempt/scratch'
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(domain,v): return 'sha256:'+hashlib.sha256(domain+b'\0'+canonical(v)).hexdigest()
def document(raw):
    assert type(raw) is bytes and 0<len(raw)<=65536
    value=json.loads(raw); assert canonical(value)==raw; return value
proof=read(F/'proof.json'); assert proof['status']=='passed' and proof['counts']['testsRun']==1
assert read(B/proof['harness']/'review.json')['selectionKind']=='history'
authority=read(F/'authority-audit.json'); runs=read(F/'run-audit.json')
assert authority['authorityCount']==1 and authority['allDatabasesUnchanged'] and authority['allSourceAuthorityEffectsZero']
assert runs['validatedRuns']==2 and runs['validatedDocuments']==74 and runs['allDatabasesUnchanged']
paths=list(R.glob('*/runtime/authority.db')); assert len(paths)==1
path=paths[0]; work=path.parent.parent; method=work.name; supervisor=work/'supervisor/attempts.db'
pins={p:sha(p) for p in (path,supervisor)}
for p in pins:
    assert not any(p.with_name(p.name+s).exists() for s in ('-wal','-shm','-journal'))
    raw=Path(proof['rawScratch']['path'])/p.relative_to(R); assert sha(raw)==pins[p]
    owner=raw.with_name(raw.name+'.owner') if p==path else raw.parent/'supervisor.owner'
    fd=os.open(owner,os.O_RDONLY|os.O_NOFOLLOW)
    try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    finally: os.close(fd)
db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
control=sqlite3.connect(supervisor.as_uri()+'?mode=ro&immutable=1',uri=True)
try:
    meta=dict(db.execute('SELECT key,value FROM meta')); reg=dict(db.execute('SELECT key,value FROM reg_meta'))
    version,identity=control.execute('SELECT version,authority FROM qs_meta').fetchone(); assert version==2
    mount=document(db.execute('SELECT record FROM iose_meta').fetchone()[0])
    assert mount['authorityId']==meta['authority'] and mount['deployment']==reg['deployment'] and mount['supervisorAuthorityId']==identity
    assert reg['io_service_execution']==mount['profile']+'|'+digest(b'HMS-PAT-IO-SERVICE-EXECUTION-v0.1',mount)
    actual={row[0]:tuple(document(v) if i<2 else v for i,v in enumerate(row[1:])) for row in control.execute('SELECT id,request,record,return_bytes FROM qs_attempts')}
    assert len(actual)==2
    baseline=read(work/'history-baseline.json'); assert baseline['launchBoundarySubstituted'] is True and baseline['actualWorkerExecuted'] is False
    original=[]; previous=None; prior_time=mount['createdAtUnixMs']; identifiers=[]
    for index,label in enumerate(('first','second'),1):
        saved=baseline[label]; receipt=saved['association']['receipt']; request=saved['attempt']['request']; record=saved['attempt']['record']
        identifier=record['attemptId']; identifiers.append(identifier)
        assert saved['attempt']['returnBytes'] is None and record['pid'] is record['lease'] is None
        assert request['context']['runId']=='run:'+str(index) and receipt['runId']==request['context']['runId']
        reservation_request,reservation_wire=db.execute('SELECT request,receipt FROM iosr_runs WHERE evaluator=? AND run=?',(receipt['evaluatorId'],receipt['runId'])).fetchone()
        reservation=document(reservation_wire)
        assert document(reservation_request)==request and actual[identifier][0]==request
        request_digest=digest(b'HMS-PAT-IO-SUPERVISOR-REQUEST-v0.1',request)
        reservation_digest=digest(b'HMS-PAT-IO-SERVICE-RUN-RESERVATION-v0.1',reservation)
        assert baseline[label+'ReservationDigest']==reservation_digest
        timestamp=receipt['committedAtUnixMs']; assert type(timestamp) is int and timestamp>=prior_time
        assert receipt==dict(profile='hms.pat.io-service-handoff/0.1',authorityId=meta['authority'],deployment=reg['deployment'],
            supervisorAuthorityId=identity,evaluatorId=request['context']['evaluatorId'],runId=request['context']['runId'],
            reservationDigest=reservation_digest,requestDigest=request_digest,attemptId=identifier,sequence=index,principal='owner',
            committedAtUnixMs=timestamp,previousHandoffDigest=previous)
        previous=digest(b'HMS-PAT-IO-SERVICE-HANDOFF-v0.1',receipt); prior_time=timestamp
        assert saved['association']['receiptDigest']==previous and record['requestDigest']==request_digest
        actual_request,actual_record,returned=actual[identifier]
        assert returned is None and actual_record['lease'] is actual_record['pid'] is None
        assert 'launching' not in actual_record['history'] and not (supervisor.parent/identifier).exists()
        if label=='first': assert actual_record==record and record['state']=='archived'
        else:
            assert record['state']=='admitted'
            assert actual_record['state']==('interrupted' if method=='test_two_logical_runs_keep_distinct_attempts_and_chain_on_reopen' else 'admitted')
        original.append([index,receipt['evaluatorId'],receipt['runId'],canonical(receipt)])
    assert identifiers[0]!=identifiers[1]
    rows=[list(r) for r in db.execute('SELECT sequence,evaluator,run,receipt FROM iose_handoffs ORDER BY sequence')]
    expected=[row[:] for row in original]; corruption=None
    if method=='test_two_logical_runs_keep_distinct_attempts_and_chain_on_reopen':
        replay=read(work/'history-replay.json'); assert replay['noNewLaunch'] is True and replay['actualWorkerExecuted'] is False
        assert replay['first']==baseline['first'] and replay['second']['association']==baseline['second']['association']
        assert replay['second']['attempt']['record']==actual[identifiers[1]][1]
        assert not (work/'history-refusal.json').exists()
    else:
        receipt=document(expected[1][3])
        if method=='test_well_formed_second_receipt_cannot_forge_previous_link':
            receipt['previousHandoffDigest']='sha256:'+'0'*64; corruption='forged-previous-link'
        elif method=='test_second_run_cannot_borrow_first_attempt_id':
            receipt['attemptId']=identifiers[0]; corruption='borrowed-attempt-id'
        elif method=='test_later_handoff_cannot_move_time_before_prior_receipt':
            assert document(original[0][3])['committedAtUnixMs']==1000
            receipt['committedAtUnixMs']=999; corruption='regressed-time'
        else:
            assert method=='test_reordering_committed_rows_is_not_a_new_valid_history'
            corruption='swapped-row-order'
        if corruption=='swapped-row-order': expected=[[1,*original[1][1:]],[2,*original[0][1:]]]
        else: expected[1][3]=canonical(receipt)
        check=read(work/'history-refusal.json')
        fingerprint=hashlib.sha256(canonical([[*row[:3],row[3].hex().upper()] for row in rows])).hexdigest()
        assert check==dict(before=fingerprint,after=fingerprint,reset=False,handoffs=2,supervisorAttempts=2)
        assert rows!=original and not (work/'history-replay.json').exists()
    assert rows==expected
finally:
    db.close();control.close()
for p,pin in pins.items(): assert sha(p)==pin
report=dict(scope='Independent two-reservation/two-attempt joins, original receipt chain, and exact retained history mutation or reopen replay. Both launches were substituted.',
    method=method,authorityId=meta['authority'],supervisorAuthorityId=identity,attemptIds=identifiers,
    reservationCount=2,inputDocuments=74,originalValidHandoffs=2,retainedCorruption=corruption,
    historicalReplayVerified=corruption is None,currentHistoryAccepted=corruption is None,
    originalOwnerLeasesFree=True,allDatabasesUnchanged=True,sourceAuthorityEffectsZero=True,
    actualWorkerExecuted=False,qualificationPassed=False)
with (F/'history-audit.json').open('x') as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
