"""Pinned primary-source download only; no acquired code execution."""
from concurrent.futures import ThreadPoolExecutor
import base64,hashlib,json,os,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
K='028ef9c96e96197026887c0f092424679298aae8'
M='adb436b2e4471218021d86f188fb58dec3946eb8'
files=[('linux',K,'fs/sync.c'),('linux',K,'fs/ext4/fsync.c'),('linux',K,'mm/filemap.c'),
       ('linux',K,'Documentation/filesystems/ext4/journal.rst'),('man-pages',M,'man/man2/fsync.2')]
def fetch(row):
 family,rev,name=row
 base='https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux' if family=='linux' else 'https://kernel.googlesource.com/pub/scm/docs/man-pages/man-pages'
 url=base+'/+/'+rev+'/'+name+'?format=TEXT'
 with urllib.request.urlopen(url,timeout=30) as reply:
  encoded=reply.read(2*1024*1024+1)
 assert len(encoded)<=2*1024*1024
 body=base64.b64decode(encoded);target=ROOT/family/name;target.parent.mkdir(parents=True,exist_ok=True)
 with target.open('xb') as f:f.write(body);f.flush();os.fsync(f.fileno())
 return dict(path=str(target.relative_to(ROOT)),url=url,revision=rev,bytes=len(body),lfLines=body.count(b'\n'),sha256=hashlib.sha256(body).hexdigest())
with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(fetch,files))
with (ROOT/'sources.json').open('x') as f:json.dump(dict(files=rows,acquiredCodeExecuted=False),f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(rows,sort_keys=True))
