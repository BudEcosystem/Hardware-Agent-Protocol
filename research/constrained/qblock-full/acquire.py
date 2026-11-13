#!/usr/bin/env python3
"""Acquire immutable snapshots for archival reading; executes no source code."""
from datetime import datetime, timezone
import hashlib, json, subprocess
from pathlib import Path
import requests
from bs4 import BeautifulSoup
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
SOURCES=[
 ('rfc9177-text','https://www.rfc-editor.org/rfc/rfc9177.txt','txt','RFC 9177, March 2022'),
 ('rfc9177-pdf','https://www.rfc-editor.org/rfc/rfc9177.pdf','pdf','RFC 9177, March 2022'),
 ('rfc9177-metadata','https://www.rfc-editor.org/rfc/rfc9177.json','json','RFC Editor metadata snapshot'),
 ('rfc9177-errata','https://www.rfc-editor.org/errata/rfc9177','html','RFC Editor errata snapshot'),
 ('iana-core-status','https://www.iana.org/assignments/core-parameters/core-parameters.xhtml','html','IANA CoRE registry snapshot'),
 ('iana-options','https://www.iana.org/assignments/core-parameters/option-numbers.csv','csv','IANA CoAP Option Numbers snapshot'),
 ('iana-content-formats','https://www.iana.org/assignments/core-parameters/content-formats.csv','csv','IANA CoAP Content-Formats snapshot'),
 ('iana-missing-blocks','https://www.iana.org/assignments/media-types/application/missing-blocks+cbor-seq','txt','IANA application/missing-blocks+cbor-seq registration'),
]
def sha(b): return hashlib.sha256(b).hexdigest()
for sub in ('raw','text','notes','figures'): (BASE/sub).mkdir(parents=True,exist_ok=True)
rows=[]
for ident,url,ext,version in SOURCES:
 r=requests.get(url,timeout=50); r.raise_for_status()
 raw=BASE/'raw'/f'{ident}.{ext}'; raw.write_bytes(r.content)
 dest=BASE/'text'/f'{ident}.txt'
 if ext=='pdf':
  subprocess.run(['pdftotext','-layout',str(raw),str(dest)],check=True)
  method='pdftotext -layout; LF retained with page form feeds'
 elif ext=='json':
  dest.write_text(json.dumps(r.json(),indent=2,ensure_ascii=False)+'\n')
  method='JSON pretty printing without information loss'
 elif ext=='html':
  soup=BeautifulSoup(r.content,'html.parser')
  for el in soup(['script','style']): el.decompose()
  dest.write_text(soup.get_text('\n',strip=True)+'\n')
  method='BeautifulSoup visible text, newline separator, script/style excluded'
 else:
  dest.write_bytes(r.content); method='byte-identical copy'
 row=dict(id=ident,url=url,final_url=r.url,retrieved_at=datetime.now(timezone.utc).isoformat(),status='downloaded',raw_path=str(raw.relative_to(ROOT)),sha256=sha(r.content),bytes=len(r.content),response_headers={k:v for k,v in r.headers.items() if k.lower() in ('content-type','etag','last-modified','date','content-length')},text_path=str(dest.relative_to(ROOT)),text_sha256=sha(dest.read_bytes()),extraction_method=method,source_version=version)
 rows.append(row)
 print(ident,len(r.content),'LF',len(dest.read_bytes().split(b'\n'))-(1 if dest.read_bytes().endswith(b'\n') else 0),r.url)
(BASE/'manifest.jsonl').write_text(''.join(json.dumps(row,sort_keys=True)+'\n' for row in rows))
