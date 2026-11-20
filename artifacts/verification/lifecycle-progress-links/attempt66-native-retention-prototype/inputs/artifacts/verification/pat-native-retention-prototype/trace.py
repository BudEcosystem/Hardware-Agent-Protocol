"""Bounded syscall observation and read-failure injection on owned fixtures only."""
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import time

BASE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_bytes())
def write(path,value):
    body=(json.dumps(value,indent=2)+'\n').encode();assert len(body)<=1048576
    with path.open('xb') as stream:stream.write(body)
assert read(BASE/'attempt01/result.json')['status']=='passed'
for row in read(BASE/'inputs.json')['files']:
    assert (BASE/row['path']).stat().st_size==row['bytes'] and sha(BASE/row['path'])==row['sha256']
OUT=BASE/'trace01';OUT.mkdir(mode=0o700,exist_ok=False)
tracer=Path(shutil.which('strace')).resolve();binary=BASE/'build01/scan'
environment={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}
resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
help_=subprocess.run([str(tracer),'--help'],env=environment,capture_output=True,timeout=5,check=True)
version=subprocess.run([str(tracer),'--version'],env=environment,capture_output=True,timeout=5,check=True)
assert len(help_.stdout)+len(version.stdout)<=65536 and help_.stderr==version.stderr==b''
with (OUT/'strace-help.txt').open('xb') as stream:stream.write(help_.stdout)
with (OUT/'strace-version.txt').open('xb') as stream:stream.write(version.stdout)
ordinary=BASE/'attempt01/fixtures/ordinary';fifo=BASE/'attempt01/fixtures/fifo'
paths=[ordinary,fifo,*ordinary.rglob('*'),*fifo.rglob('*')]
def metadata():
    rows=[]
    for path in paths:
        info=path.lstat();rows.append(dict(path=str(path),device=info.st_dev,inode=info.st_ino,mode=info.st_mode,
            size=info.st_size,uid=info.st_uid,gid=info.st_gid,nlink=info.st_nlink,mtimeNs=info.st_mtime_ns,ctimeNs=info.st_ctime_ns))
    return rows
before=metadata();write(OUT/'metadata-before.json',before)
write(OUT/'started.json',dict(binarySha256=sha(binary),tracer=str(tracer),tracerSha256=sha(tracer),
    scriptSha256=sha(Path(__file__)),fixturePaths=[str(ordinary),str(fifo)],maximumScopeSeconds=60,
    perCommandSeconds=10,traceBytesPerFile=1048576,originalCaseTreeTouched=False))
deadline=time.monotonic()+60;rows=[]
def run(name,path,expected_reason,expected_errno,injection=None):
    log=OUT/(name+'.trace');assert not log.exists()
    command=[str(tracer),'--kill-on-exit','-I','2','-s','256','-o',str(log)]
    if injection:command+=['-e','inject='+injection]
    command += [str(binary),str(path),'8192','67108864','1']
    completed=subprocess.run(command,cwd=BASE,env=environment,stdin=subprocess.DEVNULL,capture_output=True,
        timeout=min(10,max(.001,deadline-time.monotonic())))
    assert len(completed.stdout)+len(completed.stderr)<=65536
    value=json.loads(completed.stdout);assert completed.stderr==b''
    assert value['reason']==expected_reason and value['errno']==expected_errno
    assert completed.returncode==(0 if expected_reason=='OK' else 1)
    lines=log.read_text().splitlines();assert 0<len(lines)<=1000 and log.stat().st_size<=1048576
    assert lines[-1]=='+++ exited with '+str(completed.returncode)+' +++'
    calls=[]
    for line in lines[:-1]:
        match=re.match(r'^([a-z0-9_]+)\(',line);assert match,line
        calls.append(dict(name=match[1],line=line))
    assert sum(row['name']=='execve' for row in calls)==1
    assert not {'fork','vfork','clone','clone3','socket','connect','unlink','unlinkat','rename','renameat','mkdir','mkdirat','chmod','fchmod','chown','fchown','truncate','ftruncate','pwrite64','writev'}.intersection(row['name'] for row in calls)
    start=next(i for i,row in enumerate(calls) if row['name']=='openat' and json.dumps(str(path)) in row['line'])
    native=calls[start:]
    directory_fds=set();open_records=[];stat_calls=0;closed=[]
    for call in native:
        line=call['line'];name_=call['name']
        if name_=='openat':
            match=re.fullmatch(r'openat\((AT_FDCWD|[0-9]+), "([^"]+)", ([A-Z_|]+)\)\s+= ([-0-9]+)(.*)',line);assert match,line
            parent,path_,flags,fd,_=match.groups()
            assert set(flags.split('|'))=={'O_RDONLY','O_DIRECTORY','O_NOFOLLOW','O_CLOEXEC'}
            assert (parent=='AT_FDCWD' and path_==str(path)) or (int(parent) in directory_fds and path_=='nested')
            if int(fd)>=0:directory_fds.add(int(fd))
            open_records.append(call)
        elif name_=='newfstatat':
            if line.startswith('newfstatat(1, "",'):
                assert 'AT_EMPTY_PATH' in line
            else:
                assert 'AT_SYMLINK_NOFOLLOW' in line
                assert int(line.split('(',1)[1].split(',',1)[0]) in directory_fds
                stat_calls+=1
        elif name_=='getdents64':assert int(line.split('(',1)[1].split(',',1)[0]) in directory_fds
        elif name_=='close':
            fd=int(line.split('(',1)[1].split(')',1)[0]);assert fd in directory_fds
            directory_fds.remove(fd);closed.append(fd)
        elif name_=='write':assert line.startswith('write(1, ')
        else:assert name_ in {'getuid','getrusage','brk','getrandom','exit_group'},line
    assert not directory_fds
    row=dict(name=name,argv=command,expectedReason=expected_reason,expectedErrno=expected_errno,
        injection=injection,result=value,exitCode=completed.returncode,traceSha256=sha(log),syscalls=len(calls),
        nativePhaseOpenCalls=len(open_records),nativePhaseStatCalls=stat_calls,nativePhaseReadCalls=0,
        directoryDescriptorsClosed=True,originalCaseTreeTouched=False)
    rows.append(row);write(OUT/(name+'.json'),row)
    return calls
normal=run('ordinary',ordinary,'OK',0)
run('fifo',fifo,'QUALIFICATION_UNSAFE_FILE',0)
run('foreign-uid-injection',ordinary,'QUALIFICATION_UNSAFE_FILE',0,'getuid:retval=0:when=1')
run('readdir-error-injection',ordinary,'OS_ERROR',5,'getdents64:error=EIO:when=1')
open_number=0;child_open=None
for call in normal:
    if call['name']=='openat':
        open_number+=1
        if '"nested"' in call['line']:child_open=open_number;break
assert child_open is not None
run('child-open-error-injection',ordinary,'OS_ERROR',13,'openat:error=EACCES:when='+str(child_open))
after=metadata();write(OUT/'metadata-after.json',after);assert before==after
assert sha(binary)==read(BASE/'build01/build.json')['binarySha256']
write(OUT/'result.json',dict(status='passed',scopes=rows,fixtureMetadataUnchanged=True,
    binarySha256=sha(binary),tracerSha256=sha(tracer),scriptSha256=sha(Path(__file__)),
    originalCaseTreeTouched=False,qualificationWorkerLaunched=False,productionChanged=False,
    nativeFileContentReadsObserved=0,foreignUidIsInjected=True,concurrentMutationTested=False,
    syscallCoverage='All syscalls in five owned standalone fixture processes; dynamic loader precedes identified scanner phase',
    wholeWorkerTimingQualified=False))
print(json.dumps(dict(status='passed',scopes=len(rows),nativeFileContentReadsObserved=0,fixtureMetadataUnchanged=True)))
