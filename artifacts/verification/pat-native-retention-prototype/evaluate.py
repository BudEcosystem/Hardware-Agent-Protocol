"""Synthetic differential controls, then fixed metadata-only native/reference pairs."""
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import statistics
import subprocess
import sys
import time
import traceback

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PRIOR=ROOT/'artifacts/verification/pat-retention-scan-cost'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_bytes())
def write(path,value):
    body=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode();assert len(body)<=16777216
    with path.open('xb') as stream:stream.write(body)
inputs=read(BASE/'inputs.json')
for row in inputs['files']:
    path=BASE/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
OUT=BASE/'attempt01';OUT.mkdir(mode=0o700,exist_ok=False)
os.umask(0o077)
resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_FSIZE,(16777216,16777216))
resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
def expired(*args):raise TimeoutError('60-second native prototype evaluation deadline')
signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,60)
deadline=time.monotonic()+60
sys.path.insert(0,str(BASE))
from reference import tree_usage,SupervisorError
environment={'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}
allowed_command=None;launches=[];denied=[]
def audit(event,args):
    if event=='subprocess.Popen':
        executable,argv,cwd,env=args
        if list(argv)!=allowed_command or str(cwd)!=str(BASE) or env!=environment or len(launches)>=64:
            denied.append(event);raise RuntimeError('Only the exact declared metadata probe may launch')
        launches.append(list(argv))
    elif event.startswith('socket.') or event in ('sqlite3.connect','os.system','os.exec','os.fork','os.forkpty'):
        denied.append(event);raise RuntimeError('Unexpected process, network or database operation')
sys.addaudithook(audit)
def invoke(path,max_files,max_bytes,repeats,mode):
    global allowed_command
    prefix=[str(BASE/'build01/scan')] if mode=='native' else [sys.executable,'-I','-S','-B',str(BASE/'python_ref.py')]
    command=prefix+[str(path),str(max_files),str(max_bytes),str(repeats)];allowed_command=command
    started=time.monotonic_ns()
    try:
        completed=subprocess.run(command,cwd=BASE,env=environment,stdin=subprocess.DEVNULL,
            capture_output=True,timeout=min(10,max(.001,deadline-time.monotonic())))
    finally:allowed_command=None
    assert len(completed.stdout)+len(completed.stderr)<=65536 and completed.stderr==b''
    value=json.loads(completed.stdout);assert completed.returncode in (0,1)
    assert (completed.returncode==0)==(value['reason']=='OK')
    return dict(mode=mode,argv=command,exitCode=completed.returncode,result=value,outerWallNanoseconds=time.monotonic_ns()-started)
def reference_result(path,files,bytes_):
    try:
        result=tree_usage(path,max_files=files,max_bytes=bytes_)
        return dict(reason='OK',errno=0,files=result['files'],logicalBytes=result['logicalBytes'])
    except (SupervisorError,OSError) as error:
        return dict(reason=error.code if isinstance(error,SupervisorError) else 'OS_ERROR',errno=error.errno if isinstance(error,OSError) else 0)
def comparable(value):
    names=('reason','errno','files','logicalBytes') if value['reason']=='OK' else ('reason','errno')
    return {name:value[name] for name in names}
def directory(name):
    path=OUT/'fixtures'/name;path.mkdir(mode=0o700,parents=True,exist_ok=False);return path
def file(path,size=8):
    with path.open('xb') as stream:stream.write(b'x'*size)
    path.chmod(0o600)

controls=[];samples=[];held=[];locks=[];before=None;after=None;error=None
try:
    empty=directory('empty');ordinary=directory('ordinary');file(ordinary/'first',8);file(ordinary/'.hidden',3)
    nested=ordinary/'nested';nested.mkdir(mode=0o700);file(nested/'third',5)
    strange=directory('byte-name');fd=os.open(os.fsencode(strange)+b'/name-\xff',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    root_link=OUT/'fixtures/root-link';root_link.symlink_to(ordinary,target_is_directory=True)
    symlink=directory('symlink');(symlink/'entry').symlink_to(ordinary/'first')
    dirlink=directory('dirlink');(dirlink/'entry').symlink_to(nested,target_is_directory=True)
    hardlink=directory('hardlink');file(hardlink/'first');os.link(hardlink/'first',hardlink/'second')
    bad_file=directory('file-mode');file(bad_file/'entry');(bad_file/'entry').chmod(0o644)
    sticky_file=directory('file-sticky');file(sticky_file/'entry');(sticky_file/'entry').chmod(0o1600)
    bad_dir=directory('directory-mode');(bad_dir/'entry').mkdir(mode=0o755);(bad_dir/'entry').chmod(0o755)
    sgid_dir=directory('directory-sgid');(sgid_dir/'entry').mkdir(mode=0o700);(sgid_dir/'entry').chmod(0o2700)
    fifo=directory('fifo');os.mkfifo(fifo/'entry',0o600)
    depth10=directory('depth10');current=depth10
    for _ in range(10):current=current/'next';current.mkdir(mode=0o700)
    file(current/'end',1)
    depth11=directory('depth11');current=depth11
    for _ in range(11):current=current/'next';current.mkdir(mode=0o700)
    file(current/'end',1)
    single=directory('single');file(single/'entry',8)
    fixtures=[('empty-zero',empty,0,0),('ordinary',ordinary,8192,67108864),('byte-name',strange,8192,67108864),
        ('root-link',root_link,8192,67108864),('missing',OUT/'fixtures/missing',8192,67108864),
        ('root-file',single/'entry',8192,67108864),('symlink',symlink,8192,67108864),('dirlink',dirlink,8192,67108864),
        ('hardlink',hardlink,8192,67108864),('file-mode',bad_file,8192,67108864),('file-sticky',sticky_file,8192,67108864),
        ('directory-mode',bad_dir,8192,67108864),('directory-sgid',sgid_dir,8192,67108864),('fifo',fifo,8192,67108864),
        ('depth10',depth10,8192,67108864),('depth11',depth11,8192,67108864),('count-zero',single,0,67108864),
        ('count-exact',single,1,8),('bytes-below',single,8192,7),('bytes-exact',single,8192,8)]
    for name,path,files,bytes_ in fixtures:
        expected=reference_result(path,files,bytes_);actual=invoke(path,files,bytes_,1,'native')
        controls.append(dict(name=name,expected=expected,native=actual))
        assert comparable(actual['result'])==expected,(name,expected,actual)
    write(OUT/'controls.json',dict(status='passed',controls=controls,foreignUidTested=False,concurrentMutationTested=False,
        injectedSyscallFailuresTested=False,descriptorLimit=64,productionIntegration=False))

    original=read(PRIOR/'references/original-result.json');raw=Path(original['rawPath']);work=raw/'test_actual_original_matrix_import_and_cold_vault_history'
    worker=work/'supervisor'/original['originalAttemptId']
    identity=read(PRIOR/'references/original-raw-identity.json')['identity'];info=raw.lstat()
    assert stat.S_ISDIR(info.st_mode) and (info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode))==tuple(identity[key] for key in ('device','inode','uid','mode'))
    original_directory=read(PRIOR/'references/original-accounting.json')['launch']['descriptors']['attemptDirectory'];info=worker.lstat()
    assert (info.st_dev,info.st_ino)==(original_directory['device'],original_directory['inode'])
    for row in original['ownerAndWriterLocks']:
        fd=os.open(work/row['path'],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK);held.append(fd);info=os.fstat(fd)
        assert stat.S_ISREG(info.st_mode) and info.st_size==0 and info.st_nlink==1 and info.st_uid==os.getuid()
        assert (str(info.st_dev),str(info.st_ino))==(row['device'],row['inode'])
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(row)
    assert len(locks)==49
    tree=ast.parse((PRIOR/'evaluate.py').read_bytes());node=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='metadata')
    context=dict(os=os,Path=Path,stat=stat,worker=worker)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'<reviewed-metadata-inventory>','exec'),context)
    before=context['metadata']();assert before==read(PRIOR/'attempt01/metadata-after.json')
    write(OUT/'original-metadata-before.json',before)
    for number in range(7):
        order=('python','native') if number%2==0 else ('native','python')
        for mode in order:
            row=invoke(worker,8192,67108864,5,mode);row['round']=number
            assert comparable(row['result'])==dict(reason='OK',errno=0,files=3227,logicalBytes=11889866)
            assert row['result']['scans']==5 and row['result']['cpuMicroseconds']>0
            samples.append(row)
    after=context['metadata']();write(OUT/'original-metadata-after.json',after)
    assert before==after and denied==[]
except BaseException as caught:
    error=dict(type=type(caught).__name__,message=str(caught),traceback=traceback.format_exc()[-8192:])
finally:
    signal.setitimer(signal.ITIMER_REAL,0)
    for fd in reversed(held):os.close(fd)
unchanged=all((BASE/row['path']).stat().st_size==row['bytes'] and sha(BASE/row['path'])==row['sha256'] for row in inputs['files'])
receipt=dict(status='passed' if error is None and unchanged else 'failed',error=error,controls=controls,samples=samples,
    launches=launches,deniedEvents=denied,originalOwnerWriterLocks=locks,originalMetadataUnchanged=before is not None and before==after,
    sourceInputsUnchanged=unchanged,sourceInputsSha256=sha(BASE/'inputs.json'),binarySha256=sha(BASE/'build01/scan'),
    caseDatabaseReads=0,qualificationWorkersLaunched=0,productionChanged=False,foreignUidTested=False,
    concurrentMutationTested=False,injectedSyscallFailuresTested=False,pythonAuditCoversNativeSyscalls=False,
    fullToolchainClosureAttested=False,wholeWorkerTimingQualified=False)
if error is None:
    medians={mode:statistics.median(row['result']['cpuMicroseconds']/5 for row in samples if row['mode']==mode) for mode in ('python','native')}
    receipt['medianCpuMicrosecondsPerScan']=medians;receipt['nativeToPythonMedianCpuRatio']=medians['native']/medians['python']
    receipt['pairedCpuRatios']=[]
    for number in range(7):
        pair={row['mode']:row['result']['cpuMicroseconds'] for row in samples if row['round']==number}
        receipt['pairedCpuRatios'].append(pair['native']/pair['python'])
write(OUT/'result.json',receipt)
print(json.dumps({key:receipt[key] for key in ('status','originalMetadataUnchanged','medianCpuMicrosecondsPerScan','nativeToPythonMedianCpuRatio') if key in receipt}))
if error:print(json.dumps(error));raise SystemExit(1)
assert unchanged
