"""Independent run/config/request/document/receipt joins on closed retained DBs."""
import hashlib,json,sqlite3,sys
from pathlib import Path
B=Path.cwd()/'artifacts/implementation/pat-io-execution-handoff';F=B/'results'/sys.argv[1];A=F/'attempt';R=A/'scratch'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(domain,v):return 'sha256:'+hashlib.sha256(domain+b'\0'+canonical(v)).hexdigest()
def document(w):
 assert type(w)is bytes and 0<len(w)<=65536
 value=json.loads(w);assert canonical(value)==w;return value
proof=read(F/'proof.json');assert proof['status']=='failed'
assert read(A/'harness/targets.json')['targets']==['test_io_service_execution.IoServiceExecutionProcessTests.test_owned_group_persists_handoff_before_launch_and_replays_after_drift']
authority=read(F/'authority-audit.json');assert authority['allDatabasesUnchanged']and authority['allSourceAuthorityEffectsZero']
corrupt={
 'test_added_trigger_refuses_before_any_further_reservation':'extra-trigger',
 'test_all_run_tables_missing_with_anchor_are_never_recreated':'absent-tables',
 'test_changed_input_bytes_refuse_and_remain_retained':'changed-document',
 'test_metadata_limit_tampering_cannot_widen_capacity':'metadata-anchor',
 'test_missing_document_refuses_without_reconstruction':'missing-document',
 'test_non_blob_request_refuses_and_remains_retained':'request-type',
 'test_non_object_receipt_refuses_and_remains_retained':'receipt-array',
 'test_oversized_input_document_refuses_before_payload_read':'oversized-document',
 'test_partial_schema_refuses_without_recreation':'missing-table',
 'test_wrong_configuration_reference_refuses_and_remains_retained':'configuration-reference',
}
reports=[];corruptions=[];total_runs=total_documents=0
for path in sorted(R.glob('*/runtime/authority.db')):
 method=path.parent.parent.name;work=path.parent.parent;before=sha(path)
 assert not any(path.with_name(path.name+s).exists()for s in ('-wal','-shm','-journal'))
 db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
 try:
  identity=dict(db.execute('SELECT key,value FROM meta'))['authority'];reg=dict(db.execute('SELECT key,value FROM reg_meta'))
  schema={r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE name GLOB 'iosr_*'")};kind=corrupt.get(method)
  if kind:
   if kind=='extra-trigger':assert 'iosr_extra'in schema
   elif kind=='absent-tables':assert schema==set()and 'io_service_runs'in reg
   elif kind=='changed-document':assert db.execute("SELECT body FROM iosr_documents WHERE path='inputs/descriptor.json'").fetchone()==(b'{}',)
   elif kind=='metadata-anchor':
    meta=document(db.execute('SELECT record FROM iosr_meta').fetchone()[0]);assert meta['maxRuns']==32
    assert reg['io_service_runs']!='hms.pat.io-service-runs/0.1|'+digest(b'HMS-PAT-IO-SERVICE-RUNS-META-v0.1',meta)
   elif kind=='missing-document':assert db.execute("SELECT 1 FROM iosr_documents WHERE path='inputs/descriptor.json'").fetchone()is None
   elif kind=='request-type':assert db.execute('SELECT typeof(request),request FROM iosr_runs').fetchone()==('text','{}')
   elif kind=='receipt-array':assert db.execute('SELECT receipt FROM iosr_runs').fetchone()==(b'[]',)
   elif kind=='oversized-document':assert db.execute("SELECT body FROM iosr_documents WHERE path='inputs/descriptor.json'").fetchone()==(b' '*65537,)
   elif kind=='missing-table':assert 'iosr_documents'not in schema and 'io_service_runs'in reg
   elif kind=='configuration-reference':assert db.execute('SELECT configuration_sequence FROM iosr_runs').fetchone()==(128,)
   check=work/'corruption-check.json'
   if check.exists():
    value=read(check);assert value['before']==value['after']and value['restored']is False
   corruptions.append(dict(method=method,kind=kind,retained=True));runs=None;documents=None
  else:
   assert schema=={'iosr_meta','iosr_runs','iosr_documents'}
   raw_meta=db.execute('SELECT record FROM iosr_meta WHERE singleton=1').fetchone()[0];meta=document(raw_meta)
   assert meta['authorityId']==identity and meta['deployment']==reg['deployment']
   assert reg['io_service_runs']=='hms.pat.io-service-runs/0.1|'+digest(b'HMS-PAT-IO-SERVICE-RUNS-META-v0.1',meta)
   rows=db.execute('SELECT sequence,evaluator,run,intent,configuration_sequence,request,receipt FROM iosr_runs ORDER BY sequence').fetchall()
   docs=db.execute('SELECT sequence,path,body FROM iosr_documents ORDER BY sequence,path').fetchall()
   assert [r[0]for r in rows]==list(range(1,len(rows)+1))and len(rows)<=meta['maxRuns']<=32 and len(docs)<=39*meta['maxRuns']
   documents_by_run={}
   for seq,p,body in docs:
    assert type(body)is bytes and 0<len(body)<=65536;group=documents_by_run.setdefault(seq,{})
    assert p not in group;group[p]=body
   assert set(documents_by_run)=={r[0]for r in rows}
   previous=None;last_time=meta['createdAtUnixMs'];charge=len(raw_meta)+1024
   for sequence,evaluator,run,intent_raw,config_seq,request_raw,receipt_raw in rows:
    intent,request,receipt=map(document,(intent_raw,request_raw,receipt_raw));docs_for_run=documents_by_run[sequence]
    config_raw,pin_raw,config_receipt_raw=db.execute('SELECT configuration,pin,receipt FROM iosc_versions WHERE sequence=?',(config_seq,)).fetchone()
    config,pin,config_receipt=map(document,(config_raw,pin_raw,config_receipt_raw))
    config_digest=digest(b'HMS-PAT-IO-SERVICE-CONFIGURATION-RECEIPT-v0.1',config_receipt)
    artifact=document(docs_for_run['inputs/candidate.json']);artifact_digest=digest(b'HMS-PAT-JCS-SHA256-v0.1',artifact)
    assert intent==dict(profile='hms.pat.io-service-run-intent/0.1',authorityId=identity,deployment=reg['deployment'],evaluatorId=evaluator,runId=run,artifactDigest=artifact_digest,configurationReceiptDigest=config_digest)
    assert pin['authorityId']==identity and pin['configurationDigest']==digest(b'HMS-PAT-IO-AUTHORITY-SERVICE-CONFIG-v0.1',dict(authorityId=identity,configuration=config))
    assert request['context']==dict(deployment=reg['deployment'],evaluatorId=evaluator,runId=run,configurationDigest=pin['configurationDigest'],configurationRevision=config['revision'])
    assert request['implementation']==pin['implementation']and request['supervisorIdentity']==pin['supervisorIdentity']
    assert request['limits']==config['supervisorLimits']and request['groupLimits']==config['groupLimits']
    request_digest=digest(b'HMS-PAT-IO-SUPERVISOR-REQUEST-v0.1',request);header=request['bundleHeader']
    assert header['context']==request['context']and request['bundleDigest']==digest(b'HMS-PAT-IO-RUN-BUNDLE-v0.1',header)
    manifest=header['manifest'];assert set(docs_for_run)=={row['path']for row in manifest}and len(manifest)==len(docs_for_run)
    assert header['inputBytes']==sum(map(len,docs_for_run.values()))and header['inputSetDigest']==digest(b'HMS-PAT-IO-INPUT-SET-v0.1',manifest)
    for ref in manifest:
     body=docs_for_run[ref['path']];assert ref['bytes']==len(body)and ref['sha256']==hashlib.sha256(body).hexdigest();document(body)
    timestamp=receipt['committedAtUnixMs'];assert type(timestamp)is int and timestamp>=last_time;last_time=timestamp
    assert receipt==dict(profile='hms.pat.io-service-run-reservation/0.1',authorityId=identity,deployment=reg['deployment'],evaluatorId=evaluator,runId=run,sequence=sequence,artifactDigest=artifact_digest,intentDigest=digest(b'HMS-PAT-IO-SERVICE-RUN-INTENT-v0.1',intent),configurationSequence=config_seq,configurationReceiptDigest=config_digest,requestDigest=request_digest,bundleDigest=request['bundleDigest'],principal=receipt['principal'],previousReservationDigest=previous,committedAtUnixMs=timestamp)
    previous=digest(b'HMS-PAT-IO-SERVICE-RUN-RESERVATION-v0.1',receipt)
    charge+=len(intent_raw)+len(request_raw)+len(receipt_raw)+512+sum(len(body)+128 for body in docs_for_run.values())
    if method=='test_owned_group_persists_handoff_before_launch_and_replays_after_drift':
     assert len(rows)==1 and config_seq==1
     assert read(work/'run-reservation.json')==dict(reservation=receipt,reservationDigest=previous)
     assert db.execute('SELECT count(*) FROM iosc_versions').fetchone()==(1,)
     assert not (work/'handoff-replay-checks.json').exists() and not (work/'inspection/summary.json').exists()
     retained=read(work/'worker-archive.json');launching=read(work/'launching-handoff.json')
     assert retained['phases']==['admitted','launching','spawned','producer_settled','archived']
     assert retained['association']==launching['association']
     assert retained['association']['receipt']['reservationDigest']==previous
     assert retained['association']['receipt']['requestDigest']==request_digest
     identifier=retained['association']['receipt']['attemptId']
     assert retained['record']['attemptId']==identifier and launching['attempt']['record']['attemptId']==identifier
     assert launching['attempt']['record']['state']=='launching' and launching['attempt']['record']['pid'] is None
     assert launching['attempt']['request']==request
     for p,body in docs_for_run.items():assert (work/'supervisor'/identifier/'bundle'/p).read_bytes()==body
     actors=document(docs_for_run['inputs/bindings.json'])
     for actor in actors.values():
      d=actor['descriptor'];instance=d['binding']['instanceId']
      assert document(db.execute('SELECT document FROM reg_bindings WHERE instance=?',(instance,)).fetchone()[0])==d['binding']
      assert db.execute('SELECT session FROM reg_presence WHERE instance=?',(instance,)).fetchone()==(d['endpointSession'],)
    if method=='test_reserved_owned_group_replays_after_config_and_session_change':
     assert len(rows)==1 and config_seq==1 and (work/'service-configuration.json').read_bytes()==config_raw and (work/'service-pin.json').read_bytes()==pin_raw
     assert read(work/'run-reservation.json')==dict(reservation=receipt,reservationDigest=previous)
     check=read(work/'run-replay-checks.json');assert check['reservationDigest']==previous and check['requestDigest']==request_digest
     assert check['originalConfigurationReceiptDigest']==config_digest and check['activeConfigurationReceiptDigest']!=config_digest
     active=db.execute('SELECT receipt FROM iosc_versions WHERE sequence=2').fetchone()[0]
     assert check['activeConfigurationReceiptDigest']==digest(b'HMS-PAT-IO-SERVICE-CONFIGURATION-RECEIPT-v0.1',document(active))
     assert check['replayWithoutPlanning']and check['sameSupervisorAttempt']and check['sourceEffectsUnchanged']
     control_path=work/'supervisor/attempts.db';control_pin=sha(control_path)
     control=sqlite3.connect(control_path.as_uri()+'?mode=ro&immutable=1',uri=True)
     try:control_rows=control.execute('SELECT request,record FROM qs_attempts').fetchall()
     finally:control.close()
     assert sha(control_path)==control_pin and len(control_rows)==1 and control_rows[0][0]==request_raw
     record=document(control_rows[0][1]);assert record['attemptId']==check['attemptId']and record['requestDigest']==request_digest
     bundle_root=work/'supervisor'/record['attemptId']/'bundle'
     for p,body in docs_for_run.items():assert (bundle_root/p).read_bytes()==body
     actors=document(docs_for_run['inputs/bindings.json'])
     for actor in actors.values():
      d=actor['descriptor'];instance=d['binding']['instanceId'];session=d['endpointSession']
      assert document(db.execute('SELECT document FROM reg_bindings WHERE instance=?',(instance,)).fetchone()[0])==d['binding']
      assert db.execute('SELECT 1 FROM reg_session_history WHERE instance=? AND session=?',(instance,session)).fetchone()==(1,)
      assert db.execute('SELECT session FROM reg_presence WHERE instance=?',(instance,)).fetchone()[0]!=session
     image=work/'supervisor'/('code-'+request['supervisorIdentity'][7:])
     assert (image/'supervisor/io_service_runs.py').read_bytes()==(A/'project/supervisor/io_service_runs.py').read_bytes()
   assert charge<=meta['maxDataBytes'];runs=len(rows);documents=len(docs);total_runs+=runs;total_documents+=documents
   if method=='test_temp_shadow_refuses_before_reading_its_contents':
    check=read(work/'corruption-check.json');assert check['before']==check['after']and check['restored']is False
 finally:db.close()
 assert sha(path)==before
 reports.append(dict(path=path.relative_to(R).as_posix(),sha256=before,validatedRuns=runs,validatedDocuments=documents,corruptFixture=kind))
report=dict(scope='Independent authority-bound reservation, configuration-history and exact retained supervisor-input joins. A reservation is not proof of execution.',authorities=reports,validatedRuns=total_runs,validatedDocuments=total_documents,corruptFixtures=corruptions,allDatabasesUnchanged=True,sourceAuthorityEffectsZero=True,completedWorker=False,postWorkerReplayReached=False,qualificationPassed=False)
with(F/'run-audit.json').open('x')as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(authorities=len(reports),validatedRuns=total_runs,validatedDocuments=total_documents,corruptFixtures=len(corruptions))))
