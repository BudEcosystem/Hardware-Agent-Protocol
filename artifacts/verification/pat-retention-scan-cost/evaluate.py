"""One fixed metadata-only evaluation; no project import or worker process."""
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import statistics
import sys
import sysconfig
import time
import traceback

BASE=Path(__file__).resolve().parent
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    body=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
    assert len(body)<=16777216
    with path.open('xb') as stream:stream.write(body)
expected=read(BASE/'inputs.json')
for row in expected['files']:
    path=BASE/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
OUT=BASE/'attempt01';OUT.mkdir(mode=0o700,exist_ok=False)
resource.setrlimit(resource.RLIMIT_CPU,(30,30))
resource.setrlimit(resource.RLIMIT_FSIZE,(16777216,16777216))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def expired(*args):raise TimeoutError('Original 60-second evaluation wall timer elapsed')
signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,60)
preparation=read(BASE/'preparation.json');previous=read(BASE/'references/original-result.json')
accounting=read(BASE/'references/original-accounting.json');config=read(BASE/'references/original-child-config.json')
raw=Path(previous['rawPath']);work=raw/'test_actual_original_matrix_import_and_cold_vault_history'
worker=work/'supervisor'/previous['originalAttemptId']
launch=read(BASE/'references/original-input.json');archive=read(BASE/'references/original-worker-archive.json')['record']
assert launch['attemptId']==archive['attemptId']==previous['originalAttemptId']
limits=launch['request']['limits'];expected_usage=archive['archive']['usage']
assert expected_usage==dict(files=3227,logicalBytes=11889866,totalDiskQuotaEnforced=False)
assert limits['maxFilesPerAttempt']==8192 and limits['attemptReservationBytes']==67108864
environment=dict(__name__='exact_original_scan_probe',os=os,stat=stat,Path=Path,sys=sys,re=re,hashlib=hashlib,
    MAX_FILE=16777216,MAX_ORIGINS=8192,config=config,scratch=raw,current_test=config['targets'][0],
    accounting_launch_audit=[],sqlite_connections=[],prohibited=[],executed=set(),resource_reads=set(),denied_bytecode=set(),
    root=Path(config['project']),own_path=BASE/'references/attempt_child.py',stdlib=Path(sysconfig.get_path('stdlib')).resolve(),
    acquired={str((Path(config['project'])/row['path']).resolve()):row['sha256'] for row in config['expectedInputs']},
    external={row['resolvedPath']:row['sha256'] for row in config['expectedExternalInputs']})
nodes=[]
for row in preparation['extracted']:
    module=ast.parse((BASE/'references'/row['source']).read_bytes())
    node=next(node for node in module.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name==row['name'])
    assert hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()==row['astSha256']
    nodes.append(node)
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'<exact-original-scan>','exec'),environment)
tree_usage=environment['tree_usage'];original_audit=environment['audit']
probe_mode=None;events={};denied=[]
def common_audit(event,args):
    if probe_mode is None:return
    events[event]=events.get(event,0)+1
    if event=='open':
        flags=args[2]
        if (type(flags)is not int or flags & os.O_ACCMODE != os.O_RDONLY or
                not flags & os.O_DIRECTORY or not flags & os.O_NOFOLLOW or
                flags & (os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
            denied.append(event);raise RuntimeError('Only original read-only directory opens are permitted')
    elif event!='os.scandir':
        denied.append(event);raise RuntimeError('Unexpected event in metadata-only evaluation: '+event)
    if probe_mode=='original-audit':original_audit(event,args)
sys.addaudithook(common_audit)

def metadata():
    records=[]
    for parent,directories,files in os.walk(worker,followlinks=False):
        assert len(Path(parent).relative_to(worker).parts)<=10
        for name in sorted(directories+files):
            path=Path(parent)/name;info=path.lstat()
            assert stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)
            records.append(dict(path=path.relative_to(worker).as_posix(),device=info.st_dev,inode=info.st_ino,
                mode=info.st_mode,uid=info.st_uid,gid=info.st_gid,nlink=info.st_nlink,size=info.st_size,
                mtimeNs=info.st_mtime_ns,ctimeNs=info.st_ctime_ns))
            assert len(records)<=8192
    return sorted(records,key=lambda row:row['path'])

held=[];locks=[];samples=[];warm=[];before=None;after=None;error=None
started=time.monotonic_ns()
try:
    raw_identity=read(BASE/'references/original-raw-identity.json')['identity'];info=raw.lstat()
    assert stat.S_ISDIR(info.st_mode)
    assert (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==tuple(raw_identity[key] for key in ('device','inode','uid','gid','mode'))
    for row in previous['ownerAndWriterLocks']:
        path=work/row['path'];fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        held.append(fd);info=os.fstat(fd)
        assert stat.S_ISREG(info.st_mode) and info.st_size==0 and info.st_nlink==1 and info.st_uid==os.getuid()
        assert (str(info.st_dev),str(info.st_ino))==(row['device'],row['inode'])
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(row)
    assert len(locks)==49
    original_directory=accounting['launch']['descriptors']['attemptDirectory'];info=worker.lstat()
    assert stat.S_ISDIR(info.st_mode) and (info.st_dev,info.st_ino)==(original_directory['device'],original_directory['inode'])
    assert archive['lease']=={key:str(accounting['launch']['descriptors']['writerLease'][key]) for key in ('device','inode')}
    before=metadata();write(OUT/'metadata-before.json',before)
    directory_count=1+sum(stat.S_ISDIR(row['mode']) for row in before)
    assert len(before)==3227 and sum(row['size'] for row in before if stat.S_ISREG(row['mode']))==11889866
    write(OUT/'started.json',dict(originalRawIdentity=raw_identity,locks=locks,worker=str(worker),
        originalAttemptId=previous['originalAttemptId'],maximumWallSeconds=60,maximumCpuSeconds=30,
        pairs=7,scansPerSample=5,warmScansPerMode=1,expectedDirectoryOpensPerScan=directory_count))
    def scan(mode,count,round_number):
        global probe_mode,events
        events={};probe_mode=mode
        cpu=time.process_time_ns();wall=time.monotonic_ns()
        try:
            for _ in range(count):
                actual=tree_usage(worker,max_files=limits['maxFilesPerAttempt'],max_bytes=limits['attemptReservationBytes'])
                assert actual==expected_usage
        finally:
            wall=time.monotonic_ns()-wall;cpu=time.process_time_ns()-cpu;probe_mode=None
        assert events=={'open':directory_count*count,'os.scandir':directory_count*count},events
        return dict(mode=mode,round=round_number,scans=count,cpuNanoseconds=cpu,wallNanoseconds=wall,events=dict(events),usage=actual)
    for mode in ('without-original-audit','original-audit'):warm.append(scan(mode,1,-1))
    for round_number in range(7):
        order=('without-original-audit','original-audit') if round_number%2==0 else ('original-audit','without-original-audit')
        for mode in order:samples.append(scan(mode,5,round_number))
    after=metadata();write(OUT/'metadata-after.json',after)
    assert after==before and not denied and not environment['prohibited']
    assert not environment['executed'] and not environment['resource_reads'] and not environment['denied_bytecode']
except BaseException as caught:
    error=dict(type=type(caught).__name__,message=str(caught),traceback=traceback.format_exc()[-8192:])
finally:
    probe_mode=None
    signal.setitimer(signal.ITIMER_REAL,0)
    for fd in reversed(held):os.close(fd)
elapsed=time.monotonic_ns()-started
source_after=[]
for row in expected['files']:
    path=BASE/row['path'];source_after.append(dict(path=row['path'],bytes=path.stat().st_size,sha256=sha(path)))
assert source_after==expected['files']
receipt=dict(status='passed' if error is None else 'failed',error=error,samples=samples,warmScans=warm,
    elapsedNanoseconds=elapsed,metadataUnchanged=before is not None and after==before,
    ownerWriterLocks=locks,deniedEvents=denied,originalAuditProhibitedEvents=environment['prohibited'],
    sourceInputsUnchanged=True,sourceInputsSha256=sha(BASE/'inputs.json'),
    sqliteConnections=0,caseDatabaseReads=0,workerProcessesLaunched=0,productionChanged=False,
    liveGrowingTreeMeasured=False,timeoutCauseEstablished=False,commonGuardInBothModes=True)
if error is None:
    medians={mode:statistics.median(row['cpuNanoseconds']/row['scans'] for row in samples if row['mode']==mode)
        for mode in ('without-original-audit','original-audit')}
    receipt['medianCpuNanosecondsPerScan']=medians
    receipt['originalAuditToWithoutMedianCpuRatio']=medians['original-audit']/medians['without-original-audit']
    receipt['pairedCpuRatios']=[]
    for round_number in range(7):
        pair={row['mode']:row for row in samples if row['round']==round_number}
        receipt['pairedCpuRatios'].append(pair['original-audit']['cpuNanoseconds']/pair['without-original-audit']['cpuNanoseconds'])
write(OUT/'result.json',receipt)
print(json.dumps({key:receipt[key] for key in ('status','metadataUnchanged','workerProcessesLaunched','medianCpuNanosecondsPerScan','originalAuditToWithoutMedianCpuRatio') if key in receipt}))
if error:print(json.dumps(error));raise SystemExit(1)
