"""Retain the initial 404; finish libc acquisition from its canonical Git remote."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
GLIBC='ef321e23c20eebc6d6fb4044425c00e6df27b05f'
LINUX=json.loads((HERE/'linux/tag.json').read_bytes().removeprefix(b")]}'\n"))['commit']
paths=['sysdeps/unix/sysv/linux/statx.c','io/statx_generic.c','sysdeps/unix/sysv/linux/bits/statx.h',
       'io/bits/statx-generic.h','io/bits/types/struct_statx.h']
repo=HERE/'glibc-objects'
head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],timeout=10).decode().strip()
assert head==GLIBC
for path in paths:
    body=subprocess.check_output(['git','-C',str(repo),'show',GLIBC+':'+path],timeout=30)
    assert len(body)<1024**2
    target=HERE/'glibc'/path;target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as f:f.write(body)
rows=[]
for group in ['linux','glibc']:
    for path in sorted((HERE/group).rglob('*')):
        if path.is_file() and path.name!='tag.json':
            body=path.read_bytes();rows.append(dict(path=str(path.relative_to(HERE)),bytes=len(body),lfLines=body.count(b'\n'),
                sha256=hashlib.sha256(body).hexdigest(),revision=LINUX if group=='linux' else GLIBC))
output=dict(files=rows,linux=dict(commit=LINUX,tag='v7.0',origin='https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux'),
    glibc=dict(commit=GLIBC,tag='glibc-2.39',tagObject='9609a435f3f9a07c1cf607ad5821b12f735abd69',origin='https://sourceware.org/git/glibc.git',
    checkout=False,partialObjectAcquisition=True),initialAcquisitionFailure=dict(url='https://gnu.googlesource.com/glibc/+/refs/tags/glibc-2.39?format=JSON',
    status=404,linuxFilesRetained=5),acquiredCodeExecuted=False)
with (HERE/'sources.json').open('x') as f:json.dump(output,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(dict(files=len(rows),lfLines=sum(r['lfLines'] for r in rows)),sort_keys=True))
