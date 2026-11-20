"""One owned bounded child; retain every result and fresh test-state file."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[3]
SOURCE=BASE.parent/'implementation03';ATTEMPT=BASE/'attempts/attempt01'
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert not ATTEMPT.exists()
assert sha(SOURCE/'index.json')=='2f1d6c5aeaf63e960058f9b838b5ecd1080fc17d78f207f0d0b14c248da2dad4'
inputs=read(SOURCE/'index.json')['files']
for row in inputs:
    path=ROOT/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
harness=read(BASE/'index.json')
for row in harness['files']:
    path=BASE/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
ATTEMPT.mkdir(parents=True,mode=0o700);(ATTEMPT/'scratch').mkdir(mode=0o700)
argv=[sys.executable,'-I','-S','-B',str(BASE/'child.py'),str(ATTEMPT)]
started=time.monotonic_ns();timed_out=False
with (ATTEMPT/'stdout.log').open('xb') as stdout,(ATTEMPT/'stderr.log').open('xb') as stderr:
    child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,cwd=ROOT,
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONHASHSEED':'0'})
    write(ATTEMPT/'launch.json',dict(pid=child.pid,argv=argv,sourceIndexSha256=sha(SOURCE/'index.json'),
        harnessIndexSha256=sha(BASE/'index.json'),maxWallSeconds=60,childOwnedByPopen=True))
    try:code=child.wait(timeout=60)
    except subprocess.TimeoutExpired:
        timed_out=True;child.kill();code=child.wait(timeout=5)
elapsed=time.monotonic_ns()-started
unchanged=True
for row in inputs:
    path=ROOT/row['path'];unchanged&=path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
for row in harness['files']:
    path=BASE/row['path'];unchanged&=path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
child_result=read(ATTEMPT/'child-result.json') if (ATTEMPT/'child-result.json').exists() else None
files=[]
for parent,dirs,names in os.walk(ATTEMPT/'scratch',followlinks=False):
    for name in dirs:assert not (Path(parent)/name).is_symlink()
    for name in names:
        path=Path(parent)/name;info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_size<=8*1024*1024
        files.append(dict(path=str(path.relative_to(ATTEMPT/'scratch')),bytes=info.st_size,sha256=sha(path)))
assert len(files)<=1024 and sum(row['bytes'] for row in files)<=32*1024*1024
write(ATTEMPT/'scratch-index.json',sorted(files,key=lambda row:row['path']))
passed=code==0 and not timed_out and unchanged and child_result is not None and child_result['status']=='passed'
result=dict(status='passed' if passed else 'failed',exitCode=code,childState='exited',timedOut=timed_out,
    elapsedNanoseconds=elapsed,inputsUnchanged=bool(unchanged),retainedFiles=len(files),retainedBytes=sum(row['bytes'] for row in files),
    childResultSha256=sha(ATTEMPT/'child-result.json') if child_result is not None else None,
    sourceIndexSha256=sha(SOURCE/'index.json'),harnessIndexSha256=sha(BASE/'index.json'),
    fullWorkerExecuted=False,catalogIntegrated=False,physicalObjectiveVerified=False)
write(ATTEMPT/'result.json',result);print(json.dumps(result))
raise SystemExit(0 if passed else 1)
