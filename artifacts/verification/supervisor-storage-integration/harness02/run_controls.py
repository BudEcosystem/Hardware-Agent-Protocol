"""Frozen selected scopes, independent retained scratch, stop at first failure."""
import fcntl
import stat
import tempfile
import resource
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import time

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[3]
SOURCE=ROOT/'artifacts/implementation/supervisor-storage-bindings/implementation01'
MAX_FILE=16*1024*1024
MAX_SCRATCH=256*1024*1024
os.umask(0o077)
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
def inventory(root):
    rows=[];total=0
    for path in sorted(root.rglob('*')):
        assert not path.is_symlink()
        if path.is_file():
            size=path.stat().st_size;total+=size
            assert size<=MAX_FILE and total<=MAX_SCRATCH
            rows.append(dict(path=path.relative_to(root).as_posix(),bytes=size,sha256=sha(path)))
    return rows
def identity(path):
    info=path.lstat();assert stat.S_ISDIR(info.st_mode) and not path.is_symlink()
    return dict(device=info.st_dev,inode=info.st_ino,uid=info.st_uid,mode=stat.S_IMODE(info.st_mode),sticky=bool(info.st_mode&stat.S_ISVTX))
def acquire_leases(root):
    held=[];records=[]
    try:
        for path in sorted(root.rglob('*')):
            if path.is_file() and ('owner' in path.name or 'lease' in path.name) and path.stat().st_size==0:
                fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC);held.append(fd);info=os.fstat(fd)
                assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o600
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                records.append(dict(path=str(path.relative_to(root)),device=info.st_dev,inode=info.st_ino))
        return held,records
    except BaseException:
        for fd in held:os.close(fd)
        raise
frozen=read(SOURCE/'index.json')
selection=read(BASE/'control-selection.json')
assert sha(SOURCE/'index.json')==selection['sourceIndexSha256']
external=read(BASE/'external-inputs.json')
def verify():
    for row in frozen['files']:
        path=ROOT/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
    for row in external['files']:
        path=Path(row['resolvedPath']);assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
verify()
results=[]
for scope in selection['scopes']:
    out=BASE/'controls'/scope['name'];out.mkdir(parents=True,exist_ok=False)
    project=out/'project';shutil.copytree(SOURCE/'project',project)
    scratch_parent=Path('/tmp');parent_identity=identity(scratch_parent)
    assert parent_identity['uid'] in (0,os.getuid()) and (not parent_identity['mode']&0o022 or parent_identity['sticky'])
    scratch=Path(tempfile.mkdtemp(prefix='hms-split-controls-',dir=str(scratch_parent)))
    scratch_identity=identity(scratch)
    assert scratch_identity['uid']==os.getuid() and scratch_identity['mode']==0o700
    assert identity(scratch_parent)==parent_identity
    write(out/'raw-scratch-before.json',dict(path=str(scratch),identity=scratch_identity,parentIdentity=parent_identity,
        policy='Original raw scratch retained; copied bindings are evidence only'))
    child=out/'control_child.py';shutil.copyfile(BASE/'control_child.py',child)
    inputs=inventory(project)
    assert len(inputs)==selection['projectFiles']
    config=dict(project=str(project),scratch=str(scratch),out=str(out),inputs=inputs,externalRoots=external['roots'],
        externalInputs=external['files'],targets=scope['targets'])
    write(out/'config.json',config)
    command=[sys.executable,'-I','-S','-B',str(child),str(out/'config.json')]
    environment=dict(PATH='/usr/bin:/bin',LC_ALL='C.UTF-8',TMPDIR=str(scratch),SQLITE_TMPDIR=str(scratch))
    write(out/'intent.json',dict(command=command,environment=environment,wallSeconds=60,cpuSeconds=40,
        addressSpaceBytes=512*1024*1024,maxFileBytes=MAX_FILE,maxScratchBytes=MAX_SCRATCH,fdLimit=128,
        sourceIndexSha256=selection['sourceIndexSha256'],childSha256=sha(child),targets=scope['targets']))
    usage_before=resource.getrusage(resource.RUSAGE_CHILDREN)
    started=time.monotonic();error=None
    with (out/'output.log').open('xb') as log:
        process=subprocess.Popen(command,cwd=project,env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        write(out/'started.json',dict(pid=process.pid))
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout,selectors.EVENT_READ);count=0
                while selector.get_map():
                    if time.monotonic()-started>=60:raise TimeoutError('Original control wall limit')
                    for key,_ in selector.select(.1):
                        body=os.read(key.fileobj.fileno(),65536)
                        if not body:selector.unregister(key.fileobj);continue
                        count+=len(body);assert count<=4*1024*1024
                        log.write(body);log.flush()
                process.wait(timeout=max(.001,60-(time.monotonic()-started)))
        except BaseException as exc:
            error=dict(type=type(exc).__name__,message=str(exc))
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=5)
            process.stdout.close()
    elapsed=time.monotonic()-started
    usage_after=resource.getrusage(resource.RUSAGE_CHILDREN)
    child_cpu=dict(userSeconds=usage_after.ru_utime-usage_before.ru_utime,systemSeconds=usage_after.ru_stime-usage_before.ru_stime)
    after=inventory(project);verify()
    assert identity(scratch)==scratch_identity and identity(scratch_parent)==parent_identity
    leases,lease_records=acquire_leases(scratch)
    try:
        retained=inventory(scratch)
        shutil.copytree(scratch,out/'scratch')
        assert inventory(out/'scratch')==retained==inventory(scratch)
        assert identity(scratch)==scratch_identity and identity(scratch_parent)==parent_identity
        write(out/'writer-quiescence.json',dict(held=lease_records,parentExitCode=process.returncode,
            scope='Original zero-length owner/writer files; only the declared diagnostic child was allowed'))
        write(out/'raw-scratch-after.json',dict(path=str(scratch),identity=identity(scratch),parentIdentity=identity(scratch_parent),
            rawScratchRetained=True,copyVerified=True))
    finally:
        for fd in leases:os.close(fd)
    child_result=read(out/'child-result.json') if (out/'child-result.json').exists() else None
    passed=error is None and elapsed<60 and process.returncode==0 and child_result is not None and child_result['passed'] and inputs==after
    result=dict(name=scope['name'],passed=passed,exitCode=process.returncode,elapsedSeconds=elapsed,error=error,
        sourceUnchanged=inputs==after,childCpu=child_cpu,child=child_result,scratchFiles=len(retained),scratchBytes=sum(r['bytes'] for r in retained))
    write(out/'scratch-index.json',retained);write(out/'result.json',result);results.append(result)
    print(json.dumps({k:result[k] for k in ('name','passed','elapsedSeconds','error')}),flush=True)
    if not passed:break
write(BASE/'CONTROL_RESULTS.json',dict(passed=len(results)==len(selection['scopes']) and all(r['passed'] for r in results),
    scopes=[dict(name=r['name'],passed=r['passed'],testsRun=(r['child'] or {}).get('counts',{})) for r in results],
    sourceIndexSha256=selection['sourceIndexSha256']))
raise SystemExit(0 if all(r['passed'] for r in results) and len(results)==len(selection['scopes']) else 1)
