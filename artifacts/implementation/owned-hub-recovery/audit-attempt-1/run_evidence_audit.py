"""One bounded owned subprocess for retained-data audit; no job execution."""
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
HELPER_SHA = '97a1a26fe0b954efc42f52420e552c286047ebbb11c188eed69870c452c850a1'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def save(path,value):
    with path.open('x') as target:
        json.dump(value,target,indent=2,sort_keys=True);target.write('\n');target.flush();os.fsync(target.fileno())


def main():
    def interrupted(*_):
        raise RuntimeError('audit launcher interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    os.umask(0o077)
    attempt=HERE/'audit-attempt-1';attempt.mkdir(mode=0o700)
    pins={}
    for name in ('audit_evidence.py','run_evidence_audit.py'):
        pins[name]=digest(HERE/name);shutil.copyfile(HERE/name,attempt/name)
        assert digest(attempt/name)==pins[name]
    body=(HERE/'helper-check01/libowner-preconditions.so').read_bytes()
    assert len(body)<1024**2 and hashlib.sha256(body).hexdigest()==HELPER_SHA
    helper_fd=os.memfd_create('hms-audit-owner-query',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
    assert os.write(helper_fd,body)==len(body)
    seals=fcntl.F_SEAL_SEAL|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_WRITE
    fcntl.fcntl(helper_fd,fcntl.F_ADD_SEALS,seals)
    helper=ctypes.CDLL('/proc/self/fd/'+str(helper_fd))
    helper.hms_owner_signal_snapshot.argtypes=[];helper.hms_owner_signal_snapshot.restype=ctypes.c_int
    assert helper.hms_owner_signal_snapshot()==1 and len(os.listdir('/proc/self/task'))==1
    runtime=digest(Path('/proc/self/exe'));assert digest(Path(sys.executable))==runtime
    save(attempt/'intent.json',dict(sourcePins=pins,runtimeSha256=runtime,helperSha256=HELPER_SHA,
        limits=dict(cpuSeconds=5,addressBytes=128*1024**2,fileBytes=4*1024**2,openFiles=64,
                    wallSeconds=15,cleanupSeconds=3),candidateCodeImported=False,jobChildrenLaunched=False))
    child=None;pidfd=None;reason=None;reaped=False;code=None;oldmask=None
    started=time.monotonic()
    def limits():
        signal.pthread_sigmask(signal.SIG_SETMASK,oldmask)
        for kind,value in ((resource.RLIMIT_CPU,5),(resource.RLIMIT_AS,128*1024**2),
                           (resource.RLIMIT_FSIZE,4*1024**2),(resource.RLIMIT_NOFILE,64),(resource.RLIMIT_CORE,0)):
            resource.setrlimit(kind,(value,value))
    def anchor():
        assert helper.hms_owner_signal_snapshot()==1 and len(os.listdir('/proc/self/task'))==1
        assert child.returncode is None
        result=os.waitid(os.P_PID,child.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        assert os.getpgid(child.pid)==child.pid and os.getsid(child.pid)==child.pid
        return result
    with (attempt/'stdout.txt').open('xb') as out,(attempt/'stderr.txt').open('xb') as err:
        try:
            oldmask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
            try:
                child=subprocess.Popen([sys.executable,'-I','-S','-B',str(attempt/'audit_evidence.py'),str(HERE)],
                    stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True,
                    preexec_fn=limits,close_fds=True,cwd=HERE,env={'LANG':'C','LC_ALL':'C'})
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK,oldmask)
            pidfd=os.pidfd_open(child.pid,0)
            save(attempt/'started.json',dict(pid=child.pid,pgid=child.pid))
            while anchor() is None:
                if time.monotonic()-started>=15:
                    reason='AUDIT_WALL_LIMIT';break
                time.sleep(.01)
        except BaseException as error:
            reason=type(error).__name__+': '+str(error)
        finally:
            saved=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
            try:
                if child is not None:
                    if anchor() is None:
                        try:
                            if pidfd is not None:
                                signal.pidfd_send_signal(pidfd,signal.SIGKILL)
                            else:
                                os.killpg(child.pid,signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    end=time.monotonic()+3
                    while anchor() is None and time.monotonic()<end:
                        time.sleep(.01)
                    if anchor() is not None:
                        code=child.wait();reaped=True
                    else:
                        reason=reason or 'AUDIT_UNREAPED'
                if pidfd is not None:
                    os.close(pidfd)
                os.close(helper_fd)
                out.flush();err.flush();os.fsync(out.fileno());os.fsync(err.fileno())
                pending=sorted(int(value) for value in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
                stable=all(digest(HERE/name)==digest(attempt/name)==sha for name,sha in pins.items())
                stable=stable and digest(Path('/proc/self/exe'))==digest(Path(sys.executable))==runtime
                result=dict(passed=reason is None and code==0 and reaped and stable and not pending
                            and not (attempt/'stderr.txt').read_bytes(),reason=reason,returnCode=code,
                            reaped=reaped,inputsStable=stable,interruptsPendingAfterCleanup=pending,
                            elapsedSeconds=time.monotonic()-started,candidateCodeImported=False,
                            jobChildrenLaunched=False)
                if (HERE/'AUDIT.json').exists():
                    result['auditSha256']=digest(HERE/'AUDIT.json')
                save(attempt/'RESULTS.json',result);print(json.dumps(result,sort_keys=True))
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK,saved)
    assert result['passed']


if __name__=='__main__':
    main()
