"""Acquire complete pinned manual sources as data; execute no acquired code."""
import base64
import hashlib
import json
from pathlib import Path
import urllib.request

HERE=Path(__file__).resolve().parent
BASE='https://kernel.googlesource.com/pub/scm/docs/man-pages/man-pages'
TAG='refs/tags/man-pages-6.19'

def acquire(url):
    with urllib.request.urlopen(url,timeout=30) as response:
        raw=response.read(2*1024**2+1)
        if len(raw)>2*1024**2:raise ValueError('source size bound')
        return raw,dict(url=url,finalUrl=response.url,status=response.status)

def main():
    metadata,request=acquire(BASE+'/+/'+TAG+'?format=JSON')
    with (HERE/'tag.json').open('xb') as f:f.write(metadata)
    commit=json.loads(metadata.removeprefix(b")]}'\n"))['commit']
    rows=[]
    for path in ['man/man2/statx.2','man/man2/statfs.2','man/man2/statmount.2','man/man5/proc_pid_mountinfo.5']:
        raw,receipt=acquire(BASE+'/+/'+commit+'/'+path+'?format=TEXT')
        body=base64.b64decode(raw,validate=True)
        with (HERE/Path(path).name).open('xb') as f:f.write(body)
        rows.append(dict(path=Path(path).name,upstreamPath=path,bytes=len(body),lfLines=body.count(b'\n'),
            sha256=hashlib.sha256(body).hexdigest(),transportSha256=hashlib.sha256(raw).hexdigest(),**receipt))
    with (HERE/'sources.json').open('x') as f:json.dump(dict(tag=TAG,commit=commit,tagRequest=request,files=rows),f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps(dict(commit=commit,files=len(rows),lfLines=sum(r['lfLines'] for r in rows)),sort_keys=True))

if __name__=='__main__':main()
