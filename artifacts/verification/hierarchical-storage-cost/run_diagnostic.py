"""One exact two-mode diagnostic, bounded children, no retry or image recovery."""
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
PRIOR=ROOT/'artifacts/implementation/hierarchical-chunk-store'
ATTEMPT=HERE/'attempt01'
ENV={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'}

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(path):return json.loads(path.read_text())
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
def baseline():
    path=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    wanted='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    assert digest(path)==wanted
    rows=read(path)['files'];assert len(rows)==244 and all(digest(ROOT/r['path'])==r['sha256'] for r in rows)
    return dict(receiptSha256=wanted,filesExact=244)
def limits():
    for key,value in [(resource.RLIMIT_CPU,40),(resource.RLIMIT_AS,512*1024**2),
                      (resource.RLIMIT_FSIZE,16*1024**2),(resource.RLIMIT_NOFILE,128),(resource.RLIMIT_CORE,0)]:
        resource.setrlimit(key,(value,value))
def run(mode):
    work=ATTEMPT/mode;work.mkdir(mode=0o700)
    argv=[sys.executable,'-B',str(ATTEMPT/'frozen-inputs/diagnostic.py'),mode]
    save(work/'intent.json',dict(argv=argv,environment=ENV,wallSeconds=60,cpuSeconds=40,
                               addressSpaceBytes=512*1024**2,descriptors=128,fileBytes=16*1024**2))
    started=time.monotonic();timed_out=False
    with (work/'stdout.txt').open('xb') as out,(work/'stderr.txt').open('xb') as err:
        proc=subprocess.Popen(argv,cwd=work,env=ENV,stdout=out,stderr=err,start_new_session=True,preexec_fn=limits)
        save(work/'started.json',dict(pid=proc.pid,processGroup=proc.pid,unix=time.time()))
        while True:
            pid,status,usage=os.wait4(proc.pid,os.WNOHANG)
            if pid:break
            if time.monotonic()-started>=60:
                timed_out=True;os.killpg(proc.pid,signal.SIGKILL);pid,status,usage=os.wait4(proc.pid,0);break
            time.sleep(.1)
        proc.returncode=os.waitstatus_to_exitcode(status)
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        out.flush();err.flush();os.fsync(out.fileno());os.fsync(err.fileno())
    result=dict(returnCode=proc.returncode,reaped=True,timedOut=timed_out,elapsedSeconds=time.monotonic()-started,
                cpuSeconds=usage.ru_utime+usage.ru_stime,peakRSSKiB=usage.ru_maxrss)
    save(work/'result.json',result)
    if proc.returncode or timed_out:raise RuntimeError(mode+' failed or inconclusive; diagnostic stopped')
    assert (work/'stderr.txt').stat().st_size==0 and (work/'stdout.txt').stat().st_size<=65536
    report=read(work/'diagnostic.json')
    assert read(work/'stdout.txt')=={k:v for k,v in report.items() if k not in ['spans','steps','expectedFiles','backingHashes']}
    assert report['status']=='passed' and report['mode']==mode and report['files']==40 and report['directories']==20
    return report

def main():
    os.umask(0o077);assert not ATTEMPT.exists();before=baseline()
    assert digest(PRIOR/'index.json')=='8916d9e9a431fb0135d743daf38b746b5248cd81aee20dc4f92c9c645e33e26a'
    prior_rows=read(PRIOR/'index.json')['files'];assert len(prior_rows)==212
    assert all(digest(PRIOR/r['path'])==r['sha256'] for r in prior_rows)
    ATTEMPT.mkdir(mode=0o700);frozen=ATTEMPT/'frozen-inputs';frozen.mkdir(mode=0o700)
    sources=[HERE/name for name in ['PLAN.md','REVIEW.md','diagnostic.py','run_diagnostic.py']]
    sources += [PRIOR/'attempt01/frozen-inputs'/name for name in ['hierarchical_store.py','native.py','chunk_store_base.py','fixed_block.py','bridge.c']]
    sources += [PRIOR/'attempt01/hierarchical-store.so']
    rows=[]
    for source in sources:
        target=frozen/source.name
        with target.open('xb') as f:f.write(source.read_bytes());f.flush();os.fsync(f.fileno())
        rows.append(dict(path=str(source.relative_to(ROOT)),frozen=source.name,bytes=target.stat().st_size,sha256=digest(target)))
    save(ATTEMPT/'inputs.json',dict(files=rows,baselineBefore=before,priorIndexSha256=digest(PRIOR/'index.json')))
    report=dict(status='incomplete',modes={},fullWorkflowQualified=False,publicRuntimeChanged=False,
                disabledChecks=False,disabledFsync=False,geometryChanged=False)
    try:
        outputs={}
        for mode in ['coarse','nested']:
            outputs[mode]=run(mode);report['modes'][mode]=dict(receiptSha256=digest(ATTEMPT/mode/'diagnostic.json'))
            print(json.dumps(dict(mode=mode,status='passed',elapsedSeconds=outputs[mode]['elapsedSeconds'])),flush=True)
        left,right=outputs['coarse'],outputs['nested']
        for key in ['expectedFiles','backingHashes','firstOwnerCallbacks','coldOwnerCallbacks']:
            assert left[key]==right[key],key+' instrumentation mismatch'
        assert len(left['steps'])==len(right['steps'])
        for a,b in zip(left['steps'],right['steps']):
            assert {k:v for k,v in a.items() if k not in ('wallNs','cpuNs')}=={k:v for k,v in b.items() if k not in ('wallNs','cpuNs')}
        report['status']='passed';report['instrumentationEquivalent']=True;report['stepsPerMode']=len(left['steps'])
    except BaseException as exc:report['status']='failed-or-inconclusive';report['error']=f'{type(exc).__name__}: {exc}'
    finally:
        assert all(digest(ROOT/r['path'])==digest(frozen/r['frozen'])==r['sha256'] for r in rows)
        assert all(digest(PRIOR/r['path'])==r['sha256'] for r in prior_rows)
        report['baselineAfter']=baseline();report['inputsStable']=True
        files=[p for p in HERE.rglob('*') if p.is_file()]
        report['allocatedBytes']=sum(p.stat().st_blocks*512 for p in files)
        assert all(p.stat().st_size<=16*1024**2 for p in files) and report['allocatedBytes']<1024**3
        save(ATTEMPT/'RESULTS.json',report)
    print(json.dumps(report,sort_keys=True),flush=True)
    if report['status']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
