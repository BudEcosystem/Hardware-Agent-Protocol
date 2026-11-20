"""Retain bounded primary documentation; never execute acquired examples."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import time
import urllib.request

BASE=Path(__file__).resolve().parent
SOURCES=(
 ('linux-psi','https://docs.kernel.org/_sources/accounting/psi.rst.txt','rst'),
 ('linux-sched-stats','https://docs.kernel.org/_sources/scheduler/sched-stats.rst.txt','rst'),
 ('linux-getrusage','https://man7.org/linux/man-pages/man2/getrusage.2.html','html-pre'),
 ('linux-proc-pid-stat','https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html','html-pre'),
 ('python312-resource','https://docs.python.org/3.12/_sources/library/resource.rst.txt','rst'),
)
MAX_BYTES=2*1024*1024
class Pre(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.depth=0;self.parts=[];self.images=[]
    def handle_starttag(self,tag,attrs):
        if tag=='pre':
            if not self.depth:self.parts.append('\n')
            self.depth+=1
        if tag=='img':self.images.append(dict(attrs))
    def handle_endtag(self,tag):
        if tag=='pre' and self.depth:self.depth-=1;self.parts.append('\n')
    def handle_data(self,data):
        if self.depth:self.parts.append(data)
def write(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(body)
def fetch(item):
    name,url,kind=item
    request=urllib.request.Request(url,headers={'User-Agent':'HMS-research-retention/1.0'})
    with urllib.request.urlopen(request,timeout=25) as response:
        status=response.status;assert status==200
        body=response.read(MAX_BYTES+1);assert 0<len(body)<=MAX_BYTES
        final=response.url;headers=dict(response.headers)
    text=body.decode('utf-8');images=[]
    if kind=='html-pre':
        parser=Pre();parser.feed(text);parser.close();text=''.join(parser.parts).strip()+'\n';images=parser.images
        assert len(text)>1000 and name.split('linux-')[1].split('-')[0] in text.lower()
    else:assert not text.lstrip().startswith('<!DOCTYPE')
    suffix='.html' if kind=='html-pre' else '.rst.txt'
    raw=BASE/'raw'/(name+suffix);extracted=BASE/'text'/(name+'.txt')
    write(raw,body);encoded=text.encode('utf-8');write(extracted,encoded)
    return dict(id=name,requestedUrl=url,finalUrl=final,httpStatus=status,acquiredAtUnixNs=time.time_ns(),
        responseHeaders=headers,rawPath=raw.relative_to(BASE).as_posix(),rawBytes=len(body),rawSha256=hashlib.sha256(body).hexdigest(),
        textPath=extracted.relative_to(BASE).as_posix(),textBytes=len(encoded),textSha256=hashlib.sha256(encoded).hexdigest(),
        lfLines=len(text.split('\n'))-(1 if text.endswith('\n') else 0),extraction=kind,
        imageElements=images,readingStatus='unread',acquiredCodeExecuted=False)
with ThreadPoolExecutor(max_workers=5) as pool:rows=list(pool.map(fetch,SOURCES))
manifest=dict(scope='Primary documentation for a future bounded whole-worker diagnostic; no acquired code execution',sources=rows)
write(BASE/'acquisition.json',(json.dumps(manifest,indent=2)+'\n').encode())
print(json.dumps([dict(id=r['id'],bytes=r['textBytes'],lfLines=r['lfLines'],images=len(r['imageElements'])) for r in rows]))
