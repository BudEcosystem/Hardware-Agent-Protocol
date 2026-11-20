"""Retain exact candidate selection/child; change only harness placement/capture."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
OLD=ROOT/'artifacts/implementation/supervisor-storage-bindings'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('xb') as stream:stream.write(v if type(v) is bytes else (v if type(v) is str else json.dumps(v,indent=2)+'\n').encode())
assert sha(OLD/'index.json')=='088c3474ae31d3d3aee38d787ec3b84b0d5cce3f8896335ac53ae6eea02d53dd'
for r in json.loads((OLD/'index.json').read_bytes())['files']:
    p=OLD/r['path'];assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
for name in ('control_child.py','control-selection.json','external-inputs.json'):
    write(BASE/name,(OLD/name).read_bytes())
before=(OLD/'run_controls.py').read_text()
after=before.replace('import hashlib','import fcntl\nimport stat\nimport tempfile\nimport hashlib',1)
after=after.replace("SOURCE=BASE/'implementation01'", "SOURCE=ROOT/'artifacts/implementation/supervisor-storage-bindings/implementation01'")
setup='''    scratch_parent=Path('/tmp');parent_identity=identity(scratch_parent)
    assert parent_identity['uid'] in (0,os.getuid()) and (not parent_identity['mode']&0o022 or parent_identity['sticky'])
    scratch=Path(tempfile.mkdtemp(prefix='hms-split-controls-',dir=str(scratch_parent)))
    scratch_identity=identity(scratch)
    assert scratch_identity['uid']==os.getuid() and scratch_identity['mode']==0o700
    assert identity(scratch_parent)==parent_identity
    write(out/'raw-scratch-before.json',dict(path=str(scratch),identity=scratch_identity,parentIdentity=parent_identity,
        policy='Original raw scratch retained; copied bindings are evidence only'))'''
assert before.count("    scratch=out/'scratch';scratch.mkdir(mode=0o700)")==1
after=after.replace("    scratch=out/'scratch';scratch.mkdir(mode=0o700)",setup)
helper='''def identity(path):
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
'''
after=after.replace("frozen=read(SOURCE/'index.json')",helper+"frozen=read(SOURCE/'index.json')")
capture='''    after=inventory(project);verify()
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
        for fd in leases:os.close(fd)'''
assert after.count('    after=inventory(project);retained=inventory(scratch);verify()')==1
after=after.replace('    after=inventory(project);retained=inventory(scratch);verify()',capture)
ast.parse(after)
write(BASE/'run_controls.py',after)
write(BASE/'control-harness.patch',''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='stage89/run_controls.py',tofile='stage90/run_controls.py')))
write(BASE/'control-release.json',dict(reviewer='primary-agent',independentReview=False,
    sourceIndexSha256=sha(OLD/'implementation01/index.json'),oldStageIndexSha256=sha(OLD/'index.json'),
    unchangedCandidate=True,unchangedControlChild=sha(BASE/'control_child.py')==sha(OLD/'control_child.py'),
    unchangedSelection=sha(BASE/'control-selection.json')==sha(OLD/'control-selection.json'),
    controlScopes=14,controlTests=71,wallSeconds=60,cpuSeconds=40,memoryBytes=512*1024*1024,fdLimit=128,
    fileBytes=16*1024*1024,scratchBytes=256*1024*1024,rawScratchKept=True,physicalExecution=False))
files=[dict(path=p.relative_to(BASE).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(BASE.iterdir()) if p.is_file()]
write(BASE/'control-harness-index.json',dict(files=files))
print(json.dumps(dict(harnessIndexSha256=sha(BASE/'control-harness-index.json'),files=len(files),tests=71)))
