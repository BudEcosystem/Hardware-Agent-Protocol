#!/usr/bin/env python3
"""Acquire exact files from existing pinned trees, without executing sources."""
import requests,json,pathlib,hashlib,datetime,concurrent.futures
b=pathlib.Path('research/home');repos=json.loads((b/'repos.json').read_text());m=[json.loads(x) for x in (b/'manifest.jsonl').read_text().splitlines()]
items=[('esphome',f'esphome/components/{x}') for x in ['api/api_connection.h','api/subscribe_state.cpp','api/api_options.proto','noise/noise_handshake.cpp','noise/noise_handshake.h']]
def get(pair):
 rid,f=pair;r=next(x for x in repos if x['id']==rid);tree=json.loads(pathlib.Path(r['tree_metadata_path']).read_text());item=next(x for x in tree['tree'] if x['path']==f)
 url=r['repository'].replace('https://github.com/','https://raw.githubusercontent.com/')+'/'+r['commit']+'/'+f
 resp=requests.get(url,timeout=40);resp.raise_for_status();data=resp.content;sha=hashlib.sha256(data).hexdigest();blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest();assert blob==item['sha']
 p=b/'snapshots'/rid/f;p.parent.mkdir(exist_ok=True,parents=True);p.write_bytes(data)
 fi=dict(path=str(p),repository_path=f,url=url,git_blob_sha=blob,sha256=sha,bytes=len(data))
 me=dict(id=rid+':'+f,url=url,retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),repository=r['repository'],commit=r['commit'],repository_path=f,git_blob_sha=blob,reading_status='unread',http_status=200,final_url=resp.url,content_type=resp.headers.get('content-type'),raw_path=str(p),sha256=sha,bytes=len(data),extraction='Unmodified UTF-8 source; raw and text same bytes',text_path=str(p),text_sha256=sha,text_chars=len(data.decode()),acquisition_status='downloaded')
 return rid,fi,me
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: result=list(pool.map(get,items))
for rid,fi,me in result:
 next(x for x in repos if x['id']==rid)['files'].append(fi);m.append(me);print(rid,fi['repository_path'],fi['bytes'])
(b/'repos.json').write_text(json.dumps(repos,indent=2)+'\n');(b/'manifest.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in m))
