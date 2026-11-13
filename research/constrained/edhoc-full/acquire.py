#!/usr/bin/env python3
"""Download primary documents as data; execute none of their content."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, urllib.request
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[3]; BASE=Path(__file__).resolve().parent
SOURCES=[
 ('rfc9528-text','https://www.rfc-editor.org/rfc/rfc9528.txt','txt'),
 ('rfc9528-pdf','https://www.rfc-editor.org/rfc/rfc9528.pdf','pdf'),
 ('rfc9528-metadata','https://www.rfc-editor.org/rfc/rfc9528.json','json'),
 ('rfc9528-errata','https://www.rfc-editor.org/errata/rfc9528','html'),
 ('rfc9528-status','https://www.rfc-editor.org/info/rfc9528','html'),
 ('iana-edhoc','https://www.iana.org/assignments/edhoc/edhoc.xml','xml')]
def get(source):
 name,url,ext=source; when=datetime.now(timezone.utc).isoformat()
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'HMS primary-source archive'}),timeout=45) as response:
   raw=response.read(); final=response.url; headers=dict(response.headers)
  path=BASE/'raw'/f'{name}.{ext}';path.write_bytes(raw)
  row=dict(id=name,url=url,final_url=final,retrieved_at=when,status='downloaded',raw_path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),response_headers=headers)
  if ext=='txt':text=raw
  elif ext=='json':text=(json.dumps(json.loads(raw),indent=2,ensure_ascii=False)+'\n').encode()
  elif ext=='html':
   soup=BeautifulSoup(raw,'html.parser')
   for node in soup(['script','style','nav']):node.decompose()
   node=soup.find('main') or soup.find(id='content') or soup.body or soup
   text=(node.get_text('\n',strip=True)+'\n').encode()
  elif ext=='xml':text=raw
  else:text=None
  if text is not None:
   out=BASE/'text'/f'{name}.txt';out.write_bytes(text);row.update(text_path=str(out.relative_to(ROOT)),text_sha256=hashlib.sha256(text).hexdigest())
  return row
 except Exception as error:return dict(id=name,url=url,retrieved_at=when,status='failed',error=repr(error))
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(get,SOURCES))
 (BASE/'manifest.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
 print(json.dumps([{k:r.get(k) for k in ('id','status','bytes','error')} for r in rows]))
