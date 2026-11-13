#!/usr/bin/env python3
"""Download public source text only. Never import or execute acquired source."""
import concurrent.futures, hashlib, json, pathlib, datetime, requests
from bs4 import BeautifulSoup
BASE=pathlib.Path('research/home'); BASE.mkdir(exist_ok=True,parents=True)
def sha(b): return hashlib.sha256(b).hexdigest()
def put(path,b): path.parent.mkdir(exist_ok=True,parents=True); path.write_bytes(b); return str(path)
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def fetch(url):
 r=requests.get(url,timeout=90); r.raise_for_status(); return r
configs=[('ha-contributors','home-assistant/contributors.home-assistant.io','main'),('ha-core','home-assistant/core','2026.11.0'),('ha-js-websocket','home-assistant/home-assistant-js-websocket','master'),('esphome','esphome/esphome','2026.10.2'),('esphome-docs','esphome/esphome.io','current')]
def pin(c):
 name,repo,ref=c
 r=fetch(f'https://api.github.com/repos/{repo}/commits/{ref}'); j=r.json(); commit=j['sha']; cp=BASE/'metadata'/f'{name}-commit.json'; put(cp,r.content)
 t=fetch(f'https://api.github.com/repos/{repo}/git/trees/{j["commit"]["tree"]["sha"]}?recursive=1'); tj=t.json(); tp=BASE/'metadata'/f'{name}-tree.json'; put(tp,t.content)
 if tj.get('truncated'): raise ValueError(name+' truncated tree')
 return dict(id=name,repository='https://github.com/'+repo,ref=ref,commit=commit,tree_sha=tj['sha'],retrieved_at=now(),commit_metadata_path=str(cp),commit_metadata_sha256=sha(r.content),tree_metadata_path=str(tp),tree_metadata_sha256=sha(t.content),scope='Selected complete source files only; no whole-repository acquisition or reading claim. Acquired source not executed.',files=[])
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex: repos=list(ex.map(pin,configs))
put(BASE/'repos.json',(json.dumps(repos,indent=2)+'\n').encode())
for x in repos:
 print(x['id'],x['commit'])
 tree=json.loads(pathlib.Path(x['tree_metadata_path']).read_text())['tree']
 if x['id']=='ha-contributors': print('\n'.join(a['path'] for a in tree if any(k in a['path'] for k in ['state','websocket','rest-api','fetching','events.md']) and a['type']=='blob'))
 if x['id']=='esphome-docs': print('\n'.join(a['path'] for a in tree if a['path'].endswith(('components/api.mdx','components/script.mdx','automations/actions.mdx','switch/template.mdx','cover/time_based.mdx'))))
