"""Preserve an interrupted scope without opening its databases or restarting it."""
import hashlib
import json
import os
from pathlib import Path
import stat

BASE = Path(__file__).resolve().parent
OLD = BASE / 'harness07'
NEW = BASE / 'harness13'
ATTEMPT = OLD / 'attempts/attempt01'
FORENSIC = BASE / 'interruption07'

def sha(path):
    assert path.is_file() and not path.is_symlink() and path.stat().st_size <= 16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream: stream.write(body if type(body) is bytes else body.encode())
def dump(path, value): write(path,json.dumps(value,indent=2)+'\n')
def identity(path):
    s=path.lstat(); return [s.st_dev,s.st_ino,s.st_uid,stat.S_IMODE(s.st_mode)]

started=json.loads((ATTEMPT/'started.json').read_bytes())
config=json.loads((ATTEMPT/'child-config.json').read_bytes())
assert started['pid']==60357 and not Path('/proc/60357').exists()
assert not (ATTEMPT/'result.json').exists()
raw=Path(config['scratch']); assert raw.is_dir() and not raw.is_symlink()
original_identity=identity(raw)
FORENSIC.mkdir()
partial=[]
for path in sorted(ATTEMPT.rglob('*')):
    assert not path.is_symlink()
    if path.is_file(): partial.append(dict(path=path.relative_to(ATTEMPT).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
raw_files=[]; total=0
for path in sorted(raw.rglob('*')):
    assert not path.is_symlink()
    if not path.is_file(): assert path.is_dir(); continue
    s=path.stat(); total+=s.st_size; assert total<=268435456 and len(raw_files)<8192
    row=dict(path=path.relative_to(raw).as_posix(),bytes=s.st_size,sha256=sha(path))
    target=FORENSIC/'scratch'/row['path']; write(target,path.read_bytes()); target.chmod(stat.S_IMODE(s.st_mode))
    assert sha(target)==sha(path)==row['sha256'] and target.stat().st_size==s.st_size
    raw_files.append(row)
assert identity(raw)==original_identity
assert {p.relative_to(raw).as_posix() for p in raw.rglob('*') if p.is_file()}=={r['path'] for r in raw_files}
for row in raw_files: assert sha(raw/row['path'])==row['sha256']
dump(FORENSIC/'observation.json',dict(status='interrupted-unverified',scope='harness07',toolSession=50123,
    toolExecutionExitCode=143,childExitCode=None,recordedChildPid=60357,childAbsent=True,
    parentAndChildCommandsAbsentFromProcessTable=True,finalReceiptsAbsent=True,
    cause='Not established; tool returned exit 143 without final receipts and recorded processes were absent',
    rawPath=str(raw),rawIdentity=original_identity,rawRetained=True,rawFiles=raw_files,rawBytes=total,
    retainedAttemptFiles=partial,databasesOpened=False,stateRepaired=False,originalAttemptRestarted=False,
    continuation='harness13: identical methods, production and bounds in fresh state'))
NEW.mkdir()
for row in json.loads((OLD/'index.json').read_bytes())['files']:
    path=OLD/row['path']; assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
    if row['path'] in ('README.md','SCOPE.md'): continue
    write(NEW/row['path'],path.read_bytes())
write(NEW/'README.md','# Fresh continuation of scope 07\n\n[Targets](targets.json), [bounds](SCOPE.md), [source](../implementation01/README.md). The interrupted original remains unverified; its partial state is preserved separately.\n')
write(NEW/'SCOPE.md',(OLD/'SCOPE.md').read_text()+'\nFresh state follows confirmed absence of the interrupted parent and child. The original partial databases were copied without opening, recovering or repairing them. No original completed test or child exit status is invented.\n')
files=[dict(path=p.relative_to(NEW).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(NEW.rglob('*')) if p.is_file()]
dump(NEW/'index.json',dict(scope='Fresh continuation; interrupted scope 07 and raw state preserved separately',files=files))
print(json.dumps(dict(interrupted='harness07',continuation='harness13',rawFiles=len(raw_files),rawBytes=total,databasesOpened=False)))
