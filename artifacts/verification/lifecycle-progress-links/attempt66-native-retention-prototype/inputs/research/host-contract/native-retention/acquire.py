"""Acquire primary directory-traversal manuals; do not execute any example."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import time
import urllib.request

BASE=Path(__file__).resolve().parent
SOURCES=(('fdopendir','man3/fdopendir.3'),('readdir','man3/readdir.3'),
    ('fstatat','man2/fstatat.2'),('open','man2/open.2'),('closedir','man3/closedir.3'),
    ('dirfd','man3/dirfd.3'),('dup','man2/dup.2'),('getuid','man2/getuid.2'))
class Manual(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.pre=0;self.omit=0;self.text=[];self.outside=[];self.images=[]
    def handle_starttag(self,tag,attrs):
        if tag=='pre':self.pre+=1;self.text.append('\n')
        if tag in ('script','style'):self.omit+=1
        if tag=='img':self.images.append(dict(attrs))
    def handle_endtag(self,tag):
        if tag=='pre':self.pre-=1;self.text.append('\n')
        if tag in ('script','style'):self.omit-=1
    def handle_data(self,value):
        if self.pre:self.text.append(value)
        elif not self.omit and value.strip():self.outside.append(value.strip())
def write(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(body)
def fetch(item):
    name,relative=item;url='https://man7.org/linux/man-pages/'+relative+'.html'
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'HMS-research-retention/1.0'}),timeout=25) as response:
        assert response.status==200;body=response.read(2097153);assert 0<len(body)<=2097152
        final=response.url;headers=dict(response.headers)
    parser=Manual();parser.feed(body.decode('utf-8'));parser.close();assert parser.pre==parser.omit==0
    text=''.join(parser.text).strip()+'\n';outside=' | '.join(parser.outside)+'\n';encoded=text.encode()
    write(BASE/'raw'/(name+'.html'),body);write(BASE/'text'/(name+'.txt'),encoded)
    write(BASE/'surrounding'/(name+'.txt'),outside.encode())
    return dict(id=name,requestedUrl=url,finalUrl=final,acquiredUnixNs=time.time_ns(),headers=headers,
        rawPath='raw/'+name+'.html',rawBytes=len(body),rawSha256=hashlib.sha256(body).hexdigest(),
        textPath='text/'+name+'.txt',textBytes=len(encoded),textSha256=hashlib.sha256(encoded).hexdigest(),
        lfLines=text.count('\n'),surroundingPath='surrounding/'+name+'.txt',surroundingSha256=hashlib.sha256(outside.encode()).hexdigest(),
        images=parser.images,readingStatus='unread',acquiredCodeExecuted=False)
with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(fetch,SOURCES))
write(BASE/'acquisition.json',(json.dumps(dict(scope='Native retention helper source research',sources=rows),indent=2)+'\n').encode())
print(json.dumps([dict(id=row['id'],lfLines=row['lfLines'],textBytes=row['textBytes'],images=len(row['images'])) for row in rows]))
