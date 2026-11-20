"""One bounded compact-bitmap candidate attempt; stop and preserve first failure."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ATTEMPT=HERE/'attempt01'
PRIOR=ROOT/'artifacts/implementation/inline-hierarchical-store'
ATTRIBUTION=ROOT/'artifacts/verification/full-storage-attribution'
ENV={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'}
SCOPES=['hierarchy','data','namespace','bounds','recovery','corruption','orphan_recovery','owner_loss','fault']
TARGETS=['codec','edges','corruption','interruption']
NATIVE_HASH='6b48f9b9c9a829a8c5c71236c309e7e78f55f096e7c627542a739095ff57ec7a'
MOUNT_HASH='450f1d2bfd948ca0f7292884e753ccc11fd9f82dc285e150cf535864b75572bd'


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


def sealed(directory,wanted):
    assert digest(directory/'index.json')==wanted
    value=read(directory/'index.json');rows=value['files'];links=value.get('symlinks',[])
    assert all(not (directory/r['path']).is_symlink() and stat.S_ISREG((directory/r['path']).lstat().st_mode)
               and (directory/r['path']).stat().st_size==r['bytes'] and digest(directory/r['path'])==r['sha256'] for r in rows)
    assert all((directory/r['path']).is_symlink() and os.readlink(directory/r['path'])==r['target'] for r in links)
    return dict(indexSha256=wanted,filesExact=len(rows),bytesExact=sum(r['bytes'] for r in rows),symlinksExact=links)


def limits(cpu):
    for key,amount in [(resource.RLIMIT_CPU,cpu),(resource.RLIMIT_AS,512*1024**2),
            (resource.RLIMIT_FSIZE,16*1024**2),(resource.RLIMIT_NOFILE,128),(resource.RLIMIT_CORE,0)]:
        resource.setrlimit(key,(amount,amount))


def group_members(pgid):
    members=[]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():continue
        try:
            fields=(entry/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[2])==pgid:members.append(dict(pid=int(entry.name),state=fields[0]))
        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
    return members


def child_exited_unreaped(process):
    # Do not call Popen.poll/wait: the owned leader anchors numeric group identity.
    return os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT) is not None


def finish_owned_group(process):
    exited=child_exited_unreaped(process)  # Raises if ownership/waitability was lost; never signal then.
    before=[m for m in group_members(process.pid) if m['pid']!=process.pid]
    if not exited or before:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    deadline=time.monotonic()+2
    while [m for m in group_members(process.pid) if m['pid']!=process.pid] and time.monotonic()<deadline:
        time.sleep(.02)
    pid,status,usage=os.wait4(process.pid,0)  # Final signal precedes reap; retain CPU/RSS usage.
    assert pid==process.pid
    process.returncode=os.waitstatus_to_exitcode(status)
    return usage,before,group_members(process.pid)  # Read-only audit after reap; no fallback signal.


def run(name,argv,env,wall=60,cpu=40):
    work=ATTEMPT/name;work.mkdir(mode=0o700)
    save(work/'intent.json',dict(argv=argv,environment=env,cwd=str(work),wallSeconds=wall,cpuSeconds=cpu,
         addressSpaceBytes=512*1024**2,fileBytes=16*1024**2,descriptors=128))
    started=time.monotonic();timed_out=False;monitor_error=None;cleanup_error=None;proc=None
    usage=None;leftovers=[];remaining=[];reaped=False
    # Cover the Popen assignment window. The child restores the inherited mask before exec.
    blocked={signal.SIGTERM,signal.SIGINT}
    def child_limits():
        limits(cpu);signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask)
    with (work/'stdout.txt').open('xb') as out,(work/'stderr.txt').open('xb') as err:
        prior_mask=signal.pthread_sigmask(signal.SIG_BLOCK,blocked)
        try:
            proc=subprocess.Popen(argv,cwd=work,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                                  start_new_session=True,preexec_fn=child_limits)
            save(work/'started.json',dict(pid=proc.pid,processGroup=proc.pid,unix=time.time()))
            signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask)
            while not child_exited_unreaped(proc):
                if time.monotonic()-started>=wall:
                    timed_out=True;break  # Cleanup signals while the leader remains anchored.
                time.sleep(.1)
        except BaseException as error:
            monitor_error=error
        finally:
            signal.pthread_sigmask(signal.SIG_BLOCK,blocked)
            if proc is not None:
                try:
                    usage,leftovers,remaining=finish_owned_group(proc);reaped=True
                except BaseException as error:
                    cleanup_error=error  # No unanchored retry or fallback signal.
            try:
                out.flush();err.flush();os.fsync(out.fileno());os.fsync(err.fileno())
                result=dict(returnCode=None if proc is None else proc.returncode,timedOut=timed_out,reaped=reaped,
                            elapsedSeconds=time.monotonic()-started,
                            cpuSeconds=None if usage is None else usage.ru_utime+usage.ru_stime,
                            peakRSSKiB=None if usage is None else usage.ru_maxrss,
                            groupSignalAnchor='waitable unreaped owned leader; no signals after wait4',
                            leftoverMembersBeforeReap=leftovers,groupMembersAfterCleanup=remaining,
                            groupAbsentAfterCleanup=reaped and not remaining,
                            monitorError=None if monitor_error is None else f'{type(monitor_error).__name__}: {monitor_error}',
                            cleanupError=None if cleanup_error is None else f'{type(cleanup_error).__name__}: {cleanup_error}')
                save(work/'result.json',result)
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask)
    if cleanup_error is not None:raise cleanup_error
    if monitor_error is not None:raise monitor_error
    if not reaped or remaining or proc.returncode or timed_out:
        raise RuntimeError(name+' failed or inconclusive; matrix stopped')
    return work


def checks(work):
    value=read(work/'checks.json')
    assert value==read(work/'stdout.txt') and value['status']=='passed'
    assert len(value['checks'])==len(set(value['checks']))
    return dict(checks=len(value['checks']),receiptSha256=digest(work/'checks.json'))


def main():
    def interrupted(signum,_frame):raise RuntimeError('Runner interrupted by signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted)
    os.umask(0o077);assert not ATTEMPT.exists()
    before=baseline()
    prior=sealed(PRIOR,'a820ce8adda0d8e3dbb1827f2b47c48f94c7969cccc299fbd10e36fbce54f982')
    assert prior['filesExact']==340 and prior['bytesExact']==812410778 and len(prior['symlinksExact'])==1
    attribution=sealed(ATTRIBUTION,'3f673fabcdab31e027b1d535d63a1a8302350a755fde4be94bb8ed53fecdd165')
    native_control=read(PRIOR/'attempt01/native-controls/stdout.txt')
    assert native_control['status']=='passed' and native_control['cases']==12 and native_control['assertions']==1294
    prior_proc=read(PRIOR/'attempt01/native-controls/result.json')
    assert prior_proc['returnCode']==0 and prior_proc['reaped'] and not prior_proc['timedOut']
    assert digest(PRIOR/'attempt01/native-controls/ram-live.bin')==digest(PRIOR/'attempt01/native-controls/ram-durable.bin')
    ATTEMPT.mkdir(mode=0o700);frozen=ATTEMPT/'frozen-inputs';frozen.mkdir(mode=0o700)
    old=frozen/'original';old.mkdir(mode=0o700)
    names=['PLAN.md','REVIEW.md','source-reading.json','run_scopes.py','hierarchical_store.py.patch',
           'profile_controls.py.patch','retained_reader.py.patch','bitmap_controls.py','profile_controls.py',
           'mount_identity.py','mount_controls.py','fixed_block.py','candidate.py','hierarchical_store.py',
           'chunk_store_base.py','native.py','controls.py','controls.patch','diagnostic.py','test_fixed_block.py','retained_reader.py']
    sources=[(HERE/name,frozen/name) for name in names]
    sources += [(PRIOR/'attempt01/frozen-inputs/dataset.json',frozen/'dataset.json')]
    sources += [(PRIOR/name,old/name) for name in ['hierarchical_store.py','chunk_store_base.py','native.py','fixed_block.py','candidate.py','mount_identity.py','diagnostic.py']]
    sources += [(PRIOR/'attempt01/mount-probe.so',ATTEMPT/'mount-probe.so'),
                (PRIOR/'attempt01/hierarchical-store.so',ATTEMPT/'hierarchical-store.so')]
    rows=[]
    for source,target in sources:
        with target.open('xb') as stream:stream.write(source.read_bytes());stream.flush();os.fsync(stream.fileno())
        rows.append(dict(path=str(source.relative_to(ROOT)),frozen=str(target.relative_to(ATTEMPT)),sha256=digest(target)))
    dataset=read(frozen/'dataset.json');source_root=Path(dataset['sourceRoot'])
    assert digest(frozen/'dataset.json')=='475f09d59534a09b6094707def7112709c050548b958b776362bf0ce86ee0a46'
    assert len(dataset['files'])==4270 and len(dataset['directories'])==169 and sum(r['bytes'] for r in dataset['files'])==35508922
    assert all(digest(source_root/r['path'])==r['sha256'] for r in dataset['files'])
    interpreter=Path(sys.executable).resolve(strict=True);interpreter_hash=digest(interpreter)
    library=ATTEMPT/'hierarchical-store.so';mount_library=ATTEMPT/'mount-probe.so'
    assert digest(library)==NATIVE_HASH and digest(mount_library)==MOUNT_HASH
    save(ATTEMPT/'inputs.json',dict(files=rows,interpreter=str(interpreter),interpreterSha256=interpreter_hash,
         baselineBefore=before,prior=prior,attribution=attribution,datasetSha256=digest(frozen/'dataset.json'),
         unchangedNativeControls=dict(cases=12,assertions=1294,rerun=False,
             stdoutSha256=digest(PRIOR/'attempt01/native-controls/stdout.txt'),resultSha256=digest(PRIOR/'attempt01/native-controls/result.json'))))
    report=dict(status='incomplete',scopes={},publicRuntimeChanged=False,serviceStorageQualified=False,
         actualMountChanges=False,sqliteTested=False,checksDisabled=False,durabilityBarriersDisabled=False,
         inlineLimit=512,payloadChunkBytes=4096,syncSelectionChanged=False,geometryChanged=False,
         profile='hms.hierarchical-chunk-store.compact-bitmap/0.1',librarySha256=NATIVE_HASH,mountLibrarySha256=MOUNT_HASH)
    env={**ENV,'HMS_LIBRARY':str(library),'HMS_LIBRARY_SHA256':NATIVE_HASH,
         'HMS_MOUNT_LIBRARY':str(mount_library),'HMS_MOUNT_LIBRARY_SHA256':MOUNT_HASH}
    try:
        for name,script in [('mount-controls','mount_controls.py'),('profile-controls','profile_controls.py')]:
            work=run(name,[str(interpreter),'-B',str(frozen/script)],env);report['scopes'][name]=checks(work)
        assert report['scopes']['mount-controls']['checks']==52 and report['scopes']['profile-controls']['checks']==8
        work=run('provider-controls',[str(interpreter),'-B',str(frozen/'test_fixed_block.py')],
                 {**env,'HMS_BLOCK_TEST_ROOT':str(ATTEMPT/'provider-controls')})
        result=read(work/'stdout.txt');assert result==dict(tests=24,failures=0,errors=0,passed=True)
        report['scopes']['provider-controls']=result
        for name in TARGETS:
            scope='bitmap-'+name
            work=run(scope,[str(interpreter),'-B',str(frozen/'bitmap_controls.py'),name],env)
            report['scopes'][scope]=checks(work)
            assert report['scopes'][scope]['checks']=={'codec':77,'edges':27,'corruption':12,'interruption':33}[name]
            print(json.dumps(dict(scope=scope,status='passed',**report['scopes'][scope])),flush=True)
        for name in SCOPES:
            work=run(name,[str(interpreter),'-B',str(frozen/'controls.py'),name],env);report['scopes'][name]=checks(work)
            print(json.dumps(dict(scope=name,status='passed',**report['scopes'][name])),flush=True)
        assert sum(report['scopes'][name]['checks'] for name in SCOPES)==96
        outputs={}
        for name,inputs in [('comparison-original',old),('comparison-candidate',frozen)]:
            work=run(name,[str(interpreter),'-B',str(inputs/'diagnostic.py'),'coarse'],env)
            result=read(work/'diagnostic.json');assert result['status']=='passed' and len(result['steps'])==426
            outputs[name]=result
            report['scopes'][name]=dict(receiptSha256=digest(work/'diagnostic.json'),cpuSeconds=result['cpuSeconds'],
                                      elapsedSeconds=result['elapsedSeconds'],providerSyncCalls=result['providerSyncCalls'])
        left,right=outputs.values();assert left['expectedFiles']==right['expectedFiles']
        for a,b in zip(left['steps'],right['steps']):
            assert {k:v for k,v in a.items() if k not in ('wallNs','cpuNs','callbacks')}=={k:v for k,v in b.items() if k not in ('wallNs','cpuNs','callbacks')}
        for output in outputs.values():
            syncs=output['firstOwnerCallbacks']['syncs']+output['coldOwnerCallbacks']['syncs']
            assert output['providerSyncCalls']==dict(fsync=syncs*8+12,wait=0)
        report['physicalEncodingsDiffer']=left['backingHashes']!=right['backingHashes'];assert report['physicalEncodingsDiffer']
        report['comparisonEquivalent']=True
        print(json.dumps(dict(scope='comparison',status='passed',timings={k:report['scopes'][k] for k in outputs})),flush=True)
        for name in ['replay_write','replay_read']:
            selected={**env,'HMS_REPLAY_WRITER':str(ATTEMPT/'replay_write')} if name=='replay_read' else env
            work=run(name,[str(interpreter),'-B',str(frozen/'controls.py'),name],selected,180,120)
            report['scopes'][name]=checks(work)
            print(json.dumps(dict(scope=name,status='passed')),flush=True)
        report['status']='passed'
    except BaseException as error:
        report['status']='failed-or-inconclusive';report['error']=f'{type(error).__name__}: {error}'
    finally:
        assert all(digest(ROOT/r['path'])==digest(ATTEMPT/r['frozen'])==r['sha256'] for r in rows)
        assert digest(interpreter)==interpreter_hash
        assert digest(library)==NATIVE_HASH and digest(mount_library)==MOUNT_HASH
        assert all(digest(source_root/r['path'])==r['sha256'] for r in dataset['files'])
        report['baselineAfter']=baseline();report['inputsStable']=True
        files=[p for p in HERE.rglob('*') if p.is_file() and not p.is_symlink()]
        report['allocatedBytes']=sum(p.stat().st_blocks*512 for p in files)
        assert all(p.stat().st_size<=16*1024**2 for p in files) and report['allocatedBytes']<1024**3
        save(ATTEMPT/'RESULTS.json',report)
    print(json.dumps(report,sort_keys=True),flush=True)
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
