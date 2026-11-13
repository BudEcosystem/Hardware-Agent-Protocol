#!/usr/bin/env python3
"""Public text acquisition only; acquired programs are not executed."""
import concurrent.futures,hashlib,json,pathlib,datetime,requests
from bs4 import BeautifulSoup
BASE=pathlib.Path('research/home')
def sha(b): return hashlib.sha256(b).hexdigest()
def put(p,b): p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b)
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
repos=json.loads((BASE/'repos.json').read_text())
selection={
 'ha-contributors':['src/content/docs/core/internals/websocket-api.md','src/content/docs/core/internals/rest-api.md','src/content/docs/core/internals/states.md','src/content/docs/core/internals/events.md','src/content/docs/core/entities/state-updates.md','src/content/docs/core/entities/state-attributes.md','src/content/docs/core/integrations/fetching-data.md'],
 'ha-core':['homeassistant/components/websocket_api/commands.py','homeassistant/components/websocket_api/connection.py','homeassistant/components/api/__init__.py'],
 'ha-js-websocket':['lib/connection.ts','lib/entities.ts','lib/collection.ts'],
 'esphome':['esphome/components/api/api.proto','esphome/components/api/api_connection.cpp','esphome/components/api/api_server.cpp','esphome/components/api/api_frame_helper.cpp','esphome/components/api/api_frame_helper_noise.cpp','esphome/components/template/switch/template_switch.cpp','esphome/components/time_based/cover/time_based_cover.cpp'],
 'esphome-docs':['src/content/docs/components/api.mdx','src/content/docs/automations/actions.mdx','src/content/docs/components/script.mdx','src/content/docs/components/switch/template.mdx','src/content/docs/components/cover/time_based.mdx'],
}
work=[]
for repo in repos:
 tree={x['path']:x for x in json.loads(pathlib.Path(repo['tree_metadata_path']).read_text())['tree']}
 for f in selection[repo['id']]:
  if f not in tree:
   print('MISSING',repo['id'],f); continue
  work.append((repo,f,tree[f]['sha']))
def acquire(item):
 repo,f,blob=item; u=repo['repository'].replace('https://github.com/','https://raw.githubusercontent.com/')+'/'+repo['commit']+'/'+f
 r=requests.get(u,timeout=60);r.raise_for_status();b=r.content
 actual=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
 assert actual==blob,(f,actual,blob)
 p=BASE/'snapshots'/repo['id']/f; put(p,b)
 file=dict(path=str(p),repository_path=f,url=u,git_blob_sha=blob,sha256=sha(b),bytes=len(b))
 record=dict(id=repo['id']+':'+f,url=u,retrieved_at=now(),repository=repo['repository'],commit=repo['commit'],repository_path=f,git_blob_sha=blob,reading_status='unread',http_status=r.status_code,final_url=r.url,content_type=r.headers.get('content-type'),raw_path=str(p),sha256=sha(b),bytes=len(b),extraction='Unmodified UTF-8 source; raw and text are the same bytes',text_path=str(p),text_sha256=sha(b),text_chars=len(b.decode()),acquisition_status='downloaded')
 return repo['id'],file,record
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex: results=list(ex.map(acquire,work))
records=[]
for rid,file,rec in results:
 next(x for x in repos if x['id']==rid)['files'].append(file);records.append(rec)
 print(rid,file['repository_path'],rec['bytes'],len(pathlib.Path(file['path']).read_bytes().splitlines()))
# Preserve current published state-object page, including raw HTML.
u='https://www.home-assistant.io/docs/configuration/state_object/'
r=requests.get(u,timeout=60);r.raise_for_status();s=BeautifulSoup(r.content,'html.parser');body=s.find('article') or s.find('main') or s.body
for x in body.select('script,style,nav'):x.decompose()
t=body.get_text('\n',strip=True)+'\n'; rp=BASE/'raw'/'ha-state-object.html';tp=BASE/'text'/'ha-state-object.txt';put(rp,r.content);put(tp,t.encode())
records.append(dict(id='ha-state-object',url=u,retrieved_at=now(),reading_status='unread',http_status=r.status_code,final_url=r.url,content_type=r.headers.get('content-type'),raw_path=str(rp),sha256=sha(r.content),bytes=len(r.content),extraction='BeautifulSoup article fallback main/body; script/style/nav removed; get_text newline strip; HTML retained',text_path=str(tp),text_sha256=sha(t.encode()),text_chars=len(t),acquisition_status='downloaded'))
put(BASE/'repos.json',(json.dumps(repos,indent=2)+'\n').encode());put(BASE/'manifest.jsonl',''.join(json.dumps(x)+'\n' for x in records).encode())
