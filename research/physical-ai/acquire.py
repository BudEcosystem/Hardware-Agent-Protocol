"""Acquire immutable primary-source snapshots and extract readable text."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import datetime, hashlib, json, subprocess
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).parent
SOURCES=[
 ('openflexure-wot','https://arxiv.org/pdf/2101.00933','pdf'),
 ('openflexure-autofocus','https://arxiv.org/pdf/2109.06842','pdf'),
 ('gr00t-n1','https://arxiv.org/pdf/2503.14734','pdf'),
 ('openvla','https://arxiv.org/pdf/2406.09246','pdf'),
 ('gr00t-n16','https://research.nvidia.com/labs/gear/gr00t-n1_6/','html'),
 ('dgx-spark-hardware','https://docs.nvidia.com/dgx/dgx-spark/hardware.html','html'),
 ('isaac-lab','https://isaac-sim.github.io/IsaacLab/main/source/setup/ecosystem.html','html'),
]
def fetch(item):
 key,url,ext=item
 # Preserve existing evidence and reading annotations; refreshing needs a new ID.
 manifest=ROOT/'manifest.json'
 if manifest.exists():
  for previous in json.loads(manifest.read_text()):
   if previous.get('id')==key and previous.get('url')==url and previous.get('status')=='downloaded':
    return previous
 out={'id':key,'url':url,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reading_status':'unread'}
 try:
  r=requests.get(url,timeout=90);r.raise_for_status()
  p=ROOT/'raw'/f'{key}.{ext}';p.write_bytes(r.content)
  if ext=='pdf':
   if not r.content.startswith(b'%PDF'):raise ValueError('Not a PDF')
   subprocess.run(['pdftotext','-layout',str(p),str(ROOT/'text'/f'{key}.txt')],check=True)
  else:
   soup=BeautifulSoup(r.content,'html.parser')
   for el in soup(['script','style','nav','footer','header']):el.decompose()
   body=soup.find('main') or soup
   (ROOT/'text'/f'{key}.txt').write_text(body.get_text('\n',strip=True))
  out.update(status='downloaded',resolved_url=r.url,sha256=hashlib.sha256(r.content).hexdigest(),bytes=len(r.content),raw_path=str(p.relative_to(ROOT)),text_path=f'text/{key}.txt')
 except Exception as e:out.update(status='failed',error=str(e))
 return out
if __name__=='__main__':
 records=list(ThreadPoolExecutor(max_workers=4).map(fetch,SOURCES))
 manifest=ROOT/'manifest.json'
 previous=json.loads(manifest.read_text()) if manifest.exists() else []
 by_id={r['id']:r for r in previous}
 by_id.update({r['id']:r for r in records})
 records=list(by_id.values())
 manifest.write_text(json.dumps(records,indent=2)+'\n')
 print(json.dumps(records,indent=2))
