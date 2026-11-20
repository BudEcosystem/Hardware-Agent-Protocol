"""One reviewed bounded native/model proof attempt. No hierarchy adoption/replay."""
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
ATTEMPT=HERE/'attempt01'
PRIOR=ROOT/'artifacts/implementation/inline-hierarchical-store'
ENV={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'}
NAMES=['PLAN.md','MODEL.md','REVIEW.md','run_proof.py','proof.c','bridge.c','bridge.c.patch',
       'native_controls.c','upstream-inputs.json','lfs.c','lfs.h','lfs_util.c','lfs_util.h','LICENSE.md']

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def read(path):return json.loads(path.read_text())
def save(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
def baseline():
    path=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(path)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    rows=read(path)['files'];assert len(rows)==244 and all(digest(ROOT/r['path'])==r['sha256'] for r in rows)
    return dict(receiptSha256=digest(path),filesExact=244)
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


def proof_receipt(work,expected_cases):
    rows=[json.loads(line) for line in (work/'stdout.txt').read_text().splitlines()]
    assert rows and len(rows)==expected_cases+1 and all(r['status']=='passed' for r in rows)
    summary=rows[-1];assert summary['cases']==expected_cases and summary['geometryBytes']==128*1024**2
    assert not summary['physicalPowerLoss'] and not summary['hierarchyAdopted']
    assert summary['trials']==summary['oldOutcomes']+summary['newOutcomes']<=40000
    assert not (work/'stderr.txt').read_bytes()
    trace=[json.loads(line) for line in (work/'events.jsonl').read_text().splitlines()]
    expected={}
    for r in trace:
        if 'event' in r:
            events=expected.setdefault(r['case'],[]);assert r['event']==len(events)+1
            assert r['kind'] in (1,2,3) and r['block']<32768
            events.append(r)
        else:assert r['nearFullUsedBlocks']>=32768-32 and r['totalBlocks']==32768 and r['fillers']<=8192
    assert len(expected)==expected_cases
    outcomes=[json.loads(line) for line in (work/'proof.jsonl').read_text().splitlines()]
    seen=set();cuts=errors=0
    for r in outcomes:
        signature=(r['case'],r['event'],r['mode'],r['tear'],r['order']);assert signature not in seen;seen.add(signature)
        assert r['case'] in expected and r['outcome'] in ('old','new') and type(r['acknowledged']) is bool
        if r['mode']==0:assert r['event']==r['tear']==r['order']==0 and r['acknowledged'] and r['outcome']=='new'
        else:
            assert not r['acknowledged'] and 1<=r['event']<=len(expected[r['case']])
            if r['mode']==1:cuts+=1
            elif r['mode']==2:errors+=1
            else:raise AssertionError('unknown model mode')
    wanted=set()
    for name,events in expected.items():
        wanted.add((name,0,0,0,0))
        for e in events:
            policies=1 if e['kind']==3 else 4
            wanted|={(name,e['event'],1,shape,order) for shape in range(7) for order in range(policies)}
            wanted|={(name,e['event'],2,shape,0) for shape in (0,6)}
    assert seen==wanted and cuts==summary['cutTrials'] and errors==summary['errorTrials']
    return dict(summary=summary,proofRows=len(outcomes),traceSha256=digest(work/'events.jsonl'),
                proofSha256=digest(work/'proof.jsonl'),stdoutSha256=digest(work/'stdout.txt'),
                modelMatrixExact=True,independentPostExecutionImageAudit=False)


def main():
    def interrupted(signum,_frame):raise RuntimeError('Proof runner interrupted by signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted)
    os.umask(0o077);assert not ATTEMPT.exists();before=baseline()
    pins=read(HERE/'upstream-inputs.json')
    assert digest(PRIOR/'index.json')==pins['priorIndexSha256']=='a820ce8adda0d8e3dbb1827f2b47c48f94c7969cccc299fbd10e36fbce54f982'
    prior_rows={r['path']:r for r in read(PRIOR/'index.json')['files']}
    for row in pins['exactCopies']:
        assert digest(ROOT/row['source'])==digest(HERE/row['target'])==row['sha256']
        assert prior_rows[str((ROOT/row['source']).relative_to(PRIOR))]['sha256']==row['sha256']
    assert digest(PRIOR/'bridge.c')==pins['bridgeBaselineSha256']
    assert (HERE/'bridge.c').read_bytes().startswith((PRIOR/'bridge.c').read_bytes())
    compiler=Path('/usr/bin/cc').resolve(strict=True);compiler_hash=digest(compiler)
    ATTEMPT.mkdir(mode=0o700);frozen=ATTEMPT/'frozen-inputs';frozen.mkdir(mode=0o700)
    sources=[]
    for name in NAMES:
        with (frozen/name).open('xb') as stream:stream.write((HERE/name).read_bytes());stream.flush();os.fsync(stream.fileno())
        sources.append(dict(path=name,sha256=digest(frozen/name)))
    save(ATTEMPT/'inputs.json',dict(files=sources,compiler=str(compiler),compilerSha256=compiler_hash,publicBefore=before,
         nativeSourceBaseline=pins,sourceOnlyBeforeThisReviewedAttempt=True))
    report=dict(status='incomplete',scopes={},hierarchyAdopted=False,fullWorkflowRun=False,
                physicalPowerLossTested=False,providerDurabilityChanged=False,publicRuntimeChanged=False)
    try:
        run('compiler-version',[str(compiler),'--version'],ENV,30,20)
        dependencies=run('dependencies',[str(compiler),'-std=c11','-M','-I',str(frozen),str(frozen/'proof.c'),str(frozen/'native_controls.c')],ENV,30,20)
        text=(dependencies/'stdout.txt').read_text().replace('\\\n',' ')
        headers=[]
        for entry in text.splitlines():
            if ':' in entry:headers.extend(Path(x).resolve(strict=True) for x in entry.split(':',1)[1].split())
        assert headers
        save(ATTEMPT/'headers.json',[dict(path=str(p),sha256=digest(p)) for p in sorted(set(headers))])
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-DLFS_NO_MALLOC','-DLFS_NO_DEBUG','-DLFS_NO_WARN','-DLFS_NO_ERROR','-I',str(frozen)]
        for name,source in [('native-controls','native_controls.c'),('model-proof','proof.c')]:
            binary=ATTEMPT/(name+'-bin')
            run('build-'+name,[str(compiler),*flags,str(frozen/source),str(frozen/'lfs.c'),str(frozen/'lfs_util.c'),'-o',str(binary)],ENV,30,20)
            report[name+'BinarySha256']=digest(binary)
        work=run('native-controls',[str(ATTEMPT/'native-controls-bin')],ENV)
        value=read(work/'stdout.txt');assert value['status']=='passed' and value['cases']==12 and value['assertions']==1294
        assert digest(work/'ram-live.bin')==digest(work/'ram-durable.bin') and not (work/'stderr.txt').read_bytes()
        report['scopes']['native-controls']=value
        for scope,count,wall,cpu in [('basic',10,60,40),('metadata',4,60,40),('nearfull',1,180,120)]:
            work=run(scope,[str(ATTEMPT/'model-proof-bin'),scope],ENV,wall,cpu)
            report['scopes'][scope]=proof_receipt(work,count)
            print(json.dumps(dict(scope=scope,status='passed',**report['scopes'][scope])),flush=True)
        report['status']='finite-model-controls-passed'
    except BaseException as error:
        report['status']='failed-or-inconclusive';report['error']=f'{type(error).__name__}: {error}'
    finally:
        try:
            assert all(digest(HERE/r['path'])==digest(frozen/r['path'])==r['sha256'] for r in sources)
            assert digest(compiler)==compiler_hash
            if (ATTEMPT/'headers.json').exists():assert all(digest(Path(r['path']))==r['sha256'] for r in read(ATTEMPT/'headers.json'))
            for name in ['native-controls','model-proof']:
                if name+'BinarySha256' in report:assert digest(ATTEMPT/(name+'-bin'))==report[name+'BinarySha256']
            report['publicAfter']=baseline();report['inputsStable']=True
            files=[p for p in HERE.rglob('*') if p.is_file() and not p.is_symlink()]
            report['allocatedBytes']=sum(p.stat().st_blocks*512 for p in files)
            assert all(p.stat().st_size<=16*1024**2 for p in files) and report['allocatedBytes']<1024**3
        except BaseException as error:
            report['status']='failed-or-inconclusive';report['finalJoinError']=f'{type(error).__name__}: {error}'
        save(ATTEMPT/'RESULTS.json',report)
    print(json.dumps(report,sort_keys=True),flush=True)
    if report['status']!='finite-model-controls-passed':raise SystemExit(1)


if __name__=='__main__':main()
