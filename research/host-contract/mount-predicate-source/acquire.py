"""Pinned kernel/libc source acquisition only; no acquired builds or scripts."""
import base64
import hashlib
import json
from pathlib import Path
import urllib.request

HERE=Path(__file__).resolve().parent
SOURCES=[('linux','https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux','refs/tags/v7.0',
          ['fs/stat.c','fs/mount.h','fs/namespace.c','include/uapi/linux/stat.h','include/linux/stat.h']),
         ('glibc','https://gnu.googlesource.com/glibc','refs/tags/glibc-2.39',
          ['sysdeps/unix/sysv/linux/statx.c','io/statx_generic.c','sysdeps/unix/sysv/linux/bits/statx.h',
           'io/bits/statx-generic.h','io/bits/types/struct_statx.h'])]

def fetch(url):
    with urllib.request.urlopen(url,timeout=30) as response:
        body=response.read(4*1024**2+1)
        if len(body)>4*1024**2:raise ValueError('source size bound')
        return body,dict(url=url,finalUrl=response.url,status=response.status)

def main():
    rows=[];revisions=[]
    for label,base,tag,paths in SOURCES:
        folder=HERE/label;folder.mkdir()
        raw,request=fetch(base+'/+/'+tag+'?format=JSON')
        with (folder/'tag.json').open('xb') as f:f.write(raw)
        commit=json.loads(raw.removeprefix(b")]}'\n"))['commit']
        revisions.append(dict(name=label,base=base,tag=tag,commit=commit,request=request))
        for path in paths:
            raw,request=fetch(base+'/+/'+commit+'/'+path+'?format=TEXT')
            body=base64.b64decode(raw,validate=True)
            target=folder/path;target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as f:f.write(body)
            rows.append(dict(path=str(target.relative_to(HERE)),bytes=len(body),lfLines=body.count(b'\n'),
                sha256=hashlib.sha256(body).hexdigest(),transportSha256=hashlib.sha256(raw).hexdigest(),**request))
    with (HERE/'sources.json').open('x') as f:json.dump(dict(revisions=revisions,files=rows),f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps(dict(revisions=revisions,files=len(rows),lfLines=sum(r['lfLines'] for r in rows)),sort_keys=True))

if __name__=='__main__':main()
