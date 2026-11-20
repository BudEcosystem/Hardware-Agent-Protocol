"""Audit the original failed scope without opening interrupted case databases."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
STAGE=ROOT/'artifacts/implementation/pat-native-supervisor/implementation02';HARNESS=BASE/'harness01';ATTEMPT=HARNESS/'attempts/attempt01-accounting'
PIN='255b919194d150572c7b7876d941fb2e7d5866e36cdc119e91608da4b85ddc18'
HPIN='34bfe3567be9944a079d8c9809b62227e0967a59875c85a8bc84a6de53651b9a'
METHOD='test_actual_original_matrix_import_and_cold_vault_history'
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
assert result['status']=='failed' and result['currentPass'] is False and result['childState']=='exited' and result['exitCode']==1
assert result['counts']==dict(testsRun=1,failures=1,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert result['errors']==result['childErrors']==[] and result['rawScratchInventoryTerminal']
assert result['timeoutSeconds']==180 and result['limits']['scratchRetentionBytes']==268435456
assert result['projectInputCount']==291 and result['frozenPreparationInputCount']==295
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
assert len(native['scans'])==2 and sorted(v['calls'] for v in native['scans'])==[1,2400]
for label in ('compiler','driver'):assert read(ATTEMPT/(label+'-before.json'))==read(ATTEMPT/(label+'-after.json'))
assert len(read(ATTEMPT/'sqlite-connections.json'))==4
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
    assert len(locks)==55
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
    assert len(saved)==1 and saved[0][2] is None
    request,record=map(json.loads,saved[0][:2]);archive=read(work/'worker-archive.json')
    assert archive['record']==record and record['state']=='archived' and record['reason']=='SUPERVISOR_DEADLINE'
    report=record['archive'];assert report['supervisorReason']=='SUPERVISOR_DEADLINE' and report['exitCode']==-15
    assert report['transportComplete'] is False and report['unresolvedEffects'] is None and report['semanticQualificationVerified'] is False
    assert report['evidenceIntegrity'] is report['returnDigest'] is None
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
    worker=work/'supervisor'/record['attemptId'];output=worker/'output';matrix=read(output/'matrix.json')
    scan_rows={value['path']:value for value in native['scans']}
    assert scan_rows[str(work/'supervisor')]==dict(path=str(work/'supervisor'),calls=1,maxFiles=262144,maxBytes=268435456)
    assert scan_rows[str(worker)]==dict(path=str(worker),calls=2400,maxFiles=8192,maxBytes=67108864)
    assert [case['caseId'] for case in matrix['cases']]==request['bundleHeader']['caseIds']
    cases=sorted(output.glob('case-*'));manifests=sorted(output.glob('case-*/manifest.json'))
    assert len(cases)==30 and len(manifests)==29
    for i,path in enumerate(manifests):assert read(path)['caseId']==matrix['cases'][i]['caseId']
    assert matrix['cases'][29]['definition']['scenario']=='shared_resources'
    assert not (output/'result.json').exists() and not (worker/'worker-return.json').exists()
    phases=read(work/'phase-times.json');assert all(not row['phase'].startswith('import_') for row in phases)
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
    assert consumer==pins['consumer']==meta['consumerIdentity']=='sha256:d71915ba422d711245669bf2e076378527f276d8e716b2be772ec0379dbbb76d'

    # Independently derive observations; never import the observer or project code.
    accounting=read(ATTEMPT/'worker-accounting.json')
    launches=read(ATTEMPT/'worker-accounting-launch-audit.json')
    assert len(launches)==1 and launches[0]['testId']==targets[0]==accounting['testId']
    assert accounting['profile']=='hms.worker-resource-observation/1' and accounting['errors']==[]
    observed=accounting['launch'];terminal=observed['terminal']
    assert observed['launchFailure'] is None and observed['pid']==record['pid']
    assert observed['argv']==launches[0]['argv'] and launches[0]['cwd']==str(image)
    assert observed['argv'][:4]==[read(ATTEMPT/'child-runtime.json')['executable'],'-I','-B',str(image/'supervisor/worker_entry.py')]
    assert terminal['observedBy']=='original-poll' and terminal['returnCode']==report['exitCode']==-15
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
summary=dict(stageStatus='verified-progress-actual-scope-failed',sourceIndexSha256=PIN,harnessIndexSha256=HPIN,
    resultSha256=sha(ATTEMPT/'result.json'),observerControls=15,compositionControls=6,previousNativeControlsReferenced=True,productionCandidateChanged=False,publicRuntimeChanged=False,
    actualScopePassed=False,originalAttemptId=record['attemptId'],supervisorReason='SUPERVISOR_DEADLINE',
    requestedCases=30,caseDirectories=30,caseManifests=29,incompleteScenario='shared_resources',
    originalMaxWallMs=60000,transportComplete=False,workerUnresolvedEffects=None,importReached=False,
    importIntents=0,publications=0,evidenceManifests=0,sourceApplicationInvocations=0,
    readonlySourceDatabases=hashes,workerCaseDatabasesOpened=0,ownerAndWriterLocks=locks,
    sourceAndOriginsAndRetainedBytesVerified=True,producerImageFiles=265,legacyIdentity=legacy,vaultIdentity=vault_id,consumerIdentity=consumer,
    sourceIdentitiesIndependentlyRecomputed=True,rawPath=str(raw),rawFiles=len(rows),rawBytes=result['scratchRetainedBytes'],
    phaseTimes=phases,observedSpawnToSettledMs=phase_map['worker_producer_settled']-phase_map['worker_spawned'],
    nativeImageReceiptVerified=True,nativeOriginReopenedAfterChildExit=False,nativeRetention=native,workerResourceObservation=observation,
    timeoutRootCauseEstablished=False,wholeWorkerPerformanceQualified=False,catalogIntegrated=False,
    physicalObjectiveVerified=False,aggregateDiskQuotaEnforced=False,independentReview=False,goalStatus='active')
with (BASE/'RESULTS.json').open('x') as stream:json.dump(summary,stream,indent=2);stream.write('\n')
print(json.dumps({key:summary[key] for key in ('stageStatus','observerControls','compositionControls','caseManifests','importReached','rawFiles','workerResourceObservation','goalStatus')}))
