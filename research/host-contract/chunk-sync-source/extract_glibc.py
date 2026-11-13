"""Extract selected canonical glibc sources; no acquired code is executed."""
import hashlib,json,subprocess
from pathlib import Path
p=Path(__file__).resolve().parent;repo=p/'glibc-objects';commit='ef321e23c20eebc6d6fb4044425c00e6df27b05f'
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],timeout=10).decode().strip()==commit
rows=[]
for name in ['sysdeps/unix/sysv/linux/fsync.c','sysdeps/unix/sysv/linux/sync_file_range.c']:
 body=subprocess.check_output(['git','-C',str(repo),'show',commit+':'+name],timeout=30)
 dest=p/'glibc'/name;dest.parent.mkdir(parents=True,exist_ok=True)
 with dest.open('xb') as f:f.write(body)
 rows.append(dict(path=str(dest.relative_to(p)),revision=commit,bytes=len(body),lfLines=body.count(b'\n'),sha256=hashlib.sha256(body).hexdigest()))
with (p/'glibc-sources.json').open('x') as f:json.dump(dict(origin='https://sourceware.org/git/glibc.git',partialObjects=True,checkout=False,files=rows),f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(rows))
