#!/usr/bin/env python3
"""Acquire public W3C document bytes; never execute acquired scripts."""
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urljoin
import hashlib,json,datetime,concurrent.futures
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[2]; BASE=ROOT/'research/wot-architecture'
def sha(b):return hashlib.sha256(b).hexdigest()
def get(url,path):
 with urlopen(Request(url,headers={'User-Agent':'HMS-primary-source-research/1.0'}),timeout=90) as r:
  b=r.read(); headers=dict(r.headers); status=r.status; final=r.url
 path.write_bytes(b)
 return {'url':url,'final_url':final,'http_status':status,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'raw_path':str(path.relative_to(ROOT)),'sha256':sha(b),'bytes':len(b),'headers':headers}
def source(sid,url):
 p=BASE/'raw'/f'{sid}.html'; row=get(url,p); soup=BeautifulSoup(p.read_bytes(),'html.parser')
 for tag in soup(['script','style']):tag.decompose()
 b=('\n'.join(soup.stripped_strings)+'\n').encode(); textpath=BASE/'text'/f'{sid}.txt';textpath.write_bytes(b)
 row.update(id=sid,status='acquired',text_path=str(textpath.relative_to(ROOT)),text_sha256=sha(b),text_bytes=len(b),text_lf_lines=b.count(b'\n'),extraction='BeautifulSoup html.parser; remove script/style nodes; join stripped_strings with LF and final LF; no semantic content selectors')
 return row
sources=[('architecture-11-rec','https://www.w3.org/TR/2023/REC-wot-architecture11-20231205/'),('latest-alias','https://www.w3.org/TR/wot-architecture/'),('latest-11-alias','https://www.w3.org/TR/wot-architecture11/'),('publication-history','https://www.w3.org/standards/history/wot-architecture11/'),('errata-11','https://w3c.github.io/wot-architecture/errata11.html'),('editors-draft','https://w3c.github.io/wot-architecture/')]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(lambda x:source(*x),sources))
(BASE/'manifest.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
soup=BeautifulSoup((BASE/'raw/architecture-11-rec.html').read_bytes(),'html.parser'); figures=[]
for i,f in enumerate(soup.find_all('figure'),1):
 imgs=[]
 for j,img in enumerate(f.find_all('img'),1):
  src=img.get('src');suffix=Path(src).suffix;p=BASE/'figures'/f'{i:02d}-{j}{suffix}'
  imgs.append(dict(get(urljoin(sources[0][1],src),p),src=src,alt=img.get('alt')))
 figures.append({'number':i,'html_id':f.get('id'),'caption':f.find('figcaption').get_text(' ',strip=True),'images':imgs})
tables=[]
for i,t in enumerate(soup.find_all('table'),1):
 rows=[[c.get_text(' ',strip=True) for c in tr.find_all(['th','td'],recursive=False)] for tr in t.find_all('tr')]
 tables.append({'number':i,'html_id':t.get('id'),'rows':rows})
(BASE/'metadata/figure-inventory.json').write_text(json.dumps(figures,indent=2)+'\n')
(BASE/'metadata/table-inventory.json').write_text(json.dumps(tables,indent=2)+'\n')
print(json.dumps({'acquisitions':len(sources),'figures':len(figures),'figure_assets':sum(len(f['images']) for f in figures),'tables':len(tables)}))
