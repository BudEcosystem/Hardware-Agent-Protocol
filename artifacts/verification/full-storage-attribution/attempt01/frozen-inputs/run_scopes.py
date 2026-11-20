"""Freeze one observation attempt, bound/reap children, stop on first failure."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PRIOR=ROOT/'artifacts/implementation/inline-hierarchical-store'
ATTEMPT=HERE/'attempt01'
ENV={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'}


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def read(path):return json.loads(path.read_text())
def save(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def baseline():
    path=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(path)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    rows=read(path)['files'];assert len(rows)==244
    assert all(digest(ROOT/row['path'])==row['sha256'] for row in rows)
    return dict(receiptSha256=digest(path),filesExact=len(rows))


def prior():
    assert digest(PRIOR/'index.json')=='a820ce8adda0d8e3dbb1827f2b47c48f94c7969cccc299fbd10e36fbce54f982'
    index=read(PRIOR/'index.json');assert len(index['files'])==340
    assert all(digest(PRIOR/row['path'])==row['sha256'] for row in index['files'])
    assert len(index['symlinks'])==1
    assert all((PRIOR/row['path']).is_symlink() and os.readlink(PRIOR/row['path'])==row['target'] for row in index['symlinks'])
    result=read(PRIOR/'RESULTS.json');assert result['focusedChecks']==192 and not result['writerComplete']
    return dict(indexSha256=digest(PRIOR/'index.json'),filesExact=340,symlinksExact=1,
                priorFocusedChecks=192,priorFullReplayPassed=False)


def limits(cpu):
    for key,value in [(resource.RLIMIT_CPU,cpu),(resource.RLIMIT_AS,512*1024**2),
        (resource.RLIMIT_FSIZE,16*1024**2),(resource.RLIMIT_NOFILE,128),(resource.RLIMIT_CORE,0)]:
        resource.setrlimit(key,(value,value))


def run(name,argv,env,wall=60,cpu=40):
    work=ATTEMPT/name;work.mkdir(mode=0o700)
    save(work/'intent.json',dict(argv=argv,environment=env,cwd=str(work),wallSeconds=wall,cpuSeconds=cpu,
        addressSpaceBytes=512*1024**2,fileBytes=16*1024**2,descriptors=128))
    started=time.monotonic();timed_out=False
    with (work/'stdout.txt').open('xb') as out,(work/'stderr.txt').open('xb') as err:
        proc=subprocess.Popen(argv,cwd=work,env=env,stdout=out,stderr=err,
            start_new_session=True,preexec_fn=lambda:limits(cpu))
        save(work/'started.json',dict(pid=proc.pid,processGroup=proc.pid,unix=time.time()))
        while True:
            pid,status,usage=os.wait4(proc.pid,os.WNOHANG)
            if pid:break
            if time.monotonic()-started>=wall:
                timed_out=True;os.killpg(proc.pid,signal.SIGKILL)
                pid,status,usage=os.wait4(proc.pid,0);break
            time.sleep(.1)
        proc.returncode=os.waitstatus_to_exitcode(status)
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        out.flush();err.flush();os.fsync(out.fileno());os.fsync(err.fileno())
    result=dict(returnCode=proc.returncode,timedOut=timed_out,reaped=True,
        elapsedSeconds=time.monotonic()-started,cpuSeconds=usage.ru_utime+usage.ru_stime,peakRSSKiB=usage.ru_maxrss)
    save(work/'result.json',result)
    if proc.returncode or timed_out:raise RuntimeError(name+' failed or inconclusive; matrix stopped')
    return work


def observations(work,complete):
    path=work/'attribution.jsonl'
    if not path.exists():return dict(frames=0,complete=False,missing=True)
    assert path.stat().st_size<=12*1024**2
    lines=path.read_bytes().splitlines(keepends=True);frames=[];tail=0
    for number,line in enumerate(lines):
        if not line.endswith(b'\n'):
            assert number==len(lines)-1;tail=len(line);break
        assert len(line)<=65536
        frame=json.loads(line);assert frame['sequence']==len(frames)
        assert frame['schema']=='hms.storage-attribution/0.1' and not frame['nativeInternalFunctionsMeasured']
        assert frame['stackDepth']==0 and not frame['errors'] and frame['observer']['dropped']==0
        assert frame['rootCompleted']<=frame['rootStarted']<=frame['rootCompleted']+1
        for row in frame['rows']:
            assert len(row)==8 and all(type(value) is int for value in row)
            assert 0<=row[0]<len(frame['phases']) and 0<=row[1]<len(frame['labels'])
            assert 0<=row[3]<=row[2] and row[4]>=0 and row[5]>=0
        if frames:
            last=frames[-1]
            assert frame['elapsedNs']>=last['elapsedNs'] and frame['ownerSequence']>=last['ownerSequence']
            assert frame['labels']==last['labels'] and frame['phases']==last['phases']
            prior_rows={(row[0],row[1]):row for row in last['rows']}
            now_rows={(row[0],row[1]):row for row in frame['rows']}
            assert set(prior_rows)<=set(now_rows)
            assert all(all(now_rows[key][index]>=row[index] for index in range(2,6)) for key,row in prior_rows.items())
            if frame['ownerSequence']==last['ownerSequence'] and frame['callbacks'] is not None and last['callbacks'] is not None:
                assert all(frame['callbacks'][key]>=value for key,value in last['callbacks'].items())
        frames.append(frame)
    assert frames and frames[0]['event']=='initial'
    if complete:
        observer=read(work/'observer.json')
        assert frames[-1]['event']=='final' and not tail
        assert not observer['errors'] and observer['dropped']==observer['residualStackDepth']==0
        assert observer['bytesWritten']==path.stat().st_size
    return dict(frames=len(frames),bytes=path.stat().st_size,partialTailBytes=tail,complete=complete,
        lastSequence=frames[-1]['sequence'],lastElapsedNs=frames[-1]['elapsedNs'],lastEvent=frames[-1]['event'],
        lastRootStarted=frames[-1]['rootStarted'],lastRootCompleted=frames[-1]['rootCompleted'],
        lastOwnerSequence=frames[-1]['ownerSequence'],nativeInternalFunctionsMeasured=False)


def main():
    os.umask(0o077);assert not ATTEMPT.exists()
    before=baseline();previous=prior()
    host=read(PRIOR/'host-observation.json')
    assert all(digest(Path(row['path']))==row['sha256'] for row in host['files'])
    ATTEMPT.mkdir(mode=0o700);frozen=ATTEMPT/'frozen-inputs';frozen.mkdir(mode=0o700)
    sources=[(HERE/name,frozen/name) for name in ['PLAN.md','attribution.py','run_scopes.py']]
    sources += [(PRIOR/name,frozen/name) for name in ['candidate.py','hierarchical_store.py','chunk_store_base.py','native.py','fixed_block.py','mount_identity.py','controls.py','diagnostic.py']]
    sources += [(PRIOR/'attempt01/frozen-inputs/dataset.json',frozen/'dataset.json')]
    sources += [(PRIOR/'attempt01'/name,ATTEMPT/name) for name in ['hierarchical-store.so','mount-probe.so']]
    rows=[]
    for source,target in sources:
        with target.open('xb') as stream:stream.write(source.read_bytes());stream.flush();os.fsync(stream.fileno())
        rows.append(dict(path=str(source.relative_to(ROOT)),frozen=str(target.relative_to(ATTEMPT)),sha256=digest(target)))
    dataset=read(frozen/'dataset.json');source_root=Path(dataset['sourceRoot'])
    assert len(dataset['files'])==4270 and len(dataset['directories'])==169
    assert sum(row['bytes'] for row in dataset['files'])==35508922
    assert all(digest(source_root/row['path'])==row['sha256'] for row in dataset['files'])
    library_hash=digest(ATTEMPT/'hierarchical-store.so');mount_hash=digest(ATTEMPT/'mount-probe.so')
    assert library_hash=='6b48f9b9c9a829a8c5c71236c309e7e78f55f096e7c627542a739095ff57ec7a'
    assert mount_hash=='450f1d2bfd948ca0f7292884e753ccc11fd9f82dc285e150cf535864b75572bd'
    save(ATTEMPT/'inputs.json',dict(files=rows,prior=previous,baselineBefore=before,host=host,
        datasetSha256=digest(frozen/'dataset.json'),librarySha256=library_hash,mountLibrarySha256=mount_hash))
    env={**ENV,'HMS_LIBRARY':str(ATTEMPT/'hierarchical-store.so'),'HMS_LIBRARY_SHA256':library_hash,
        'HMS_MOUNT_LIBRARY':str(ATTEMPT/'mount-probe.so'),'HMS_MOUNT_LIBRARY_SHA256':mount_hash}
    report=dict(status='incomplete',scopes={},publicRuntimeChanged=False,productionSourcesChanged=False,
        geometryChanged=False,checksDisabled=False,durabilityBarriersDisabled=False,
        nativeInternalFunctionsMeasured=False,instrumentationIntrusive=True,serviceStorageQualified=False)
    try:
        outputs={}
        for name,argv in [('comparison-original',[sys.executable,'-B',str(frozen/'diagnostic.py'),'coarse']),
                          ('comparison-observed',[sys.executable,'-B',str(frozen/'attribution.py'),'screen'])]:
            work=run(name,argv,env)
            value=read(work/'diagnostic.json');assert value['status']=='passed' and len(value['steps'])==426
            assert read(work/'stdout.txt')=={key:item for key,item in value.items() if key not in ['spans','steps','expectedFiles','backingHashes']}
            outputs[name]=value
            report['scopes'][name]=dict(receiptSha256=digest(work/'diagnostic.json'),cpuSeconds=value['cpuSeconds'],elapsedSeconds=value['elapsedSeconds'])
            if name=='comparison-observed':report['scopes'][name]['observations']=observations(work,True)
        left,right=outputs.values()
        for name in ['expectedFiles','firstOwnerCallbacks','coldOwnerCallbacks','backingHashes','providerSyncCalls']:assert left[name]==right[name]
        for a,b in zip(left['steps'],right['steps']):
            assert {key:value for key,value in a.items() if key not in ('wallNs','cpuNs')}=={key:value for key,value in b.items() if key not in ('wallNs','cpuNs')}
        report['screenEquivalent']=True
        print(json.dumps(dict(scope='comparison',status='passed',scopes=report['scopes'])),flush=True)
        work=run('replay_write',[sys.executable,'-B',str(frozen/'attribution.py'),'replay_write'],env,180,120)
        value=read(work/'checks.json');assert value==read(work/'stdout.txt') and value['status']=='passed'
        report['scopes']['replay_write']=dict(receiptSha256=digest(work/'checks.json'),checks=len(value['checks']),observations=observations(work,True))
        work=run('replay_read',[sys.executable,'-B',str(frozen/'controls.py'),'replay_read'],{**env,'HMS_REPLAY_WRITER':str(ATTEMPT/'replay_write')},180,120)
        value=read(work/'checks.json');assert value==read(work/'stdout.txt') and value['status']=='passed'
        report['scopes']['replay_read']=dict(receiptSha256=digest(work/'checks.json'),checks=len(value['checks']))
        report['status']='passed'
    except BaseException as error:
        report['status']='failed-or-inconclusive';report['error']=type(error).__name__+': '+str(error)
    finally:
        for scope in ['comparison-observed','replay_write']:
            work=ATTEMPT/scope
            if (work/'attribution.jsonl').exists() and scope not in report['scopes']:
                try:report.setdefault('partialObservations',{})[scope]=observations(work,False)
                except BaseException as error:
                    report.setdefault('observationInspectionErrors',{})[scope]=type(error).__name__+': '+str(error)
                    report['status']='failed-or-inconclusive'
        assert all(digest(ROOT/row['path'])==digest(ATTEMPT/row['frozen'])==row['sha256'] for row in rows)
        assert all(digest(Path(row['path']))==row['sha256'] for row in host['files'])
        assert all(digest(source_root/row['path'])==row['sha256'] for row in dataset['files'])
        report['baselineAfter']=baseline();report['inputsStable']=True
        files=[path for path in HERE.rglob('*') if path.is_file()]
        assert all(path.stat().st_size<=16*1024**2 for path in files)
        report['allocatedBytes']=sum(path.stat().st_blocks*512 for path in files);assert report['allocatedBytes']<1024**3
        save(ATTEMPT/'RESULTS.json',report)
    print(json.dumps(report,sort_keys=True),flush=True)
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
