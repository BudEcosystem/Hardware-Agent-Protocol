"""One owned isolated pure-evaluation child; preserve every original result."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

BASE=Path(__file__).resolve().parent
def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream: json.dump(value,stream,indent=2);stream.write('\n')
def verify():
    rows=read(BASE/'inputs.json')['files']
    for row in rows:
        path=BASE/row['path']
        assert not path.is_symlink() and path.stat().st_size==row['bytes']<=16777216 and sha(path)==row['sha256']
    return rows
before=verify(); inputs_pin=sha(BASE/'inputs.json')
attempt=BASE/'attempt01'; attempt.mkdir()
write(attempt/'inputs-before.json',before)
environment={'PATH':'/usr/bin:/bin','LC_ALL':'C.UTF-8','TZ':'UTC'}
command=[sys.executable,'-I','-S','-B',str(BASE/'child.py')]
write(attempt/'command.json',dict(argv=command,cwd=str(BASE),environment=environment,
    wallLimitSeconds=60,cpuLimitSeconds=30,retainedOutputLimitBytes=4194304,
    inputIndexSha256=inputs_pin,pythonExecutableSha256=sha(Path(sys.executable).resolve())))
process=None; result=dict(status='preparing',currentPass=False,goalStatus='active'); start=time.monotonic()
try:
    process=subprocess.Popen(command,cwd=BASE,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    write(attempt/'owned-child.json',dict(pid=process.pid,ownedByThisAttempt=True))
    try:
        stdout,stderr=process.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        process.kill();stdout,stderr=process.communicate(timeout=5)
        result['timedOut']=True
    assert len(stdout)+len(stderr)<=4194304
    with (attempt/'stdout.json').open('xb') as stream:stream.write(stdout)
    with (attempt/'stderr.log').open('xb') as stream:stream.write(stderr)
    result['exitCode']=process.returncode
    result['childState']='exited'
    if process.returncode==0 and not stderr and not result.get('timedOut'):
        report=json.loads(stdout)
        assert report['status']=='passed' and not report['prohibitedAttempts'] and report['inputsUnchanged']
        result.update(status='passed',currentPass=True,differentialCases=report['differentialCases'],
            candidateToReferenceMedianCpuRatio=report['candidateToReferenceMedianCpuRatio'])
    else:result['status']='failed'
except BaseException as error:
    result.update(status='failed',currentPass=False,errorType=type(error).__name__,errorMessage=str(error)[:4096])
finally:
    if process is not None and process.poll() is None:
        process.kill();process.wait(timeout=5)
    result['elapsedSeconds']=time.monotonic()-start
    result['inputIndexUnchanged']=sha(BASE/'inputs.json')==inputs_pin
    after=verify();write(attempt/'inputs-after.json',after)
    result['inputsUnchanged']=before==after
    result['currentPass']=result['currentPass'] and result['inputsUnchanged'] and result['inputIndexUnchanged']
    if not result['currentPass']:result['status']='failed'
    write(attempt/'result.json',result)
print(json.dumps(result))
raise SystemExit(0 if result['currentPass'] else 1)
