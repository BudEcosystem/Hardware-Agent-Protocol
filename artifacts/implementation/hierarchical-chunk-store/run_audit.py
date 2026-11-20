"""Bounded single read-only audit with frozen source and wait4 process receipt."""
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
WORK=HERE/'audit-process01'

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
def limits():
    for key,value in [(resource.RLIMIT_CPU,60),(resource.RLIMIT_AS,512*1024**2),
                      (resource.RLIMIT_FSIZE,16*1024**2),(resource.RLIMIT_NOFILE,128),(resource.RLIMIT_CORE,0)]:
        resource.setrlimit(key,(value,value))

def main():
    os.umask(0o077);assert (HERE/'attempt01/RESULTS.json').is_file();WORK.mkdir(mode=0o700)
    for name in ['audit_evidence.py','run_audit.py','AUDIT-PLAN.md']:
        with (WORK/name).open('xb') as f:f.write((HERE/name).read_bytes());f.flush();os.fsync(f.fileno())
    env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1','HMS_AUDIT_STAGE':str(HERE)}
    argv=[sys.executable,'-B',str(WORK/'audit_evidence.py')]
    save(WORK/'intent.json',dict(argv=argv,environment=env,wallSeconds=90,cpuSeconds=60,
        addressSpaceBytes=512*1024**2,descriptors=128,fileBytes=16*1024**2,
        sourceSha256={name:digest(WORK/name) for name in ['audit_evidence.py','run_audit.py','AUDIT-PLAN.md']}))
    started=time.monotonic();timed_out=False
    with (WORK/'stdout.txt').open('xb') as out,(WORK/'stderr.txt').open('xb') as err:
        proc=subprocess.Popen(argv,cwd=WORK,env=env,stdout=out,stderr=err,start_new_session=True,preexec_fn=limits)
        save(WORK/'started.json',dict(pid=proc.pid,processGroup=proc.pid,unix=time.time()))
        while True:
            pid,status,usage=os.wait4(proc.pid,os.WNOHANG)
            if pid:break
            if time.monotonic()-started>=90:
                timed_out=True;os.killpg(proc.pid,signal.SIGKILL);pid,status,usage=os.wait4(proc.pid,0);break
            time.sleep(.1)
        proc.returncode=os.waitstatus_to_exitcode(status)
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        out.flush();err.flush();os.fsync(out.fileno());os.fsync(err.fileno())
    result=dict(returnCode=proc.returncode,reaped=True,timedOut=timed_out,elapsedSeconds=time.monotonic()-started,
                cpuSeconds=usage.ru_utime+usage.ru_stime,peakRSSKiB=usage.ru_maxrss)
    save(WORK/'result.json',result);print(json.dumps(result,sort_keys=True),flush=True)
    if proc.returncode or timed_out:raise SystemExit(1)

if __name__=='__main__':main()
