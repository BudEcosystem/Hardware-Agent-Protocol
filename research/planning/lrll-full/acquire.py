#!/usr/bin/env python3
"""Acquire official research documents and selected pinned source files; execute none."""
from datetime import datetime,timezone
import hashlib,json,subprocess
from pathlib import Path
import requests
from bs4 import BeautifulSoup
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
def sha(b):return hashlib.sha256(b).hexdigest()
def fetch(ident,url,ext,version,folder='raw'):
    destination=BASE/folder/f'{ident}.{ext}';destination.parent.mkdir(parents=True,exist_ok=True)
    row=dict(id=ident,url=url,retrieved_at=datetime.now(timezone.utc).isoformat(),source_version=version)
    try:
        r=requests.get(url,timeout=60);row.update(final_url=r.url,http_status=r.status_code)
        r.raise_for_status();destination.write_bytes(r.content)
        row.update(status='downloaded',raw_path=str(destination.relative_to(ROOT)),sha256=sha(r.content),bytes=len(r.content),response_headers={k:v for k,v in r.headers.items() if k.lower() in ('content-type','etag','last-modified','date','content-length')})
        text=BASE/'text'/f'{ident}.txt'
        if ext=='pdf':
            subprocess.run(['pdftotext','-layout',str(destination),str(text)],check=True);method='pdftotext -layout; LF with form feed preserved'
        elif ext=='html':
            soup=BeautifulSoup(r.content,'html.parser')
            for x in soup(['script','style']):x.decompose()
            text.write_text(soup.get_text('\n',strip=True)+'\n');method='BeautifulSoup visible text, newline-separated, scripts/styles excluded'
        elif ext=='json':text.write_text(json.dumps(r.json(),indent=2,ensure_ascii=False)+'\n');method='JSON pretty print'
        else:text.write_bytes(r.content);method='byte-identical copy'
        row.update(text_path=str(text.relative_to(ROOT)),text_sha256=sha(text.read_bytes()),extraction_method=method)
    except Exception as e:
        row.update(status='failed',error=f'{type(e).__name__}: {e}')
    with (BASE/'manifest.jsonl').open('a') as f:f.write(json.dumps(row,sort_keys=True)+'\n')
    print(ident,row['status'],row.get('bytes'),row.get('error',''),flush=True)
    return row
if __name__=='__main__':
    fetch('lrll-status','https://arxiv.org/abs/2406.18746','html','arXiv status snapshot')
    fetch('lrll-v2','https://arxiv.org/pdf/2406.18746v2','pdf','arXiv:2406.18746v2, 2024-07-15')
