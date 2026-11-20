"""Independent retained authority/board checks, without importing project code."""
import fcntl,hashlib,json,os,sqlite3,sys
from pathlib import Path
B=Path.cwd()/'artifacts/implementation/pat-io-service-runs';F=B/'results'/sys.argv[1];A=F/'attempt';R=A/'scratch'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(domain,v):return 'sha256:'+hashlib.sha256(domain+b'\0'+canonical(v)).hexdigest()
def document(w):
 assert type(w)is bytes and 0<len(w)<=65537
 v=json.loads(w);assert canonical(v)==w;return v
proof=read(F/'proof.json');assert proof['status']=='failed'
assert read(A/'harness/targets.json')['targets']==['test_io_service_runs.IoReservedProcessTests.test_reserved_owned_group_replays_after_config_and_session_change']
result=read(A/'result.json');assert result['childState']=='exited' and not (Path('/proc')/str(result['pid'])).exists()
corrupt={
 'test_added_index_refuses_and_is_retained':'extra-index',
 'test_all_owned_tables_missing_with_anchor_never_reinitialize':'absent-tables',
 'test_legacy_unbound_pin_cannot_enter_authority_history':'legacy-pin',
 'test_metadata_capacity_tampering_is_not_a_limit_change':'metadata-anchor',
 'test_missing_head_refuses_and_is_never_rebuilt':'missing-head',
 'test_mutation_header_mismatch_refuses_and_is_retained':'mutation-header',
 'test_non_object_receipt_refuses_and_is_retained':'receipt-array',
 'test_noncanonical_pin_refuses_and_is_retained':'noncanonical-pin',
 'test_oversized_configuration_refuses_before_parsing':'oversized-configuration',
 'test_partial_schema_refuses_and_is_never_recreated':'missing-table',
}
rows=[];corrupt_rows=[];authority_ids=set();version_count=0
for path in sorted(R.glob('*/runtime*/authority.db')):
 work=path.parent.parent;method=work.name
 original=Path(proof['rawScratch']['path'])/path.relative_to(R);fd=os.open(str(original)+'.owner',os.O_RDONLY|os.O_NOFOLLOW)
 try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 finally:os.close(fd)
 assert not any(path.with_name(path.name+s).exists()for s in ('-wal','-shm','-journal'))
 before=sha(path);db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
 try:
  assert db.execute('PRAGMA page_size').fetchone()==(1024,)
  meta=dict(db.execute('SELECT key,value FROM meta'));reg=dict(db.execute('SELECT key,value FROM reg_meta'))
  identity=meta['authority'];authority_ids.add(identity)
  assert all(db.execute('SELECT count(*) FROM '+table).fetchone()==(0,) for table in ('operations','claims','events','replay_keys'))
  schema={r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE name GLOB 'iosc_*'")}
  kind=corrupt.get(method)
  if method in {'test_cross_authority_runtime_and_deployment_cannot_supply_configuration','test_cross_authority_runtime_cannot_supply_fresh_run'} and path.parent.name=='runtime-other':
   assert not schema and 'io_service_configuration'not in reg;versions=0
  elif kind:
   if kind=='extra-index':assert 'iosc_unreviewed'in schema
   elif kind=='absent-tables':assert schema==set() and 'io_service_configuration'in reg
   elif kind=='legacy-pin':assert json.loads(db.execute('SELECT pin FROM iosc_versions').fetchone()[0])['profile']=='hms.pat.io-service-pin/0.1'
   elif kind=='metadata-anchor':
    store_meta=document(db.execute('SELECT record FROM iosc_meta').fetchone()[0]);assert store_meta['maxRevisions']==128
    assert reg['io_service_configuration']!='hms.pat.io-service-store/0.1|'+digest(b'HMS-PAT-IO-SERVICE-STORE-META-v0.1',store_meta)
   elif kind=='missing-head':assert db.execute('SELECT count(*) FROM iosc_heads').fetchone()==(0,)
   elif kind=='mutation-header':assert db.execute('SELECT request FROM iosc_mutations').fetchone()==(b'{}',)
   elif kind=='receipt-array':assert db.execute('SELECT receipt FROM iosc_versions').fetchone()==(b'[]',)
   elif kind=='noncanonical-pin':assert db.execute('SELECT pin FROM iosc_versions').fetchone()[0].endswith(b' ')
   elif kind=='oversized-configuration':assert db.execute('SELECT configuration FROM iosc_versions').fetchone()==(b' '*65537,)
   elif kind=='missing-table':assert 'iosc_heads'not in schema and 'io_service_configuration'in reg
   check=work/'corruption-check.json'
   if check.exists():
    value=read(check);assert value['before']==value['after'] and value['reset']is False
   corrupt_rows.append(dict(method=method,kind=kind,corruptionRetained=True))
   versions=None
  else:
   assert schema=={'iosc_meta','iosc_versions','iosc_heads','iosc_mutations'}
   store_meta=document(db.execute('SELECT record FROM iosc_meta WHERE singleton=1').fetchone()[0])
   assert store_meta['authorityId']==identity and store_meta['deployment']==reg['deployment']
   assert reg['io_service_configuration']=='hms.pat.io-service-store/0.1|'+digest(b'HMS-PAT-IO-SERVICE-STORE-META-v0.1',store_meta)
   records=db.execute('SELECT sequence,evaluator,revision,configuration,pin,receipt FROM iosc_versions ORDER BY sequence').fetchall()
   mutations={r[3]:r for r in db.execute('SELECT principal,operation_key,request,sequence FROM iosc_mutations')}
   assert len(records)==len(mutations)<=store_meta['maxRevisions']<=128
   assert [r[0]for r in records]==list(range(1,len(records)+1))
   previous={};heads={};last_time=store_meta['createdAtUnixMs']
   for sequence,evaluator,revision,c,p,r in records:
    config,pin,receipt=map(document,(c,p,r));principal,key,request_wire,seq=mutations[sequence];request=document(request_wire)
    assert seq==sequence and config['revision']==revision and config['evaluatorId']==evaluator
    assert revision==(previous[evaluator][0]+1 if evaluator in previous else 1)
    assert config['deployment']==reg['deployment'] and pin['authorityId']==identity and pin['profile']=='hms.pat.io-service-pin/0.2'
    config_id=digest(b'HMS-PAT-IO-AUTHORITY-SERVICE-CONFIG-v0.1',dict(authorityId=identity,configuration=config))
    assert pin['configurationDigest']==config_id and pin['configurationRevision']==revision
    assert pin['evaluatorId']==evaluator and pin['deployment']==config['deployment'] and pin['installationDigest']==config['installationDigest']
    assert request==dict(profile='hms.pat.io-service-configuration-mutation/0.1',authorityId=identity,deployment=reg['deployment'],principal=principal,operationKey=key,evaluatorId=evaluator,expectedRevision=revision-1,configurationDigest=config_id)
    timestamp=receipt['committedAtUnixMs'];assert type(timestamp)is int and timestamp>=last_time;last_time=timestamp
    assert receipt==dict(profile='hms.pat.io-service-configuration-receipt/0.1',authorityId=identity,deployment=reg['deployment'],evaluatorId=evaluator,configurationRevision=revision,sequence=sequence,configurationDigest=config_id,servicePinDigest=digest(b'HMS-PAT-IO-SERVICE-PIN-v0.1',pin),previousReceiptDigest=previous[evaluator][1]if evaluator in previous else None,principal=principal,operationKey=key,requestDigest=digest(b'HMS-PAT-IO-SERVICE-CONFIGURATION-MUTATION-v0.1',request),committedAtUnixMs=timestamp)
    previous[evaluator]=(revision,digest(b'HMS-PAT-IO-SERVICE-CONFIGURATION-RECEIPT-v0.1',receipt));heads[evaluator]=sequence
   assert dict(db.execute('SELECT evaluator,sequence FROM iosc_heads'))==heads
   versions=len(records);version_count+=versions
   if method=='test_temp_shadow_table_refuses_before_reading_it':
    check=read(work/'corruption-check.json');assert check['before']==check['after'] and check['reset']is False
   if 'IoAuthorityProcessTests' in read(A/'harness/targets.json')['targets'][0]:
    assert len(records)==1
    assert (work/'service-configuration.json').read_bytes()==records[0][3] and (work/'service-pin.json').read_bytes()==records[0][4]
    saved=read(work/'service-configuration-receipt.json');assert saved==dict(receipt=document(records[0][5]),receiptDigest=previous[evaluator][1])
    control=sqlite3.connect((work/'supervisor/attempts.db').as_uri()+'?mode=ro&immutable=1',uri=True)
    try:request_raw,record_raw=control.execute('SELECT request,record FROM qs_attempts').fetchone()
    finally:control.close()
    run,record=map(document,(request_raw,record_raw));assert run['context']['configurationDigest']==pin['configurationDigest']
    inputs=work/'supervisor'/record['attemptId']/'bundle/inputs';actors=read(inputs/'bindings.json')
    for role,actor in actors.items():
     descriptor=actor['descriptor'];instance=descriptor['binding']['instanceId']
     assert json.loads(db.execute('SELECT document FROM reg_bindings WHERE instance=?',(instance,)).fetchone()[0])==descriptor['binding']
     assert db.execute('SELECT session FROM reg_presence WHERE instance=?',(instance,)).fetchone()==(descriptor['endpointSession'],)
    image=work/'supervisor'/('code-'+run['supervisorIdentity'][7:])
    assert (image/'supervisor/io_service_store.py').read_bytes()==(A/'project/supervisor/io_service_store.py').read_bytes()
    checks=read(work/'inspection/supervisor-checks.json');assert checks['preLaunchInputsMatched'] and checks['exactReplayBeforeAndAfterReopen'] and checks['changedSameKeyRefused']
 finally:db.close()
 assert sha(path)==before
 boards=list(path.parent.glob('synthetic-io-board-*.db'));assert len(boards)==1;board=boards[0];boardpin=sha(board)
 db=sqlite3.connect(board.as_uri()+'?mode=ro&immutable=1',uri=True)
 try:
  assert db.execute('SELECT sum(activations),sum(completed),sum(canceled) FROM io_effects').fetchone()==(0,0,0)
  assert all(db.execute('SELECT count(*) FROM '+table).fetchone()==(0,)for table in ('io_owners','io_receipts','io_receipt_versions'))
 finally:db.close()
 assert sha(board)==boardpin
 rows.append(dict(path=path.relative_to(R).as_posix(),sha256=before,authorityId=identity,validatedVersions=versions,corruptFixture=kind,boardSha256=boardpin,effects=[0,0,0],claims=0,ownerFree=True))
assert len(authority_ids)==len(rows)
report=dict(scope='Independent source-free retained configuration/receipt/history joins and actual registry-to-run descriptor association; no promotion or physical qualification.',authorities=rows,validatedVersions=version_count,corruptFixtures=corrupt_rows,authorityCount=len(rows),allSourceAuthorityEffectsZero=True,allDatabasesUnchanged=True,qualificationPassed=False)
with(F/'authority-audit.json').open('x')as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k]for k in ('authorityCount','validatedVersions','allSourceAuthorityEffectsZero','allDatabasesUnchanged')}))
