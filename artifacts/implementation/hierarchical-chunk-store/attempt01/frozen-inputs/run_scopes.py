"""One frozen bounded attempt; failure stops the matrix and preserves all state."""
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
CORE=ROOT/'research/host-contract/littlefs-core'
PRIOR=ROOT/'artifacts/verification/supervisor-storage-integration'
ACTUAL=PRIOR/'harness01/attempts/attempt01-actual'
BASE=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
SCOPES=['hierarchy','data','namespace','bounds','recovery','corruption','orphan_recovery','owner_loss','fault']
ENV={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'}

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def save(path,value):
    with path.open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())

def sealed(directory,wanted):
    assert digest(directory/'index.json')==wanted
    rows=json.loads((directory/'index.json').read_text())['files']
    assert all(digest(directory/r['path'])==r['sha256'] for r in rows)
    return dict(indexSha256=wanted,filesExact=len(rows))

def baseline():
    wanted='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    assert digest(BASE)==wanted
    rows=json.loads(BASE.read_text())['files']
    assert len(rows)==244 and all(digest(ROOT/r['path'])==r['sha256'] for r in rows)
    return dict(receiptSha256=wanted,filesExact=244)

def limits(cpu):
    for key,amount in [(resource.RLIMIT_CPU,cpu),(resource.RLIMIT_AS,512*1024**2),
                       (resource.RLIMIT_FSIZE,16*1024**2),(resource.RLIMIT_NOFILE,128),(resource.RLIMIT_CORE,0)]:
        resource.setrlimit(key,(amount,amount))

def run(name,argv,env,wall=60,cpu=40):
    work=ATTEMPT/name;work.mkdir(mode=0o700)
    save(work/'intent.json',dict(argv=argv,environment=env,cwd=str(work),wallSeconds=wall,cpuSeconds=cpu,
                               addressSpaceBytes=512*1024**2,fileBytes=16*1024**2,descriptors=128))
    started=time.monotonic();timed_out=False
    with (work/'stdout.txt').open('xb') as out,(work/'stderr.txt').open('xb') as err:
        proc=subprocess.Popen(argv,cwd=work,env=env,stdout=out,stderr=err,start_new_session=True,preexec_fn=lambda:limits(cpu))
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
    result=dict(returnCode=proc.returncode,timedOut=timed_out,reaped=True,elapsedSeconds=time.monotonic()-started,
                cpuSeconds=usage.ru_utime+usage.ru_stime,peakRSSKiB=usage.ru_maxrss)
    save(work/'result.json',result)
    if proc.returncode or timed_out:raise RuntimeError(name+' failed or inconclusive; matrix stopped')
    return work

def verify_scope(work,name):
    assert (work/'stderr.txt').stat().st_size==0 and (work/'stdout.txt').stat().st_size<=65536
    result=json.loads((work/'checks.json').read_text())
    assert json.loads((work/'stdout.txt').read_text())==result
    assert result['scope']==name and result['status']=='passed' and result['checks']
    assert len(result['checks'])==len(set(result['checks']))
    return dict(checks=len(result['checks']),receiptSha256=digest(work/'checks.json'))

def main():
    os.umask(0o077);assert not ATTEMPT.exists()
    baseline_before=baseline()
    prior=sealed(PRIOR,'8a5cd13eeb4544fecdb1d4b81da231b8daea9beacfe7840b5989b110f90ef15a')
    core=sealed(CORE,'c149f635c72262102a1d5c2ff3f2fc08c56fc6dc1fc9a1306037114d1650fd0e')
    assert digest(HERE/'chunk_store_base.py')=='11233050890e6db2289dd1f6c117570e22f4a72e6d1c765b1a9642e0196d6a2c'
    assert digest(HERE/'fixed_block.py')=='b5173152c5505934275b89a4c1c2e54f4bd4fa75b9a60b8e7f149bd3456b42db'
    files=json.loads((ACTUAL/'scratch-index.json').read_text());source=ACTUAL/'scratch'
    assert len(files)==4270 and sum(r['bytes'] for r in files)==35508922
    assert all((source/r['path']).stat().st_size==r['bytes'] and digest(source/r['path'])==r['sha256'] for r in files)
    directories=sorted((str(p.relative_to(source)) for p in source.rglob('*') if p.is_dir()),key=lambda p:(p.count('/'),p))
    assert len(directories)==169
    ATTEMPT.mkdir(mode=0o700);frozen=ATTEMPT/'frozen-inputs';frozen.mkdir(mode=0o700)
    save(frozen/'dataset.json',dict(sourceRoot=str(source),sourceIndexSha256=digest(ACTUAL/'scratch-index.json'),
                                   files=files,directories=directories))
    names=['PLAN.md','REVIEW.md','bridge.c','chunk_store_base.py','fixed_block.py','hierarchical_store.py',
           'native.py','native-adaptation.patch','controls.py','run_scopes.py']
    sources=[HERE/name for name in names]+[CORE/'repo'/name for name in ['lfs.c','lfs.h','lfs_util.c','lfs_util.h','LICENSE.md']]
    rows=[]
    for source in sources:
        target=frozen/source.name
        with target.open('xb') as f:f.write(source.read_bytes());f.flush();os.fsync(f.fileno())
        rows.append(dict(path=str(source.relative_to(ROOT)),frozen=source.name,bytes=target.stat().st_size,sha256=digest(target)))
    compiler=Path('/usr/bin/cc').resolve(strict=True);compiler_hash=digest(compiler)
    save(ATTEMPT/'inputs.json',dict(files=rows,compiler=str(compiler),compilerSha256=compiler_hash,
         baselineBefore=baseline_before,prior=prior,core=core,datasetSha256=digest(frozen/'dataset.json')))
    report=dict(status='incomplete',scopes={},filesystemMounted=False,sqliteTested=False,physicalPowerLossTested=False,
                serviceStorageQualified=False,aggregateServiceQuotaEnforced=False,backedControlCapacity=False)
    try:
        run('compiler-version',[str(compiler),'--version'],ENV,30,20)
        library=ATTEMPT/'hierarchical-store.so'
        run('build',[str(compiler),'-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
                    '-DLFS_NO_MALLOC','-DLFS_NO_DEBUG','-DLFS_NO_WARN','-DLFS_NO_ERROR','-I',str(frozen),
                    str(frozen/'bridge.c'),str(frozen/'lfs.c'),str(frozen/'lfs_util.c'),'-o',str(library)],ENV,30,20)
        library_hash=digest(library);report['librarySha256']=library_hash
        env={**ENV,'HMS_LIBRARY':str(library),'HMS_LIBRARY_SHA256':library_hash}
        for name in SCOPES+['replay_write','replay_read']:
            actual=name.startswith('replay_')
            selected={**env,'HMS_REPLAY_WRITER':str(ATTEMPT/'replay_write')} if name=='replay_read' else env
            work=run(name,[sys.executable,'-B',str(frozen/'controls.py'),name],selected,180 if actual else 60,120 if actual else 40)
            report['scopes'][name]=verify_scope(work,name)
            print(json.dumps(dict(scope=name,**report['scopes'][name],status='passed')),flush=True)
        report['status']='passed'
    except BaseException as exc:
        report['status']='failed-or-inconclusive';report['error']=f'{type(exc).__name__}: {exc}'
    finally:
        report['baselineAfter']=baseline()
        assert digest(compiler)==compiler_hash
        assert all(digest(ROOT/r['path'])==digest(frozen/r['frozen'])==r['sha256'] for r in rows)
        if 'librarySha256' in report:assert digest(ATTEMPT/'hierarchical-store.so')==report['librarySha256']
        source_root=Path(json.loads((frozen/'dataset.json').read_text())['sourceRoot'])
        assert all(digest(source_root/r['path'])==r['sha256'] for r in files)
        inventory=[p for p in HERE.rglob('*') if p.is_file()]
        report['stageAllocatedBytes']=sum(p.stat().st_blocks*512 for p in inventory)
        assert all(p.stat().st_size<=16*1024**2 for p in inventory) and report['stageAllocatedBytes']<1024**3
        report['inputsStable']=True
        save(ATTEMPT/'RESULTS.json',report)
    print(json.dumps(report,sort_keys=True),flush=True)
    if report['status']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
