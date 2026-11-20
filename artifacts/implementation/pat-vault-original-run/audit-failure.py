"""Audit retained failed scopes and the incomplete original worker without repair."""
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
PINS={'implementation01':'14e33c595526a7a7d626d635dcff7327fef65e9a94b28c85b7d43a109b212414',
      'implementation02':'4a1f5b97cb29e897fc865ca5dcf46397bfdec6c4154a302dfdac1b546e66c4f4',
      'harness01':'dcf60daa4c4e39426c51aa3ac2a1679799a37a8f3b0ba91d07f682b9017f2ea3',
      'harness02':'fb7c98f67057baaec11152acff67d6eaac71eacb99e56b0df69579be837f83cf',
      'harness03':'7e85f2300c1346c34caaa377416eae197fa88e4b3c6ad37e5e10928823eac532'}
METHOD='test_actual_original_matrix_import_and_cold_vault_history'
def read(path): return json.loads(path.read_bytes())
def sha(path):
    assert path.is_file() and not path.is_symlink() and path.stat().st_size<=16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def wire_hash(body): return 'sha256:'+hashlib.sha256(body).hexdigest()
def canonical(value):
    def check(item):
        if type(item)is dict:
            assert all(type(k)is str and k.isascii() for k in item)
            for v in item.values(): check(v)
        elif type(item)is list:
            for v in item: check(v)
        else: assert type(item)in(str,int,bool,type(None)) and (type(item)is not int or abs(item)<=2**53-1)
    check(value); return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(domain,value): return wire_hash(domain+b'\0'+canonical(value))
def verify(path,row): assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
def inventory(folder):
    rows=[]
    for path in sorted(folder.rglob('*')):
        assert not path.is_symlink()
        if path.is_file(): rows.append(dict(path=path.relative_to(folder).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    return rows
def write(path,value):
    with path.open('x') as stream: json.dump(value,stream,indent=2); stream.write('\n')

for name,pin in PINS.items():
    folder=BASE/name; assert sha(folder/'index.json')==pin
    for row in read(folder/'index.json')['files']: verify((ROOT if name.startswith('implementation') else folder)/row['path'],row)
projects=[]
for name in ('implementation01','implementation02'):
    folder=BASE/name/'project'; projects.append({p.relative_to(folder).as_posix():sha(p) for p in folder.rglob('*') if p.is_file()})
assert len(projects[0])==len(projects[1])==286
assert {name for name in projects[0] if projects[0][name]!=projects[1][name]}=={'tests/test_vault_original_run.py'}
trees=[ast.parse((BASE/name/'project/tests/test_vault_original_run.py').read_bytes()) for name in ('implementation01','implementation02')]
assert len({ast.dump(next(n for n in tree.body if isinstance(n,ast.ClassDef))) for tree in trees})==1
baseline=read(BASE/'implementation02/baseline-inputs.json')['files']; assert len(baseline)==285
for row in baseline: verify(BASE/'implementation02/project'/row['path'],row)
summaries=[]
for number in (1,2,3):
    harness=BASE/('harness%02d'%number); attempt=harness/'attempts/attempt01-actual'
    result=read(attempt/'result.json')
    assert result['status']=='failed' and result['currentPass'] is False and result['childState']=='exited' and result['exitCode']==1
    assert result['timeoutSeconds']==180 and result['limits']['singleAcquiredFileBytes']==16777216
    assert result['limits']['scratchRetentionBytes']==268435456 and result['limits']['retainedLogBytes']==8388608
    assert result['projectInputCount']==286 and result['externalInputCount']==159
    for label,prefix in (('inputs',attempt/'project'),('frozen',ROOT),('harness',attempt/'harness')):
        before=read(attempt/(label+'-before.json')); assert before==read(attempt/(label+'-after.json'))
        for row in before: verify(prefix/row['path'],row)
    external=read(attempt/'external-before.json'); assert external==read(attempt/'external-after.json')
    for row in external['files']: verify(Path(row['resolvedPath']),row)
    raw=Path(result['scratchPath']); original=read(attempt/'raw-scratch-before.json')['identity']; info=raw.lstat()
    assert (info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode))==(original['device'],original['inode'],original['uid'],original['mode'])
    rows=inventory(raw); assert rows==inventory(attempt/'scratch')==read(attempt/'scratch-index.json')
    assert sum(r['bytes'] for r in rows)==result['scratchRetainedBytes']<=268435456 and len(rows)<=8192
    origins=read(attempt/'imports.json'); assert origins['violations']==[]
    assert origins['prohibitedAttempts']==(['sqlite3.connect'] if number==2 else [])
    for row in origins['records']:
        if 'sha256' in row: assert sha(Path(row['origin']))==row['sha256']
    connections=read(attempt/'sqlite-connections.json'); assert len(connections)=={1:0,2:3,3:4}[number]
    proof=read(attempt/'writer-quiescence.json')
    if number<3: assert proof['records']==[]
    if number==1:
        assert result['counts'] is None and rows==[]
        assert 'ModuleNotFoundError' in (attempt/'output.log').read_text()
    else:
        assert result['counts']==dict(testsRun=1,failures=int(number==3),errors=int(number==2),skips=0,expectedFailures=0,unexpectedSuccesses=0)
        for label in ('compiler','driver'): assert read(attempt/(label+'-before.json'))==read(attempt/(label+'-after.json'))
    summaries.append(dict(scope=harness.name,status='failed',resultSha256=sha(attempt/'result.json'),
        counts=result['counts'],elapsedSeconds=result['elapsedSeconds'],rawPath=str(raw),
        rawFiles=len(rows),rawBytes=result['scratchRetainedBytes'],sqliteOpens=len(connections),sourceAndCopyBytesVerified=True))

attempt=BASE/'harness03/attempts/attempt01-actual'; result=read(attempt/'result.json')
raw=Path(result['scratchPath']); work=raw/METHOD; copied=attempt/'scratch'/METHOD
locks=[]; held=[]; dbs=[]; hashes={}
try:
    for path in sorted(work.rglob('*')):
        if path.is_file() and (path.name.endswith('.owner') or path.name=='writer.lease'):
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK); held.append(fd); info=os.fstat(fd)
            assert stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1 and info.st_size==0
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            locks.append(dict(path=path.relative_to(work).as_posix(),device=str(info.st_dev),inode=str(info.st_ino)))
    assert len(locks)==57
    board=next((work/'runtime').glob('synthetic-io-board-*.db'))
    paths=[work/'runtime/authority.db',work/'vault/evidence.db',work/'supervisor/attempts.db',board]
    for path in paths:
        assert not any(os.path.lexists(str(path)+suffix) for suffix in ('-journal','-wal','-shm'))
        hashes[str(path)]=sha(path); assert sha(copied/path.relative_to(work))==hashes[str(path)]
        db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True,isolation_level=None)
        db.execute('PRAGMA query_only=ON'); dbs.append(db)
    authority,vault,supervisor,board_db=dbs
    rows=supervisor.execute('SELECT request,record,return_bytes FROM qs_attempts LIMIT 2').fetchall(); assert len(rows)==1
    request=json.loads(rows[0][0]); record=json.loads(rows[0][1]); assert rows[0][2] is None
    assert record['state']=='archived' and record['reason']=='SUPERVISOR_DEADLINE'
    archive=record['archive']; assert archive['exitCode']==-15 and archive['transportComplete'] is False
    assert archive['unresolvedEffects'] is None and archive['semanticQualificationVerified'] is False
    assert archive['evidenceIntegrity'] is None and archive['returnDigest'] is None
    assert request['groupLimits']['maxWallMs']==60000 and len(request['bundleHeader']['caseIds'])==30
    writer=next(row for row in locks if row['path'].endswith('/'+record['attemptId']+'/writer.lease'))
    assert record['lease']=={name:writer[name] for name in ('device','inode')}
    handoff=json.loads(authority.execute('SELECT receipt FROM iose_handoffs').fetchone()[0])
    reservation=json.loads(authority.execute('SELECT receipt FROM iosr_runs').fetchone()[0])
    assert handoff['attemptId']==record['attemptId'] and handoff['requestDigest']==record['requestDigest']
    assert handoff['reservationDigest']==digest(b'HMS-PAT-IO-SERVICE-RUN-RESERVATION-v0.1',reservation)
    assert handoff['supervisorAuthorityId']==supervisor.execute('SELECT authority FROM qs_meta').fetchone()[0]
    assert authority.execute('SELECT count(*) FROM iosr_runs').fetchone()[0]==authority.execute('SELECT count(*) FROM iose_handoffs').fetchone()[0]==1
    assert [row[0] for row in authority.execute('SELECT revision FROM iosc_versions')]==[1]
    counts={name:authority.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('evi_intents','evi_publications','operations','claims')}
    assert set(counts.values())=={0}
    assert all(vault.execute('SELECT count(*) FROM '+name).fetchone()[0]==0 for name in ('ev_manifests','ev_documents','ev_bodies'))
    meta=json.loads(authority.execute('SELECT record FROM evi_meta').fetchone()[0])
    assert json.loads(vault.execute('SELECT record FROM ev_meta').fetchone()[0])==meta['vault']
    assert meta['authorityId']==meta['vault']['authorityId']==authority.execute("SELECT value FROM meta WHERE key='authority'").fetchone()[0]
    assert authority.execute("SELECT value FROM reg_meta WHERE key='vault_evidence_import'").fetchone()[0]=='hms.pat.vault-import/0.1|'+digest(b'HMS-PAT-VAULT-IMPORT-MOUNT-v0.1',meta)
    assert all(row[1:]==(0,0,0) for row in board_db.execute('SELECT instance,activations,completed,canceled FROM io_effects'))
    assert board_db.execute('SELECT count(*) FROM io_owners').fetchone()[0]==0
    producer=work/'supervisor'/record['attemptId']; output=producer/'output'
    matrix=read(output/'matrix.json'); assert [case['caseId'] for case in matrix['cases']]==request['bundleHeader']['caseIds']
    case_dirs=sorted(p for p in output.glob('case-*') if p.is_dir())
    manifests=sorted(output.glob('case-*/manifest.json'))
    assert len(case_dirs)==30 and len(manifests)==29
    for i,path in enumerate(manifests): assert read(path)['caseId']==matrix['cases'][i]['caseId']
    assert not (output/'result.json').exists() and not (producer/'worker-return.json').exists()
    assert matrix['cases'][-1]['kind']=='resource_challenge' and matrix['cases'][-1]['definition']['scenario']=='shared_resources'
    phases=read(work/'phase-times.json'); assert all(not row['phase'].startswith('import_') for row in phases)
    phase_map={row['phase']:row['elapsedMs'] for row in phases}
    assert phase_map['worker_spawned']<phase_map['worker_producer_settled']<=phase_map['worker_complete']
    image=work/'supervisor'/('code-'+request['supervisorIdentity'][7:]); image_paths=sorted(p for p in image.rglob('*') if p.is_file())
    assert len(image_paths)==262
    external=read(attempt/'external-before.json')['files']; source_rows=[]
    for path in image_paths:
        relative=path.relative_to(image).as_posix(); value=sha(path)
        if relative.startswith('dependencies/'):
            matches=[row for row in external if row['resolvedPath'].endswith('/'+relative[len('dependencies/'):])]
            assert len(matches)==1 and matches[0]['sha256']==value
        else: assert sha(attempt/'project'/relative)==value
        source_rows.append(dict(path=relative,bytes=path.stat().st_size,sha256=value))
    for name in ('__init__.py','contracts.py','archive.py','reducer.py','store.py'):
        path=attempt/'project/evidence'/name; source_rows.append(dict(path='evidence/'+name,bytes=path.stat().st_size,sha256=sha(path)))
    legacy=digest(b'HMS-PAT-IO-EVIDENCE-CONSUMER-v0.1',sorted(source_rows,key=lambda row:row['path']))
    def sources(package,names):
        return [dict(path=package+'/'+name,bytes=(attempt/'project'/package/name).stat().st_size,sha256=sha(attempt/'project'/package/name)) for name in names]
    vault_id=digest(b'HMS-PAT-EVIDENCE-VAULT-IMPLEMENTATION-v0.1',dict(legacyIdentity=legacy,sources=sources('evidence_vault',('__init__.py','contracts.py','connection.py','store.py'))))
    consumer_id=digest(b'HMS-PAT-VAULT-IMPORT-IMPLEMENTATION-v0.1',dict(vaultIdentity=vault_id,sources=sources('evidence_authority',('__init__.py','contracts.py','store.py'))))
    assert vault_id==meta['vault']['implementationDigest']=='sha256:a7b12404007cfabb919c5eee9c3db3d3b33c39d6322c7d37e82e1020100910b5'
    assert consumer_id==meta['consumerIdentity']=='sha256:0e7ff6440fdb93e941ff4b5b0f2f275558f67f1e63a3c719c66756f81b7971d5'
    for db in reversed(dbs): db.close()
    dbs=[]
    for path,expected in hashes.items(): assert sha(Path(path))==expected
    assert inventory(raw)==read(attempt/'scratch-index.json')==inventory(attempt/'scratch')
finally:
    for db in reversed(dbs): db.close()
    for fd in reversed(held): os.close(fd)

report=dict(stageStatus='verified-progress-actual-scope-failed',sourcePins=PINS,productionChanged=False,
    retainedScopes=summaries,originalAttemptId=record['attemptId'],supervisorReason='SUPERVISOR_DEADLINE',
    originalMaxWallMs=60000,requestedCases=30,caseDirectories=30,caseManifests=29,
    lastIncompleteCaseKind=matrix['cases'][-1]['kind'],lastIncompleteScenario=matrix['cases'][-1]['definition']['scenario'],
    completeReturnPresent=False,transportComplete=False,workerUnresolvedEffects=None,
    importReached=False,importIntents=0,evidenceManifests=0,publications=0,sourceApplicationInvocations=0,
    actualOriginalRunProfileVerified=False,readonlyDatabases=len(hashes),ownerAndWriterLocks=locks,
    unchangedDatabaseHashes=hashes,producerImageFiles=262,legacyConsumerIdentity=legacy,
    vaultIdentity=vault_id,consumerIdentity=consumer_id,sourceIdentitiesIndependentlyRecomputed=True,
    phaseTimes=phases,observedSpawnToSettledMs=phase_map['worker_producer_settled']-phase_map['worker_spawned'],
    timeoutRootCauseEstablished=False,physicalObjectiveVerified=False,aggregateDiskQuotaEnforced=False,
    catalogIntegrated=False,goalStatus='active')
write(BASE/'RESULTS.json',report)
print(json.dumps({key:report[key] for key in ('stageStatus','requestedCases','caseManifests','importReached','readonlyDatabases','goalStatus')}))
